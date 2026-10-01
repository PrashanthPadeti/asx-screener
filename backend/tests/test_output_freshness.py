"""
Every deferrable job is either observable or named as unobservable
===================================================================
A job that takes the auxiliary lease and finds a canonical run in flight
returns without writing. Correct -- and indistinguishable from a quiet week,
because the process exits 0 either way and nothing reads the log line.

So the registry in `scripts/assert_output_freshness.py` must cover every such
job. The coverage is DERIVED from the call sites rather than listed here,
because a list of job names is exactly the thing that goes stale when someone
adds the fifth job.

Two ways to be covered, and the second matters as much as the first:

    ANCHORS      its own output carries a timestamp; freshness is assertable
    UNOBSERVABLE it writes only into screener.universe, which the canonical
                 run rebuilds, so it has no timestamp of its own -- named,
                 with the reason, rather than omitted

An unchecked job missing from a report reads as a healthy one. That is the
failure this file exists to prevent, one level up from the one the script
prevents.

Run under pytest, or standalone:
    cd backend && ../asx-venv/bin/python tests/test_output_freshness.py
"""

import ast
import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

SCRIPT = BACKEND / "scripts/assert_output_freshness.py"


def _deferrable_jobs() -> set[str]:
    """Modules that CALL auxiliary_lease, not ones that merely mention it.

    Detected from the call site. Matching the bare string catches
    canonical_lease, which defines it, and launch_authority, which names it in
    a message -- neither is a job and neither has output to be fresh.
    """
    jobs = set()
    for path in (BACKEND / "compute/engine").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and getattr(node.func, "id", "") == "auxiliary_lease"):
                jobs.add(path.stem)
                break
    return jobs


def _covered() -> tuple[set[str], set[str]]:
    src = SCRIPT.read_text(encoding="utf-8")
    # \w, not [a-z_]: the first version of this could not match the 5 in
    # top5_strategy and reported a covered job as missing.
    anchors = set(re.findall(r'Anchor\("(\w+)"', src))
    tree = ast.parse(src)
    unobservable: set[str] = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Assign)
                and any(getattr(t, "id", "") == "UNOBSERVABLE"
                        for t in node.targets)
                and isinstance(node.value, ast.Dict)):
            unobservable = {k.value for k in node.value.keys
                            if isinstance(k, ast.Constant)}
    return anchors, unobservable


def test_every_deferrable_job_is_covered():
    anchors, unobservable = _covered()
    missing = _deferrable_jobs() - (anchors | unobservable)
    assert not missing, (
        f"these jobs defer silently and nothing proves they ever ran again: "
        f"{sorted(missing)}. Give each an anchor, or name it in UNOBSERVABLE "
        f"with the reason its output carries no timestamp.")


def test_the_detection_finds_the_real_jobs():
    """The mutation control. If the call-site detection broke and returned an
    empty set, the test above would pass while covering nothing."""
    jobs = _deferrable_jobs()
    assert {"short_positions", "pros_cons", "asx_indices", "top5_strategy"} <= jobs
    # And it must NOT pick up the module that defines the helper.
    assert "canonical_lease" not in jobs
    assert "launch_authority" not in jobs


def test_unobservable_entries_carry_a_reason():
    """"Cannot be checked" is only acceptable with the reason attached.
    Without it the entry is a way to silence a job rather than to describe
    one."""
    _, unobservable = _covered()
    src = SCRIPT.read_text(encoding="utf-8")
    for job in unobservable:
        m = re.search(rf'"{re.escape(job)}":\s*\n?\s*"([^"]+)"', src)
        assert m and len(m.group(1)) > 40, (
            f"{job} is listed as unobservable with no substantive reason")


def test_a_threshold_is_not_tighter_than_the_cadence():
    """A limit below the job's own period would fire on exactly the behaviour
    the lease exists to produce -- one deferral -- and train people to ignore
    it. Both anchors allow at least two cycles."""
    src = SCRIPT.read_text(encoding="utf-8")
    for job, hours in re.findall(r'Anchor\("(\w+)",[^)]*?(\d+ \* \d+),', src):
        a, b = (int(x) for x in hours.split("*"))
        assert a * b >= 24 * 7, (
            f"{job}: {a * b}h is tighter than a weekly cadence plus one "
            f"tolerated deferral")


def test_the_script_fails_rather_than_reports_by_default():
    """--report exists for a dashboard. The default must exit non-zero, or
    scheduling it proves nothing."""
    src = SCRIPT.read_text(encoding="utf-8")
    assert "return 0 if args.report else 1" in src


def test_every_anchor_column_is_one_the_job_actually_writes():
    """An anchor is a guess until it is checked against the writer.

    The first version anchored top5_strategy on `created_at`; the job writes
    `computed_at`. The script reported BROKEN rather than raising, which is
    why that was a measurement instead of a 22:00 Sunday traceback -- but a
    freshness check whose column does not exist proves nothing either.

    Derived from the writing module's own SQL, so the two cannot drift.
    """
    anchors, _ = _covered()
    src = SCRIPT.read_text(encoding="utf-8")
    for job in anchors:
        column = re.search(
            rf'Anchor\("{re.escape(job)}",\s*"[^"]+",\s*"(\w+)"', src)
        assert column, f"cannot read the anchor column for {job}"
        module = BACKEND / "compute/engine" / f"{job}.py"
        assert module.exists(), f"{job} has no module to check against"
        assert column.group(1) in module.read_text(encoding="utf-8"), (
            f"{job} is anchored on {column.group(1)}, which does not appear "
            f"in {module.name} -- the job does not write that column")


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
