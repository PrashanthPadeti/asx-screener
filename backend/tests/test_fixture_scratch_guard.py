#!/usr/bin/env python
"""
The destructive fixture must refuse anything but an approved scratch database
=============================================================================
`tests/fixtures/prove_stale_metric_rejection.py` mutates `market.daily_metrics`
and `market.daily_prices` in its setup. It lives under `tests/`, which
`canonical_boundary` excludes from the publication-authority scan -- correctly,
because a fixture is not application code. But that exclusion means the
fixture's own target guard is now the ONLY barrier between it and production.

A guard that is the sole barrier has to be negative-tested, and the first one
was not. It asked:

    "scratch" not in url

which is a substring test standing in for a database-identity test. Measured
against it, with three URLs all resolving to the PRODUCTION database:

    postgresql://nobody:nobody@host/asx_screener             REFUSED
    postgresql://scratch:nobody@host/asx_screener            ADMITTED
    postgresql://nobody:nobody@host/asx_screener?application_name=scratch
                                                             ADMITTED

Two of three reached psycopg2. `scratch` in a username or a connection
parameter satisfied it while the database was production. Only a dead port
stopped destructive setup from running against the real database.

The governed property is "the database this URL RESOLVES to is one I am
allowed to destroy", so the URL is parsed and matched against an exact
allowlist. These cases are now a test.

Run:  python tests/test_fixture_scratch_guard.py
"""

import importlib.util
import sys
import types
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
FIXTURE = BACKEND / "tests" / "fixtures" / "prove_stale_metric_rejection.py"


def _load_fixture():
    """Import the fixture without a database driver or a configured URL.

    psycopg2 and app.core.db are stubbed so this test is hermetic: it must be
    runnable anywhere, including a machine with no driver installed, or the
    guard protecting production would go unchecked exactly where someone is
    most likely to run the fixture by hand.
    """
    sys.modules.setdefault("psycopg2", types.ModuleType("psycopg2"))
    if "app.core.db" not in sys.modules:
        app = sys.modules.setdefault("app", types.ModuleType("app"))
        core = sys.modules.setdefault("app.core", types.ModuleType("app.core"))
        db = types.ModuleType("app.core.db")
        db.get_database_url_sync = lambda: ""
        sys.modules["app.core.db"] = db
        app.core = core
        core.db = db

    spec = importlib.util.spec_from_file_location("_fixture_under_test", FIXTURE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


FX = _load_fixture()

#: (url, database it resolves to, may the fixture mutate it)
CASES = (
    ("postgresql://nobody:nobody@h:5432/asx_screener",
     "asx_screener", False),
    # `scratch` in the USERNAME. Admitted by the substring guard.
    ("postgresql://scratch:nobody@h:5432/asx_screener",
     "asx_screener", False),
    # `scratch` in a CONNECTION PARAMETER. Admitted by the substring guard.
    ("postgresql://nobody:nobody@h:5432/asx_screener?application_name=scratch",
     "asx_screener", False),
    # `scratch` in the HOST.
    ("postgresql://nobody:nobody@scratch-db:5432/asx_screener",
     "asx_screener", False),
    # A database merely NAMED like scratch is still not the approved one.
    ("postgresql://nobody:nobody@h:5432/scratch_asx_screener",
     "scratch_asx_screener", False),
    ("postgresql://nobody:nobody@h:5432/asx_screener_scratch2",
     "asx_screener_scratch2", False),
    # The approved target, and only this.
    ("postgresql://nobody:nobody@h:5432/asx_screener_scratch",
     "asx_screener_scratch", True),
    ("postgresql://u:p@h:5432/asx_screener_scratch?sslmode=require",
     "asx_screener_scratch", True),
)


def test_the_resolved_database_is_parsed_not_matched():
    for url, expected, _ in CASES:
        got = FX._target_database(url)
        assert got == expected, (
            f"{url}\n  resolved to {got!r}, expected {expected!r}")


def test_only_approved_targets_are_admitted():
    for url, _, may_mutate in CASES:
        admitted = FX._target_database(url) in FX.APPROVED_TARGETS
        assert admitted == may_mutate, (
            f"{url}\n  {'ADMITTED' if admitted else 'refused'}, "
            f"expected {'admitted' if may_mutate else 'REFUSED'}")


def test_production_is_refused_however_scratch_appears_elsewhere():
    """The three cases that actually happened, named individually.

    A loop that silently stopped covering these would still pass the test
    above with an empty CASES tuple.
    """
    for url in (
        "postgresql://scratch:nobody@h:5432/asx_screener",
        "postgresql://nobody:nobody@h:5432/asx_screener?application_name=scratch",
        "postgresql://nobody:nobody@scratch-db:5432/asx_screener",
    ):
        assert "scratch" in url, "this case no longer tests what it claims to"
        assert FX._target_database(url) not in FX.APPROVED_TARGETS, (
            f"production admitted because 'scratch' appears elsewhere: {url}")


def test_the_allowlist_is_exact_names_not_a_pattern():
    """A pattern is how the first guard failed; this stops it coming back."""
    assert isinstance(FX.APPROVED_TARGETS, (set, frozenset)), (
        "APPROVED_TARGETS is not a set of exact names")
    for name in FX.APPROVED_TARGETS:
        assert "scratch" in name and name != "scratch", name
        for ch in "*?%[]":
            assert ch not in name, f"{name!r} looks like a pattern"


def test_the_check_can_actually_fail():
    """Mutation control: the old substring rule must fail this suite."""
    def old_guard(url: str) -> bool:
        return "scratch" in url
    leaked = [u for u, _, may in CASES if not may and old_guard(u)]
    assert leaked, (
        "the substring rule admits none of these, so the cases do not "
        "reproduce the defect and prove nothing")


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
