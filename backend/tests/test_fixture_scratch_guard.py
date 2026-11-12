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
import os
import sys
import types
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
# On sys.path so the REAL app.core / compute packages resolve. Without
# this the import below fails and the stub branch takes over, which
# shadows app.core with a bare module and breaks any fixture that
# imports a second thing from it.
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
FIXTURES_DIR = BACKEND / "tests" / "fixtures"

#: Every fixture that opens a connection in order to MUTATE data.
#:
#: Discovered, not listed. On 13 Nov 2026 this file named exactly one
#: path, and a second mutating fixture was added beside it --
#: prove_retired_columns_are_emptied.py -- which inherited no protection
#: at all while this suite kept reporting 5/5. A guard that watches one
#: member of a growing population is a guard that will be wrong later.
#:
#: The discriminator is `_connect`: a fixture that defines one is asking
#: for a writable session and must prove it refuses production.
def _mutating_fixtures() -> list[Path]:
    found = []
    for path in sorted(FIXTURES_DIR.glob("*.py")):
        if path.name.startswith("_"):
            continue
        text = path.read_text(encoding="utf-8")
        if "def _connect(" in text and "_target_database" in text:
            found.append(path)
    return found


#: The one name this guard exists to keep out, and the lookalikes that
#: have actually been tried against it.
PRODUCTION = "asx_screener"


def _load_fixture(fixture: Path):
    """Import the fixture without a database driver or a configured URL.

    psycopg2 and app.core.db are stubbed so this test is hermetic: it must be
    runnable anywhere, including a machine with no driver installed, or the
    guard protecting production would go unchecked exactly where someone is
    most likely to run the fixture by hand.
    """
    # psycopg2 AND its extras submodule. A fixture that drives the real
    # upsert imports execute_values, and a bare module stub is not a
    # package, so the import fails with a message about packaging rather
    # than about the guard -- and the guard would go unchecked on exactly
    # the machine where someone runs the fixture by hand.
    pg = sys.modules.setdefault("psycopg2", types.ModuleType("psycopg2"))
    pg.__path__ = getattr(pg, "__path__", [])      # a package, not a module
    for sub, attrs in (("extras", {"execute_values": lambda *a, **k: None,
                                   "Json": lambda v: v,
                                   "RealDictCursor": object}),
                       ("extensions", {"register_adapter": lambda *a: None,
                                       "AsIs": lambda v: v,
                                       "ISOLATION_LEVEL_AUTOCOMMIT": 0}),
                       ("sql", {"SQL": lambda v: v, "Identifier": lambda v: v}),
                       ("errors", {})):
        name = f"psycopg2.{sub}"
        if name not in sys.modules:
            mod = types.ModuleType(name)
            for key, value in attrs.items():
                setattr(mod, key, value)
            sys.modules[name] = mod
            setattr(pg, sub, mod)
    for attr, value in (("connect", lambda *a, **k: None),
                        ("Error", Exception),
                        ("OperationalError", Exception),
                        ("ProgrammingError", Exception)):
        if not hasattr(pg, attr):
            setattr(pg, attr, value)
    # app.core.db: prefer the REAL one. The original stub replaced `app`
    # and `app.core` with bare modules, which are not packages -- so any
    # fixture importing a second thing from app.core failed with a
    # packaging error instead of being checked. Stub only if the real
    # import is genuinely unavailable, and set __path__ so it stays a
    # package when we do.
    if "app.core.db" not in sys.modules:
        try:
            os.environ.setdefault(
                "DATABASE_URL_SYNC",
                "postgresql://unused:unused@127.0.0.1:1/unused")
            importlib.import_module("app.core.db")
        except Exception:                                  # noqa: BLE001
            app = sys.modules.setdefault("app", types.ModuleType("app"))
            app.__path__ = []                              # make it a package
            core = sys.modules.setdefault("app.core",
                                          types.ModuleType("app.core"))
            core.__path__ = []
            db = types.ModuleType("app.core.db")
            db.get_database_url_sync = lambda: ""
            sys.modules["app.core.db"] = db
            app.core = core
            core.db = db

    spec = importlib.util.spec_from_file_location(
        f"_fixture_under_test_{fixture.stem}", fixture)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


FIXTURES = _mutating_fixtures()
LOADED = {f.name: _load_fixture(f) for f in FIXTURES}

#: The original subject, kept under its old name so the cases
#: written for it keep applying to it specifically.
FX = LOADED["prove_stale_metric_rejection.py"]

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
    """A pattern is how the first guard failed; this stops it coming back.

    Scoped to THIS fixture, deliberately. It is a check on the shape of one
    allowlist, and shape is a proxy: the property that matters is that
    production is refused, which the suite below asserts over every
    fixture. A sibling fixture legitimately uses an anchored pattern,
    because the gate builds a per-run database whose name it cannot know in
    advance -- and an anchored pattern refuses production just as firmly as
    a literal does.
    """
    assert isinstance(FX.APPROVED_TARGETS, (set, frozenset)), (
        "APPROVED_TARGETS is not a set of exact names")
    for name in FX.APPROVED_TARGETS:
        assert "scratch" in name and name != "scratch", name
        for ch in "*?%[]":
            assert ch not in name, f"{name!r} looks like a pattern"


# ── Every mutating fixture, not just the first one ──────────────────────────

def test_the_population_is_not_empty_and_is_more_than_one():
    """The check that would have caught this guard going stale.

    It watched a single hardcoded path. A second mutating fixture was added
    beside it on 13 Nov 2026 and inherited nothing, while this suite kept
    reporting 5/5 -- a guard passing over a population it no longer covered.
    """
    assert FIXTURES, (
        f"no mutating fixtures discovered in {FIXTURES_DIR}. Either they "
        f"were all removed, or the discriminator in _mutating_fixtures no "
        f"longer matches them and every test below is checking nothing.")
    names = sorted(f.name for f in FIXTURES)
    assert "prove_stale_metric_rejection.py" in names, (
        f"the original subject is missing from {names}")
    assert len(names) >= 2, (
        f"only {names} discovered. If a mutating fixture was deleted that "
        f"is fine; confirm it, because this number falling silently is how "
        f"the coverage was lost the first time.")


def test_every_mutating_fixture_exposes_a_testable_predicate():
    """Otherwise the guard can only be checked by opening a connection."""
    missing = [name for name, mod in LOADED.items()
               if not callable(getattr(mod, "_may_mutate", None))]
    assert not missing, (
        f"{missing} do not expose _may_mutate(database) -> bool, so their "
        f"production check cannot be tested without connecting.")


def test_every_mutating_fixture_refuses_production():
    """The one property all of them must have, however they express it."""
    offenders = []
    for name, mod in LOADED.items():
        for database in (PRODUCTION, "asx_screener_prod", "postgres",
                         "template1", f"{PRODUCTION}_",
                         f"x{PRODUCTION}", ""):
            if mod._may_mutate(database):
                offenders.append(f"{name} would mutate {database!r}")
    assert not offenders, "; ".join(offenders)


def test_every_mutating_fixture_refuses_a_url_that_only_mentions_a_target():
    """The failure that actually happened, applied to every fixture.

    `scratch` in a username, in a connection parameter and in a hostname
    each got past the original substring guard while the URL resolved to
    production.
    """
    urls = (
        "postgresql://scratch:nobody@h:5432/asx_screener",
        "postgresql://nobody:nobody@h:5432/asx_screener?application_name=scratch",
        "postgresql://nobody:nobody@scratch-db:5432/asx_screener",
        "postgresql://asx_gate_1:nobody@h:5432/asx_screener",
        "postgresql://nobody:nobody@h:5432/asx_screener?x=asx_gate_1",
    )
    offenders = []
    for name, mod in LOADED.items():
        for url in urls:
            if mod._may_mutate(mod._target_database(url)):
                offenders.append(f"{name} admitted {url}")
    assert not offenders, "; ".join(offenders)


def test_each_fixture_admits_something_so_the_refusals_mean_something():
    """A predicate that refuses everything passes every test above."""
    admits = {
        "prove_stale_metric_rejection.py": "asx_screener_scratch",
        "prove_retired_columns_are_emptied.py": "asx_gate_3465907",
    }
    for name, mod in LOADED.items():
        target = admits.get(name)
        assert target is not None, (
            f"{name} is a mutating fixture with no known-good target listed "
            f"here. Add one, or its refusals prove nothing.")
        assert mod._may_mutate(target), (
            f"{name} refuses {target!r}, which it is supposed to accept. "
            f"A predicate that refuses everything satisfies every other "
            f"assertion in this file.")


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
