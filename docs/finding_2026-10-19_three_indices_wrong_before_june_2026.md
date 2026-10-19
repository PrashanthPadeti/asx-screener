# ASX20, AXFJ and AXMJ carry the wrong series before June 2026

**Found:** 19 October 2026, while verifying EODHD symbol mappings
**Status:** OPEN — repair decided (fix history before switching source), method not yet decided
**Severity:** published values are wrong, not merely stale

## What was measured

Agreement between each stored index series and every Australian index EODHD
lists (35 candidates, each fetched once), by calendar month, over 400 days.
Median level difference; outliers counted separately.

Five series agree with their correctly-named symbol across the whole window
at `0.00000%`. Three do not, and all three break in the **same month**:

| Code | Sep 2025 – May 2026 | Jun 2026 onward | Symbol it then matches |
|---|---|---|---|
| ASX20 | median ≈ **46%** | `0.00000%` | `ATLI.INDX` — S&P/ASX 20 |
| AXFJ | median ≈ **31,000%** | `0.00000%` | `AXFJ.INDX` — S&P/ASX 200 Financials |
| AXMJ | median ≈ **138,000%** | `0.00000%` | `AXMJ.INDX` — S&P/ASX 200 Materials |

After the break each matches the symbol whose **name** matches the index, to
five decimal places, across 71 sessions and five months. Before it, they do
not match that symbol at all.

## What the pre-June values appear to be

**ASX20 held the All Ordinaries.** Measured over the full 400 days, stored
ASX20 matches `AORD.INDX` at a median of `0.00000%` with 73 outliers — and
those 73 sessions are the post-June ones. So on the ~177 pre-June sessions
the stored "ASX 20" is the All Ordinaries, exactly. On 2026-08-24, after the
break, ours reads 5,190.4 against the All Ordinaries' 9,316.7.

We published the All Ordinaries under the name "ASX 20" for at least nine
months.

**AXFJ and AXMJ held values that are not index levels.** The ratios imply
pre-June stored values near 30 and 19 against true levels near 9,700 and
26,500 — roughly 1/317 and 1/1,380. What they actually were is not
established. Over the full window the closest candidate for both was the
S&P/ASX 200 VIX, which is suggestive of small-magnitude values and nothing
more.

## What is NOT established

**The cause.** `^ATLI`, `^AXFJ` and `^AXMJ` have been the configured tickers
since the original ingestion commit (`fb5846f`), never changed. No commit
between May and July 2026 touches the index mapping, and within this
repository `index_prices.py` is the only writer of `market.index_prices`.

So no change in this repository explains the break. That is **not** proof of
an external writer, and not proof that the provider changed what those
tickers return. It narrows where to look; it does not identify the cause.
An earlier finding in this codebase asserted an external writer from exactly
this kind of absence and was wrong to.

**The full extent.** Agreement was measured over 400 days. Whether the
contamination begins earlier — possibly at first ingestion — is unmeasured.
Any repair needs that boundary first.

## Live consequence, to be measured

`compute_rows` derives `return_1y`, `return_ytd`, `high_52w` and `low_52w`
from this same stored series. A one-year window currently straddles the June
break, so for AXFJ it spans a ~317× step. Unless something downstream
filters it, the site may be publishing a one-year return in the tens of
thousands of percent for these three today.

That is a customer-facing correctness defect and outranks the source switch
that found it.

## Why this blocks the EODHD switch

The switch was to be justified by "this symbol continues the series we
publish". For these three, the series we publish is not one series, so that
evidence does not exist in the form the rule requires. The 71 post-break
sessions are real evidence about the current series — but building a source
switch on top of history known to be wrong repairs nothing and buries the
defect under a release.

Decision taken 19 Oct 2026: **repair the history first, then switch all
eight as one clean release.**

## Open questions for the repair

1. How far back does the contamination go? Measure before choosing a method.
2. Repair, or truncate? EODHD carries the correct series for all three.
   Replacing known-wrong rows with a documented decision is not the same as
   one provider silently overwriting another's — but it IS a historical
   overwrite, and the forward-only rule exists for good reasons. The choice
   needs stating explicitly, not assuming.
3. What happens to derived values computed across the boundary, before the
   repair lands?

## Related

- `engineering_rule_verdict_from_filtered_view` — a 120-day window showed
  these three as clean matches; 400 days showed they were not one series.
  The shorter window was not wrong about its own range, only about what it
  could see.
- `docs/finding_2026-10-09_axjo_accumulation_is_price_series.md` — the other
  index serving a series it was not advertised as.
