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

## Side-effect authority

Every authority a stage holds beyond its PostgreSQL connection, classified.
**Surveyed, not assumed** — `smtplib|resend|requests.post|httpx|webhook|boto3|
stripe|redis` across every orchestrated stage.

| Authority | Where | Reached by | Rehearsal disposition |
|---|---|---|---|
| **PostgreSQL** | every compute stage | `DATABASE_URL_SYNC` | **redirected** — scratch database, and each child proves its own `current_database()` before its first statement |
| **Redis** | `build_screener_universe._flush_screener_cache` (the only one) | `os.getenv("REDIS_URL", "redis://localhost:6379/0")` | **redirected** — logical db 15; the default is what flushed production in d15 |
| **Filesystem (raw zone)** | `download_eod_prices`, `download_short_positions` | `RAW_DATA_DIR` | **redirected**, or skipped — a rehearsal reuses the existing raw zone read-only |
| **Email (Resend)** | `scripts/utils/alert.py`, called by **both orchestrators** on any step failure | `RESEND_API_KEY` + `ADMIN_EMAILS` | **explicitly disabled** in the child on `P0A_EXPECTED_DB` |
| **External API (read)** | EODHD, ASIC downloads | `EODHD_API_KEY` | **not exercised** — read-only, but consumes the metered budget `budget_audit.py` governs |
| Webhooks / object storage / payment | — | — | **none exist** in any orchestrated stage |

The email path deserves its own note. It fires on the **failure** path, which
is the path a rehearsal is most likely to reach, and it would tell the real
admins that the **production** pipeline failed and to SSH in and re-run it —
when what failed was a rehearsal against a scratch database. The likelier the
side effect, the less acceptable it is to leave it to an environment
convention, so it is refused in `alert.py` on the same signal the database and
Redis gates use, and both directions are asserted in
`tests/test_runtime_envelope.py`: suppressed under confinement, and still
reaching the send path in production, so the suppression cannot quietly become
a permanent disablement.

**No stage is left unresolved-blocking.** Every authority above is redirected,
disabled, or shown not to exist.

---

## Stage manifest

`GOV?` = writes one or more of the 72 governed storage columns.
`POST-FIN?` = can run after a finalisation and mutate governed storage.
`AUTHORITY` = non-PostgreSQL side effects, per the table above.

### Daily pipeline — `scripts/eodhd/v2/jobs/daily_pipeline.py`

Every step is additionally reached by the orchestrator's **email** authority:
a non-zero exit from any of them calls `send_failure_alert`.

| # | Entrypoint | Writes | GOV? | POST-FIN? | AUTHORITY |
|---|---|---|---|---|---|
| 1 | `download_eod_prices.py` | *(raw zone, filesystem)* | no | no | filesystem, EODHD read |
| 2 | `asic/download_short_positions.py` | *(raw zone)* | no | no | filesystem, ASIC read |
| 3 | `load_to_staging_prices.py` | `staging_au.eod_prices` | no | no | filesystem read |
| 4 | `asic/load_to_staging_short.py` | `staging_au.short_positions` | no | no | filesystem read |
| 5 | `transforms/transform_prices.py` | `market.daily_prices` | no | no | postgres only |
| 6 | `asic/transforms/transform_short.py` | `market.short_positions` | no | no | postgres only |
| 7 | `compute/engine/daily_compute.py` | `market.computed_metrics` | **feeds** | no | postgres only |
| 8 | `compute/engine/technical_compute.py` | `market.daily_metrics` | **feeds** | no | postgres only |
| 9 | `compute/engine/halfyearly_compute.py` | `market.halfyearly_metrics` | **feeds** | no | postgres only |
| 10 | `compute/engine/period_metrics_compute.py` | `market.period_metrics` | **feeds** | no | postgres only |
| 11–12 | index / fund prices | index + fund tables | no | no | EODHD read |
| **13** | **`build_screener_universe.py`** | **`screener.universe`** | **YES** | **YES — the defect** | **postgres + REDIS** |
| 14 | `compute/engine/heatmap_compute.py` | `market.heatmap_cache`, `heatmap_labels` | no | no | postgres only |
| 15 | market snapshots | snapshot tables | no | no | postgres only |
| — | **canonical tail** | — | — | — | **ABSENT** |

Step 13 is the only stage in either pipeline holding an authority outside
PostgreSQL and its own filesystem — and it is also the stage at the centre of
the temporal integrity defect.

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
| 8 | `build_screener_universe.py` | `screener.universe` | **YES** | **holds the Redis authority** |
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

## Producer population proofs

Every producer proves its population at **its own semantic grain**. Three of
the four are really questions about time, and a proof collapsed to company
codes cannot ask them: the consumer takes the latest row with no recency
bound, so a code present at the wrong date is served exactly like a code
present at the right one.

| Producer | Grain | Expected set, derived from | Actual set, observed from |
|---|---|---|---|
| `technical_compute` | `asx_code + date` | `daily_prices ⋈ companies_current`, each code's own latest trading day, ≥ 20 days of history | `RETURNING asx_code, date` |
| `halfyearly_compute` | `asx_code + fiscal_year` | `quarterly_metrics`, years with a quarter and a revenue-bearing company | `RETURNING asx_code, fiscal_year` |
| `period_metrics_compute` | `asx_code + computed_date` | `DISTINCT asx_code FROM daily_prices` × today | `RETURNING asx_code, computed_date` |
| `transform_prices` | `asx_code + row_count + date_set_digest` | `staging_au.eod_prices`, same window | the target **after** the write, same window |
| *(already proven)* `yearly_compute`, `daily_compute`, `universe_build` | `asx_code` | source domain | written set |

Rules they all follow:

- **Set equality is the proof; counts are diagnostics.** Equal counts over
  different members fails. Zero exceptions with an incomplete population fails.
- **Expected is never the producer's own selection list.** A run compared
  against its own selection agrees by construction.
- **Actual is what PostgreSQL persisted**, via `RETURNING` on an unconditional
  upsert — not what the process submitted, and not counted until the
  transaction that carried it committed.
- **Both directions.** `expected − actual` is a missed source; `actual −
  expected` means the producer wrote something its own domain does not account
  for, so one of the two is wrong and the run cannot say which.
- **Missing source is not a failed producer; missed eligible source is.**
- **Scoped runs record nothing** — their expected population is not the source
  domain, and a stage row claiming otherwise would be a false claim the
  resolver would act on.
- **Failure is executable**, `sys.exit(main())`, not a log line.

### Why `transform_prices` is not proved by containment

`market.daily_prices` is historical. "Does the target contain every expected
code" is satisfied by rows loaded months ago, so a run that transformed nothing
would pass it for every company — the exact failure the proof exists to catch.
It is therefore proved as set equality against staging **over the same window
on both sides**, per code, by a digest of that code's complete date set. The
digest, not min/max/count: a day swapped out of the middle leaves the count and
both endpoints unchanged.

### Three defects found by construction, before any run

1. `technical_compute` selected `market.companies.status = 'active'`; its
   consumer joins `market.companies_current`, which is `is_current = TRUE` —
   SCD2 row currency, **not** listing status. A producer narrower than its own
   consumer, which is precisely the defect that left 2,954 `yearly_metrics`
   rows with a live source untouched.
2. `transform_prices` took its code list from `staging_au.company_profile`
   while the rows come from `staging_au.eod_prices`. A code in the feed but not
   the profile was never transformed — and a full run **truncates first**, so
   its entire price history was destroyed and not rebuilt, while the counters
   reported a clean run.
3. That `TRUNCATE` had **no precondition**. Against empty staging it succeeded,
   the reload wrote nothing, and every downstream producer then computed
   correctly over no data. It now refuses.

The selections are fixed rather than left for the proof to report nightly.
None of this has been observed against production data yet: these changes are
on `p0a-correctness`, and production runs `main`. **The rehearsal is the first
evidence, and it must be green before any merge.**

---

## Open audit items

Not yet established; required before the rehearsal is designed.

1. ~~**Target isolation per stage.**~~ **CLOSED** — `compute/engine/
   runtime_envelope.py`. Each of the eight canonical-path writers proves its
   own `current_database()` through the connection it is about to write
   through, as the first executable statement after connecting. Asked of the
   live connection, never of the URL the caller meant to use: the
   orchestrators spawn stages with `subprocess.run` and several re-read
   `.env`, so a redirect proven in the parent proves nothing about the child.
   Outside a discovery run the gate only logs. Nine guards in
   `tests/test_runtime_envelope.py`, each mutation-tested until it failed.
2. ~~**Non-PostgreSQL side effects.**~~ **CLOSED** — see
   [Side-effect authority](#side-effect-authority). Nothing unresolved
   remains: Redis and the filesystem redirected, email disabled under
   confinement, external APIs read-only, and no webhook, object-store or
   payment authority exists in any orchestrated stage.
3. **APScheduler set.** 19 jobs; only `asx_indices` and `short_positions`
   touch `screener.universe`. The remainder (alerts, digests, portfolio,
   announcements, capital raises, cleanup, predictions) are **not** part of
   the canonical path and must not be pulled into the rehearsal merely
   because cron invokes them.
4. ~~**Expected-population proof per producer.**~~ **CLOSED** — see
   [Producer population proofs](#producer-population-proofs). Each proves its
   own population at its own grain. None has been added to `REQUIRED_STAGES`:
   which are formal prerequisites of a canonical run follows from the
   dependency graph, not from having been audited.

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
