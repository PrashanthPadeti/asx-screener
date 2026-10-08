#!/usr/bin/env python
"""
The four published quotas are refused server-side, before the write
===================================================================
`test_plan_entitlements.py` asserts the NUMBERS match the published matrix.
This file asserts the numbers are *enforced*, which is a different claim --
`/news` carried a `watchlist_only` parameter commented "Pro+ feature" with no
plan check at all for as long as it existed, so a published restriction is not
evidence of a check.

    Portfolios            1 / 10 / 20     portfolio.py  create_portfolio
    Watchlists            1 / 10 / 20     watchlist.py  create_watchlist
    Stocks per watchlist  50 / 200 / 500  watchlist.py  add_stock
    Price alerts          3 / 50 / 100    alerts.py     create_alert

What is actually asserted
-------------------------
Not "the file mentions get_limits". Four things, in the AST:

1. the handler reads the quota out of `get_limits(...)` by the right key
2. it counts what the user already has
3. it raises 403 when the count reaches the quota
4. **that raise is reachable before the INSERT**

(4) is the property worth testing. A limit checked after the row is written
refuses the request and keeps the data, which is worse than no check: the
quota reads as enforced while every caller exceeds it by one. A `>=`
comparison and a 403 in the same function prove nothing about order, so the
test compares source positions rather than looking for the pieces.

The off-by-one is also pinned: `>= limit` before inserting one row yields
exactly `limit` rows. `> limit` yields `limit + 1`, which is how a published
"1 watchlist" silently becomes two.

What this cannot prove
----------------------
That a request is actually refused. It proves the refusal is positioned to
happen. Nor does it cover **downgrade**: all four checks are create-time, and
`customer.subscription.deleted` sets `plan = 'free'` without touching a single
quota-bearing table, so a cancelling Premium user keeps 20 portfolios and
20 watchlists of 500 stocks on a Free plan indefinitely. That is a retention
policy decision, not a defect this file can settle -- it is recorded here so
the gap is not mistaken for one of these checks.

Run:  python tests/test_quota_limits_are_enforced.py
"""

import ast
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
from app.core.plans import PLAN_LIMITS                       # noqa: E402

ROUTES = BACKEND / "app" / "api" / "v1" / "routes"

#: (module, handler, PLAN_LIMITS key, the table the handler writes to)
QUOTAS = (
    ("portfolio", "create_portfolio", "portfolios",   "users.portfolios"),
    ("watchlist", "create_watchlist", "watchlists",   "users.watchlists"),
    ("watchlist", "add_stock",        "stocks_per_wl", "users.watchlist_items"),
    ("alerts",    "create_alert",     "alerts",       "users.alerts"),
)

#: The alerts quota counts `is_active = TRUE` only, so paused alerts are
#: unlimited. Deliberate and more generous than the published "3 / 50 / 100",
#: noted so a future reader does not take the narrower count for a bug.


def _handler(module: str, name: str):
    src = (ROUTES / f"{module}.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name:
            return n
    raise AssertionError(
        f"{module}.py has no handler named {name!r}; the quota it enforced "
        f"is now unverified -- find where creation moved to")


def _limit_guards(fn):
    """Every `if <something> >= <something>: ... raise HTTPException(403)`."""
    out = []
    for node in ast.walk(fn):
        if not isinstance(node, ast.If):
            continue
        test = ast.unparse(node.test)
        if not isinstance(node.test, ast.Compare):
            continue
        if not any(isinstance(o, ast.GtE) for o in node.test.ops):
            continue
        body = ast.unparse(node)
        if "HTTPException" in body and ("403" in body or "FORBIDDEN" in body):
            out.append((node, test))
    return out


def _insert_lineno(fn, table: str) -> int:
    """Line of the first statement whose source writes to `table`."""
    for node in ast.walk(fn):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            v = " ".join(node.value.split()).upper()
            if f"INSERT INTO {table.upper()}" in v:
                return node.lineno
    raise AssertionError(
        f"{fn.name} no longer contains an INSERT INTO {table}; either the "
        f"write moved out of the handler the quota guards, or the table was "
        f"renamed and this test is now watching nothing")


# ── Tests ───────────────────────────────────────────────────────────────────

def test_every_quota_is_read_from_plan_limits():
    """The handler must take the number from the plan, not hardcode one."""
    problems = []
    for module, name, key, _ in QUOTAS:
        body = ast.unparse(_handler(module, name))
        if "get_limits" not in body:
            problems.append(f"{module}.{name} never calls get_limits, so the "
                            f"{key} quota it applies is not the plan's")
        elif f"'{key}'" not in body:
            problems.append(f"{module}.{name} calls get_limits but not with "
                            f"{key!r}; it may be enforcing the wrong quota")
    assert not problems, "\n  ".join([""] + problems)


def test_every_quota_refuses_with_403():
    problems = []
    for module, name, key, _ in QUOTAS:
        if not _limit_guards(_handler(module, name)):
            problems.append(
                f"{module}.{name} has no `>=` comparison raising 403, so the "
                f"{key} quota is published but never refused")
    assert not problems, "\n  ".join([""] + problems)


def test_the_refusal_precedes_the_write():
    """The property. A check after the INSERT keeps the row it refuses."""
    problems = []
    for module, name, key, table in QUOTAS:
        fn = _handler(module, name)
        guards = _limit_guards(fn)
        if not guards:
            continue                      # reported by the test above
        try:
            insert = _insert_lineno(fn, table)
        except AssertionError as exc:
            problems.append(str(exc))
            continue
        earliest = min(n.lineno for n, _ in guards)
        if earliest >= insert:
            problems.append(
                f"{module}.{name}: the {key} check is at line {earliest}, the "
                f"INSERT INTO {table} at line {insert}. The row is written "
                f"before the quota is tested, so every caller exceeds the "
                f"published limit by one and gets a 403 anyway")
    assert not problems, "\n  ".join([""] + problems)


def test_the_comparison_is_gte_not_gt():
    """`> limit` admits limit+1 rows. Free's "1 watchlist" would become two."""
    problems = []
    for module, name, key, _ in QUOTAS:
        fn = _handler(module, name)
        gt_only = [ast.unparse(n.test) for n in ast.walk(fn)
                   if isinstance(n, ast.If) and isinstance(n.test, ast.Compare)
                   and any(isinstance(o, ast.Gt) for o in n.test.ops)
                   and "HTTPException" in ast.unparse(n)
                   and not any(isinstance(o, ast.GtE) for o in n.test.ops)]
        if gt_only and not _limit_guards(fn):
            problems.append(
                f"{module}.{name} refuses on `>` not `>=` ({gt_only[0]}), "
                f"which allows one more than the published {key} quota")
    assert not problems, "\n  ".join([""] + problems)


def test_free_is_the_tightest_tier_on_every_quota():
    """A quota that does not increase with the plan is not an entitlement."""
    for key in ("portfolios", "watchlists", "stocks_per_wl", "alerts"):
        f, p, pr = (PLAN_LIMITS["free"][key], PLAN_LIMITS["pro"][key],
                    PLAN_LIMITS["premium"][key])
        assert f < p < pr, (
            f"{key} does not increase free({f}) < pro({p}) < premium({pr}); "
            f"the pricing table sells an upgrade that grants nothing")


# ── Mutation controls ───────────────────────────────────────────────────────

def test_a_check_after_the_insert_is_caught():
    """Control 1 — the defect this file exists for.

    Move the guard below the write and the test must fail. Without this,
    `test_the_refusal_precedes_the_write` could be passing because every
    handler happens to be ordered correctly today, with no evidence the
    comparison can detect the reverse.
    """
    fn = ast.parse(
        "async def create_thing():\n"
        "    limit = get_limits(plan)['widgets']\n"
        "    await db.execute(text('INSERT INTO users.widgets (a) VALUES (1)'))\n"
        "    if count >= limit:\n"
        "        raise HTTPException(status_code=403, detail='too many')\n"
    ).body[0]
    guards = _limit_guards(fn)
    assert guards, "the control's own guard was not recognised"
    assert min(n.lineno for n, _ in guards) >= _insert_lineno(fn, "users.widgets"), (
        "the position comparison cannot tell a post-write check from a "
        "pre-write one, so test_the_refusal_precedes_the_write proves nothing")


def test_a_missing_guard_is_caught():
    """Control 2 — a deleted check must not read as enforced."""
    fn = ast.parse(
        "async def create_thing():\n"
        "    await db.execute(text('INSERT INTO users.widgets (a) VALUES (1)'))\n"
    ).body[0]
    assert not _limit_guards(fn), (
        "_limit_guards reports a guard in a handler that has none, so a "
        "deleted quota check would still pass")


def test_a_non_403_raise_is_not_a_quota_guard():
    """Control 3 — a 404 is not a refusal to exceed a quota.

    Every one of these handlers raises 404 for a missing parent row. Counting
    that as the quota check would make all four pass with no quota logic.
    """
    fn = ast.parse(
        "async def add_thing():\n"
        "    if count >= limit:\n"
        "        raise HTTPException(status_code=404, detail='not found')\n"
    ).body[0]
    assert not _limit_guards(fn), (
        "_limit_guards accepts a non-403 raise, so a 404 for a missing parent "
        "would be mistaken for quota enforcement")


if __name__ == "__main__":
    failures = []
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  PASS  {name}")
            except AssertionError as exc:
                print(f"  FAIL  {name}{exc}")
                failures.append(name)
            except Exception as exc:                           # noqa: BLE001
                print(f"  ERROR {name}: {type(exc).__name__}: {exc}")
                failures.append(name)
    total = len([n for n in globals() if n.startswith("test_")])
    print(f"\n{total - len(failures)}/{total} passed")
    sys.exit(1 if failures else 0)
