"""
A recorded split is not an explanation until it reconciles
==========================================================
Until v11.2.58 a split record suppressed the discontinuity detector merely by
existing: any step within SPLIT_WINDOW_DAYS of one was marked explained, and
nobody checked that the ratio accounted for it.

MPP showed the cost. A 1-for-40 was on record, so the detector stayed silent.
The price went from 0.0011 to 1.7200 across the event -- a factor of 1,564.
The ratio explained 40 of it. The other 39x became a +2150% one-year return
on a collapsed company, sitting at the top of "best 1-year return", which is
the column customers screen on. The whole v11.2.52-55 withholding mechanism
was in place and running, and it withheld nothing, because the thing it
trusts to decide was the thing that was wrong.

The cases below are the REAL population, measured against production on
27 Oct 2026, not invented ones. That matters: the first threshold I proposed
(10%) would have classified routine micro-cap volatility as corruption and
withheld hundreds of correct returns. Testing against the actual distribution
is what showed the band had to be a factor of two.
"""

import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from compute.engine.split_adjustment import (                  # noqa: E402
    reconcile_splits, unexplained_discontinuities, _is_flat,
    withhold_contaminated_metrics, apply_split_adjustment,
    RECONCILE_BAND, IMMATERIAL_FACTOR,
)

START = date(2025, 1, 1)


def _series(before_close: float, after_close: float, split_day: int = 300,
            n: int = 600) -> pd.DataFrame:
    """A flat series at `before_close` that steps to `after_close`.

    Flat on purpose: any movement would be a second effect confounding the
    one under test. The step lands on `split_day`.
    """
    dates = [START + timedelta(days=i) for i in range(n)]
    close = np.where(np.arange(n) < split_day, before_close, after_close)
    return pd.DataFrame({
        "date": pd.to_datetime(dates),
        "open": close, "high": close, "low": close, "close": close,
        # adj_close equal to close: the provider shows no adjustment at all.
        # This is the case the old detector could not see.
        "adj_close": close,
        "volume": np.full(n, 1000.0),
    })


def _trading_series(before_close: float, after_close: float,
                    split_day: int = 300, n: int = 600) -> pd.DataFrame:
    """Like _series, but the price moves day to day.

    Needed because a FLAT series and a continuous one are different things,
    and conflating them is what produced PGL's and HXL's 0.000000 returns.
    """
    df = _series(before_close, after_close, split_day, n)
    wobble = 1.0 + 0.25 * np.sin(np.arange(n) / 9.0)
    for col in ("open", "high", "low", "close", "adj_close"):
        df[col] = df[col].to_numpy() * wobble
    return df


def _split_on(df: pd.DataFrame, day: int = 300):
    return pd.Timestamp(df["date"].iloc[day]).date()


# ── The MPP case ────────────────────────────────────────────────────────────

def test_a_ratio_that_does_not_account_for_the_step_is_unreconciled():
    """MPP, with its real numbers."""
    df = _series(0.0011, 1.7200)
    splits = [(_split_on(df), 0.025)]           # 1-for-40
    adjustable, unreconciled, _ = reconcile_splits(df, splits)
    assert not adjustable, (
        "the 1-for-40 was accepted as an explanation for a 1,564x step")
    assert len(unreconciled) == 1, (
        "MPP's split reconciled; the +2150% return would be published again")


def test_the_mpp_case_withholds_the_year_of_returns():
    """The point of detecting it. Reaching the right verdict and then
    publishing the number anyway would be worthless."""
    df = _series(0.0011, 1.7200)
    splits = [(_split_on(df), 0.025)]
    adjustable, unreconciled, _ = reconcile_splits(df, splits)
    df["return_1y"] = 21.5
    df, withheld = withhold_contaminated_metrics(df, adjustable, unreconciled)
    assert withheld > 0, "nothing was withheld for an unreconciled split"
    # Every row for a year after the event must be blank.
    after = df.iloc[300:300 + 252]
    assert after["return_1y"].notna().sum() == 0, (
        "a return spanning the unreconciled event is still published")


def test_the_detector_cannot_see_it_on_its_own():
    """Why the reconciliation had to be added rather than the threshold
    tuned. The detector reads close/adj_close; MPP's provider series was
    self-consistent, so that ratio never steps and `broke` is empty."""
    df = _series(0.0011, 1.7200)
    splits = [(_split_on(df), 0.025)]
    seen_alone = unexplained_discontinuities(df, splits)
    assert not seen_alone.any(), (
        "this test's premise is wrong -- if the detector CAN see it, the "
        "reconciliation is solving a problem that does not exist")


# ── Clean data must not be corrupted ────────────────────────────────────────

def test_a_split_with_no_price_step_is_not_applied():
    """NTM has two 1-for-15 records six days apart. The series steps once.
    Applying both would multiply by 225 -- the repair creating a far larger
    error than the defect."""
    df = _trading_series(0.0030, 0.0030)        # trades, but no net step
    splits = [(_split_on(df), 0.066667)]
    adjustable, unreconciled, skipped = reconcile_splits(df, splits)
    assert not adjustable, (
        "a split was applied to a continuous series, creating a 15x "
        "discontinuity in clean data")
    assert len(skipped) == 1
    assert not unreconciled, (
        "a continuous series was withheld; there is nothing wrong with it")


def test_a_flat_series_is_not_evidence_of_continuity():
    """PGL and HXL, which v11.2.58 got wrong.

    Both sat on one unchanged price for a year. No step could appear in a
    series that never moves, so the split was skipped as "already applied",
    and today over a year-ago gave a return of exactly 0.000000 -- a number
    that is certainly wrong, replacing -0.93 and -0.90 which may well have
    been right.

    Stillness is the absence of evidence, not evidence of continuity.
    """
    df = _series(0.0010, 0.0010)                # never moves, all year
    splits = [(_split_on(df), 0.066667)]        # a material 1-for-15
    adjustable, unreconciled, skipped = reconcile_splits(df, splits)
    assert not adjustable, "a flat series was adjusted"
    assert len(unreconciled) == 1, (
        "a split against an untraded series was skipped as already "
        "continuous; the return comes out as exactly 0.000000")
    assert not skipped


def test_an_immaterial_ratio_is_skipped_without_withholding():
    """Bonus issues and DRP adjustments sit at ratios like 1.0035. Nine
    stocks in the measured population were these. Withholding a year of
    returns over a 0.35% share-count change would be absurd."""
    df = _series(0.2850, 0.2825)
    splits = [(_split_on(df), 1.001114)]        # ELT, from production
    adjustable, unreconciled, skipped = reconcile_splits(df, splits)
    assert not unreconciled, "an immaterial ratio caused a withholding"
    assert len(skipped) == 1


def test_a_genuine_consolidation_still_adjusts():
    """The mechanism must keep working. KLV: 1-for-10, 0.075 -> 0.70."""
    df = _series(0.0750, 0.7000)
    splits = [(_split_on(df), 0.100000)]
    adjustable, unreconciled, _ = reconcile_splits(df, splits)
    assert len(adjustable) == 1, (
        "a correctly recorded consolidation was rejected; returns across it "
        "would be withheld instead of corrected")
    assert not unreconciled

    out = apply_split_adjustment(df, adjustable)
    # Pre-split prices restated into post-split terms: 0.075 x 10 = 0.75,
    # continuous with the 0.70 that followed.
    assert abs(float(out["close_adj"].iloc[0]) - 0.75) < 1e-9
    assert abs(float(out["close_adj"].iloc[-1]) - 0.70) < 1e-9


# ── The band is what the population demanded ────────────────────────────────

def test_ordinary_volatility_is_not_treated_as_corruption():
    """The first threshold I proposed was 10%, which would have called every
    one of these a fault. They are price movements around a consolidation,
    not data defects, and withholding them would remove correct returns from
    hundreds of stocks.

    Residuals taken from the 27 Oct 2026 production measurement.
    """
    # (ratio, residual) -> construct a step giving that residual.
    for ratio, residual in [(0.200000, 0.923),    # AUZ
                            (0.100000, 0.778),    # ENL
                            (0.050000, 1.150),    # EVR
                            (0.033333, 0.533)]:   # BUY
        before = 0.10
        after = before / ratio * residual
        df = _series(before, after)
        adjustable, unreconciled, _ = reconcile_splits(
            df, [(_split_on(df), ratio)])
        assert len(adjustable) == 1 and not unreconciled, (
            f"ratio={ratio} residual={residual} was called unreconciled; "
            f"this is ordinary movement across the event window")


def test_the_real_faults_are_caught():
    """Every anomaly beyond a factor of two in the measured population."""
    for code, ratio, residual in [("VTA", 0.025000, 0.0003),
                                  ("LIB", 0.050000, 0.033),
                                  ("G11", 0.100000, 0.090),
                                  ("RAP", 0.500000, 0.110),
                                  ("ROG", 1.250000, 2.500),
                                  ("CHM", 0.010000, 2.100)]:
        before = 0.10
        after = before / ratio * residual
        df = _series(before, after)
        adjustable, unreconciled, skipped = reconcile_splits(
            df, [(_split_on(df), ratio)])
        assert not adjustable, f"{code} was adjusted on a ratio that is wrong"
        assert len(unreconciled) == 1 or len(skipped) == 1, (
            f"{code} was neither withheld nor skipped")


def test_the_boundary_withholds_rather_than_guesses():
    """DTM sits at residual 0.481, just outside the band, and is withheld.

    That is the intended answer, not a casualty of a round number. At 0.48
    the stock either fell by half across the event or the ratio is wrong by
    half, and nothing in the data distinguishes them. The band cannot be
    widened to admit it without also admitting ROG at exactly 2.500, which
    is a real fault -- so the choice is which error to make at the margin,
    and withholding one correct return beats publishing one wrong one.
    """
    before = 0.10
    after = before / 0.066667 * 0.481
    df = _series(before, after)
    _, unreconciled, _ = reconcile_splits(df, [(_split_on(df), 0.066667)])
    assert len(unreconciled) == 1, (
        "the band was widened past the measured population; check that ROG "
        "at 2.500 is still caught before accepting this")


def test_the_band_is_symmetric_in_log_space():
    """A factor of two too large and a factor of two too small are the same
    error. An asymmetric band would catch consolidations and miss splits."""
    for residual in (RECONCILE_BAND * 1.01, 1.0 / (RECONCILE_BAND * 1.01)):
        before = 0.10
        after = before / 0.1 * residual
        df = _series(before, after)
        _, unreconciled, skipped = reconcile_splits(df, [(_split_on(df), 0.1)])
        assert len(unreconciled) == 1 or len(skipped) == 1, (
            f"residual {residual:.3g} was accepted as reconciling")


# ── The window, which is how MPP escaped the first measurement ──────────────

def test_the_step_may_sit_either_side_of_the_recorded_date():
    """MPP's price stepped on 2 March; the recorded split_date is 3 March.
    A reconciliation keyed to the exact date compares two post-event prices,
    finds no step, and concludes the series is continuous -- the one verdict
    that is certainly wrong."""
    df = _series(0.0011, 1.7200, split_day=300)
    # Record the split THREE days after the price actually moved.
    recorded = pd.Timestamp(df["date"].iloc[303]).date()
    _, unreconciled, _ = reconcile_splits(df, [(recorded, 0.025)])
    assert len(unreconciled) == 1, (
        "a split recorded a few days off the price step was not reconciled "
        "against it")


def test_an_event_outside_the_series_is_adjusted_not_withheld():
    """A split older than any price we hold cannot corrupt a window inside
    the series, and withholding for it would blank history for no reason."""
    df = _series(0.10, 0.10)
    ancient = date(1999, 1, 1)
    adjustable, unreconciled, _ = reconcile_splits(df, [(ancient, 0.1)])
    assert len(adjustable) == 1 and not unreconciled


def test_constants_are_what_the_population_showed():
    """Pinned so a later tweak is a deliberate act with this file to answer
    to, rather than a quiet adjustment that re-opens the defect."""
    assert RECONCILE_BAND == 2.0
    assert IMMATERIAL_FACTOR == 0.10


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
