"""
Split adjustment, and withholding what cannot be adjusted
=========================================================
Every technical indicator was computed from the raw close until 26 Oct 2026.
A 1-for-10 consolidation multiplies the raw price by ten, so the measured
result was:

    MPP  Metro Performance Glass   shown +999%   actually -72.5%
    IOV  Ion Video                 shown +262%   actually -96.4%
    ASP  Aspermont                 shown +155%   actually -99.0%

105 stocks carried a wrong 1-year return on the day this was written, and
the error runs in the direction that does most harm: companies consolidate
*because* they have collapsed, so the defect placed the exchange's worst
performers at the top of "best 1-year return".

Two populations, two treatments, both checked here:

  recorded split      adjust — the ratio makes the correction exact
  no recorded split   withhold — 78 discontinuities have no source, because
                      market.corporate_events is empty

The numbers below are the real ones. MPP's 1-for-40 and ENL's 1-for-10 are
the cases this code exists for; a test over invented ratios would not have
caught a reciprocal applied the wrong way round.
"""

import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from compute.engine.split_adjustment import (                  # noqa: E402
    apply_split_adjustment, cumulative_adjustment,
    unexplained_discontinuities, withhold_contaminated_metrics,
    withhold_spanning_windows,
)


def _frame(prices, dates=None, adj=None):
    n = len(prices)
    # `dates or ...` raises on a DatetimeIndex — its truth value is
    # ambiguous — so every case passing explicit dates errored rather than
    # ran. An `is None` check is the only safe form here.
    if dates is None:
        dates = pd.date_range("2026-01-01", periods=n, freq="D")
    df = pd.DataFrame({
        "date": pd.to_datetime(dates),
        "open": prices, "high": prices, "low": prices, "close": prices,
        "adj_close": adj if adj is not None else prices,
        "volume": [1000] * n,
    })
    return df


# ── Adjustment ──────────────────────────────────────────────────────────────

def test_a_consolidation_does_not_look_like_a_gain():
    """The defect, in one assertion.

    A stock trades at 0.10, does a 1-for-10 consolidation, and trades at
    1.00. Nothing happened to its value. On the raw close that is +900%.
    """
    dates = pd.to_datetime(["2026-09-01", "2026-09-11"])
    df = _frame([0.10, 1.00], dates=dates)
    out = apply_split_adjustment(df, [(date(2026, 9, 11), 0.1)])

    raw_return = df["close"].iloc[-1] / df["close"].iloc[0] - 1
    adj_return = out["close_adj"].iloc[-1] / out["close_adj"].iloc[0] - 1

    assert round(raw_return, 2) == 9.00, "the raw series should show +900%"
    assert abs(adj_return) < 1e-9, (
        f"after adjustment the return should be 0, got {adj_return}")


def test_a_real_collapse_still_reads_as_a_collapse():
    """MPP: 1-for-40, and the business genuinely fell.

    Adjustment must not turn a loss into a gain OR a gain into a loss; it
    removes the share-count change and leaves the price change.
    """
    dates = pd.to_datetime(["2026-03-02", "2026-03-03"])
    # 0.0275 -> consolidated x40 = 1.10, but it actually traded at 0.30
    df = _frame([0.0275, 0.30], dates=dates)
    out = apply_split_adjustment(df, [(date(2026, 3, 3), 0.025)])
    adj_return = out["close_adj"].iloc[-1] / out["close_adj"].iloc[0] - 1
    assert adj_return < 0, (
        f"a stock that lost value must not show a gain; got {adj_return:.2%}")
    assert round(adj_return, 3) == round(0.30 / (0.0275 * 40) - 1, 3)


def test_todays_price_is_never_restated():
    """The most recent rows carry factor 1.0, so the quoted price is
    untouched — only history is restated into today's terms."""
    df = _frame([1.0, 2.0, 3.0])
    out = apply_split_adjustment(df, [(date(2026, 1, 2), 0.5)])
    assert out["adj_factor"].iloc[-1] == 1.0
    assert out["close_adj"].iloc[-1] == out["close"].iloc[-1]


def test_the_split_date_itself_is_not_adjusted():
    """The split date already carries the post-split price."""
    dates = pd.to_datetime(["2026-09-10", "2026-09-11", "2026-09-12"])
    df = _frame([0.10, 1.00, 1.05], dates=dates)
    out = apply_split_adjustment(df, [(date(2026, 9, 11), 0.1)])
    assert out["adj_factor"].tolist() == [10.0, 1.0, 1.0]


def test_ohlc_are_adjusted_together():
    """Adjusting close alone leaves an adjusted close beside raw highs and
    breaks ATR, Bollinger and the 52-week range."""
    df = _frame([1.0, 2.0])
    out = apply_split_adjustment(df, [(date(2026, 1, 2), 0.5)])
    for col in ("open", "high", "low", "close"):
        assert f"{col}_adj" in out.columns, f"{col} was not adjusted"
        assert out[f"{col}_adj"].iloc[0] == df[col].iloc[0] * 2.0


def test_volume_is_adjusted_inversely():
    """Ten times as many shares existed before a 1-for-10, so dollar volume
    stays invariant across the event."""
    df = _frame([0.10, 1.00])
    out = apply_split_adjustment(df, [(date(2026, 1, 2), 0.1)])
    dollar_before = out["close_adj"].iloc[0] * out["volume_adj"].iloc[0]
    assert round(dollar_before, 6) == round(
        df["close"].iloc[0] * df["volume"].iloc[0], 6)


def test_several_splits_compound():
    dates = pd.to_datetime(["2026-01-01", "2026-02-01", "2026-03-01"])
    df = _frame([1.0, 1.0, 1.0], dates=dates)
    out = apply_split_adjustment(df, [(date(2026, 2, 1), 0.5),
                                      (date(2026, 3, 1), 0.1)])
    # Before both: x2 then x10
    assert out["adj_factor"].iloc[0] == 20.0
    assert out["adj_factor"].iloc[1] == 10.0
    assert out["adj_factor"].iloc[2] == 1.0


def test_an_unusable_ratio_is_skipped_not_guessed():
    """Zero or None cannot be inverted. Skipping leaves the discontinuity
    for the withholding pass, so a bad ratio degrades to 'unknown' rather
    than to a silently wrong number."""
    df = _frame([1.0, 2.0])
    for bad in (0, None, -1):
        out = apply_split_adjustment(df, [(date(2026, 1, 2), bad)])
        assert (out["adj_factor"] == 1.0).all()


def test_no_splits_leaves_the_series_alone():
    df = _frame([1.0, 2.0, 3.0])
    out = apply_split_adjustment(df, [])
    assert (out["close_adj"] == out["close"]).all()


# ── Withholding ─────────────────────────────────────────────────────────────

def test_an_unexplained_discontinuity_is_detected():
    """close/adj_close steps when the provider restates for an event."""
    df = _frame([1.0, 1.0, 1.0, 1.0],
                adj=[1.0, 1.0, 0.5, 0.5])          # ratio 1,1,2,2
    flags = unexplained_discontinuities(df, [])
    assert flags.tolist() == [False, False, True, False]


def test_a_discontinuity_next_to_a_recorded_split_is_not_withheld():
    """It is adjusted, so withholding it too would remove a number we can
    actually compute."""
    dates = pd.to_datetime(["2026-09-09", "2026-09-10", "2026-09-11", "2026-09-12"])
    df = _frame([1.0, 1.0, 1.0, 1.0], dates=dates, adj=[1.0, 1.0, 0.5, 0.5])
    flags = unexplained_discontinuities(df, [(date(2026, 9, 11), 0.1)])
    assert not flags.any(), "an adjusted event was withheld as well"


def test_an_ordinary_dividend_is_not_withheld():
    """A dividend-driven price drop is a real market movement that a price
    return should include. Only share-count events corrupt the series."""
    df = _frame([1.0] * 4, adj=[1.0, 1.0, 0.97, 0.97])   # a 3% ex-div step
    assert not unexplained_discontinuities(df, []).any()


def test_withholding_spans_the_whole_window():
    """A 1-year return is wrong for 252 rows after the event, not on the day
    of it alone."""
    values = pd.Series([1.0] * 10)
    flags = pd.Series([False] * 10)
    flags.iloc[3] = True
    out = withhold_spanning_windows(values, flags, periods=4)
    # rows 3,4,5,6 have the event inside their 4-row window
    assert out.isna().tolist() == [False, False, False,
                                   True, True, True, True,
                                   False, False, False]


def test_metrics_are_withheld_and_counted():
    n = 300
    df = _frame([1.0] * n)
    df["adj_close"] = [1.0] * 150 + [0.5] * 150      # a step at row 150
    df["return_1y"] = 0.0
    df["return_1m"] = 0.0
    df, withheld = withhold_contaminated_metrics(df, [])
    assert withheld > 0, "nothing was withheld over a clear discontinuity"
    assert pd.isna(df["return_1y"].iloc[150]), "the event row kept its return"
    assert not pd.isna(df["return_1y"].iloc[149]), (
        "a row BEFORE the event was withheld; the window looks backwards")


def test_a_clean_series_withholds_nothing():
    df = _frame([1.0, 1.1, 1.2])
    df["return_1m"] = [0.1, 0.2, 0.3]
    df, withheld = withhold_contaminated_metrics(df, [])
    assert withheld == 0
    assert df["return_1m"].notna().all()


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
