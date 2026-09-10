"""
One plan per request, four statements from it
=============================================
``plan_screen`` is the single authority a typed query passes through on its
way to SQL. These tests execute the plan's four statements against a real
sqlite table and assert the response-level invariants:

    ungoverned ordering   ranked_total == total, no exclusions
    governed ordering     ranked_total + excluded == total
                          exclusions drawn only from screen members
    one resolved scope    every statement carries the same snapshot

The last one is not observable from a single query. It is a property of the
request, and it is asserted by checking that all four statements are built
from one plan object rather than from four independent resolutions.

Run under pytest, or standalone:
    cd /opt/asx-screener/backend && ../asx-venv/bin/python tests/test_screen_plan.py
"""

import ast
import json
import sqlite3
import sys
from datetime import date
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
from app.core.screener_fields import build_registry  # noqa: E402
from compute.engine.applicability import (  # noqa: E402
    Domain,
    Observation,
    assess,
    unhealthy,
)
from compute.engine.metric_states import persist_row  # noqa: E402
from compute.engine.screen_predicates import CriterionType  # noqa: E402
from compute.engine.screen_sql import (  # noqa: E402
    CompileError,
    RunScope,
    ValidatedRun,
    plan_screen,
)
from compute.engine.universe_writer import column_for  # noqa: E402

ROUTE = Path(__file__).resolve().parents[1] / "app/api/v1/routes/screener.py"


def _literal(name: str):
    tree = ast.parse(ROUTE.read_text(encoding="utf-8"))
    for node in tree.body:
        targets = ([node.target] if isinstance(node, ast.AnnAssign)
                   else node.targets if isinstance(node, ast.Assign) else [])
        for t in targets:
            if isinstance(t, ast.Name) and t.id == name:
                return ast.literal_eval(node.value)
    raise AssertionError(f"{name} not found")


REGISTRY = build_registry(_literal("ALLOWED_FIELDS"), _literal("SORTABLE_COLS"))
RUN_ID = 4711
SCOPE = RunScope.from_validated_runs(
    [ValidatedRun(RUN_ID, "FACTOR_MODEL_V1", (), validated=True)])

GOVERNED = ["debt_to_equity", "roe", "grossed_up_yield"]
UNGOVERNED = ["market_cap", "sector"]


def companies() -> dict:
    obs = Observation(equity=8e10, earnings=1e10)
    return {
        "IND1": (dict(market_cap=5000.0, sector="Materials"), {
            "debt_to_equity": assess("debt_to_equity", 0.4, Domain.GENERAL_CORPORATE),
            "roe": assess("roe", 0.22, Domain.GENERAL_CORPORATE, obs),
            "grossed_up_yield": assess("grossed_up_yield", 0.06,
                                       Domain.GENERAL_CORPORATE)}),
        "IND2": (dict(market_cap=2000.0, sector="Materials"), {
            "debt_to_equity": assess("debt_to_equity", 3.0, Domain.GENERAL_CORPORATE),
            "roe": assess("roe", 0.11, Domain.GENERAL_CORPORATE, obs),
            "grossed_up_yield": assess("grossed_up_yield", 0.02,
                                       Domain.GENERAL_CORPORATE)}),
        "CBA": (dict(market_cap=9000.0, sector="Financials"), {
            "debt_to_equity": assess("debt_to_equity", 4.6, Domain.BANK),
            "roe": assess("roe", 0.1284, Domain.BANK, obs),
            "grossed_up_yield": assess("grossed_up_yield", 0.045, Domain.BANK)}),
        "FEED": (dict(market_cap=800.0, sector="Materials"), {
            "debt_to_equity": assess("debt_to_equity", 0.6, Domain.GENERAL_CORPORATE),
            "roe": assess("roe", 0.15, Domain.GENERAL_CORPORATE, obs),
            "grossed_up_yield": unhealthy("grossed_up_yield", "feed incomplete")}),
        "QAN": (dict(market_cap=400.0, sector="Industrials"), {
            "debt_to_equity": assess("debt_to_equity", 1.1, Domain.GENERAL_CORPORATE),
            "roe": assess("roe", 2.06, Domain.GENERAL_CORPORATE,
                          Observation(equity=-1.2e9)),
            "grossed_up_yield": assess("grossed_up_yield", None,
                                       Domain.GENERAL_CORPORATE)}),
    }


def build_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    cols = ", ".join(f"{column_for(m)} REAL" for m in GOVERNED)
    conn.execute(f"CREATE TABLE u (asx_code TEXT, {cols}, market_cap REAL, "
                 f"sector TEXT, metric_states TEXT, compute_run_id INTEGER)")

    for code, (plain, assessments) in companies().items():
        values, states = persist_row(assessments)
        conn.execute(
            f"INSERT INTO u VALUES ({', '.join('?' * (len(GOVERNED) + 5))})",
            [code] + [values[m] for m in GOVERNED] + [plain["market_cap"],
             plain["sector"], json.dumps(states), RUN_ID])
    conn.commit()
    return conn


def plan(criteria=(), order=None, direction=Direction.DESC, scope=SCOPE):
    parsed = canonicalise(
        ParsedQuery(expression=AllOf(tuple(criteria)) if criteria else None,
                    ordering=Ordering(order, direction) if order else None),
        REGISTRY)
    return plan_screen(parsed, REGISTRY, scope, dialect="sqlite",
                       table_alias="")


def scalar(conn, sql, params):
    return conn.execute(sql, params).fetchone()[0]


def codes(conn, sql, params):
    return [r[0] for r in conn.execute(sql, params)]


# ── Ungoverned ordering must look untouched ──────────────────────────────────

def test_an_ungoverned_ordering_leaves_the_counts_identical():
    """An ordinary market-cap query must not acquire the appearance of having
    been through applicability machinery."""
    conn = build_db()
    p = plan(order="market_cap")

    assert scalar(conn, p.count_sql("u"), p.params) == 5
    assert scalar(conn, p.ranked_count_sql("u"), p.params) == 5
    assert p.exclusion_sql("u", "asx_code") is None
    assert not p.order_governed


def test_an_ungoverned_filter_carries_no_case_expression():
    p = plan([Criterion("sector", CriterionType.REQUIRED, "eq", "Materials")])
    assert "CASE WHEN" not in p.where
    assert "metric_states" not in p.where.split("compute_run_id")[-1]


def test_an_ungoverned_page_is_ordinary():
    conn = build_db()
    p = plan(order="market_cap")
    assert codes(conn, p.page_sql("u", "asx_code", limit=3), p.params) == \
        ["CBA", "IND1", "IND2"]


# ── Governed ordering: the counts must reconcile ─────────────────────────────

def test_ranked_total_plus_excluded_equals_total():
    conn = build_db()
    p = plan(order="grossed_up_yield")

    total = scalar(conn, p.count_sql("u"), p.params)
    ranked = scalar(conn, p.ranked_count_sql("u"), p.params)
    excluded = len(codes(conn, p.exclusion_sql("u", "asx_code"), p.params))

    assert total == 5 and ranked == 3 and excluded == 2
    assert ranked + excluded == total


def test_exclusions_are_drawn_only_from_screen_members():
    """A company failing an unrelated REQUIRED criterion was never in the
    result set; counting it as 'excluded from the ordering' would
    double-report one absence."""
    conn = build_db()
    p = plan([Criterion("sector", CriterionType.REQUIRED, "eq", "Materials")],
             order="grossed_up_yield")

    total = scalar(conn, p.count_sql("u"), p.params)
    excluded = codes(conn, p.exclusion_sql("u", "asx_code"), p.params)

    assert total == 3, "IND1, IND2, FEED are Materials"
    assert excluded == ["FEED"], "QAN is not a member, so not an exclusion"
    assert scalar(conn, p.ranked_count_sql("u"), p.params) + len(excluded) == total


def test_the_page_never_spends_a_slot_on_a_non_participant():
    conn = build_db()
    p = plan(order="grossed_up_yield")
    page = codes(conn, p.page_sql("u", "asx_code", limit=3), p.params)

    assert page == ["IND1", "CBA", "IND2"]
    assert not set(page) & {"FEED", "QAN"}


def test_a_governed_filter_and_a_governed_order_reconcile_together():
    conn = build_db()
    p = plan([Criterion("roe", CriterionType.REQUIRED, "gt", 12)],
             order="grossed_up_yield")

    total = scalar(conn, p.count_sql("u"), p.params)
    ranked = scalar(conn, p.ranked_count_sql("u"), p.params)
    excluded = len(codes(conn, p.exclusion_sql("u", "asx_code"), p.params))

    assert ranked + excluded == total
    assert "QAN" not in codes(conn, p.count_sql("u").replace("COUNT(*)",
                                                             "asx_code"),
                              p.params), "negative equity is not a high ROE"


# ── One scope, every statement ───────────────────────────────────────────────

def test_every_statement_carries_the_same_snapshot():
    """Resolving the scope per statement would let a compute finishing
    mid-request give one response two internally valid, mutually inconsistent
    snapshots."""
    p = plan(order="grossed_up_yield")
    statements = [p.count_sql("u"), p.ranked_count_sql("u"),
                  p.page_sql("u", "asx_code", 10), p.exclusion_sql("u", "asx_code")]

    for sql in statements:
        assert f"compute_run_id IN ({RUN_ID})" in sql

    assert p.snapshot == SCOPE.snapshot and p.run_ids == [RUN_ID]


def test_a_governed_query_without_a_scope_is_refused():
    try:
        plan([Criterion("roe", CriterionType.REQUIRED, "gt", 10)], scope=None)
    except CompileError as e:
        assert "no validated run scope" in str(e)
    else:
        raise AssertionError("governed data outside a contract must refuse")


def test_an_ungoverned_query_needs_no_scope():
    """The 274 fields P0-A does not govern must not acquire a run dependency."""
    p = plan([Criterion("sector", CriterionType.REQUIRED, "eq", "Materials")],
             scope=None)
    assert p.snapshot is None and "compute_run_id" not in p.where


# ── Membership is unaffected by ordering participation ───────────────────────

def test_membership_never_narrows_to_the_ranked_set():
    """total answers a different question from ranked_total, and the count
    query must not quietly answer the ranked one."""
    conn = build_db()
    with_order = plan(order="grossed_up_yield")
    without = plan()

    assert scalar(conn, with_order.count_sql("u"), with_order.params) == \
        scalar(conn, without.count_sql("u"), without.params) == 5


def test_pagination_is_stable_across_pages():
    conn = build_db()
    p = plan(order="grossed_up_yield")
    page1 = codes(conn, p.page_sql("u", "asx_code", 2, 0), p.params)
    page2 = codes(conn, p.page_sql("u", "asx_code", 2, 2), p.params)

    assert page1 == ["IND1", "CBA"] and page2 == ["IND2"]
    assert not set(page1) & set(page2), "no row appears on two pages"


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
