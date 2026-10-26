"""
The billing surface: admin-only, non-blocking, and honest about failure
=======================================================================
This page shows every paying customer, what they pay, when they are next
charged, and their full transaction history. Three properties have to hold,
and each has a specific incident behind it.

1. ADMIN ONLY, ENFORCED
   An entitlement is true only when the access path enforces it. Thirteen
   endpoints in this codebase were once reachable unauthenticated. Revenue
   and customer payment history is the worst possible thing to leave open.

2. NEVER BLOCKS THE EVENT LOOP
   The Stripe SDK is synchronous. A blocking network call inside an async
   handler stops the API answering anything at all -- the same failure that
   made short_positions a five-minute outage. Every Stripe call must go
   through asyncio.to_thread.

3. A FAILED READ IS NOT AN EMPTY RESULT
   If Stripe cannot be reached, the page must say so where the numbers are
   read. A dashboard that renders zeros on a failed call tells the owner
   their business shrank. Cannot-obtain and does-not-exist are different
   facts.

Structural, by AST. These are syntactic properties -- which decorator, which
dependency, which call wraps which -- so they are checked in the syntax
rather than by matching strings that would also match a docstring.
"""

import ast
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

MODULE = BACKEND / "app" / "api" / "v1" / "routes" / "admin_billing.py"
ROUTER = BACKEND / "app" / "api" / "v1" / "router.py"


def _tree() -> ast.Module:
    return ast.parse(MODULE.read_text(encoding="utf-8"), str(MODULE))


def _endpoints() -> list[ast.AsyncFunctionDef]:
    """Functions carrying an @router.<method> decorator."""
    out = []
    for node in ast.walk(_tree()):
        if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            continue
        for dec in node.decorator_list:
            func = dec.func if isinstance(dec, ast.Call) else dec
            if (isinstance(func, ast.Attribute)
                    and isinstance(func.value, ast.Name)
                    and func.value.id == "router"):
                out.append(node)
                break
    return out


def _depends_on(fn, name: str) -> bool:
    """Whether a parameter default is Depends(<name>)."""
    for default in fn.args.defaults + [d for d in fn.args.kw_defaults if d]:
        if (isinstance(default, ast.Call)
                and getattr(default.func, "id", "") == "Depends"
                and default.args
                and getattr(default.args[0], "id", "") == name):
            return True
    return False


def test_the_module_exists_and_declares_endpoints():
    """The population for everything below."""
    assert MODULE.exists(), f"{MODULE} is missing"
    eps = _endpoints()
    assert len(eps) >= 2, (
        f"only {len(eps)} endpoints found; this suite's checks would pass "
        f"over almost nothing")


def test_every_endpoint_requires_an_admin():
    """Declared is not enough -- the access path must enforce it.

    Customer payment history and revenue totals. If this ever fails, the
    correct response is to take the route out, not to note it.
    """
    unguarded = [fn.name for fn in _endpoints()
                 if not _depends_on(fn, "require_admin")]
    assert not unguarded, (
        "these billing endpoints do not require an admin: "
        + ", ".join(unguarded))


def test_no_stripe_call_runs_on_the_event_loop():
    """Every Stripe SDK call must sit inside a function that is only ever
    invoked through asyncio.to_thread.

    The SDK blocks. Called directly from an async handler it stops the whole
    API -- not this page, the whole API -- for the duration of the round
    trip, and Stripe is a third party whose latency we do not control.
    """
    tree = _tree()

    # Names of the sync helpers that touch Stripe.
    stripe_helpers = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):          # sync def only
            src = ast.dump(node)
            if "Subscription" in src or "Invoice" in src or "Customer" in src:
                stripe_helpers.add(node.name)

    # Every call to one of those must be an argument to asyncio.to_thread.
    threaded, direct = set(), []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if (isinstance(func, ast.Attribute) and func.attr == "to_thread"
                and node.args):
            target = node.args[0]
            if isinstance(target, ast.Name):
                threaded.add(target.id)
        elif isinstance(func, ast.Name) and func.id in stripe_helpers:
            direct.append(func.id)

    assert stripe_helpers, (
        "no Stripe-touching helper found; this check has lost its population")
    missed = sorted(stripe_helpers - threaded)
    assert not missed, (
        f"these Stripe helpers are never dispatched via asyncio.to_thread: "
        f"{missed}. A synchronous Stripe call on the event loop stops the "
        f"entire API answering.")
    assert not direct, (
        f"Stripe helper(s) called directly rather than through to_thread: "
        f"{sorted(set(direct))}")


def test_a_stripe_failure_is_reported_not_swallowed():
    """The list endpoint must carry the error into its response.

    Returning rows with silently-absent billing fields would render as
    'nobody is subscribed', which is the shape of a false reassurance.
    """
    src = MODULE.read_text(encoding="utf-8")
    assert "stripe_error" in src, "no stripe_error channel exists"
    # It must reach the SUMMARY, which is where the totals are read. An error
    # attached only to individual rows is easy to miss above a headline
    # number that is quietly wrong.
    summary = src[src.index('"summary"'):]
    assert "stripe_error" in summary[:800], (
        "the summary block does not carry stripe_error — the totals could "
        "be rendered as fact while the read that produced them failed")


def test_cancelling_customers_are_not_counted_as_recurring_revenue():
    """MRR must exclude a subscription that will not renew.

    A customer who has turned off auto-renewal is still 'active' in Stripe
    right up to the end date. Counting them keeps revenue looking healthy
    until the month it is not -- and that invisibility is the exact defect
    this page was built to fix.
    """
    src = MODULE.read_text(encoding="utf-8")
    body = src[src.index("def _mrr_minor"):]
    body = body[:body.index("\ndef ")]
    assert "cancel_at_period_end" in body, (
        "_mrr_minor does not consider cancel_at_period_end, so MRR includes "
        "revenue that is already leaving")


def test_the_router_registers_the_billing_surface():
    src = ROUTER.read_text(encoding="utf-8")
    assert "admin_billing" in src, "the billing router is not registered"
    assert "/admin/billing" in src, "unexpected prefix for the billing router"


if __name__ == "__main__":
    # The gate runs suites as standalone scripts and reads this summary.
    # Without it the file would exit 0 having executed nothing and be
    # counted as passing -- see v11.2.47.
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
        except Exception as e:                                # noqa: BLE001
            failures.append(name)
            print(f"  ERROR {name}  - {type(e).__name__}: {e}")
    print(f"\n{len(tests) - len(failures)}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
