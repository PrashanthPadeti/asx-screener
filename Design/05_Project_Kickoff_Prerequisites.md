# ASX Screener — Project Kickoff & Prerequisites

> Version 1.0 | April 2026
> Everything you need to acquire, register, and set up BEFORE writing code.

---

## Quick Answer: Where Do We Start?

```
SEQUENCE (in order — do not skip steps):

WEEK 1:  Business & Legal → Domain → Cloud Accounts → Dev Environment
WEEK 2:  Database (local) → Data Sources → First data flowing
WEEK 3:  Project scaffold → Backend skeleton → First API endpoint
WEEK 4+: Feature development begins (screener, company pages, etc.)
```

---

## PHASE 0 — Before Any Code (Week 1)

### 0.1 — Business & Legal Setup

You need an ABN or ACN to register a `.com.au` domain. You also need it for Stripe payments.

**Option A — Sole Trader (Cheapest, fastest)**
| Step | Where | Cost | Time |
|---|---|---|---|
| Register ABN | business.gov.au/abn-lookup | **Free** | 15 min |
| Register Business Name | business.gov.au | **$44/yr** | 30 min |

**Option B — Pty Ltd Company (Recommended for long-term)**
| Step | Where | Cost | Time |
|---|---|---|---|
| Register company | asic.gov.au or a company formation service | **$597** ASIC fee | 1–2 days |
| ACN automatically issued with company | — | Included | — |
| Register ABN (for the company) | business.gov.au | **Free** | 15 min |

> **Recommendation:** Start as Sole Trader now, convert to Pty Ltd when revenue justifies it.
> You only need the ABN (free) to get started.

---

### 0.2 — Domain Registration

**Recommended Domain Names (check availability):**
```
Primary choices:
  asxscreener.com.au      ← Best — clear, memorable, Australian
  asxanalytics.com.au
  asxfundamentals.com.au
  screener.com.au         ← Premium if available

International backup (if .com.au unavailable):
  asxscreener.com
  asxanalytics.com
```

**Domain Registrars for .com.au:**
| Registrar | Price/yr | Notes |
|---|---|---|
| Crazy Domains | ~$15 AUD | Cheap, Australian |
| Netregistry | ~$20 AUD | Australian, good UI |
| GoDaddy | ~$18 AUD | International, widely used |
| Cloudflare Registrar | At-cost (~$10) | Best value, no markup |

> **What you need:** ABN number to register `.com.au`

**Also register:**
- `asxscreener.com` (international backup, $15–20/yr)
- Consider: `app.asxscreener.com.au` (subdomain for the web app)

---

### 0.3 — Cloud & Service Accounts to Create

Create ALL of these accounts in Week 1 (most are free):

```
┌─────────────────────────────────────────────────────────────────────┐
│  ACCOUNT SETUP CHECKLIST                                             │
│                                                                      │
│  INFRASTRUCTURE                                                      │
│  ☐ AWS Account         → aws.amazon.com          Free tier (12mo)  │
│  ☐ Cloudflare Account  → cloudflare.com          Free plan          │
│    (DNS + CDN + DDoS protection — point your domain here)           │
│                                                                      │
│  VERSION CONTROL                                                     │
│  ☐ GitHub Organisation → github.com/organisations Free plan         │
│    Name it: asx-screener (or your brand name)                       │
│    Create repos: asx-screener-web, asx-screener-api,                │
│                  asx-screener-pipeline, asx-screener-infra           │
│                                                                      │
│  STARTUP HOSTING (cheaper than AWS for Phase 1)                     │
│  ☐ Railway.app Account → railway.app             $5/mo Hobby        │
│    (PostgreSQL + TimescaleDB + Redis + API all in one platform)     │
│  ☐ Vercel Account      → vercel.com              Free plan          │
│    (Next.js frontend hosting — free tier is very generous)          │
│                                                                      │
│  PAYMENTS                                                            │
│  ☐ Stripe Account      → stripe.com              Free (1.75% + 30¢)│
│    (Supports Australia, AUD, monthly subscriptions)                 │
│                                                                      │
│  EMAIL                                                               │
│  ☐ Resend Account      → resend.com              Free 3000/mo       │
│    (Transactional email — modern, simple, developer-friendly)       │
│  ☐ Google Workspace    → workspace.google.com    $10 AUD/mo         │
│    (Business email: hello@asxscreener.com.au)                      │
│                                                                      │
│  MONITORING                                                          │
│  ☐ Sentry Account      → sentry.io               Free plan          │
│    (Error tracking — frontend + backend)                            │
│  ☐ UptimeRobot         → uptimerobot.com         Free plan          │
│    (Uptime monitoring, alerts when site goes down)                  │
│                                                                      │
│  AI / DATA                                                           │
│  ☐ Anthropic Account   → console.anthropic.com   Pay as you go      │
│    (Claude API — for AI features, announcement parsing)             │
│  ☐ OpenAI Account      → platform.openai.com     Pay as you go      │
│    (Embeddings API — text-embedding-3-small for vector search)      │
│                                                                      │
│  ANALYTICS                                                           │
│  ☐ PostHog Account     → posthog.com             Free 1M events/mo  │
│    (Product analytics — track which features users use)             │
│                                                                      │
│  DESIGN                                                              │
│  ☐ Figma Account       → figma.com               Free plan          │
│    (UI/UX wireframes and design — we'll use this for wireframes)    │
│                                                                      │
│  COMMUNICATION                                                       │
│  ☐ Slack Workspace     → slack.com               Free plan          │
│    (Team communication + pipeline alert notifications)              │
└─────────────────────────────────────────────────────────────────────┘
```

---

### 0.4 — Monthly Cost Summary (Phase 1 — Development)

```
Phase 1: Development & MVP (months 1–4)

  Domain (.com.au + .com)            ~$4/mo    ($50/yr)
  Google Workspace (email)           $10/mo
  Railway.app (DB + backend)         $20/mo    (PostgreSQL + Redis)
  Vercel (frontend)                  $0/mo     (free tier)
  Anthropic Claude API               $30/mo    (announcements + AI)
  OpenAI Embeddings                  $5/mo
  Stripe (no monthly fee)            $0/mo     (per-transaction only)
  Resend (email)                     $0/mo     (free tier)
  Sentry                             $0/mo     (free tier)
  ─────────────────────────────────────────────
  TOTAL PHASE 1:                     ~$70 AUD/mo

Phase 2: Launch (months 5–8) — add as you grow
  AWS RDS PostgreSQL (db.t4g.medium) $80/mo
  AWS ElastiCache Redis              $30/mo
  AWS ECS (API + workers)            $100/mo
  Data provider (Morningstar/basic)  $500/mo
  ─────────────────────────────────────────────
  TOTAL PHASE 2:                     ~$750 AUD/mo
  Break-even: ~26 Pro subscribers ($29/mo)
```

---

## PHASE 1 — Development Environment Setup (Week 1–2)

### 1.1 — Your Local Machine Requirements

| Tool | Version | Purpose | Install From |
|---|---|---|---|
| **Git** | 2.40+ | Version control | git-scm.com |
| **Python** | 3.12+ | Backend, pipelines, compute engine | python.org |
| **Node.js** | 20 LTS | Frontend (Next.js) | nodejs.org |
| **Docker Desktop** | Latest | Local DB + services | docker.com/desktop |
| **VS Code** | Latest | Code editor | code.visualstudio.com |
| **DBeaver** | Latest | Database GUI | dbeaver.io (free) |
| **Postman** | Latest | API testing | postman.com (free) |

**VS Code Extensions to install:**
```
Python (Microsoft)
Pylance
ESLint
Prettier
Tailwind CSS IntelliSense
PostgreSQL (Chris Kolkman)
Docker
GitLens
Thunder Client (API testing inside VS Code)
```

---

### 1.2 — Local Development Setup (Docker Compose)

This is your local development stack — mirrors production exactly.

**Directory structure to create:**
```
asx-screener/
├── api/                    ← FastAPI backend
│   ├── app/
│   │   ├── routers/
│   │   ├── models/
│   │   ├── services/
│   │   └── main.py
│   ├── requirements.txt
│   └── Dockerfile
│
├── web/                    ← Next.js frontend
│   ├── src/
│   │   ├── app/
│   │   ├── components/
│   │   └── lib/
│   ├── package.json
│   └── Dockerfile
│
├── pipeline/               ← Airflow DAGs + workers
│   ├── dags/
│   │   ├── price_ingest.py
│   │   ├── compute_engine.py
│   │   └── announcements.py
│   ├── compute_engine/
│   └── requirements.txt
│
├── infra/                  ← Infrastructure as code
│   ├── docker-compose.yml
│   ├── docker-compose.prod.yml
│   └── terraform/          ← (Phase 2 — AWS setup)
│
└── .env.example            ← Template for environment variables
```

**docker-compose.yml (local dev):**
```yaml
version: '3.8'

services:

  postgres:
    image: timescale/timescaledb-ha:pg16-latest
    environment:
      POSTGRES_DB: asx_screener
      POSTGRES_USER: asx_admin
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./infra/sql/init/:/docker-entrypoint-initdb.d/
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U asx_admin -d asx_screener"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    command: redis-server --maxmemory 512mb --maxmemory-policy allkeys-lru
    volumes:
      - redis_data:/data

  elasticsearch:
    image: docker.elastic.co/elasticsearch/elasticsearch:8.13.0
    environment:
      - discovery.type=single-node
      - xpack.security.enabled=false
      - "ES_JAVA_OPTS=-Xms512m -Xmx512m"
    ports:
      - "9200:9200"
    volumes:
      - es_data:/usr/share/elasticsearch/data

  api:
    build: ./api
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql://asx_admin:${DB_PASSWORD}@postgres:5432/asx_screener
      REDIS_URL: redis://redis:6379/0
      ES_URL: http://elasticsearch:9200
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY}
      SECRET_KEY: ${SECRET_KEY}
    depends_on:
      postgres:
        condition: service_healthy
    volumes:
      - ./api:/app
    command: uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

  web:
    build: ./web
    ports:
      - "3000:3000"
    environment:
      NEXT_PUBLIC_API_URL: http://localhost:8000
    volumes:
      - ./web:/app
      - /app/node_modules
    command: npm run dev

  airflow:
    image: apache/airflow:2.9.0-python3.12
    environment:
      AIRFLOW__CORE__EXECUTOR: LocalExecutor
      AIRFLOW__DATABASE__SQL_ALCHEMY_CONN: postgresql://asx_admin:${DB_PASSWORD}@postgres:5432/asx_screener_airflow
      AIRFLOW__CORE__FERNET_KEY: ${AIRFLOW_FERNET_KEY}
    ports:
      - "8080:8080"
    volumes:
      - ./pipeline/dags:/opt/airflow/dags
      - ./pipeline/compute_engine:/opt/airflow/compute_engine
    depends_on:
      - postgres
    command: airflow standalone

volumes:
  postgres_data:
  redis_data:
  es_data:
```

**Start local environment:**
```bash
# Clone repo
git clone https://github.com/your-org/asx-screener
cd asx-screener

# Copy environment variables template
cp .env.example .env
# Edit .env with your values

# Start all services
docker compose up -d

# Check all services are healthy
docker compose ps

# View logs
docker compose logs -f api
```

---

### 1.3 — Environment Variables (.env.example)

```bash
# ─── Database ───────────────────────────────────────
DB_PASSWORD=your_secure_password_here
DATABASE_URL=postgresql://asx_admin:${DB_PASSWORD}@localhost:5432/asx_screener

# ─── Redis ──────────────────────────────────────────
REDIS_URL=redis://localhost:6379/0

# ─── Elasticsearch ──────────────────────────────────
ES_URL=http://localhost:9200

# ─── Auth ───────────────────────────────────────────
SECRET_KEY=generate_with_openssl_rand_hex_32
NEXTAUTH_SECRET=generate_with_openssl_rand_hex_32
NEXTAUTH_URL=http://localhost:3000

# Google OAuth (from Google Cloud Console)
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=

# ─── AI APIs ────────────────────────────────────────
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...         # For embeddings (text-embedding-3-small)

# ─── Payments ───────────────────────────────────────
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PUBLISHABLE_KEY=pk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...

# ─── Email ──────────────────────────────────────────
RESEND_API_KEY=re_...
FROM_EMAIL=hello@asxscreener.com.au

# ─── Data Sources ───────────────────────────────────
# Yahoo Finance: no key needed (uses yfinance library)
# ASIC short data: no key needed (public download)
# ASX announcements: no key needed (public API)

# Phase 2: paid data providers
MORNINGSTAR_API_KEY=      # Leave blank in Phase 1
REFINITIV_API_KEY=        # Leave blank in Phase 1

# ─── AWS (Phase 2+) ─────────────────────────────────
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_REGION=ap-southeast-2   # Sydney region
S3_BUCKET_DOCUMENTS=asx-screener-documents
S3_BUCKET_EXPORTS=asx-screener-exports

# ─── Monitoring ─────────────────────────────────────
SENTRY_DSN=https://...@sentry.io/...
POSTHOG_API_KEY=phc_...

# ─── Airflow ────────────────────────────────────────
AIRFLOW_FERNET_KEY=generate_with_python_fernet
AIRFLOW__CORE__EXECUTOR=LocalExecutor
```

---

## PHASE 2 — Database Setup (Week 2)

### 2.1 — Database Initialisation SQL

Run these in order when PostgreSQL first starts:

```sql
-- 1. Create schemas
CREATE SCHEMA IF NOT EXISTS market;
CREATE SCHEMA IF NOT EXISTS financials;
CREATE SCHEMA IF NOT EXISTS users;
CREATE SCHEMA IF NOT EXISTS ai;

-- 2. Enable extensions
CREATE EXTENSION IF NOT EXISTS timescaledb;      -- Time-series
CREATE EXTENSION IF NOT EXISTS vector;           -- pgvector for AI embeddings
CREATE EXTENSION IF NOT EXISTS pg_trgm;          -- Fuzzy text search
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";      -- UUID generation
CREATE EXTENSION IF NOT EXISTS pg_stat_statements; -- Query performance monitoring

-- 3. Verify TimescaleDB is active
SELECT extname, extversion FROM pg_extension WHERE extname = 'timescaledb';
-- Should return: timescaledb | 2.x.x

-- 4. Set search path
ALTER DATABASE asx_screener SET search_path TO market, financials, users, ai, public;
```

**Then run the full schema from Document 02:**
```bash
# Apply full schema (from 02_Database_Design_LLD.md SQL)
psql -h localhost -U asx_admin -d asx_screener -f infra/sql/schema/01_market.sql
psql -h localhost -U asx_admin -d asx_screener -f infra/sql/schema/02_financials.sql
psql -h localhost -U asx_admin -d asx_screener -f infra/sql/schema/03_users.sql
psql -h localhost -U asx_admin -d asx_screener -f infra/sql/schema/04_ai.sql
```

### 2.2 — Database Migration Tool

Use **Alembic** (Python) for database migrations — never manually alter the production schema.

```bash
cd api
pip install alembic
alembic init alembic

# Create first migration (auto-generates from SQLAlchemy models)
alembic revision --autogenerate -m "initial_schema"
alembic upgrade head
```

---

## PHASE 3 — Data Sources Setup (Week 2)

This is the most critical decision: **where does your financial data come from?**

### 3.1 — Free Data Sources (Use These First)

```
┌─────────────────────────────────────────────────────────────────────┐
│  FREE DATA SOURCES — Available Day 1                                 │
│                                                                      │
│  1. ASX COMPANY LIST                                                 │
│     URL: asx.com.au/asx/research/listedCompanies.do               │
│     Format: CSV download                                             │
│     Contains: ASX Code, Company Name, GICS Industry Group           │
│     Update: Daily (but company list changes rarely)                 │
│     Action: Download once, seed companies table                     │
│                                                                      │
│  2. EOD PRICE DATA                                                   │
│     Library: yfinance (Python)                                       │
│     Install: pip install yfinance                                    │
│     Usage: yf.Ticker("BHP.AX").history(period="max")               │
│     Contains: OHLCV + adjusted prices + splits + dividends          │
│     Limits: No official rate limit but be respectful (< 2K/day)    │
│     Action: Backfill 15 years, then daily updates                   │
│                                                                      │
│  3. ASIC SHORT SELLING DATA                                          │
│     URL: asic.gov.au/regulatory-resources/markets/short-selling/   │
│          short-position-reports/                                     │
│     Format: CSV, published daily ~3:30 PM AEST                      │
│     Contains: ASX Code, Short Position, % of Issued Capital         │
│     Action: Download daily in pipeline                               │
│                                                                      │
│  4. ASX ANNOUNCEMENTS (semi-official)                                │
│     URL: asx.com.au/asx/1/company/{CODE}/announcements             │
│          ?count=20&market_sensitive=false                            │
│     Format: JSON (undocumented but stable)                          │
│     Contains: Headline, date, PDF link, price sensitivity flag      │
│     Rate limit: ~100 req/min across all codes                       │
│     Action: Poll every 5 min for ASX200, 30 min for others         │
│                                                                      │
│  5. S&P/ASX INDEX COMPOSITION                                        │
│     URL: asx.com.au/markets/indices/                                │
│     Format: PDF factsheets (quarterly)                               │
│     Action: Download quarterly, parse to update index flags         │
│                                                                      │
│  6. RBA DATA (Interest Rates, FX)                                    │
│     URL: rba.gov.au/statistics/tables/                              │
│     Format: Excel/CSV                                                │
│     Contains: Cash rate, bond yields, AUD/USD                       │
│     Action: Monthly update for risk-free rate in Sharpe calculation │
└─────────────────────────────────────────────────────────────────────┘
```

### 3.2 — Financial Statements: The Hard Problem

**The reality:** ASX financial statements are NOT freely available in structured format. Here are your options ranked by Phase:

```
┌─────────────────────────────────────────────────────────────────────┐
│  FINANCIAL STATEMENT DATA OPTIONS                                    │
│                                                                      │
│  PHASE 1 (MVP) — Extract from PDFs using AI                         │
│  ─────────────────────────────────────────────────────────────────  │
│  How: Download annual report PDF from ASX → Claude Sonnet extracts  │
│       P&L, Balance Sheet, Cash Flow as structured JSON               │
│  Cost: ~$0.05–0.10 per company per year (Claude API cost)           │
│  Accuracy: ~90–95% (needs manual QA for top 50 stocks)              │
│  Coverage: Start with ASX 200 → expand to ASX 300                   │
│  Time: ~2–3 hours compute to process all ASX 200 annual reports     │
│                                                                      │
│  Setup needed:                                                       │
│  • Anthropic API key (already in .env)                               │
│  • PyMuPDF: pip install pymupdf                                      │
│  • AWS S3 bucket for storing PDFs                                    │
│                                                                      │
│  PHASE 2 (Launch) — Paid data provider                              │
│  ─────────────────────────────────────────────────────────────────  │
│  Option A: Morningstar Direct API                                    │
│    Price: Contact for quote (~$5,000–15,000 AUD/yr)                 │
│    Coverage: All ASX stocks, 15 years history                        │
│    Quality: Excellent, standardised                                  │
│                                                                      │
│  Option B: Refinitiv (LSEG) Eikon/Workspace API                     │
│    Price: ~$20,000+ AUD/yr (institutional pricing)                  │
│    Coverage: Full ASX + global                                       │
│    Quality: Best-in-class                                            │
│                                                                      │
│  Option C: Wisesheets (cheaper alternative)                          │
│    Price: ~$500–2,000 AUD/yr                                        │
│    Coverage: ASX + major markets                                     │
│    Quality: Good for most ratios                                     │
│    Website: wisesheets.io                                            │
│                                                                      │
│  Option D: Financial Modelling Prep (FMP) API                        │
│    Price: ~$300 USD/yr (Basic) → $720 USD/yr (Professional)         │
│    Coverage: ASX coverage is partial (~top 300 stocks)              │
│    Quality: Good for common metrics                                  │
│    Website: financialmodelingprep.com                                │
│    Note: Best value for Phase 2 startup                              │
│                                                                      │
│  ★ RECOMMENDATION FOR PHASE 2:                                      │
│    Start with FMP API ($300/yr) for structured data,                 │
│    supplement with PDF extraction for gaps.                          │
│    Upgrade to Morningstar when revenue > $5K/month.                  │
└─────────────────────────────────────────────────────────────────────┘
```

### 3.3 — Data Source Account Setup

```bash
# Install Python data libraries
pip install yfinance pandas numpy requests beautifulsoup4 \
            pymupdf sqlalchemy psycopg2-binary alembic \
            celery redis anthropic openai fastapi uvicorn \
            python-dotenv pydantic-settings

# Test Yahoo Finance immediately (no account needed)
python -c "
import yfinance as yf
bhp = yf.Ticker('BHP.AX')
hist = bhp.history(period='5d')
print(hist[['Close', 'Volume']])
print('Yahoo Finance: WORKING ✅')
"

# Test ASX Announcements API
python -c "
import requests
r = requests.get('https://www.asx.com.au/asx/1/company/BHP/announcements?count=5')
data = r.json()
print(f'Latest announcement: {data[\"data\"][0][\"headline\"]}')
print('ASX Announcements API: WORKING ✅')
"
```

---

## PHASE 4 — First Data Load (Week 2)

### Priority Order for Data Loading:

```
STEP 1: Seed companies table (30 min)
  → Download ASX company list CSV
  → Import into market.companies table
  → Flag GICS sectors, index membership
  → Result: 2,200 companies in DB

STEP 2: Backfill 5 years of price history (2–4 hours)
  → Use yfinance to fetch 5-year EOD data
  → Write to market.daily_prices (TimescaleDB)
  → Compute technical indicators for full history
  → Result: ~1.1M price rows, tech indicators ready

STEP 3: Load ASX 200 financial statements (1–2 days)
  → Download annual reports from ASX (last 5 years)
  → Run Claude extraction pipeline
  → QA top 50 stocks manually
  → Result: 200 companies × 5 years = 1,000 financial records

STEP 4: Run first compute engine pass
  → Compute all 544 metrics for the 200 stocks with financials
  → Result: First screener results available

STEP 5: Seed ASIC short data (1 day history)
  → Download latest ASIC short positions
  → Result: Short interest for all 2,200 stocks

✅ At this point: you have a working local screener
   covering 200 stocks with full fundamentals.
```

---

## PHASE 5 — Python Project Setup

### 5.1 — Backend (FastAPI) Project Init

```bash
cd api
python -m venv venv
source venv/Scripts/activate  # Windows bash

pip install fastapi uvicorn[standard] sqlalchemy alembic \
            asyncpg psycopg2-binary redis anthropic \
            python-jose passlib python-multipart \
            pandas numpy yfinance requests \
            python-dotenv pydantic-settings

# Create requirements.txt
pip freeze > requirements.txt

# Run API
uvicorn app.main:app --reload
# API available at: http://localhost:8000
# Auto-docs at:     http://localhost:8000/docs
```

**api/app/main.py (starter):**
```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="ASX Screener API",
    version="0.1.0",
    docs_url="/docs",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health_check():
    return {"status": "ok", "version": "0.1.0"}

@app.get("/api/v1/stocks/{asx_code}")
def get_stock(asx_code: str):
    # TODO: implement
    return {"asx_code": asx_code.upper()}
```

### 5.2 — Frontend (Next.js) Project Init

```bash
cd web

# Create Next.js app with TypeScript + Tailwind
npx create-next-app@latest . \
  --typescript \
  --tailwind \
  --eslint \
  --app \
  --src-dir \
  --import-alias "@/*"

# Install additional dependencies
npm install \
  @tanstack/react-query \
  @tanstack/react-table \
  zustand \
  react-hook-form \
  zod \
  lightweight-charts \
  recharts \
  next-auth \
  @radix-ui/react-dialog \
  @radix-ui/react-dropdown-menu \
  clsx \
  tailwind-merge \
  lucide-react

# Start dev server
npm run dev
# Frontend at: http://localhost:3000
```

---

## Full Prerequisites Summary Checklist

```
LEGAL & BUSINESS
☐ Register ABN (business.gov.au) — FREE, 15 min
☐ Register business name — $44 AUD

DOMAINS (register in order)
☐ Register asxscreener.com.au (or chosen name) — ~$15/yr
☐ Register asxscreener.com (backup) — ~$15/yr
☐ Point both domains to Cloudflare nameservers — FREE

ACCOUNTS (all free to create)
☐ GitHub Organisation — FREE
☐ AWS Account — FREE tier
☐ Cloudflare — FREE
☐ Railway.app — FREE then $5/mo
☐ Vercel — FREE
☐ Stripe — FREE (1.75% + 30¢ per transaction)
☐ Resend (email) — FREE
☐ Google Workspace — $10 AUD/mo
☐ Anthropic Console — pay-as-you-go
☐ Sentry — FREE
☐ PostHog — FREE

LOCAL MACHINE
☐ Git installed and configured
☐ Python 3.12 installed
☐ Node.js 20 LTS installed
☐ Docker Desktop installed and running
☐ VS Code installed with extensions
☐ DBeaver installed (database GUI)

REPOSITORIES
☐ GitHub org created
☐ asx-screener-api repo created
☐ asx-screener-web repo created
☐ asx-screener-pipeline repo created
☐ .gitignore configured (ignore .env files!)

LOCAL ENVIRONMENT
☐ docker-compose.yml created (from above)
☐ .env file created from .env.example
☐ docker compose up -d — all services healthy
☐ Database schemas applied
☐ TimescaleDB extension verified

FIRST DATA
☐ ASX company list downloaded and imported
☐ 5-year price history backfilled (yfinance)
☐ ASIC short data loaded
☐ ASX 200 annual reports downloaded
☐ Claude extraction pipeline run for financial statements
☐ First compute engine run completed

✅ READY TO BUILD
```

---

## Recommended Week-by-Week Plan

```
WEEK 1 (Days 1–7): Setup & Accounts
  Mon:  Register ABN + business name + domains
  Tue:  Create all cloud accounts (GitHub, AWS, Vercel, Stripe, etc.)
  Wed:  Install local dev tools (Python, Node, Docker, VS Code)
  Thu:  Set up Docker Compose, get DB running locally
  Fri:  Apply database schema, verify TimescaleDB working
  Sat:  Load ASX company list, first yfinance test
  Sun:  Download ASX 200 annual reports (start the download)

WEEK 2 (Days 8–14): Data Foundation
  Mon:  Backfill 5-year price history (let it run)
  Tue:  Build Claude PDF extraction pipeline (run against 10 stocks to test)
  Wed:  QA extracted financials vs actual reports for accuracy
  Thu:  Run extraction on all ASX 200
  Fri:  First compute engine run — verify metrics look right vs ASX data
  Sat:  Set up ASIC short data pipeline
  Sun:  Set up ASX announcements poller (first version)

WEEK 3 (Days 15–21): First API Endpoints
  Mon:  FastAPI project scaffold
  Tue:  /api/v1/stocks endpoint (search + basic data)
  Wed:  /api/v1/screener/run endpoint (basic version)
  Thu:  /api/v1/companies/{code}/overview endpoint
  Fri:  User auth (NextAuth.js + email)
  Sat:  Connect Next.js frontend to API
  Sun:  Basic stock search working in browser

WEEK 4 (Days 22–28): First Feature Complete
  → Screener query builder UI
  → Company detail page (first pass)
  → Show it to 5 beta users for feedback

FROM WEEK 5: Build features as per roadmap in 01_Architecture_and_HLD.md
```

---

*This document covers everything needed before and during initial setup.*
*Next: `06_Frontend_Wireframes.md` — UI design for all major pages*
