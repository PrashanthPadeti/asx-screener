# Returns are computed on unadjusted close, and the adjusted column cannot replace it

**Found** 24 October 2026, from an F841 (`a = df["adj_close"]`, assigned and
never used) surfaced once ruff had a declared ruleset.
**Status** step 1 CLOSED 26 Oct 2026 (splits ingestion repaired, see the
update at the foot of this file). The defect itself remains **not fixed**:
returns are still computed from unadjusted close. The obvious fix is
unavailable and
the alternative has a completeness gap. Evidence recorded here so the work
can start from measurement rather than memory.

## The defect

`compute/engine/technical_compute.py` computes every return from the raw
close:

```python
c = df["close"]                                    # UNADJUSTED
df["daily_return"] = c.pct_change()
df["return_1m"]    = (c / c.shift(21)  - 1)
df["return_3m"]    = (c / c.shift(63)  - 1)
df["return_1y"]    = (c / c.shift(252) - 1)
```

`adj_close` is selected, cast to float and written to the output row, but
**consumed by no calculation**. The only binding was the unused one.

A 2-for-1 split therefore shows as roughly **−50%** in every return window
spanning it; a 1-for-250 consolidation shows as a 250× gain. The moving
averages, Bollinger bands and the 52-week range inherit the same break.

## Why the obvious fix is wrong

`adjusted_close` is a **total-return** series, not a split-adjusted price.
CBA, ratio `close / adjusted_close` by period:

| period | ratio | |
|---|---|---|
| 2024-02-21 → 2024-08-20 | 1.06248 | |
| 2024-08-21 → 2025-02-18 | 1.04346 | |
| 2025-02-19 → 2025-08-19 | 1.02902 | |
| 2025-08-20 → 2026-02-17 | 1.01338 | ex-date 2025-08-20 |
| 2026-02-18 → 2026-10-23 | 1.00000 | ex-date 2026-02-18 |

Every band boundary is an ex-dividend date. Substituting it would silently
convert a price return into a total return — the same conflation for which
AXJO was withheld in v11.2.18.

**And it is not maintained coherently.** CBA went ex-dividend on 2026-08-19
($2.70); the ratio stays 1.000000 across that date except for a *single row*
at 2026-08-18 of 1.016882, which is exactly 2.70/160. The provider
recomputes the whole series after each dividend; ingestion only rewrites the
rows it re-fetches, so the column is a mixture of vintages. Switching to it
would inject a fake 1.7% jump at every vintage boundary.

## Why the alternative is not ready

Over 18 months, 700,063 rows, 2,484 codes:

| | |
|---|---|
| ratio discontinuities > 10% in a day | **222** |
| explained by a recorded split (±5 days) | **91** |
| transient spikes — ratio leaves and returns, so nothing happened to the price | **40** |
| **persistent steps with no recorded split** | **91** |

`market.splits` holds 2,305 rows across 861 codes back to 2000, 116 of them
in the last 18 months — but it accounts for only 91 of 222 discontinuities.
The 40 transient ones are corrupt `adjusted_close` rows. The remaining **91
are real, persistent, and unrecorded**: large special dividends, capital
returns, rights issues or splits the table is missing.

Building a split-only factor from `market.splits` alone would correct some
stocks and leave ~91 events untouched — worse than uniform error, because
the survivors become harder to find.

Also: the latest recorded split is **2026-04-28**, six months before this
was written. Genuinely quiet period or stalled ingestion is unestablished.

`ratio` runs both ways — 0.050000 is a 1-for-20 consolidation, 0.004000 a
1-for-250. Inverting the convention would multiply an error by 250 rather
than remove it.

## What this needs, in order

1. **Establish `market.splits` freshness** against an independent source.
   Six months without a split on the ASX is possible and should be proven,
   not assumed.
2. **Classify the 91 persistent unexplained steps.** Join to
   `market.dividends` and `market.corporate_events` first; whatever remains
   is a population the pipeline has no record of.
3. **Decide what the labels mean.** "Return 1Y" is currently a raw price
   ratio. It should be a split-adjusted price return, or a total return
   named as one. It cannot be both.
4. **Derive a split-adjusted series** — a per-code cumulative factor from
   validated corporate actions, applied to open/high/low/close together.
   Adjusting close alone would mix an adjusted close with raw highs and
   break ATR, Bollinger and the 52-week range.
5. **Recompute and backfill**, with a row-level reconciliation of before
   and after, as in the v11.2.25 index repair.
6. **Declare `adjusted_close` untrusted** until its staleness is fixed; it
   is currently a total-return series maintained in mixed vintages.

## Rule

An unused variable was the only visible trace. `a = df["adj_close"]` was
dead code in the strict sense, and behind it sat every return on the site
computed on a basis nobody had chosen.

The fix that suggests itself — "use the adjusted column" — would have been
worse than the defect: wrong metric, plus fake jumps where ingestion
vintages meet. The column's name described an intent, not its contents, and
the only way to find that out was to plot the ratio against known ex-dates.
A column called `adjusted_close` deserves the same scepticism as a vendor
series called a price index.

---

## Update, 26 October 2026 — step 1 closed, measured

**Step 1 was "establish `market.splits` freshness against an independent
source". Done. It was not fresh, and the cause was two bugs, not a quiet
market.**

### What was wrong

`market.splits` had not changed since **2026-04-28** — 181 days. The ASX does
not go six months without a consolidation, and it had not: EODHD held every
one of them, and the raw payloads were on disk the whole time.

**1. The loader selected the OLDEST payload per code.**

```python
for f in sorted(paths):        # ascending — oldest first
    if code not in seen:
        seen[code] = f         # keeps the first it sees
```

under a comment reading *"one (latest) file per code"*. Payloads are named
`CODE.AU_YYYY-MM-DD.json.gz`, so ascending order keeps the earliest fetch and
discards every split recorded since.

**2. Nothing ran the loader anyway.** `load_to_staging_splits` was absent
from `pipeline_runner`'s `STAGING_SCRIPTS` while `transform_splits` sat in
`TRANSFORM_SCRIPTS` — so the transform ran, exit 0, against a staging table
nothing filled. Neither `daily_pipeline` nor `weekly_pipeline` mentioned
splits at all.

**3. And the first fix was half wrong.** Switching to the NEWEST payload
(v11.2.52) recovered 31 recent splits and **lost 173 historical ones**.
EODHD's splits endpoint does not reliably return the full series: EVR's
`2026-10-04` payload contains only the 1-for-10 of 2026-09-08 — one record —
despite `from=2000-01-01`, while its `2026-04-28` payload holds the 2008 and
2017 consolidations. **A payload is evidence of the splits it contains and
evidence of nothing about those it omits.** v11.2.53 unions every payload.

### Why six months passed unnoticed

`assert_output_freshness.py` runs daily and derives its population from
"the API reads this table AND a scheduled job writes it". No scheduled job
wrote `market.splits`, so it could not be stale by that definition. **The
check was correctly excluding the one table that was wrong.** Wiring the job
into `weekly_pipeline` brings it into that population by the same rule.

### Measured result

| | before | after |
|---|---|---|
| `market.splits` rows | 2,305 | **2,546** |
| latest split | 2026-04-28 | **2026-10-22** |
| splits after 28 Apr | 0 | **51** |
| rows lost from the pre-repair backup | — | **0** |

Discontinuity classification re-run over the same 18 months, 184 persistent
steps:

| | before | after |
|---|---|---|
| explained by a recorded split | 91 | **106** |
| still unexplained | 93 | **78** |

### What remains open

**The defect in this document is not fixed.** Returns are still computed from
unadjusted close in `compute/engine/technical_compute.py`; nothing about the
calculation changed. What changed is that step 1's precondition is now true:
split data is current, maintained weekly, and guarded.

Still outstanding, in the original order:

2. **78 persistent discontinuities remain unexplained.**
   `market.corporate_events` is **completely empty** — it explained 0 of 184
   — so capital returns, rights issues and special dividends have no source
   at all. That is a separate finding and the next blocker.
3. Decide what "Return 1Y" means: split-adjusted price return, or total
   return named as one.
4. Derive the adjusted series across open/high/low/close together.
5. Recompute and backfill with row-level reconciliation.
6. `adjusted_close` remains untrusted — total-return, mixed vintages.

**Interim option, if 2–5 stay out of reach:** withhold rather than publish.
Where a return window spans a detected discontinuity, publish the return as
unknown with a reason, as AXJO was withheld in v11.2.18. Detection needs only
the price series; explanation is what needs corporate actions.

### Rule earned here

Both selection rules — oldest and newest — were shipped on the same day, and
both lost data. The check that caught the second was not "did the row count
go up" but **"is anything from the backup now missing"**. A repair needs a
loss check, not only a gain check; they are different questions and only the
second one found it.
