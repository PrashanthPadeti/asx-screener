# ASX Screener — Architecture & High-Level Design (HLD)

> Version 1.0 | April 2026

---

## 1. System Architecture Overview

```
╔══════════════════════════════════════════════════════════════════════════════════╗
║                          ASX SCREENER — SYSTEM ARCHITECTURE                     ║
╚══════════════════════════════════════════════════════════════════════════════════╝

  ┌─────────────────────────────────────────────────────────────┐
  │                     EXTERNAL DATA SOURCES                    │
  │                                                              │
  │  ┌──────────────┐ ┌─────────────┐ ┌────────────────────┐   │
  │  │ Yahoo Finance │ │ ASX Official│ │ ASIC (Short Data)  │   │
  │  │  (EOD Prices) │ │Announcements│ │ Aggregated Short   │   │
  │  └──────┬───────┘ └──────┬──────┘ └─────────┬──────────┘   │
  │         │                │                   │               │
  │  ┌──────┴───────┐ ┌──────┴──────┐ ┌─────────┴──────────┐   │
  │  │   Refinitiv  │ │ Morningstar │ │  S&P ESG / MSCI    │   │
  │  │ (Financials) │ │ (Financials)│ │  (ESG Ratings)     │   │
  │  └──────┬───────┘ └──────┬──────┘ └─────────┬──────────┘   │
  └─────────┼────────────────┼───────────────────┼──────────────┘
            │                │                   │
            └────────────────┼───────────────────┘
                             │  (Scheduled ingestion via Airflow)
                             ▼
  ┌──────────────────────────────────────────────────────────────────────────────┐
  │                        DATA INGESTION LAYER                                   │
  │                                                                               │
  │   ┌─────────────────────────────────────────────────────────────────────┐   │
  │   │                    Apache Airflow (Orchestrator)                      │   │
  │   │                                                                       │   │
  │   │  DAG: price_ingest  DAG: financials  DAG: announcements  DAG: asic  │   │
  │   │  [4:15 PM AEST]     [Quarterly]      [Every 5 min]       [5 PM]     │   │
  │   └───────────────────────────────┬─────────────────────────────────────┘   │
  │                                   │                                           │
  │   ┌───────────────────────────────▼─────────────────────────────────────┐   │
  │   │              Python Ingestion Workers (Celery Workers)                │   │
  │   │                                                                       │   │
  │   │   price_worker.py    financials_worker.py    announcement_worker.py  │   │
  │   │   short_worker.py    dividend_worker.py       esg_worker.py          │   │
  │   └───────────────────────────────┬─────────────────────────────────────┘   │
  └───────────────────────────────────┼──────────────────────────────────────────┘
                                      │
                                      ▼
  ┌──────────────────────────────────────────────────────────────────────────────┐
  │                          DATA STORAGE LAYER                                   │
  │                                                                               │
  │  ┌────────────────────────────────┐   ┌──────────────────────────────────┐  │
  │  │   PostgreSQL 16 + TimescaleDB  │   │         Redis 7 (Cache)          │  │
  │  │                                │   │                                  │  │
  │  │  • companies (master)          │   │  • live_price:{ASX_CODE}         │  │
  │  │  • daily_prices (hypertable)   │   │  • screen_result:{hash}          │  │
  │  │  • annual_financials           │   │  • company_ratios:{ASX_CODE}     │  │
  │  │  • half_year_financials        │   │  • session:{user_id}             │  │
  │  │  • computed_metrics (daily)    │   │  • alert_queue                   │  │
  │  │  • dividends                   │   │  TTL: prices=15s, screens=5min   │  │
  │  │  • short_interest              │   │      ratios=1hr, sessions=24hr   │  │
  │  │  • asx_announcements           │   └──────────────────────────────────┘  │
  │  │  • users / watchlists          │                                          │
  │  │  • saved_screens               │   ┌──────────────────────────────────┐  │
  │  │  • portfolios                  │   │    Elasticsearch / OpenSearch    │  │
  │  │  • alerts                      │   │                                  │  │
  │  │  + mining_data, reit_data      │   │  • stocks index (search/filter)  │  │
  │  └────────────────────────────────┘   │  • announcements index           │  │
  │                                       │  • screen query execution        │  │
  │  ┌────────────────────────────────┐   └──────────────────────────────────┘  │
  │  │          AWS S3 / Blob         │                                          │
  │  │  • Annual reports (PDFs)       │   ┌──────────────────────────────────┐  │
  │  │  • ASX announcement PDFs       │   │       pgvector (in PostgreSQL)   │  │
  │  │  • User exports (xlsx/csv)     │   │  • Annual report embeddings      │  │
  │  │  • AI document embeddings      │   │  • Announcement embeddings       │  │
  │  └────────────────────────────────┘   │  • For AI semantic search        │  │
  │                                       └──────────────────────────────────┘  │
  └──────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
  ┌──────────────────────────────────────────────────────────────────────────────┐
  │                        COMPUTE ENGINE LAYER                                   │
  │                    (Runs daily after data ingestion)                          │
  │                                                                               │
  │   ┌─────────────────────────────────────────────────────────────────────┐   │
  │   │                  Metric Computation Engine (Python)                   │   │
  │   │                                                                       │   │
  │   │  Stage 1: Technical Indicators   Stage 2: Valuation Ratios           │   │
  │   │  Stage 3: Profitability Ratios   Stage 4: Growth Metrics             │   │
  │   │  Stage 5: Risk & Quality Scores  Stage 6: ASX-Specific Metrics       │   │
  │   │                                                                       │   │
  │   │  • Parallel processing (16 workers × 140 stocks each = 2,200 total)  │   │
  │   │  • Vectorized Pandas computation (not row-by-row)                    │   │
  │   │  • Writes to computed_metrics table                                  │   │
  │   │  • Invalidates Redis cache for all updated stocks                    │   │
  │   │  • Target runtime: < 20 minutes for all 2,200 stocks                 │   │
  │   └─────────────────────────────────────────────────────────────────────┘   │
  │                                                                               │
  │   ┌─────────────────────────────────────────────────────────────────────┐   │
  │   │                     Alert Engine (Python)                             │   │
  │   │  • Re-runs all active user screen queries                            │   │
  │   │  • Compares results vs previous run                                  │   │
  │   │  • Queues notifications (email/push) for new matches                 │   │
  │   └─────────────────────────────────────────────────────────────────────┘   │
  └──────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
  ┌──────────────────────────────────────────────────────────────────────────────┐
  │                       APPLICATION / API LAYER                                 │
  │                                                                               │
  │  ┌──────────────────────────────────────────────────────────────────────┐   │
  │  │                      FastAPI Backend (Python)                          │   │
  │  │                                                                        │   │
  │  │  /api/v1/                                                              │   │
  │  │    stocks/          → Stock search, company data, ratios              │   │
  │  │    screener/        → Execute screens, save queries, get results      │   │
  │  │    watchlists/      → CRUD watchlists                                 │   │
  │  │    portfolios/      → Portfolio CRUD + performance                    │   │
  │  │    alerts/          → Alert management                                │   │
  │  │    feed/            → Personalised news/announcements feed            │   │
  │  │    ai/              → AI Q&A, summaries, insights                     │   │
  │  │    auth/            → Login, register, OAuth                          │   │
  │  │    admin/           → Internal admin endpoints                        │   │
  │  │                                                                        │   │
  │  │  WebSocket:  /ws/prices/{asx_code}   (live price streaming)          │   │
  │  │              /ws/feed                (live announcement feed)         │   │
  │  └──────────────────────────────────────────────────────────────────────┘   │
  │                                                                               │
  │  ┌──────────────────────────────────────────────────────────────────────┐   │
  │  │                      AI Service (Python)                               │   │
  │  │                                                                        │   │
  │  │  • Claude claude-sonnet-4-6 (complex Q&A, summaries)                │   │
  │  │  • Claude claude-haiku-4-5-20251001 (fast classification, tagging)  │   │
  │  │  • RAG pipeline: PDF → chunks → embeddings → pgvector → query        │   │
  │  │  • Prompt caching enabled (financial templates cached)               │   │
  │  └──────────────────────────────────────────────────────────────────────┘   │
  └──────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
  ┌──────────────────────────────────────────────────────────────────────────────┐
  │                         PRESENTATION LAYER                                    │
  │                                                                               │
  │  ┌───────────────────────────────┐   ┌────────────────────────────────────┐ │
  │  │     Next.js 14 (Web App)      │   │   React Native (Mobile App)        │ │
  │  │   TypeScript + TailwindCSS    │   │   iOS + Android                    │ │
  │  │   TradingView Charts          │   │   Push notifications               │ │
  │  │   SSR + Static Generation     │   │   Offline watchlist cache          │ │
  │  │   CDN-cached public pages     │   └────────────────────────────────────┘ │
  │  └───────────────────────────────┘                                           │
  └──────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. High-Level Design (HLD)

### 2.1 System Decomposition — Major Components

```
┌─────────────────────────────────────────────────────────────┐
│                    COMPONENT MAP                             │
│                                                              │
│  C1: Data Ingestion Service                                  │
│  C2: Compute Engine (Metric Calculator)                      │
│  C3: Alert Engine                                            │
│  C4: FastAPI Backend (REST + WebSocket)                      │
│  C5: AI Service                                              │
│  C6: Next.js Frontend (Web)                                  │
│  C7: React Native App (Mobile)                               │
│  C8: Notification Service (Email + Push)                     │
│  C9: Admin Dashboard (Internal)                              │
│                                                              │
│  Stores:                                                     │
│  S1: PostgreSQL + TimescaleDB (Primary DB)                   │
│  S2: Redis (Cache + Queue)                                   │
│  S3: Elasticsearch (Search + Screening)                      │
│  S4: AWS S3 (Document Storage)                               │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Request Flow — Stock Screener Query

```
User types query:
"Market cap > 500 AND PE < 20 AND ROE > 15 AND Franking > 80"

  Browser/App
      │
      ▼
  Next.js Frontend
  → Validates query syntax client-side
  → POST /api/v1/screener/run
      │
      ▼
  FastAPI Backend
  → Check Redis cache (hash of query) ──→ HIT: return cached results (< 5 min old)
  → MISS: Parse query into SQL WHERE clause
  → Execute against computed_metrics + companies (PostgreSQL)
  → Apply user's column preferences
  → Store result in Redis (TTL: 5 min)
  → Return paginated results (50 per page)
      │
      ▼
  Frontend renders sortable results table
  → User saves query → POST /api/v1/screener/save
  → User sets alert → POST /api/v1/alerts/create
```

### 2.3 Request Flow — Company Detail Page

```
User clicks "BHP" company page

  Browser
      │
      ▼
  Next.js (SSR)
  → GET /api/v1/stocks/BHP/overview
  → GET /api/v1/stocks/BHP/financials (annual P&L, BS, CF)
  → GET /api/v1/stocks/BHP/metrics    (computed_metrics for today)
  → GET /api/v1/stocks/BHP/price-chart (TimescaleDB aggregated data)
  → All calls in parallel via Promise.all()
      │
      ▼
  FastAPI
  → Redis cache check per endpoint (TTL varies)
  → PostgreSQL for financial data
  → TimescaleDB for price history
  → Return JSON responses
      │
      ▼
  Next.js renders:
  → Static sections: ISR (revalidate every hour)
  → Price chart: Client-side WebSocket subscription
  → Financial tables: Server rendered
  → AI insights: On-demand (user triggers)
```

### 2.4 Request Flow — Daily Data Pipeline

```
  4:00 PM AEST  ─── ASX Market Closes

  4:15 PM  ─── Airflow triggers DAG: price_ingest
                    │
                    ├─ Fetch all 2,200 ASX EOD prices (Yahoo Finance)
                    ├─ Validate: check for stale/missing data
                    ├─ Write to daily_prices (TimescaleDB)
                    └─ Mark price_ingest COMPLETE

  5:00 PM  ─── Airflow triggers DAG: asic_short_data
                    │
                    ├─ Download ASIC aggregated short sales CSV
                    ├─ Parse and write to short_interest table
                    └─ Mark asic_short COMPLETE

  5:30 PM  ─── Airflow triggers DAG: compute_engine (depends on price_ingest)
                    │
                    ├─ Load today's prices (all stocks)
                    ├─ Load latest financial statements (all stocks)
                    ├─ STAGE 1: Technical Indicators (parallel, 16 workers)
                    ├─ STAGE 2: Valuation Ratios
                    ├─ STAGE 3: Profitability & Quality Ratios
                    ├─ STAGE 4: Growth Metrics
                    ├─ STAGE 5: Risk Scores (Altman Z, Piotroski, etc.)
                    ├─ STAGE 6: ASX-Specific (Franking yields, etc.)
                    ├─ Write batch to computed_metrics table
                    ├─ Invalidate Redis cache (all stocks)
                    ├─ Re-sync Elasticsearch documents
                    └─ Mark compute_engine COMPLETE  [~6:00 PM]

  6:30 PM  ─── Airflow triggers DAG: alert_engine (depends on compute_engine)
                    │
                    ├─ Load all active screen alerts
                    ├─ Re-run each saved screen query
                    ├─ Diff results vs previous run
                    ├─ Queue notifications for new matches
                    └─ Notification Service sends emails + push

  Continuous ─── Airflow triggers DAG: announcements (every 5 min, 8AM-8PM)
                    │
                    ├─ Poll ASX announcements API
                    ├─ New announcements → Claude Haiku for classification
                    ├─ Write to asx_announcements
                    └─ Push to WebSocket feed for subscribed users
```

---

## 3. Technology Decision Matrix

### 3.1 Database Selection — Long-Term Recommendation

```
╔═══════════════════╦══════════╦═══════════╦═══════════╦══════════╦════════════╗
║ Criterion         ║ PostgreSQL║ClickHouse ║ MongoDB   ║ MySQL    ║ CockroachDB║
║                   ║+TimescaleDB║          ║           ║          ║            ║
╠═══════════════════╬══════════╬═══════════╬═══════════╬══════════╬════════════╣
║ Time-series perf  ║ ★★★★★   ║ ★★★★★    ║ ★★★      ║ ★★★     ║ ★★★★      ║
║ Relational data   ║ ★★★★★   ║ ★★       ║ ★★★      ║ ★★★★    ║ ★★★★★     ║
║ ACID compliance   ║ ★★★★★   ║ ★★★      ║ ★★★★     ║ ★★★★    ║ ★★★★★     ║
║ Complex queries   ║ ★★★★★   ║ ★★★★     ║ ★★★      ║ ★★★★    ║ ★★★★★     ║
║ Write throughput  ║ ★★★★    ║ ★★★★★    ║ ★★★★★    ║ ★★★★    ║ ★★★       ║
║ Ecosystem/tooling ║ ★★★★★   ║ ★★★★     ║ ★★★★★    ║ ★★★★★   ║ ★★★       ║
║ Vector/AI support ║ ★★★★★   ║ ★★       ║ ★★★★     ║ ★★       ║ ★★        ║
║ Managed cloud     ║ ★★★★★   ║ ★★★★     ║ ★★★★★    ║ ★★★★★   ║ ★★★★      ║
║ Cost (startup)    ║ ★★★★★   ║ ★★★★★    ║ ★★★      ║ ★★★★★   ║ ★★★       ║
║ Scale (10M rows+) ║ ★★★★★   ║ ★★★★★    ║ ★★★      ║ ★★★      ║ ★★★★★     ║
╠═══════════════════╬══════════╬═══════════╬═══════════╬══════════╬════════════╣
║ TOTAL             ║  49/50   ║  41/50    ║  38/50    ║ 40/50    ║  40/50     ║
╚═══════════════════╩══════════╩═══════════╩═══════════╩══════════╩════════════╝

WINNER: PostgreSQL 16 + TimescaleDB (our primary database)
```

**Why PostgreSQL + TimescaleDB wins for this project:**

| Reason | Detail |
|---|---|
| TimescaleDB hypertables | Auto-partitions price data by time, transparent to queries |
| 98% compression | Old price data compressed automatically, saving 95%+ storage |
| Continuous aggregates | Pre-computed weekly/monthly OHLCV without extra queries |
| pgvector | AI document embeddings stored IN the same database |
| Row-level security | Multi-tenant user data isolation at DB level |
| Full SQL | Complex screener queries (JOINs, window functions, CTEs) |
| Ecosystem | ORMs, migrations (Alembic), monitoring (pgBadger), backups |
| Managed options | AWS RDS, TimescaleDB Cloud, Supabase (for startups) |
| Single technology | No polyglot complexity — one DB for everything |
| Proven at scale | Used by financial firms with billions of rows |

**Phase 3+ Addition: ClickHouse (Analytics Sidecar)**
- Add ClickHouse ONLY for backtesting queries and heavy analytics
- Replicate computed_metrics and daily_prices to ClickHouse via CDC
- Do NOT replace PostgreSQL — use ClickHouse as a read-only analytics layer

---

## 4. Infrastructure Design

### 4.1 AWS Architecture

```
                    ┌─────────────────────────────────────────┐
                    │              Route 53 (DNS)              │
                    │         screener.com.au → ALB           │
                    └────────────────┬────────────────────────┘
                                     │
                    ┌────────────────▼────────────────────────┐
                    │       CloudFront CDN                     │
                    │  • Static assets (JS, CSS, images)       │
                    │  • Next.js ISR pages (TTL: 1hr)          │
                    │  • API responses (TTL: 0 — pass-through) │
                    └────────────────┬────────────────────────┘
                                     │
                    ┌────────────────▼────────────────────────┐
                    │     Application Load Balancer            │
                    │  • SSL termination (ACM certificates)    │
                    │  • Route /api/* → FastAPI               │
                    │  • Route /* → Next.js                    │
                    └──────┬──────────────────┬───────────────┘
                           │                  │
            ┌──────────────▼───┐    ┌─────────▼──────────────┐
            │  Next.js (ECS)   │    │   FastAPI (ECS)         │
            │  Fargate         │    │   Fargate               │
            │  2–8 tasks       │    │   2–16 tasks            │
            │  Auto-scaling    │    │   Auto-scaling          │
            └──────────────────┘    └─────────┬──────────────┘
                                              │
               ┌──────────────────────────────┼──────────────────────────────┐
               │                              │                              │
  ┌────────────▼──────────┐  ┌───────────────▼─────────┐  ┌────────────────▼──┐
  │ RDS PostgreSQL (Multi-│  │ ElastiCache Redis       │  │ OpenSearch (ES)   │
  │ AZ) + TimescaleDB     │  │ Cluster                 │  │ Domain            │
  │                       │  │ Primary + 1 Replica     │  │ 3-node cluster    │
  │ • db.r7g.2xlarge      │  │ cache.r7g.large         │  │ m6g.large.search  │
  │ • 500 GB SSD (gp3)    │  │ 16 GB RAM               │  │                   │
  │ • Read replica (1)    │  │                         │  │                   │
  └───────────────────────┘  └─────────────────────────┘  └───────────────────┘

  Separate VPC Subnet:
  ┌────────────────────────────────────────────────────────┐
  │               Airflow (MWAA) + Celery Workers          │
  │  • 4–16 Celery workers (c6g.xlarge Spot instances)     │
  │  • Compute Engine runs here daily                      │
  │  • Isolated from web traffic                           │
  └────────────────────────────────────────────────────────┘

  Storage:
  ┌────────────────────────────────────────────────────────┐
  │  S3 Buckets                                            │
  │  • asx-screener-documents (annual reports, PDFs)       │
  │  • asx-screener-exports   (user CSV/Excel exports)     │
  │  • asx-screener-backups   (DB snapshots)               │
  └────────────────────────────────────────────────────────┘
```

### 4.2 Environments

| Environment | Purpose | Scale |
|---|---|---|
| **Development** | Local dev (Docker Compose) | 1 instance each |
| **Staging** | Pre-prod testing, limited data | Minimal instances |
| **Production** | Live users | Auto-scaled |

### 4.3 Docker Compose (Local Development)

```yaml
services:
  postgres:     # PostgreSQL 16 + TimescaleDB
  redis:        # Redis 7
  elasticsearch: # Elasticsearch 8
  airflow:      # Airflow scheduler + webserver
  api:          # FastAPI backend
  web:          # Next.js frontend
  worker:       # Celery workers
```

---

## 5. Security Design

```
┌────────────────────────────────────────────────────────────┐
│                    SECURITY LAYERS                          │
│                                                             │
│  Layer 1 — Network                                          │
│  • All services in private VPC subnets                     │
│  • DB / Redis / ES: NOT internet-accessible                │
│  • Security groups: strict port allowlisting               │
│  • WAF on CloudFront (block known attack patterns)         │
│                                                             │
│  Layer 2 — Authentication                                   │
│  • NextAuth.js: Google OAuth + Email magic link            │
│  • JWT tokens (15 min access, 7 day refresh)               │
│  • Rate limiting: 100 req/min (free), 1000 req/min (pro)   │
│  • Bcrypt for password hashing                             │
│                                                             │
│  Layer 3 — Authorisation                                    │
│  • Feature flags per subscription tier                     │
│  • Row-level security in PostgreSQL                        │
│  • API endpoints check plan before serving premium data    │
│                                                             │
│  Layer 4 — Data                                             │
│  • Secrets: AWS Secrets Manager (DB passwords, API keys)   │
│  • Encryption at rest: AES-256 (RDS, S3, ElastiCache)     │
│  • Encryption in transit: TLS 1.3 everywhere               │
│  • PII: user emails encrypted in DB                        │
│                                                             │
│  Layer 5 — Application                                      │
│  • Input validation: Pydantic (FastAPI)                    │
│  • SQL injection: parameterised queries only               │
│  • XSS: Next.js content security policy headers            │
│  • CSRF: SameSite cookies + CSRF tokens                    │
└────────────────────────────────────────────────────────────┘
```

---

## 6. Scalability Design

### 6.1 Scale Targets by Phase

| Metric | Phase 1 | Phase 2 | Phase 3 |
|---|---|---|---|
| Registered users | 500 | 10,000 | 100,000 |
| Paying users | 50 | 1,000 | 10,000 |
| API requests/day | 50K | 2M | 50M |
| Stocks covered | 200 | 2,200 | 2,200 |
| DB size (total) | 10 GB | 100 GB | 1 TB |
| Price rows (TimescaleDB) | 500K | 8M | 80M |
| Compute engine runtime | < 10 min | < 20 min | < 30 min |

### 6.2 Bottlenecks & Mitigations

| Bottleneck | Mitigation |
|---|---|
| Screener queries slow | Elasticsearch for complex filters; Redis result cache |
| Compute engine too slow | Parallel workers + vectorized Pandas; batch DB writes |
| Price chart data slow | TimescaleDB continuous aggregates for weekly/monthly OHLCV |
| DB connection exhaustion | PgBouncer connection pooler in front of PostgreSQL |
| AI responses slow | Claude prompt caching; async background generation |
| Peak traffic (market open/close) | Auto-scaling ECS tasks; Redis absorbs read spikes |

---

## 7. Monitoring & Observability

```
┌────────────────────────────────────────────────────────────┐
│                  MONITORING STACK                           │
│                                                             │
│  Application:  Datadog APM + Logs                          │
│  Errors:       Sentry (frontend + backend)                 │
│  Uptime:       Datadog Synthetics (page + API checks)      │
│  DB:           pg_stat_statements + Datadog DB monitoring  │
│  Pipeline:     Airflow Web UI + custom Slack alerts        │
│                                                             │
│  KEY ALERTS (PagerDuty):                                    │
│  • Price ingest fails → immediate alert                    │
│  • Compute engine fails → immediate alert                  │
│  • API p95 latency > 2s → warn                             │
│  • DB disk > 80% → warn                                    │
│  • Redis memory > 85% → warn                               │
│                                                             │
│  DASHBOARDS:                                               │
│  • Data freshness (when each dataset last updated)         │
│  • Compute engine stage timings                            │
│  • API latency per endpoint                                │
│  • Active users / screen runs / alert deliveries           │
└────────────────────────────────────────────────────────────┘
```

---

*Next: See `02_Database_Design_LLD.md` for full database schema*
