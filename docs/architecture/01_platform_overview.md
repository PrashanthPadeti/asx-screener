# Data Platform Overview

## Architecture Principle

```
Shared Bronze (Raw Zone)  →  Project-Specific Silver  →  Project-Specific Gold
```

All projects share one Raw Zone / Data Lake for downloaded market data.
After the Raw Zone, every project has its own independent processing layers,
schemas, compute engines, and application tables.

**Key guarantee**: A schema change, bug fix, or new feature in one project
cannot break, affect, or be read by any other project.

---

## Architecture Diagram

```
┌────────────────────────────────────────────────────────────────────────────────┐
│                        BRONZE LAYER  (Shared Data Lake)                        │
│                    /opt/data-lake/raw/   —   immutable, append-only            │
│                                                                                │
│  eodhd/exchange=AU/    eodhd/exchange=NSE/    eodhd/exchange=NYSE/             │
│  eodhd/exchange=BSE/   eodhd/exchange=NASDAQ/ asic/  nse-india/  sec/  finra/ │
└──────────┬─────────────────┬──────────────────────┬──────────────┬────────────┘
           │ reads           │ reads                │ reads        │ reads
           ▼                 ▼                      ▼              ▼
  ┌──────────────┐  ┌──────────────────┐  ┌──────────────┐  ┌──────────────┐
  │ ASX SCREENER │  │ INDIA NIFTY      │  │ US SCREENER  │  │ CHARTING     │
  │  Project A   │  │ SCREENER         │  │  Project C   │  │  Project D   │
  │              │  │  Project B       │  │              │  │              │
  │  stg_au.*    │  │  stg_in.*        │  │  stg_us.*    │  │  stg_charts.*│
  │  mkt_au.*    │  │  mkt_in.*        │  │  mkt_us.*    │  │  charts_mkt.*│
  │  fin_au.*    │  │  fin_in.*        │  │  fin_us.*    │  │              │
  │  screener_au │  │  screener_in.*   │  │  screener_us │  │  charts.*    │
  └──────────────┘  └──────────────────┘  └──────────────┘  └──────────────┘
           │                 │                      │              │
           └─────────────────┴──────────────────────┴──────────────┘
                                      │
                         ┌────────────▼────────────┐
                         │  SHARED INFRASTRUCTURE   │
                         │  users.*  notifications.*│
                         │  ai.*  subscriptions.*   │
                         └─────────────────────────┘
```

---

## Layer Definitions

### Bronze Layer — Shared Raw Zone

**Purpose**: Store every downloaded file from every data provider, unmodified.

- **Location**: `/opt/data-lake/raw/`
- **Owned by**: `datalake_ingest` service account (read-only for all project accounts)
- **Format**: Provider's original format (JSON, JSON.GZ, CSV)
- **Mutation policy**: Append-only. Files are never modified or deleted after write.
- **Who writes**: Only the shared download pipeline (`/opt/data-lake/jobs/`)
- **Who reads**: Any project's staging ingestion scripts

See [02_bronze_layer_guide.md](02_bronze_layer_guide.md) for the full file layout and conventions.

### Silver Layer — Project-Specific Staging + Transform

**Purpose**: Ingest Bronze files into the project's own DB tables; normalise and clean.

Each project has two sub-layers:

| Sub-layer | Schema prefix | Description |
|---|---|---|
| Staging | `stg_{market}.*` | Raw DB landing — mirrors Bronze content in relational form |
| Market Transform | `mkt_{market}.*` | Clean, normalised, TimescaleDB time-series tables |
| Financials | `fin_{market}.*` | Normalised financial statements per market's accounting standard |

Rules:
- Staging tables are truncate-and-reload or upsert-on-date; no computed columns
- Transform tables derive from staging; they may add computed columns (e.g. adjusted prices)
- No project's transform layer reads another project's staging or transform schemas
- Each project runs its own ingestion job independently of other projects

### Gold Layer — Project-Specific Application Tables

**Purpose**: Denormalised, query-optimised tables that the API reads directly.

| Project | Schema | Key table |
|---|---|---|
| ASX Screener | `screener_au.*` | `screener_au.universe` |
| India Nifty Screener | `screener_in.*` | `screener_in.universe` |
| US Screener | `screener_us.*` | `screener_us.universe` |
| Charting | `charts.*` | `charts.ohlcv_cache`, `charts.saved_charts` |

The Gold table is rebuilt nightly by each project's build script. It is the only table
the project's API backend reads for screener queries.

---

## Project Details

### Project A: ASX Screener

**Market**: Australian Securities Exchange (ASX)
**Data sources**: EODHD (exchange=AU), ASIC short positions, ASX announcements

**Unique features**:
- Franking credits → grossed-up dividend yield
- REIT-specific: NTA per share, WALE, gearing ratio
- Mining-specific: AISC per oz, reserve life
- Half-yearly reporting (H1/H2) — no Q1/Q2/Q3/Q4
- ASIC-sourced short position data

**Schema summary**:
```
stg_au.*          Staging
mkt_au.*          Market data (TimescaleDB)
fin_au.*          Financials (IFRS/Australian GAAP)
screener_au.*     Application layer
```

**Golden Record**: `screener_au.universe` — one row per stock, rebuilt nightly.

---

### Project B: India Nifty Screener

**Market**: National Stock Exchange (NSE) and Bombay Stock Exchange (BSE)
**Data sources**: EODHD (exchange=NSE, exchange=BSE), NSE India direct feeds, SEBI data

**Unique features**:
- Promoter holdings % (mandatory SEBI disclosure) — key risk signal
- Pledged shares % (promoter pledge — insider stress indicator)
- FII/DII net flow tracking (Foreign/Domestic Institutional flows)
- Nifty index membership: Nifty 50, 100, 200, 500, Midcap 150, Smallcap 250
- Market cap tiers in INR per SEBI definition (Largecap top 100, Midcap 101-250, Smallcap 251+)
- Quarterly reporting mandatory (standalone + consolidated results)
- Circuit breakers: upper/lower circuit % — stock-specific daily price limits
- BSE/NSE dual-listing deduplication (same company, two exchange codes)
- No franking credits — dividend yield is pre-tax gross yield
- Dividend Distribution Tax (DDT) replaced by shareholder-level taxation (post 2020)

**Schema summary**:
```
stg_in.*          Staging
mkt_in.*          Market data (TimescaleDB)
fin_in.*          Financials (Indian GAAP / Ind AS)
screener_in.*     Application layer
```

**Golden Record**: `screener_in.universe` — one row per stock, rebuilt nightly.

**India-only tables**:
```
mkt_in.fii_dii_flows        FII/DII institutional buy/sell flows (daily)
mkt_in.promoter_holdings    SEBI-mandated promoter holding disclosures
mkt_in.pledged_shares       Promoter pledge data
mkt_in.circuit_limits       Per-stock upper/lower circuit bands
fin_in.quarterly_results    Quarterly P&L (standalone + consolidated)
```

---

### Project C: US Screener

**Market**: NYSE, NASDAQ, AMEX
**Data sources**: EODHD (exchange=NYSE/NASDAQ/AMEX), SEC EDGAR, FINRA short interest

**Unique features**:
- Quarterly reporting (10-Q mandatory via SEC)
- S&P 500 / Russell 1000/2000 / Nasdaq 100 index membership
- Market cap tiers in USD (Mega ≥$200B, Large $10-200B, Mid $2-10B, Small $300M-2B, Micro $50-300M, Nano <$50M)
- SEC Form 4 insider trading (mandatory disclosure within 2 business days)
- SEC 13F institutional ownership (quarterly, ≥$100M AUM threshold)
- FINRA bi-monthly short interest data (short float %, days-to-cover)
- GAAP vs non-GAAP EPS reconciliation
- No franking credits — straightforward dividend yield

**Schema summary**:
```
stg_us.*          Staging
mkt_us.*          Market data (TimescaleDB)
fin_us.*          Financials (US GAAP)
screener_us.*     Application layer
```

**Golden Record**: `screener_us.universe` — one row per stock, rebuilt nightly.

**US-only tables**:
```
mkt_us.short_interest        FINRA bi-monthly short reports
mkt_us.insider_trades        SEC Form 4 insider buy/sell
mkt_us.institutional_13f     SEC 13F quarterly institutional holdings
fin_us.quarterly_results     10-Q data
```

---

### Project D: Charting (Multi-Market)

**Markets**: All (AU, IN, US — and any future market)
**Data sources**: Bronze files from all exchanges

**Design principle**: Market-agnostic. All instruments use a unified namespace:
`{MARKET}:{CODE}` — e.g. `AU:BHP`, `IN:RELIANCE`, `US:AAPL`

**Key differences from Screener projects**:
- Uses **split-adjusted** prices (for continuous chart lines across corporate actions)
- Screener projects use **unadjusted** prices (for accurate valuation ratios)
- Needs multi-timeframe pre-aggregated bars (1m, 5m, 15m, 1h, 4h, 1d, 1w, 1M)
- Needs corporate event annotations (dividends, splits, earnings dates) on chart timeline
- Real-time/streaming path in addition to EOD batch path

**Schema summary**:
```
stg_charts.*      Staging (unified, all markets)
charts_mkt.*      Chart-optimised transform layer
charts.*          Application layer
```

**Key tables**:
```
charts_mkt.ohlcv             Unified split-adjusted OHLCV, all markets
charts_mkt.corporate_events  Dividends + splits merged for chart annotations
charts_mkt.indicator_cache   Pre-computed indicator series
charts_mkt.multi_tf_bars     Pre-aggregated multi-timeframe bars
charts.saved_charts          User-saved chart configurations
charts.drawing_objects       Trendlines, annotations saved by users
charts.watchlists
charts.alert_levels
```

---

## Shared Infrastructure

These schemas are shared across all projects (user accounts, billing, notifications):

```
users.*             Auth, profiles, subscriptions, API keys
notifications.*     Email/push alerts, price alerts
ai.*                AI summaries, embeddings, analysis cache
subscriptions.*     Stripe billing, plan management
```

**Rule**: Project application code may read `users.*` for auth. It must not write
to `users.*` outside of the auth/subscription flow. All user-facing features
(watchlists, saved screens, alerts) are stored in the **project's own schema**.

---

## Database Role Isolation

```
Role                 READ access                           WRITE access
───────────────────────────────────────────────────────────────────────────────
datalake_ingest      (none — file system only)            raw.*, all stg_*.*
screener_au_app      stg_au.*, mkt_au.*, fin_au.*         screener_au.*
                     screener_au.*, users.*
screener_in_app      stg_in.*, mkt_in.*, fin_in.*         screener_in.*
                     screener_in.*, users.*
screener_us_app      stg_us.*, mkt_us.*, fin_us.*         screener_us.*
                     screener_us.*, users.*
charts_app           stg_charts.*, charts_mkt.*           charts.*
                     charts.*, users.*
readonly             screener_au.universe,                (none)
                     screener_in.universe,
                     screener_us.universe
```

No project role has SELECT on another project's schemas. This is enforced at the
PostgreSQL role level, not just at the application level.

---

## Pipeline Schedule

```
Time (UTC)      Job                             Owner
─────────────────────────────────────────────────────────────────
18:30 Mon-Fri   download_eodhd_au.py            data-lake
18:30 Mon-Fri   download_asic_shorts.py         data-lake
18:35 Mon-Fri   download_eodhd_nse_bse.py       data-lake  (India market = IST+5:30)
23:30 Mon-Fri   download_eodhd_us.py            data-lake  (US market closes ~21:00 UTC)
23:35 Mon-Fri   download_sec_form4.py           data-lake
──── after downloads complete ────────────────────────────────────
19:00 Mon-Fri   asx_daily_pipeline.py           ASX Screener project
08:00 Tue-Sat   india_daily_pipeline.py         India Screener project  (IST morning)
00:30 Tue-Sat   us_daily_pipeline.py            US Screener project
19:30 Mon-Fri   charting_daily_pipeline.py      Charting project
```

Each project's pipeline is fully independent and does not call or depend on
another project's pipeline completing.
