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


# ── The other half of the contract ───────────────────────────────────────────
#
# Every test above checks that the DRIVER reads the inheritance flag. None of
# them checked that the WRAPPER sets it before spawning the driver, and that
# is where it broke in production on 30 Sep 2026:
#
#     22:33:14  canonical execution lease acquired by weekly_pipeline
#     22:33:14  REFUSING: canonical execution lease held by an unidentified
#               session; canonical_driver waited 0s and is refusing
#     22:33:14  canonical driver exited 2 — no publication this cycle
#
# The wrapper set the flag AFTER subprocess.run, because it was written when
# the flag's only audience was the suffix. subprocess inherits os.environ at
# spawn time, so a flag set afterwards is a flag the child never sees. The
# driver refused against its own parent and nothing published.
#
# A contract with two parties needs a test that spans both of them.

WRAPPERS = ("scripts/eodhd/v2/jobs/weekly_pipeline.py",
            "scripts/eodhd/v2/jobs/daily_pipeline.py")


def _canonical_execution(path: Path) -> ast.FunctionDef:
    tree = ast.parse((BACKEND / path).read_text(encoding="utf-8"))
    return next(n for n in ast.walk(tree)
                if isinstance(n, ast.FunctionDef)
                and n.name == "canonical_execution")


def test_each_wrapper_hands_the_lease_over_before_spawning_the_driver():
    for wrapper in WRAPPERS:
        fn = _canonical_execution(wrapper)

        sets = [n.lineno for n in ast.walk(fn)
                if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Subscript)
                        and getattr(t.value, "attr", "") == "environ"
                        for t in n.targets)]
        spawns = [n.lineno for n in ast.walk(fn)
                  if isinstance(n, ast.Call)
                  and getattr(n.func, "attr", "") == "run"
                  and "p0a_canonical_run" in ast.dump(n)]

        assert sets, f"{wrapper}: the wrapper never sets the inheritance flag"
        assert spawns, f"{wrapper}: no canonical driver spawn found"
        assert min(sets) < min(spawns), (
            f"{wrapper}: the inheritance flag is set at line {min(sets)}, "
            f"after the driver is spawned at line {min(spawns)}. subprocess "
            f"inherits os.environ at spawn time, so the driver will refuse "
            f"against its own parent and nothing will publish.")


def test_each_wrapper_clears_the_flag_on_every_path():
    """It must not leak into whatever the operator runs next in that shell."""
    for wrapper in WRAPPERS:
        fn = _canonical_execution(wrapper)
        body = ast.dump(fn)
        assert "pop" in body, f"{wrapper}: the flag is never cleared"
        assert any(isinstance(n, ast.Try) and n.finalbody
                   for n in ast.walk(fn)), (
            f"{wrapper}: the flag must be cleared in a finally, or a driver "
            f"failure leaves it set")


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
