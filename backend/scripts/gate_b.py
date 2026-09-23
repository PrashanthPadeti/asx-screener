"""
Gate B — post-recompute publication contract
============================================
Gate A proved that while no validated contract exists, no governed
observation escapes and every absence carries a reason. Once a canonical run
is finalised that premise is gone, and the opposite question becomes the
release question:

    are governed values now SERVED, for exactly the run that was published,
    and is everything withheld from them withheld for a stated reason that
    the contract actually supports

Both halves matter and the second is the one that catches real defects. A
surface that serves nothing passes "nothing leaked" perfectly.

Run-anchored, never "latest"
----------------------------
The gate validates ONE finalised run, named on the command line or resolved
once and printed. Every assertion is then about that run id. This is not
fussiness: the scratch database carries five runs, two of which are dead, and
an assertion about "the most recent finalisation" would have quietly changed
subject between the publication and the gate. Pass the id the publication
printed:

    python scripts/gate_b.py --run-id 5

Read-only. It opens one connection, issues SELECTs, and never writes: a
release gate that mutates the thing it is judging cannot be rerun to check
itself.

    cd /opt/asx-screener/backend && ../asx-venv/bin/python scripts/gate_b.py
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psycopg2  # noqa: E402

from app.api.v1.routes.screener import _EXPORT_COLS  # noqa: E402
from app.core.db import get_database_url_sync  # noqa: E402
from app.core.deps import get_current_user  # noqa: E402
from app.core.row_projection import NOT_ASSESSED, NO_CONTRACT, OUTSIDE_SNAPSHOT  # noqa: E402
from app.main import app  # noqa: E402
from app.schemas.screener import ScreenerRow  # noqa: E402
from compute.engine.metric_states import (  # noqa: E402
    GOVERNED_METRICS, LATEST_MODEL_VERSION,
)
from compute.engine.run_plans import PLANS, plan_requirements  # noqa: E402
from compute.engine.run_resolution import validated_run_ids  # noqa: E402
from compute.engine.serving_population import serving_predicate  # noqa: E402
from compute.engine.universe_writer import persisted_governed  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

# Paid, because the CSV export is gated behind one and a 401 would skip the
# surface rather than prove it. Same reasoning as Gate A.
app.dependency_overrides[get_current_user] = lambda: {"plan": "pro", "id": 1}

GOVERNED = GOVERNED_METRICS[LATEST_MODEL_VERSION]

#: column -> canonical metric, for the metrics this model version actually
#: STORES. Not `column_for(m) for m in GOVERNED`: that is what Gate A uses, and
#: it is safe there only because Gate A never touches a storage column — it
#: intersects with ScreenerRow and the export header, and NOT_PERSISTED metrics
#: fall out on their own. Gate B queries screener.universe directly, so the
#: same expression reached for u.dividend_payout_ratio, a governed metric with
#: no column at all, and the gate died on UndefinedColumn mid-assertion.
COL2CANON = {c: m for m, c in persisted_governed(LATEST_MODEL_VERSION).items()}
API_GOV = {c: m for c, m in COL2CANON.items() if c in ScreenerRow.model_fields}
CSV_GOV = sorted(set(COL2CANON) & set(_EXPORT_COLS))

#: Governed but not stored, so no storage assertion can cover them. Named here
#: and reported in the evidence: a gate that quietly narrows its own scope is
#: how a green result stops meaning what its reader thinks it means.
UNSTORED = sorted(GOVERNED - set(persisted_governed(LATEST_MODEL_VERSION)))

#: The reasons the projector synthesises when it withholds for a CONTRACT-level
#: cause rather than an assessed one. A row ATTRIBUTED TO THE PUBLISHED RUN must
#: never carry one: they say "this row's relationship to the contract is
#: broken", which is what publication was supposed to fix. A row attributed
#: elsewhere may legitimately carry OUTSIDE_SNAPSHOT — membership is
#: deliberately not scoped to the run, so a newly listed company appears in an
#: ungoverned screen with its governed fields failed closed. That distinction is
#: the whole assertion: the gate must measure per row, against storage.
CONTRACT_LEVEL_REASONS = {NO_CONTRACT, OUTSIDE_SNAPSHOT, NOT_ASSESSED}

breaches: list[str] = []


def check(ok: bool, claim: str, detail: str = "") -> None:
    """`claim` is what must be TRUE; `detail` says what was found instead.

    The first draft passed one string, phrased as the failure. It printed
    "PASS  the resolver does not serve run 5; it serves [5, 4, 2, 1]" — a
    correct result rendered as its own contradiction. A release gate's output
    is read months later by someone deciding whether a publication was sound,
    and evidence that has to be mentally inverted to be understood will
    eventually be read the wrong way round.
    """
    if not ok:
        breaches.append(f"{claim}{f' — {detail}' if detail else ''}")
    print(f"  {'PASS' if ok else 'FAIL'}  {claim}"
          + (f"\n        {detail}" if detail and not ok else ""))


# ── The anchor ───────────────────────────────────────────────────────────────

def resolve_anchor(cur, requested: int | None) -> tuple[int, str, str]:
    """The one finalised run this gate is about. Returns (id, model, plan)."""
    cur.execute("""
        SELECT r.id, r.factor_model_version, r.plan_name
          FROM screener.compute_runs r
          JOIN screener.compute_run_finalizations f ON f.run_id = r.id
         WHERE (%s::bigint IS NULL OR r.id = %s)
         ORDER BY r.run_at DESC
         LIMIT 1;""", (requested, requested))
    row = cur.fetchone()
    if row is None:
        raise SystemExit(
            f"GATE B CANNOT RUN: no finalised run"
            + (f" with id {requested}" if requested else "")
            + ". Gate B validates a publication; without one there is nothing "
              "to validate and a pass would mean nothing.")
    return row


# ── The assertions ───────────────────────────────────────────────────────────

def lifecycle(cur, run_id: int, model: str, plan_name: str) -> None:
    """Finalisation, plan-specific required stages, and a clean read-back."""
    check(model == LATEST_MODEL_VERSION,
          f"run {run_id} was computed under the model this build serves",
          f"run model is {model}, this build serves {LATEST_MODEL_VERSION}")

    plan = PLANS.get(plan_name)
    check(plan is not None,
          f"run {run_id}'s plan {plan_name!r} is known to this build",
          "the resolver cannot evaluate the requirements of a plan it has "
          "never heard of")
    if plan is None:
        return

    cur.execute("""
        SELECT stage_name, status FROM screener.compute_run_stages
         WHERE run_id = %s;""", (run_id,))
    stages = dict(cur.fetchall())
    missing = [s for s in plan.required if stages.get(s) != "success"]
    check(not missing,
          f"every stage {plan_name} requires succeeded for run {run_id}",
          f"not SUCCESS: {missing}")

    # The recorded violation count is not evidence: finalise() refuses to
    # insert a row with a non-zero one, so reading it back can only ever say
    # "zero". What CAN have changed since is the population itself — that is
    # the V2 temporal invariant, that no writer touches a governed column
    # outside a canonical run without invalidating the contract atomically. So
    # re-derive the attributed count now and hold the finalisation to it.
    cur.execute("""
        SELECT rows_written, persistence_violations
          FROM screener.compute_run_finalizations WHERE run_id = %s;""",
        (run_id,))
    rows_written, violations = cur.fetchone()
    # Not an equality against rows_written: a snapshot spans several runs, and
    # a later publication legitimately re-attributes rows away from an earlier
    # one. What must hold is that this run still carries rows — a publication
    # every one of whose rows has been superseded is not the one serving, and
    # validating it would answer a question nobody asked.
    cur.execute("""
        SELECT count(*) FROM screener.universe WHERE compute_run_id = %s;""",
        (run_id,))
    attributed_now = cur.fetchone()[0]
    check(attributed_now > 0,
          f"run {run_id} still holds attributed rows",
          f"it finalised over {rows_written:,} rows and now holds none, so it "
          f"has been wholly superseded and is not what is being served")
    print(f"        run {run_id} | {model} | {plan_name} | "
          f"{rows_written:,} rows written, {attributed_now:,} still attributed "
          f"| {violations} recorded violations | "
          f"{len(plan.required)} required stages")


def resolver_selects(cur, run_id: int) -> None:
    """The exact run, and nothing unfinalised — however new."""
    servable = validated_run_ids(cur)
    check(run_id in servable,
          f"the resolver serves run {run_id}",
          f"it serves {servable}")

    cur.execute("""
        SELECT r.id FROM screener.compute_runs r
          LEFT JOIN screener.compute_run_finalizations f ON f.run_id = r.id
         WHERE f.run_id IS NULL;""")
    unfinalised = [r[0] for r in cur.fetchall()]
    leaked = sorted(set(unfinalised) & set(servable))
    check(not leaked,
          "no unfinalised run is servable, however recent",
          f"these are both unfinalised and servable: {leaked}")
    newer = [r for r in unfinalised if r > run_id]
    print(f"        servable={servable} unfinalised={unfinalised} "
          f"newer-unfinalised={newer or 'none'}")


def storage_contract(cur, run_id: int) -> None:
    """Suppressed means persisted NULL, not hidden at projection.

    The distinction the canonical boundary froze. A value withheld only by
    the projector is still in the database, still exported by anything that
    reads the column directly, and still ranked by any query that forgets the
    applicability clause. persist_row() nulls it; this proves it did.
    """
    contradictions = 0
    sampled = 0
    # COL2CANON is column -> metric. Destructured the other way round, this
    # loop passed the metric name as a column: `u.dividend_payout_ratio`,
    # whose column is `payout_ratio`. The two names coincide for most governed
    # metrics, so the aliased ones were the only ones that could expose it --
    # and they did, on the first real run.
    for column, metric in COL2CANON.items():
        cur.execute(f"""
            SELECT count(*) FROM screener.universe u
             WHERE u.compute_run_id = %s
               AND u.metric_states ? %s
               AND u.{column} IS NOT NULL;""", (run_id, metric))
        n = cur.fetchone()[0]
        sampled += 1
        contradictions += n
        if n:
            breaches.append(f"{metric}: {n} rows carry BOTH a suppression "
                            f"entry and a stored value")
    check(contradictions == 0,
          f"a suppressed metric is persisted NULL across all {sampled} stored "
          f"governed columns, not merely hidden at projection",
          f"{contradictions} rows carry both a suppression entry and a value")

    cur.execute(f"""
        SELECT count(*) FROM screener.universe u
         WHERE {serving_predicate('u')} AND u.metric_states IS NULL
           AND u.compute_run_id = %s;""", (run_id,))
    unassessed = cur.fetchone()[0]
    check(unassessed == 0,
          f"every served row attributed to run {run_id} carries a sidecar",
          f"{unassessed} carry none; values and states must be written "
          f"together or the value cannot be interpreted")

    # The canonical read-back, live and over the whole servable set rather
    # than one run: every company the product serves must be attributed to
    # SOME validated run. A row in the serving population attributed to none
    # of them has its governed fields failed closed, which is safe but is not
    # a published product.
    servable = validated_run_ids(cur)
    cur.execute(f"""
        SELECT count(*) FROM screener.universe u
         WHERE {serving_predicate('u')}
           AND (u.compute_run_id IS NULL OR NOT (u.compute_run_id = ANY(%s)));""",
        (servable,))
    unattributed = cur.fetchone()[0]
    cur.execute(f"""
        SELECT count(*) FROM screener.universe u
         WHERE {serving_predicate('u')};""")
    serving = cur.fetchone()[0]
    check(unattributed == 0,
          f"all {serving:,} served companies are attributed to a validated run",
          f"{unattributed:,} are attributed to none of {servable}, so their "
          f"governed fields are withheld from every client")
    print(f"        serving population {serving:,}, unattributed {unattributed:,}")
    if UNSTORED:
        print(f"        NOT covered by any storage assertion (governed but "
              f"not persisted): {', '.join(UNSTORED)}")


def attribution_of(cur, codes: list[str]) -> dict:
    """asx_code -> the run each row is actually attributed to, from storage.

    The projector strips compute_run_id from responses, so the API cannot say
    which side of the snapshot boundary a row sits on. Without that, every
    OUTSIDE_SNAPSHOT looks the same as a defect, and the gate either passes
    everything or fails everything.
    """
    cur.execute("""
        SELECT asx_code, compute_run_id FROM screener.universe
         WHERE asx_code = ANY(%s);""", (codes,))
    return dict(cur.fetchall())


def api_projection(client, cur, run_id: int) -> None:
    """Attributed values are served; every absence has a real cause."""
    response = client.post("/api/v1/screener",
                           json={"filters": [], "sort_by": "market_cap",
                                 "page_size": 50})
    check(response.status_code == 200, "the screen endpoint answers 200",
          f"it returned {response.status_code}")
    if response.status_code != 200:
        return
    body = response.json()
    rows = body.get("data", [])
    check(bool(rows), "the screen returns rows to judge",
          "it returned none, so every projection assertion below would pass "
          "vacuously")
    check(body.get("snapshot") is not None,
          "the response carries a snapshot identifier",
          "it carries none, which means no validated contract was resolvable")
    check(run_id in (body.get("run_ids") or []),
          f"the API's own resolved snapshot includes run {run_id}",
          f"it resolved {body.get('snapshot')} over runs {body.get('run_ids')}")
    print(f"        snapshot={body.get('snapshot')} "
          f"run_ids={body.get('run_ids')} rows={len(rows)}")

    attributed = attribution_of(cur, [r["asx_code"] for r in rows])
    served = blank = outside = in_scope_rows = 0
    for row in rows:
        code = row["asx_code"]
        in_scope = attributed.get(code) == run_id
        in_scope_rows += in_scope
        states = row.get("metric_states") or {}
        for column, metric in API_GOV.items():
            entry = states.get(metric)
            value = row.get(column)
            if entry is None:
                # Inside a validated contract, no entry means APPLICABLE — so a
                # value must be present. A null here is the silent blank the
                # whole programme exists to eliminate.
                if value is None:
                    blank += 1
                    breaches.append(f"{code}: {metric} is null with no "
                                    f"sidecar entry")
                else:
                    served += 1
                continue
            if value is not None:
                breaches.append(f"{code}: {metric} carries a suppression "
                                f"entry AND a value")
            if "observed" in entry:
                breaches.append(f"{code}: {metric} leaked observed")
            if entry.get("reason") in CONTRACT_LEVEL_REASONS:
                if in_scope:
                    breaches.append(
                        f"{code}: {metric} withheld as {entry['reason']!r} "
                        f"although the row IS attributed to run {run_id}")
                else:
                    outside += 1

    check(served > 0, "governed values are actually served to clients",
          "not one governed value appeared on any row, so the publication "
          "achieved nothing a client can see")
    check(in_scope_rows > 0,
          f"the sampled rows include some attributed to run {run_id}",
          "none are, so the projection assertions measured nothing about "
          "this publication")
    print(f"        rows-in-scope={in_scope_rows}/{len(rows)} served={served} "
          f"unexplained-blanks={blank} out-of-scope-suppressions={outside}")


def busiest_governed_metric(cur, run_id: int) -> tuple[str, str]:
    """The governed metric with the most applicable rows under this run.

    Chosen from data rather than hardcoded. A gate that always filters on `roe`
    proves the contract for `roe`, and silently proves nothing on the day that
    one metric happens to be unavailable everywhere — which is exactly the day
    it matters.
    """
    best, count = None, -1
    for column, metric in API_GOV.items():
        cur.execute(f"""
            SELECT count(*) FROM screener.universe
             WHERE compute_run_id = %s AND {column} IS NOT NULL
               AND NOT (metric_states ? %s);""", (run_id, metric))
        n = cur.fetchone()[0]
        if n > count:
            best, count = (metric, column), n
    if best is None or count <= 0:
        raise SystemExit(
            f"GATE B CANNOT RUN: run {run_id} has no governed metric with a "
            f"single applicable row. Filtering and ranking assertions would "
            f"pass vacuously.")
    print(f"        filtering on {best[0]} ({count:,} applicable rows)")
    return best


def three_valued_filter(client, metric: str, column: str) -> None:
    """Unproven does not become false, and is not coerced into an order.

    REQUIRED  applicable AND predicate
    EXCLUDED  NOT (applicable AND predicate)   -- unproven does not reject
    ORDERED   applicable                       -- the ranking subset
    """
    req = client.post("/api/v1/screener",
                      json={"filters": [{"field": column, "operator": "gt",
                                         "value": 0}],
                            "sort_by": column, "sort_dir": "desc",
                            "page_size": 25})
    check(req.status_code == 200,
          f"a screen filtered on governed {column} answers 200",
          f"it returned {req.status_code}")
    if req.status_code != 200:
        return
    rows = req.json().get("data", [])
    check(bool(rows), f"filtering on {column} returns rows to judge",
          "it returned none, so the REQUIRED assertion below is vacuous")

    bad = []
    for row in rows:
        states = row.get("metric_states") or {}
        if metric in states:
            bad.append(f"{row['asx_code']} suppressed but matched")
        elif row.get(column) is None:
            bad.append(f"{row['asx_code']} null but matched")
        elif row.get(column) <= 0:
            bad.append(f"{row['asx_code']}={row.get(column)} fails the predicate")
    check(not bad,
          f"every row matching the {column} filter is applicable AND satisfies "
          f"the predicate",
          f"these were admitted and must not have been: {bad[:3]}")
    print(f"        required-filter rows={len(rows)} violations={len(bad)}")

    # Sorting must rank the applicable subset, never coerce a suppression to
    # an extreme. A NULL sorted as -infinity would put every unproven company
    # at one end of a ranking users read as a league table.
    ordered = [r.get(column) for r in rows if r.get(column) is not None]
    check(ordered == sorted(ordered, reverse=True),
          f"the descending ranking on {column} is monotonic, with no "
          f"suppression coerced to an extreme",
          f"the served order was {ordered[:5]}")

    exclusion = req.json().get("excluded_from_ordering")
    ranked_total = req.json().get("ranked_total")
    check(ranked_total is not None,
          f"ordering by governed {column} reports the ranked subset separately "
          f"from screen membership",
          "ranked_total is absent, so the client cannot tell the two apart")
    print(f"        ranked_total={ranked_total} excluded={exclusion}")


def export_containment(client, cur, run_id: int) -> None:
    """The CSV obeys the same rules as the API, on the same rows."""
    export = client.post("/api/v1/screener/export",
                         json={"filters": [], "sort_by": "market_cap",
                               "page_size": 25})
    check(export.status_code == 200, "the CSV export answers 200",
          f"it returned {export.status_code}")
    if export.status_code != 200:
        return

    rows = list(csv.reader(io.StringIO(export.text)))
    check(len(rows) > 1, "the CSV carries data rows",
          "it carries only a header")
    index = {name: i for i, name in enumerate(_EXPORT_COLS)}

    populated = blank = 0
    for line in rows[1:11]:
        code = line[0]
        cur.execute("""
            SELECT metric_states FROM screener.universe
             WHERE asx_code = %s AND compute_run_id = %s;""", (code, run_id))
        found = cur.fetchone()
        if not found:
            continue
        states = found[0] or {}
        if isinstance(states, str):
            states = json.loads(states)
        for column in CSV_GOV:
            if index[column] >= len(line):
                continue
            cell = line[index[column]].strip()
            metric = COL2CANON[column]
            if metric in states and cell:
                breaches.append(f"csv {code}: {column} suppressed in the API "
                                f"but populated in the export ({cell!r})")
            populated += bool(cell)
            blank += not cell
    check(populated > 0, "the export carries governed values",
          "it carries none, so containment cannot be distinguished from an "
          "empty file")
    print(f"        csv governed cells: populated={populated} blank={blank}")


def unknown_contract_fails_closed(cur, run_id: int) -> None:
    """An unrecognised model or plan must serve nothing, not everything."""
    from compute.engine.run_resolution import validated_runs_sql_psycopg

    cur.execute(validated_runs_sql_psycopg(),
                {"supported": ["NO_SUCH_MODEL"],
                 "plan_requirements": json.dumps(plan_requirements()),
                 "limit": 8})
    check(not cur.fetchall(),
          "an unsupported factor model serves nothing",
          "a run was served under model 'NO_SUCH_MODEL'")

    cur.execute(validated_runs_sql_psycopg(),
                {"supported": list(GOVERNED_METRICS.keys()),
                 "plan_requirements": json.dumps({"NO_SUCH_PLAN": []}),
                 "limit": 8})
    served = [r[0] for r in cur.fetchall()]
    check(run_id not in served,
          "a plan unknown to the resolver serves nothing",
          f"run {run_id} was served while its plan was absent from the "
          f"requirements map; an unrecognised contract must fail closed")


# ── Entry point ──────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", type=int, default=None,
                        help="The finalised run to validate. Pass the id the "
                             "publication printed; omitted, the newest "
                             "finalised run is resolved and reported.")
    args = parser.parse_args()

    conn = psycopg2.connect(get_database_url_sync())
    conn.set_session(readonly=True, autocommit=True)
    cur = conn.cursor()

    cur.execute("SELECT current_database()")
    database = cur.fetchone()[0]

    # Prove the read-only claim rather than asserting it in a docstring. With
    # autocommit on, the refusal costs nothing and leaves no state behind; if
    # this write SUCCEEDS the gate can mutate what it is judging, and a green
    # result from it would be worth nothing.
    try:
        cur.execute("CREATE TEMP TABLE gate_b_write_probe (x int)")
        raise SystemExit(
            "GATE B REFUSES TO RUN: its own session accepted a write. A "
            "release gate that can modify the publication it is validating "
            "cannot be trusted to have validated it.")
    except psycopg2.errors.ReadOnlySqlTransaction:
        pass

    # Every column the gate is about to name, checked once, before any
    # assertion. The alternative is what actually happened twice: the gate
    # crashes on UndefinedColumn part-way through, having printed PASS for the
    # assertions it reached and nothing at all for the ones it did not — a
    # partial result that looks like a report.
    cur.execute("""
        SELECT column_name FROM information_schema.columns
         WHERE table_schema = 'screener' AND table_name = 'universe';""")
    present = {r[0] for r in cur.fetchall()}
    absent = sorted(set(COL2CANON) - present)
    if absent:
        raise SystemExit(
            f"GATE B CANNOT RUN: {LATEST_MODEL_VERSION} governs metrics whose "
            f"storage columns are absent from screener.universe: {absent}. "
            f"Either the database is behind the model version, or the gate is "
            f"naming columns wrongly; both must be settled before any "
            f"assertion about persistence means anything.")

    run_id, model, plan_name = resolve_anchor(cur, args.run_id)
    print(f"\nGATE B — database {database}, run {run_id}, model {model}, "
          f"plan {plan_name}")
    if args.run_id is None:
        print("  (run resolved, not supplied — pass --run-id to anchor "
              "explicitly)")
    print()

    print("lifecycle")
    lifecycle(cur, run_id, model, plan_name)
    print("resolver")
    resolver_selects(cur, run_id)
    print("storage contract")
    storage_contract(cur, run_id)
    print("unknown contract")
    unknown_contract_fails_closed(cur, run_id)

    with TestClient(app) as client:
        print("api projection")
        api_projection(client, cur, run_id)
        print("three-valued filter and ranking")
        metric, column = busiest_governed_metric(cur, run_id)
        three_valued_filter(client, metric, column)
        print("export containment")
        export_containment(client, cur, run_id)

    cur.close()
    conn.close()

    print()
    if breaches:
        print(f"GATE B FAILED — {len(breaches)} breach(es) on run {run_id}:")
        for breach in breaches:
            print("  -", breach)
        return 1
    print(f"GATE B PASSED — run {run_id} ({model}/{plan_name}) is published, "
          f"served, and contained")
    return 0


if __name__ == "__main__":
    sys.exit(main())
