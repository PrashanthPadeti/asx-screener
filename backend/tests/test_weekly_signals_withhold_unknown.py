"""A weekly signal that cannot be computed is NULL, not false.

Four boolean signals on market.weekly_metrics were written as
`bool(g(series, False))`. Under 41 weekly bars there is no 40-week average
and no prior one, so `golden_cross` and `death_cross` were unknowable --
and were stored as a measured `false`. `above_sma10w` and `above_sma40w`
the same, under 10 and 40 bars.

market.daily_metrics writes NULL in the identical situation, deliberately,
so a short series is not reported as a bearish reading. The two tables
disagreed about what an uncomputable signal means, and the four columns are
nullable with no default -- the schema could always hold the answer.

The subtlety that made this more than a one-word fix: in pandas a
comparison against NaN yields **False**, not NaN. `sma_10 > sma_40` had
already collapsed unknown into false before the default was consulted.
Changing `False` to `None` there would have changed nothing at all, and the
test would have passed on a value that was still wrong.

So these tests run the real computation over a real short series and read
what it produces, rather than asserting on the shape of the source.
"""

import os
import sys
from datetime import date, timedelta
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

# weekly_compute resolves DATABASE_URL_SYNC at IMPORT time, so importing it
# to test a pure pandas computation needs the variable set. A placeholder is
# safe because nothing here opens a connection -- the functions under test
# take a DataFrame and return tuples.
#
# That the variable is needed at all to test arithmetic is the module-level
# configuration pattern that has bitten this project before. Noted, not
# fixed here: changing it belongs with the module, not with a test of its
# signals.
os.environ.setdefault("DATABASE_URL_SYNC",
                      "postgresql://unused:unused@127.0.0.1:1/unused")

try:
    import pandas as pd
except ImportError:                                   # pragma: no cover
    print("pandas is not installed; this suite cannot run")
    raise SystemExit(0)

from compute.engine import weekly_compute as wc       # noqa: E402

#: Column positions in the row tuple the builder emits.
GOLDEN, DEATH, ABOVE_10, ABOVE_40 = -6, -5, -4, -3

#: Bars needed before each signal is knowable.
NEEDS = {"golden_cross": 41, "death_cross": 41,
         "above_sma10w": 10, "above_sma40w": 40}


def _daily_frame(weeks: int, start: float = 10.0, step: float = 0.25):
    """A clean daily series long enough to resample into `weeks` weeks."""
    rows = []
    day = date(2024, 1, 1)
    price = start
    for i in range(weeks * 5):
        while day.weekday() >= 5:
            day += timedelta(days=1)
        rows.append({"time": pd.Timestamp(day), "open": price,
                     "high": price + 0.1, "low": price - 0.1,
                     "close": price, "volume": 100_000})
        price += step
        day += timedelta(days=1)
    return pd.DataFrame(rows).set_index("time")


def _rows(weeks: int):
    """Run the real builder. Named directly, not probed for.

    An earlier version tried several plausible names and gave up with an
    assertion if none matched. That is a population check doing its job --
    it refused to report 5/5 over nothing -- but probing for a function is
    how a suite keeps passing after the function is renamed and it quietly
    starts testing a different one. The name is `build_weekly_rows`.
    """
    return wc.build_weekly_rows("TEST", _daily_frame(weeks))


def test_the_builder_is_reachable_and_produces_rows():
    """Population check: an empty result passes every assertion below."""
    rows = _rows(60)
    assert rows, "the builder produced no rows for a 60-week series"
    assert len(rows[0]) > 30, (
        f"a row has {len(rows[0])} fields; the signal offsets this file "
        f"uses are positional and would be reading the wrong columns")


def test_a_short_series_withholds_rather_than_denies():
    """The exact case that produced a false: fewer bars than the window."""
    rows = _rows(6)
    assert rows, "no rows for a 6-week series"
    first = rows[0]
    for name, index in (("golden_cross", GOLDEN), ("death_cross", DEATH),
                        ("above_sma40w", ABOVE_40)):
        assert first[index] is None, (
            f"{name} is {first[index]!r} on a 6-week series. There are not "
            f"enough bars for a 40-week average, so the honest value is "
            f"None. False here is an assertion nobody measured.")


def test_a_long_series_still_produces_real_booleans():
    """Withholding must not swallow the signal where it IS computable."""
    rows = _rows(80)
    last = rows[-1]
    for name, index in (("golden_cross", GOLDEN), ("death_cross", DEATH),
                        ("above_sma10w", ABOVE_10), ("above_sma40w", ABOVE_40)):
        assert isinstance(last[index], bool), (
            f"{name} is {last[index]!r} at week 80, where every input "
            f"exists. Masking has gone too far and is withholding a signal "
            f"that can be computed.")


def test_each_signal_becomes_known_only_once_its_window_is_full():
    """The boundary, per signal, rather than one example.

    A test over a single short series passes if the mask is too wide. This
    walks the series and finds where each signal first becomes non-None.
    """
    rows = _rows(80)
    first_known = {}
    for name, index in (("golden_cross", GOLDEN), ("death_cross", DEATH),
                        ("above_sma10w", ABOVE_10), ("above_sma40w", ABOVE_40)):
        for position, row in enumerate(rows, start=1):
            if row[index] is not None:
                first_known[name] = position
                break

    missing = sorted(set(NEEDS) - set(first_known))
    assert not missing, f"{missing} were never computable over 80 weeks"

    wrong = {name: (position, NEEDS[name])
             for name, position in first_known.items()
             if position < NEEDS[name]}
    assert not wrong, (
        f"these signals report a value before their window is full "
        f"(got, needed): {wrong}. A value computed from a partial window is "
        f"the same defect as a false computed from no window.")


def test_no_signal_is_ever_the_python_false_from_a_none():
    """`bool(None)` is False, and that is how a fix like this gets undone.

    Routing a withheld signal through bool() one line later restores the
    conflation silently. Asserted over every row of a short series, where
    every signal should be None.
    """
    for row in _rows(6):
        for name, index in (("golden_cross", GOLDEN), ("death_cross", DEATH),
                            ("above_sma40w", ABOVE_40)):
            assert row[index] is not False, (
                f"{name} is the Python False on a series too short to "
                f"compute it")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed, failed = 0, []
    for fn in tests:
        try:
            fn()
            passed += 1
        except AssertionError as exc:
            failed.append((fn.__name__, str(exc)))
        except Exception as exc:  # noqa: BLE001
            failed.append((fn.__name__, f"{type(exc).__name__}: {exc}"))
    for name, msg in failed:
        print(f"FAIL {name}\n     {msg}\n")
    print(f"{passed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
