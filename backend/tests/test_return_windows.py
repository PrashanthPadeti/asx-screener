"""
A period is a period, at every horizon
======================================
`close / close.shift(252)` was labelled a one-year return. 252 is a count of
ROWS, and a row is a day the stock traded. For a daily trader the two agree,
which is why this lasted; for anything else they diverge silently. MRD sat at
the top of the served screener on 27 Oct 2026 at +1,595%, from an anchor dated
2025-07-17 -- a 467-day "year".

v11.2.62 fixed that with day counts. Day counts are still an approximation of
what the names claim -- 30 days is not a month, and 15 x 365 misses by four
days -- so the windows are now calendar offsets.

The multi-year horizons arrive here from two other places, both worse:

  return_3y/5y/7y/10y/15y  yearly_compute.price_return(), whose price_at()
                           applies the same "last close at or before" rule
                           with NO grace bound, ends at the fiscal period end
                           rather than today, and has no corporate-action
                           withholding. It published return_3y = 1449.0 for
                           JNS -- +144,900% -- beside a return_1y of +247%.

  return_2y/4y/6y/8y/9y    nothing. No producer exists. They are filterable,
                           sortable and shown on company pages, and the
                           universe is upserted, so they hold whatever was
                           last written to them by code that is gone. 376
                           served stocks carried a two-year return while
                           having no one-year return.

These tests fix the PROPERTY -- a window measures the period it names, and
where it cannot, it says nothing -- rather than any particular stock's number.
"""

import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from compute.engine.return_windows import (                     # noqa: E402
    WINDOWS, LONG_WINDOWS, ALL_WINDOWS, HIGH_LOW_DAYS,
    anchor_positions, window_return, rolling_extreme,
)

START = date(2024, 1, 1)
ONE_YEAR = pd.DateOffset(years=1)


def _daily(n: int = 800, start: date = START) -> pd.Series:
    """Every calendar day -- a stock that never misses a session."""
    return pd.Series([pd.Timestamp(start + timedelta(days=i)) for i in range(n)])


def _gappy(dense_days: int, gap_days: int, tail_days: int) -> pd.Series:
    """Trades, stops dead, then trades again. The MRD/thin-stock shape."""
    days = list(range(dense_days))
    days += list(range(dense_days + gap_days, dense_days + gap_days + tail_days))
    return pd.Series([pd.Timestamp(START + timedelta(days=i)) for i in days])


def _span(dates: pd.Series, i: int, pos: int) -> int:
    return (dates[i] - dates[pos]).days


# ── The window measures what it claims ──────────────────────────────────────

def test_a_year_is_a_year_for_a_daily_trader():
    """The case that must not move. A stock trading every session had a
    correct number before this change and must have the same one after."""
    dates = _daily(800)
    close = pd.Series(np.linspace(1.0, 5.0, 800))
    out = window_return(close, dates, ONE_YEAR, 7)

    last = len(dates) - 1
    target = dates[last] - ONE_YEAR
    anchor = dates[dates <= target].index[-1]
    expected = close[last] / close[anchor] - 1
    assert abs(out.iloc[last] - expected) < 1e-9


def test_the_mrd_shape_no_longer_reaches_past_the_year():
    """206 rows in 400 days put the 252nd row back at 467 days. Calendar
    anchoring must land inside the window regardless of row count."""
    dates = _gappy(dense_days=200, gap_days=160, tail_days=200)
    pos = anchor_positions(dates, ONE_YEAR, 7)

    last = len(dates) - 1
    assert pos[last] >= 0, "no anchor found for a stock with 3+ years of history"
    assert 365 <= _span(dates, last, pos[last]) <= 365 + 7


def test_the_row_based_window_would_have_been_wrong_here():
    """The premise. If shift(252) agreed with the calendar on this fixture,
    the fixture does not reproduce the defect and proves nothing."""
    dates = _gappy(dense_days=200, gap_days=160, tail_days=200)
    last = len(dates) - 1
    assert last >= 252
    assert (dates[last] - dates[last - 252]).days > 365 + 7


def test_a_calendar_year_is_not_365_days_across_a_leap():
    """Why offsets replaced day counts.

    From 2025-02-28 back one year is 2024-02-28, and that span CONTAINS
    29 Feb 2024, so it is 366 days. From 2025-03-01 it is 2024-03-01, which
    is past the 29th, so it is 365. A fixed 365 is wrong on one side of that
    boundary and the error is invisible either way.

    (Written the other way round first, from reasoning rather than
    arithmetic, and caught by running it.)
    """
    e = pd.Timestamp("2025-02-28")
    assert (e - (e - ONE_YEAR)).days == 366
    d = pd.Timestamp("2025-03-01")
    assert (d - (d - ONE_YEAR)).days == 365


def test_the_end_of_february_clamps_rather_than_overflowing():
    """29 Feb minus one year has no same-date answer. DateOffset clamps to
    the 28th; it must not roll forward into March, which would shorten the
    window."""
    d = pd.Timestamp("2024-02-29")
    assert (d - ONE_YEAR) == pd.Timestamp("2023-02-28")


# ── Absence must stay absent ────────────────────────────────────────────────

def test_no_quote_near_the_window_start_yields_no_return():
    """The nearest available price is NOT an acceptable substitute. Using it
    produces a well-formed number measuring an unknown period -- the defect,
    not a workaround for it. This is exactly what yearly_compute.price_at()
    does, having no grace bound at all."""
    dates = _gappy(dense_days=60, gap_days=400, tail_days=60)
    close = pd.Series(np.full(len(dates), 1.0))
    out = window_return(close, dates, ONE_YEAR, 7)
    assert pd.isna(out.iloc[-1]), (
        "a return was published from an anchor well outside the window")


def test_a_series_shorter_than_the_window_yields_nothing():
    dates = _daily(100)
    close = pd.Series(np.linspace(1.0, 2.0, 100))
    out = window_return(close, dates, ONE_YEAR, 7)
    assert out.notna().sum() == 0


def test_a_zero_opening_price_is_not_a_gain():
    dates = _daily(800)
    close = pd.Series(np.full(800, 2.0))
    close.iloc[0] = 0.0
    out = window_return(close, dates, ONE_YEAR, 7)
    assert pd.isna(out.iloc[366])


# ── The anchor rule itself ──────────────────────────────────────────────────

def test_the_anchor_never_shortens_the_window():
    """The anchor is the last row AT OR BEFORE the target, not the nearest.
    The nearest could sit after it, making the return measure LESS than it
    claims -- no better than measuring more, and harder to notice."""
    dates = _daily(800)
    for name, (offset, grace) in ALL_WINDOWS.items():
        pos = anchor_positions(dates, offset, grace)
        for i in range(len(dates)):
            if pos[i] >= 0:
                assert dates[pos[i]] <= dates[i] - offset, (
                    f"{name} anchored after its own target")


def test_every_published_return_sits_inside_its_grace():
    """The property, over every window and every row, rather than over the
    one case that prompted the change."""
    dates = _gappy(dense_days=300, gap_days=45, tail_days=400)
    for name, (offset, grace) in ALL_WINDOWS.items():
        pos = anchor_positions(dates, offset, grace)
        for i in range(len(dates)):
            if pos[i] >= 0:
                gap = (dates[i] - offset) - dates[pos[i]]
                assert 0 <= gap.days <= grace, (
                    f"{name} anchored {gap.days} days before its target, "
                    f"outside its {grace}-day grace")


def test_a_longer_horizon_may_publish_where_a_shorter_one_cannot():
    """A correction, recorded so it is not re-asserted.

    Production showed 376 served stocks with a two-year return and no
    one-year return, and that was first read as impossible -- "a two-year
    window needs strictly more history". It does need more history, but that
    is not what the anchor asks for. The anchor needs a quote NEAR A
    PARTICULAR DATE, and a stock can have traded around its two-year
    anniversary and not around its one-year one.

    This fixture is exactly that shape: trades for 500 days, stops for 300,
    resumes. The four-year target lands in the dense early stretch and
    publishes; the three-year target lands in the hole and correctly does
    not.

    So coverage across horizons is NOT monotonic, and a test asserting that
    it is would fail on correct data. What remains true, and is tested by
    test_the_anchor_never_shortens_the_window, is that a published horizon
    always spans at least the period it names.

    The orphan columns are still a defect -- nothing writes return_2y/4y/6y/
    8y/9y -- but the evidence for that is the absent producer, not an
    arithmetic impossibility.
    """
    dates = _gappy(dense_days=500, gap_days=300, tail_days=900)
    close = pd.Series(np.linspace(1.0, 4.0, len(dates)))
    last = len(dates) - 1

    def published(name: str) -> bool:
        offset, grace = ALL_WINDOWS[name]
        return not pd.isna(window_return(close, dates, offset, grace).iloc[last])

    assert published("return_4y"), "the fixture no longer exercises the case"
    assert not published("return_3y"), (
        "the three-year target no longer falls in the gap, so this fixture "
        "does not demonstrate non-monotonic coverage")


def test_the_grace_absorbs_closures_and_nothing_more():
    """What the grace is FOR, stated as bounds rather than as a ratio.

    It bridges the gap between a calendar target and the most recent session
    at or before it. That gap is a property of the exchange calendar, not of
    the window: the longest ordinary ASX closure is four days (Good Friday
    through Easter Monday), and it is four days whether the window is a week
    or fifteen years. The upper bound exists because anything much larger
    stops being a closure allowance and becomes a staleness allowance.

    A ratio-based rule was tried and was wrong: it called the 7-day window's
    4-day grace excessive while passing the 1-year window's 14-day grace,
    which is the one that could actually misstate a period.
    """
    for name, (_, grace) in ALL_WINDOWS.items():
        assert grace >= 4, f"{name}: under four days blanks returns at Easter"
        assert grace <= 14, f"{name}: over a fortnight is a staleness allowance"


def test_a_long_weekend_does_not_blank_a_weekly_return():
    """Weekdays only, with an Easter-shaped four-day break."""
    days = [d for d in range(400)
            if (START + timedelta(days=d)).weekday() < 5
            and not (120 <= d <= 123)]
    dates = pd.Series([pd.Timestamp(START + timedelta(days=d)) for d in days])
    close = pd.Series(np.full(len(dates), 1.0))
    out = window_return(close, dates, *WINDOWS["return_1w"])
    assert out.iloc[40:].notna().mean() > 0.95


# ── The horizons that had no producer ───────────────────────────────────────

def test_every_served_horizon_has_a_window():
    """screener.universe carries these columns, the screener filters and
    sorts on them, and the company page shows them. Five of them -- 2y, 4y,
    6y, 8y, 9y -- were written by nothing at all.

    Pinned against the served column list, not against what this module
    happens to define, because the defect was precisely that the producer's
    set and the served set had drifted apart.
    """
    served = {f"return_{n}y" for n in (2, 3, 4, 5, 6, 7, 8, 9, 10, 15)}
    missing = served - set(ALL_WINDOWS)
    assert not missing, f"served columns with no producer: {sorted(missing)}"


def test_the_long_horizons_are_calendar_years():
    for n in (2, 3, 5, 10, 15):
        offset, _ = LONG_WINDOWS[f"return_{n}y"]
        d = pd.Timestamp("2026-10-27")
        assert (d - offset) == pd.Timestamp(f"{2026 - n}-10-27")


def test_the_one_year_grace_is_the_measured_one():
    """Pinned to a measurement, not to taste.

    Of the 2,093 served stocks on 28 Oct 2026, 1,567 had a close before their
    one-year target; 1,554 of those anchored within three days, two within
    4-7, one at 15-30, ten past 90. The 8-14 day bucket was empty, so 14
    admitted a 379-day "year" and bought not one additional stock.

    Raising this again is a decision about customer-visible numbers and needs
    its own measurement, not a judgement call.
    """
    assert WINDOWS["return_1y"][1] == 7


def test_the_windows_are_declared_not_scattered():
    """Pinned. These are read by technical_compute and by the governed-metric
    contract; a change here changes what every return column means."""
    assert set(WINDOWS) == {
        "return_1w", "return_1m", "return_3m", "return_6m", "return_1y"}
    assert set(LONG_WINDOWS) == {
        f"return_{n}y" for n in (2, 3, 4, 5, 6, 7, 8, 9, 10, 15)}
    assert set(ALL_WINDOWS) == set(WINDOWS) | set(LONG_WINDOWS)
    assert HIGH_LOW_DAYS == 365


# ── 52-week high and low ────────────────────────────────────────────────────

def test_the_52w_high_uses_a_calendar_year():
    dates = _daily(800)
    high = pd.Series(np.full(800, 1.0))
    high.iloc[0] = 99.0            # an old peak, outside the year
    high.iloc[700] = 5.0           # inside it
    assert rolling_extreme(high, dates, "max").iloc[-1] == 5.0


def test_a_thin_stock_gets_a_52w_high_after_a_calendar_year():
    """rolling(252) needed 252 ROWS, so a stock trading twice a week had no
    52-week high after three years of listing."""
    days = list(range(0, 500, 3))
    dates = pd.Series([pd.Timestamp(START + timedelta(days=d)) for d in days])
    high = pd.Series(np.linspace(1.0, 2.0, len(dates)))
    assert rolling_extreme(high, dates, "max").notna().any()


def test_no_52w_high_before_the_history_covers_it():
    """The opposite failure, which a bare rolling('365D') would introduce:
    min_periods=1 hands a stock listed last week a '52-week high'."""
    dates = _daily(200)
    high = pd.Series(np.linspace(1.0, 2.0, 200))
    assert rolling_extreme(high, dates, "max").notna().sum() == 0


def test_the_low_is_the_same_rule_in_the_other_direction():
    dates = _daily(800)
    low = pd.Series(np.full(800, 10.0))
    low.iloc[0] = 0.01
    low.iloc[700] = 2.0
    assert rolling_extreme(low, dates, "min").iloc[-1] == 2.0


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
        except Exception as e:                                # noqa: BLE001
            failures.append(name)
            print(f"  ERROR {name}  - {type(e).__name__}: {e}")
    print(f"\n{len(tests) - len(failures)}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
