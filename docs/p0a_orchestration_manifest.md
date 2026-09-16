# P0-A-2 — Orchestration manifest

**Status: audit in progress. Not yet a rehearsal plan.**

P0-A-1 proved the database matched canonical intent **at commit time**
(discovery-15, run 2: 2,103 = 2,103 rows, 72 governed metrics, 0 attribution
errors, 0 contradictions, 0 payload mismatches, 1.63s).

This document answers the question P0-A-1 was never intended to: does the
production orchestration **preserve** that correctness over time.

It does not. See [The temporal integrity defect](#the-temporal-integrity-defect).

---

## The invariant

> Any writer that changes one of the 72 governed storage columns must either
> be part of a canonical run ending in full persistence, read-back validation
> and finalisation, **or** invalidate the previous contract atomically with
> its write.
>
> There is no third state where governed values change and old attribution
> survives.

---

## The temporal integrity defect

**Found by reading, before any rehearsal.**

| | |
|---|---|
| `composite_score.py` — the canonical writer | **weekly pipeline only** (step 9a). Zero references in `daily_pipeline.py`. |
| `build_screener_universe.py` — **daily** step 13 | rebuilds the governed columns via UPSERT |
| `metric_states`, `compute_run_id` | appear **nowhere** in that file — never written, therefore **survive** the rebuild |

So on every weekday that is not the weekly run, the daily pipeline:

1. refreshes `market.computed_metrics`, `market.daily_metrics`,
   `market.halfyearly_metrics`, `market.period_metrics`;
2. rebuilds `screener.universe` from them — changing governed values;
3. **stops**, leaving the previous canonical run's sidecar and
   `compute_run_id` attached to values it never assessed.

A row in that state is worse than an unassessed row: it *claims* to be
canonically assessed, so the projector trusts it and serves it. Under V2 this
means a finalised run is valid for hours, not for a week.

**This is the same stale-survival class P0-A-1 closed *inside* a run,
reappearing *between* runs.** The full-population read-back would pass at
publication and be false by the next evening.

---

## Dependency graph — what feeds the 72 governed values

Derived from actual `INSERT/UPDATE/TRUNCATE` and `FROM/JOIN` references, not
from filenames or schedule order.

```
financials.annual_pnl / balance_sheet / cashflow   [weekly: staging load]
market.valuation_snapshot                          [weekly: transform_valuation]
market.dividends                                   [weekly: transform_dividends → assert]
market.analyst_ratings                             [weekly: transform_analyst_ratings]
        │
market.yearly_metrics        ← yearly_compute      [WEEKLY]
market.computed_metrics      ← daily_compute       [DAILY]
market.daily_metrics         ← technical_compute   [DAILY]
market.halfyearly_metrics    ← halfyearly_compute  [DAILY]
market.period_metrics        ← period_metrics      [DAILY]
        │
        └──→ screener.universe ← build_screener_universe   [DAILY]   governed values
                     │
                     └──→ composite_score (canonical commit)  [WEEKLY ONLY]  ← the gap
```

Four of the five direct inputs to the governed columns are refreshed **daily**.
The canonical tail runs **weekly**. That mismatch is the defect.

---

## Stage manifest

`GOV?` = writes one or more of the 72 governed storage columns.
`POST-FIN?` = can run after a finalisation and mutate governed storage.

### Daily pipeline — `scripts/eodhd/v2/jobs/daily_pipeline.py`

| # | Entrypoint | Writes | Reads | GOV? | POST-FIN? |
|---|---|---|---|---|---|
| 1 | `download_eod_prices.py` | *(raw zone, filesystem)* | `market.companies` | no | no |
| 2 | `asic/download_short_positions.py` | *(raw zone)* | — | no | no |
| 3 | `load_to_staging_prices.py` | `staging_au.eod_prices` | — | no | no |
| 4 | `asic/load_to_staging_short.py` | `staging_au.short_positions` | — | no | no |
| 5 | `transforms/transform_prices.py` | `market.daily_prices` | `staging_au.eod_prices`, `staging_au.company_profile` | no | no |
| 6 | `asic/transforms/transform_short.py` | `market.short_positions` | staging | no | no |
| 7 | `compute/engine/daily_compute.py` | `market.computed_metrics` | prices, dividends, financials, companies | **feeds** | no |
| 8 | `compute/engine/technical_compute.py` | `market.daily_metrics` | prices, companies, shares_stats | **feeds** | no |
| 9 | `compute/engine/halfyearly_compute.py` | `market.halfyearly_metrics` | `market.quarterly_metrics` | **feeds** | no |
| 10 | `compute/engine/period_metrics_compute.py` | `market.period_metrics` | `market.daily_prices` | **feeds** | no |
| 11–12 | index / fund prices | index + fund tables | — | no | no |
| **13** | **`build_screener_universe.py`** | **`screener.universe`** | financials, cm, ym, daily_metrics, valuation_snapshot, dividends, announcements, staging | **YES** | **YES — the defect** |
| 14 | `compute/engine/heatmap_compute.py` | `market.heatmap_cache`, `heatmap_labels` | `screener.universe`, prices | no | no |
| 15 | market snapshots | snapshot tables | universe | no | no |
| — | **canonical tail** | — | — | — | **ABSENT** |

### Weekly pipeline — `scripts/eodhd/v2/jobs/weekly_pipeline.py`

| # | Entrypoint | Writes | GOV? | Notes |
|---|---|---|---|---|
| 0a–0c | ASIC short chain | staging + `market.short_positions` | no | |
| 1 | `load_to_staging_fundamentals.py` | staging tables | no | |
| 2 | `transforms/transform_valuation.py` | `market.valuation_snapshot` | **feeds** | |
| 3 | `transforms/transform_analyst_ratings.py` | `market.analyst_ratings` | **feeds** | |
| 3b | dividends: load → transform → **assert health** | `staging_au.dividends`, `market.dividends` | **feeds** | NOW-3; assertion fails the job |
| 4 | `yearly_compute.py` | `market.yearly_metrics` | **feeds** | prunes orphans |
| 5 | `halfyearly_compute.py` | `market.halfyearly_metrics` | **feeds** | |
| 6 | `weekly_compute.py` | `market.weekly_metrics` | no | |
| 7 | `monthly_compute.py` | `market.monthly_metrics` | no | 1st Monday only |
| 8 | `build_screener_universe.py` | `screener.universe` | **YES** | |
| **9a** | **`composite_score.py`** | **`screener.universe` (canonical)** | **YES — canonical** | the only finalisation today |
| 9b | `pros_cons.py` | `screener.universe` (`pros`, `cons`) | **no — 0/72** | safe post-finalisation |
| 9c | `sector_benchmarks.py` | `market.sector_benchmarks` | no | reads universe |

### Non-canonical universe writers — negative evidence

Each writes `screener.universe` but intersects the governed set at **0 of 72**,
which is the *only* reason they may run after a finalisation. Asserted by
`tests/test_orchestration_contract.py` so it cannot drift silently.

| Producer | Columns written | Schedule |
|---|---|---|
| `asx_indices.py` | `is_asx20/50/100/200/300` | APScheduler 17:50 |
| `short_positions.py` | `short_pct`, `short_interest_chg_1w` | APScheduler 18:30 |
| `dilution_metrics.py` | `shares_outstanding_cagr_3y`, `shares_change_1y`, `dilution_years_3y`, `max_annual_dilution_3y`, `shares_history_years` | weekly-ish |
| `pros_cons.py` | `pros`, `cons` | weekly 9b |

---

## Open audit items

Not yet established; required before the rehearsal is designed.

1. **Target isolation per stage.** Every write-producing stage must prove the
   database it actually reached immediately before its first write. The
   orchestrators spawn subprocesses (`subprocess.run`), so a single inherited
   `DATABASE_URL_SYNC` proves nothing about what each child resolved — some
   call `load_dotenv()` again, some build async URLs, some connect
   independently.
2. **Non-PostgreSQL side effects.** Known so far: Redis cache invalidation in
   `build_screener_universe` (*"Cache invalidated: 2 asx:screener:* keys
   flushed"* — it flushed **production** Redis during a scratch run),
   filesystem raw-zone writes, and the email paths in the alert/digest
   workers. Each must be redirected, disabled, or shown irrelevant.
3. **APScheduler set.** 19 jobs; only `asx_indices` and `short_positions`
   touch `screener.universe`. The remainder (alerts, digests, portfolio,
   announcements, capital raises, cleanup, predictions) are **not** part of
   the canonical path and must not be pulled into the rehearsal merely
   because cron invokes them.
4. **Expected-population proof per producer.** `yearly_compute`,
   `daily_compute` and `universe_build` prove theirs. `technical_compute`,
   `halfyearly_compute`, `period_metrics_compute` and the transforms do not.

---

## Implied target architecture — not yet implemented

**Primary.** The daily sequence must end in canonical publication: after
`build_screener_universe` rewrites governed values, the same scheduled run
executes the canonical commit, read-back validation and finalisation.

**Defence in depth.** Any provisional governed write must invalidate the
previous attribution and state if the canonical tail does not complete, so a
failure is *unavailable* rather than *falsely authoritative*.

This creates a short fail-closed interval while the tail runs. Double-buffered
publication is the later improvement if measurement shows that interval is
product-significant; it is explicitly **not** in scope before P0-A closes.

**Rehearsal shape.** P0-A-2 must therefore test the temporal sequence, not a
single pass:

```
canonical publication → next daily cycle mutates inputs → canonical publication again
                     → contract remains coherent throughout
```

One cycle would not reproduce the defect this audit found.
