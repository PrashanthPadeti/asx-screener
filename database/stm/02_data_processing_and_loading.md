# Deliverable #2 — Data Processing and Loading Jobs

**Evidence date:** schema snapshots 6–9 Nov 2026, `asx_screener@ubuntu-s-2vcpu-4gb-syd1`.
**Lineage:** `database/stm/lineage.json`, 242 modules scanned, 142 touching the database, 85 tables written.
**Generated inputs:** `backend/scripts/stm/extract_lineage.py`, `snapshot_schema.py`.

This document says what moves data between the layers, what each job writes,
and where a value can be wrong without anything failing. It is a companion to
the column-level mapping (`stm_*.csv`, 1,576 columns at 100% coverage) and to
the execution order (`03_job_execution_runsheet.md`).

Nothing here is asserted from memory. Table membership, writers and
operations come from a static parse of the code that runs; row counts and
constraints come from a dated snapshot of the production database. Where a
claim is *not* established, it says so.

---

## 1. The shape of the pipeline

```
EODHD / ASIC / ASX          the outside world
        │
        │  download_*.py            writes FILES, not tables
        ▼
  staging_au.*               BRONZE      15 tables
        │
        │  load_to_staging_*.py     file -> table, as received
        │  transforms/*.py          conform, type, key
        ▼
  financials.*  market.*      SILVER      22 tables
        │
        │  compute/engine/*.py      derive, aggregate, score
        ▼
  market.* (computed)         GOLD        20 tables
        │
        │  build_screener_universe.py   one statement, 341 columns
        │  + 8 UPDATE-in-place modules
        ▼
  screener.*                  UNIVERSE     4 tables
```

Two further groups exist and are *not* part of the medallion flow:

- **out-of-scope — 21 tables.** `meta.*`, `users.*`, and other operational
  tables. They are written by the same jobs and carry no analytical
  content. `screener.saved_screens` is among them by declaration rather
  than by schema: it holds user-authored screen definitions keyed on
  `user_id`, written by an API route, and is not pipeline output.
- **UNCLASSIFIED — 0 tables.** Every write target is now declared.
  `market.scheduler_job_runs` is per-run telemetry from
  `app/workers/pipeline_tracker.py` and joins the control tables;
  `market.ai_summaries` holds generated company summaries written on demand
  by the companies API route, with no scheduled producer and no run
  attribution, so it is not a computed measure. Both became visible only
  when `app/` joined the lineage scan, and both would otherwise have
  defaulted into a medallion layer on their schema name alone.

### A note on "intermediate and temp tables"

There are none in the sense the question usually means. No job creates a
`TEMP TABLE`, and no table exists solely as scratch between two steps of one
job. What plays that role here is different and worth naming, because it is
where several defects in this document live:

- **Bronze IS the staging layer.** `staging_au.*` holds the feed as received,
  one row per entity, replaced wholesale on each load. It is the only
  "landing" surface.
- **Three Bronze tables are read directly by the Universe builder**, bypassing
  Silver entirely: `staging_au.shares_stats`, `staging_au.company_profile`
  and `staging_au.fundamentals`. That is a layer violation and it is
  load-bearing — `fundamentals.reporting_currency` drives the applicability
  gate that marks eight valuation ratios NOT_MEANINGFUL.
- **`screener.universe` is its own intermediate.** The builder inserts 341
  columns, then eight separate modules UPDATE the same rows in place. Between
  the insert and the last update, the row is published-shaped but not
  published — which is exactly what `compute_run_id` exists to signal.

---

## 2. Bronze — `staging_au.*` (15 tables)

```
analyst_ratings   balance_sheet    cash_flow       company_profile
dividends         earnings         eod_prices      exchange_symbols
fundamentals      highlights       income_statement shares_stats
short_positions   splits           valuation
```

**Jobs.** `scripts/eodhd/v2/download_*.py` fetch from EODHD and write to the
filesystem — they write no table, and the run sheet labels them
`(writes no table)` rather than leaving a blank that could be read as "touches
nothing". `scripts/eodhd/v2/load_to_staging_*.py` and
`scripts/asic/load_to_staging_short.py` load those files into Bronze.

**Load strategy.** Predominantly full replacement per entity. Three of the
tables the Universe reads directly carry `UNIQUE (asx_code)` —
`shares_stats`, `company_profile`, `fundamentals`, 2,037 rows each. That
constraint is doing more work than it appears: the builder's laterals over
those tables take `LIMIT 1` with no `ORDER BY`, which is deterministic *only*
because the unique key makes the WHERE clause pick exactly one row.

**What can be wrong here without failing.** Bronze is as current as its last
load and carries no per-row as-at timestamp that reaches the Universe. A feed
that returns a stale document loads cleanly.

---

## 3. Silver — `financials.*` and conformed `market.*` (22 tables)

```
financials.annual_balance_sheet   financials.annual_cashflow
financials.annual_pnl             financials.earnings_quarterly

market.analyst_ratings   market.asx_announcements   market.capital_raises
market.commodity_prices  market.companies           market.daily_prices
market.dividends         market.exchange_list       market.fund_prices
market.funds             market.fx_rates            market.global_index_prices
market.index_prices      market.shares_history      market.short_interest
market.short_positions   market.splits              market.valuation_snapshot
```

**Jobs.** `scripts/eodhd/v2/transforms/*.py` and
`scripts/asic/transforms/transform_short.py`. These conform types, apply the
business key, and in several cases are the first point at which a row becomes
addressable by `asx_code`.

**Two structural facts that matter downstream:**

1. **`market.companies` is SCD Type 2.** `market.companies_current` is the
   `is_current` slice, guarded by a UNIQUE PARTIAL index on
   `(asx_code) WHERE is_current = true`. That index — not the view
   definition — is what makes "one row per company" true, and the entire
   one-row-per-code guarantee of `screener.universe` rests on it.

   A consequence worth stating plainly: a reclassification rewrites the
   sector on every historical metric's row without restating the metric.

2. **`market.daily_prices` is the pipeline's freshness anchor.** The
   incremental window starts three days behind the table's own Sydney-date
   watermark, not behind the clock. That is deliberate — a clock-derived
   window makes a missed day permanent, and a missed day here is a continuity
   failure rather than a fresh table with a hole.

**Known defects in this layer** (full detail in `OPEN_FINDINGS.md`):

| # | Table | What |
|---|---|---|
| 3 | `market.capital_raises` | writer uses `ON CONFLICT DO NOTHING`, so a correction to an already-ingested raise never lands |
| 2 | `market.short_interest` | no backend reader found; not confirmed unused |

---

## 4. Gold — computed `market.*` (20 tables)

**Jobs.** `compute/engine/*.py` — `daily_compute`, `technical_compute`,
`yearly_compute`, `halfyearly_compute`, `quarterly_compute`,
`monthly_compute`, `weekly_compute`, `period_metrics_compute` and others.

This is the layer where the product's numbers are actually made, and it holds
the highest concentration of open findings:

| # | Table | What | Status |
|---|---|---|---|
| 6a–6d | `market.yearly_metrics` | 27 of 188 columns never written; 37 hold frozen values produced by the superseded `_avg` helper — proven by window-length inversions where `avg_roe_10y` exceeds `avg_roe_7y` on the same company | CONFIRMED |
| 7a | `market.computed_metrics` | written by a dynamically built UPDATE whose SET list varies per run, so a column omitted on a run KEEPS the previous run's value | OPEN |
| 7b | `market.computed_metrics` | 103 of 147 columns all-zero | CONFIRMED |
| 9 | `market.halfyearly_metrics` | the half is assigned by ROW POSITION in a calendar-year grouping; 1,827 of 32,263 company-years (5.7%) misassigned | MEASURED |
| 10 | `market.weekly_metrics` | four boolean signals write FALSE where the value is uncomputable; `market.daily_metrics` writes NULL in the identical situation | OPEN |
| 1 | `market.period_metrics` | window names do not describe the windows; windows anchor on the clock; highs and lows unadjusted | OPEN |

The pattern across 6a, 7a and 10 is one pattern: **an absent value and a
measured value are stored identically.** 10 writes a false where it means
unknown; 7a leaves yesterday's number where it means unknown; 6a leaves a
column that was never computed looking exactly like one that was.

**Price basis, which affects every return and technical in this layer.**
Computations run on UNADJUSTED close. `adjusted_close` exists and is not used:
it is a total-return series and is separately known to be stale, so a return
computed from it would mix a price return with a total return. A corporate
action inside a window therefore moves a value for a reason that is not a
price move; the daily engine withholds across detected actions, and the
coverage of that detection is finding 1c.

---

## 5. Universe — `screener.*` (5 tables)

```
screener.universe                     376 columns, 2,566 rows
screener.compute_runs                 one row per run
screener.compute_run_stages           append-only stage evidence
screener.compute_run_finalizations    one row per PUBLISHED run
```

`screener.saved_screens` sits in the same schema and is NOT in this
layer. It is user data, declared out-of-scope rather than defaulted in.

### 5.1 How the row is built

`screener.universe` is written by **nine** jobs — one insert and eight
updates in place. Precedence is ordering, and ordering is the contract:

| Order | Job | Writes | Effect |
|---|---|---|---|
| 1 | `build_screener_universe.py` | 341 columns, one `INSERT ... ON CONFLICT DO UPDATE` | the row exists; values are PROVISIONAL |
| 2 | `asx_indices.py` | 5 index flags | overwrites the builder's values |
| 2 | `short_positions.py` | `short_pct`, `short_interest_chg_1w` | overwrites the builder's values |
| 2 | `dilution_metrics.py` | 5 dilution columns | insert does not write these at all |
| 2 | `pros_cons.py` | `pros`, `cons` | insert does not write these at all |
| 3 | `composite_score.py` | 16 score and multibagger columns | insert does not write these at all |
| 4 | `universe_writer.py` | 80 GOVERNED columns, from a registry | the canonical commit — this is what a customer reads |
| 4 | `metric_states.py` | `metric_states`, `compute_run_id` | the attribution |

The builder deliberately sets `metric_states` and `compute_run_id` to NULL,
atomically with its own write. That is not a bug — it is the builder revoking
a canonical claim it is not entitled to make, because it has assessed
nothing. `app/core/row_projection.py` turns a NULL `compute_run_id` into
`OUTSIDE_SNAPSHOT` and nulls every governed value with a stated cause, so a
row that has not reached the canonical writer **fails closed at the API**
rather than being served as current.

### 5.2 Why the row is exactly one row per company

Proven structurally, not assumed — `backend/tests/test_universe_join_cardinality.py`:

| Source | Count | Rule | At most one row |
|---|---|---|---|
| driving relation | 1 | `market.companies_current`, UNIQUE PARTIAL index | one |
| plain `LEFT JOIN` | 2 | `ON asx_code`, the other side's PRIMARY KEY | at most one |
| lateral, `LIMIT 1` | 25 | ordered, or an equality on a unique key | at most one |
| lateral, aggregate | 4 | no `GROUP BY` | exactly one |

Zero of the 32 sources can fan the driving row out. Cardinality and
determinism are checked separately, because `LIMIT 1` settles only the first:
twelve laterals take `LIMIT 1` with no `ORDER BY` and are deterministic
because their WHERE clause pins a unique key — `fiscal_year = pnl0.fiscal_year - 1`
for the annual ones, `UNIQUE (asx_code)` for the three Bronze tables.

### 5.3 Known defects in this layer

| # | What | Status |
|---|---|---|
| 11 | Ten columns no statement writes. Nine are NULL on every row. `price_to_52w_high` is FROZEN on 2,290 of 2,566 rows — it is in neither the insert list nor the `DO UPDATE SET` list, so an existing row's value is never touched by any run — and it is served through a registered filter, a sort column and a response field | MEASURED |
| 12 | The six market-cap tier flags are `COALESCE(..., FALSE)` on `NOT NULL DEFAULT false` columns, while `market_cap_tier` beside them returns NULL. 641 of 2,566 rows (25.0%) carry six falses and a NULL tier | MEASURED |
| 13 | A `dp52` lateral computed the 52-week extremes a **second** time — `MAX(high)`/`MIN(low)` over 365 days of raw `market.daily_prices` — with no coverage rule and no split adjustment, and four published columns were derived from it while the extreme beside them came from the governed producer | **FIXED** — the lateral is removed; the extremes and everything derived from them read `dm` |

Finding 11 is the sharper one, and not for the reason it first appeared.
Nine empty columns are a schema promise nobody kept — visible, inert, easy to
fix. The tenth is a value frozen at an unknown past date sitting beside a
`price` and a `high_52w` that are refreshed daily. **Empty is visible; stale
is not.**

Finding 13 is the same lesson one level up. Two producers for one quantity
is not redundancy; it is a contradiction the row publishes without saying
so. The governed extreme and the ratio taken of it sat in adjacent columns
and came from different computations — one that required 365 days of
coverage and split-adjusted prices, one that required nothing and used raw
ones. **A ratio must come from the same producer as the quantity it is a
ratio of.**

---

## 6. Coverage denominators, reconciled

A coverage figure is only as good as the number it divides by, so the
denominators are recorded here with their provenance.

### The three layers

| Layer | Target columns | Authored | Coverage |
|---|---|---|---|
| Bronze -> Silver | 404 | 404 | 100% |
| Silver -> Gold | 771 | 771 | 100% |
| Gold -> Universe | 401 | 401 | 100% |
| **Total** | **1,576** | **1,576** | **100%** |

`generate_stm.py --fail-on-unmapped` exits 0 against these.

### Gold -> Universe: 401, and where 542 came from

An earlier figure of 542 for this layer was **never a measurement**. It was
written into the STM generator's own docstring when the generator was
authored (commit `be72c21`), before any snapshot of `screener.universe`
existed, and it was corrected to 376 in `20bc4b3`. Nothing ever counted 542
columns; no migration, snapshot or catalogue query produces that number.

The measured figures reconcile exactly:

```
542   asserted, never measured
-166  columns that were never in the table
 376  screener.universe, measured
 +25  compute-run lifecycle columns added to the layer's scope
 401  Gold -> Universe target columns
```

`542 - 401 = 141`, and that difference is **two separate movements** rather
than one: 166 columns removed because they did not exist, and 25 added
because the layer covers more than one table.

The 25 are `screener.compute_runs` (8), `screener.compute_run_stages` (11)
and `screener.compute_run_finalizations` (6). They are in scope because they
decide whether a universe row may be served at all, and a mapping document
that described the row but not its publication contract would be describing
half the surface.

### Why 376 is trustworthy

Four independent confirmations, none of them a restatement of another:

- the production snapshot declares 376 columns and carries 376 rows
- the ordinals are contiguous 1-376 with no duplicate names
- the generator emitted exactly 376 rows for the table
- `universe_writer.verify_storage()` reads `information_schema.columns` at
  run time and refuses to write when a governed column is absent, so a
  wrong column set would stop the pipeline rather than produce a document

### A denominator that moved during this work

The Gold -> Universe target set briefly became 1,577. Adding `app/` to the
lineage scan made `screener.saved_screens` visible, and the `screener`
schema resolved to "Universe" by a blanket schema rule, so a table of
user-authored screen definitions joined the layer and the coverage could not
close.

That is the same defect the `market.*` split was fixed for, in a schema the
UNCLASSIFIED guard did not cover. The Universe layer is now declared per
table, `screener.saved_screens` is declared out-of-scope, and an undeclared
`screener.*` table is UNCLASSIFIED rather than admitted.

The episode is worth recording because the denominator was wrong in the safe
direction for only one run: a 100% that was measured against a population
missing a table reads exactly like a 100% that was not.

## 7. What is NOT established

Stated so that absence of a claim is not read as a clean finding:

- **Why `market_cap` is absent for 639 companies.** `valuation_snapshot` is
  joined on its primary key, so the absence is in the source. Whether those
  are suspended securities, recent listings, or companies whose
  shares-outstanding never arrived is a separate question from how the
  absence is reported.
- **Whether EODHD quarterly figures are standalone-period or cumulative
  year-to-date.** Summing or differencing them depends on the answer, and
  `market.quarterly_metrics` has overlapping writers whose insert ownership
  and update precedence are not yet documented.
- **`stock_count` 189 and 277 against nominal 200 and 300** on
  `market.index_snapshots` (finding 5).
- **Six scheduled jobs** whose callables do not resolve to a module:
  `fund_prices`, `anomaly_detect`, `capital_raise_scan`,
  `mining_reit_metrics`, `top5_strategy`, `asx_companies`. Their data effects
  are UNKNOWN, which the run sheet records as `(unresolved)` rather than as
  an empty writes column.
