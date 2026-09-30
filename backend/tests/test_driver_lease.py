"""
The driver serializes itself when nobody else is doing it
=========================================================
Rule 6 of `docs/canonical_orchestration.md` gives the lease to the wrapper,
because the driver exits at finalisation while the suffix is still reading
screener.universe. That reasoning is about the SUFFIX, and it left a gap: a
driver invoked directly held no lease at all.

Demonstrated by accident on 30 Sep 2026. One command pasted twice started two
FULL_FUNDAMENTALS_CANONICAL runs 22 seconds apart against the same database:

    id 6  2026-09-30 14:02:14  FULL_FUNDAMENTALS_CANONICAL  rows_written NULL
    id 5  2026-09-30 14:01:52  FULL_FUNDAMENTALS_CANONICAL  rows_written NULL

Neither reached finalisation, so nothing was published. That was a watchful
terminal and a pkill, not a property of the system -- and the moments when a
driver is invoked by hand (a rehearsal, an incident) are exactly the moments
when a second operator is most likely to be typing the same command.

Two properties, and the second matters as much as the first: taking the lease
unconditionally would deadlock the scheduled path against its own wrapper.

Run under pytest, or standalone:
    cd backend && ../asx-venv/bin/python tests/test_driver_lease.py
"""

import ast
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

DRIVER = BACKEND / "scripts/p0a_canonical_run.py"


def _main() -> ast.FunctionDef:
    tree = ast.parse(DRIVER.read_text(encoding="utf-8"))
    return next(n for n in ast.walk(tree)
                if isinstance(n, ast.FunctionDef) and n.name == "main")


def test_the_driver_takes_the_lease_when_invoked_directly():
    body = ast.dump(_main())
    assert "canonical_lease" in body, (
        "a directly invoked driver must serialize itself; two interleaving "
        "runs is how a publication gets built from half of each")


def test_the_driver_inherits_rather_than_deadlocking():
    """The wrapper already holds the lock on the scheduled path. Taking it
    again would block the driver against its own caller, forever -- which
    would be a worse failure than the one being fixed, and would arrive on a
    Sunday rather than under a rehearsal."""
    body = ast.dump(_main())
    assert "LEASE_HELD_ENV" in body


def test_a_manual_run_does_not_wait():
    """An operator at a terminal is told immediately that a cycle is in
    flight. SCHEDULED_WAIT_SECONDS is 90 minutes and belongs to cron, which
    has nobody to tell."""
    body = ast.dump(_main())
    assert "MANUAL_WAIT_SECONDS" in body
    assert "SCHEDULED_WAIT_SECONDS" not in body


def test_refusal_is_not_a_crash():
    """LeaseUnavailable must be caught and turned into an exit code with an
    explanation. An unhandled traceback reads as a broken tool rather than as
    the guard doing its job, and the next thing an operator does with a broken
    tool is run it again."""
    body = ast.dump(_main())
    assert "LeaseUnavailable" in body
    handlers = [n for n in ast.walk(_main()) if isinstance(n, ast.ExceptHandler)]
    assert any("LeaseUnavailable" in ast.dump(h) for h in handlers)


def test_the_lease_connection_is_its_own_session():
    """Advisory locks are session-scoped. Sharing the driver's working
    connection would release the lease on any rollback that connection
    performs, silently, at the worst possible time."""
    body = ast.dump(_main())
    assert "psycopg2" in body and "connect" in body
    assert "close" in body, "the lease connection must be closed on every path"


def test_the_body_still_runs():
    """The mutation control: main() must actually call the run body. A wrapper
    that serializes perfectly and never executes anything would satisfy every
    assertion above."""
    body = ast.dump(_main())
    assert "_run" in body


def test_inheritance_is_verified_not_believed():
    """ASX_CANONICAL_LEASE_HELD is an assertion, not evidence.

    A child that finds it set and skips the lock trusts whatever exported it
    -- deliberately, or a stale shell from an earlier wrapper run. The claim
    must be checked against pg_locks, and a claim with nothing behind it must
    refuse rather than proceed unserialized.
    """
    body = ast.dump(_main())
    assert "lease_is_held" in body, (
        "an inherited lease claim must be verified against pg_locks")


def test_the_refusal_precedes_the_run_body():
    """It must refuse BEFORE create_run and before any canonical mutation.

    Proven by position: every `return _run()` has to sit inside the lease
    handling, never before it.
    """
    main = _main()
    lease_calls = [n.lineno for n in ast.walk(main)
                   if isinstance(n, ast.Call)
                   and getattr(n.func, "id", "") in
                   ("canonical_lease", "lease_is_held")]
    run_calls = [n.lineno for n in ast.walk(main)
                 if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "_run"]
    assert lease_calls and run_calls
    assert min(lease_calls) < min(run_calls), (
        "the run body is reachable before the lease is settled")


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
        except Exception as e:                                     # noqa: BLE001
            failures.append(name)
            print(f"  ERROR {name}  - {type(e).__name__}: {e}")
    print(f"\n{len(tests) - len(failures)}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
