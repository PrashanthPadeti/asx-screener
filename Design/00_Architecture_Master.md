# ASX Screener — Master Architecture & Design Document

**Version:** 1.0  
**Date:** 2026-04-27  
**Status:** Living document — update as decisions are made  
**Server:** 209.38.84.102 (DigitalOcean, 2vCPU / 4GB RAM, Ubuntu)

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Architecture Diagram](#2-architecture-diagram)
3. [High-Level Design — Components](#3-high-level-design--components)
4. [Data Layer Design — 4-Layer Model](#4-data-layer-design--4-layer-model)
5. [Raw Zone Design](#5-raw-zone-design)
6. [Staging Layer Design](#6-staging-layer-design)
7. [Transform Layer Design](#7-transform-layer-design)
8. [Golden Record Design](#8-golden-record-design)
9. [Scripts and Jobs Design](#9-scripts-and-jobs-design)
10. [Pipeline Orchestration](#10-pipeline-orchestration)
11. [API Design](#11-api-design)
12. [Infrastructure Design](#12-infrastructure-design)
13. [Development Roadmap](#13-development-roadmap)
14. [Build Status — What Exists vs What Needs Building](#14-build-status)
15. [User Portal & RBAC](13_User_Portal_and_RBAC.md) — Free vs Paid access, saved screens, watchlists, Stripe

---

## 1. System Overview

The ASX Screener is a professional-grade stock screening platform for the Australian Securities Exchange (ASX), equivalent in scope and depth to screener.in (India) but designed specifically for Australian market conventions. The platform serves investors, analysts, and traders who need to filter, rank, and analyse the ~2,000 ASX-listed securities using fundamental, technical, and ASX-specific criteria including franking credits, mining company metrics, REIT data, and ASIC short-selling statistics.

The system is built around a **4-layer data architecture**: a Raw Zone (immutable gzipped files), a Staging layer (as-is database load), a Transform layer (clean, normalised, computed tables), and a Golden Record (a single denormalised screener table with ~458 pre-computed metrics per stock). This layered design means all expensive joins and computations happen in nightly batch jobs, and screener queries hit a single flat table with no joins, targeting sub-10ms response times at scale. The sole data provider is **EODHD** (End-of-Day Historical Data), an officially licensed ASX data vendor, which supplies end-of-day prices, full financial statements, dividends, splits, and company fundamentals.

The application stack is intentionally lean: Python 3.12 for all data pipelines and compute jobs, FastAPI + uvicorn for the backend API, Next.js for the frontend, and PostgreSQL 16 with TimescaleDB for the database. The entire stack runs on a single DigitalOcean droplet, sized to handle the ASX universe of ~2,000 stocks with room to scale. ASX-specific features — franking credits (unique to Australian dividend imputation), mining company ore reserves and AISC costs, REIT NAV and WALE metrics, ASX index membership (ASX20/50/100/200/300/All Ords), and ASIC daily short-selling data — are first-class citizens in the data model, not afterthoughts.

---

## 2. Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           EXTERNAL DATA SOURCES                              │
│                                                                               │
│   EODHD API (licensed)          ASIC Website         ASX Website             │
│   - /fundamentals/{ticker}.AU   - Daily short data   - Index membership      │
│   - /eod/{ticker}.AU            (CSV download)       (ASX20/50/100/200/300)  │
│   - /eod/bulk-download/AU                                                     │
│   - /div/{ticker}.AU                                                          │
│   - /splits/{ticker}.AU                                                       │
│   - /exchange-symbol-list/AU                                                  │
└──────────────────────────┬──────────────────────────────────────────────────┘
                           │  HTTP / REST
                           ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    LAYER 1 — RAW ZONE  (disk)                                │
│                                                                               │
│  /opt/asx-screener/data/raw/eodhd/exchange=AU/                               │
│                                                                               │
│  ├── fundamentals/full_snapshot/     {CODE}.AU_YYYY-MM-DD.json.gz            │
│  ├── eod_prices/historical/          {CODE}.AU_YYYY-MM-DD.json.gz            │
│  ├── eod_prices/incremental/         {YYYY-MM-DD}.json.gz (bulk)             │
│  ├── dividends/historical/           {CODE}.AU_YYYY-MM-DD.json.gz            │
│  ├── splits/historical/              {CODE}.AU_YYYY-MM-DD.json.gz            │
│  ├── symbol_list/                    exchange_AU_YYYY-MM-DD.json.gz          │
│  ├── audit/                          run manifests (JSON)                     │
│  ├── errors/                         failed calls (4xx, no data)             │
│  ├── quarantine/                     bad schema / manual review              │
│  └── retry/                          rate limits / 5xx / timeouts            │
│                                                                               │
│  Rules: immutable, never overwritten, never deleted,                          │
│         gzipped, date-stamped, checksum-verified                              │
└──────────────────────────┬──────────────────────────────────────────────────┘
                           │  load_to_staging_*.py (raw → DB, no transform)
                           ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    LAYER 2 — STAGING  (staging.* schema)                     │
│                                                                               │
│  Append-only raw load. Column names match EODHD fields exactly.              │
│  No transformations. is_latest / is_archived flags.                           │
│                                                                               │
│  staging.eod_prices          staging.income_statement                         │
│  staging.fundamentals        staging.balance_sheet                            │
│  staging.dividends           staging.cash_flow                                │
│  staging.splits              staging.earnings                                 │
│  staging.exchange_symbols    staging.company_profile                          │
│  staging.highlights          staging.valuation                                │
│  staging.analyst_ratings                                                      │
└──────────────────────────┬──────────────────────────────────────────────────┘
                           │  transform_*.py (clean, normalise, map)
                           ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                  LAYER 3 — TRANSFORM  (market.* + financials.* schemas)      │
│                                                                               │
│  Clean, normalised, standardised tables. Renamed columns.                    │
│  Compute jobs run here → write derived metrics.                               │
│                                                                               │
│  market.companies             financials.annual_pnl                           │
│  market.daily_prices          financials.annual_balance_sheet                 │
│  market.dividends             financials.annual_cashflow                      │
│  market.splits                financials.annual_ratios                        │
│  market.analyst_ratings       financials.quarterly_pnl                        │
│  market.exchange_list         financials.halfyearly_pnl                       │
│  market.exchange_details      financials.earnings_quarterly                   │
│  market.short_interest                                                        │
│  market.news                                                                  │
│                                                                               │
│  Compute outputs:                                                             │
│  market.daily_metrics         market.yearly_metrics                           │
│  market.weekly_metrics        market.quarterly_metrics                        │
│  market.monthly_metrics       market.halfyearly_metrics                       │
└──────────────────────────┬──────────────────────────────────────────────────┘
                           │  build_screener_universe.py
                           ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                  LAYER 4 — GOLDEN RECORD  (market.screener_universe)         │
│                                                                               │
│  1 row per stock. ~458 columns. Zero joins at query time.                    │
│  Rebuilt nightly. Sub-10ms screener queries.                                 │
│                                                                               │
│  26 categories: Identity, Price, Moving Averages, Momentum, Trend,           │
│  Volatility, Volume, Returns, Risk-Adjusted, P&L (FY0/FY1/FY2/TTM),         │
│  Margins, Balance Sheet, Per Share, Valuation, Returns on Capital,           │
│  Efficiency, Leverage, Quality Scores, Growth CAGRs, Avg Multiples,          │
│  Dividends, Short Interest, ASX-Specific, Quarterly, Insider Holdings         │
└──────────────────────────┬──────────────────────────────────────────────────┘
                           │  FastAPI (2 workers, uvicorn)
                           ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         API LAYER  (FastAPI)                                  │
│                                                                               │
│  POST /api/v1/screener          — Dynamic multi-filter screener              │
│  GET  /api/v1/screener/fields   — Available filter fields + operators        │
│  GET  /api/v1/companies/{code}  — Full company profile                       │
│  GET  /api/v1/companies/{code}/prices                                        │
│  GET  /api/v1/companies/{code}/financials                                    │
│  GET  /api/v1/companies/{code}/dividends                                     │
│  GET  /health                   — Health check                               │
└──────────────────────────┬──────────────────────────────────────────────────┘
                           │  JSON / REST
                           ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      FRONTEND  (Next.js)                                      │
│                                                                               │
│  Screener UI — filter builder, results table, column picker                   │
│  Company page — profile, charts, financials, dividends                        │
│  Preset screens — Value, Dividend, Quality, Growth, Technical                 │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. High-Level Design — Components

### 3.1 Component Inventory

| Component | Technology | Responsibility |
|-----------|-----------|----------------|
| Download scripts | Python 3.12 | Call EODHD API, write raw gzipped files to disk |
| Quality checker | Python 3.12 | Validate raw files before staging load |
| Audit logger | Python 3.12 | Write run manifests per dataset per date |
| Error handler | Python 3.12 | Route failed downloads to errors/quarantine/retry |
| Staging loaders | Python 3.12 | Load raw files as-is into staging.* schema |
| Transform jobs | Python 3.12 | Clean, normalise, rename: staging → market/financials |
| Compute jobs | Python 3.12 | Compute all ratios, indicators, scores, CAGRs |
| Universe builder | Python 3.12 | Flatten all sources into screener_universe (Golden Record) |
| FastAPI backend | Python 3.12 + FastAPI | REST API serving screener queries and company data |
| PostgreSQL 16 | PostgreSQL + TimescaleDB | Primary database; hypertables for time-series |
| Next.js frontend | TypeScript + Next.js | Screener UI, company pages |
| Scheduler | cron (system) | Nightly/weekly/monthly pipeline orchestration |
| Cold storage | DigitalOcean Spaces / S3 | Archive raw files older than 3 months |

### 3.2 Data Flow Summary

```
EODHD API
   → download scripts (Layer 1: raw gzipped files on disk)
   → quality_checks.py (validate each file)
   → audit_logger.py (write manifest)
   → load_to_staging scripts (Layer 2: append-only DB load)
   → transform scripts (Layer 3: clean + rename)
   → compute jobs (Layer 3: derive all metrics)
   → build_screener_universe.py (Layer 4: Golden Record)
   → FastAPI screener endpoint
   → Next.js UI
```

### 3.3 ASX-Specific Features

These features differentiate the product from generic screeners:

| Feature | Description | Implementation |
|---------|-------------|----------------|
| Franking credits | Australian dividend imputation — grossed-up yield | `franked_yield = dps * (1 + franking_pct/100 * 0.43/0.57) / price` |
| Grossed-up yield | Post-tax yield for superannuation funds | In screener_universe: `franked_yield` column |
| Mining depth | Ore reserves (oz), resources (oz), AISC per oz | `financials.mining_data` → `screener_universe.ore_reserve_oz` etc. |
| REIT metrics | NAV/unit, WALE, gearing, distribution yield, MER | `financials.reit_data` → `screener_universe.nav_per_share`, `wale_years` etc. |
| ASIC short data | Daily short position as % of float | `market.short_interest` → `screener_universe.short_interest_pct` |
| Index membership | ASX20/50/100/200/300/All Ords flags | `market.companies.is_asx200` etc. → screener filter |
| LIC/ETF NTA | Net Tangible Assets per share, discount/premium | `screener_universe.nta_per_share`, `nta_discount_premium` |
| Imputation credits | Per-share imputation credit dollar amount | `screener_universe.imputation_credit_per_share` |

---

## 4. Data Layer Design — 4-Layer Model

### Layer 1: Raw Zone (Disk)

**Purpose:** Immutable archive of every API response, exactly as received.  
**Location:** `/opt/asx-screener/data/raw/`  
**Format:** Gzipped JSON (`.json.gz`)  
**Rules:**
- Files are **never overwritten** — re-runs use new date stamps
- Files are **never deleted** — archive to cold storage after 3 months
- Every file has a corresponding audit entry
- Quality checks run **before** the file is committed to the output path

### Layer 2: Staging (staging.* schema)

**Purpose:** Load raw data into the database with zero transformation.  
**Rules:**
- Column names match EODHD field names exactly (snake_case mapping only)
- Append-only — no UPDATE or DELETE
- Every row has `loaded_at TIMESTAMPTZ`, `source_file TEXT`, `is_latest BOOLEAN`, `is_archived BOOLEAN`
- Deduplication via checksum on the raw content

### Layer 3: Transform (market.* + financials.* schemas)

**Purpose:** Clean, normalise, standardise field names to our schema; compute all derived metrics.  
**Rules:**
- Transform jobs read from staging, write to market/financials
- UPSERT on natural key (asx_code + date/fiscal_year)
- Compute jobs write to the metric tables (daily_metrics, yearly_metrics, etc.)
- Transform and compute are separate concerns — keep them in separate scripts

### Layer 4: Golden Record (market.screener_universe)

**Purpose:** One denormalised row per stock, zero joins at query time.  
**Rules:**
- Only `build_screener_universe.py` writes to this table
- Rebuilt nightly (full refresh for all ~2,000 stocks, or incremental for updated stocks)
- All ~458 columns must be populated or NULL — no computed-on-query columns
- Every screener query hits this table and this table only

---

## 5. Raw Zone Design

### 5.1 Folder Structure

```
/opt/asx-screener/data/raw/
└── eodhd/
    └── exchange=AU/
        ├── exchange_list/
        │   └── exchange_AU_YYYY-MM-DD.json.gz
        │
        ├── exchange_details/
        │   └── exchange_AU_YYYY-MM-DD.json.gz
        │
        ├── symbol_list/
        │   └── symbols_AU_YYYY-MM-DD.json.gz
        │
        ├── eod_prices/
        │   ├── historical/
        │   │   └── {CODE}.AU_YYYY-MM-DD.json.gz      (one file per stock per download)
        │   └── incremental/
        │       └── {YYYY-MM-DD}.json.gz               (bulk daily download, all stocks)
        │
        ├── fundamentals/
        │   ├── full_snapshot/
        │   │   └── {CODE}.AU_YYYY-MM-DD.json.gz      (one file per stock per download)
        │   └── incremental_snapshot/
        │       └── {YYYY-MM-DD}/
        │           └── {CODE}.AU.json.gz              (weekly refresh batch)
        │
        ├── dividends/
        │   ├── historical/
        │   │   └── {CODE}.AU_YYYY-MM-DD.json.gz
        │   └── incremental/
        │       └── {YYYY-MM-DD}.json.gz
        │
        ├── splits/
        │   ├── historical/
        │   │   └── {CODE}.AU_YYYY-MM-DD.json.gz
        │   └── incremental/
        │       └── {YYYY-MM-DD}.json.gz
        │
        ├── technical_indicators/
        │   └── {CODE}.AU_YYYY-MM-DD.json.gz
        │
        ├── news/
        │   └── incremental/
        │       └── {YYYY-MM-DD}.json.gz
        │
        ├── short_interest/                            (ASIC data, separate source)
        │   └── {YYYY-MM-DD}.csv.gz
        │
        ├── audit/
        │   └── {dataset}_{YYYY-MM-DD}.json           (run manifests)
        │
        ├── errors/
        │   └── {CODE}.AU_{YYYY-MM-DD}_{error_type}.json  (4xx, no data)
        │
        ├── quarantine/
        │   └── {CODE}.AU_{YYYY-MM-DD}_{reason}.json.gz   (bad schema — manual review)
        │
        └── retry/
            └── {CODE}.AU_{YYYY-MM-DD}_{attempt}.json      (5xx / timeout / rate limit)
```

### 5.2 File Naming Conventions

| Dataset | Pattern | Example |
|---------|---------|---------|
| Per-stock file | `{CODE}.AU_YYYY-MM-DD.json.gz` | `BHP.AU_2026-04-27.json.gz` |
| Bulk daily | `{YYYY-MM-DD}.json.gz` | `2026-04-27.json.gz` |
| Symbol list | `symbols_AU_YYYY-MM-DD.json.gz` | `symbols_AU_2026-04-27.json.gz` |
| Exchange details | `exchange_AU_YYYY-MM-DD.json.gz` | `exchange_AU_2026-04-27.json.gz` |
| Audit manifest | `{dataset}_{YYYY-MM-DD}.json` | `fundamentals_2026-04-27.json` |
| Error file | `{CODE}.AU_{DATE}_{type}.json` | `BHP.AU_2026-04-27_http404.json` |

### 5.3 Quality Checks

Every downloaded file must pass all checks before being written to its final output path. Failed files are routed immediately to `errors/` or `quarantine/`.

| Check | What it validates | Failure action |
|-------|------------------|----------------|
| HTTP status | Response was 200 OK | errors/ |
| Valid JSON | Parseable JSON content | quarantine/ |
| Not empty | Response is not `{}` or `[]` | errors/ |
| Symbol match | `General.Code` matches requested ticker | quarantine/ |
| Date freshness | `General.UpdatedAt` is recent (within 7 days) | quarantine/ |
| Completeness | Required top-level keys present | quarantine/ |
| Duplicate checksum | SHA-256 of content not already stored | skip (already have it) |
| File size | Size > 500 bytes (not a stub response) | quarantine/ |

**Checksum deduplication:** Before writing, compute SHA-256 of the gzip content. Check `audit/checksums.db` (SQLite) or the audit log. If already seen, skip write and log as `DUPLICATE`.

### 5.4 Error Handling

| Folder | Trigger | Behaviour |
|--------|---------|-----------|
| `errors/` | HTTP 4xx, empty response, zero records | Log, do not retry automatically |
| `quarantine/` | Schema mismatch, unexpected structure, date mismatch | Manual review required before re-loading |
| `retry/` | HTTP 5xx, connection timeout, rate limit (429) | Automatic retry max 3 times with exponential backoff |

**Retry logic:**
```
Attempt 1: wait 2s
Attempt 2: wait 8s
Attempt 3: wait 30s
After 3 failures → move to retry/ folder, log, continue to next stock
```

### 5.5 Audit Manifest Format

One JSON file per dataset per run date, written to `audit/`:

```json
{
  "run_id":       "fundamentals_2026-04-27_143022",
  "dataset":      "fundamentals",
  "run_date":     "2026-04-27",
  "started_at":   "2026-04-27T14:30:22Z",
  "finished_at":  "2026-04-27T19:15:44Z",
  "total_stocks": 1978,
  "success":      1954,
  "errors":       12,
  "quarantine":   8,
  "retried":      4,
  "skipped":      0,
  "files": [
    {"code": "BHP", "file": "BHP.AU_2026-04-27.json.gz", "size_bytes": 48221, "checksum": "sha256:abc123..."},
    ...
  ]
}
```

### 5.6 Data Retention Policy

| Zone | Retention | Action after retention period |
|------|-----------|-------------------------------|
| Raw Zone (disk) | 3 months local | Archive to DigitalOcean Spaces (S3-compatible), delete local |
| Staging (DB) | 12 months active | Move rows older than 12 months to archive DB schema; set `is_archived = TRUE` |
| Transform layer | Latest only | UPSERT — old values overwritten on each run |
| Golden Record | Latest only | Full rebuild nightly — no historical rows kept |

---

## 6. Staging Layer Design

The staging layer loads raw files with zero transformation. Column names follow EODHD's naming conventions (snake_case conversion only). Each load run **truncates** the target tables and reloads from the latest raw files — staging always holds the current snapshot, never historical rows.

### 6.1 Core Rules

**No business logic in staging.** No calculations, no renaming of values, no unit conversions, no nullability coercion beyond what the DB requires. The staging layer is a faithful DB representation of what EODHD returned.

**Truncate and Reload — not append-only.** History is preserved in the Raw Zone (the immutable gzipped files on disk). The DB does not need to store every historical snapshot — that would duplicate the Raw Zone and add `is_latest`/`is_archived` complexity for zero benefit in a screener. Staging is a transient landing pad for the Transform layer.

**Reload strategy by dataset:**

| Dataset | Strategy | Reason |
|---------|----------|--------|
| `staging.fundamentals` and all derived tables | `TRUNCATE … RESTART IDENTITY` (full run) | Weekly full refresh replaces all ~2,000 rows |
| `staging.eod_prices` (historical) | `TRUNCATE` (full run) | One-time historical load; incremental takes over |
| `staging.eod_prices` (incremental) | `DELETE WHERE date = target_date` then insert | Idempotent daily re-run without wiping all prices |
| `staging.dividends` | `TRUNCATE` (full run) | Dividend history is loaded as one full refresh |
| `staging.exchange_symbols` | `TRUNCATE` | Symbol list replaced on each sync |

**Partial runs** (`--codes`, `--date`, `--from-code`) do **not** truncate — they upsert into the live table. This allows refreshing a single stock without affecting others.

### 6.2 Table Definitions

#### staging.eod_prices

Source: `/eod/{ticker}.AU` (historical) and `/eod/bulk-download/AU` (incremental)

| Column | Type | Notes |
|--------|------|-------|
| id | BIGSERIAL PK | |
| asx_code | VARCHAR(10) | |
| date | DATE | EODHD `date` field |
| open | NUMERIC(12,4) | |
| high | NUMERIC(12,4) | |
| low | NUMERIC(12,4) | |
| close | NUMERIC(12,4) | |
| adjusted_close | NUMERIC(12,4) | |
| volume | BIGINT | |
| source_file | TEXT | filename of raw file |
| loaded_at | TIMESTAMPTZ | |

Unique constraint: `(asx_code, date)` — one row per stock per day.

#### staging.fundamentals

Source: `/fundamentals/{ticker}.AU` — stores the full raw JSON blob plus key extracted top-level fields for indexing.

| Column | Type | Notes |
|--------|------|-------|
| id | BIGSERIAL PK | |
| asx_code | VARCHAR(10) | |
| snapshot_date | DATE | date of download |
| raw_json | JSONB | full EODHD fundamentals response |
| general_code | VARCHAR(10) | `General.Code` |
| general_name | TEXT | `General.Name` |
| general_sector | TEXT | `General.Sector` |
| general_industry | TEXT | `General.Industry` |
| updated_at_eodhd | DATE | `General.UpdatedAt` |
| source_file | TEXT | |
| loaded_at | TIMESTAMPTZ | |
| checksum | VARCHAR(64) | SHA-256 of raw JSON |

Unique constraint: `(asx_code)` — one row per stock (truncate-and-reload means only the latest snapshot is kept).

Note: The `raw_json` JSONB column means all sub-sections (Financials, Highlights, Valuation, etc.) are accessible. Downstream extract tables (`staging.income_statement` etc.) are populated by parsing this blob.

#### staging.income_statement

Source: parsed from `staging.fundamentals.raw_json → Financials.Income_Statement.yearly`

| Column | Type | Notes |
|--------|------|-------|
| id | BIGSERIAL PK | |
| asx_code | VARCHAR(10) | |
| date | DATE | EODHD `date` field (period end) |
| period_type | VARCHAR(10) | 'yearly' or 'quarterly' |
| total_revenue | NUMERIC(20,4) | raw EODHD value |
| cost_of_revenue | NUMERIC(20,4) | |
| gross_profit | NUMERIC(20,4) | |
| total_operating_expenses | NUMERIC(20,4) | |
| operating_income | NUMERIC(20,4) | |
| ebitda | NUMERIC(20,4) | |
| interest_expense | NUMERIC(20,4) | |
| income_before_tax | NUMERIC(20,4) | |
| income_tax_expense | NUMERIC(20,4) | |
| net_income | NUMERIC(20,4) | |
| eps | NUMERIC(12,6) | |
| eps_diluted | NUMERIC(12,6) | |
| depreciation_amortization | NUMERIC(20,4) | |
| loaded_at | TIMESTAMPTZ | |

Unique constraint: `(asx_code, date, period_type)`

#### staging.balance_sheet

Source: parsed from `staging.fundamentals.raw_json → Financials.Balance_Sheet.yearly`

| Column | Type | Notes |
|--------|------|-------|
| id | BIGSERIAL PK | |
| asx_code | VARCHAR(10) | |
| date | DATE | |
| period_type | VARCHAR(10) | |
| total_assets | NUMERIC(20,4) | |
| total_current_assets | NUMERIC(20,4) | |
| cash_and_short_term_investments | NUMERIC(20,4) | |
| net_receivables | NUMERIC(20,4) | |
| inventory | NUMERIC(20,4) | |
| total_non_current_assets | NUMERIC(20,4) | |
| property_plant_equipment_net | NUMERIC(20,4) | |
| goodwill | NUMERIC(20,4) | |
| intangible_assets | NUMERIC(20,4) | |
| total_liabilities | NUMERIC(20,4) | |
| total_current_liabilities | NUMERIC(20,4) | |
| short_long_term_debt_total | NUMERIC(20,4) | |
| long_term_debt | NUMERIC(20,4) | |
| total_stockholder_equity | NUMERIC(20,4) | |
| retained_earnings | NUMERIC(20,4) | |
| common_stock | NUMERIC(20,4) | |
| loaded_at | TIMESTAMPTZ | |

Unique constraint: `(asx_code, date, period_type)`

#### staging.cash_flow

Source: parsed from `staging.fundamentals.raw_json → Financials.Cash_Flow.yearly`

| Column | Type | Notes |
|--------|------|-------|
| id | BIGSERIAL PK | |
| asx_code | VARCHAR(10) | |
| date | DATE | |
| period_type | VARCHAR(10) | |
| total_cash_from_operating_activities | NUMERIC(20,4) | |
| capital_expenditures | NUMERIC(20,4) | |
| total_cash_from_investing_activities | NUMERIC(20,4) | |
| total_cash_from_financing_activities | NUMERIC(20,4) | |
| dividends_paid | NUMERIC(20,4) | |
| change_to_cash | NUMERIC(20,4) | |
| free_cash_flow | NUMERIC(20,4) | |
| loaded_at | TIMESTAMPTZ | |

Unique constraint: `(asx_code, date, period_type)`

#### staging.earnings

Source: parsed from `staging.fundamentals.raw_json → Earnings`

| Column | Type | Notes |
|--------|------|-------|
| id | BIGSERIAL PK | |
| asx_code | VARCHAR(10) | |
| date | DATE | |
| period_type | VARCHAR(10) | 'actual' or 'estimate' |
| eps_actual | NUMERIC(12,6) | |
| eps_estimate | NUMERIC(12,6) | |
| eps_difference | NUMERIC(12,6) | |
| surprise_percent | NUMERIC(8,4) | |
| loaded_at | TIMESTAMPTZ | |

Unique constraint: `(asx_code, date, period_type)`

#### staging.dividends

Source: `/div/{ticker}.AU`

| Column | Type | Notes |
|--------|------|-------|
| id | BIGSERIAL PK | |
| asx_code | VARCHAR(10) | |
| date | DATE | ex-dividend date |
| dividend | NUMERIC(12,6) | adjusted amount (EODHD "dividends" field) |
| unadjusted_value | NUMERIC(12,6) | |
| currency | VARCHAR(5) | |
| source_file | TEXT | |
| loaded_at | TIMESTAMPTZ | |

Unique constraint: `(asx_code, date)`

#### staging.splits

Source: `/splits/{ticker}.AU`

| Column | Type | Notes |
|--------|------|-------|
| id | BIGSERIAL PK | |
| asx_code | VARCHAR(10) | |
| date | DATE | |
| split | VARCHAR(20) | e.g. '2:1' |
| source_file | TEXT | |
| loaded_at | TIMESTAMPTZ | |

Unique constraint: `(asx_code, date)`

#### staging.exchange_symbols

Source: `/exchange-symbol-list/AU`

| Column | Type | Notes |
|--------|------|-------|
| id | BIGSERIAL PK | |
| code | VARCHAR(10) | ASX code |
| name | TEXT | |
| country | VARCHAR(5) | |
| exchange | VARCHAR(10) | |
| currency | VARCHAR(5) | |
| type | VARCHAR(30) | 'Common Stock', 'ETF', etc. |
| isin | VARCHAR(20) | |
| snapshot_date | DATE | |
| source_file | TEXT | |
| loaded_at | TIMESTAMPTZ | |

Unique constraint: `(code)`

#### staging.company_profile

Source: parsed from `staging.fundamentals.raw_json → General`

| Column | Type | Notes |
|--------|------|-------|
| id | BIGSERIAL PK | |
| asx_code | VARCHAR(10) | |
| snapshot_date | DATE | |
| code | VARCHAR(10) | |
| type | VARCHAR(20) | |
| name | TEXT | |
| exchange | VARCHAR(10) | |
| currency_code | VARCHAR(5) | |
| country_name | TEXT | |
| isin | VARCHAR(20) | |
| cusip | VARCHAR(20) | |
| cik | VARCHAR(20) | |
| employer_id_number | VARCHAR(20) | |
| fiscal_year_end | VARCHAR(20) | e.g. 'June' |
| ipo_date | DATE | |
| sector | TEXT | |
| industry | TEXT | |
| gic_sector | TEXT | |
| gic_group | TEXT | |
| gic_industry | TEXT | |
| gic_sub_industry | TEXT | |
| description | TEXT | |
| address | TEXT | |
| phone | TEXT | |
| web_url | TEXT | |
| full_time_employees | INTEGER | |
| updated_at | DATE | EODHD field |
| source_file | TEXT | |
| loaded_at | TIMESTAMPTZ | |

Unique constraint: `(asx_code)` — one current row per stock.

#### staging.highlights

Source: parsed from `staging.fundamentals.raw_json → Highlights`

Key EODHD fields stored as-is: `MarketCapitalization`, `EBITDA`, `PERatio`, `PEGRatio`, `WallStreetTargetPrice`, `BookValue`, `DividendShare`, `DividendYield`, `EarningsShare`, `EPSEstimateCurrentYear`, `RevenuePerShareTTM`, `ProfitMargin`, `OperatingMarginTTM`, `ReturnOnAssetsTTM`, `ReturnOnEquityTTM`, `RevenueTTM`, `GrossProfitTTM`, `DilutedEpsTTM`, `QuarterlyEarningsGrowthYOY`, `QuarterlyRevenueGrowthYOY`.

Unique constraint: `(asx_code)` — one row per stock.

#### staging.valuation

Source: parsed from `staging.fundamentals.raw_json → Valuation`

Key fields: `TrailingPE`, `ForwardPE`, `PriceSalesTTM`, `PriceBookMRQ`, `EnterpriseValue`, `EnterpriseValueRevenue`, `EnterpriseValueEbitda`.

Unique constraint: `(asx_code)` — one row per stock.

#### staging.analyst_ratings

Source: parsed from `staging.fundamentals.raw_json → AnalystRatings`

| Column | Type | Notes |
|--------|------|-------|
| asx_code | VARCHAR(10) | |
| snapshot_date | DATE | |
| rating | NUMERIC(4,2) | |
| target_price | NUMERIC(12,4) | |
| strong_buy | INTEGER | |
| buy | INTEGER | |
| hold | INTEGER | |
| sell | INTEGER | |
| strong_sell | INTEGER | |
| loaded_at | TIMESTAMPTZ | |

Unique constraint: `(asx_code)` — one row per stock.

---

## 7. Transform Layer Design

### 7.1 Design Principles

- Transform scripts read from `staging.*` and write to `market.*` or `financials.*`
- Field names use our standard snake_case naming (not EODHD's mixed case)
- Units are standardised: financial values in **AUD millions**, ratios as **decimals or percentages explicitly named**
- Currency: all values converted to AUD at load time (EODHD returns AUD for ASX)
- `market.companies` uses **SCD Type 2** to track company attribute changes over time
- All other transform tables use **UPSERT** on natural key (asx_code + date/fiscal_year)
- Financials tables carry a `data_as_of TIMESTAMPTZ` column for lightweight restatement tracking

### 7.2 Market Schema Tables

#### market.companies — SCD Type 2

The authoritative company reference table. Uses Slowly Changing Dimension Type 2 to capture changes to sector classification, stock type, fiscal year end, and status over time.

**Why SCD Type 2?** ASX companies frequently change GICS sector (reclassification), convert stock type (equity → REIT or stapled security), change fiscal year end, or transition to delisted/suspended. Without history, a sector change would silently corrupt all historical screener results.

**SCD Type 2 columns:**

| Column | Type | Notes |
|--------|------|-------|
| id | BIGSERIAL PK | surrogate key |
| asx_code | VARCHAR(10) | natural key — NOT unique alone |
| valid_from | DATE NOT NULL | date this version became active |
| valid_to | DATE | NULL = currently active version |
| is_current | BOOLEAN | TRUE for the active version only |

**Partial unique index:** `UNIQUE (asx_code) WHERE is_current = TRUE` — only one current row per stock, DB-enforced.

**Tracked fields** (a change in any of these creates a new version):

| Field | Why tracked |
|-------|-------------|
| `gics_sector` | Sector reclassifications are common |
| `gics_industry_group` | |
| `gics_industry` | |
| `gics_sub_industry` | |
| `stock_type` | equity → REIT conversions, stapling events |
| `status` | active → suspended → delisted |
| `fiscal_year_end_month` | Changes affect how financials are dated |
| `is_reit` | |
| `is_miner` | |

**Non-tracked fields** (updated in-place on the current row, no new version):

`company_name`, `short_name`, `isin`, `website`, `employee_count`, `description`, `is_asx20/50/100/200/300/all_ords` (index membership changes too frequently to version).

**Convenience view:** `market.companies_current` — `SELECT * FROM market.companies WHERE is_current = TRUE`. Use this for all screener queries.

**All columns:**

| Column | Type | Notes |
|--------|------|-------|
| id | BIGSERIAL PK | surrogate key |
| asx_code | VARCHAR(10) | |
| company_name | TEXT | |
| short_name | TEXT | |
| isin | VARCHAR(20) | |
| abn | VARCHAR(20) | |
| asx_sector | TEXT | ASX GICS sector |
| gics_sector | TEXT | **SCD2-tracked** |
| gics_industry_group | TEXT | **SCD2-tracked** |
| gics_industry | TEXT | **SCD2-tracked** |
| gics_sub_industry | TEXT | **SCD2-tracked** |
| stock_type | TEXT | 'equity', 'reit', 'lic', 'etf', 'stapled' — **SCD2-tracked** |
| listing_date | DATE | |
| status | TEXT | 'active', 'suspended', 'delisted' — **SCD2-tracked** |
| fiscal_year_end_month | SMALLINT | 6=June, 12=December — **SCD2-tracked** |
| website | TEXT | |
| employee_count | INTEGER | |
| description | TEXT | |
| country_of_incorporation | VARCHAR(50) | |
| is_reit | BOOLEAN DEFAULT FALSE | **SCD2-tracked** |
| is_miner | BOOLEAN DEFAULT FALSE | **SCD2-tracked** |
| is_asx20 | BOOLEAN DEFAULT FALSE | updated in-place |
| is_asx50 | BOOLEAN DEFAULT FALSE | updated in-place |
| is_asx100 | BOOLEAN DEFAULT FALSE | updated in-place |
| is_asx200 | BOOLEAN DEFAULT FALSE | updated in-place |
| is_asx300 | BOOLEAN DEFAULT FALSE | updated in-place |
| is_all_ords | BOOLEAN DEFAULT FALSE | updated in-place |
| valid_from | DATE NOT NULL | SCD2: date this version became active |
| valid_to | DATE | SCD2: NULL = currently active |
| is_current | BOOLEAN NOT NULL | SCD2: TRUE for active version |
| created_at | TIMESTAMPTZ | first time this stock was loaded |
| updated_at | TIMESTAMPTZ | last in-place update timestamp |

#### market.daily_prices

TimescaleDB hypertable, partitioned by time. One row per stock per trading day.

| Column | Type | Notes |
|--------|------|-------|
| time | TIMESTAMPTZ | Partition key (TimescaleDB) |
| asx_code | VARCHAR(10) | |
| open | NUMERIC(12,4) | |
| high | NUMERIC(12,4) | |
| low | NUMERIC(12,4) | |
| close | NUMERIC(12,4) | |
| adjusted_close | NUMERIC(12,4) | Split and dividend adjusted |
| volume | BIGINT | |

Unique constraint: `(asx_code, time)`

#### market.dividends

| Column | Type | Notes |
|--------|------|-------|
| asx_code | VARCHAR(10) | |
| ex_date | DATE | |
| amount | NUMERIC(12,6) | AUD per share |
| franking_pct | NUMERIC(5,2) | 0–100 |
| record_date | DATE | |
| pay_date | DATE | |
| period | VARCHAR(20) | 'final', 'interim', 'special' |
| currency | VARCHAR(5) | |

#### market.splits

| Column | Type | Notes |
|--------|------|-------|
| asx_code | VARCHAR(10) | |
| split_date | DATE | |
| ratio_from | NUMERIC(10,4) | |
| ratio_to | NUMERIC(10,4) | |
| description | TEXT | e.g. '2:1' |

#### market.analyst_ratings

| Column | Type |
|--------|------|
| asx_code | VARCHAR(10) |
| snapshot_date | DATE |
| consensus_rating | NUMERIC(4,2) |
| target_price | NUMERIC(12,4) |
| strong_buy | INTEGER |
| buy | INTEGER |
| hold | INTEGER |
| sell | INTEGER |
| strong_sell | INTEGER |
| updated_at | TIMESTAMPTZ |

#### market.short_interest

Source: ASIC daily short position files (CSV download from asic.gov.au)

| Column | Type | Notes |
|--------|------|-------|
| asx_code | VARCHAR(10) | |
| report_date | DATE | |
| short_position_shares | BIGINT | |
| total_issued_shares | BIGINT | |
| short_pct_of_issued | NUMERIC(8,4) | % |
| product_name | TEXT | |

#### market.exchange_list / market.exchange_details

Reference tables for exchange metadata. Rarely updated (monthly).

### 7.3 Financials Schema Tables

All financial values in **AUD millions**. Fiscal year = calendar year of June 30 end (ASX standard: FY2024 = July 2023 – June 2024).

**Restatement tracking:** Financial tables use UPSERT — a restatement from EODHD overwrites the prior value for that fiscal year. The `data_as_of TIMESTAMPTZ` column records when the row was last loaded, providing a lightweight audit trail. Full SCD Type 2 is not applied to financial tables because: (1) the fiscal year is already a natural point-in-time key; (2) financial restatements are uncommon; (3) the screener does not backtest on historical financial data.

#### financials.annual_pnl

One row per stock per fiscal year. Source of truth for P&L.

| Column | Type | Notes |
|--------|------|-------|
| asx_code | VARCHAR(10) | |
| fiscal_year | SMALLINT | e.g. 2024 |
| period_end_date | DATE | e.g. 2024-06-30 |
| revenue | NUMERIC(18,2) | AUD M |
| cost_of_revenue | NUMERIC(18,2) | |
| gross_profit | NUMERIC(18,2) | |
| gross_margin | NUMERIC(8,4) | % |
| ebitda | NUMERIC(18,2) | |
| depreciation | NUMERIC(18,2) | |
| ebit | NUMERIC(18,2) | operating profit |
| interest_expense | NUMERIC(18,2) | |
| other_income | NUMERIC(18,2) | |
| pbt | NUMERIC(18,2) | profit before tax |
| tax | NUMERIC(18,2) | |
| net_profit | NUMERIC(18,2) | PAT |
| minority_interest | NUMERIC(18,2) | |
| eps | NUMERIC(10,4) | AUD |
| eps_diluted | NUMERIC(10,4) | |
| dps | NUMERIC(10,4) | dividends per share AUD |
| dps_franking_pct | NUMERIC(5,2) | 0–100 |
| shares_outstanding | BIGINT | |
| updated_at | TIMESTAMPTZ | last upsert timestamp |
| data_as_of | TIMESTAMPTZ | when row was last loaded from EODHD |

Unique constraint: `(asx_code, fiscal_year)`

#### financials.annual_balance_sheet

| Column | Type | Notes |
|--------|------|-------|
| asx_code | VARCHAR(10) | |
| fiscal_year | SMALLINT | |
| period_end_date | DATE | |
| total_assets | NUMERIC(18,2) | AUD M |
| total_current_assets | NUMERIC(18,2) | |
| cash_equivalents | NUMERIC(18,2) | |
| trade_receivables | NUMERIC(18,2) | |
| inventory | NUMERIC(18,2) | |
| total_non_current_assets | NUMERIC(18,2) | |
| net_block | NUMERIC(18,2) | net PPE |
| gross_block | NUMERIC(18,2) | |
| accumulated_depreciation | NUMERIC(18,2) | |
| goodwill | NUMERIC(18,2) | |
| intangibles | NUMERIC(18,2) | |
| total_liabilities | NUMERIC(18,2) | |
| total_current_liab | NUMERIC(18,2) | |
| total_non_current_liab | NUMERIC(18,2) | |
| short_term_debt | NUMERIC(18,2) | |
| long_term_debt | NUMERIC(18,2) | |
| trade_payables | NUMERIC(18,2) | |
| total_equity | NUMERIC(18,2) | |
| retained_earnings | NUMERIC(18,2) | |
| equity_capital | NUMERIC(18,2) | paid-up capital |
| total_debt | NUMERIC(18,2) | short + long term |
| net_debt | NUMERIC(18,2) | total_debt - cash |
| book_value_per_share | NUMERIC(10,4) | |
| shares_outstanding | BIGINT | |
| updated_at | TIMESTAMPTZ | |
| data_as_of | TIMESTAMPTZ | when row was last loaded from EODHD |

Unique constraint: `(asx_code, fiscal_year)`

#### financials.annual_cashflow

| Column | Type | Notes |
|--------|------|-------|
| asx_code | VARCHAR(10) | |
| fiscal_year | SMALLINT | |
| period_end_date | DATE | |
| cfo | NUMERIC(18,2) | operating cash flow |
| cfi | NUMERIC(18,2) | investing cash flow |
| cff | NUMERIC(18,2) | financing cash flow |
| capex | NUMERIC(18,2) | capital expenditure |
| fcf | NUMERIC(18,2) | cfo + capex (capex is negative) |
| dividends_paid | NUMERIC(18,2) | |
| net_change_in_cash | NUMERIC(18,2) | |
| cash_end | NUMERIC(18,2) | |
| updated_at | TIMESTAMPTZ | |
| data_as_of | TIMESTAMPTZ | when row was last loaded from EODHD |

Unique constraint: `(asx_code, fiscal_year)`

#### financials.quarterly_pnl / financials.halfyearly_pnl

Same structure as `annual_pnl` with an additional `quarter` (1-4) or `half` (1-2) column and `period_type` column.

#### financials.earnings_quarterly

Analyst estimates vs actuals for quarterly earnings surprises.

#### financials.annual_ratios

Pre-computed ratios at annual level (populated by `compute_yearly.py`). This table is a mirror of the key outputs from `market.yearly_metrics` at the financial level, kept for historical ratio lookup.

### 7.4 Compute Metric Tables

All metric tables share the same pattern: `(asx_code, time)` unique key, UPSERT on each run.

#### market.daily_metrics

Populated by `compute_daily.py`. One row per stock per trading day.

Categories computed:
- Moving averages: SMA 5/10/20/50/100/200, EMA 12/20/26/50/200
- Momentum: RSI 7/14/21, MACD (line/signal/hist), Stochastic K/D, CCI, Williams %R, ROC, MFI
- Trend: ADX 14, +DI/-DI, Aroon Up/Down/Oscillator
- Volatility: ATR 14, Bollinger Bands (upper/mid/lower/%B/width), Historical Vol 20d/60d
- Volume: OBV, VWAP, CMF 20
- Signals: golden cross, death cross, new 52W high/low, above SMA flags

#### market.weekly_metrics / monthly_metrics

Weekly and monthly OHLCV aggregates, plus derived metrics at those timeframes (weekly RSI, monthly momentum, etc.).

#### market.yearly_metrics

Populated by `compute_yearly.py`. One row per stock per fiscal year. ~120 columns covering:
- All valuation ratios (PE, PB, PS, PCF, P/FCF, EV/EBITDA, EV/EBIT, EV/Revenue, PEG, Graham Number)
- Return on capital (ROE, ROA, ROIC, ROCE, CROIC)
- All margins (gross, EBITDA, EBIT, pretax, net, OCF, FCF)
- All efficiency ratios (asset turnover, DSO, DIO, DPO, CCC)
- All leverage/liquidity ratios (current, quick, cash ratio, D/E, D/Assets, ND/EBITDA, ICR)
- Quality scores: Piotroski F-Score (0-9), Altman Z-Score, Beneish M-Score
- Multi-year CAGRs (3Y/5Y/7Y/10Y) for revenue, net income, EPS, EBITDA, FCF, BVPS, DPS, price
- Multi-year averages (3Y/5Y/7Y/10Y) for ROE, ROA, ROIC, ROCE, all margins
- Risk: beta 1Y/3Y/5Y, volatility 1Y/3Y, Sharpe 1Y/3Y

#### market.quarterly_metrics / halfyearly_metrics

Quarterly and half-yearly P&L metrics extracted from EODHD's quarterly financial data.

---

## 8. Golden Record Design

### 8.1 Table: market.screener_universe

**Location:** Currently `market.screener_universe`. To be moved to `screener.universe` in a future migration once the `staging` schema work is complete.

**Built by:** `jobs/build_screener_universe.py`  
**Rebuilt:** Nightly, after all compute jobs complete  
**Rows:** ~2,000 (one per active ASX stock)  
**Columns:** ~458 pre-computed metrics  

### 8.2 Column Categories

| Category | Column Range | Source Table | Count |
|----------|-------------|--------------|-------|
| CAT 1 — Stock Identity | asx_code → fiscal_year_end_month | market.companies | 22 |
| CAT 2 — Price & Market | last_price → relative_volume | market.daily_prices | 24 |
| CAT 3 — Moving Averages | sma_5 → above_sma200 | market.daily_metrics | 20 |
| CAT 4 — Momentum & Oscillators | rsi_7 → momentum_6m | market.daily_metrics | 18 |
| CAT 5 — Trend Indicators | adx_14 → new_52w_low | market.daily_metrics | 10 |
| CAT 6 — Volatility | atr_14 → true_range | market.daily_metrics | 14 |
| CAT 7 — Volume & Breadth | obv → avg_volume_1y | market.daily_metrics | 8 |
| CAT 8 — Price Returns | return_1d → price_cagr_10y | daily/monthly metrics | 14 |
| CAT 9 — Risk-Adjusted | sharpe_1y → relative_strength_xjo | market.yearly_metrics | 10 |
| CAT 10 — P&L FY0 | revenue → dividend_paid_total | financials.annual_pnl | 24 |
| CAT 10b — P&L FY1 | revenue_fy1 → gross_margin_fy1 | financials.annual_pnl | 14 |
| CAT 10c — P&L FY2 | revenue_fy2 → net_margin_fy2 | financials.annual_pnl | 6 |
| CAT 10d — TTM | revenue_ttm, net_income_ttm | quarterly aggregation | 2 |
| CAT 11 — Margin Ratios | gross_margin → tax_rate_effective | market.yearly_metrics | 8 |
| CAT 12 — Balance Sheet FY0 | total_assets → book_value_per_share | financials.annual_balance_sheet | 34 |
| CAT 12b — Balance Sheet FY1 | total_debt_fy1 → net_block_fy1 | financials.annual_balance_sheet | 3 |
| CAT 12c — Balance Sheet Historical | total_debt_3y → net_block_7y | financials.annual_balance_sheet | 11 |
| CAT 13 — Per Share | eps → net_debt_per_share | financials.annual_pnl + yearly_metrics | 10 |
| CAT 14 — Valuation Ratios | pe_ratio → graham_number | market.yearly_metrics | 18 |
| CAT 15 — Return on Capital | roe → roaa | market.yearly_metrics | 6 |
| CAT 16 — Efficiency | asset_turnover → capex_intensity | market.yearly_metrics | 9 |
| CAT 17 — Leverage & Liquidity | current_ratio → altman_z_score | market.yearly_metrics | 12 |
| CAT 18 — Quality Scores | piotroski_f_score → quality_score | market.yearly_metrics | 5 |
| CAT 19 — Multi-Year CAGRs | revenue_cagr_3y → dividend_cagr_5y | market.yearly_metrics | 26 |
| CAT 20 — Multi-Year Averages | avg_roe_3y → avg_current_ratio_3y | market.yearly_metrics | 28 |
| CAT 20b — Avg Values | avg_ebit_5y, avg_ebit_10y | market.yearly_metrics | 2 |
| CAT 21 — Dividend & Income | dps_ttm → dividend_growth_streak | pnl + yearly_metrics | 8 |
| CAT 21b — Cash Flow FY1 | ocf_fy1 → cash_end_fy1 | financials.annual_cashflow | 6 |
| CAT 21c — Cash Flow Historical | fcf_3y → cash_7y | financials.annual_cashflow | 15 |
| CAT 22 — Short Selling | short_interest_pct → short_change_1m | market.short_interest | 5 |
| CAT 23 — ASX-Specific | nta_per_share → cash_cost_per_oz | reit_data / mining_data | 12 |
| CAT 24 — Quarterly Metrics | revenue_latest_q → ebit_margin_same_q_prior_yr | market.quarterly_metrics | 29 |
| CAT 25 — Insider Holdings | insider_holding_pct → insider_holding_change_1y | market.companies | 3 |
| CAT 26 — Metadata | price_date → stale_flag | computed at build time | 10 |

**Total: ~458 columns**

### 8.3 Key Indexes

Partial indexes on `is_active = TRUE` for all screener-critical columns:

```sql
-- Single-column indexes for individual filters
CREATE INDEX idx_su_pe           ON market.screener_universe (pe_ratio);
CREATE INDEX idx_su_roe          ON market.screener_universe (roe);
CREATE INDEX idx_su_market_cap   ON market.screener_universe (market_cap);
CREATE INDEX idx_su_franked_yield ON market.screener_universe (franked_yield);
CREATE INDEX idx_su_piotroski    ON market.screener_universe (piotroski_f_score);
-- ... (40+ individual indexes)

-- Composite indexes for common combined filters
CREATE INDEX idx_su_value_screen   ON market.screener_universe (pe_ratio, dividend_yield, market_cap) WHERE is_active = TRUE;
CREATE INDEX idx_su_quality_screen ON market.screener_universe (avg_roce_5y, debt_to_equity) WHERE is_active = TRUE AND is_profitable = TRUE;
CREATE INDEX idx_su_growth_screen  ON market.screener_universe (revenue_cagr_5y, net_income_cagr_5y) WHERE is_active = TRUE;
CREATE INDEX idx_su_tech_screen    ON market.screener_universe (rsi_14, dma50_ratio, dma200_ratio) WHERE is_active = TRUE;
```

### 8.4 Build Script Logic

`jobs/build_screener_universe.py` runs as the final step each night:

1. Get list of all active stocks from `market.companies`
2. For each stock (in batches of 200):
   - Load company profile
   - Load latest daily price row
   - Load latest daily_metrics row
   - Load latest weekly, monthly metrics
   - Load yearly_metrics (latest FY)
   - Load annual_pnl (FY0, FY1, FY2, FY3, FY5, FY7, FY10)
   - Load annual_balance_sheet (same years)
   - Load annual_cashflow (same years)
   - Load short_interest (latest)
   - Load reit_data / mining_data (if applicable)
   - Load quarterly_metrics (latest 4 quarters)
   - Assemble all into one dict
   - Upsert into `market.screener_universe`
3. Mark stale rows (`stale_flag = TRUE` for price > 3 days old)
4. Log build stats (total, success, failed, duration)

---

## 9. Scripts and Jobs Design

### 9.1 Folder Structure

```
scripts/
└── eodhd/
    ├── utils/                            [TO BUILD]
    │   ├── quality_checks.py             [TO BUILD]
    │   ├── audit_logger.py               [TO BUILD]
    │   └── error_handler.py              [TO BUILD]
    │
    ├── download/                         [TO BUILD — proper versions]
    │   ├── download_fundamentals.py      [TO BUILD]
    │   ├── download_eod_prices.py        [TO BUILD]
    │   ├── download_daily_bulk_prices.py [TO BUILD]
    │   ├── download_dividends.py         [TO BUILD]
    │   ├── download_splits.py            [TO BUILD]
    │   └── download_exchange_symbols.py  [TO BUILD]
    │
    ├── load/                             [TO BUILD]
    │   ├── load_to_staging_fundamentals.py  [TO BUILD]
    │   ├── load_to_staging_prices.py        [TO BUILD]
    │   ├── load_to_staging_dividends.py     [TO BUILD]
    │   └── load_to_staging_splits.py        [TO BUILD]
    │
    └── [legacy — bypass staging, to be retired]
        ├── download_historical_fundamentals.py   [EXISTS]
        ├── download_historical_prices.py         [EXISTS]
        ├── download_historical_dividends.py      [EXISTS]
        ├── download_daily_prices.py              [EXISTS]
        ├── download_daily_fundamentals.py        [EXISTS]
        ├── load_fundamentals.py                  [EXISTS — bypasses staging]
        ├── load_prices.py                        [EXISTS — bypasses staging]
        └── load_dividends.py                     [EXISTS — bypasses staging]

jobs/
├── transform/                            [TO BUILD]
│   ├── transform_companies.py            [TO BUILD]
│   ├── transform_prices.py               [TO BUILD]
│   ├── transform_financials.py           [TO BUILD]
│   └── transform_dividends.py            [TO BUILD]
│
└── compute/
    ├── compute_daily.py                  [EXISTS]
    ├── compute_weekly.py                 [EXISTS]
    ├── compute_monthly.py                [EXISTS]
    ├── compute_yearly.py                 [EXISTS — comprehensive]
    ├── compute_quarterly.py              [EXISTS]
    ├── compute_halfyearly.py             [EXISTS]
    └── build_screener_universe.py        [EXISTS]
```

### 9.2 Script Descriptions

#### utils/quality_checks.py

```
Inputs: raw file path (or bytes)
Outputs: QualityResult(passed: bool, checks: list[Check], error_bucket: str)

Checks performed:
  1. http_status_ok         — HTTP 200 confirmed in metadata
  2. valid_json             — json.loads() succeeds
  3. not_empty              — result is not {} or [] or None
  4. symbol_match           — General.Code == requested ticker
  5. date_freshness         — General.UpdatedAt within 7 days
  6. required_keys_present  — General, Highlights, Financials keys exist
  7. checksum_duplicate     — SHA-256 not in audit log (skip if duplicate)
  8. min_file_size          — bytes > 500

Failure routing:
  http errors, not_empty → errors/
  schema, symbol, date   → quarantine/
  (5xx handled by caller before quality_checks)
```

#### utils/audit_logger.py

```
Maintains run manifests in raw/eodhd/exchange=AU/audit/
One JSON file per dataset per run date.

Functions:
  start_run(dataset, run_date)           → run_id
  log_file(run_id, code, path, checksum) → None
  log_error(run_id, code, reason)        → None
  log_quarantine(run_id, code, reason)   → None
  finish_run(run_id, stats)              → writes manifest JSON
  load_checksum_db()                     → set of known checksums
  add_checksum(checksum)                 → None
```

#### utils/error_handler.py

```
Routes failed downloads to correct folder based on failure type.
Writes error metadata JSON alongside failed files.
Manages the retry queue.

Functions:
  route_error(code, date, response, failure_type) → writes to errors/ or quarantine/
  add_to_retry_queue(code, date, attempt)         → writes to retry/
  process_retry_queue()                            → re-runs items in retry/ up to max_retries
  clear_old_retry_files(max_age_days=7)           → cleanup
```

#### download scripts (new proper versions)

Each download script follows this pattern:
1. Load config (API key, raw base path, date)
2. Load list of stocks to process (from DB or from prior symbol file)
3. Call `audit_logger.start_run()`
4. For each stock:
   a. Call EODHD API
   b. On 5xx/timeout: call `error_handler.add_to_retry_queue()`; continue
   c. On success: run `quality_checks.validate(response)`
   d. If failed quality: route via `error_handler.route_error()`; continue
   e. Write `.json.gz` to correct raw zone folder
   f. Call `audit_logger.log_file()`
5. Process retry queue (max 3 attempts)
6. Call `audit_logger.finish_run()`

#### load_to_staging scripts

Each script reads from the raw zone and loads into staging, with NO transformation:

```
load_to_staging_fundamentals.py:
  - Reads all .json.gz files from fundamentals/full_snapshot/ for a given date
  - Parses each file
  - Inserts into staging.fundamentals (full blob + key fields)
  - Extracts and inserts sub-sections:
      staging.income_statement  (Financials.Income_Statement.yearly)
      staging.balance_sheet     (Financials.Balance_Sheet.yearly)
      staging.cash_flow         (Financials.Cash_Flow.yearly)
      staging.earnings          (Earnings)
      staging.company_profile   (General)
      staging.highlights        (Highlights)
      staging.valuation         (Valuation)
      staging.analyst_ratings   (AnalystRatings)
  - Marks previous rows as is_latest = FALSE before inserting new rows
  - Logs counts to audit
```

#### transform scripts

```
transform_companies.py:
  - Reads staging.company_profile + staging.exchange_symbols (is_latest = TRUE)
  - Maps EODHD fields to market.companies columns
  - Derives is_reit, is_miner from sector/industry
  - Upserts into market.companies

transform_prices.py:
  - Reads staging.eod_prices (is_latest = TRUE, new rows only)
  - Validates prices (close > 0, volume >= 0)
  - Upserts into market.daily_prices (TimescaleDB hypertable)

transform_financials.py:
  - Reads staging.income_statement, balance_sheet, cash_flow (is_latest = TRUE)
  - Applies field renaming and unit standardisation
  - Derives: fiscal_year from period_end_date, gross_margin, net_debt, fcf
  - Upserts into financials.annual_pnl, annual_balance_sheet, annual_cashflow

transform_dividends.py:
  - Reads staging.dividends (is_latest = TRUE)
  - Maps to market.dividends
  - Note: franking_pct not in EODHD dividend API — sourced from fundamentals SplitsDividends section
```

#### compute jobs (existing, maintained)

| Script | Frequency | Runtime | What it computes |
|--------|-----------|---------|-----------------|
| compute_yearly.py | After financial load | ~30 min | ~120 valuation, margin, efficiency, leverage, quality, CAGR, risk metrics per FY per stock |
| compute_halfyearly.py | After financial load | ~10 min | Half-year P&L comparisons |
| compute_quarterly.py | After financial load | ~10 min | Quarterly P&L, QoQ and YoY growth |
| compute_monthly.py | Nightly | ~5 min | Monthly OHLCV aggregates, monthly returns |
| compute_weekly.py | Nightly | ~5 min | Weekly OHLCV aggregates, weekly momentum |
| compute_daily.py | Nightly | ~15 min | All technical indicators (SMA, EMA, RSI, MACD, Bollinger, etc.) |
| build_screener_universe.py | Nightly (last) | ~20 min | Flatten all sources into Golden Record |

---

## 10. Pipeline Orchestration

### 10.1 Nightly Pipeline (every weekday, after ASX close ~4:00 PM AEST)

```
17:00 AEST  download_daily_bulk_prices.py
             → downloads bulk EOD for today (all ASX stocks, one API call)
             → writes to raw/eod_prices/incremental/{date}.json.gz

17:15 AEST  load_to_staging_prices.py
             → loads today's bulk prices into staging.eod_prices

17:20 AEST  transform_prices.py
             → staging.eod_prices → market.daily_prices

17:30 AEST  compute_daily.py
             → market.daily_prices → market.daily_metrics (all technicals)

17:45 AEST  compute_weekly.py
             → market.daily_prices → market.weekly_metrics

17:50 AEST  compute_monthly.py
             → market.daily_prices → market.monthly_metrics

18:00 AEST  build_screener_universe.py
             → all compute tables → market.screener_universe

18:20 AEST  [DONE] — screener data is fresh for today
```

### 10.2 Weekly Pipeline (Sundays 08:00 AEST)

```
08:00  download_fundamentals.py (recent reporters — stocks that filed results this week)
08:30  download_dividends.py (all stocks — weekly refresh)
09:00  download_exchange_symbols.py (weekly symbol universe refresh)
09:10  load_to_staging_fundamentals.py
09:40  load_to_staging_dividends.py
10:00  transform_companies.py (update company metadata)
10:10  transform_financials.py (update P&L/BS/CF)
10:20  transform_dividends.py
10:30  compute_yearly.py (recompute ratios for updated stocks)
11:00  compute_halfyearly.py
11:10  compute_quarterly.py
11:20  build_screener_universe.py (full rebuild with updated fundamentals)
```

### 10.3 Monthly Pipeline (1st of month, 06:00 AEST)

```
06:00  download_exchange_details.py (exchange metadata)
06:10  Full symbol universe refresh (download_exchange_symbols.py --full)
06:20  load_to_staging_* (all datasets)
07:00  transform_companies.py (full company refresh)
07:10  [run nightly pipeline as normal]
```

### 10.4 One-Time Historical Load (run once)

```
[Step 1] download_exchange_symbols.py   → symbol universe
[Step 2] load_to_staging_*              → staging tables
[Step 3] transform_companies.py         → market.companies

[Step 4] download_fundamentals.py --all → 3-5 hours for ~2,000 stocks
[Step 5] load_to_staging_fundamentals.py
[Step 6] transform_financials.py

[Step 7] download_eod_prices.py --all   → historical OHLCV
[Step 8] load_to_staging_prices.py
[Step 9] transform_prices.py

[Step 10] download_dividends.py --all
[Step 11] load_to_staging_dividends.py
[Step 12] transform_dividends.py

[Step 13] download_splits.py --all
[Step 14] load_to_staging_splits.py

[Step 15] compute_yearly.py --mode historical   → all FYs for all stocks
[Step 16] compute_halfyearly.py --mode historical
[Step 17] compute_quarterly.py --mode historical
[Step 18] compute_monthly.py
[Step 19] compute_weekly.py
[Step 20] compute_daily.py
[Step 21] build_screener_universe.py
```

### 10.5 Cron Schedule (system cron on droplet)

```cron
# Nightly (weekdays) — 5:00 PM AEST = 07:00 UTC
0 7 * * 1-5  /opt/asx-screener/scripts/run_nightly.sh >> /opt/asx-screener/logs/nightly.log 2>&1

# Weekly — Sunday 8:00 AM AEST = Sunday 22:00 UTC (Saturday)
0 22 * * 6   /opt/asx-screener/scripts/run_weekly.sh >> /opt/asx-screener/logs/weekly.log 2>&1

# Monthly — 1st of month 6:00 AM AEST = 20:00 UTC prior day
0 20 28-31 * *  [ "$(date +\%d -d tomorrow)" = "01" ] && /opt/asx-screener/scripts/run_monthly.sh
```

---

## 11. API Design

### 11.1 Base URL

```
Production:  https://asxscreener.com.au/api/v1
Development: http://localhost:8000/api/v1
```

### 11.2 Implemented Endpoints

#### POST /api/v1/screener

Run a stock screen with dynamic filters. Queries `market.screener_universe` exclusively.

**Request:**
```json
{
  "filters": [
    {"field": "sector",       "operator": "eq",  "value": "Materials"},
    {"field": "pe_ratio",     "operator": "lt",  "value": 20},
    {"field": "roe",          "operator": "gte", "value": 15},
    {"field": "market_cap",   "operator": "gte", "value": 100},
    {"field": "franked_yield","operator": "gte", "value": 4}
  ],
  "sort_by":   "market_cap",
  "sort_dir":  "desc",
  "page":      1,
  "page_size": 50
}
```

**Response:**
```json
{
  "data": [
    {
      "asx_code": "BHP",
      "company_name": "BHP Group Limited",
      "gics_sector": "Materials",
      "close": 45.12,
      "market_cap": 142000.0,
      "pe_ratio": 12.4,
      "roe": 22.1,
      "franked_yield": 6.8
    }
  ],
  "total": 12,
  "page": 1,
  "page_size": 50,
  "total_pages": 1,
  "filters_applied": 5
}
```

**Supported filter operators:** `gt`, `gte`, `lt`, `lte`, `eq`, `neq`, `in`

**Filterable fields (current):** sector, gics_sector, industry, is_reit, is_miner, is_asx200, is_asx300, is_all_ords, close, open, high, low, volume, high_52w, low_52w, change_pct, market_cap, pe_ratio, pb_ratio, ps_ratio, ev_ebitda, dividend_yield, grossed_up_yield, franking_pct, roe, roa, roce, roic, opm, npm, debt_to_equity, current_ratio, revenue_growth_1y, revenue_growth_3y, profit_growth_1y, profit_growth_3y, piotroski_score, altman_z_score, short_interest_pct, beta_1y

#### GET /api/v1/screener/fields

Returns all filterable fields with type metadata, grouped by category. Used by the frontend to build the filter UI dynamically.

#### GET /api/v1/companies/{asx_code}

Full company profile. Queries `market.companies` + `market.screener_universe`.

#### GET /api/v1/companies/{asx_code}/prices

Historical daily OHLCV. Queries `market.daily_prices`.  
Parameters: `from_date`, `to_date`, `interval` (daily/weekly/monthly)

#### GET /api/v1/companies/{asx_code}/financials

Annual P&L, Balance Sheet, Cash Flow. Queries `financials.*`.  
Parameters: `years` (default 10), `period_type` (annual/quarterly/half)

#### GET /api/v1/companies/{asx_code}/dividends

Full dividend history with franking credits. Queries `market.dividends`.

#### GET /health

Returns `{"status": "ok", "version": "...", "environment": "..."}`. Used by load balancer health checks.

### 11.3 Planned Endpoints (Phase 2+)

| Endpoint | Description |
|----------|-------------|
| GET /api/v1/screener/presets | Built-in screens (Value, Dividend, Quality, Growth, Technical) |
| GET /api/v1/companies/{code}/technicals | Technical indicators |
| GET /api/v1/companies/{code}/peers | Peer comparison |
| GET /api/v1/companies/{code}/analyst | Analyst ratings and targets |
| GET /api/v1/indices/{index} | Index constituents (ASX20/50/100/200/300) |
| GET /api/v1/sector/{sector} | Sector summary and comparison |
| POST /api/v1/watchlist | Watchlist management (requires auth) |
| GET /api/v1/search | Company search with autocomplete |

### 11.4 Technical Details

- **Framework:** FastAPI with SQLAlchemy async
- **Workers:** 2 uvicorn workers (sized for 4GB RAM droplet)
- **Connection pool:** SQLAlchemy async with pool_size=5, max_overflow=10
- **SQL injection prevention:** Field whitelist via `ALLOWED_FIELDS` dict; parameterised queries only
- **CORS:** `localhost:3000` (dev), `asxscreener.com.au` (prod)
- **Docs:** `/docs` (Swagger UI) enabled in DEBUG mode only

---

## 12. Infrastructure Design

### 12.1 Server

| Property | Value |
|----------|-------|
| Provider | DigitalOcean |
| Region | Sydney (syd1) — closest to ASX data |
| Droplet | 2 vCPU / 4GB RAM / 80GB SSD |
| IP | 209.38.84.102 |
| OS | Ubuntu 22.04 LTS |
| Python | 3.12 |

### 12.2 Database

| Property | Value |
|----------|-------|
| Engine | PostgreSQL 16 |
| Extension | TimescaleDB (time-series hypertables) |
| Extension | pgvector (AI embeddings, future) |
| Extension | pg_trgm (text search, company name) |
| Extension | pg_stat_statements (query monitoring) |
| Database | asx_screener |
| User | asx_user |
| Schemas | market, financials, staging, screener, users, ai, meta, public |

**TimescaleDB hypertables:** `market.daily_prices` (partitioned by 1 month chunks)

**DB sizing estimate:**

| Table | Rows | Size estimate |
|-------|------|---------------|
| market.daily_prices | 2,000 stocks × 30Y × 252 trading days | ~15M rows / ~3GB |
| market.daily_metrics | same as prices | ~15M rows / ~5GB |
| financials.annual_pnl | 2,000 × 30 years | 60K rows / ~50MB |
| market.screener_universe | 2,000 | 2,000 rows / ~20MB |
| staging.fundamentals (JSON) | 2,000 × weekly snapshots | ~10GB/year |
| **Total estimate** | | **~25-30GB active** |

### 12.3 Storage Layout

```
/opt/asx-screener/
├── data/
│   └── raw/                          # Raw zone (Layer 1)
│       └── eodhd/exchange=AU/        # ~5-10GB/year of gzipped files
├── logs/                             # Pipeline job logs
├── scripts/                          # Download and load scripts
├── jobs/                             # Transform and compute jobs
├── backend/                          # FastAPI application
└── frontend/                         # Next.js application (or separate server)
```

### 12.4 Cold Storage (Archive)

- **Provider:** DigitalOcean Spaces (S3-compatible)
- **Region:** syd1 (same region as droplet — no egress fees)
- **Bucket:** `asx-screener-raw-archive`
- **Trigger:** Files older than 3 months moved automatically by monthly archive script
- **Cost:** ~$0.02/GB/month — negligible for ~10GB/year

### 12.5 Process Management

```
# FastAPI backend — managed by systemd
/etc/systemd/system/asx-screener-api.service
ExecStart=/opt/asx-screener/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2

# Next.js frontend — managed by PM2 or systemd
/etc/systemd/system/asx-screener-frontend.service
ExecStart=/usr/bin/node /opt/asx-screener/frontend/.next/standalone/server.js
```

### 12.6 Nginx (Reverse Proxy)

```nginx
# /etc/nginx/sites-available/asxscreener.com.au
server {
    server_name asxscreener.com.au www.asxscreener.com.au;

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
    }

    location / {
        proxy_pass http://127.0.0.1:3000;
    }
}
```

---

## 13. Development Roadmap

### Phase 0 — Foundation Cleanup (Priority: IMMEDIATE)

**Goal:** Fix the existing data pipeline to use the 4-layer architecture properly.

| Task | Effort | Status |
|------|--------|--------|
| Create `staging.*` schema and all staging tables | M | NOT STARTED |
| Build `utils/quality_checks.py` | S | NOT STARTED |
| Build `utils/audit_logger.py` | S | NOT STARTED |
| Build `utils/error_handler.py` | S | NOT STARTED |
| Restructure raw zone folder layout to agreed spec | S | NOT STARTED |
| Build proper download scripts (with quality checks) | M | IN PROGRESS (partial) |
| Build `load_to_staging_*` scripts | M | NOT STARTED |
| Build `transform_*` scripts | M | NOT STARTED |
| Migrate existing data: populate staging from current raw files | L | NOT STARTED |
| Add `screener.*` schema (rename from `market.screener_universe`) | S | NOT STARTED |

### Phase 1 — Data Pipeline Complete (Target: 2 weeks)

**Goal:** Full 4-layer pipeline running nightly without manual intervention.

| Task | Effort | Status |
|------|--------|--------|
| Run historical data load through new pipeline | L | NOT STARTED |
| Set up cron jobs for nightly/weekly/monthly | S | NOT STARTED |
| Set up ASIC short interest data download | M | NOT STARTED |
| Set up DigitalOcean Spaces cold storage archival | S | NOT STARTED |
| Pipeline monitoring (log alerts, stale data flags) | M | NOT STARTED |
| Test full pipeline end-to-end | M | NOT STARTED |

### Phase 2 — API Completion (Target: 3 weeks from Phase 0 done)

**Goal:** All planned API endpoints implemented, tested, and documented.

| Task | Effort | Status |
|------|--------|--------|
| Expand screener to all 458 filterable fields | M | PARTIAL (30 fields done) |
| GET /companies/{code} full company page | M | NOT STARTED |
| GET /companies/{code}/prices with intervals | S | NOT STARTED |
| GET /companies/{code}/financials | M | NOT STARTED |
| GET /companies/{code}/dividends | S | NOT STARTED |
| GET /screener/presets (built-in screens) | S | NOT STARTED |
| GET /search with pg_trgm autocomplete | S | NOT STARTED |
| API rate limiting (slowapi) | S | NOT STARTED |
| API response caching (Redis or in-memory) | M | NOT STARTED |
| Screener query logging (what users filter on) | S | NOT STARTED |

### Phase 3 — Frontend (Target: 4 weeks from Phase 2 done)

**Goal:** Screener UI live with core features.

| Task | Effort | Status |
|------|--------|--------|
| Screener filter builder UI | L | NOT STARTED |
| Results table with sortable columns | M | NOT STARTED |
| Column picker (show/hide metrics) | M | NOT STARTED |
| Preset screens (Value, Dividend, Growth, Quality) | M | NOT STARTED |
| Company profile page | L | NOT STARTED |
| Price chart (TradingView Lightweight Charts) | M | NOT STARTED |
| Financial statements tables | M | NOT STARTED |
| Dividend history with franking credit display | M | NOT STARTED |
| Mobile responsive design | M | NOT STARTED |
| Export to CSV | S | NOT STARTED |

### Phase 4 — ASX-Specific Depth (Target: ongoing)

| Task | Effort |
|------|--------|
| REIT: NAV, WALE, gearing, distribution yield | M |
| Mining: ore reserves, resources, AISC per oz | M |
| ASIC short selling data integration | M |
| Index membership (ASX20/50/100/200/300) | S |
| Imputation credit calculator | S |
| LIC: NTA discount/premium | M |

### Phase 5 — Premium Features (Future)

| Task | Effort |
|------|--------|
| User accounts + watchlists | L |
| Saved screens | M |
| Email alerts | M |
| AI-powered stock summaries (pgvector + Claude) | L |
| Peer comparison tool | M |
| Portfolio tracker | L |

**Effort key:** S = Small (<1 day), M = Medium (2-5 days), L = Large (1-2 weeks)

---

## 14. Build Status

### 14.1 What Exists

| Component | Location | Status | Notes |
|-----------|----------|--------|-------|
| PostgreSQL schemas (market, financials) | migrations/001 | DONE | |
| market.companies | migrations/002 | DONE | |
| market.daily_prices (hypertable) | migrations/003 | DONE | |
| market.dividends, splits, analyst_ratings | migrations/004, 012 | DONE | |
| financials.annual_pnl, balance_sheet, cashflow | migrations/005 | DONE | |
| market.daily_metrics | migrations/008 | DONE | |
| market.weekly/monthly/yearly/quarterly_metrics | migrations/008 | DONE | |
| market.screener_universe (~458 cols) | migrations/009, 011 | DONE | |
| FastAPI app (main.py, router) | backend/app/ | DONE | |
| POST /screener with 30 filter fields | backend/app/api/v1/routes/screener.py | DONE | |
| GET /screener/fields | backend/app/api/v1/routes/screener.py | DONE | |
| compute_yearly.py (comprehensive) | jobs/compute/ | DONE | |
| compute_daily.py | jobs/compute/ | DONE | |
| compute_weekly.py | jobs/compute/ | DONE | |
| compute_monthly.py | jobs/compute/ | DONE | |
| compute_quarterly.py | jobs/compute/ | DONE | |
| compute_halfyearly.py | jobs/compute/ | DONE | |
| build_screener_universe.py | jobs/ | DONE | |
| download_historical_fundamentals.py | scripts/eodhd/ | DONE (legacy) | Bypasses staging |
| download_historical_prices.py | scripts/eodhd/ | DONE (legacy) | Bypasses staging |
| download_historical_dividends.py | scripts/eodhd/ | DONE (legacy) | Bypasses staging |
| download_daily_prices.py | scripts/eodhd/ | DONE (legacy) | Bypasses staging |
| load_fundamentals.py | scripts/eodhd/ | DONE (legacy) | Bypasses staging |
| load_prices.py | scripts/eodhd/ | DONE (legacy) | Bypasses staging |
| Next.js project structure | frontend/ | SCAFFOLDED | No screener UI yet |
| Raw zone files (partial data) | data/raw/ | PARTIAL | Wrong folder layout |

### 14.2 What Needs Building

| Component | Priority | Phase |
|-----------|----------|-------|
| staging.* schema (13 tables) | P0 — CRITICAL | Phase 0 |
| utils/quality_checks.py | P0 — CRITICAL | Phase 0 |
| utils/audit_logger.py | P0 — CRITICAL | Phase 0 |
| utils/error_handler.py | P0 — CRITICAL | Phase 0 |
| Restructure raw zone folders to spec | P0 | Phase 0 |
| Proper download scripts (with quality checks + audit) | P0 | Phase 0 |
| load_to_staging_fundamentals.py | P0 | Phase 0 |
| load_to_staging_prices.py | P0 | Phase 0 |
| load_to_staging_dividends.py | P0 | Phase 0 |
| load_to_staging_splits.py | P0 | Phase 0 |
| transform_companies.py | P0 | Phase 0 |
| transform_prices.py | P0 | Phase 0 |
| transform_financials.py | P0 | Phase 0 |
| transform_dividends.py | P0 | Phase 0 |
| screener.* schema (rename from market.*) | P1 | Phase 0 |
| Cron job setup (nightly/weekly/monthly) | P1 | Phase 1 |
| ASIC short interest downloader | P1 | Phase 1 |
| Cold storage archival script | P2 | Phase 1 |
| Expand screener to 458 fields | P1 | Phase 2 |
| GET /companies/{code} endpoint | P1 | Phase 2 |
| GET /companies/{code}/prices endpoint | P1 | Phase 2 |
| GET /companies/{code}/financials endpoint | P1 | Phase 2 |
| GET /companies/{code}/dividends endpoint | P1 | Phase 2 |
| GET /search endpoint | P2 | Phase 2 |
| GET /screener/presets endpoint | P2 | Phase 2 |
| Screener UI (filter builder + results table) | P1 | Phase 3 |
| Company profile page | P1 | Phase 3 |
| Price chart component | P2 | Phase 3 |
| Financials tables component | P2 | Phase 3 |
| Dividend history display | P2 | Phase 3 |
| REIT-specific metrics pipeline | P3 | Phase 4 |
| Mining-specific metrics pipeline | P3 | Phase 4 |
| ASIC short data pipeline | P2 | Phase 4 |

---

## Appendix A: EODHD API Reference

| Endpoint | Purpose | Call frequency | Rate cost |
|----------|---------|----------------|-----------|
| `GET /fundamentals/{ticker}.AU` | Full company fundamentals | Weekly per stock | 1 call |
| `GET /eod/{ticker}.AU` | Historical OHLCV per stock | Historical once | 1 call |
| `GET /eod/bulk-download/AU?date={date}` | All ASX stocks for one day | Daily | 1 call total |
| `GET /div/{ticker}.AU` | Full dividend history | Historical + weekly | 1 call |
| `GET /splits/{ticker}.AU` | Full split history | Historical + monthly | 1 call |
| `GET /exchange-symbol-list/AU` | All ASX tickers | Weekly | 1 call |
| `GET /exchange-details/AU` | Exchange metadata | Monthly | 1 call |

**EODHD ALL-IN-ONE plan:** 100,000 API calls/day  
**Historical load estimate:** ~2,000 stocks × 5 endpoints = 10,000 calls (~10% of daily limit)  
**Daily nightly:** 1 bulk EOD call + ~2,000 weekly fundamentals spread over 7 days ≈ 290/day sustained

---

## Appendix B: Compute Job Sequence

The compute jobs must run in this order each nightly cycle:

```
Seq 1: transform_prices.py          (must run before any compute)
Seq 2: compute_yearly.py            (requires: annual_pnl, balance_sheet, cashflow, daily_prices)
Seq 3: compute_halfyearly.py        (requires: halfyearly_pnl)
Seq 4: compute_quarterly.py         (requires: quarterly_pnl)
Seq 5: compute_monthly.py           (requires: daily_prices)
Seq 6: compute_weekly.py            (requires: daily_prices)
Seq 7: compute_daily.py             (requires: daily_prices — most computationally intensive)
Seq 8: build_screener_universe.py   (requires: ALL compute tables complete)
```

Note: Seq 2-4 only need to run when new financial data has been loaded. On price-only nightly runs (no new fundamentals), skip Seq 2-4.

---

## Appendix C: Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Data provider | EODHD | Officially licensed, comprehensive ASX data, reasonable cost |
| Raw storage | Gzipped JSON on disk | Immutable, cheap, reconstructable, no DB dependency |
| Staging approach | Append-only, no transform | Audit trail, replay capability, separation of concerns |
| Golden Record | Single flat table, no joins | Sub-10ms screener queries, simple API code |
| Time-series DB | TimescaleDB on PostgreSQL | Best-in-class PostgreSQL extension, not a separate system |
| Financial units | AUD millions | Consistent with ASX company reporting, avoids integer overflow |
| Fiscal year convention | Calendar year of June 30 | Standard ASX convention (FY2024 = ends June 30, 2024) |
| Screening architecture | Filter whitelist + parameterised SQL | SQL injection prevention, no ORM overhead for screener |
| Backend workers | 2 uvicorn workers | Sized for 4GB RAM; can increase when RAM is upgraded |
| Franking credits | Stored as %, grossed-up yield computed | Matches ATO and ASX reporting conventions |

---

*Document maintained by the ASX Screener development team. Last updated: 2026-04-27.*
