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

#: A day-over-day move in close/adjusted_close beyond this is a corporate
#: action, not a price move. Ordinary ex-dividend steps on the ASX sit far
#: below it; the measured population of 222 discontinuities over 18 months
#: was found at this threshold.
DISCONTINUITY = 0.10

#: How far from a recorded split date a discontinuity may sit and still be
#: considered explained by it. Ex-dates, announcement dates and the date the
#: provider restates the series do not always coincide.
SPLIT_WINDOW_DAYS = 5


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
    for split_date, ratio in splits:
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


def unexplained_discontinuities(df: pd.DataFrame, splits) -> pd.Series:
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
    if n < 2 or "adj_close" not in df.columns or "close" not in df.columns:
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
    for split_date, ratio_value in splits:
        if not ratio_value or ratio_value <= 0:
            continue
        sd = pd.Timestamp(split_date)
        near = (dates >= sd - pd.Timedelta(days=SPLIT_WINDOW_DAYS)) & \
               (dates <= sd + pd.Timedelta(days=SPLIT_WINDOW_DAYS))
        explained |= near.to_numpy()

    return broke & ~explained


#: Metric -> lookback in rows. A metric is wrong for its whole window after
#: an unadjustable event, not merely on the day of it.
CONTAMINATED_BY_WINDOW = {
    "daily_return": 1, "log_return": 1, "gap_pct": 1,
    "return_1d": 1, "return_1w": 5, "return_1m": 21,
    "return_3m": 63, "return_6m": 126, "return_1y": 252,
}


def withhold_contaminated_metrics(df: pd.DataFrame, splits) -> tuple:
    """Blank the metrics whose window spans an event we cannot adjust.

    Returns (df, n_withheld). The count is returned rather than logged here
    so the caller can report it as a run statistic — a repair that silently
    removes numbers is as hard to audit as one that silently invents them.
    """
    flags = unexplained_discontinuities(df, splits)
    if not flags.any():
        return df, 0

    withheld = 0
    for column, periods in CONTAMINATED_BY_WINDOW.items():
        if column not in df.columns:
            continue
        before = df[column].notna().sum()
        df[column] = withhold_spanning_windows(df[column], flags, periods)
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
