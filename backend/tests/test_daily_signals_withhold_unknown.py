"""A daily signal that cannot be computed is NULL, not false.

Finding 15, and a correction to finding 10.

Finding 10 closed partly on the claim that `market.daily_metrics` "already
writes NULL for an uncomputable signal". It does not, and the claim was
asserted without being checked. `compute_indicators` wrote every boolean as
a bare pandas comparison:

    df["above_sma200"] = c > df["sma_200"]
    df["golden_cross"] = (df["sma_50"] > df["sma_200"]) & (...)

A comparison against NaN yields **False**, and `_v()` converts
`np.bool_(False)` to `False` rather than None. So a stock with 100 bars --
enough for an RSI, not enough for a 200-day average -- was published with
`above_sma200 = false` and both crosses `false`. Measured claims about an
average that does not exist.

WHY THIS ONE REACHES THE CUSTOMER AND FINDING 10'S DID NOT
----------------------------------------------------------
`market.weekly_metrics` is read by nothing: the universe joins it and no
column selects from it. `market.daily_metrics` is read by four columns of
`screener.universe` directly -- `above_sma50`, `above_sma200`,
`golden_cross`, `death_cross` -- so these falses are served, filtered on
and sorted by.

The warm-up filter in the row builder (`df[df["rsi_14"].notna()]`, about 15
bars) removes the most extreme cases and not the ones that matter. It is
exactly the stocks with some history but not much that get a confident
negative.

WHAT THESE TESTS DO
-------------------
Run the real `compute_indicators` over real short series and read what it
produces, rather than asserting on the shape of the source. A test that
grepped for `.where(` would pass on a mask applied to the wrong column.
"""

import os
import sys
from datetime import date, timedelta
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

# technical_compute resolves DATABASE_URL_SYNC at import time, so importing
# it to test a pure pandas computation needs the variable set. A placeholder
# is safe: nothing here opens a connection, and compute_indicators takes a
# DataFrame and returns a DataFrame.
os.environ.setdefault("DATABASE_URL_SYNC",
                      "postgresql://unused:unused@127.0.0.1:1/unused")

try:
    import numpy as np
    import pandas as pd
except ImportError:                                        # pragma: no cover
    print("pandas is not installed; this suite cannot run")
    raise SystemExit(0)

from compute.engine import technical_compute as tc         # noqa: E402

#: signal -> the shortest series on which it can possibly be known.
#:
#: The averages need their window. The 52-week flags need a series spanning
#: 365 CALENDAR days, which is the rolling_extreme rule, not a row count --
#: so they are expressed in trading days at roughly 252 a year and checked
#: with slack rather than pinned to an exact bar.
NEEDS_BARS = {
    "above_sma20": 20,
    "above_sma50": 50,
    "above_sma100": 100,
    "above_sma200": 200,
    "golden_cross": 200,
    "death_cross": 200,
    "obv_rising": 20,
    "above_vwap": 20,
}

#: The four the universe reads straight from this table.
SERVED = ("above_sma50", "above_sma200", "golden_cross", "death_cross")

#: Needs a full 52 weeks of calendar coverage, not a bar count.
NEEDS_52W = ("new_52w_high", "new_52w_low", "volume_breakout")

ALL_SIGNALS = tuple(NEEDS_BARS) + NEEDS_52W


def _frame(bars: int, start: float = 10.0, step: float = 0.05):
    """A clean daily OHLCV series of `bars` trading days."""
    rows = []
    day = date(2024, 1, 1)
    price = start
    for _ in range(bars):
        while day.weekday() >= 5:
            day += timedelta(days=1)
        rows.append({"date": pd.Timestamp(day), "open": price,
                     "high": price + 0.1, "low": price - 0.1,
                     "close": price, "volume": 100_000})
        price += step
        day += timedelta(days=1)
    return pd.DataFrame(rows)


def _last(bars: int, column: str):
    out = tc.compute_indicators(_frame(bars), shares=1_000_000)
    assert column in out.columns, f"{column} was not produced at all"
    return out[column].iloc[-1]


def _is_unknown(value) -> bool:
    return value is None or (isinstance(value, float) and np.isnan(value))


# ── Population ──────────────────────────────────────────────────────────────

def test_the_computation_runs_and_produces_every_signal():
    """An absent column passes every assertion that only checks for None."""
    out = tc.compute_indicators(_frame(400), shares=1_000_000)
    missing = [s for s in ALL_SIGNALS if s not in out.columns]
    assert not missing, (
        f"{missing} are not produced by compute_indicators. The tests below "
        f"would report success over columns that do not exist.")
    assert len(out) == 400, f"the frame came back with {len(out)} rows"


# ── The property ────────────────────────────────────────────────────────────

def test_a_short_series_withholds_every_signal_it_cannot_compute():
    """30 bars: an RSI exists, a 200-day average does not."""
    out = tc.compute_indicators(_frame(30), shares=1_000_000)
    row = out.iloc[-1]
    for signal, needed in NEEDS_BARS.items():
        if needed <= 30:
            continue
        assert _is_unknown(row[signal]), (
            f"{signal} is {row[signal]!r} on a 30-bar series, which needs "
            f"{needed} bars. False here is a measured claim about an "
            f"average that does not exist.")


def test_the_four_signals_the_universe_serves_are_withheld_not_denied():
    """Named separately because these are the ones a customer sees."""
    out = tc.compute_indicators(_frame(100), shares=1_000_000)
    row = out.iloc[-1]
    for signal in SERVED:
        if NEEDS_BARS[signal] <= 100:
            continue
        assert _is_unknown(row[signal]), (
            f"{signal} is {row[signal]!r} on a 100-bar series. This column "
            f"is read directly by screener.universe, so a false here is "
            f"served, filtered on and sorted by.")


def test_a_long_series_still_produces_real_booleans():
    """Withholding must not swallow a signal that IS computable."""
    out = tc.compute_indicators(_frame(400), shares=1_000_000)
    row = out.iloc[-1]
    for signal in NEEDS_BARS:
        value = row[signal]
        assert not _is_unknown(value), (
            f"{signal} is absent at bar 400, where every input exists. The "
            f"mask has gone too far and is withholding a computable signal.")


def test_each_signal_becomes_known_only_once_its_window_is_full():
    """The boundary, per signal, rather than one example.

    A single short series passes even if the mask is far too wide. This
    walks one long series and finds where each signal first becomes known.
    """
    out = tc.compute_indicators(_frame(400), shares=1_000_000)
    early = {}
    for signal, needed in NEEDS_BARS.items():
        col = out[signal]
        first = next((i for i in range(len(col))
                      if not _is_unknown(col.iloc[i])), None)
        if first is None:
            early[signal] = ("never known", needed)
        elif first + 1 < needed:
            early[signal] = (f"first known at bar {first + 1}", needed)
    assert not early, (
        f"these signals report a value before their window is full "
        f"(got, needed): {early}. A value from a partial window is the same "
        f"defect as a false from no window.")


def test_the_52_week_flags_need_52_weeks_of_calendar_coverage():
    """rolling_extreme blanks a row whose series does not span 365 DAYS.

    Checked in calendar terms rather than bars, because that is the rule
    the producer actually applies -- finding 13's whole subject was a second
    producer that counted rows instead.
    """
    short = tc.compute_indicators(_frame(120), shares=1_000_000).iloc[-1]
    for signal in NEEDS_52W:
        assert _is_unknown(short[signal]), (
            f"{signal} is {short[signal]!r} on a series spanning about six "
            f"months. There is no 52-week extreme to compare against.")

    span = tc.compute_indicators(_frame(400), shares=1_000_000)
    days = (span["date"].iloc[-1] - span["date"].iloc[0]).days
    assert days > 365, (
        f"the 400-bar fixture spans {days} days, so it does not test the "
        f"52-week boundary at all")
    row = span.iloc[-1]
    for signal in NEEDS_52W:
        assert not _is_unknown(row[signal]), (
            f"{signal} is absent on a series spanning {days} days, where the "
            f"52-week extreme exists")


def test_no_signal_is_ever_the_python_false_from_a_none():
    """`bool(None)` is False, and that is how a fix like this gets undone.

    Routing a withheld signal through bool() one line later restores the
    conflation silently, and every test above would still pass if it read
    the value before that line.
    """
    out = tc.compute_indicators(_frame(30), shares=1_000_000)
    row = out.iloc[-1]
    for signal, needed in NEEDS_BARS.items():
        if needed <= 30:
            continue
        assert row[signal] is not False, (
            f"{signal} is the Python False on a series too short to compute "
            f"it")


def test_the_row_writer_preserves_the_withholding():
    """The masked value must survive `_v()` on the way to the column.

    The mask is worth nothing if the conversion that follows turns NaN into
    False. `_v` is the single point where a computed value becomes a column
    value, so it is checked directly against what the mask produces.
    """
    out = tc.compute_indicators(_frame(30), shares=1_000_000)
    for signal, needed in NEEDS_BARS.items():
        if needed <= 30:
            continue
        converted = tc._v(out[signal].iloc[-1])
        assert converted is None, (
            f"_v() turned a withheld {signal} into {converted!r}. The "
            f"column would store that instead of NULL.")

    long = tc.compute_indicators(_frame(400), shares=1_000_000)
    for signal in SERVED:
        converted = tc._v(long[signal].iloc[-1])
        assert isinstance(converted, bool), (
            f"_v() turned a computable {signal} into {converted!r}, which "
            f"is not a boolean the column can store")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed, failed = 0, []
    for fn in tests:
        try:
            fn()
            passed += 1
        except AssertionError as exc:
            failed.append((fn.__name__, str(exc)))
        except Exception as exc:                           # noqa: BLE001
            failed.append((fn.__name__, f"{type(exc).__name__}: {exc}"))
    for name, msg in failed:
        print(f"FAIL {name}\n     {msg}\n")
    print(f"{passed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
