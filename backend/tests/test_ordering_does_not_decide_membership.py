"""An ordering decides position, never membership
================================================
A Premium customer loaded "Multi-Factor Quality + Momentum", removed the
Piotroski filter, and the page showed

    9 stocks matched
    No stocks match your filters.

Both lines came from one response. The count answered membership; the data
query answered membership AND ranking participation, because it carried

    WHERE {where} AND {plan.order_applicable}

and ``piotroski_f_score`` is computed for none of the 2,113 companies, so no
member could participate. The preset sets the sort as well as the filters, so
removing the Piotroski FILTER left the Piotroski SORT -- and four presets
sorted by it.

Three statements carried the clause: the filter screen's data query, the
Query Mode CSV export (under a comment promising it matched the interactive
route exactly), and ScreenPlan.page_sql. compile_screen had stated the
intended rule the whole time:

    "a company with an unavailable yield stays in the result set and is
     absent from the yield ordering. Neither dropped nor zeroed."

What is tested where
--------------------
The BEHAVIOUR -- members survive, non-participants sort last, a withheld
value cannot position a row -- executes against sqlite in
test_screen_plan.py, through the plan object the route shares.

This file guards the ROUTE, which emits Postgres against a table the gate's
clone has no rows in. So it asserts the property structurally, from the AST:
``order_applicable`` may be read only where it decides ORDER, plus the one
count that deliberately measures participation. A textual search would pass
on the paragraph above, which names the defect in full -- that is how three
guards were fooled on 30 Oct 2026.

Run under pytest, or standalone:
    cd backend && ../asx-venv/bin/python tests/test_ordering_does_not_decide_membership.py
"""

import ast
import sys
from pathlib import Path

BACKEND  = Path(__file__).resolve().parents[1]
ROUTE    = BACKEND / "app/api/v1/routes/screener.py"
PLAN     = BACKEND / "compute/engine/screen_sql.py"
FRONTEND = BACKEND.parent / "frontend"

sys.path.insert(0, str(BACKEND))


# ── Where the route is allowed to consult participation ──────────────────────
# _order_by  builds the ORDER BY, which is the whole point of the attribute.
# run_screener runs the ranked count, which deliberately measures how many
#              members participate -- it reports a number, it filters nothing.
PARTICIPATION_READERS = {"_order_by", "run_screener"}


def _enclosing_functions(tree) -> dict:
    """node -> name of the function it sits in, for every node in the tree."""
    owner = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for child in ast.walk(node):
            owner.setdefault(child, node.name)
    return owner


def _participation_reads(path: Path) -> list:
    """(function name, line) for every read of ``.order_applicable``."""
    tree  = ast.parse(path.read_text(encoding="utf-8"))
    owner = _enclosing_functions(tree)
    return [(owner.get(n, "<module>"), n.lineno)
            for n in ast.walk(tree)
            if isinstance(n, ast.Attribute) and n.attr == "order_applicable"]


def test_the_route_consults_participation_only_where_it_decides_order():
    reads = _participation_reads(ROUTE)
    assert reads, (
        "the route never reads order_applicable at all; a governed sort no "
        "longer distinguishes a rankable company from an unrankable one, and "
        "a withheld value can position a row")

    stray = sorted({fn for fn, _ in reads} - PARTICIPATION_READERS)
    assert not stray, (
        f"order_applicable is read in {stray}, outside the ordering and the "
        f"ranked count. Every previous occurrence outside those narrowed a "
        f"WHERE, which is how membership came to depend on sortability")


def test_the_route_builds_every_order_by_through_one_function():
    """Three statements had their own ORDER BY and only some of them were
    right. A rule that lives in one function cannot be half-applied."""
    src = ROUTE.read_text(encoding="utf-8")
    assert src.count("ORDER BY {order_by}") >= 3, (
        "fewer than three statements take their ordering from _order_by; "
        "the filter screen, Query Mode and the CSV export all need it")
    assert "ORDER BY {sort_expr}" not in src, (
        "a statement still interpolates the sort column directly, so it "
        "bypasses the participation-first rule")


def test_participation_leads_the_ordering():
    """NULLS LAST is not sufficient on its own.

    A metric is withheld by the SIDECAR; the column underneath can still hold
    the forensic value. CBA's EV/EBITDA is stored as 0.0 and suppressed --
    under a plain ``ORDER BY ev_to_ebitda ASC NULLS LAST`` it wins the
    cheapest-first screen outright.
    """
    tree = ast.parse(ROUTE.read_text(encoding="utf-8"))
    fn = next((n for n in ast.walk(tree)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
               and n.name == "_order_by"), None)
    assert fn is not None, "_order_by is gone; the rule has no single home"

    appends = [n for n in ast.walk(fn)
               if isinstance(n, ast.Call)
               and isinstance(n.func, ast.Attribute)
               and n.func.attr == "append"]
    assert len(appends) >= 3, (
        f"_order_by builds {len(appends)} sort key(s); it needs the "
        f"participation flag, the metric and a tiebreak")

    guarded = [n for n in ast.walk(fn) if isinstance(n, ast.If)]
    assert guarded, (
        "the participation key is unconditional, so an ungoverned sort "
        "acquires a CASE expression it has no use for")


def test_membership_has_exactly_one_definition():
    """The ranked count was built from ``plan.where`` alone while the count
    and the page carried the price and status conditions too, so it counted
    delisted companies as ranked members and min() hid the overcount."""
    tree = ast.parse(ROUTE.read_text(encoding="utf-8"))
    names = {n.name for n in ast.walk(tree)
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    assert "_membership_where" in names, (
        "membership is not defined in one place, so the count, the page and "
        "the ranked count can each answer a different question")

    calls = [n for n in ast.walk(tree)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
             and n.func.id == "_membership_where"]
    assert len(calls) >= 4, (
        f"only {len(calls)} statement(s) use the shared membership "
        f"definition; the filter screen, its ranked count, Query Mode and "
        f"the CSV export all draw from the same set")


# ── The plan object, which the route and the tests share ─────────────────────

def test_the_page_statement_does_not_narrow_by_participation():
    """ScreenPlan.page_sql. Its behaviour is executed in test_screen_plan.py;
    this asserts the clause itself is gone, so a revert is visible here even
    if the sqlite fixture stops covering the case."""
    tree = ast.parse(PLAN.read_text(encoding="utf-8"))
    fn = next((n for n in ast.walk(tree)
               if isinstance(n, ast.FunctionDef) and n.name == "page_sql"), None)
    assert fn is not None, "ScreenPlan.page_sql is gone"

    body = ast.dump(ast.Module(body=fn.body, type_ignores=[]))
    assert "'where'" in body or "where" in body, "page_sql no longer filters at all"

    # The old shape: `clauses = f"{clauses} AND {self.order_applicable}"`.
    joined = [n for n in ast.walk(fn)
              if isinstance(n, ast.JoinedStr)
              and " AND " in "".join(v.value for v in n.values
                                     if isinstance(v, ast.Constant)
                                     and isinstance(v.value, str))]
    assert not joined, (
        "page_sql composes an ' AND ' into its WHERE again; membership must "
        "come from self.where alone")


def test_the_counts_still_answer_their_own_questions():
    """The fix must not go the other way. ranked_count_sql and exclusion_sql
    exist to say who cannot be ranked; dropping the clause from THEM would
    make the exclusion unreportable and the page silent again."""
    src = PLAN.read_text(encoding="utf-8")
    tree = ast.parse(src)
    for name in ("ranked_count_sql", "exclusion_sql"):
        fn = next((n for n in ast.walk(tree)
                   if isinstance(n, ast.FunctionDef) and n.name == name), None)
        assert fn is not None, f"ScreenPlan.{name} is gone"
        reads = [n for n in ast.walk(fn)
                 if isinstance(n, ast.Attribute) and n.attr == "order_applicable"]
        assert reads, (
            f"{name} no longer consults participation, so the response can "
            f"no longer say who was excluded from the ordering")


# ── The reason must survive to the customer ──────────────────────────────────
# Absence was recorded, stored, returned -- and died at the page. The backend
# has sent ranked_total and excluded_from_ordering since the ordering contract
# shipped; neither name appeared anywhere in the frontend.

def _frontend(name: str) -> str:
    path = FRONTEND / name
    if not path.exists():
        raise Skipped(f"{name} (frontend not present in this checkout)")
    return path.read_text(encoding="utf-8")


class Skipped(Exception):
    """Needs something this environment does not have."""


def test_the_client_type_declares_the_exclusion():
    src = _frontend("lib/api.ts")
    for field in ("ranked_total", "excluded_from_ordering"):
        assert field in src, (
            f"ScreenerResponse does not declare {field}, so no page can read "
            f"it: the API explains itself and TypeScript discards it")


def test_the_screener_page_reads_and_renders_the_exclusion():
    src = _frontend("app/screener/page.tsx")
    assert "res.excluded_from_ordering" in src, (
        "the page never reads excluded_from_ordering off the response")
    assert "setExcluded" in src, (
        "the exclusion is read and thrown away without reaching state")
    assert "excluded.count" in src, (
        "nothing renders the exclusion; the customer still sees an "
        "unexplained result")


def test_the_page_cannot_call_a_non_empty_result_empty():
    """The precise lie: total 9, rows 0, and the words "No stocks match your
    filters". The cause is fixed upstream, but the page must not be able to
    say it again."""
    src = _frontend("app/screener/page.tsx")
    assert "total > 0 ?" in src, (
        "the empty state does not distinguish 'nothing matched' from "
        "'something matched and none of it arrived'")


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failures, skipped = [], []
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except Skipped as e:
            skipped.append(name)
            print(f"  SKIP  {name}  - needs {e}")
        except AssertionError as e:
            failures.append(name)
            print(f"  FAIL  {name}  - {e}")
        except Exception as e:                                 # noqa: BLE001
            failures.append(name)
            print(f"  ERROR {name}  - {type(e).__name__}: {e}")
    passed = len(tests) - len(failures) - len(skipped)
    print(f"\n{passed}/{len(tests)} passed"
          + (f", {len(skipped)} skipped" if skipped else ""))
    sys.exit(1 if failures else 0)
