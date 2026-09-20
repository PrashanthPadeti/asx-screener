"""
Last Monday is a date subtraction, not a day-number substitution
================================================================
`weekly_pipeline.py` computed the start of the just-completed week as

    today.replace(day=today.day - today.weekday())

replace() cannot cross a month boundary, so this raises ValueError whenever
last Monday fell in the previous month — 11 of 2026's 52 Sundays, roughly one
a month. It worked perfectly the other three weeks, which is why it ran
undetected from at least June: the 240-byte rotated logs of 12 Jul and 9 Aug
are tracebacks, and market.yearly_metrics read 30 Aug for three weeks because
the 6 Sep run died here before reaching yearly_compute.

The failure was invisible for a second reason worth keeping in mind: a
monthly crash in a weekly job looks like noise, and the surviving runs keep
the data fresh enough that nobody goes looking.

Run under pytest, or standalone:
    cd /opt/asx-screener/backend && ../asx-venv/bin/python tests/test_weekly_pipeline_dates.py
"""

import ast
import re
import sys
from datetime import date, timedelta
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
PIPELINE = BACKEND / "scripts" / "eodhd" / "v2" / "jobs" / "weekly_pipeline.py"


def _source():
    src = PIPELINE.read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        doc = ast.get_docstring(node, clean=False) if isinstance(
            node, (ast.Module, ast.FunctionDef, ast.ClassDef)) else None
        if doc:
            src = src.replace(doc, "")
    return "\n".join(ln for ln in src.splitlines()
                     if not ln.strip().startswith("#"))


def test_last_monday_is_computed_by_subtraction():
    """replace(day=...) is the bug; timedelta is the fix."""
    code = _source()
    assert "today - timedelta(days=days_since_monday)" in code, (
        "last_monday is not computed by date subtraction")
    # Only an ARITHMETIC day number. `today.replace(day=1)` appears elsewhere
    # in this file and is perfectly safe — day 1 exists in every month. The
    # first draft of this guard banned replace(day=...) outright and failed on
    # that correct line, which is the safe direction to be wrong in but still
    # wrong.
    arithmetic = re.search(r"replace\(\s*day\s*=[^)]*[-+]", code)
    assert not arithmetic, (
        f"a day number is being computed by arithmetic inside replace(): "
        f"{arithmetic.group(0)!r}. It cannot cross a month boundary and will "
        f"raise ValueError roughly once a month.")
    assert "from datetime import date, timedelta" in code


def test_every_day_of_four_years_yields_a_monday_on_or_before_today():
    """The property, exercised rather than argued.

    Every day from 2024 to 2027 — not just Sundays — because the job can be
    run by hand on any day, and that is exactly how it will be run to recover
    the three weeks it has missed.
    """
    d, end = date(2024, 1, 1), date(2027, 12, 31)
    while d <= end:
        last_monday = d - timedelta(days=d.weekday())
        assert last_monday.weekday() == 0, f"{d}: {last_monday} is not a Monday"
        assert last_monday <= d, f"{d}: {last_monday} is in the future"
        assert (d - last_monday).days < 7, f"{d}: {last_monday} is over a week back"
        d += timedelta(days=1)


def test_the_old_expression_really_did_fail_and_this_is_not_hindsight():
    """Pin the dates, so the regression has a witness rather than a story.

    If someone later reintroduces replace(day=...) reasoning that it "looks
    fine", these are the days it is not fine on.
    """
    crashes = []
    d = date(2026, 1, 1)
    while d.year == 2026:
        if d.weekday() == 6:                       # the job runs Sundays
            try:
                d.replace(day=d.day - d.weekday())
            except ValueError:
                crashes.append(d)
        d += timedelta(days=1)

    assert len(crashes) == 11, f"expected 11 crashing Sundays, got {len(crashes)}"
    assert date(2026, 9, 6) in crashes, (
        "6 Sep 2026 is the run that actually died and left yearly_metrics "
        "stale for three weeks")
    # And the fix handles every one of them.
    for c in crashes:
        assert (c - timedelta(days=c.weekday())).weekday() == 0


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
    print(f"\n{len(tests) - len(failures)}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
