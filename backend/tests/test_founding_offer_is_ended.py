#!/usr/bin/env python
"""
The founding-member promotion stays ended unless someone means to restart it
============================================================================
Ended 6 Oct 2026. `FOUNDING_MEMBER_LIMIT` is the single switch, and zero
disables the promotion in both places that matter:

    /billing/founding-member-status -> enabled: False, so the pricing page
                                       renders no offer at all
    _claim_founding_member          -> refuses, so no new subscriber is
                                       granted extended access

The DEFAULT is zero rather than an override in .env. At 100 the promotion
would silently return on any host whose .env lacked the key -- a fresh
deploy, a restored config, a new environment. An ended promotion should need
a deliberate act to restart, not an omission to resume.

Read with the AST rather than imported, so this runs without
pydantic-settings installed. A guard on a business decision is worth little
if it only runs where the full dependency set does.

Run:  python tests/test_founding_offer_is_ended.py
"""

import ast
import sys
from pathlib import Path

CONFIG = Path(__file__).resolve().parents[1] / "app" / "core" / "config.py"


def _default_of(name: str):
    tree = ast.parse(CONFIG.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", "") == name:
            return ast.literal_eval(node.value)
    raise AssertionError(f"{name} is not declared in {CONFIG}")


def test_the_promotion_is_off_by_default():
    limit = _default_of("FOUNDING_MEMBER_LIMIT")
    assert limit == 0, (
        f"FOUNDING_MEMBER_LIMIT defaults to {limit}, which RESTARTS the "
        f"founding-member promotion: the pricing page advertises it again and "
        f"new subscribers are granted 6 months for 1, or 3 years for 1. If "
        f"that is intended, change this test in the same commit and say why.")


def test_the_switch_still_gates_both_surfaces():
    """Zero is only an off switch while both call sites still consult it.

    A refactor that stopped reading the setting in either place would leave
    this test passing while the offer came back on one surface.
    """
    routes = (CONFIG.parents[1] / "api" / "v1" / "routes" / "stripe_routes.py")
    source = routes.read_text(encoding="utf-8")
    assert "FOUNDING_MEMBER_LIMIT" in source, (
        "stripe_routes no longer reads FOUNDING_MEMBER_LIMIT; the switch is "
        "not connected to anything")
    assert "founding_limit > 0" in source, (
        "the claim path no longer gates on a positive limit, so a new "
        "subscriber could be granted the offer while the pricing page hides it")
    assert "limit <= 0" in source, (
        "the status endpoint no longer short-circuits on a non-positive "
        "limit, so the pricing page could advertise an offer nobody can claim")


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
    total = len([n for n in globals() if n.startswith("test_")])
    print(f"\n{total - len(failures)}/{total} passed")
    sys.exit(1 if failures else 0)
