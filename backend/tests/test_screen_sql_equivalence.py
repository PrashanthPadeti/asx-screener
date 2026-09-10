"""
Python and SQL must decide the same thing
=========================================
The classic drift: the Python contract says one thing and the WHERE clause
says another, and nobody notices because both look reasonable in isolation.

So this runs the *same fixture* through both — the pure ``evaluate()`` engine
and the compiled SQL executed by a real SQL engine — and asserts identical
membership and identical ranking participation. sqlite is used because it is
in the standard library and executes actual SQL; the Postgres form is compiled
and shape-checked here, and proven on the server.

The fixture carries all five reasons a metric may not evaluate, so the
equivalence is tested against every state rather than only against NULL.

Run under pytest, or standalone:
    cd /opt/asx-screener/backend && ../asx-venv/bin/python tests/test_screen_sql_equivalence.py
"""

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from compute.engine.applicability import (  # noqa: E402
    Domain,
    Observation,
    assess,
    unhealthy,
)
from compute.engine.metric_states import persist_row  # noqa: E402
from compute.engine.screen_predicates import (  # noqa: E402
    CriterionType,
    evaluate,
    order_by as py_order_by,
    resolve,
)
from compute.engine.screen_sql import (  # noqa: E402
    CompileError,
    Criterion,
    OPERATORS,
    applicable_sql,
    compile_criterion,
    compile_screen,
    order_participation_sql,
)
from compute.engine.universe_writer import column_for  # noqa: E402

METRICS = ["debt_to_equity", "roe", "grossed_up_yield"]


def companies() -> dict:
    """Five companies covering every reason a metric may not evaluate."""
    obs = Observation(equity=8e10, earnings=1e10)
    return {
        # Ordinary industrial: everything applicable.
        "IND1": {
            "debt_to_equity": assess("debt_to_equity", 0.4, Domain.GENERAL_CORPORATE),
            "roe": assess("roe", 0.22, Domain.GENERAL_CORPORATE, obs),
            "grossed_up_yield": assess("grossed_up_yield", 0.06,
                                       Domain.GENERAL_CORPORATE),
        },
        # Highly levered industrial: applicable, and genuinely fails.
        "IND2": {
            "debt_to_equity": assess("debt_to_equity", 3.0, Domain.GENERAL_CORPORATE),
            "roe": assess("roe", 0.11, Domain.GENERAL_CORPORATE, obs),
            "grossed_up_yield": assess("grossed_up_yield", 0.02,
                                       Domain.GENERAL_CORPORATE),
        },
        # Bank: D/E out of domain, roe fine, yield fine.
        "CBA": {
            "debt_to_equity": assess("debt_to_equity", 4.6, Domain.BANK),
            "roe": assess("roe", 0.1284, Domain.BANK, obs),
            "grossed_up_yield": assess("grossed_up_yield", 0.045, Domain.BANK),
        },
        # Broken dividend feed: yield unavailable for source reasons.
        "FEED": {
            "debt_to_equity": assess("debt_to_equity", 0.6, Domain.GENERAL_CORPORATE),
            "roe": assess("roe", 0.15, Domain.GENERAL_CORPORATE, obs),
            "grossed_up_yield": unhealthy("grossed_up_yield", "feed incomplete"),
        },
        # Negative equity: roe not meaningful by observation; no value at all
        # for the yield.
        "QAN": {
            "debt_to_equity": assess("debt_to_equity", 1.1, Domain.GENERAL_CORPORATE),
            "roe": assess("roe", 2.06, Domain.GENERAL_CORPORATE,
                          Observation(equity=-1.2e9)),
            "grossed_up_yield": assess("grossed_up_yield", None,
                                       Domain.GENERAL_CORPORATE),
        },
    }


def build_db() -> sqlite3.Connection:
    """A universe table shaped like the real one: numerics plus the sidecar."""
    conn = sqlite3.connect(":memory:")
    cols = ", ".join(f"{column_for(m)} REAL" for m in METRICS)
    conn.execute(f"CREATE TABLE universe (asx_code TEXT, {cols}, "
                 f"metric_states TEXT)")

    for code, assessments in companies().items():
        values, states = persist_row(assessments)
        placeholders = ", ".join("?" for _ in range(len(METRICS) + 2))
        conn.execute(
            f"INSERT INTO universe VALUES ({placeholders})",
            [code] + [values[m] for m in METRICS] + [json.dumps(states)])
    conn.commit()
    return conn


def sql_membership(conn, criteria) -> list[str]:
    compiled = compile_screen(criteria, dialect="sqlite")
    rows = conn.execute(
        f"SELECT asx_code FROM universe WHERE {compiled.where} ORDER BY asx_code",
        compiled.params).fetchall()
    return [r[0] for r in rows]


def python_membership(criteria) -> list[str]:
    out = []
    for code, assessments in companies().items():
        outcomes = [
            evaluate(assessments[c.metric], c.criterion,
                     _test(c.operator, c.value))
            for c in criteria]
        if resolve(code, outcomes).included:
            out.append(code)
    return sorted(out)


def _test(operator: str, value: float):
    return {
        "gt": lambda v: v > value, "gte": lambda v: v >= value,
        "lt": lambda v: v < value, "lte": lambda v: v <= value,
        "eq": lambda v: v == value, "ne": lambda v: v != value,
    }[operator]


# ── Membership equivalence, across every criterion type ──────────────────────

SCREENS = {
    "required_low_leverage": [
        Criterion("debt_to_equity", CriterionType.REQUIRED, "lt", 1.5)],
    "excluded_high_leverage": [
        Criterion("debt_to_equity", CriterionType.EXCLUDED, "gt", 1.5)],
    "required_yield": [
        Criterion("grossed_up_yield", CriterionType.REQUIRED, "gte", 0.04)],
    "excluded_low_roe": [
        Criterion("roe", CriterionType.EXCLUDED, "lt", 0.12)],
    "buy_and_hold": [
        Criterion("debt_to_equity", CriterionType.EXCLUDED, "gt", 1.5),
        Criterion("roe", CriterionType.EXCLUDED, "lt", 0.10),
    ],
    "quality_and_income": [
        Criterion("roe", CriterionType.REQUIRED, "gte", 0.12),
        Criterion("grossed_up_yield", CriterionType.REQUIRED, "gte", 0.04),
    ],
}


def test_python_and_sql_agree_on_membership_for_every_screen():
    conn = build_db()
    for name, criteria in SCREENS.items():
        assert sql_membership(conn, criteria) == python_membership(criteria), name


def test_the_fixture_actually_exercises_disagreement_potential():
    """Guards the guard: if every screen returned everyone, agreement would be
    trivial and the equivalence test would prove nothing."""
    conn = build_db()
    sizes = {len(sql_membership(conn, c)) for c in SCREENS.values()}
    assert len(sizes) > 1 and min(sizes) < 5, \
        "the screens must actually discriminate between companies"


# ── The two rules that SQL is most likely to get wrong ───────────────────────

def test_sql_does_not_exclude_a_bank_on_an_unevaluable_leverage_exclusion():
    conn = build_db()
    members = sql_membership(
        conn, [Criterion("debt_to_equity", CriterionType.EXCLUDED, "gt", 1.5)])

    assert "CBA" in members, "the exclusion is unproven, so it cannot reject"
    assert "IND2" not in members, "3.0x is proven and does reject"


def test_sql_does_not_admit_a_bank_on_an_unproven_requirement():
    conn = build_db()
    members = sql_membership(
        conn, [Criterion("debt_to_equity", CriterionType.REQUIRED, "lt", 1.5)])

    assert "CBA" not in members, "the requirement is unproven, so no match"
    assert "IND1" in members


def test_the_same_non_evaluation_goes_both_ways_in_sql_too():
    """The asymmetry survives compilation, not just the Python engine."""
    conn = build_db()
    required = sql_membership(
        conn, [Criterion("debt_to_equity", CriterionType.REQUIRED, "lt", 1.5)])
    excluded = sql_membership(
        conn, [Criterion("debt_to_equity", CriterionType.EXCLUDED, "gt", 1.5)])

    assert "CBA" not in required and "CBA" in excluded


def test_a_source_unhealthy_yield_neither_matches_nor_excludes():
    conn = build_db()
    required = sql_membership(
        conn, [Criterion("grossed_up_yield", CriterionType.REQUIRED, "gte", 0.04)])
    excluded = sql_membership(
        conn, [Criterion("grossed_up_yield", CriterionType.EXCLUDED, "lt", 0.04)])

    assert "FEED" not in required
    assert "FEED" in excluded


# ── Ranking participation is separate from membership ────────────────────────

def test_ranking_participation_matches_the_python_engine():
    conn = build_db()
    compiled = compile_screen([], order_by="grossed_up_yield", dialect="sqlite")

    rows = conn.execute(
        f"SELECT asx_code FROM universe WHERE {compiled.order_applicable} "
        f"ORDER BY {compiled.order_by}", compiled.params).fetchall()
    sql_ranked = [r[0] for r in rows]

    rows_py = {code: a["grossed_up_yield"]
               for code, a in companies().items()}
    assert sql_ranked == py_order_by(rows_py, descending=True)


def test_a_company_absent_from_the_ranking_is_still_in_the_universe():
    """Membership and ranking participation are different questions."""
    conn = build_db()
    compiled = compile_screen([], order_by="grossed_up_yield", dialect="sqlite")

    everyone = [r[0] for r in conn.execute(
        "SELECT asx_code FROM universe ORDER BY asx_code")]
    ranked = [r[0] for r in conn.execute(
        f"SELECT asx_code FROM universe WHERE {compiled.order_applicable}")]

    assert "FEED" in everyone and "FEED" not in ranked
    assert "QAN" in everyone and "QAN" not in ranked


def test_an_unavailable_yield_never_sorts_as_zero():
    conn = build_db()
    compiled = compile_screen([], order_by="grossed_up_yield",
                              descending=False, dialect="sqlite")
    ranked = [r[0] for r in conn.execute(
        f"SELECT asx_code FROM universe WHERE {compiled.order_applicable} "
        f"ORDER BY {compiled.order_by}")]

    assert ranked[0] == "IND2", "the genuine 2% leads an ascending sort"
    assert "FEED" not in ranked and "QAN" not in ranked


def test_participation_is_reportable_from_sql():
    conn = build_db()
    flag = order_participation_sql("grossed_up_yield", dialect="sqlite")
    rows = dict(conn.execute(
        f"SELECT asx_code, {flag} FROM universe").fetchall())

    assert rows["IND1"] and not rows["FEED"] and not rows["QAN"]


# ── Preferences never become filters ─────────────────────────────────────────

def test_a_preference_does_not_restrict_membership():
    conn = build_db()
    criteria = [Criterion("roe", CriterionType.PREFERRED, "gte", 0.20)]

    assert compile_criterion(criteria[0], "p0", "sqlite") is None
    assert len(sql_membership(conn, criteria)) == 5, \
        "a soft signal compiled into WHERE would be a hard filter"


def test_a_preference_contributes_only_when_applicable():
    conn = build_db()
    compiled = compile_screen(
        [Criterion("roe", CriterionType.PREFERRED, "gte", 0.12)],
        dialect="sqlite")
    expression = compiled.preference_expressions["roe"]

    scores = dict(conn.execute(
        f"SELECT asx_code, {expression} FROM universe", compiled.params))

    assert scores["IND1"] == 1 and scores["CBA"] == 1
    assert scores["IND2"] == 0, "0.11 is applicable and simply below"
    assert scores["QAN"] == 0, "not meaningful contributes nothing, not a penalty"


# ── The applicability clause itself ──────────────────────────────────────────

def test_applicability_requires_both_a_value_and_no_sidecar_entry():
    for dialect in ("postgres", "sqlite"):
        clause = applicable_sql("debt_to_equity", dialect)
        assert "IS NOT NULL" in clause
        assert "metric_states" in clause


def test_the_postgres_form_uses_the_json_operator_and_the_physical_column():
    clause = applicable_sql("ev_ebitda", "postgres")
    assert "ev_to_ebitda IS NOT NULL" in clause, "physical column"
    assert "metric_states -> 'ev_ebitda' IS NULL" in clause, "canonical key"


def test_an_unknown_operator_is_refused_at_definition_time():
    try:
        Criterion("roe", CriterionType.REQUIRED, "DROP TABLE", 1.0)
    except CompileError as e:
        assert "not a permitted operator" in str(e)
    else:
        raise AssertionError("a screen must not be able to inject an operator")


def test_every_permitted_operator_compiles_and_runs():
    conn = build_db()
    for operator in OPERATORS:
        criteria = [Criterion("roe", CriterionType.REQUIRED, operator, 0.15)]
        assert sql_membership(conn, criteria) == python_membership(criteria), \
            operator


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
