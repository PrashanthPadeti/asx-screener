# Starting a New Project — Checklist

Use this checklist when bootstrapping a new screener project (e.g. India Nifty,
US Screener) or any other project on this data platform.

Completing this checklist correctly ensures the new project is:
- Fully isolated from all existing projects
- Reading from the shared Bronze Raw Zone
- Using the correct schema naming convention
- Schedulable without interfering with existing pipelines

---

## Before You Start

- [ ] Read [01_platform_overview.md](01_platform_overview.md) — understand the full architecture
- [ ] Read [03_naming_conventions.md](03_naming_conventions.md) — confirm your market code and schema names
- [ ] Confirm which exchanges and data sources you need (EODHD exchanges, market-specific providers)
- [ ] Confirm Bronze data is already being downloaded for your market, OR coordinate with the platform team to add a new download job

---

## Step 1 — Database Setup

### 1.1 Create schemas

```sql
-- Replace {market} with your market code: au, in, us, etc.
CREATE SCHEMA IF NOT EXISTS stg_{market};
CREATE SCHEMA IF NOT EXISTS mkt_{market};
CREATE SCHEMA IF NOT EXISTS fin_{market};
CREATE SCHEMA IF NOT EXISTS screener_{market};
```

### 1.2 Create a dedicated DB role

```sql
-- Create role (replace {market})
CREATE ROLE screener_{market}_app LOGIN PASSWORD 'your_strong_password';

-- Grant access to own schemas only
GRANT USAGE, CREATE ON SCHEMA stg_{market}     TO screener_{market}_app;
GRANT USAGE, CREATE ON SCHEMA mkt_{market}     TO screener_{market}_app;
GRANT USAGE, CREATE ON SCHEMA fin_{market}     TO screener_{market}_app;
GRANT USAGE, CREATE ON SCHEMA screener_{market} TO screener_{market}_app;

-- Grant read-only on shared infra (auth)
GRANT USAGE ON SCHEMA users TO screener_{market}_app;
GRANT SELECT ON ALL TABLES IN SCHEMA users TO screener_{market}_app;

-- IMPORTANT: Do NOT grant access to other projects' schemas
-- No access to stg_au, mkt_au, fin_au, screener_au (or any other market)
```

### 1.3 Verify isolation

```sql
-- This should fail (role cannot see other project's data)
SET ROLE screener_{market}_app;
SELECT * FROM mkt_au.daily_prices LIMIT 1;  -- should return permission denied
RESET ROLE;
```

---

## Step 2 — Database Migrations

Create numbered migration files in `database/migrations/`:

```
001_extensions_and_schemas.sql     -- CREATE EXTENSION timescaledb; CREATE SCHEMA ...
002_stg_{market}_tables.sql        -- Staging tables
003_mkt_{market}_companies.sql     -- Companies master table
004_mkt_{market}_timeseries.sql    -- TimescaleDB hypertables
005_fin_{market}_tables.sql        -- Financial statement tables
006_screener_{market}_universe.sql -- Golden Record table
```

Run migrations in order:

```bash
for f in database/migrations/*.sql; do
    psql $DATABASE_URL -f "$f" && echo "Applied: $f"
done
```

---

## Step 3 — Project Directory Structure

Mirror the ASX Screener structure, adapting for your market:

```
{market}-screener/
├── backend/
│   ├── app/
│   │   ├── api/v1/routes/
│   │   │   └── screener.py         ← API endpoint
│   │   ├── schemas/
│   │   │   └── screener.py         ← Pydantic models
│   │   └── core/
│   │       └── cache.py
│   └── migrations/
├── compute/
│   └── engine/
│       ├── daily_compute.py        ← writes to mkt_{market}.computed_metrics
│       └── yearly_compute.py       ← writes to mkt_{market}.yearly_metrics
├── scripts/
│   └── {provider}/
│       └── v1/
│           ├── download_eod_prices.py
│           ├── load_to_staging_prices.py
│           ├── transform_daily_prices.py
│           └── build_screener_universe.py
├── jobs/
│   └── daily_pipeline.py           ← orchestrates all steps
├── database/
│   └── migrations/
├── docs/
│   └── architecture/               ← copy from asx-screener/docs/architecture/
└── .env
```

---

## Step 4 — Environment Variables

Add to your project's `.env`:

```bash
# Database (project-specific role)
DATABASE_URL_SYNC=postgresql://screener_{market}_app:password@localhost:5432/asx_screener

# Data lake (shared path — read only)
DATA_LAKE_PATH=/opt/data-lake/raw

# Provider API keys (may be shared with other projects via platform .env)
EODHD_API_KEY=your_key

# Redis namespace (use project-specific DB number)
REDIS_URL=redis://localhost:6379/{db_number}
# AU=1, IN=2, US=3, Charts=4

# Market identifier (used in logging and cache keys)
MARKET_CODE={market}   # au, in, us
```

---

## Step 5 — Staging Ingestion

Your staging ingestion script reads from the Bronze Raw Zone and loads
into your project's `stg_{market}.*` tables.

Key pattern:

```python
# ALWAYS read from the shared data lake path
DATA_LAKE = Path(os.getenv("DATA_LAKE_PATH", "/opt/data-lake/raw"))

# ALWAYS write into your own staging schema
STAGING_SCHEMA = f"stg_{MARKET_CODE}"

# Read manifest to find today's file
manifest_path = DATA_LAKE / "eodhd" / f"exchange={EXCHANGE}" / "audit" / f"eod_prices_{run_date}_*.json"

# Validate checksum before loading
validate_checksum(file_path, manifest["files"][0]["checksum"])

# Load into staging
cur.execute(f"INSERT INTO {STAGING_SCHEMA}.eod_prices (...) VALUES ...")
```

**Never hardcode the data lake path.** Always use the `DATA_LAKE_PATH` env var.

---

## Step 6 — Transform Layer

The transform layer reads from `stg_{market}.*` and writes to `mkt_{market}.*`.

Follow the ASX Screener patterns:
- `mkt_{market}.daily_prices` is a TimescaleDB hypertable partitioned by time
- `mkt_{market}.daily_metrics` stores pre-computed technical indicators
- Use `ON CONFLICT (asx_code, time) DO UPDATE SET ...` for upserts
  - For other markets: `ON CONFLICT ({ticker_col}, time) DO UPDATE SET ...`

The ticker column name for each market:

| Market | Ticker column name | Example value |
|---|---|---|
| AU | `asx_code` | `BHP` |
| IN | `nse_code` | `RELIANCE` |
| US | `ticker` | `AAPL` |

---

## Step 7 — Compute Engine

The compute engine calculates derived metrics (margins, CAGR, quality scores)
and writes to `mkt_{market}.yearly_metrics` and `mkt_{market}.computed_metrics`.

Copy the ASX Screener compute engines as a starting point:
- `compute/engine/yearly_compute.py` → adapt for your market's accounting standard
- `compute/engine/daily_compute.py` → mostly universal, minor column name changes

Market-specific additions (beyond the universal set):
- **India**: Add promoter_holdings_pct, pledged_pct, fii_net_buy columns to yearly_metrics
- **US**: Add insider_buy_signal, institutional_ownership_change columns

---

## Step 8 — Golden Record (screener.universe equivalent)

Your project's Golden Record is `screener_{market}.universe`.

It must follow the same pattern as `screener_au.universe`:
- One row per instrument
- All columns pre-joined and denormalised
- Rebuilt nightly via `build_screener_universe.py`
- Single `INSERT ... ON CONFLICT DO UPDATE SET` query (not multiple queries)
- TCP keepalives on the psycopg2 connection (long-running query protection):

```python
conn = psycopg2.connect(
    DATABASE_URL,
    keepalives=1,
    keepalives_idle=30,
    keepalives_interval=10,
    keepalives_count=5,
    options="-c statement_timeout=0",
)
```

Standard columns that every screener universe must have:

```sql
-- Identity
ticker, company_name, sector, industry, stock_type, status,
is_large, is_mid, is_small, is_micro, is_nano, market_cap_tier,

-- Price
price, price_date, volume, avg_volume_20d, market_cap, high_52w, low_52w,

-- Valuation
pe_ratio, forward_pe, price_to_book, price_to_sales, ev_to_ebitda,
price_to_fcf, fcf_yield,

-- Dividends
dividend_yield, dps_ttm, payout_ratio,

-- Profitability
gross_margin, ebitda_margin, net_margin, operating_margin,
roe, roa, roce,

-- Growth
revenue_growth_1y, revenue_growth_3y_cagr, earnings_growth_1y,
eps_cagr_5y, ebitda_growth_1y, fcf_growth_1y,

-- Balance Sheet
debt_to_equity, current_ratio, net_debt_to_ebitda, interest_coverage,

-- Technicals
rsi_14, macd, macd_signal, sma_50, sma_200, adx_14,
above_sma50, above_sma200, golden_cross, death_cross,
dma50_ratio, dma200_ratio, relative_volume,

-- Returns
return_1w, return_1m, return_3m, return_6m, return_1y, return_ytd,
drawdown_from_ath, volatility_20d, beta_1y,

-- Quality
piotroski_f_score, altman_z_score,

-- Metadata
universe_built_at
```

Add market-unique columns on top of this standard set.

---

## Step 9 — API Backend

Copy the ASX Screener backend pattern:
- `POST /api/v1/{market}/screener` — run a screen
- `GET  /api/v1/{market}/screener/fields` — list filterable fields
- `GET  /api/v1/{market}/screener/presets` — pre-built templates

The `ALLOWED_FIELDS` registry approach (field → SQL column mapping) is mandatory.
Never accept raw column names from API clients.

Cache key prefix must use your market code:

```python
CACHE_PREFIX = f"{MARKET_CODE}:screener:"   # e.g. "in:screener:" or "us:screener:"
```

---

## Step 10 — Pipeline Orchestration

Create `jobs/daily_pipeline.py` following the ASX Screener pattern:

```python
Steps:
  1. Download bulk EOD prices       → Bronze (read-only from data lake)
  2. Load staging prices            → stg_{market}.*
  3. Transform daily prices         → mkt_{market}.daily_prices
  4. Daily compute engine           → mkt_{market}.computed_metrics
  4b. Technical compute engine      → mkt_{market}.daily_metrics
  4c. Yearly compute engine         → mkt_{market}.yearly_metrics (weekly or as needed)
  5. Build screener.universe        → screener_{market}.universe
```

---

## Step 11 — Crontab Registration

Add your pipeline to the **server crontab** (not PM2 for scheduled tasks):

```bash
crontab -e
```

Add (adjust time for your market's close):
```
# {Market} Screener daily pipeline
{minute} {hour} * * 1-5 cd /opt/{market}-screener && /opt/{market}-screener/venv/bin/python jobs/daily_pipeline.py >> /opt/{market}-screener/logs/daily_pipeline_{market}.log 2>&1
```

**Do not share a crontab entry with another project.** Each project has its own
cron line, its own log file, and runs independently.

---

## Step 12 — Verification Checklist

Before going live, verify:

- [ ] `SELECT COUNT(*) FROM screener_{market}.universe;` returns expected number of stocks
- [ ] `SELECT * FROM screener_{market}.universe LIMIT 5;` shows sensible data (no all-nulls rows)
- [ ] API returns 200 on `POST /api/v1/{market}/screener` with empty filters
- [ ] DB role isolation verified (role cannot read other market schemas)
- [ ] Crontab entry added with correct market log file
- [ ] Redis cache key prefix uses market code (not shared with other projects)
- [ ] `.env` uses project-specific DB role (not `asx_user` or another project's role)
- [ ] `docs/architecture/` copied into project repo
- [ ] Build script uses TCP keepalives (see Step 8)

---

## What NOT to Do

| Do not | Reason |
|---|---|
| Read from `mkt_au.*` in the India project | Cross-project dependency — breaks isolation |
| Use the `asx_user` DB role in a new project | Gives access to ASX data — use a new role |
| Write Bronze files from a project pipeline | Only `datalake_ingest` writes to Bronze |
| Share a log file with another project | Makes debugging impossible |
| Use `public` schema | No namespacing — collisions guaranteed |
| Skip the TCP keepalives on the build script connection | Long-running upsert will SSL-timeout |
| Add a new download job to a project's crontab | Downloads belong to the data lake, not a project |
