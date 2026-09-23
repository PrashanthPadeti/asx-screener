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
from compute.engine.universe_writer import column_for  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

# Paid, because the CSV export is gated behind one and a 401 would skip the
# surface rather than prove it. Same reasoning as Gate A.
app.dependency_overrides[get_current_user] = lambda: {"plan": "pro", "id": 1}

GOVERNED = GOVERNED_METRICS[LATEST_MODEL_VERSION]
COL2CANON = {column_for(m): m for m in GOVERNED}
API_GOV = {c: m for c, m in COL2CANON.items() if c in ScreenerRow.model_fields}
CSV_GOV = sorted(set(COL2CANON) & set(_EXPORT_COLS))

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


def check(ok: bool, message: str) -> None:
    if not ok:
        breaches.append(message)
    print(f"  {'PASS' if ok else 'FAIL'}  {message}")


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
          f"run {run_id} model is {model}, this build serves "
          f"{LATEST_MODEL_VERSION}")

    plan = PLANS.get(plan_name)
    check(plan is not None,
          f"run {run_id} plan {plan_name!r} is unknown to this build; the "
          f"resolver could not evaluate its requirements")
    if plan is None:
        return

    cur.execute("""
        SELECT stage_name, status FROM screener.compute_run_stages
         WHERE run_id = %s;""", (run_id,))
    stages = dict(cur.fetchall())
    missing = [s for s in plan.required if stages.get(s) != "success"]
    check(not missing,
          f"run {run_id} ({plan_name}) required stages not SUCCESS: {missing}")

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
          f"run {run_id} finalised over {rows_written:,} rows and now holds "
          f"none; it has been wholly superseded and is not what is being served")
    print(f"        run {run_id} | {model} | {plan_name} | "
          f"{rows_written:,} rows written, {attributed_now:,} still attributed "
          f"| {violations} recorded violations | "
          f"{len(plan.required)} required stages")


def resolver_selects(cur, run_id: int) -> None:
    """The exact run, and nothing unfinalised — however new."""
    servable = validated_run_ids(cur)
    check(run_id in servable,
          f"the resolver does not serve run {run_id}; it serves {servable}")

    cur.execute("""
        SELECT r.id FROM screener.compute_runs r
          LEFT JOIN screener.compute_run_finalizations f ON f.run_id = r.id
         WHERE f.run_id IS NULL;""")
    unfinalised = [r[0] for r in cur.fetchall()]
    leaked = sorted(set(unfinalised) & set(servable))
    check(not leaked,
          f"unfinalised runs are servable: {leaked}. A failed run must never "
          f"be selected, however recent.")
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
    for metric, column in COL2CANON.items():
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
          f"{contradictions} value/state contradictions across {sampled} "
          f"governed columns in storage")

    cur.execute(f"""
        SELECT count(*) FROM screener.universe u
         WHERE {serving_predicate('u')} AND u.metric_states IS NULL
           AND u.compute_run_id = %s;""", (run_id,))
    unassessed = cur.fetchone()[0]
    check(unassessed == 0,
          f"{unassessed} rows attributed to run {run_id} carry NO sidecar; "
          f"values and states must be written together")

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
          f"{unattributed:,} of {serving:,} served companies are attributed to "
          f"no validated run ({servable}); their governed fields are withheld "
          f"from every client")
    print(f"        serving population {serving:,}, unattributed {unattributed:,}")


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
    check(response.status_code == 200,
          f"screen returned {response.status_code}, want 200")
    if response.status_code != 200:
        return
    body = response.json()
    rows = body.get("data", [])
    check(bool(rows), "screen returned no rows; the gate would prove nothing")
    check(body.get("snapshot") is not None,
          "response carries no snapshot identifier after publication")
    check(run_id in (body.get("run_ids") or []),
          f"the API resolved snapshot {body.get('snapshot')} over runs "
          f"{body.get('run_ids')}, which does not include the published run "
          f"{run_id}")
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

    check(served > 0,
          "no governed value was served on any row; publication achieved "
          "nothing a client can see")
    check(in_scope_rows > 0,
          f"none of the sampled rows is attributed to run {run_id}; the "
          f"projection assertions measured nothing about this publication")
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
    check(req.status_code == 200, f"governed filter {req.status_code}, want 200")
    if req.status_code != 200:
        return
    rows = req.json().get("data", [])
    check(bool(rows), f"filtering on {column} returned nothing to judge")

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
          f"REQUIRED filter admitted rows it must exclude: {bad[:3]}")
    print(f"        required-filter rows={len(rows)} violations={len(bad)}")

    # Sorting must rank the applicable subset, never coerce a suppression to
    # an extreme. A NULL sorted as -infinity would put every unproven company
    # at one end of a ranking users read as a league table.
    ordered = [r.get(column) for r in rows if r.get(column) is not None]
    check(ordered == sorted(ordered, reverse=True),
          f"a descending ranking on {column} is not descending: {ordered[:5]}")

    exclusion = req.json().get("excluded_from_ordering")
    ranked_total = req.json().get("ranked_total")
    check(ranked_total is not None,
          f"ordering by governed {column} reported no ranked_total, so the "
          f"client cannot tell screen membership from the ranked subset")
    print(f"        ranked_total={ranked_total} excluded={exclusion}")


def export_containment(client, cur, run_id: int) -> None:
    """The CSV obeys the same rules as the API, on the same rows."""
    export = client.post("/api/v1/screener/export",
                         json={"filters": [], "sort_by": "market_cap",
                               "page_size": 25})
    check(export.status_code == 200,
          f"csv export {export.status_code}, want 200")
    if export.status_code != 200:
        return

    rows = list(csv.reader(io.StringIO(export.text)))
    check(len(rows) > 1, "csv has no data rows")
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
    check(populated > 0,
          "the export carries no governed values at all; containment cannot "
          "be distinguished from an empty file")
    print(f"        csv governed cells: populated={populated} blank={blank}")


def unknown_contract_fails_closed(cur, run_id: int) -> None:
    """An unrecognised model or plan must serve nothing, not everything."""
    from compute.engine.run_resolution import validated_runs_sql_psycopg

    cur.execute(validated_runs_sql_psycopg(),
                {"supported": ["NO_SUCH_MODEL"],
                 "plan_requirements": json.dumps(plan_requirements()),
                 "limit": 8})
    check(not cur.fetchall(),
          "a run was served under an unsupported factor model")

    cur.execute(validated_runs_sql_psycopg(),
                {"supported": list(GOVERNED_METRICS.keys()),
                 "plan_requirements": json.dumps({"NO_SUCH_PLAN": []}),
                 "limit": 8})
    served = [r[0] for r in cur.fetchall()]
    check(run_id not in served,
          f"run {run_id} was served while its plan was unknown to the "
          f"resolver; an unrecognised contract must fail closed")


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
