"""
The detector of last resort: the price series itself
====================================================
Two detectors came before this one, and both need a document.

  unexplained_discontinuities  reads close/adjusted_close, so it sees only
                               what the provider chose to adjust
  reconcile_splits             needs a split record to check against

Where there is no record AND the provider did nothing, both are blind.

The served case is **ACS**: active, carried by the screener, a 7.1x step with
nothing in market.splits, publishing +3,233% as a one-year return after
v11.2.58 had already run over it. That is what this detector exists for, and
why the threshold below sits where it does.

ID8 is the larger example -- a 159x step on 2026-09-24, same shape, same
blindness in both earlier detectors -- and the fixtures here use its numbers
because they make the arithmetic obvious. It is NOT a customer-facing case:
ID8 is delisted, and the serving population is `status = 'active' AND price
IS NOT NULL`, so no customer could ever see the +10,455% it published. An
earlier version of this docstring claimed it sat "at the top of the
screener". It did not. The defect was real; its reach was not what was
written here.

This detector reads the only evidence left. It cannot correct anything: the
step size is the corporate action and the day's trading mixed together, and
nothing separates them. It withholds.

The threshold is 5x, set from the measured population rather than chosen --
see UNEXPLAINED_STEP. The cases below are the real ones.
"""

import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from compute.engine.split_adjustment import (                  # noqa: E402
    raw_price_discontinuities, unexplained_discontinuities,
    withhold_contaminated_metrics, apply_split_adjustment,
    reconcile_splits, UNEXPLAINED_STEP,
)

START = date(2025, 1, 1)


def _series(before: float, after: float, step_day: int = 300,
            n: int = 600, with_adj: bool = True) -> pd.DataFrame:
    dates = [START + timedelta(days=i) for i in range(n)]
    close = np.where(np.arange(n) < step_day, before, after)
    df = pd.DataFrame({
        "date": pd.to_datetime(dates),
        "open": close, "high": close, "low": close, "close": close,
        "volume": np.full(n, 1000.0),
    })
    if with_adj:
        # The provider adjusted nothing: adj_close tracks close exactly, so
        # their ratio never steps. This is what makes the older detector
        # blind, and it is the condition ID8 was actually in.
        df["adj_close"] = close
    return df


# ── The ID8 case ────────────────────────────────────────────────────────────

def test_a_step_with_no_record_and_no_provider_adjustment_is_caught():
    """ID8: 0.006 -> 0.9550 on 2026-09-24, 159x, nothing on record."""
    df = _series(0.0060, 0.9550)
    flags = raw_price_discontinuities(df)
    assert flags.any(), "a 159x step was not detected"
    assert int(flags.sum()) == 1, "more than the step day was flagged"
    assert bool(flags.iloc[300]), "the flag is not on the step day"


def test_the_older_detector_is_blind_to_it():
    """The premise. If close/adj_close can see this, the new detector is
    solving a problem that does not exist and should not have been built."""
    df = _series(0.0060, 0.9550)
    close = df["close"].astype(float)
    adj = df["adj_close"].astype(float)
    ratio = close / adj
    assert float(ratio.max()) == float(ratio.min()), (
        "adj_close does not track close in this fixture, so it does not "
        "reproduce the condition ID8 was in")


def test_the_id8_case_withholds_a_year_of_returns():
    df = _series(0.0060, 0.9550)
    df["return_1y"] = 104.5556
    df, withheld = withhold_contaminated_metrics(df, [], [])
    assert withheld > 0, "nothing withheld for an undocumented 159x step"
    after = df.iloc[300:300 + 252]
    assert after["return_1y"].notna().sum() == 0, (
        "a return spanning the undocumented step is still published")


def test_it_runs_through_the_main_detector():
    """Wired in, not merely present. A function nothing calls protects
    nothing."""
    df = _series(0.0060, 0.9550)
    assert unexplained_discontinuities(df, [], []).any(), (
        "raw_price_discontinuities is not reached by the detector the "
        "compute path actually calls")


def test_the_served_case_is_caught():
    """ACS -- the one that reached customers.

    7.1x is the step size observed in production; the prices here are
    constructed to produce it rather than copied, because the ratio is what
    the detector reads. It sits only 1.4x above the threshold, so this is
    also the case that would be lost first if UNEXPLAINED_STEP were raised.
    """
    df = _series(0.10, 0.71)
    flags = raw_price_discontinuities(df)
    assert flags.any(), (
        "a 7.1x step with no record went undetected on a stock the screener "
        "actually serves")
    assert int(flags.sum()) == 1


def test_the_served_case_withholds_its_returns():
    df = _series(0.10, 0.71)
    df["return_1y"] = 32.3333
    df, withheld = withhold_contaminated_metrics(df, [], [])
    assert withheld > 0
    after = df.iloc[300:300 + 252]
    assert after["return_1y"].notna().sum() == 0, (
        "+3,233% is still published on a served stock")


# ── What it must not do ─────────────────────────────────────────────────────

def test_a_real_doubling_is_left_alone():
    """57 stocks in the measured population had a single step between 2x and
    5x. Those are takeover bids and drill results -- real returns, and the
    ones customers most want to find. Withholding them to catch share-count
    changes would destroy correct numbers wholesale."""
    for factor in (2.0, 3.0, 4.5):
        df = _series(0.10, 0.10 * factor)
        assert not raw_price_discontinuities(df).any(), (
            f"a {factor}x single-day move was withheld; that is a real "
            f"return, not a corporate action")


def test_a_reconciled_split_is_not_flagged_twice():
    """The detector reads the series the indicators use, so an adjusted
    split has already been removed from it. KLV: a clean 1-for-10."""
    df = _series(0.0750, 0.7000)
    adjustable, unreconciled, _ = reconcile_splits(df, [(
        pd.Timestamp(df["date"].iloc[300]).date(), 0.100000)])
    assert len(adjustable) == 1 and not unreconciled
    out = apply_split_adjustment(df, adjustable)
    assert not raw_price_discontinuities(out).any(), (
        "a correctly adjusted consolidation was flagged by the raw-price "
        "detector; its windows would be withheld despite being correct")


def test_a_missing_quote_is_not_a_collapse():
    """A gap in the series is absence of a price, not a 100% fall."""
    df = _series(0.10, 0.10)
    df.loc[300, "close"] = np.nan
    df.loc[301, "close"] = 0.0
    assert not raw_price_discontinuities(df).any(), (
        "a missing or zero quote was treated as a price movement")


def test_it_works_without_a_provider_series_at_all():
    """adj_close may be absent. The detector must not depend on it -- that
    dependency is the defect it exists to cover."""
    df = _series(0.0060, 0.9550, with_adj=False)
    assert raw_price_discontinuities(df).any()


def test_the_threshold_is_what_the_population_showed():
    """Pinned. Lowering it to 2x would withhold 57 more stocks, nearly all
    of them real moves; raising it past 7x would let ACS through."""
    assert UNEXPLAINED_STEP == 5.0


def test_the_boundary_is_symmetric():
    """A 5x rise and a 5x fall are the same event seen from either side."""
    up = _series(0.10, 0.10 * (UNEXPLAINED_STEP * 1.01))
    down = _series(0.10, 0.10 / (UNEXPLAINED_STEP * 1.01))
    assert raw_price_discontinuities(up).any()
    assert raw_price_discontinuities(down).any()


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
