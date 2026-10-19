# ASX20, AXFJ and AXMJ carry the wrong series for 13 months

**Found:** 19 October 2026, while verifying EODHD symbol mappings
**Status:** OPEN — repair decided (fix history before switching source)
**Severity:** stored history is wrong; served headline numbers are not

> **This document was corrected on first measurement.** The initial version,
> written from a 400-day window, said these series were wrong "before June
> 2026" and that the start of the contamination was unmeasured and might
> reach first ingestion. A 2000-day window shows the opposite: four years of
> correct history precede a bounded 13-month window. The earlier conclusion
> was not merely incomplete, it was wrong about the shape of the defect, and
> it was wrong because the window could not see past itself — the same error
> this codebase already has a rule for.

## What was measured

Agreement between each stored index series and every Australian index EODHD
lists (35 candidates, each fetched once), by calendar month, over 2000 days.
Median level difference; outliers counted separately.

Six of the nine targets agree with their correctly-named symbol across the
entire 1,351-session history at `0.00000%`. Three show an identical,
bounded anomaly:

| Code | 2021-05 … 2025-04 | 2025-05 … 2026-05 | 2026-06 … now |
|---|---|---|---|
| ASX20 | `0.00000%` | ≈ 44–47% | `0.00000%` |
| AXFJ | `0.00000%` | ≈ 31,000% | `0.00000%` |
| AXMJ | `0.00000%` | ≈ 138,000% | `0.00000%` |

Same start month, same end month, three independent series. Roughly 265
sessions each, about 19.6% of their stored history.

## What the window contains

**ASX20 held the All Ordinaries.** During the window `AORD.INDX` matches it
exactly while `ATLI.INDX` (the real S&P/ASX 20) does not. On 2026-01-21 the
stored value is 9,108.6 against a true ASX 20 of 4,750.0.

**AXFJ and AXMJ held values that are not index levels.** 29.68 on 2025-08-18
against a true 9,510.3; 16.50 on 2026-02-16 against a true 23,764.2 —
roughly 1/320 and 1/1,440. What they actually were is **not established**.
The S&P/ASX 200 VIX is the nearest candidate by magnitude and is not an
exact match, so it is a resemblance, not an identification.

## Why the served numbers are still correct

`index_prices.run()` calls `compute_rows(df)` on the **freshly fetched**
frame, so `return_1y`, `return_ytd` and the 52-week extremes are derived
from the provider's current history rather than from stored rows. Measured
on 19 Oct 2026, every one is plausible:

    ASX20   return_1y  0.0326   52w 4603.70 – 5390.80
    AXFJ    return_1y -0.0467
    AXMJ    return_1y  0.1709

A one-year window straddles the bad period and the figure is unaffected,
because the figure never reads the bad rows.

**The chart does.** `/indices/{code}` plots stored history, so ASX20, AXFJ
and AXMJ show the wrong series for 13 months with a step at each boundary.
That is the live customer-visible defect.

## Mechanism: consistent, not proven

The configured tickers have never changed since the original ingestion
commit (`fb5846f`), no commit between May and July 2026 touches the mapping,
and `index_prices.py` is the only writer of `market.index_prices` in this
repository.

The explanation consistent with every observation is one this codebase has
already documented for fund prices: **append-only persistence freezes each
row at its fetch-time basis.** If the provider served the wrong series
during that window and has since corrected its own history, our rows stay
frozen at what was served then, while a fetch today returns correct values
for the same dates. That is exactly the pattern observed.

It is **not proven**. No provider statement has been obtained, and an
earlier finding here inferred an external writer from an absence of local
commits and was wrong to. Recorded as the leading explanation, not a cause.

## The repair

Bounded and verifiable, which the earlier unbounded reading would not have
been:

- **Scope:** ASX20, AXFJ, AXMJ, dates 2025-05-01 … 2026-05-31. ~265 rows
  each, ~800 total. Nothing outside the window is touched.
- **Source:** EODHD, which matches our own stored history exactly on both
  sides of the window — so it is not a new series being spliced in, it is
  the series we already publish, for the dates where ours is wrong.
- **Nature:** a deliberate historical overwrite of rows known to be wrong.
  This is a documented exception to forward-only, which exists to stop one
  provider silently rewriting another's rows. Silence and ignorance are what
  that rule guards against, and neither applies here.
- **Verification:** re-run the monthly agreement after the repair. Every
  month must read `0.00000%`, and the six clean series must be unchanged.

## Open

1. Derived values stored on rows INSIDE the window are frozen too, and were
   computed from contaminated frames. Repairing `close_price` does not
   repair them. Recompute, or withhold.
2. Whether any other series has a bounded window like this. Only these nine
   index codes were examined.
3. The same freezing applies to `market.fund_prices`. Unmeasured.

## Related

- `engineering_rule_verdict_from_filtered_view` — 120 days showed these as
  clean matches, 400 days showed a break at June, 2000 days showed a bounded
  window with four clean years before it. Each window was accurate about its
  own range and wrong about the defect.
- `docs/finding_2026-10-09_axjo_accumulation_is_price_series.md`
