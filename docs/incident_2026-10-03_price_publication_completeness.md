# 3 October 2026 — price publication completeness

Found while investigating a four-day September gap. Far larger than the gap
that led to it.

## The defect

`market.daily_prices` was missing rows that `staging_au.eod_prices` held, on
**6,800 distinct dates**, in two regimes:

| period | staged-but-unpublished per day |
|---|---|
| 2022 → 2026-04-27 | ~13, rising slowly to ~23 |
| 2026-04-28 → 2026-10-02 | **~400–480** |

544 instruments listed in `screener.universe` had **fewer than 30 published
daily prices**. Not new listings: ATM held 6,775 staged rows from 2000-01-03
and 12 published rows from 2026-08-10. BHP, the control, read 6,807 = 6,807.

`market_from` for the affected population clusters on **2026-08-10**, which
is the day they first appeared in the canonical table and began accruing one
row per day with nothing behind them.

## Why

`daily_pipeline` runs `transform_prices --from-date YESTERDAY`. A code newly
present in staging is published only from the day it is first picked up
forward. Nothing ever revisits the history that arrived with it. A full run
(no date bounds) would publish everything, but it `TRUNCATE`s and is manual —
so the backlog is only ever cleared by hand.

## Repair

| step | codes | rows written | missing before |
|---|---|---|---|
| ATM, mechanism test | 1 | 6,775 | 6,763 |
| main repair | 593 | 102,300 | ~2.9M est. |
| residue | 15 | 24,029 | 2,060 |

Afterwards: **0 codes / 0 rows** staged-but-unpublished.

`--codes` keeps `is_full_run` false, so the `TRUNCATE` branch is unreachable
and writes are additive upserts. Upserts into compressed chunks were verified
on ATM (history back to 2000) before the bulk repair.

Rows written exceed rows missing because a `--codes` run transforms every
staged row for those codes, re-upserting correct ones.

## A selection defect in the repair itself

The 593-code population was drawn from the TARGET:

    SELECT asx_code FROM market.daily_prices GROUP BY asx_code HAVING count(*) < 30

Ten codes had **zero** rows there and no group at all — IBK among them, 1,789
staged rows spanning 2008–2018. Structurally invisible to the selector. Found
only by re-running the source-side anti-join afterwards. See the standing rule
on deriving repair populations from the source.

## What is and is not established

**Established:** every staged `(asx_code, date)` now has a published row —
`staging ⊆ market` over the comparable key space.

**Not established:** set equality. The reverse difference was not computed,
and market-only rows (retained Yahoo history, staging retention semantics)
are a separate question.

## Canonical recomputation — run 6, completed

`DAILY_CANONICAL` under the execution lease, hand-invoked (the driver takes
the lease itself; `LEASE_HELD_ENV` is the wrapper's way of saying a parent
already holds it, and must not be set for a standalone run).

    reuse PERMITTED: yearly source fingerprint is unchanged, proven by run 2
    yearly_compute   NOT executed
    transform_prices        1,760 / 1,760    sets are equal
    daily_compute           1,861 / 1,861
    technical_compute       2,346 / 2,346
    halfyearly_compute     32,039 / 32,039
    period_metrics_compute  2,479 / 2,479
    universe_build          2,539 / 2,539    (PROVISIONAL)
    composite_score         2,121 published under run 6, 0 violations
    yearly fingerprint still current at publication
    read-back PASS — 0 attribution errors, 0 contradictions, 0 mismatches

A first attempt was killed by ^C mid `technical_compute` (1,300/2,346). The
designed semantics held exactly: no advisory lock survived, the universe was
untouched, run 4 kept serving, nothing was published.

## The 418 unattributed rows — resolved, not a defect

    active     2121 rows    0 unattributed   2121 on run 6
    delisted    418 rows  418 unattributed      0 on run 6

`universe_build` writes 2,539 provisional rows; `composite_score` loads and
attributes only the 2,121 active ones. So with
A = universe_build population, B = publication-eligible, C = run-6-attributed:
**B == C exactly**, and A − B is precisely the delisted set. Reproducible
across runs — run 4 finalised 2,115 of 2,539 for the same reason.

**P0-A stays closed.** Remaining question is a product one: whether delisted
instruments should be present in `screener.universe` at all.

## Customer-visible impact — confirmed, not merely inferred

Deterministic before/after sample, run 4 → run 6:

    high_52w      ALPH   11.36 -> 11.91     CIIH 1.44 -> 1.72
                  ETPMPD 169.91 -> 195.99
    drawdown_from_ath   ETPMPD -0.5948 -> -0.1807
    ATM           above_sma200 False -> True, dma200_ratio 0.997 -> 1.1492
    GFXD          adx_14, bb_*, ema_20  None -> populated

52-week highs rose because a year of history became visible for the first
time. Those values were wrong on the site this morning.

**The most important case is a metric that disappeared:**

    dma200_ratio   ALPH 1.0175 -> None   (96 staged rows)
                   CIIH 1.0244 -> None   (107)
                   ETPMPD 0.8517 -> None (90)

A 200-day moving average cannot exist on ~90–107 observations. Before the
repair the system published one anyway, computed from a truncated series.
Its disappearance is a correctness improvement: the truncated source state
was capable of producing apparently valid metrics from insufficient history.
Judged by "more data means more metrics", this would have been misfiled as a
regression.

Metric movement is corroborating evidence. The proof that recomputation
occurred is the canonical execution itself.

## Still outstanding

1. **Derived metrics are stale.** 52-week ranges, moving averages, RSI,
   momentum and returns for the affected codes were computed from 5–30 days
   of data. Publishing prices does not recompute them.
2. **Yearly scope must be re-derived.** An earlier count of 16
   fingerprint-affected codes predates the residue repair and must not be
   carried forward as an acceptance number.
3. **One deliberate FULL canonical run** under the execution lease — with
   `yearly_compute` running rather than reused, provisional rebuild, commit,
   readback, finalisation and publication-time fingerprint validation.
4. **69 short-history instruments unclassified.** Short staging history does
   not establish `INSUFFICIENT_HISTORY`; it may equally be `SOURCE_MISSING`
   or an ingestion/retention defect. Cannot-exist is not failed-to-obtain.
5. **Baseline B contamination.** Both repairs (09:28:07–13 and
   09:33:10–13) ran inside the 09:05–10:25 Baseline B probe window. ~9
   seconds of concentrated writes against a 15-second sampling interval.
   Recorded so B↔C comparison is not silently invalidated.

## Sampling before recompute

Capture customer-visible metrics for a deterministic sample of affected codes
BEFORE the canonical run, so afterwards "recomputation was required" can be
distinguished from "a customer-visible metric actually changed".
