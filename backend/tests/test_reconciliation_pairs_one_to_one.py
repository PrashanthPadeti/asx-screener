#!/usr/bin/env python
"""
Reconciliation pairs one declared entry with one observed entry
===============================================================
`launch_authority.reconciliation` exists to catch production running what
code review cannot see. It compares declared against installed cron
entries and reports UNDECLARED, NOT INSTALLED, CADENCE DRIFT and
ENABLED-STATE DRIFT.

It pairs them like this:

    want_targets = {s.target for s in desired()}       # a SET
    have_targets = {s.target for s in observed(...)}   # a SET
    ...
    w = next(s for s in desired()         if s.target == target)
    h = next(s for s in observed(crontab) if s.target == target)

`next()` takes the FIRST match. So if one script is scheduled twice --
ordinary in a crontab, and the obvious way to run a pipeline at two times
-- only the first pairing is ever compared. A second installed schedule
for an already-declared target raises:

    no UNDECLARED     the target IS declared
    no CADENCE DRIFT  the first entry matched

and is therefore invisible to the one control whose job is to notice it.

Found 24 Oct 2026 while chasing an F841 (`want` and `have`, built keyed by
identity and never used -- leftovers). The unused variables were harmless;
reading why they were there exposed this.

The fix reports the ambiguity rather than resolving it. Pairing
many-to-many is a design decision; noticing that the current pairing
cannot be trusted is not, and a control that silently checks half its
population is worse than one that says it cannot check.

Run:  python tests/test_reconciliation_pairs_one_to_one.py
"""

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from compute.engine import launch_authority as la            # noqa: E402

#: A real declared target, so the entry is canonical-relevant and the
#: reconciliation actually considers it.
TARGET = "backend/scripts/eodhd/v2/jobs/daily_pipeline.py"

PREFIX = ("cd /opt/asx-screener && set -a && . /opt/asx-screener/backend/"
          ".env && set +a && /opt/asx-screener/asx-venv/bin/python")


def _line(cadence: str) -> str:
    return f"{cadence}  {PREFIX} {TARGET}"


def test_the_target_used_here_is_really_declared():
    """Premise check. If the generator stops declaring this script, the
    cases below would be exercising a target reconciliation ignores, and
    would pass while testing nothing."""
    assert TARGET in {s.target for s in la.desired()}, (
        f"{TARGET} is no longer declared; pick another target or this "
        f"suite proves nothing")


def test_a_target_scheduled_twice_is_reported_as_ambiguous():
    """The blind spot, made visible."""
    crontab = "\n".join([_line("30 8 * * 1-5"), _line("30 14 * * 1-5")])
    found = la.reconciliation(crontab)

    ambiguous = [f for f in found if f.startswith("AMBIGUOUS")]
    assert ambiguous, (
        "a target scheduled twice was not reported. Only the first entry is "
        "compared, so the second schedule is unchecked:\n  "
        + "\n  ".join(found))
    assert TARGET in ambiguous[0]
    assert "2 times" in ambiguous[0]


def test_a_single_schedule_is_not_reported_as_ambiguous():
    """False-positive control: the ordinary case must stay quiet."""
    found = la.reconciliation(_line("30 8 * * 1-5"))
    assert not [f for f in found if f.startswith("AMBIGUOUS")], found


def test_the_duplicate_is_invisible_to_the_other_checks():
    """Why AMBIGUOUS has to exist as its own finding.

    Asserted directly: the second schedule produces no UNDECLARED and no
    CADENCE DRIFT, because the target IS declared and the FIRST entry
    matches. Without the ambiguity report, nothing at all would be said
    about it.
    """
    crontab = "\n".join([_line("30 8 * * 1-5"),       # matches the generator
                         _line("30 14 * * 1-5")])     # unchecked today
    found = la.reconciliation(crontab)

    about_target = [f for f in found
                    if TARGET in f and not f.startswith("AMBIGUOUS")]
    drift = [f for f in about_target
             if f.startswith(("CADENCE DRIFT", "UNDECLARED"))]
    assert not drift, (
        "the second schedule is now caught by another check; if pairing was "
        "made many-to-many, this test and the ambiguity report should be "
        "revisited:\n  " + "\n  ".join(drift))


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
