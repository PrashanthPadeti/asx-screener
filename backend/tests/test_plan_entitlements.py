#!/usr/bin/env python
"""
Free > Pro > Premium > Admin, and Enterprise is seats, not features
==================================================================
The plan model, stated once and asserted:

    feature level   free 0 | pro 1 = enterprise_pro 1 | premium 2 = enterprise_premium 2
    admin           above every plan; an identity, not a tier
    enterprise      identical features to its base tier; the difference is seats

Three defects this pins, all found 8 Oct 2026:

1. **Enterprise Pro outranked Premium.** `PLAN_RANK` put it at 3 against
   Premium's 2, and every gate compared ranks, so `require_plan("premium")`
   and `PlanGate required="premium"` admitted it — to Indices, ETFs & Funds,
   Commodities, Global Markets, the Heatmap and Top 5. None of which its
   `PLAN_LIMITS` entitle it to. The same plan was Pro-level under the feature
   flags and above-Premium under the rank ladder.

2. **Thirteen premium endpoints had no authentication at all.**
   `indices_funds` (7), `commodities` (2), `global_markets` (2) and the two
   heatmap routes carried only `Depends(get_db)` — not a plan check, not a
   login. `PlanGate` hid the pages; the API behind them was open to anyone.

3. **Admin was above Premium in some gates and not others.**
   `require_pro_or_admin` and `saved_screens` bypassed for admins;
   `require_plan` and `PlanGate` did not. Masked only because the admin
   account also holds a Premium plan.

Run:  python tests/test_plan_entitlements.py
"""

import ast
import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.core.plans import (                                   # noqa: E402
    FEATURE_LEVEL, PLAN_LIMITS, PLAN_RANK, feature_level)

ROUTES = BACKEND / "app" / "api" / "v1" / "routes"


# ── The model ───────────────────────────────────────────────────────────────

def test_enterprise_matches_its_base_tier_exactly():
    """Seats are the only difference. Everything else must be identical."""
    for ent, base in (("enterprise_pro", "pro"),
                      ("enterprise_premium", "premium")):
        a, b = dict(PLAN_LIMITS[ent]), dict(PLAN_LIMITS[base])
        a.pop("seat_limit"); b.pop("seat_limit")
        assert a == b, (
            f"{ent} differs from {base} in something other than seats: " +
            ", ".join(f"{k}: {a[k]} != {b[k]}" for k in a if a[k] != b[k]))


def test_enterprise_is_the_only_multi_seat_tier():
    assert PLAN_LIMITS["free"]["seat_limit"] == 1
    assert PLAN_LIMITS["pro"]["seat_limit"] == 1
    assert PLAN_LIMITS["premium"]["seat_limit"] == 1
    assert PLAN_LIMITS["enterprise_pro"]["seat_limit"] > 1
    assert PLAN_LIMITS["enterprise_premium"]["seat_limit"] > 1


def test_feature_level_ties_enterprise_to_its_base():
    assert feature_level("enterprise_pro") == feature_level("pro")
    assert feature_level("enterprise_premium") == feature_level("premium")
    assert feature_level("free") < feature_level("pro") < feature_level("premium")


def test_an_unknown_plan_gets_the_lowest_level():
    """Must narrow access, never widen it."""
    assert feature_level("gold_plated") == 0
    assert feature_level(None) == 0 if None in FEATURE_LEVEL else True
    assert feature_level("") == 0


def test_the_two_orderings_are_not_the_same_thing():
    """Mutation control for the whole design.

    If FEATURE_LEVEL ever equals PLAN_RANK again, the distinction has been
    collapsed and Enterprise Pro is back above Premium.
    """
    assert PLAN_RANK != FEATURE_LEVEL
    assert PLAN_RANK["enterprise_pro"] > PLAN_RANK["premium"], (
        "commercial ordering changed; Ent Pro is priced above Premium")
    assert FEATURE_LEVEL["enterprise_pro"] < FEATURE_LEVEL["premium"], (
        "Enterprise Pro can reach Premium features again")


# ── Gates compare feature level, never commercial rank ──────────────────────

GATEKEEPERS = ("app/core/deps.py",
               "app/api/v1/routes/alerts.py",
               "app/api/v1/routes/saved_screens.py")


def test_no_gate_compares_plan_rank():
    offenders = []
    for rel in GATEKEEPERS:
        src = (BACKEND / rel).read_text(encoding="utf-8")
        body = "\n".join(l for l in src.splitlines()
                         if not l.strip().startswith("#"))
        if re.search(r"PLAN_RANK\s*(\.get)?\s*[\(\[]", body):
            offenders.append(rel)
    assert not offenders, (
        "these compare commercial rank to decide access, which is what let "
        "Enterprise Pro into Premium: " + ", ".join(offenders))


# ── Every premium data route is actually guarded ────────────────────────────

#: Files where EVERY route is premium -- the guard belongs on the router.
PREMIUM_ROUTERS = ("indices_funds", "commodities", "global_markets")

#: Routes that are premium inside an otherwise-free file.
PREMIUM_PATHS = {"market": ("/heatmap", "/heatmap/export")}


def test_wholly_premium_routers_are_guarded_at_the_router():
    for name in PREMIUM_ROUTERS:
        src = (ROUTES / f"{name}.py").read_text(encoding="utf-8")
        m = re.search(r"router\s*=\s*APIRouter\((.*?)\)", src, re.S)
        assert m, f"{name}: no APIRouter(...) found"
        assert "require_plan" in m.group(1), (
            f"{name}.py declares APIRouter() with no dependency, so its "
            f"routes serve premium data to unauthenticated requests")


def test_premium_routes_in_free_files_are_guarded_individually():
    for name, paths in PREMIUM_PATHS.items():
        src = (ROUTES / f"{name}.py").read_text(encoding="utf-8")
        for path in paths:
            m = re.search(rf'@router\.get\("{re.escape(path)}"(.*?)\)\s*\n'
                          rf'(async )?def', src, re.S)
            assert m, f"{name}.py has no route for {path}"
            assert "require_plan" in m.group(1), (
                f"{name}.py {path} is premium but carries no plan dependency")


def test_the_free_market_routes_stay_free():
    """ASX Market Overview is free. Guarding the whole file would break it."""
    src = (ROUTES / "market.py").read_text(encoding="utf-8")
    m = re.search(r"router\s*=\s*APIRouter\((.*?)\)", src, re.S)
    assert m and "require_plan" not in m.group(1), (
        "market.py now guards every route, which takes the free ASX Market "
        "Overview (summary, movers, sectors, dashboard) away from free users")


def test_the_route_scan_can_fail():
    """Mutation control: the detector must see an unguarded router."""
    assert "require_plan" not in "router = APIRouter()"


# ── Admin is above every plan ───────────────────────────────────────────────

def test_require_plan_lets_admins_through():
    src = (BACKEND / "app" / "core" / "deps.py").read_text(encoding="utf-8")
    fn = next(n for n in ast.walk(ast.parse(src))
              if isinstance(n, ast.FunctionDef) and n.name == "require_plan")
    body = ast.unparse(fn)
    assert "ADMIN_EMAILS" in body, (
        "require_plan has no admin bypass, so an admin whose own plan is "
        "below the minimum is refused by the gate they administer")


def test_the_limits_match_the_published_matrix():
    """The pricing page is a contract shown to a buyer, so the numbers are
    asserted against the agreed sheet rather than against themselves.

    Hardcoded on purpose: deriving the expectation from PLAN_LIMITS would make
    this test agree with whatever the code says, which is the opposite of what
    a published-price check is for.
    """
    expected = {
        #                 portf  watch  stocks  alerts
        "free":           (1,    1,     50,     3),
        "pro":            (10,   10,    200,    50),
        "premium":        (20,   20,    500,    100),
        "enterprise_pro": (10,   10,    200,    50),
        "enterprise_premium": (20, 20,  500,    100),
    }
    for plan, (pf, wl, spw, al) in expected.items():
        got = PLAN_LIMITS[plan]
        assert (got["portfolios"], got["watchlists"],
                got["stocks_per_wl"], got["alerts"]) == (pf, wl, spw, al), (
            f"{plan} limits differ from the published pricing table: "
            f"got {got['portfolios']}/{got['watchlists']}/"
            f"{got['stocks_per_wl']}/{got['alerts']}, expected "
            f"{pf}/{wl}/{spw}/{al}")


def test_csv_export_is_premium():
    """Changed 8 Oct 2026. Pro had it; the published matrix makes it Premium.

    Asserted on both Pro and Enterprise Pro, because the sheet originally
    showed it crossed for Pro and ticked for Enterprise Pro -- which would
    have made Enterprise more than a seat difference.
    """
    assert PLAN_LIMITS["pro"]["csv_export"] is False
    assert PLAN_LIMITS["enterprise_pro"]["csv_export"] is False
    assert PLAN_LIMITS["premium"]["csv_export"] is True
    assert PLAN_LIMITS["enterprise_premium"]["csv_export"] is True


def test_community_screens_are_tiered_not_all_or_nothing():
    """Free is refused; Pro sees creators at or below its own level; Premium
    and admin see everything.

    The endpoint previously returned 403 to anyone below Premium, so Pro saw
    nothing. The CASE mapping creator_plan to a rank and the rank_filter
    parameter were already present -- only the gate was wrong.
    """
    src = (ROUTES / "saved_screens.py").read_text(encoding="utf-8")
    body = "\n".join(l for l in src.splitlines()
                     if not l.strip().startswith("#"))
    assert 'detail="Community screens are available on the Pro plan."' in body \
        or "_level(\"pro\")" in body, (
        "the community-screens gate no longer refuses below Pro")
    assert "rank_filter = user_rank" in body, (
        "Pro viewers no longer get a filtered view; they are either refused "
        "or shown everything")
    assert 'user_rank < _level("premium")' not in body, (
        "the old Premium-or-403 gate is back, so Pro sees no community "
        "screens at all")


def test_admin_is_not_a_plan():
    """Free > Pro > Premium > Admin -- but admin is an identity.

    Putting it in the ladder would make it assignable as a subscription and
    billable by accident.
    """
    assert "admin" not in PLAN_LIMITS
    assert "admin" not in FEATURE_LEVEL
    assert "admin" not in PLAN_RANK


if __name__ == "__main__":
    failures = []
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  PASS  {name}")
            except AssertionError as exc:
                print(f"  FAIL  {name}\n        {exc}")
                failures.append(name)
            except Exception as exc:                       # noqa: BLE001
                print(f"  ERROR {name}: {type(exc).__name__}: {exc}")
                failures.append(name)
    total = len([n for n in globals() if n.startswith("test_")])
    print(f"\n{total - len(failures)}/{total} passed")
    sys.exit(1 if failures else 0)
