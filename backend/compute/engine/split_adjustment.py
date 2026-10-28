"""
Split-adjusting a price series, and knowing when not to
======================================================
Every technical indicator in `technical_compute` was computed from the raw
close. A 1-for-10 consolidation multiplies the raw price by ten, so a stock
that lost 72% of its value showed a **+999%** one-year return — Metro
Performance Glass did exactly that, and 104 other stocks carried a wrong
1-year return on the same day.

The direction matters: consolidations INFLATE returns, and companies
consolidate because they have collapsed. So the defect took the exchange's
worst performers and put them at the top of "best 1-year return".

Two mechanisms here, for two different populations.

ADJUST what we can explain
--------------------------
`market.splits` records the ratio. Prices before a split are restated into
post-split terms, so the series is continuous and every window spanning it
measures the price change rather than the share-count change.

    ratio 0.1  =  1-for-10 consolidation  =  price x10 on the day
    historical prices before it are multiplied by 1/0.1 = 10

Applied to open, high, low and close TOGETHER, and to volume inversely.
Adjusting close alone would leave an adjusted close beside raw highs and
break ATR, the Bollinger bands and the 52-week range — the finding called
this out explicitly.

WITHHOLD what we cannot
-----------------------
78 persistent discontinuities in the last 18 months have no recorded split:
capital returns, rights issues and special dividends.
`market.corporate_events` is empty, so there is nothing to adjust them with.

For those, a return is not computed. It is published as unknown, because an
absent number sends someone to check and a wrong number does not. Same
decision as withholding AXJO in v11.2.18.

Detection needs only the price series; explanation is what needs corporate
actions. So we can withhold accurately long before we can correct.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# One definition of a window, shared by the metric and by the guard that
# withholds it. return_windows imports nothing from this module, so the
# dependency runs one way only.
from compute.engine.return_windows import ALL_WINDOWS, anchor_positions

#: A day-over-day move in close/adjusted_close beyond this is a corporate
#: action, not a price move. Ordinary ex-dividend steps on the ASX sit far
#: below it; the measured population of 222 discontinuities over 18 months
#: was found at this threshold.
DISCONTINUITY = 0.10

#: How far from a recorded split date a discontinuity may sit and still be
#: considered explained by it. Ex-dates, announcement dates and the date the
#: provider restates the series do not always coincide.
SPLIT_WINDOW_DAYS = 5


#: A recorded ratio this close to 1.0 changes the share count by less than
#: this fraction. Bonus issues and DRP adjustments land here. Applying one is
#: within the noise; withholding a year of returns over one would be wildly
#: disproportionate, so these are skipped and nothing is withheld for them.
IMMATERIAL_FACTOR = 0.10

#: How far the observed price step may differ from the recorded ratio and
#: still count as explained by it.
#:
#: Deliberately loose. The boundary prices sit days apart, so ordinary price
#: movement is inside this number, and most of these companies are micro-caps
#: consolidating alongside a capital raise -- a 30% move across the event is
#: routine. The population measured on 27 Oct 2026 separates cleanly at a
#: factor of two: genuine noise sat between 0.48 and 1.25, while every real
#: fault was beyond 2x or below 0.5x (MPP at 39, VTA at 0.0003, LIB at 0.03,
#: ROG at 2.5). A tighter band would flag volatility as corruption and
#: withhold hundreds of correct returns.
RECONCILE_BAND = 2.0


def _boundary_prices(df: pd.DataFrame, split_date,
                     window: int = SPLIT_WINDOW_DAYS) -> tuple:
    """Last close before the split window, and first close after it.

    The window is the same one the detector uses: ex-dates, announcement
    dates and the date the provider restates the series do not always
    coincide, so a price taken on the recorded date itself may already be
    the post-event one. MPP is exactly that case -- its price stepped the
    day BEFORE the recorded split_date, which is how a reconciliation keyed
    to the exact date missed it entirely.
    """
    if "date" not in df.columns or "close" not in df.columns or df.empty:
        return None, None

    dates = pd.to_datetime(df["date"])
    sd = pd.Timestamp(split_date)
    close = pd.to_numeric(df["close"], errors="coerce")

    before = close[(dates < sd - pd.Timedelta(days=window)) & close.notna()]
    after = close[(dates > sd + pd.Timedelta(days=window)) & close.notna()]
    if before.empty or after.empty:
        return None, None

    b, a = float(before.iloc[-1]), float(after.iloc[0])
    return (b, a) if b > 0 and a > 0 else (None, None)


#: A series whose whole span around an event moves less than this has not
#: really traded. Deliberately tiny: this is meant to catch a price that is
#: literally unchanged, not a quiet one. A genuinely dull stock still prints
#: more variation than 1% across two months.
FLAT_TOLERANCE = 0.01

#: Rows either side of the event to judge trading by. Wide enough that a
#: suspension around the event does not look like a flat series, narrow
#: enough to describe the event's own neighbourhood.
FLAT_WINDOW_DAYS = 60


def _is_flat(df: pd.DataFrame, split_date,
             window: int = FLAT_WINDOW_DAYS) -> bool:
    """Did the price fail to move at all around this event?

    Used to tell "the split was already applied, so there is no step" from
    "nothing traded, so there could not have been a step". Only the first is
    a reason to skip a split; the second is a reason to withhold.
    """
    if "date" not in df.columns or "close" not in df.columns or df.empty:
        return False

    dates = pd.to_datetime(df["date"])
    sd = pd.Timestamp(split_date)
    near = (dates >= sd - pd.Timedelta(days=window)) & \
           (dates <= sd + pd.Timedelta(days=window))

    close = pd.to_numeric(df["close"], errors="coerce")[near.to_numpy()]
    close = close[close.notna() & (close > 0)]
    if len(close) < 2:
        # Too few prices to judge. Treat as flat: an event we cannot see the
        # neighbourhood of is not one we can declare already handled.
        return True

    return bool(float(close.max()) / float(close.min()) - 1.0
                < FLAT_TOLERANCE)


def reconcile_splits(df: pd.DataFrame, splits) -> tuple:
    """Decide, per split, whether the record explains what the prices did.

    Returns (adjustable, unreconciled, skipped). Each entry is
    (split_date, ratio, residual).

    THE DEFECT THIS EXISTS FOR
    --------------------------
    Until v11.2.58 a recorded split suppressed the discontinuity detector
    merely by existing: any step within SPLIT_WINDOW_DAYS of one was marked
    explained, without ever checking that the ratio accounted for it.

    MPP showed what that costs. A 1-for-40 was recorded, so the detector
    stayed silent -- but the price went from 0.0011 to 1.72, a factor of
    1,564. The recorded ratio explained 40 of it. The remaining 39x flowed
    into return_1y as +2150%, on a stock that had collapsed, and sat at the
    top of "best 1-year return" because consolidations inflate returns and
    companies consolidate when they have collapsed.

    So the rule is no longer "is there a record" but "does the record
    reconcile", with three outcomes:

      ADJUST       the step matches the ratio
      SKIP         there is no step to explain -- the series is already
                   continuous, so the record is a duplicate or was applied
                   upstream. Adjusting would CREATE a discontinuity in clean
                   data, which is worse than the bug being fixed. NTM has
                   two 1-for-15 records six days apart; applying both would
                   multiply by 225.
      WITHHOLD     there is a step and the ratio does not account for it.
                   We cannot correct it -- deriving a factor from the price
                   move would be inventing a corporate action out of a price
                   change -- so the affected windows publish as unknown.

    A note on what is NOT attempted: no attempt is made to decide whether
    the price series or the split record is the wrong one. For MPP either
    could be. The honest output is the same either way.
    """
    adjustable, unreconciled, skipped = [], [], []

    for split_date, ratio in splits:
        if not ratio or ratio <= 0:
            skipped.append((split_date, ratio, None))
            continue

        factor = 1.0 / float(ratio)
        if abs(factor - 1.0) < IMMATERIAL_FACTOR:
            skipped.append((split_date, ratio, None))
            continue

        before, after = _boundary_prices(df, split_date)
        if before is None:
            # No price either side -- the event is outside the series, so it
            # cannot corrupt a window inside it. Adjusting is harmless and
            # keeps older history consistent.
            adjustable.append((split_date, ratio, None))
            continue

        observed = after / before
        residual = observed / factor

        if 1.0 / RECONCILE_BAND <= residual <= RECONCILE_BAND:
            adjustable.append((split_date, ratio, residual))
        elif 1.0 / RECONCILE_BAND <= observed <= RECONCILE_BAND:
            # No step -- but that only means the split was already applied
            # if the series was TRADING. A price that has not moved at all
            # cannot show a step, so its stillness is the absence of
            # evidence rather than evidence of continuity.
            #
            # v11.2.59 shipped this rule citing PGL and HXL. That citation
            # was wrong and is retracted here. Both of their splits RECONCILE
            # exactly -- HXL's 1-for-4 gives 0.0130 x 4 = 0.0520, today's
            # price -- so they never reach this branch, and their 0.000000
            # returns are correct rather than the defect they were presented
            # as. The -0.9333 and -0.9000 those replaced were the wrong
            # numbers.
            #
            # The rule stands on its own terms, which is why it was kept:
            # `observed == 1.0` means "no step was seen", and a series that
            # never moves cannot show one. Reading that as "the split is
            # already in the series" infers continuity from an instrument
            # that produced no evidence either way.
            #
            # Honest about its population: no production case is currently
            # known to take this branch. It is a conservative default, not a
            # repair of an observed defect, and if it still has no population
            # at the next review it should be reconsidered rather than kept
            # on the strength of sounding right. See the memory rule on
            # guards losing their population.
            if _is_flat(df, split_date):
                unreconciled.append((split_date, ratio, residual))
            else:
                skipped.append((split_date, ratio, residual))
        else:
            unreconciled.append((split_date, ratio, residual))

    return adjustable, unreconciled, skipped


def cumulative_adjustment(dates: pd.Series, splits) -> np.ndarray:
    """Factor to multiply each row's price by, to restate it in today's terms.

    `splits` is an iterable of (split_date, ratio). A row dated strictly
    BEFORE a split is multiplied by 1/ratio; the split date itself already
    carries the new price, so it is not adjusted.

    The most recent rows always come out at 1.0, which is why today's quoted
    price is never altered by this.
    """
    factor = np.ones(len(dates), dtype=float)
    if len(dates) == 0:
        return factor

    d = pd.to_datetime(pd.Series(dates).reset_index(drop=True))
    for split_date, ratio in ((s[0], s[1]) for s in splits):
        # A ratio of zero or None cannot be inverted. Skipping it leaves the
        # series unadjusted across that event, which the withholding pass
        # below then catches as an unexplained discontinuity — so a bad
        # ratio degrades to "unknown", never to a silently wrong number.
        if not ratio or ratio <= 0:
            continue
        factor[(d < pd.Timestamp(split_date)).to_numpy()] *= 1.0 / float(ratio)
    return factor


def apply_split_adjustment(df: pd.DataFrame, splits) -> pd.DataFrame:
    """Add `*_adj` columns restating the series in post-split terms.

    The raw columns are left untouched: what is DISPLAYED as a historical
    price stays as it was quoted on the day, while what is COMPUTED uses the
    continuous series. Mixing the two is the defect, not the fix.
    """
    out = df.copy()
    factor = cumulative_adjustment(out["date"], splits)
    out["adj_factor"] = factor

    for col in ("open", "high", "low", "close"):
        if col in out.columns:
            out[f"{col}_adj"] = out[col].astype(float) * factor

    if "volume" in out.columns:
        # Inversely: ten times as many shares existed before a 1-for-10, so
        # the comparable volume is volume/factor. Dollar volume
        # (price x volume) is then invariant across the event, which is what
        # makes liquidity measures comparable either side of it.
        out["volume_adj"] = out["volume"].astype(float) / factor

    return out


def unexplained_discontinuities(df: pd.DataFrame, splits,
                                unreconciled=()) -> pd.Series:
    """Boolean per row: a corporate action happened here that we cannot adjust.

    Detected from close/adjusted_close — a step in that ratio means the
    provider restated the series for an event. Steps within
    SPLIT_WINDOW_DAYS of a recorded split are excluded: those are adjusted
    above.

    Ex-dividend steps are NOT withheld, deliberately. A dividend-driven
    price drop is a real market movement that a price return should include;
    only events that change the share count corrupt the series. The 10%
    threshold leaves ordinary dividends well clear.
    """
    n = len(df)
    flags = pd.Series(np.zeros(n, dtype=bool), index=df.index)
    if n < 2:
        return flags

    # A split whose ratio does not reconcile with the price step is an
    # unexplained event regardless of what the close/adj_close ratio shows.
    # This runs BEFORE the early return below, because the detector's own
    # evidence is the provider's adjustment -- and for MPP the provider
    # adjusted by 39 when the series moved by 1,564, so its series looked
    # perfectly consistent while being wrong. An explanation that does not
    # reconcile must flag the event even when the detector cannot see it.
    if len(unreconciled):
        dates_all = pd.to_datetime(df["date"])
        for split_date, _ratio in ((s[0], s[1]) for s in unreconciled):
            sd = pd.Timestamp(split_date)
            near = (dates_all >= sd - pd.Timedelta(days=SPLIT_WINDOW_DAYS)) & \
                   (dates_all <= sd + pd.Timedelta(days=SPLIT_WINDOW_DAYS))
            flags |= near.to_numpy()

    # A step in the series we actually compute from, which no split
    # explains. See raw_price_discontinuities.
    flags |= raw_price_discontinuities(df)

    if "adj_close" not in df.columns or "close" not in df.columns:
        return flags

    close = df["close"].astype(float)
    adj = df["adj_close"].astype(float)
    ratio = close.where(adj.notna() & (adj != 0)) / adj.replace(0, np.nan)

    step = ratio / ratio.shift(1)
    broke = (step - 1.0).abs() > DISCONTINUITY
    broke = broke.fillna(False)

    if not broke.any():
        return flags

    dates = pd.to_datetime(df["date"])
    explained = pd.Series(np.zeros(n, dtype=bool), index=df.index)
    for split_date, ratio_value in ((s[0], s[1]) for s in splits):
        if not ratio_value or ratio_value <= 0:
            continue
        sd = pd.Timestamp(split_date)
        near = (dates >= sd - pd.Timedelta(days=SPLIT_WINDOW_DAYS)) & \
               (dates <= sd + pd.Timedelta(days=SPLIT_WINDOW_DAYS))
        explained |= near.to_numpy()

    # `flags` already carries the unreconciled events. They must survive the
    # mask below: an unreconciled split is itself a recorded split, so it
    # appears in `explained` and would otherwise erase its own flag.
    return flags | (broke & ~explained)


#: A single-day move beyond this factor, in the series we compute from, is
#: treated as a corporate action we have no record of.
#:
#: Set from the measured population on 27 Oct 2026. Excluding steps near a
#: recorded split, the unexplained events in 400 days were:
#:
#:     2-5x    59 events across 57 stocks
#:     5-8x     5 events across  5 stocks
#:     8-11x    3 events across  2 stocks
#:    14-17x    1 event
#:     >=20x   10 events across  5 stocks
#:
#: The shape is what sets the threshold. Below 5x, 57 distinct stocks with
#: one event each -- scattered, no repeats, which is what news-driven moves
#: look like. A takeover bid or a drill result can double a micro-cap in a
#: day, and that is a real return, the most interesting one on the screener.
#: Withholding those to catch share-count changes would destroy correct
#: numbers wholesale.
#:
#: Above 5x the population collapses to ~13 stocks, and they look like
#: share-count changes: ID8 at 159x, IS3 at 15x, ACS at 7.1x, none with a
#: split on record.
#:
#: The cost of the choice, stated plainly: a genuine five-bagger in ONE DAY
#: is withheld. That is rare enough, and conspicuous enough when it happens,
#: to be the better error than publishing a consolidation as a 15,000%
#: return.
UNEXPLAINED_STEP = 5.0


def _computed_series(df: pd.DataFrame) -> pd.Series:
    """The closes the indicators are actually built from.

    `close_adj` when split adjustment has run, raw `close` otherwise. Using
    the computed series is what makes the detector below need no exclusion
    list: a reconciled split has already been removed from it, so anything
    still stepping is unexplained BY CONSTRUCTION rather than by a date
    comparison that could drift out of step with the adjustment.
    """
    col = "close_adj" if "close_adj" in df.columns else "close"
    return pd.to_numeric(df[col], errors="coerce")


def raw_price_discontinuities(df: pd.DataFrame) -> pd.Series:
    """Steps in the price series itself, with no corporate action to explain them.

    WHY THIS EXISTS
    ---------------
    Both earlier detectors need a document. `unexplained_discontinuities`
    reads the provider's close/adjusted_close ratio -- it sees only what
    EODHD chose to adjust. `reconcile_splits` needs a split record to check.
    Where there is no record AND the provider did nothing, both are blind,
    and the share-count change flows into return_1y untouched.

    ID8 is the case: its price stepped 159x on 2026-09-24, with no split in
    market.splits and adjusted_close moving exactly in step with close. It
    published a +10,455% one-year return, at the top of the screener, after
    v11.2.58 had already run over it.

    So this detector reads the only evidence left -- the price series.

    WHAT IT DELIBERATELY DOES NOT DO
    --------------------------------
    It does not try to work out the factor and correct the series. The step
    size is not a ratio: it is the corporate action and the day's trading
    mixed together, and no amount of arithmetic separates them. Deriving a
    factor from it would be inventing a corporate action out of a price
    move. The windows are withheld, exactly as for an unreconciled split.
    """
    n = len(df)
    flags = pd.Series(np.zeros(n, dtype=bool), index=df.index)
    if n < 2:
        return flags

    close = _computed_series(df)
    step = close / close.shift(1)
    broke = ((step > UNEXPLAINED_STEP) |
             (step < 1.0 / UNEXPLAINED_STEP)).fillna(False)
    # A zero or missing price is absence of a quote, not a 100% collapse.
    broke &= close.notna() & (close > 0) & \
        close.shift(1).notna() & (close.shift(1) > 0)
    return flags | broke.to_numpy()


#: Metric -> lookback in rows. A metric is wrong for its whole window after
#: an unadjustable event, not merely on the day of it.
#: Metrics whose lookback really is a row count, and for which a row count is
#: the correct unit: each compares a close with its immediate predecessor.
CONTAMINATED_BY_ROWS = {
    "daily_return": 1, "log_return": 1, "gap_pct": 1, "return_1d": 1,
}

#: The period returns are withheld over their OWN window, read from
#: ALL_WINDOWS rather than restated here.
#:
#: This was previously a second declaration in rows -- return_1y: 252,
#: return_6m: 126 and so on -- and it stopped matching the thing it guards
#: the moment v11.2.62 anchored the returns on the calendar. A return
#: measured over 365 days was being withheld over 252 rows: for a stock
#: trading every weekday those are nearly the same span, and for anything
#: thinner they are not. A guard that defines the window differently from the
#: metric it protects will disagree with it on exactly the stocks the metric
#: was hardest to get right for.
#:
#: Worse, a hand-maintained list cannot acquire a new window. The ten
#: multi-year horizons added in this release would have computed with no
#: withholding at all, which is how yearly_compute came to publish
#: return_3y = 1449.0 for JNS.
#:
#: So the window comes from one place. Adding a horizon to ALL_WINDOWS gives
#: it withholding automatically, and removing one cannot leave an orphaned
#: guard behind.
CONTAMINATED_BY_WINDOW = {name: offset_grace
                          for name, offset_grace in ALL_WINDOWS.items()}


def withhold_contaminated_metrics(df: pd.DataFrame, splits,
                                  unreconciled=()) -> tuple:
    """Blank the metrics whose window spans an event we cannot adjust.

    Returns (df, n_withheld). The count is returned rather than logged here
    so the caller can report it as a run statistic — a repair that silently
    removes numbers is as hard to audit as one that silently invents them.
    """
    flags = unexplained_discontinuities(df, splits, unreconciled)
    if not flags.any():
        return df, 0

    withheld = 0

    for column, periods in CONTAMINATED_BY_ROWS.items():
        if column not in df.columns:
            continue
        before = df[column].notna().sum()
        df[column] = withhold_spanning_windows(df[column], flags, periods)
        withheld += int(before - df[column].notna().sum())

    for column, (offset, grace_days) in CONTAMINATED_BY_WINDOW.items():
        if column not in df.columns:
            continue
        before = df[column].notna().sum()
        df[column] = withhold_spanning_calendar_windows(
            df[column], flags, df["date"], offset, grace_days)
        withheld += int(before - df[column].notna().sum())

    # YTD has no fixed window: it runs from the last close of the previous
    # calendar year, so anything from the first flagged row of the current
    # year onwards is contaminated.
    if "return_ytd" in df.columns and flags.any():
        years = pd.to_datetime(df["date"]).dt.year
        for year in years[flags].unique():
            in_year = (years == year)
            first_bad = df.index[in_year & flags].min()
            affected = in_year & (df.index >= first_bad)
            before = df.loc[affected, "return_ytd"].notna().sum()
            df.loc[affected, "return_ytd"] = np.nan
            withheld += int(before)

    return df, withheld


def withhold_unrepresentable(df: pd.DataFrame, limits: dict) -> tuple:
    """NULL values a column cannot physically hold, rather than failing the insert.

    A deeply consolidated stock restates to astronomical historical prices.
    JAV has five consolidations — 1-for-35, 1-for-15, 1-for-30, 1-for-10 and
    1-for-31 — compounding to a factor of ~4.88 million, so its 90.42 high
    becomes ~441 million against a NUMERIC(12,4) ceiling of 10^8.

    The arithmetic is right and the column is too small. Both facts are
    permanent, so the honest value is "unknown":

      - a wider column would only move the ceiling, and the next stock with
        six consolidations would hit it
      - clamping would publish a number that is definitely wrong
      - raising is what it did before, and psycopg2 aborts the whole
        execute_values batch — one JAV silently discarded thirteen correct
        stocks and left their old, wrong returns in place

    `limits` is read from information_schema rather than hardcoded, so a
    column widened or narrowed in a migration changes this automatically.
    """
    withheld = 0
    for column, max_abs in limits.items():
        if column not in df.columns:
            continue
        values = pd.to_numeric(df[column], errors="coerce")
        # >= because NUMERIC(p,s) admits strictly less than 10**(p-s).
        too_big = values.abs() >= max_abs
        if too_big.any():
            withheld += int(too_big.sum())
            df.loc[too_big, column] = np.nan
    return df, withheld


def withhold_spanning_calendar_windows(values: pd.Series, flags: pd.Series,
                                       dates: pd.Series, offset,
                                       grace_days: int) -> pd.Series:
    """NaN out any value whose CALENDAR window contains an unexplained event.

    The window is the one the return itself used -- same anchor_positions(),
    same offset, same grace -- so the guard cannot disagree with the metric
    about which prices were compared.

    The contaminated interval is (anchor, row]: an event ON the anchor day is
    not contamination, because the anchor close and every close after it are
    already on the post-event basis and the ratio between them is sound. An
    event after the anchor mixes two bases and the ratio is not a return.

    A row with NO anchor is not clean, it is unestablishable: the window
    reaches past the start of the series, so the whole series up to that row
    is the window. Contamination there is any flag at or before the row --
    "at or before", never after, because a future event cannot retroactively
    contaminate a past comparison and treating it as if it could is how a
    guard acquires lookahead.

    Under the real producer such a row is already NaN, so this costs nothing
    in production. It matters because the column can be populated by
    something other than this window definition, and then silence would be a
    contaminated number kept by a guard that declined to look at it.
    """
    if not flags.any():
        return values

    pos = anchor_positions(dates, offset, grace_days)
    f = pd.Series(flags).reset_index(drop=True).astype(bool).to_numpy()

    # cum[k] = number of flagged rows strictly before k, so the count inside
    # (pos, i] is cum[i + 1] - cum[pos + 1].
    cum = np.concatenate([[0], np.cumsum(f)])
    i = np.arange(len(f))

    contaminated = np.zeros(len(f), dtype=bool)
    anchored = pos >= 0
    contaminated[anchored] = (
        cum[i[anchored] + 1] - cum[pos[anchored] + 1]) > 0
    # No anchor: the window is everything up to this row.
    contaminated[~anchored] = cum[i[~anchored] + 1] > 0

    return values.where(~pd.Series(contaminated, index=values.index))


def withhold_spanning_windows(values: pd.Series, flags: pd.Series,
                              periods: int) -> pd.Series:
    """NaN out any value whose lookback window contains an unexplained event.

    `periods` is the window the metric looks back over, in rows. A return
    over 252 rows is wrong for 252 rows after the event, not merely on the
    day of it — which is why this spans rather than points.
    """
    if periods <= 0 or not flags.any():
        return values
    # A window of N rows ending at row i covers rows i-N+1 .. i, and the
    # event affects the comparison whenever it lies inside it.
    spanned = flags.rolling(window=periods, min_periods=1).max().astype(bool)
    return values.where(~spanned)
