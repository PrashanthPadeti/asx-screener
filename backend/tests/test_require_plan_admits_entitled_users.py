#!/usr/bin/env python
"""
An entitled user must be admitted, not 500'd
============================================
22 October 2026. A customer subscribed to Premium at 05:20 UTC and by 05:23
every premium feature was returning 500:

    6  /api/v1/market-data/funds      NameError: name 'min_rank' is not defined
    4  /api/v1/market/heatmap         NameError: name 'min_rank' is not defined
    2  /api/v1/top5/current           NameError: name 'min_rank' is not defined
    2  /api/v1/top5/history           NameError: name 'min_rank' is not defined
    1  /api/v1/market-data/indices    NameError: name 'min_rank' is not defined
    1  /api/v1/commodities/           NameError: name 'min_rank' is not defined

He asked for a refund within ten minutes, and he was right to.

`require_plan` referenced `min_rank`, which a rename to `_level(minimum)`
had left behind. The line sits AFTER the plan comparison, so it was only
ever reached by users who PASSED it:

    unentitled user  -> 403, clean, with upgrade messaging
    ENTITLED user    -> NameError -> 500

The gate worked perfectly for everyone it was meant to refuse and broke for
everyone it was meant to admit. Paying was the thing that broke the site.

Why no test caught it
---------------------
The entitlement suite asserts that gates REFUSE. Refusal takes the early
return and never reaches the faulty line, so every one of those tests
passed while the admitting path raised NameError on first use. A gate has
two outcomes and only one was ever exercised.

These tests exercise the other one.

Run:  python tests/test_require_plan_admits_entitled_users.py
"""

import asyncio
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parents[1]
BACKEND = _HERE if (_HERE / "app" / "core" / "deps.py").exists() else Path.cwd()
sys.path.insert(0, str(BACKEND))

from fastapi import HTTPException                              # noqa: E402

from app.core.deps import require_plan                         # noqa: E402


def _call(plan: str, status: str = "active", email: str = "u@example.com"):
    """Invoke the dependency's inner check directly with a user dict."""
    check = require_plan("premium")
    return asyncio.run(check(user={"id": "u1", "email": email, "plan": plan,
                                   "subscription_status": status}))


def _raises(plan: str, status: str = "active") -> int | None:
    try:
        _call(plan, status)
    except HTTPException as exc:
        return exc.status_code
    return None


# ── The defect, stated as the property it violated ──────────────────────────

def test_an_entitled_subscriber_is_admitted():
    """The exact case that 500'd: premium plan, active subscription.

    Not "does not raise HTTPException" -- a NameError is not an
    HTTPException, so a test phrased that way would have passed while the
    endpoint returned 500.
    """
    user = _call("premium", "active")
    assert user["plan"] == "premium"


def test_admission_does_not_raise_any_exception_at_all():
    """Named separately because the failure was NameError, not HTTP 500.

    FastAPI turns an unhandled exception into a 500; the gate itself raised
    a plain NameError. Asserting on HTTP status alone cannot see that.
    """
    try:
        _call("premium", "active")
    except HTTPException:
        raise AssertionError("an entitled subscriber was refused")
    except Exception as exc:                                   # noqa: BLE001
        raise AssertionError(
            f"the gate raised {type(exc).__name__}: {exc} — FastAPI returns "
            f"this to the customer as 500 Internal Server Error")


def test_every_premium_gated_route_uses_this_function():
    """The blast radius, derived rather than listed.

    Six endpoints failed from one line because they share this gate. If a
    seventh is added, it inherits whatever this function does.
    """
    import re
    routes = (BACKEND / "app" / "api" / "v1" / "routes")
    users = sorted({p.name for p in routes.glob("*.py")
                    if re.search(r"require_plan\(", p.read_text(encoding="utf-8"))})
    assert len(users) >= 5, (
        f"expected require_plan to gate several route modules, found {users}")


# ── The paid-plan checks that never ran ─────────────────────────────────────

def test_a_past_due_subscriber_is_asked_to_fix_payment():
    """402, not 500.

    This block was unreachable, so a customer whose card failed was shown a
    broken site instead of a message telling them what to do about it.
    """
    assert _raises("premium", "past_due") == 402


def test_an_inactive_subscription_is_refused_cleanly():
    assert _raises("premium", "cancelled") == 403
    assert _raises("premium", "inactive") == 403


def test_a_trialing_subscriber_is_admitted():
    assert _call("premium", "trialing")["plan"] == "premium"


# ── Refusal still works. It always did; that is the point ───────────────────

def test_an_unentitled_user_is_still_refused():
    """The path that always worked, kept working.

    Every existing entitlement test exercises this one, which is why none of
    them saw the defect.
    """
    assert _raises("free", "inactive") == 403
    assert _raises("pro", "active") == 403


def test_the_subscription_check_is_skipped_for_free_minimums():
    """`_level(minimum) > 0` means "this gate requires a paid plan".

    A free-minimum gate must not demand an active subscription, or every
    free user would be refused by a check that does not apply to them.
    """
    free_gate = require_plan("free")
    user = asyncio.run(free_gate(user={"id": "u1", "email": "f@example.com",
                                       "plan": "free",
                                       "subscription_status": "inactive"}))
    assert user["plan"] == "free"


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
            except Exception as exc:                           # noqa: BLE001
                print(f"  ERROR {name}: {type(exc).__name__}: {exc}")
                failures.append(name)
    total = len([n for n in globals() if n.startswith("test_")])
    print(f"\n{total - len(failures)}/{total} passed")
    sys.exit(1 if failures else 0)
