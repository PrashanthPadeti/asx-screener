"""
The guard must cover the metric, at every horizon
=================================================
CONTAMINATED_BY_WINDOW used to be a hand-written map of column -> row count:

    "return_1y": 252, "return_6m": 126, "return_3m": 63, ...

Two failures followed from it being a second declaration of the window.

**It stopped matching what it guards.** v11.2.62 anchored the returns on the
calendar; the guard kept counting rows. For a stock trading every weekday 252
rows is about 365 days and the two nearly agree. For a thin stock they do
not -- and a thin stock is exactly the case the calendar anchoring existed to
get right.

**It could not acquire a new window.** Ten multi-year horizons move into
technical_compute in this release. Under a hand-written map they would have
computed with no withholding at all, which is the state yearly_compute was
already in when it published return_3y = 1449.0 for JNS (+144,900%) beside a
return_1y of +247%.

So the guard now reads ALL_WINDOWS. These tests assert the coupling holds --
over the whole declared population, not over the horizons someone remembered.
"""

import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from compute.engine.return_windows import ALL_WINDOWS            # noqa: E402
from compute.engine.split_adjustment import (                    # noqa: E402
    CONTAMINATED_BY_WINDOW, CONTAMINATED_BY_ROWS,
    withhold_contaminated_metrics, withhold_spanning_calendar_windows,
)

START = date(2008, 1, 1)
N = 6700                      # ~18 years of calendar days
STEP = 6000                   # the unexplained event


def _series() -> pd.DataFrame:
    """Flat at 0.10, then a 7.1x step with nothing on record. The ACS shape."""
    dates = [START + timedelta(days=i) for i in range(N)]
    close = np.where(np.arange(N) < STEP, 0.10, 0.71)
    df = pd.DataFrame({
        "date": pd.to_datetime(dates),
        "open": close, "high": close, "low": close, "close": close,
        "volume": np.full(N, 1000.0),
        "adj_close": close,
    })
    for name in ALL_WINDOWS:
        df[name] = 1.0        # a value on every row, so withholding is visible
    return df


# ── Coverage ────────────────────────────────────────────────────────────────

def test_every_declared_window_is_guarded():
    """The population check. A horizon that exists in ALL_WINDOWS and not in
    the guard computes unprotected, which is the state the multi-year returns
    arrived in."""
    missing = set(ALL_WINDOWS) - set(CONTAMINATED_BY_WINDOW)
    assert not missing, f"windows with no withholding: {sorted(missing)}"


def test_the_guard_invents_no_windows_of_its_own():
    """The other direction. A guard for a metric nobody computes is a rule
    that can never fire and will be trusted anyway."""
    extra = set(CONTAMINATED_BY_WINDOW) - set(ALL_WINDOWS)
    assert not extra, f"guards for windows that do not exist: {sorted(extra)}"


def test_the_row_based_guards_are_only_single_period_metrics():
    """Row counting is correct for these and only these: each compares a
    close with its immediate predecessor."""
    assert set(CONTAMINATED_BY_ROWS) == {
        "daily_return", "log_return", "gap_pct", "return_1d"}
    assert all(p == 1 for p in CONTAMINATED_BY_ROWS.values())


# ── Behaviour, at every horizon ─────────────────────────────────────────────

def test_every_horizon_withholds_across_an_unexplained_step():
    """The JNS case, generalised. Each window spanning the step must be
    blanked -- including the fifteen-year one, which no hand-written map ever
    listed."""
    df, _ = withhold_contaminated_metrics(_series(), [], [])
    just_after = STEP + 5
    for name in ALL_WINDOWS:
        assert pd.isna(df.loc[just_after, name]), (
            f"{name} still published across an undocumented 7.1x step")


def test_a_window_that_closes_before_the_step_is_untouched():
    """Withholding must not be indiscriminate. A one-week return a year
    before the event never compared a pre-event price with a post-event one
    and is a correct number."""
    df, _ = withhold_contaminated_metrics(_series(), [], [])
    long_before = STEP - 400
    assert df.loc[long_before, "return_1w"] == 1.0


def test_the_event_day_itself_is_withheld():
    df, _ = withhold_contaminated_metrics(_series(), [], [])
    assert pd.isna(df.loc[STEP, "return_1w"])


def test_an_event_on_the_anchor_day_is_not_contamination():
    """The boundary, and it is a real one.

    The return is close[i] / close[anchor]. If the event lands ON the anchor
    day, the anchor close and every close after it are already on the
    post-event basis, so the ratio is sound. Withholding it would destroy a
    correct number.
    """
    n = 800
    dates = pd.Series(pd.to_datetime(
        [START + timedelta(days=i) for i in range(n)]))
    values = pd.Series(np.full(n, 1.0))
    flags = pd.Series(np.zeros(n, dtype=bool))

    row = 700
    offset, grace = ALL_WINDOWS["return_1y"]
    anchor = row - 365
    flags.iloc[anchor] = True

    out = withhold_spanning_calendar_windows(values, flags, dates, offset, grace)
    assert out.iloc[row] == 1.0, (
        "an event on the anchor day was treated as contamination")

    flags.iloc[anchor] = False
    flags.iloc[anchor + 1] = True
    out = withhold_spanning_calendar_windows(values, flags, dates, offset, grace)
    assert pd.isna(out.iloc[row]), (
        "an event one day after the anchor mixes two price bases and must "
        "withhold")


def test_a_future_event_never_withholds_a_past_return():
    """No lookahead, including on the unanchored rows the guard now covers.
    A return computed before the event is correct and stays correct."""
    n = 800
    dates = pd.Series(pd.to_datetime(
        [START + timedelta(days=i) for i in range(n)]))
    values = pd.Series(np.full(n, 1.0))
    flags = pd.Series(np.zeros(n, dtype=bool))
    flags.iloc[600] = True

    offset, grace = ALL_WINDOWS["return_1y"]
    out = withhold_spanning_calendar_windows(values, flags, dates, offset, grace)
    assert out.iloc[:600].notna().all(), (
        "a later event withheld returns computed before it happened")


def test_an_unanchored_row_is_not_silently_trusted():
    """A row whose window reaches past the start of the series cannot be
    shown to be clean. Under the real producer it is NaN anyway; the guard
    must not decline to look at it merely because it has no anchor."""
    n = 400                                   # shorter than a one-year window
    dates = pd.Series(pd.to_datetime(
        [START + timedelta(days=i) for i in range(n)]))
    values = pd.Series(np.full(n, 1.0))
    flags = pd.Series(np.zeros(n, dtype=bool))
    flags.iloc[10] = True

    offset, grace = ALL_WINDOWS["return_2y"]
    out = withhold_spanning_calendar_windows(values, flags, dates, offset, grace)
    assert pd.isna(out.iloc[300]), (
        "a value survived on a row whose window cannot be established and "
        "which contains an unexplained event")


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
