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
    RunScope,
    OPERATORS,
    applicable_sql,
    compile_criterion,
    compile_screen,
    order_participation_sql,
)
from compute.engine.universe_writer import column_for  # noqa: E402

METRICS = ["debt_to_equity", "roe", "grossed_up_yield"]
RUN_ID = 4711
SCOPE = RunScope((RUN_ID,))


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
                 f"metric_states TEXT, compute_run_id INTEGER)")

    for code, assessments in companies().items():
        values, states = persist_row(assessments)
        placeholders = ", ".join("?" for _ in range(len(METRICS) + 3))
        conn.execute(
            f"INSERT INTO universe VALUES ({placeholders})",
            [code] + [values[m] for m in METRICS] + [json.dumps(states), RUN_ID])
    conn.commit()
    return conn


def sql_membership(conn, criteria) -> list[str]:
    compiled = compile_screen(criteria, SCOPE, dialect="sqlite")
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
    compiled = compile_screen([], SCOPE, order_by="grossed_up_yield", dialect="sqlite")

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
    compiled = compile_screen([], SCOPE, order_by="grossed_up_yield", dialect="sqlite")

    everyone = [r[0] for r in conn.execute(
        "SELECT asx_code FROM universe ORDER BY asx_code")]
    ranked = [r[0] for r in conn.execute(
        f"SELECT asx_code FROM universe WHERE {compiled.order_applicable}")]

    assert "FEED" in everyone and "FEED" not in ranked
    assert "QAN" in everyone and "QAN" not in ranked


def test_an_unavailable_yield_never_sorts_as_zero():
    conn = build_db()
    compiled = compile_screen([], SCOPE, order_by="grossed_up_yield",
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
        [Criterion("roe", CriterionType.PREFERRED, "gte", 0.12)], SCOPE,
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


# ── Run scoping · the clause is only sound inside a validated contract ───────

def test_a_screen_cannot_be_compiled_without_a_run_scope():
    try:
        RunScope(())
    except CompileError as e:
        assert "validated compute run" in str(e)
    else:
        raise AssertionError("an unscoped screen must not be compilable")


def test_the_run_scope_is_always_in_the_where_clause():
    compiled = compile_screen([], SCOPE, dialect="sqlite")
    assert "compute_run_id IN (4711)" in compiled.where


def test_a_legacy_row_is_not_readable_through_the_applicability_clause():
    """The reason scoping is required rather than advisory.

    A row written before the sidecar existed has a populated numeric column
    and no metric_states entry — which is exactly what an APPLICABLE metric
    looks like. Every predicate would evaluate it and every predicate would be
    wrong, silently, because nothing about the row looks unusual.
    """
    conn = build_db()
    conn.execute(
        "INSERT INTO universe VALUES ('LEGACY', 4.6, 0.05, 0.09, '{}', NULL)")
    conn.commit()

    unscoped = [r[0] for r in conn.execute(
        "SELECT asx_code FROM universe WHERE "
        + applicable_sql("debt_to_equity", "sqlite"))]
    assert "LEGACY" in unscoped, "absent sidecar reads as applicable — the trap"

    scoped = sql_membership(
        conn, [Criterion("debt_to_equity", CriterionType.REQUIRED, "lt", 5.0)])
    assert "LEGACY" not in scoped, "the run scope keeps it out"


def test_a_scope_may_only_name_runs_that_passed_validation():
    """A positional argument prevents omission, not untrustworthiness. A route
    could satisfy the signature while still naming a run whose recompute was
    never verified."""
    from compute.engine.screen_sql import ValidatedRun

    good = ValidatedRun(4711, "FACTOR_MODEL_V1", (), validated=True)
    unchecked = ValidatedRun(4712, "FACTOR_MODEL_V1", (), validated=False)

    assert RunScope.from_validated_runs([good]).run_ids == (4711,)

    try:
        RunScope.from_validated_runs([good, unchecked])
    except CompileError as e:
        assert "4712" in str(e) and "persistence validation" in str(e)
    else:
        raise AssertionError("an unvalidated run must not enter a scope")


def test_one_snapshot_is_one_contract():
    """Several run ids only where sharding forces it, and only when every
    shard shares a model version and a source-health state."""
    from compute.engine.screen_sql import ValidatedRun

    shard_a = ValidatedRun(1, "FACTOR_MODEL_V1", (), validated=True)
    shard_b = ValidatedRun(2, "FACTOR_MODEL_V1", (), validated=True)
    assert RunScope.from_validated_runs([shard_a, shard_b]).run_ids == (1, 2)

    different_health = ValidatedRun(3, "FACTOR_MODEL_V1", ("dividends",),
                                    validated=True)
    try:
        RunScope.from_validated_runs([shard_a, different_health])
    except CompileError as e:
        assert "more than one contract" in str(e)
    else:
        raise AssertionError(
            "a ranking must not span runs with different source health")


def test_a_scope_cannot_span_model_versions():
    from compute.engine.screen_sql import ValidatedRun

    v1 = ValidatedRun(1, "FACTOR_MODEL_V1", (), validated=True)
    v2 = ValidatedRun(2, "FACTOR_MODEL_V2", (), validated=True)
    try:
        RunScope.from_validated_runs([v1, v2])
    except CompileError:
        pass
    else:
        raise AssertionError("two model versions are two contracts")


def test_an_empty_validated_set_is_refused():
    try:
        RunScope.from_validated_runs([])
    except CompileError as e:
        assert "no validated compute run" in str(e)
    else:
        raise AssertionError("no trusted run means no screen, not every row")


def test_rows_from_an_unvalidated_run_are_excluded():
    conn = build_db()
    conn.execute(
        "INSERT INTO universe VALUES ('OTHER', 0.3, 0.20, 0.05, '{}', 9999)")
    conn.commit()

    members = sql_membership(
        conn, [Criterion("debt_to_equity", CriterionType.REQUIRED, "lt", 1.5)])
    assert "OTHER" not in members, "a different run is a different contract"


# ── Pagination applies to participants, not to the result set ────────────────

def test_top_n_does_not_spend_slots_on_unrankable_rows():
    """The trap: membership and participation separated correctly, then LIMIT
    applied to a query that still contains the non-participants. The customer
    asks for the top 3 yields and gets two real answers and a hole."""
    from compute.engine.screen_sql import paginated_ranking_sql

    conn = build_db()
    compiled = compile_screen([], SCOPE, order_by="grossed_up_yield",
                              dialect="sqlite")

    sql = paginated_ranking_sql(compiled, "universe", "asx_code", limit=3,
                                dialect="sqlite")
    top3 = [r[0] for r in conn.execute(sql, compiled.params)]

    assert len(top3) == 3, "three real answers, not three rows"
    assert "FEED" not in top3 and "QAN" not in top3
    assert top3 == ["IND1", "CBA", "IND2"], "0.06, 0.045, 0.02 descending"


def test_the_naive_query_spends_slots_on_nulls_in_one_direction_or_the_other():
    """Documents what the helper prevents — and that the direction is a
    dialect accident, which is the reason not to rely on NULL ordering at all.

        sqlite     NULLs last on DESC, first on ASC
        Postgres   the opposite: NULLS LAST on ASC, NULLS FIRST on DESC

    So "top 20 lowest P/E" is poisoned under sqlite and "top 20 highest
    yield" under Postgres. A route that tested one direction on one engine
    would conclude the problem does not exist.
    """
    conn = build_db()
    compiled = compile_screen([], SCOPE, order_by="grossed_up_yield",
                              descending=False, dialect="sqlite")
    naive = [r[0] for r in conn.execute(
        f"SELECT asx_code FROM universe WHERE {compiled.where} "
        f"ORDER BY {compiled.order_by} LIMIT 3", compiled.params)]

    assert set(naive) & {"FEED", "QAN"}, \
        "sqlite sorts NULLs first ascending, so they take the top slots"
    assert naive[:2] == ["FEED", "QAN"], \
        "two of the three answers are companies with no measurable yield"


def test_the_helper_is_unaffected_by_null_ordering_in_either_direction():
    """Because non-participants never reach the ORDER BY at all."""
    from compute.engine.screen_sql import paginated_ranking_sql

    conn = build_db()
    for descending in (True, False):
        compiled = compile_screen([], SCOPE, order_by="grossed_up_yield",
                                  descending=descending, dialect="sqlite")
        page = [r[0] for r in conn.execute(
            paginated_ranking_sql(compiled, "universe", "asx_code", limit=3,
                                  dialect="sqlite"), compiled.params)]
        assert not set(page) & {"FEED", "QAN"}, descending
        assert len(page) == 3


def test_offset_walks_the_participant_set():
    from compute.engine.screen_sql import paginated_ranking_sql

    conn = build_db()
    compiled = compile_screen([], SCOPE, order_by="grossed_up_yield",
                              dialect="sqlite")
    page2 = [r[0] for r in conn.execute(
        paginated_ranking_sql(compiled, "universe", "asx_code", limit=2,
                              offset=2, dialect="sqlite"), compiled.params)]

    assert page2 == ["IND2"], "three participants, so page two holds one"


def test_the_excluded_are_returned_alongside_rather_than_discarded():
    from compute.engine.screen_sql import excluded_from_ordering_sql

    conn = build_db()
    compiled = compile_screen([], SCOPE, order_by="grossed_up_yield",
                              dialect="sqlite")
    excluded = {r[0] for r in conn.execute(
        excluded_from_ordering_sql(compiled, "universe", "asx_code"),
        compiled.params)}

    assert excluded == {"FEED", "QAN"}, \
        "so a surface can say 2 companies could not be ranked"


# ── contract_key is semantic, not forensic ───────────────────────────────────

def test_forensic_detail_does_not_fragment_a_logical_snapshot():
    """Two shards both saying dividends is unhealthy are one snapshot, even
    with different watermarks and diagnostic wording."""
    from compute.engine.screen_sql import ValidatedRun

    a = ValidatedRun(1, "FACTOR_MODEL_V1", ("dividends",), validated=True,
                     detail={"dividends": "latest ex-date 2026-08-03, 38 days"})
    b = ValidatedRun(2, "FACTOR_MODEL_V1", ("dividends",), validated=True,
                     detail={"dividends": "latest ex-date 2026-08-04, 37 days"})

    assert a.contract_key == b.contract_key
    assert RunScope.from_validated_runs([a, b]).run_ids == (1, 2)


def test_the_set_of_affected_sources_is_what_is_compared():
    from compute.engine.screen_sql import ValidatedRun

    a = ValidatedRun(1, "FACTOR_MODEL_V1", ("dividends", "prices"),
                     validated=True)
    b = ValidatedRun(2, "FACTOR_MODEL_V1", ("prices", "dividends"),
                     validated=True)
    assert a.contract_key == b.contract_key, "order is not semantic"

    c = ValidatedRun(3, "FACTOR_MODEL_V1", ("dividends",), validated=True)
    assert a.contract_key != c.contract_key, "a different set is a different fact"


# ── Three-valued composition · UNKNOWN must not become evidence ──────────────
# The collapse being prevented:
#
#     yield > 5%  on SOURCE_UNHEALTHY  ->  FALSE
#     NOT (yield > 5%)                 ->  TRUE
#
# NOT is not in the query grammar today (_KEYWORDS is {"AND", "OR"}), so this
# is not user-reachable through the language. It is reachable through the
# compiler's own EXCLUDED shape and through any future grammar extension, and
# a latent version of this defect is worth closing while it is cheap.

def three_valued(conn, expr: str, params: dict) -> dict:
    """Each company's raw TRUE/FALSE/NULL for one expression."""
    rows = conn.execute(
        f"SELECT asx_code, {expr} FROM universe WHERE {SCOPE.sql('sqlite')}",
        params).fetchall()
    return {code: value for code, value in rows}


def yield_over(threshold: float, param: str = "t"):
    return Criterion("grossed_up_yield", CriterionType.REQUIRED, "gt", threshold)


def test_an_unevaluable_leaf_is_null_not_false():
    """The property everything else rests on. FALSE is a claim; NULL is not."""
    from compute.engine.screen_sql import three_valued_sql

    conn = build_db()
    expr = three_valued_sql(yield_over(0.05), "t", "sqlite")
    values = three_valued(conn, expr, {"t": 0.05})

    assert values["IND1"] == 1, "0.06 > 0.05 is proven true"
    assert values["IND2"] == 0, "0.02 > 0.05 is proven false"
    assert values["FEED"] is None, "source unhealthy says nothing"
    assert values["QAN"] is None, "no value says nothing"


def test_case_1_not_of_an_unevaluable_condition_is_not_proven_true():
    """NOT UNKNOWN = UNKNOWN, so it cannot admit a row."""
    from compute.engine.screen_sql import membership_sql, three_valued_sql

    conn = build_db()
    inner = three_valued_sql(yield_over(0.05), "t", "sqlite")
    negated = f"NOT ({inner})"

    values = three_valued(conn, negated, {"t": 0.05})
    assert values["FEED"] is None, "NOT UNKNOWN stays UNKNOWN"

    admitted = [c for c, v in three_valued(
        conn, membership_sql(negated, CriterionType.REQUIRED, "sqlite"),
        {"t": 0.05}).items() if v]
    assert "FEED" not in admitted, \
        "an unevaluable yield must not prove the company yields under 5%"
    assert "IND2" in admitted, "a genuine 0.02 is proven under 5%"


def test_case_2_true_or_unknown_admits_on_the_true_half():
    from compute.engine.screen_sql import membership_sql, three_valued_sql

    conn = build_db()
    # roe > 0.10 is true for every fixture company; the yield half is unknown
    # for FEED.
    a = three_valued_sql(
        Criterion("roe", CriterionType.REQUIRED, "gt", 0.10), "a", "sqlite")
    b = three_valued_sql(yield_over(0.05), "t", "sqlite")

    clause = membership_sql(f"({a}) OR ({b})", CriterionType.REQUIRED, "sqlite")
    admitted = [c for c, v in three_valued(
        conn, clause, {"a": 0.10, "t": 0.05}).items() if v]

    assert "FEED" in admitted, \
        "A independently proves membership; the unknown half is irrelevant"


def test_case_3_false_or_unknown_does_not_admit():
    from compute.engine.screen_sql import membership_sql, three_valued_sql

    conn = build_db()
    # roe > 0.9 is false for everyone.
    a = three_valued_sql(
        Criterion("roe", CriterionType.REQUIRED, "gt", 0.9), "a", "sqlite")
    b = three_valued_sql(yield_over(0.05), "t", "sqlite")

    raw = three_valued(conn, f"({a}) OR ({b})", {"a": 0.9, "t": 0.05})
    assert raw["FEED"] is None, "FALSE OR UNKNOWN is UNKNOWN, not FALSE"

    clause = membership_sql(f"({a}) OR ({b})", CriterionType.REQUIRED, "sqlite")
    admitted = [c for c, v in three_valued(
        conn, clause, {"a": 0.9, "t": 0.05}).items() if v]
    assert "FEED" not in admitted


def test_case_4_not_of_a_disjunction_stays_unknown_when_undecidable():
    from compute.engine.screen_sql import three_valued_sql

    conn = build_db()
    a = three_valued_sql(
        Criterion("roe", CriterionType.REQUIRED, "gt", 0.9), "a", "sqlite")
    b = three_valued_sql(yield_over(0.05), "t", "sqlite")

    raw = three_valued(conn, f"NOT (({a}) OR ({b}))", {"a": 0.9, "t": 0.05})

    assert raw["FEED"] is None, "undecidable stays undecidable"
    assert raw["IND1"] == 0, "decidable: IND1's yield does exceed 5%"
    assert raw["IND2"] == 1, "decidable: neither half holds for IND2"


ROLE_TRUTH_TABLE = {
    # raw E   -> (admitted under REQUIRED, admitted under EXCLUDED)
    "TRUE":  (True,  False),
    "FALSE": (False, True),
    "NULL":  (False, True),      # the row that decides whether this is right
}


def test_the_role_collapse_truth_table():
    """The boundary is where the bug would reappear if written naively.

    For REQUIRED a plain `WHERE E` happens to behave correctly, because FALSE
    and NULL are both rejected. For EXCLUDED, `WHERE NOT E` is wrong: NOT NULL
    is NULL, SQL drops the row, and non-evaluation becomes evidence for
    exclusion — the exact defect the CASE leaf was built to prevent, undone
    one line later.

    COALESCE must therefore sit *inside* the negation, collapsing UNKNOWN to
    "not proven" before the NOT rather than after it.
    """
    from compute.engine.screen_sql import membership_sql

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE t (label TEXT, e INTEGER)")
    conn.executemany("INSERT INTO t VALUES (?,?)",
                     [("TRUE", 1), ("FALSE", 0), ("NULL", None)])

    for role, index in ((CriterionType.REQUIRED, 0), (CriterionType.EXCLUDED, 1)):
        clause = membership_sql("e", role, "sqlite")
        admitted = dict(conn.execute(
            f"SELECT label, CASE WHEN {clause} THEN 1 ELSE 0 END FROM t"))
        for label, expected in ROLE_TRUTH_TABLE.items():
            assert bool(admitted[label]) is expected[index], \
                f"{role.value} on {label}"


def test_the_naive_exclusion_fails_the_table():
    """Kept so the reason for the COALESCE ordering cannot be optimised away."""
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE t (label TEXT, e INTEGER)")
    conn.executemany("INSERT INTO t VALUES (?,?)",
                     [("TRUE", 1), ("FALSE", 0), ("NULL", None)])

    naive = dict(conn.execute(
        "SELECT label, CASE WHEN NOT e THEN 1 ELSE 0 END FROM t"))

    assert not naive["NULL"], \
        "NOT NULL is NULL and the row is dropped — non-evaluation acting as " \
        "evidence for exclusion"
    assert bool(naive["NULL"]) is not ROLE_TRUTH_TABLE["NULL"][1], \
        "which is precisely the opposite of the required behaviour"


def test_an_exclusion_still_keeps_a_row_it_cannot_evaluate():
    """The boundary rule, unchanged by the three-valued leaf."""
    conn = build_db()
    members = sql_membership(
        conn, [Criterion("grossed_up_yield", CriterionType.EXCLUDED, "gt", 0.03)])

    assert "FEED" in members, "the exclusion is unproven, so it cannot reject"
    assert "IND1" not in members, "0.06 is proven above 0.03 and does reject"


def test_a_required_criterion_still_refuses_what_it_cannot_prove():
    conn = build_db()
    members = sql_membership(
        conn, [Criterion("grossed_up_yield", CriterionType.REQUIRED, "gt", 0.03)])

    assert "FEED" not in members and "IND1" in members


def test_the_snapshot_names_the_contract_not_a_shard():
    """A response says what it was computed under. Naming one run id would be
    false the first time sharding appeared."""
    from compute.engine.screen_sql import ValidatedRun

    a = ValidatedRun(1, "FACTOR_MODEL_V1", (), validated=True)
    b = ValidatedRun(2, "FACTOR_MODEL_V1", (), validated=True)

    one = RunScope.from_validated_runs([a, b])
    same = RunScope.from_validated_runs([b, a])
    assert one.snapshot == same.snapshot, "order is not part of the identity"

    degraded = RunScope.from_validated_runs(
        [ValidatedRun(1, "FACTOR_MODEL_V1", ("dividends",), validated=True)])
    healthy = RunScope.from_validated_runs([a])
    assert degraded.snapshot != healthy.snapshot, \
        "the same rows under different source health is a different contract"


def test_the_snapshot_is_opaque():
    """A client compares it; it does not parse it. The moment it looks
    structured someone reads a run id out of it."""
    from compute.engine.screen_sql import ValidatedRun

    scope = RunScope.from_validated_runs(
        [ValidatedRun(4711, "FACTOR_MODEL_V1", (), validated=True)])

    assert scope.snapshot.startswith("snap_")
    assert "4711" not in scope.snapshot
    assert "FACTOR_MODEL_V1" not in scope.snapshot
    assert scope.run_ids == (4711,), "the ids stay available as diagnostics"


def test_an_exclusion_nested_in_a_disjunction_is_refused_not_guessed():
    """Its meaning there is undefined, and picking one is how the original
    defect arrived."""
    from app.core.parsed_query import AnyOf, Criterion as TypedCriterion
    from compute.engine.screen_sql import assert_role_is_decidable

    tree = AnyOf((
        TypedCriterion("roe", CriterionType.REQUIRED, "gt", 0.1),
        TypedCriterion("grossed_up_yield", CriterionType.EXCLUDED, "gt", 0.05)))

    try:
        assert_role_is_decidable(tree)
    except CompileError as e:
        assert "no defined meaning" in str(e)
    else:
        raise AssertionError("an undefined composition must be refused")


def test_an_exclusion_at_the_top_of_a_conjunction_is_fine():
    from app.core.parsed_query import AllOf, Criterion as TypedCriterion
    from compute.engine.screen_sql import assert_role_is_decidable

    assert_role_is_decidable(AllOf((
        TypedCriterion("roe", CriterionType.REQUIRED, "gt", 0.1),
        TypedCriterion("grossed_up_yield", CriterionType.EXCLUDED, "gt", 0.05))))


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
