"""
Calendar-anchored return and 52-week windows
============================================
A "1-year return" is a claim about a year. It was computed as
`close / close.shift(252)` -- 252 ROWS back, not 252 days -- and a row is a
day the stock traded, not a day that passed.

For a stock that trades every session the two agree, which is why this
survived: BHP has ~252 rows in a year and the number is right. For anything
that trades intermittently they diverge without any signal that they have.
MRD, at the top of the served screener on 27 Oct 2026 with +1,595%, had 206
rows in 400 calendar days; its 252nd row back fell on 2025-07-17, so the
"one-year return" measured 467 days. Across the universe, 576 of 1,770
stocks with enough history spanned more than 380 days and 219 more than 450.

The same defect sat in `high_52w` / `low_52w` (`rolling(252)`), and through
them in `pct_from_52w_high`, `pct_from_52w_low`, `new_52w_high` and
`new_52w_low`.

`return_ytd` was never affected: it already anchored on dates, ten lines
below the block this replaces. The file held both conventions.

Not changed here, because row-based is correct for them:
  return_1d   the previous close IS the previous close
  roc_10/20   rate of change over N periods, by definition
  hv_20d/60d  volatility over N observations, by definition

What this cannot do
-------------------
Find a price that does not exist. Where a stock has no quote near the start
of the window, there is no comparable price and therefore no return --
`None`, which the governed layer renders as unavailable. Taking the nearest
available price instead would produce a well-formed number measuring an
unknown period, which is the defect being fixed, not a workaround for it.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

#: Window length in calendar days, and how stale the opening price may be.
#:
#: The grace absorbs weekends and public holidays: the anchor is the last
#: close at or before `date - length`, and on an ordinary week that is one to
#: four days earlier. It is NOT a staleness allowance. A wide grace would
#: re-admit exactly what this module exists to stop -- at 20% of the window,
#: a "1-year return" could legitimately span 14 months -- so it is bounded in
#: absolute days and kept small relative to the window it guards.
#:
#: 1w is tightest because a 7-day grace on a 7-day window would double it.
#:
#: return_1y's 7 is MEASURED. Over the 2,093 served stocks on 28 Oct 2026,
#: 1,567 had any close before their one-year target date, and of those 1,554
#: anchored within three days. Two sat at 4-7 days, one at 15-30, and ten
#: beyond 90 -- genuinely stale names, withheld at any grace worth having.
#: The 8-14 day bucket was EMPTY, so the 14 originally written here bought
#: nothing and cost the thing this module exists to prevent: at 14 days a
#: "one-year return" may span a year and a fortnight for no measured gain.
#: Seven is where the last real stock sits.
#:
#: 3m and 6m remain PROVISIONAL at 14. Their distributions have not been
#: measured, and the 1-year result does not transfer: a shorter window has
#: fewer chances for a thin stock to have traded near its target, so its
#: gap distribution could be wider, not narrower. The measurement is on the
#: backlog and belongs on a replica or a dump -- taking it against the live
#: database is what caused the 28 Oct outage.
#:
#: 1w's 4 and 1m's 7 are unchanged. Four is the exchange calendar itself --
#: Good Friday through Easter Monday -- and 1w is tightest because a 7-day
#: grace on a 7-day window would double it.
WINDOWS: dict[str, tuple[int, int]] = {
    "return_1w": (7, 4),
    "return_1m": (30, 7),
    "return_3m": (91, 14),
    "return_6m": (182, 14),
    "return_1y": (365, 7),
}

#: The high/low windows. Same length, but the grace does a DIFFERENT job and
#: the measurement above does not govern it. There it is an anchor gap: how
#: stale the single opening price may be. Here it is a minimum-history
#: threshold: a stock publishes no 52-week high until its series spans
#: 365 - 14 = 351 days. Nothing is read from the boundary, so a wider value
#: cannot misstate a period -- it only decides how early a newly listed stock
#: gets a high at all. Narrowing it to 7 would withhold slightly longer for
#: no gain in correctness, so it stays at 14 deliberately, not by omission.
HIGH_LOW_DAYS = 365
HIGH_LOW_GRACE = 14


def anchor_positions(dates: pd.Series, length_days: int,
                     grace_days: int) -> np.ndarray:
    """Row index of each row's opening price, or -1 where there is none.

    The anchor is the LAST row at or before `date - length_days`. Taking the
    last one rather than the nearest matters: the nearest could sit after the
    target, shortening the window instead of lengthening it, and a return
    that silently measures less than it claims is no better than one that
    measures more.
    """
    idx = pd.DatetimeIndex(pd.to_datetime(pd.Series(dates).reset_index(drop=True)))
    if len(idx) == 0:
        return np.zeros(0, dtype=int)

    targets = idx - pd.Timedelta(days=length_days)
    # searchsorted on the right, minus one: the last position whose date is
    # <= target. -1 means every row is newer than the target, i.e. the series
    # does not reach back far enough.
    pos = idx.searchsorted(targets, side="right") - 1

    found = pos >= 0
    safe = np.where(found, pos, 0)
    gap_days = (targets - idx[safe]).days.to_numpy()
    close_enough = gap_days <= grace_days

    return np.where(found & close_enough, pos, -1)


def window_return(close: pd.Series, dates: pd.Series, length_days: int,
                  grace_days: int) -> pd.Series:
    """`close / close_at_anchor - 1`, or NaN where no anchor qualifies."""
    pos = anchor_positions(dates, length_days, grace_days)
    c = pd.Series(close).reset_index(drop=True).astype(float).to_numpy()

    base = np.where(pos >= 0, c[np.clip(pos, 0, None)], np.nan)
    # A zero opening price is not a 100% gain, it is an unusable denominator.
    base = np.where(base == 0, np.nan, base)

    return pd.Series(c / base - 1.0, index=pd.Series(close).index)


def rolling_extreme(values: pd.Series, dates: pd.Series, how: str,
                    length_days: int = HIGH_LOW_DAYS,
                    grace_days: int = HIGH_LOW_GRACE) -> pd.Series:
    """Max or min over a CALENDAR window, NaN until the history covers it.

    `rolling(252)` yielded NaN until 252 rows existed, which for a thin stock
    meant well over a year and for a suspended one meant never. A calendar
    window has the opposite failure available to it -- `rolling("365D")` has
    `min_periods=1`, so a stock listed last Tuesday would be handed a
    "52-week high" drawn from four days. Neither is acceptable, so the window
    is calendar-based AND the row is blank until the series actually spans
    it.
    """
    if how not in ("max", "min"):
        raise ValueError(f"how must be 'max' or 'min', got {how!r}")

    v = pd.Series(values).reset_index(drop=True).astype(float)
    idx = pd.DatetimeIndex(pd.to_datetime(pd.Series(dates).reset_index(drop=True)))
    s = pd.Series(v.to_numpy(), index=idx)

    window = f"{length_days}D"
    rolled = s.rolling(window).max() if how == "max" else s.rolling(window).min()

    # Blank every row whose history does not reach back a full window.
    covered = (idx - idx[0]).days.to_numpy() >= (length_days - grace_days)
    out = np.where(covered, rolled.to_numpy(), np.nan)

    return pd.Series(out, index=pd.Series(values).index)
