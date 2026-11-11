"""A suite that RAN and failed is a finding, not an environment fault.

The full-suite gate sorts every suite into passed, failed or INCONCLUSIVE.
Only `failed` blocks a release. INCONCLUSIVE exists for a good reason -- a
suite that could not reach the database or import its dependencies has
proved nothing, and counting it as a pass or as a pre-existing failure would
be a lie in either direction.

The classification was done by scanning the suite's OUTPUT for markers like
`ModuleNotFoundError`, `Connection refused` and `psycopg`. That scan cannot
tell "this suite could not run" from "this suite ran, failed, and mentioned
a driver by name in its failure message".

On 10 Nov 2026 it did not. `test_sql_percent_literals.py`, the guard written
in v11.2.65 for an undoubled percent sign in a SQL literal, correctly failed
on exactly that defect in UPSERT_SQL. It named the file, the line and the
constant, and explained that

    psycopg2 will consume a bind parameter at each one

`psycopg` is in ENV_MARKERS. The gate filed a precise, correct, blocking
finding under INCONCLUSIVE, which blocks nothing. v11.2.78 shipped a
statement that could not be executed, and the first canonical run after it
died before writing a row -- with the diagnosis already sitting in the gate
log of the release that shipped it.

The evidence needed to tell the two apart was already being collected. A
suite that prints its completion marker -- `N/M passed`, or `ALL ... CHECKS
PASSED` -- reached the end of its runner. It ran. Whatever it printed on the
way, its failures are findings.

This test reads the real regexes out of the real script and applies them
with the real `grep`, so it checks the gate rather than a description of the
gate. The load-bearing case is the first one: the actual output that was
misclassified.
"""

import re
import subprocess
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
GATE = BACKEND / "scripts" / "gate_full_suite.sh"

#: The real failure output of test_sql_percent_literals.py on the broken
#: tree, 10 Nov 2026. Contains both "psycopg2" and a completion marker.
THE_MISCLASSIFIED_OUTPUT = """\
  FAIL  test_no_sql_literal_contains_an_undoubled_percent_sign  - 1 SQL \
literal line(s) contain a percent sign that is neither doubled nor part of \
a placeholder. psycopg2 will consume a bind parameter at each one -- \
raising IndexError if it runs off the end of the parameter list, and \
binding the wrong values silently if it does not:
    scripts/eodhd/v2/build_screener_universe.py:81 [UPSERT_SQL]
        -- 1,674 (91.1%) were wrong by more than 0.01, median error 0.10 on a
  PASS  test_the_collector_still_sees_the_projects_sql
  FAIL  test_the_statement_that_failed_is_clean_now  - UPSERT_SQL has an \
undoubled percent sign again.

2/4 passed
"""

#: A suite that genuinely could not run: no completion marker at all.
A_REAL_ENVIRONMENT_FAULT = """\
Traceback (most recent call last):
  File "tests/test_snapshot_projection.py", line 9, in <module>
    import fastapi
ModuleNotFoundError: No module named 'fastapi'
"""

#: A suite that ran, with some tests failing on a missing import. Under the
#: repaired rule this is a failure, reported per test: those tests fail at
#: both commits, so attribution files them PRE-EXISTING and nothing is
#: wrongly blocked -- while a test that newly fails still blocks.
A_SUITE_THAT_RAN_WITH_SOME_IMPORT_ERRORS = """\
  PASS  test_one
  ERROR test_two: ModuleNotFoundError: No module named 'sqlalchemy'

8/9 passed
"""


def _regex(name: str) -> str:
    """Pull a regex out of the gate script rather than restating it."""
    text = GATE.read_text(encoding="utf-8")
    m = re.search(rf"^{name}='([^']*)'", text, re.M)
    assert m, (f"{name} is no longer a single-quoted assignment in "
               f"{GATE.name}. This test reads the gate's own regexes; if "
               f"they moved, follow them rather than restating them here.")
    return m.group(1)


def _matches(pattern: str, text: str) -> bool:
    """Real grep -E, so dialect differences cannot make this test lie."""
    with tempfile.NamedTemporaryFile("w", suffix=".out", delete=False,
                                     encoding="utf-8") as fh:
        fh.write(text)
        path = fh.name
    try:
        r = subprocess.run(["grep", "-qE", pattern, path],
                           capture_output=True)
        return r.returncode == 0
    finally:
        Path(path).unlink(missing_ok=True)


def _verdict(text: str) -> str:
    """The gate's classification of a FAILING suite, by its own regexes."""
    env = _matches(_regex("ENV_MARKERS"), text)
    ran = _matches(_regex("RAN_MARKER"), text)
    return "INCONCLUSIVE" if (env and not ran) else "FAILED"


def test_the_finding_that_was_thrown_away_now_blocks():
    assert _verdict(THE_MISCLASSIFIED_OUTPUT) == "FAILED", (
        "the v11.2.65 percent-sign guard's real failure output is still "
        "being filed as an environment fault. It ran -- it printed '2/4 "
        "passed' -- and it found the defect that broke the next production "
        "run. INCONCLUSIVE blocks nothing.")


def test_a_suite_that_could_not_run_is_still_inconclusive():
    """The repair must not destroy the category it narrows."""
    assert _verdict(A_REAL_ENVIRONMENT_FAULT) == "INCONCLUSIVE", (
        "a suite that never reached its first test is now being reported as "
        "a failure. That is the opposite error, and it makes every "
        "environment fault look like a broken feature.")


def test_a_suite_that_ran_is_a_finding_even_with_import_errors():
    assert _verdict(A_SUITE_THAT_RAN_WITH_SOME_IMPORT_ERRORS) == "FAILED", (
        "a suite that reached the end of its runner is reporting results. "
        "Its per-test failures are attributable; discarding the whole file "
        "loses the tests that passed and the tests that newly broke.")


def test_the_env_scan_is_actually_conditioned_on_the_marker():
    """Structural: the two conditions must be combined, not just present.

    Defining RAN_MARKER and never ANDing it into the environment branch
    would leave every test above passing -- they read the regexes, not the
    control flow -- while the gate behaved exactly as it did before.
    """
    text = GATE.read_text(encoding="utf-8")
    pattern = (r'grep\s+-qE\s+"\$ENV_MARKERS"\s+"\$out"\s*&&\s*'
               r'!\s*grep\s+-qE\s+"\$RAN_MARKER"\s+"\$out"')
    assert re.search(pattern, text), (
        "the environment-marker branch does not require the ABSENCE of a "
        "completion marker. Without that conjunction a suite that ran and "
        "failed is still filed as an environment fault, whatever this "
        "file's other tests appear to show.")


def test_psycopg_is_still_in_the_env_markers():
    """The repair is the conjunction, not deleting the marker.

    Dropping `psycopg` would also have fixed the symptom, and would have
    blinded the gate to a suite that genuinely cannot reach the database --
    which is most of them. The marker must stay.
    """
    assert "psycopg" in _regex("ENV_MARKERS"), (
        "`psycopg` was removed from ENV_MARKERS. That silences the symptom "
        "by giving up the category: a suite that truly cannot connect would "
        "then be reported as a broken feature.")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed, failed = 0, []
    for fn in tests:
        try:
            fn()
            passed += 1
            print(f"  PASS  {fn.__name__}")
        except AssertionError as exc:
            failed.append((fn.__name__, str(exc)))
            print(f"  FAIL  {fn.__name__}")
        except Exception as exc:                         # noqa: BLE001
            failed.append((fn.__name__, f"{type(exc).__name__}: {exc}"))
            print(f"  ERROR {fn.__name__}")
    print()
    for name, msg in failed:
        print(f"FAIL {name}\n     {msg}\n")
    print(f"{passed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
