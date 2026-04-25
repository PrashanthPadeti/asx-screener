# ASX Screener — Data Sizing, Storage Calculation & DB Plan Selection

> Version 1.0 | April 2026
> Answers: How big is 15 years of ALL ASX data? Which plan do we need?

---

## Key Numbers (ASX Market Facts)

```
Total ASX-listed companies:          ~2,200
Trading days per year:                ~252
Years of history we want:             15 years
Total trading days (15 yr):           3,780
Announcements per trading day:        ~300–500 (all ASX)
Annual reports per company/year:      1
Half-year reports:                    1 (most ASX companies)
Quarterly activity reports (miners):  4 (for ~400 mining companies)
Dividends per company/year:           ~2 (average)
```

---

## Table-by-Table Storage Calculation

### 1. market.daily_prices

```
Columns (per row):
  time (TIMESTAMPTZ)         8 bytes
  asx_code (VARCHAR 10)     10 bytes
  open, high, low, close,
  adjusted_close (NUMERIC)  40 bytes  (5 × 8 bytes each)
  volume (BIGINT)            8 bytes
  value_traded (NUMERIC)     8 bytes
  trades_count (INTEGER)     4 bytes
  vwap (NUMERIC)             8 bytes
  data_source (VARCHAR)     10 bytes
  PostgreSQL row overhead   23 bytes
  ─────────────────────────────────
  Total per row:           ~119 bytes ≈ 130 bytes (aligned)

Row count:
  2,200 stocks × 3,780 days = 8,316,000 rows

Raw data size:
  8,316,000 × 130 bytes = 1.08 GB

Index (asx_code, time DESC):
  ~400 MB

Total UNCOMPRESSED:        ~1.5 GB
TimescaleDB compression:   ~92% on data older than 3 months
  Compressed older data:   ~120 MB
  Recent 3 months (raw):   ~22 MB
TOTAL with compression:    ~140–200 MB  ✅ Very small!
```

---

### 2. market.technical_indicators

```
Columns: ~55 numeric columns (DMA, RSI, MACD, ATR, Bollinger,
          Volume metrics, Returns, 52W levels, signals, etc.)

Per row size:
  55 NUMERIC(12,4) columns × 8 bytes  = 440 bytes
  5  BOOLEAN columns × 1 byte         =   5 bytes
  2  BIGINT (volume, OBV)              =  16 bytes
  time + asx_code + overhead           =  41 bytes
  ────────────────────────────────────────────────
  Total per row:                       ~502 bytes ≈ 520 bytes

Row count: 8,316,000 rows (same as daily_prices)

Raw data size:
  8,316,000 × 520 bytes = 4.32 GB

Index overhead:            ~600 MB

Total UNCOMPRESSED:        ~4.9 GB
TimescaleDB compression:   ~88%
TOTAL with compression:    ~600–800 MB

──────────────────────────────────────────────────────────────
⚠️  DESIGN DECISION: Do we need 15 years of technical indicators?

  Option A: Store all 15 years → 600-800 MB compressed
  Option B: Store last 2 years only, recompute older on demand
            → 80-100 MB  (saves 700 MB, but needs recompute for
               old backtesting queries)

  Recommendation: Store all (disk is cheap, recomputing is slow)
──────────────────────────────────────────────────────────────
```

---

### 3. market.computed_metrics (THE BIG ONE)

```
This is our largest table — 200+ numeric columns per stock per day.

Columns: ~200 numeric/boolean columns
Per row size:
  200 NUMERIC columns × 8 bytes = 1,600 bytes
  text/meta fields               =    50 bytes
  time + asx_code + overhead     =    41 bytes
  ─────────────────────────────────────────────
  Total per row:                ~1,691 bytes ≈ 1,700 bytes

Row count options:
  Option A: Every stock, every day, 15 years
            2,200 × 3,780 = 8,316,000 rows
            8,316,000 × 1,700 = 14.1 GB uncompressed
            Compressed:         ~2.5-3.5 GB

  Option B: Every stock, every day, LAST 1 YEAR only
  (historical year-end snapshots stored separately)
            2,200 × 252 = 554,400 rows
            554,400 × 1,700 = 942 MB uncompressed
            Compressed:     ~200-300 MB

  Option C (RECOMMENDED): Smart tiered storage
  ┌──────────────────────────────────────────────────────┐
  │ Last 90 days: daily rows (live screener)             │
  │ Last 1 year:  daily rows (trend analysis)            │
  │ 1-5 years:    monthly snapshots (end-of-month only)  │
  │ 5-15 years:   annual snapshots (end-of-year only)    │
  └──────────────────────────────────────────────────────┘
  Storage: ~800 MB compressed
  This gives you backtesting capability without huge storage.

──────────────────────────────────────────────────────────────
⚠️  IMPORTANT: Most metrics in computed_metrics don't change
  much day to day. Storing every daily value for 15 years
  is mostly redundant. Smart tiering saves 5-6 GB.
──────────────────────────────────────────────────────────────
```

---

### 4. financials.annual_pnl / balance_sheet / cashflow

```
Annual P&L (per row: ~50 numeric columns):
  Row size: ~500 bytes
  Rows: 2,200 companies × 15 years = 33,000 rows
  Total: 33,000 × 500 = 16.5 MB

Annual Balance Sheet (per row: ~55 columns):
  Row size: ~550 bytes
  Rows: 33,000
  Total: 33,000 × 550 = 18.2 MB

Annual Cash Flow (per row: ~30 columns):
  Row size: ~350 bytes
  Rows: 33,000
  Total: 11.6 MB

Half-Year P&L + CF:
  Rows: 2,200 × 30 half-years = 66,000 rows
  Total: ~25-30 MB

Mining quarterly reports:
  400 miners × 4 per year × 15 years = 24,000 rows
  Total: ~12 MB

TOTAL FINANCIAL STATEMENTS:     ~85-90 MB  ← Tiny!
```

---

### 5. market.short_interest

```
Per row: ~80 bytes
Rows: 2,200 × 3,780 days = 8,316,000 rows
  (Note: ASIC short data started ~2010, so ~15 years is accurate)

Uncompressed: 8,316,000 × 80 = 665 MB
TimescaleDB compression: ~90%
TOTAL with compression:  ~65-100 MB  ✅
```

---

### 6. market.asx_announcements

```
Per row (with AI summary text ~500 chars):
  Fixed fields:  ~200 bytes
  AI summary:    ~500 bytes
  ai_key_points (JSONB): ~300 bytes
  Total: ~1,000 bytes per announcement

Rows:
  ~350 announcements/day average × 250 days × 15 years
  = 1,312,500 rows

Raw size: 1,312,500 × 1,000 = 1.31 GB
Compression: ~60% (text doesn't compress as well as numbers)
TOTAL: ~520 MB
```

---

### 7. market.dividends

```
Per row: ~200 bytes
Rows: ~5,000 events/year × 15 years = 75,000 rows
Total: 75,000 × 200 = 15 MB  ← Negligible
```

---

### 8. ai.document_chunks (pgvector embeddings)

```
Per row:
  chunk_text (~2,000 chars):     ~2,000 bytes
  embedding vector (1,536 dims): 1,536 × 4 bytes = 6,144 bytes
  metadata fields:               ~200 bytes
  Total per chunk:               ~8,344 bytes ≈ 8.5 KB

Estimated documents:
  Phase 1 (ASX 200, 10 years):
    200 companies × 10 reports × 60 chunks/report = 120,000 chunks
    120,000 × 8.5 KB = 1.02 GB

  Phase 2 (ASX 300, 15 years):
    300 × 15 × 60 = 270,000 chunks = 2.3 GB

  Phase 3 (all ASX 500+, 15 years):
    500 × 15 × 60 = 450,000 chunks = 3.8 GB

  Note: pgvector index (IVFFlat) adds ~50% overhead
  Phase 1 total: ~1.5 GB
  Phase 3 total: ~5.7 GB
```

---

### 9. Users, Watchlists, Portfolios, Screens

```
Phase 1 (< 1,000 users):   ~50 MB
Phase 2 (10,000 users):    ~500 MB
Phase 3 (100,000 users):   ~5 GB
```

---

### 10. PostgreSQL System Overhead

```
WAL (Write-Ahead Log):          256 MB – 1 GB  (controlled by config)
System catalogs + pg_stat:      ~100 MB
Temporary files (query sort):   ~500 MB (depends on queries)
VACUUM dead tuples:             ~5-10% of table size
Connection overhead:            ~5 MB per connection × 50 = 250 MB
──────────────────────────────────────────────────────────────────
Total system overhead:          ~1.5 – 2.5 GB
```

---

## TOTAL DATABASE SIZE SUMMARY

```
╔══════════════════════════════════════════════════════════════════════╗
║  TOTAL STORAGE ESTIMATE (15 Years, ALL ASX)                          ║
╠══════════════════════════════════════════════════════════════════════╣
║                                                                      ║
║  TABLE                        UNCOMPRESSED    COMPRESSED             ║
║  ─────────────────────────────────────────────────────────           ║
║  daily_prices (15yr)          1.5  GB         200  MB               ║
║  technical_indicators (15yr)  4.9  GB         700  MB               ║
║  computed_metrics             14.1 GB         3.0  GB  (smart tier) ║
║  ↳ smart tiered version        2.0 GB          400 MB  ← USE THIS   ║
║  annual financials (all)       0.1  GB          90  MB               ║
║  short_interest (15yr)         0.7  GB         100  MB               ║
║  asx_announcements (15yr)      1.3  GB         520  MB               ║
║  dividends                    0.01  GB          15  MB               ║
║  ai_doc_chunks (Phase 1)       1.0  GB         1.5  GB  (vectors)   ║
║  users/watchlists/portfolios   0.05 GB          50  MB               ║
║  indexes (all tables)          4.0  GB         4.0  GB  (no compress)║
║  PostgreSQL system overhead    2.0  GB         2.0  GB               ║
║  ─────────────────────────────────────────────────────────           ║
║  TOTAL (smart tiered)         ~17.6 GB        ~9.6 GB               ║
║  TOTAL (full history)         ~29.7 GB        ~12.6 GB              ║
║                                                                      ║
║  REALISTIC PRODUCTION TOTAL:  9 – 13 GB  (after compression)        ║
╚══════════════════════════════════════════════════════════════════════╝
```

---

## How Long Will the Aiven $19/mo (5 GB) Plan Last?

```
╔══════════════════════════════════════════════════════════════════════╗
║  AIVEN HOBBYIST PLAN SPECS:                                          ║
║  Storage: 5 GB    RAM: 1 GB    Connections: 25                       ║
╠══════════════════════════════════════════════════════════════════════╣
║                                                                      ║
║  DATA LOAD TIMELINE vs 5 GB LIMIT:                                   ║
║                                                                      ║
║  Day 1:  Schema only                              ~50 MB   ✅        ║
║  Day 2:  + ASX company list (2,200 stocks)        ~60 MB   ✅        ║
║  Day 3:  + 15yr price history (FULL backfill)     ~1.5 GB  ✅        ║
║           (compressed = ~300 MB for 14.75yr data)                   ║
║           (uncompressed = ~200 MB for recent 3mo data)              ║
║           Total prices with indexes: ~1.5 GB                        ║
║  Day 4:  + Annual financials (15yr, all ASX)      +100 MB  ✅        ║
║  Day 4:  + Short interest history (15yr)          +100 MB  ✅        ║
║  Day 4:  + Dividends                              + 15 MB  ✅        ║
║          ─────────────────────────────────────────────────          ║
║          Running total after initial load:        ~1.8 GB  ✅        ║
║                                                                      ║
║  Week 2: + Technical indicators (15yr backfill)   +700 MB           ║
║          Running total:                           ~2.5 GB  ✅        ║
║                                                                      ║
║  Week 3: + ASX announcements (15yr backfill)      +520 MB           ║
║          Running total:                           ~3.0 GB  ✅        ║
║                                                                      ║
║  Week 3: + First computed_metrics run (today)     + 10 MB           ║
║          Running total:                           ~3.1 GB  ✅        ║
║                                                                      ║
║  Week 4: + AI document chunks (ASX 200, 5yr)      +800 MB ⚠️        ║
║          Running total:                           ~3.9 GB  ⚠️ 78%   ║
║                                                                      ║
║  Month 2: + Daily computed_metrics (~5 MB/day × 20 days)  +100 MB  ║
║           + Daily announcements (~5 MB/month)              + 20 MB  ║
║           + System growth (VACUUM, WAL, temp files)        +200 MB  ║
║           Running total:                          ~4.2 GB  ⚠️ 84%   ║
║                                                                      ║
║  Month 3: Daily growth ~125 MB/month                                 ║
║           Running total:                          ~4.4 GB  ⚠️ 88%   ║
║                                                                      ║
║  Month 4: Running total:                          ~4.6 GB  🔴 92%   ║
║                                                                      ║
║  ─────────────────────────────────────────────────────────          ║
║  VERDICT:                                                            ║
║                                                                      ║
║  The $19/mo plan WILL hold the initial full 15-year backfill        ║
║  of prices + financials + indicators (~3 GB after compression).     ║
║                                                                      ║
║  BUT you will hit the 5 GB wall within 3-4 months of going live,   ║
║  mostly due to AI vectors + daily computed_metrics accumulation.    ║
║                                                                      ║
║  THE REAL KILLER is the 1 GB RAM limit — not the storage.           ║
║  Running the Compute Engine against 2,200 stocks × 200 metrics      ║
║  will cause out-of-memory errors on 1 GB RAM.                       ║
╚══════════════════════════════════════════════════════════════════════╝
```

---

## The RAM Problem is Worse Than the Storage Problem

```
MEMORY REQUIREMENTS:

PostgreSQL shared_buffers (recommended: 25% of RAM):
  On 1 GB RAM Hobbyist plan: 256 MB
  This is what PostgreSQL uses as its buffer cache.
  For 9+ GB of data, 256 MB cache = constant disk I/O = SLOW.

Compute Engine (Python, Pandas):
  Loading all 2,200 stocks' price history into Pandas DataFrames:
  2,200 × 200 days × ~500 bytes = 220 MB per stage
  Running 6 parallel stages = 1.3 GB minimum RAM needed

  On 1 GB Hobbyist plan → KILLS the Compute Engine.
  The Airflow/Celery worker will be on a separate server,
  but the DB queries from it will time out / cause swap.

Active user queries (screener running):
  Each screen query does full table scan on computed_metrics
  (~2 GB table, 256 MB cache = lots of disk reads = slow)

CONNECTION LIMIT: 25 connections max
  FastAPI (async): 10 connections
  Airflow/Celery:  5 connections
  Total:           15 — technically fits but very tight.
```

---

## Aiven Plan Comparison for This Project

```
╔════════════════════╦══════════╦══════════╦════════╦══════════════════╗
║ Plan               ║ RAM      ║ Storage  ║ Price  ║ Our Use Case     ║
╠════════════════════╬══════════╬══════════╬════════╬══════════════════╣
║ Hobbyist           ║ 1 GB     ║ 5 GB     ║ $19/mo ║ ❌ Development  ║
║                    ║          ║          ║        ║    only (subset) ║
╠════════════════════╬══════════╬══════════╬════════╬══════════════════╣
║ Startup-1          ║ 2 GB     ║ 20 GB    ║ $50/mo ║ ⚠️  MVP/beta    ║
║                    ║          ║          ║        ║    (tight on RAM)║
╠════════════════════╬══════════╬══════════╬════════╬══════════════════╣
║ Business-4         ║ 4 GB     ║ 80 GB    ║ $98/mo ║ ✅ Phase 2      ║
║                    ║          ║          ║        ║    Launch ready  ║
╠════════════════════╬══════════╬══════════╬════════╬══════════════════╣
║ Business-8         ║ 8 GB     ║ 160 GB   ║$186/mo ║ ✅ Phase 2–3    ║
║                    ║          ║          ║        ║    Comfortable   ║
╠════════════════════╬══════════╬══════════╬════════╬══════════════════╣
║ Premium-6x         ║ 16 GB    ║ 175 GB   ║$370/mo ║ ✅ Phase 3      ║
╠════════════════════╬══════════╬══════════╬════════╬══════════════════╣
║ Premium-14x        ║ 32 GB    ║ 280 GB   ║$640/mo ║ ✅ Phase 3 max  ║
╚════════════════════╩══════════╩══════════╩════════╩══════════════════╝

For 9-13 GB of compressed data + comfortable RAM:
  → Minimum viable: Business-4 ($98/mo, 4 GB RAM, 80 GB storage)
  → Recommended:    Business-8 ($186/mo, 8 GB RAM, 160 GB storage)
```

---

## Revised Recommendation — 3-Tier Approach

```
╔══════════════════════════════════════════════════════════════════════╗
║  REVISED DATABASE PLAN (honest sizing)                               ║
╠══════════════════════════════════════════════════════════════════════╣
║                                                                      ║
║  PHASE 0: LOCAL DEVELOPMENT (free, always)                           ║
║  Docker: timescale/timescaledb-ha:pg16                              ║
║  Spec:   Your laptop/PC RAM (8-16 GB)                               ║
║  Data:   Full dataset for development                               ║
║  Cost:   $0                                                          ║
║  Use:    All development and testing — 100% of code written here    ║
║                                                                      ║
║  PHASE 1: BETA / STAGING (Months 1-4)                               ║
║  Service: Aiven Business-4 OR DigitalOcean 8 GB Droplet             ║
║  Spec:    4 GB RAM / 80 GB storage                                  ║
║  Cost:    $98/mo (Aiven) OR $48/mo (DO Droplet + self-managed)     ║
║  Data:    FULL 15-year ASX dataset                                  ║
║  Use:     Beta testing with real users (< 200 users)               ║
║                                                                      ║
║  ⚠️  The $19/mo Hobbyist plan is ONLY for:                           ║
║     • Proof of concept queries                                       ║
║     • Schema validation                                             ║
║     • Development with a SMALL dataset (200 stocks, 2 years)       ║
║     • Never for full production data load                           ║
║                                                                      ║
║  PHASE 2: LAUNCH (Months 5-12)                                       ║
║  Service: DigitalOcean 32 GB Droplet (Sydney) + TimescaleDB         ║
║  Spec:    32 GB RAM / 640 GB SSD                                    ║
║  Cost:    $168 USD/mo (~$260 AUD/mo)                                ║
║  Handles: Up to 10,000 active users comfortably                    ║
║                                                                      ║
║  PHASE 3: SCALE (Months 12+)                                         ║
║  Primary: AWS EC2 r6g.2xlarge (Sydney)                              ║
║  Spec:    64 GB RAM / 1 TB NVMe                                     ║
║  Cost:    ~$490 AUD/mo (on-demand) / ~$294/mo (1-yr reserved)      ║
║  Handles: 100,000+ users                                            ║
╚══════════════════════════════════════════════════════════════════════╝
```

---

## Practical "Start Smart" Data Loading Strategy

```
Instead of loading everything on Day 1, load incrementally:

WEEK 1: Core data only (fits in Hobbyist if needed)
  ✅ ASX company list (2,200 stocks)        → 5 MB
  ✅ Last 5 years of price data only        → 500 MB compressed
  ✅ Annual financials (last 5 years)       → 30 MB
  ✅ Short interest (last 1 year)           → 15 MB
  Total: ~550 MB — fits ANY plan

WEEK 2: Extend price history
  ✅ Backfill prices to 15 years            → +500 MB (compressed)
  ✅ Technical indicators (last 5 years)    → +200 MB
  ✅ ASIC short interest (15 years)         → +100 MB
  Total: ~1.4 GB — still fits Hobbyist

WEEK 3: Add richer data
  ✅ Technical indicators (backfill 15yr)   → +500 MB
  ✅ ASX announcements (last 1 year)        → +35 MB
  ✅ Dividends (15 years)                   → +15 MB
  Total: ~2.0 GB — Hobbyist getting full

WEEK 4: First compute run
  ✅ computed_metrics (today only)          → +10 MB
  Total: ~2.0 GB — Hobbyist OK

MONTH 2: Start adding AI vectors
  ⚠️ AI doc chunks (top 50 stocks)          → +200 MB
  ⚠️ Daily growth (~125 MB/month)
  Total: ~2.5 GB — Hobbyist at 50%

MONTH 3-4: Upgrade to Business plan
  → ASX announcements historical backfill   → +500 MB
  → AI chunks (ASX 200)                     → +800 MB
  → computed_metrics accumulation           → +300 MB
  Total: ~4.1 GB → UPGRADE BEFORE THIS POINT
  → Move to Aiven Business-4 ($98/mo)
     OR DigitalOcean 8 GB Droplet ($48/mo)
```

---

## Cost vs Longevity — The Real Answer

```
┌─────────────────────────────────────────────────────────────────────┐
│  HOW LONG DOES $19/MO LAST FOR FULL ASX DATA?                        │
│                                                                      │
│  Scenario A: Load everything at once (15yr, all ASX)                │
│    Storage used after load: ~3.5-4 GB                               │
│    Headroom remaining:      ~1-1.5 GB                               │
│    How long before full:    2-3 MONTHS of daily updates             │
│    RAM issue:               IMMEDIATE — 1 GB RAM cannot run         │
│                             Compute Engine on 2,200 stocks          │
│                                                                      │
│  Scenario B: Incremental load (recommended approach above)          │
│    Week 1-2 data:           ~1.5 GB — fits comfortably              │
│    Full load (month 2-3):   ~3.5 GB — getting tight                 │
│    With AI vectors:         EXCEEDS 5 GB                            │
│    Useful life:             3-4 MONTHS maximum                      │
│                                                                      │
│  Scenario C: Dev only (200 stocks, 2 years data)                    │
│    Storage: ~400-500 MB — fits easily                               │
│    RAM: 1 GB still too small for Compute Engine                     │
│    Useful life: 6-12 months for dev testing                         │
│                                                                      │
│  ─────────────────────────────────────────────────────────          │
│  BOTTOM LINE:                                                        │
│                                                                      │
│  $19/mo (5GB, 1GB RAM) = DEV TESTING ONLY                           │
│  For full 15yr ASX production data = NEVER adequate                 │
│                                                                      │
│  MINIMUM for full production data:                                   │
│  Aiven Business-4: $98/mo  (4GB RAM, 80GB storage)                 │
│  DigitalOcean 8GB: $48/mo  (8GB RAM, 160GB SSD) ← BEST VALUE       │
│                    + self-managed PostgreSQL + TimescaleDB           │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Storage Growth Projection (Production)

```
MONTHLY GROWTH AFTER FULL INITIAL LOAD:

  New daily_prices rows:           2,200 × 21 days = 46,200/mo
  Storage:                         ~6 MB/mo compressed

  New technical_indicators:        46,200 rows/mo
  Storage:                         ~25 MB/mo compressed

  New computed_metrics (daily):    2,200 × 21 = 46,200/mo
  Storage:                         ~80 MB/mo compressed

  New asx_announcements:           300 × 21 days = 6,300/mo
  Storage:                         ~6 MB/mo

  New short_interest:              46,200 rows/mo
  Storage:                         ~4 MB/mo

  User data growth (1,000 users):  ~20 MB/mo

  TOTAL MONTHLY GROWTH:            ~141 MB/mo
                                   ~1.7 GB/year

STORAGE CAPACITY PLANNING:
  Year 1:  9.6 GB + 1.7 GB  = 11.3 GB
  Year 2:  11.3 GB + 1.7 GB = 13.0 GB
  Year 3:  13.0 GB + 1.7 GB = 14.7 GB
  Year 5:  14.7 GB + 3.4 GB = 18.1 GB
  Year 10: ~27 GB total

A 160 GB plan handles 60+ years of data growth.
A 640 GB plan is essentially unlimited for this project.
```

---

## Final Recommendation

```
╔══════════════════════════════════════════════════════════════════════╗
║  WHAT TO USE AND WHEN                                                ║
╠══════════════════════════════════════════════════════════════════════╣
║                                                                      ║
║  TODAY → MONTH 1 (Active development, no real users):               ║
║  ─────────────────────────────────────────────────                  ║
║  Use LOCAL Docker only.                                             ║
║  Your PC has 8-16 GB RAM and 500+ GB disk → handles everything.    ║
║  Cost: $0                                                            ║
║                                                                      ║
║  MONTH 1-2 (First beta users, need cloud DB):                       ║
║  ────────────────────────────────────────────                       ║
║  DigitalOcean 8 GB Droplet + TimescaleDB (Sydney)                  ║
║  Cost: $48 USD/mo (~$75 AUD/mo)                                     ║
║  Handles: Full 15-yr ASX data, 200 beta users, Compute Engine       ║
║                                                                      ║
║  MONTH 3-6 (Public launch, paying users):                           ║
║  ─────────────────────────────────────────                          ║
║  Upgrade to DigitalOcean 32 GB Droplet (Sydney)                    ║
║  Cost: $168 USD/mo (~$260 AUD/mo)                                   ║
║  Handles: 15-yr data + AI vectors + 2,000 active users             ║
║                                                                      ║
║  Skip the $19/mo Aiven Hobbyist plan entirely for production.       ║
║  It is NOT adequate for the full ASX dataset in RAM or storage.     ║
║                                                                      ║
║  Use Aiven Hobbyist only if you want a quick cloud test with a      ║
║  small subset (100 stocks, 1 year) — nothing more.                  ║
╚══════════════════════════════════════════════════════════════════════╝
```
