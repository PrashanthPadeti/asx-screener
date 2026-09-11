"""
The clean zero: a bank's EV/EBITDA of 0.0, through every layer
==============================================================
Observed in production on 11 Sep 2026. A live TestClient smoke against the
production database returned, for CBA:

    ev_to_ebitda = 0.0
    current_ratio = 0.0643

as ordinary numeric values, with no applicability state, despite BANK-domain
suppression rules.

0.0 is more dangerous than an absurd number. It looks clean, sorts cleanly,
serialises cleanly, and survives every "is this plausible?" glance. Sorted
ascending on EV/EBITDA it places the four major banks at the top of the
cheapest companies on the ASX — a very strong false signal produced by a
value nobody would flag by eye.

Two distinct defects produce it, and only one of them is fixed:

    containment    the invalid number can leave the API, export and ranking
                   surfaces. Closed by projection, even against legacy
                   storage, and proven by Gate A on 6f265f8.

    persistence    the number exists in the governed numeric column at all.
                   Closed only by canonical assessment plus recompute. Still
                   open — this is Gate B.

This fixture is the adversarial case for the whole stack, so a failure here
names a specific downstream semantics leak rather than a general one. The
target state after recompute:

    ev_to_ebitda column          NULL
    metric_states["ev_ebitda"]   state=not_meaningful, cause=domain,
                                 observed=0.0   (database only)
    customer payload             ev_to_ebitda=null, state and cause, no
                                 observed

Run under pytest, or standalone:
    cd /opt/asx-screener/backend && ../asx-venv/bin/python tests/test_bank_ev_ebitda_zero.py
"""

import ast
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.parsed_query import (  # noqa: E402
    AllOf,
    Criterion,
    Direction,
    Ordering,
    ParsedQuery,
    canonicalise,
)
from app.core.row_projection import project_row  # noqa: E402
from app.core.screener_fields import build_registry  # noqa: E402
from compute.engine.anomaly_eval import (  # noqa: E402
    AnomalyOutcome,
    AnomalyRule,
    evaluate_rule,
)
from compute.engine.applicability import (  # noqa: E402
    Applicability,
    Cause,
    Domain,
    assess,
)
from compute.engine.metric_states import persist_row, violations  # noqa: E402
from compute.engine.peer_benchmarks import BenchmarkReason, benchmark  # noqa: E402
from compute.engine.screen_predicates import CriterionType  # noqa: E402
from compute.engine.screen_sql import RunScope, ValidatedRun, plan_screen  # noqa: E402
from compute.engine.universe_writer import column_for  # noqa: E402

ROUTE = Path(__file__).resolve().parents[1] / "app/api/v1/routes/screener.py"

#: The observed production value. Not a made-up number.
STORED_ZERO = 0.0

V1 = "FACTOR_MODEL_V1"
RUN = 4711
EV_COL = column_for("ev_ebitda")


def _literal(name):
    tree = ast.parse(ROUTE.read_text(encoding="utf-8"))
    for node in tree.body:
        targets = ([node.target] if isinstance(node, ast.AnnAssign)
                   else node.targets if isinstance(node, ast.Assign) else [])
        for t in targets:
            if isinstance(t, ast.Name) and t.id == name:
                return ast.literal_eval(node.value)
    raise AssertionError(f"{name} not found")


REGISTRY = build_registry(_literal("ALLOWED_FIELDS"), _literal("SORTABLE_COLS"))
SCOPE = RunScope.from_validated_runs(
    [ValidatedRun(RUN, V1, (), validated=True)])

PROMISED = {"ev_ebitda": EV_COL}


def bank_assessment():
    """What the canonical writer must produce for CBA's stored zero."""
    return assess("ev_ebitda", STORED_ZERO, Domain.BANK)


def industrial(value):
    return assess("ev_ebitda", value, Domain.GENERAL_CORPORATE)


# ── 1. Assessment ────────────────────────────────────────────────────────────

def test_the_zero_is_assessed_not_meaningful_because_of_domain():
    """Not INSUFFICIENT_DATA and not UNAVAILABLE: the number exists and the
    feed is healthy. EV/EBITDA is meaningless for a bank whatever the input,
    so the cause is the domain, not the observation."""
    a = bank_assessment()

    assert a.state is Applicability.NOT_MEANINGFUL
    assert a.cause is Cause.DOMAIN
    assert not a.ok


def test_the_same_zero_is_a_real_value_for_an_industrial():
    """The zero is not intrinsically invalid — it is invalid *for a bank*.
    A rule that rejected zeros everywhere would be a different, wrong fix."""
    a = industrial(8.2)
    assert a.ok and a.value == 8.2


# ── 2 & 3. Persistence ───────────────────────────────────────────────────────

def test_the_public_numeric_column_becomes_null():
    values, states = persist_row({"ev_ebitda": bank_assessment()})

    assert values["ev_ebitda"] is None, \
        "the governed numeric column must not hold a suppressed value"
    assert states["ev_ebitda"]["state"] == "not_meaningful"
    assert states["ev_ebitda"]["cause"] == "domain"


def test_the_forensic_zero_survives_only_in_the_sidecar():
    """The old computation did produce a zero, and that fact is worth
    keeping. It belongs where a legacy SELECT cannot reach it."""
    _, states = persist_row({"ev_ebitda": bank_assessment()})

    assert states["ev_ebitda"]["observed"] == STORED_ZERO


def test_a_row_still_carrying_the_zero_is_a_persistence_violation():
    """The contradictory state: a value beside an entry. This is what the
    database looks like today, and what the recompute must eliminate."""
    _, states = persist_row({"ev_ebitda": bank_assessment()})
    legacy = {"ev_ebitda": STORED_ZERO}          # as stored before P0-A

    found = violations(legacy, states, model_version=V1)
    assert any(v.kind == "contradictory_state" for v in found), \
        f"expected a contradiction, got {[v.kind for v in found]}"


# ── 4. Projection ────────────────────────────────────────────────────────────

def test_the_api_never_exposes_the_zero():
    values, states = persist_row({"ev_ebitda": bank_assessment()})
    row = {EV_COL: values["ev_ebitda"], "asx_code": "CBA",
           "metric_states": states, "compute_run_id": RUN}

    served, served_states = project_row(row, model_version=V1,
                                        expected=PROMISED, run_ids=[RUN])

    assert served[EV_COL] is None
    assert served_states["ev_ebitda"]["cause"] == "domain"
    assert "observed" not in served_states["ev_ebitda"], \
        "the forensic zero must not cross the API boundary"


def test_even_a_torn_row_holding_the_zero_projects_as_null():
    """Containment must not depend on persistence having been fixed first.
    Against legacy storage — value present, entry present — the read path
    still withholds."""
    _, states = persist_row({"ev_ebitda": bank_assessment()})
    row = {EV_COL: STORED_ZERO, "asx_code": "CBA",      # legacy value intact
           "metric_states": states, "compute_run_id": RUN}

    served, _ = project_row(row, model_version=V1, expected=PROMISED,
                            run_ids=[RUN])
    assert served[EV_COL] is None


# ── 5, 7, 8. The screen ──────────────────────────────────────────────────────

def build_db():
    """One bank with the suppressed zero, four industrials with real values."""
    conn = sqlite3.connect(":memory:")
    conn.execute(f"CREATE TABLE u (asx_code TEXT, {EV_COL} REAL, "
                 f"metric_states TEXT, compute_run_id INTEGER)")

    rows = {"CBA": bank_assessment(), "IND1": industrial(6.0),
            "IND2": industrial(9.5), "IND3": industrial(14.0),
            "IND4": industrial(22.0)}
    for code, assessment in rows.items():
        values, states = persist_row({"ev_ebitda": assessment})
        conn.execute("INSERT INTO u VALUES (?, ?, ?, ?)",
                     (code, values["ev_ebitda"], json.dumps(states), RUN))
    conn.commit()
    return conn


def plan(criteria=(), order=None, direction=Direction.ASC):
    parsed = canonicalise(
        ParsedQuery(expression=AllOf(tuple(criteria)) if criteria else None,
                    ordering=Ordering(order, direction) if order else None),
        REGISTRY)
    return plan_screen(parsed, REGISTRY, SCOPE, dialect="sqlite",
                       table_alias="")


def codes(conn, sql, params):
    return [r[0] for r in conn.execute(sql, params)]


def test_cheapest_first_does_not_put_the_bank_at_the_top():
    """The headline failure. Ascending EV/EBITDA is the "cheapest companies"
    screen, and a stored 0.0 wins it outright."""
    conn = build_db()
    p = plan(order="ev_to_ebitda", direction=Direction.ASC)
    page = codes(conn, p.page_sql("u", "asx_code", limit=5), p.params)

    assert page[0] != "CBA", "a suppressed zero must not rank as cheapest"
    assert "CBA" not in page
    assert page == ["IND1", "IND2", "IND3", "IND4"]


def test_the_bank_is_excluded_from_the_ranking_but_not_from_the_universe():
    conn = build_db()
    p = plan(order="ev_to_ebitda", direction=Direction.ASC)

    total = conn.execute(p.count_sql("u"), p.params).fetchone()[0]
    ranked = conn.execute(p.ranked_count_sql("u"), p.params).fetchone()[0]
    excluded = codes(conn, p.exclusion_sql("u", "asx_code"), p.params)

    assert total == 5, "the bank is still a member of the universe"
    assert ranked == 4 and excluded == ["CBA"]
    assert ranked + len(excluded) == total


def test_a_required_criterion_cannot_admit_the_bank():
    """REQUIRED admits only a proven TRUE. `ev_to_ebitda < 5` must not match
    a company whose EV/EBITDA was never evaluable — non-evaluation is not
    evidence for a positive requirement."""
    conn = build_db()
    p = plan([Criterion("ev_to_ebitda", CriterionType.REQUIRED, "lt", 5)])
    members = codes(conn, p.count_sql("u").replace("COUNT(*)", "asx_code"),
                    p.params)

    assert "CBA" not in members, "0.0 < 5 must never be evaluated"
    assert members == [], "no industrial is under 5 either"


def test_an_excluded_criterion_cannot_reject_the_bank():
    """The mirror, and the one a naive fix breaks. `NOT (ev_to_ebitda < 5)`
    must keep the bank: the exclusion is unproven, and dropping it would make
    non-evaluation evidence for an exclusion."""
    conn = build_db()
    p = plan([Criterion("ev_to_ebitda", CriterionType.EXCLUDED, "lt", 5)])
    members = codes(conn, p.count_sql("u").replace("COUNT(*)", "asx_code"),
                    p.params)

    assert "CBA" in members, \
        "a company that cannot be evaluated cannot be excluded"
    assert set(members) == {"CBA", "IND1", "IND2", "IND3", "IND4"}


# ── 6. Peer benchmarks ───────────────────────────────────────────────────────

def test_the_bank_does_not_shift_the_sector_benchmark():
    """Suppression happens before any cross-sectional statistic. A zero in
    the population would drag the median and the P25 toward it."""
    peers = [bank_assessment()] + [industrial(v) for v in
                                   (6.0, 9.5, 14.0, 22.0, 11.0)]
    result = benchmark("ev_ebitda", peers)

    assert result.state is Applicability.APPLICABLE
    assert result.n_total_peers == 6
    assert result.n_applicable_peers == 5, "the bank is out of domain"
    assert result.n_valid_peers == 5
    assert result.median == 11.0, \
        "the median of the five industrials, unmoved by the zero"
    assert result.p25 > STORED_ZERO


def test_a_sector_of_only_banks_yields_no_benchmark_rather_than_zero():
    """Financials. Every peer is out of domain, so there is no statistic to
    publish — and publishing 0.0 would be the same defect at sector scale."""
    result = benchmark("ev_ebitda", [bank_assessment() for _ in range(8)])

    assert result.state is not Applicability.APPLICABLE
    assert result.reason_code is BenchmarkReason.OUT_OF_DOMAIN_FOR_ALL
    assert result.median is None


# ── 9. Anomaly detection ─────────────────────────────────────────────────────

CHEAP_RULE = AnomalyRule(
    flag_type="DEEP_VALUE_EV_EBITDA",
    required_metrics=("ev_ebitda",),
    predicate=lambda v: v["ev_ebitda"] < 5.0,
)


def test_an_anomaly_needing_ev_ebitda_is_not_evaluated_for_a_bank():
    """NOT_EVALUATED, not NOT_FIRED. "We could not check" and "we checked and
    it did not fire" are different facts, and collapsing them would let a
    bank silently accumulate a clean record on a rule that never ran."""
    result = evaluate_rule(CHEAP_RULE, "CBA",
                           {"ev_ebitda": bank_assessment()})

    assert result.outcome is AnomalyOutcome.NOT_EVALUATED
    assert not result.evaluated
    assert Cause.DOMAIN in result.causes
    assert result.blocked_on == ("ev_ebitda",)


def test_the_rule_fires_for_an_industrial_with_a_genuine_low_multiple():
    """The rule is not broken — it is inapplicable to banks. Without this the
    previous test would pass against a rule that never fires at all."""
    result = evaluate_rule(CHEAP_RULE, "IND1", {"ev_ebitda": industrial(3.2)})

    assert result.outcome is AnomalyOutcome.FIRED


def test_a_rule_declared_on_the_storage_spelling_is_refused():
    """ev_to_ebitda is the column; ev_ebitda is the metric. A rule naming the
    column is how this escaped assessment in the first place."""
    try:
        AnomalyRule(flag_type="X", required_metrics=(EV_COL,),
                    predicate=lambda v: True)
    except Exception as exc:
        assert "ev_ebitda" in str(exc)
    else:
        raise AssertionError("a storage spelling must not be accepted")


# ── Standalone runner ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failures = []
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as e:
            failures.append(name)
            print(f"  FAIL  {name}  - {e}")
        except Exception as e:
            failures.append(name)
            print(f"  ERROR {name}  - {type(e).__name__}: {e}")

    print(f"\n{len(tests) - len(failures)}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
