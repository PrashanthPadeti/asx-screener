# ASX Screener — Current State & Architecture Reference
## June 2026 Edition

> **Production URL:** https://asxscreener.com.au  
> **Server:** Digital Ocean ubuntu-s-2vcpu-4gb-syd1 (Sydney)  
> **Status:** ✅ Live & Active  
> **Last Updated:** June 2026

---

## Executive Summary

ASX Screener (asxscreener.com.au) is a production institutional-grade stock screening platform for the Australian Securities Exchange. It provides real-time filtering of 1,300+ ASX-listed stocks across 200+ metrics, 31 pre-built investment screens, AI-powered natural language queries, sector browsing, watchlists, portfolios, and alerts. The platform serves Free, Pro, and Premium subscription tiers.

---

## 1. System Architecture

### 1.1 Technology Stack

| Component | Technology | Version/Detail |
|-----------|-----------|----------------|
| Frontend | Next.js (Turbopack) | 16.2.4 |
| Frontend Runtime | PM2 | Latest, Port 8000 |
| Backend API | FastAPI (Python) | Async endpoints |
| Backend Runtime | Uvicorn (systemd) | asx-api.service |
| Database | PostgreSQL | Active |
| Hosting | Digital Ocean | ubuntu-s-2vcpu-4gb-syd1, Sydney |
| Domain | asxscreener.com.au | Production TLS |
| AI Engine | Claude (Anthropic) | Premium feature |
| Data Provider | EODHD | Prices + Fundamentals |
| Short Data | ASIC | Weekly regulatory data |
| Styling | Tailwind CSS | Flexbox preferred over bracket notation |

### 1.2 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        USERS (Browser)                       │
└─────────────────────────┬───────────────────────────────────┘
                          │ HTTPS
┌─────────────────────────▼───────────────────────────────────┐
│          Next.js Frontend (PM2, Port 8000)                   │
│  /screener  /scans  /market  /company  /admin  ...           │
└─────────────────────────┬───────────────────────────────────┘
                          │ REST API (JSON)
┌─────────────────────────▼───────────────────────────────────┐
│          FastAPI Backend (Uvicorn, systemd)                   │
│  /api/v1/screener  /api/v1/market  /api/v1/companies  ...    │
└─────────────────────────┬───────────────────────────────────┘
                          │ SQL (asyncpg)
┌─────────────────────────▼───────────────────────────────────┐
│              PostgreSQL Database                              │
│  screener.universe  |  companies  |  daily_prices  |  ...    │
└─────────────────────────▲───────────────────────────────────┘
                          │ Compute Jobs (cron)
┌─────────────────────────┴───────────────────────────────────┐
│                   Data Pipeline                              │
│  EODHD (prices/fundamentals) → compute jobs → universe view  │
│  ASIC (short positions) → short_positions table              │
│  ASX (companies/announcements) → companies table             │
└─────────────────────────────────────────────────────────────┘
```

### 1.3 Deployment Process

```bash
# Deploy command (run on server)
cd /opt/asx-screener && ./deploy.sh

# What deploy.sh does:
# 1. git pull (from remote)
# 2. pip install (if Python deps changed)
# 3. Restart backend (systemd: asx-api.service)
# 4. npm run build (Next.js production build)
# 5. PM2 restart (asx-frontend)
# 6. Status check (ports, PM2, systemd)
```

> **Note:** Server-side code edits via Node.js scripts do NOT sync to git automatically.
> Windows local code and server code may diverge between sessions.
> For hotfixes: edit server files directly. For releases: commit + push → deploy.

---

## 2. Frontend Pages & Features

### 2.1 Page Inventory

| Route | Page Name | Access | Description |
|-------|-----------|--------|-------------|
| `/screener` | Stock Screener | All | **CORE PAGE** — main filtering interface |
| `/scans` | Alpha Screens | All | 31 pre-built institutional screens |
| `/market` | Market Overview | All | ASX market summary, indices, sectors |
| `/company/[code]` | Company Detail | All | Individual stock deep-dive |
| `/watchlist` | Watchlist | Logged In | Personal stock watchlist |
| `/portfolio` | Portfolio | Logged In | Portfolio tracking & P&L |
| `/alerts` | Alerts | Logged In | Price and metric alerts |
| `/pricing` | Pricing | All | Subscription plans |
| `/admin` | Admin Panel | **Admin Only** | System health, jobs, data management |

### 2.2 Stock Screener Page (`/screener`) — CORE PAGE

**Layout:** Single column on mobile, 2-column on desktop (main content + Browse Sectors sidebar)

#### Header Section
```
[Stock Screener ●Live]          [Help] [Filter Screen] [AI Query PREMIUM]
Filter 1,300+ ASX stocks with institutional-grade metrics
```

#### Alpha Screens Quick Access Banner
Dark gradient (slate-900 → blue-950 → indigo-900) with 5 horizontal cards:

| Card | Link | Count |
|------|------|-------|
| 🏆 Premium | `/scans#premium-screens` | 11 screens |
| 📊 Pro Strategies | `/scans#pro-strategies` | 15 screens |
| ⚡ Quick Screens | `/scans#quick-screens` | 4 free |
| 🌐 Sector Screens | `/scans#sector-screens` | 12 sectors |
| 👥 Community | `/scans#community-picks` | User picks |

#### Filter Screen Mode
- **Market Cap quick-filter:** All | Mega ≥$50B | Large $10B-$50B | Mid $2B-$10B | Small $300M-$2B | Micro $50M-$300M | Nano <$50M
- **Empty state** (when no filters): 3 example cards (Value Income, Quality Growth, Deep Value) — clicking populates filters only, user runs manually
- **Filter rows:** Field selector → Operator → Value → Delete
- **200+ filterable fields** grouped by category
- **Buttons:** Run Screen | Save Screen | My Screens
- **Results:** Sortable table | Pagination (50/page) | CSV Export (Pro+)

#### AI Query Mode (Premium Only)
- Dark gradient panel
- Natural language input → Claude AI → filters → results
- Examples shown to guide usage

#### Browse Sectors Sidebar (Desktop ≥1024px only)
- Sticky right sidebar (256px wide)
- 12 GICS sectors with live stock counts (from `/api/v1/market/sectors`)
- Click → applies sector filter + runs screener
- Hidden on mobile/tablet (`hidden lg:block`)

### 2.3 Alpha Screens Page (`/scans`)

**Display Name:** Alpha Screens  
**Navigation Label:** Alpha Screens (renamed from "Scans")  
**URL:** /scans (unchanged for SEO)

#### Stats Bar
```
31 Total Screens  |  4 Free  |  27 Pro + Premium
```

#### 5 Sections (with section IDs for anchor navigation)

| Section | ID | Color | Count | Badge |
|---------|-----|-------|-------|-------|
| Premium Screens | `#premium-screens` | Purple | 11 | PREMIUM |
| Pro Strategies | `#pro-strategies` | Blue | 15 | PRO |
| Quick Screens | `#quick-screens` | Yellow | 4 | Free |
| Sector Screens | `#sector-screens` | Slate | 12 | Free |
| Community Picks | `#community-picks` | Green | Dynamic | — |

#### Card Features
- Theme-based background color per investment type (see Appendix A)
- Correct PRO vs PREMIUM badge differentiation
- First 3 filter pills shown as preview chips
- Hover: `-translate-y-0.5` + shadow
- Click → `/screener?preset=[id]` (loads screener with preset)
- Scroll-to-anchor on hash navigation (useEffect, 400ms + 900ms double-fire)

---

## 3. Alpha Screens Catalog (All 31 Screens)

### 3.1 Quick Screens — Free (4 screens)

| ID | Name | Key Filters | Sort By |
|----|------|-------------|---------|
| `value_franked` | Value + Fully Franked | PE ≤ 15, Franking 100%, Div Yield ≥ 3%, Net Margin > 0 | Grossed-up Yield ↓ |
| `momentum` | Price Momentum | Return 3M ≥ 10%, Above SMA200, ADX ≥ 25, RSI ≤ 65 | Return 3M ↓ |
| `piotroski_strong` | Piotroski Strong (F ≥ 7) | F-Score ≥ 7, Mkt Cap ≥ 100M | F-Score ↓ |
| `turnaround` | Potential Turnaround | RSI ≤ 35, FCF > 0, D/E ≤ 1.5 | RSI ↑ |

### 3.2 Pro Strategies — Pro Plan Required (15 screens)

| ID | Name | Key Filters | New? |
|----|------|-------------|------|
| `dividend_income` | Dividend Income Portfolio | Yield ≥ 4%, Franking ≥ 70% | — |
| `quality_undervalued` | Quality Undervalued | PE ≤ 15, F-Score ≥ 7, ROE ≥ 12%, D/E ≤ 0.5 | — |
| `high_growth` | Fast Growing Companies | Rev Growth ≥ 20%, EPS Growth ≥ 15% | — |
| `ma_crossover` | 50/200-Day MA Crossover | Above SMA50 & SMA200, Return 1M ≥ 3% | — |
| `new_52w_highs` | New 52-Week Highs | Within 5% of 52W High, Return 3M ≥ 5% | — |
| `deep_value_growth` | P/E < 10 + EPS Growth | PE 0-10, EPS Growth ≥ 5% | — |
| `halfyearly_acceleration` | Half-Yearly Acceleration | Rev HoH ≥ 10%, NI HoH ≥ 10% | — |
| `new_52w_lows` | Near 52-Week Lows | Within 10% of 52W Low, RSI ≤ 40 | — |
| `volume_breakout` | Volume Breakout | Volume Ratio ≥ 2x, Return 1W ≥ 3% | — |
| `rsi_oversold` | RSI Oversold (< 30) | RSI ≤ 30, Cap ≥ 100M | — |
| `rsi_overbought` | RSI Overbought (> 70) | RSI ≥ 70, Return 3M ≥ 5% | — |
| `cash_flow_champion` | Cash Flow Champion | FCF Yield ≥ 5%, ROE ≥ 12%, D/E ≤ 0.5 | ★ NEW |
| `dividend_growth_machine` | Dividend Growth Machine | Consec Yrs ≥ 5, Div CAGR 3Y ≥ 5%, Payout ≤ 80% | ★ NEW |
| `earnings_momentum_surge` | Earnings Momentum Surge | EPS Growth ≥ 25%, Rev Growth ≥ 15%, Above SMA200 | ★ NEW |
| `roic_compounder` | ROIC Compounder | Avg ROIC 3Y ≥ 15%, ROIC ≥ 12%, Rev Growth ≥ 8% | ★ NEW |
| `gross_margin_fortress` | Gross Margin Fortress | Avg Gross Margin 5Y ≥ 40%, ROE ≥ 15% | ★ NEW |

### 3.3 Premium Screens — Premium Plan Required (11 screens)

| ID | Name | Key Filters | New? |
|----|------|-------------|------|
| `ai_top5` | AI Ranked Top 5 | F-Score ≥ 7, ROE ≥ 15%, EPS Growth ≥ 10%, Above SMA200, Cap ≥ 500M | — |
| `mining_value` | Advanced Mining Value Screen | is_miner, PE 0-15, F-Score ≥ 6, Cap ≥ 100M | — |
| `areit_income` | A-REIT Income Screen | is_reit, Div Yield ≥ 5%, Margin > 0 | — |
| `franking_optimiser` | Franking Credit Optimiser | Franking 100%, Grossed Yield ≥ 7%, F-Score ≥ 5 | — |
| `short_interest_risk` | Short Interest Risk Screen | Short Pct ≥ 5%, Cap ≥ 100M | — |
| `multi_factor_qm` | Multi-Factor Quality + Momentum | ROE ≥ 15%, Margin ≥ 8%, Rev Growth ≥ 10%, Above SMA200 | — |
| `asx_dividend_aristocrats` | ASX Dividend Aristocrats | Consec Yrs ≥ 7, Div CAGR 5Y ≥ 5%, Franking ≥ 50%, Cap ≥ 500M | ★ NEW |
| `quality_elite_compounder` | Quality Elite Compounder | ROE ≥ 20%, Avg ROIC 5Y ≥ 15%, Margin ≥ 12%, D/E ≤ 0.3 | ★ NEW |
| `altman_safety_screen` | Altman Z-Score Safety | Altman Z ≥ 3, Current Ratio ≥ 2, D/E ≤ 0.5, F-Score ≥ 6 | ★ NEW |
| `low_beta_income_shield` | Low Beta Income Shield | Beta ≤ 0.8, Div Yield ≥ 3%, Franking ≥ 50%, Cap ≥ 500M | ★ NEW |
| `small_cap_hidden_gems` | Small Cap Hidden Gems | Cap $50M-$500M, F-Score ≥ 7, Rev Growth ≥ 20%, Margin ≥ 5% | ★ NEW |

---

## 4. Backend API Architecture

### 4.1 Framework
- **FastAPI** (Python) with async/await throughout
- **Uvicorn** ASGI server
- **systemd** service: `asx-api.service`
- **PostgreSQL** via asyncpg driver

### 4.2 Key API Routes

| Method | Route | Auth | Description |
|--------|-------|------|-------------|
| POST | `/api/v1/screener/run` | Optional | Execute screener query |
| GET | `/api/v1/screener/fields` | None | All filterable fields + metadata |
| GET | `/api/v1/screener/presets` | None | All 31 pre-built presets |
| GET | `/api/v1/market/sectors` | None | Sector stats + live stock counts |
| GET | `/api/v1/market/overview` | None | Market summary, indices |
| GET | `/api/v1/companies/{code}` | None | Company detail data |
| POST | `/api/v1/ai/query` | Premium | AI natural language screener |
| GET | `/api/v1/watchlist` | Required | User watchlist |
| POST | `/api/v1/screens/save` | Required | Save custom screen |
| GET | `/api/v1/screens/community` | None | Public community screens |
| GET | `/api/v1/admin/health` | Admin | System health metrics |

### 4.3 Screener Filter Fields (200+ metrics)

**Valuation:** `pe_ratio`, `pb_ratio`, `ps_ratio`, `ev_to_ebitda`, `peg_ratio`, `fcf_yield`, `price_to_fcf`

**Profitability:** `net_margin`, `gross_margin`, `ebitda_margin`, `operating_margin`, `roe`, `roa`, `roic`, `avg_roic_3y`, `avg_roic_5y`

**Quality:** `piotroski_f_score`, `altman_z_score`, `debt_to_equity`, `current_ratio`, `net_debt`, `percent_insiders`

**Growth:** `revenue_growth_1y`, `earnings_growth_1y`, `revenue_growth_hoh`, `net_income_growth_hoh`, `avg_roa_3y`, `avg_roa_5y`, `avg_roe_3y`, `avg_roe_5y`, `avg_roce_3y`, `avg_roce_5y`, `avg_net_margin_3y`, `avg_net_margin_5y`, `fcf_cagr_3y`, `fcf_cagr_5y`, `avg_gross_margin_3y`, `avg_gross_margin_5y`

**Dividends:** `dividend_yield`, `franking_pct`, `grossed_up_yield`, `payout_ratio`, `dividend_cagr_3y`, `dividend_cagr_5y`, `dividend_consecutive_yrs`

**Technicals:** `rsi_14`, `adx_14`, `above_sma20`, `above_sma50`, `above_sma200`, `return_1w`, `return_1m`, `return_3m`, `return_1y`, `momentum_3m`, `momentum_6m`, `volume`, `volume_ratio`, `volatility_20d`, `volatility_60d`, `beta_1y`, `beta_3y`, `sharpe_1y`, `bb_width`, `pct_from_52w_high`, `pct_from_52w_low`

**ASX-Specific:** `is_miner`, `is_reit`, `short_pct`, `nta_discount_premium`, `franking_pct`

---

## 5. Database Architecture

### 5.1 Key Tables

| Table/View | Purpose | Updated |
|------------|---------|---------|
| `screener.universe` | Main 200+ column screener view | After each compute |
| `companies` | ASX company master data | Daily |
| `daily_prices` | EOD prices from EODHD | Daily |
| `annual_metrics` | Yearly fundamental metrics | Weekly |
| `quarterly_metrics` | Quarterly P&L data | Quarterly |
| `halfyearly_metrics` | HoH acceleration (ASX-specific) | Half-yearly |
| `technical_indicators` | RSI, SMA, ADX, momentum | Daily |
| `short_positions` | ASIC short interest data | Weekly |
| `watchlist` | User watchlist entries | Real-time |
| `saved_screens` | User-saved filter screens | Real-time |
| `subscriptions` | User subscription/plan data | Real-time |

### 5.2 Screener Universe View
The `screener.universe` materialized view joins all metric tables into a single 200+ column queryable view. The screener API builds dynamic SQL `WHERE` clauses from user filters and queries this view directly.

```sql
-- Simplified example of what the screener generates:
SELECT asx_code, company_name, sector, price, market_cap, pe_ratio, roe, dividend_yield, ...
FROM screener.universe
WHERE pe_ratio <= 15
  AND franking_pct = 100
  AND dividend_yield >= 3
  AND net_margin > 0
ORDER BY grossed_up_yield DESC
LIMIT 50 OFFSET 0;
```

---

## 6. Data Pipeline & Job Executions

### 6.1 Data Sources

| Source | Data Type | Frequency | Method |
|--------|-----------|-----------|--------|
| EODHD | EOD prices, dividends, splits | Daily | REST API download |
| EODHD | Fundamentals (P&L, balance sheet, cash flow) | Weekly | Bulk download |
| ASIC | Short position reports | Weekly (Tuesdays) | CSV download |
| ASX | Company listings, announcements | Daily | ASX website |
| Internal | Compute engines | Various | Python scripts |

### 6.2 Compute Job Schedule

| Script | Cron Schedule | What It Computes |
|--------|---------------|-----------------|
| `compute_daily.py` | Daily post-market | Price updates, RSI, SMA 20/50/200, ADX, momentum 3M/6M, volume ratios, 52W high/low, beta, volatility |
| `compute_weekly.py` | Saturday | Revenue growth, EPS growth, margins, ROE, ROA from EODHD fundamental refresh |
| `compute_monthly.py` | 1st of month | Composite quality scores, AI ranking model, sector benchmarks |
| `compute_quarterly.py` | Quarterly | Quarterly EPS, revenue, D/E ratio updates |
| `compute_halfyearly.py` | After HY results | HoH acceleration metrics (revenue_growth_hoh, net_income_growth_hoh) |
| `compute_yearly.py` | Annually | 3Y/5Y averages for ROE, ROA, ROIC, ROCE, gross margins; Altman Z-Score |
| `build_screener_universe.py` | After each compute | Rebuilds `screener.universe` materialized view |

### 6.3 End-to-End Data Flow

```
┌──────────────────────────────────────────────────────────────┐
│ STEP 1: Data Ingestion                                        │
│  EODHD API → download_daily_prices.py → daily_prices table   │
│  EODHD API → download_fundamentals.py → annual_metrics       │
│  ASIC CSV  → load_short_positions.py  → short_positions      │
│  ASX data  → load_asx_companies.py   → companies table       │
└──────────────────────────┬───────────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────┐
│ STEP 2: Compute Engines                                       │
│  compute_daily.py   → technical_indicators table             │
│  compute_weekly.py  → weekly_metrics table                   │
│  compute_monthly.py → composite_scores table                 │
│  compute_yearly.py  → long_term_metrics table                │
└──────────────────────────┬───────────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────┐
│ STEP 3: Screener Universe Rebuild                            │
│  build_screener_universe.py → REFRESH MATERIALIZED VIEW      │
│                               screener.universe              │
└──────────────────────────┬───────────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────┐
│ STEP 4: API Serving                                          │
│  FastAPI /api/v1/screener/run → queries screener.universe    │
└──────────────────────────┬───────────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────┐
│ STEP 5: User Interface                                        │
│  Next.js renders results → user sees filtered stocks         │
└──────────────────────────────────────────────────────────────┘
```

### 6.4 Admin Panel Job Management
- **System Health:** CPU, Memory, Disk gauges (live)
- **Manual Triggers:** Button for each compute job
- **ETF/Fund Prices:** Separate update trigger
- **Weekly Fundamentals:** Manual refresh button
- **Short Positions:** ASIC data refresh
- **Historical Predictions:** ML model prediction tracking (admin only)

---

## 7. Subscription Plans & Feature Access

| Feature | Free | Pro | Premium |
|---------|:----:|:---:|:-------:|
| Quick Screens (4) | ✅ | ✅ | ✅ |
| Pro Strategies (15) | ❌ | ✅ | ✅ |
| Premium Screens (11) | ❌ | ❌ | ✅ |
| Sector Screens (12) | ✅ | ✅ | ✅ |
| Community Screens | ✅ | ✅ | ✅ |
| Browse Sectors (sidebar) | ✅ | ✅ | ✅ |
| AI Query | ❌ | ❌ | ✅ |
| CSV Export | ❌ | ✅ | ✅ |
| Results Limit | 500 | All | All |
| Watchlist | ✅ | ✅ | ✅ |
| Portfolio | ✅ | ✅ | ✅ |
| Alerts | Limited | ✅ | ✅ |
| Save Screens | ✅ | ✅ | ✅ |
| Community Share | ✅ | ✅ | ✅ |

**Plan IDs in code:** `free`, `pro`, `premium`, `enterprise_pro`, `enterprise_premium`

---

## 8. Navigation & UI Structure

### 8.1 Main Navigation Bar
```
[ASX Screener logo] [Screener] [Market] [Alpha Screens] [Resources ▾] [Premium Data ▾] [Admin ▾*]
                                                    [🔍 Search ASX...] [A Premium ▾]
```
*Admin tab: **hidden from all non-admin users**

### 8.2 Screener Mode Toggle
```
[🔲 Filter Screen]  [✨ AI Query  PREMIUM]
```

---

## 9. Project File Structure

### 9.1 Server (`/opt/asx-screener/`)

```
/opt/asx-screener/
├── deploy.sh                          # Deployment script
├── frontend/                          # Next.js 16.2.4 app
│   ├── app/
│   │   ├── screener/
│   │   │   ├── page.tsx               # ★ CORE PAGE — Stock Screener
│   │   │   └── components/
│   │   │       └── BrowseSectors.tsx  # Sector sidebar component
│   │   ├── scans/
│   │   │   └── page.tsx               # Alpha Screens page
│   │   ├── market/page.tsx
│   │   ├── company/[code]/page.tsx
│   │   ├── admin/page.tsx             # Admin only
│   │   ├── watchlist/page.tsx
│   │   ├── portfolio/page.tsx
│   │   ├── alerts/page.tsx
│   │   └── pricing/page.tsx
│   ├── components/
│   │   ├── Navbar.tsx                 # "Alpha Screens" nav label
│   │   ├── HelpDrawer.tsx
│   │   └── WatchlistButton.tsx
│   └── lib/
│       ├── api.ts                     # API hooks (getMarketSectors, etc.)
│       ├── utils.ts                   # SECTORS[], SECTOR_COLORS{}
│       ├── auth.ts                    # useAuth hook
│       └── helpContent.ts
├── backend/
│   └── app/
│       ├── api/v1/routes/
│       │   ├── screener.py            # ★ 31 presets defined here
│       │   ├── market.py              # /market/sectors endpoint
│       │   ├── companies.py
│       │   ├── ai.py                  # Claude AI query
│       │   └── saved_screens.py
│       ├── services/
│       └── workers/
├── jobs/compute/
│   ├── compute_daily.py
│   ├── compute_weekly.py
│   ├── compute_monthly.py
│   ├── compute_quarterly.py
│   ├── compute_halfyearly.py
│   └── compute_yearly.py
└── scripts/
    ├── eodhd/                         # EODHD data downloaders
    ├── asic/                          # ASIC short position loader
    └── asx/                           # ASX company data
```

---

## 10. Current Deployment Status (June 2026)

### 10.1 Production Snapshot

| Metric | Value |
|--------|-------|
| URL | https://asxscreener.com.au |
| Server | ubuntu-s-2vcpu-4gb-syd1 (Sydney) |
| Frontend | Next.js 16.2.4, PM2, online ✅ |
| Backend | FastAPI uvicorn, systemd, ~94-97MB RAM ✅ |
| Database | PostgreSQL, active ✅ |
| Stocks tracked | 1,300+ ASX listings |
| Total screens | 31 (4 free + 15 pro + 11 premium + 12 sectors) |
| Deploy count | 147+ successful deployments |

### 10.2 Features Added (June 2026 Session)

1. ✅ **Browse Sectors sidebar** — sticky right panel on screener (desktop ≥1024px)
2. ✅ **Alpha Screens page redesign** — 4 organized sections + color-coded cards
3. ✅ **10 new institutional screens** — 5 Pro + 5 Premium → total now 31
4. ✅ **Screener page FinTech revamp** — gradient title, live badge, dark access banner
5. ✅ **Sector Screens section** — 12 GICS sectors with live stock counts
6. ✅ **Color-coded cards** — per investment theme (dividend=amber, growth=blue, etc.)
7. ✅ **PRO vs PREMIUM badges** — correctly differentiated (was always showing PRO)
8. ✅ **Anchor link navigation** — scroll-to-section on hash links
9. ✅ **Example screens empty state** — Value Income, Quality Growth, Deep Value
10. ✅ **Navigation rename** — "Scans" → "Alpha Screens"

### 10.3 Known Technical Notes

| Issue | Detail |
|-------|--------|
| Code divergence | Server edits via Node.js scripts don't auto-sync to git |
| Tailwind bracket notation | `grid-cols-[1fr_280px]` has known rendering issues → use flexbox |
| Mobile sidebar | Browse Sectors hidden on <1024px by design |
| Sector name mismatch | DB uses "Healthcare" / "Technology" vs GICS "Health Care" / "Information Technology" — may affect color theming |
| Deploy script | Pulls from git remote — local changes must be committed first |

---

## Appendix A: Sector Color Mapping

| GICS Sector | DB Name | Color Theme |
|-------------|---------|-------------|
| Communication Services | Communication Services | Blue |
| Consumer Discretionary | Consumer Discretionary | Orange |
| Consumer Staples | Consumer Staples | Green |
| Energy | Energy | Yellow |
| Financials | Financials | Indigo |
| Health Care | Healthcare* | Rose |
| Industrials | Industrials | Slate |
| Information Technology | Technology* | Sky |
| Materials | Materials | Amber |
| Real Estate | Real Estate | Purple |
| Utilities | Utilities | Teal |
| Other | Other | Gray |

*Note: DB sector names may differ from GICS standard names

---

## Appendix B: Card Theme Colors (Alpha Screens)

| Screen Type | BG Color | Border | Icon Color |
|-------------|----------|--------|------------|
| Dividend/Income | `amber-50` | `amber-200` | `amber-600` |
| Value/Quality | `green-50` | `green-200` | `green-600` |
| Growth/Momentum | `blue-50` | `blue-200` | `blue-600` |
| Technical/Trading | `orange-50` | `orange-200` | `orange-600` |
| AI/Premium/Elite | `purple-50` | `purple-200` | `purple-600` |
| Mining | `amber-50` | `amber-200` | `amber-700` |
| REIT/Property | `teal-50` | `teal-200` | `teal-600` |
| Cash Flow/ROIC | `emerald-50` | `emerald-200` | `emerald-600` |
| Risk/Short | `red-50` | `red-200` | `red-500` |
| Small Cap | `indigo-50` | `indigo-200` | `indigo-600` |

---

## Appendix C: Key Code Locations (Server)

| What | File | Line/Section |
|------|------|--------------|
| All 31 presets defined | `/opt/asx-screener/backend/app/api/v1/routes/screener.py` | Line ~1063 (`get_screener_presets()`) |
| Sector stats API | `/opt/asx-screener/backend/app/api/v1/routes/market.py` | `/market/sectors` endpoint |
| Screener main page | `/opt/asx-screener/frontend/app/screener/page.tsx` | Full page component |
| Browse Sectors component | `/opt/asx-screener/frontend/app/screener/components/BrowseSectors.tsx` | Component file |
| Alpha Screens page | `/opt/asx-screener/frontend/app/scans/page.tsx` | Full page component |
| Navigation labels | `/opt/asx-screener/frontend/components/Navbar.tsx` | Nav items array |
| Sector constants | `/opt/asx-screener/frontend/lib/utils.ts` | `SECTORS[]`, `SECTOR_COLORS{}` |
| API hooks | `/opt/asx-screener/frontend/lib/api.ts` | `getMarketSectors()`, `getScreenerPresets()` |

---

*Document: ASX_Screener_Current_State_June2026.md*  
*Version: 1.0 | June 2026 | ASX Screener Production*
