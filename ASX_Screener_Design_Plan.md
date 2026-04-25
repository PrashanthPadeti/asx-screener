# ASX Advanced Stock Screener — Full Design & Architecture Plan

> Version 1.0 | April 2026
> Modelled after screener.in — built for the Australian Securities Exchange (ASX)
> with significant enhancements tailored to Australian investors.

---

## Table of Contents

1. [Project Vision & Goals](#1-project-vision--goals)
2. [Screener.in Feature Audit](#2-screenerin-feature-audit--what-we-replicate)
3. [ASX-Specific Enhancements](#3-asx-specific-enhancements--beyond-screenerin)
4. [Metrics & Ratios Coverage](#4-metrics--ratios-coverage)
5. [Technology Stack](#5-technology-stack)
6. [Data Architecture & Sources](#6-data-architecture--sources)
7. [Database Design](#7-database-design)
8. [Daily Data Pipeline](#8-daily-data-pipeline)
9. [Feature-by-Feature Design](#9-feature-by-feature-design)
10. [Subscription Tiers](#10-subscription-tiers)
11. [Development Roadmap (Phases)](#11-development-roadmap-phases)
12. [Infrastructure & DevOps](#12-infrastructure--devops)
13. [Team Requirements](#13-team-requirements)
14. [Estimated Costs](#14-estimated-costs)

---

## 1. Project Vision & Goals

### Vision
Build the most comprehensive stock screening and fundamental analysis platform for ASX-listed companies — surpassing screener.in in depth, data quality, and investor utility for the Australian market.

### Core Goals
- **Screen** all ASX stocks using SQL-style queries across 200+ fundamental, technical, and custom metrics
- **Automate** daily data ingestion and metric recomputation for current-year figures
- **Provide** deep-dive company pages with 10+ years of historical financials
- **Enable** Australian-specific analysis (franking credits, superannuation benchmarking, ASX announcements, ASIC short-selling data, mining/resources sector depth)
- **Community** — allow users to share, discover, and fork screening queries
- **AI-powered** — intelligent concall summaries, annual report Q&A, earnings insights

### Target Users
- Self-directed retail investors (primary)
- Financial advisers (secondary)
- SMSF trustees (secondary)
- Students & analysts (tertiary)

---

## 2. Screener.in Feature Audit — What We Replicate

| Feature | Screener.in | Our ASX Screener |
|---|---|---|
| SQL-type stock screener | ✅ | ✅ Enhanced |
| Pre-built screens library | ✅ 50,000+ | ✅ Launch with 200+ curated |
| Company detail pages | ✅ | ✅ Enhanced |
| 10-year financial history | ✅ | ✅ |
| P&L / Balance Sheet / Cash Flow | ✅ | ✅ |
| Quarterly results | ✅ | ✅ Half-year + Quarterly Activity |
| Peer comparison | ✅ | ✅ Enhanced |
| Watchlists | ✅ | ✅ |
| Portfolio tracker | ✅ | ✅ Enhanced |
| Shareholding data | ✅ Promoter/FII/DII | ✅ Director/Institutional/Retail |
| Insider trades | ✅ | ✅ |
| Dividend history | ✅ | ✅ + Franking credits |
| Excel export | ✅ | ✅ + Google Sheets |
| Alerts & notifications | ✅ | ✅ Enhanced |
| AI document Q&A | ✅ Screener AI | ✅ ASX AI |
| Concall summaries | ✅ | ✅ AGM + Earnings calls |
| Community screens | ✅ | ✅ |
| Mobile app | ✅ Android only | ✅ iOS + Android |
| Free + Paid tiers | ✅ | ✅ |

---

## 3. ASX-Specific Enhancements — Beyond Screener.in

These are features unique to the Australian market that screener.in does NOT offer:

### 3.1 Franking Credits & Dividend Imputation
- Display **franked vs unfranked** dividend amounts per share
- Calculate **grossed-up dividend yield** (including franking credit value)
- **Effective tax rate comparison** for different investor tax brackets
- **Franking credit account balance** (where disclosed)
- Screen by: `Franking percentage > 80` or `Grossed-up yield > 7`

### 3.2 Mining & Resources Sector Depth
Australia's #1 sector — requires specialised metrics:
- **Ore reserves** (proven + probable) in tonnes/oz/barrels
- **Resources** (measured + indicated + inferred)
- **All-in Sustaining Cost (AISC)** for gold/copper miners
- **Net Asset Value (NAV) per share** — standard for mining valuation
- **Production guidance vs actuals** tracking
- **Quarterly Activity Reports (QARs)** ingestion & display
- **Commodity exposure** mapping (which metals/minerals each company produces)
- **Hedging book** summaries
- Screen by: `AISC < Gold_price * 0.7` or `Reserve_life > 10`

### 3.3 A-REIT (Real Estate Investment Trust) Metrics
- **Funds From Operations (FFO)** per unit
- **Adjusted FFO (AFFO)** per unit
- **Net Tangible Assets (NTA)** per unit — premium/discount to NTA
- **Gearing ratio** (preferred metric over D/E for REITs)
- **Weighted Average Lease Expiry (WALE)**
- **Occupancy Rate**
- **Cap Rate** comparisons
- Screen by: `NTA_discount > 15` or `FFO_yield > 6`

### 3.4 ASIC Short-Selling Data
- Daily **short interest** as % of free float (from ASIC public data)
- **Short interest trend** (increasing/decreasing)
- Short-seller activity alerts
- Screen by: `Short_interest > 10` or `Short_interest_change_1week > 2`

### 3.5 ASX Announcements Intelligence
- Real-time ASX announcement feed per company
- **AI-categorised** announcements: earnings, capital raises, director changes, operational updates, material events
- **Capital raise tracker** — placements, rights issues, entitlement offers, SPPs
  - Discount to last price
  - Dilution % of shares
  - Use of proceeds
- **Director & substantial holder** change alerts (Section 671B / CHESS notices)

### 3.6 Superannuation Benchmarking
- Compare stock/portfolio returns vs **major super fund benchmarks** (Australian Super, ART, Hostplus)
- **Risk-adjusted return** comparison (Sharpe, Sortino)
- **Balanced option** vs ASX All Ords vs individual stocks
- Useful for SMSF trustees evaluating direct equities vs managed funds

### 3.7 ASX Index Membership
- Track membership of: **ASX 20, 50, 100, 200, 300, All Ords, Small Ords, Emerging Companies**
- Filter by index inclusion/exclusion
- **Index rebalancing** alerts
- Screen by: `In_ASX200 = Yes AND Market_Cap > 2000`

### 3.8 Australian Sector & Industry Classification
- Use **GICS** (Global Industry Classification Standard) aligned to ASX
- Australian-specific sub-sector depth for:
  - Banks (Big 4 + regionals + neobanks)
  - Insurance (general + life)
  - Mining (by commodity)
  - REITs (retail/office/industrial/diversified)
  - Healthcare (biotech + medical devices + hospitals)
- **Industry peer comparisons** within ASX context

### 3.9 Capital Structure Intelligence
- **CHESS Holdings** linkage (where available)
- **Escrow expiry** tracker for newly listed companies
- **IPO age** tracking — filter by years since listing
- **Buyback program** tracker — active, completed, announced

### 3.10 ESG & Sustainability Scoring
- Australia-specific ESG ratings (from S&P Global, MSCI, or proprietary)
- **Climate risk** disclosure tracking
- **Net-zero commitments** tracking
- Screen by ESG score or carbon intensity

### 3.11 Advanced Technical Indicators (Beyond Screener.in)
- All indicators screener.in offers PLUS:
  - **ATR** (Average True Range) — volatility measure
  - **Bollinger Bands** position
  - **Stochastic RSI**
  - **OBV** (On-Balance Volume)
  - **VWAP** (Volume Weighted Average Price)
  - **ADX** (Average Directional Index)
  - **Golden Cross / Death Cross** detection
  - **52-week range position** (percentile)

### 3.12 AI Enhancements (Beyond Screener.in's AI)
- **Annual Report AI** — Q&A against full AGLC annual reports
- **Earnings Call AI** — ASX companies' AGM/results call summaries
- **ASX Announcement Parser** — AI reads and categorises all announcements
- **Peer-relative AI** — "How does this company compare to its peers on capital allocation?"
- **Portfolio AI** — holistic portfolio health check with recommendations

---

## 4. Metrics & Ratios Coverage

### Category Summary

| Category | Count | Source Files |
|---|---|---|
| Price & Technical | ~30 | Price Metrics.txt |
| Fundamental Ratios | ~105 | Ratios.txt + User Ratios.txt |
| Annual P&L | ~50 | Annual P&L Metrics.txt |
| Quarterly P&L | ~35 | Quarter P&L.txt |
| Balance Sheet | ~55 | Balance Sheet Metrics.txt |
| Cash Flow | ~25 | CashFlow Metrics.txt |
| CSV (Extended) | ~204 | Financial Ratios CSV |
| ASX-Specific (new) | ~40 | New additions |
| **TOTAL** | **~544** | |

### Metric Groupings for Screener Query Builder

```
GROUP 1: VALUATION
  Market Cap, EV, PE, Forward PE, PB, PS, PCF, PFCF,
  EV/EBITDA, EV/EBIT, EV/Sales, EV/FCF, PEG Ratio,
  Earnings Yield, FCF Yield, Graham Number, NCAVPS,
  Altman Z-Score, Piotroski Score, G-Factor

GROUP 2: PROFITABILITY  
  ROE, ROA, ROCE, ROIC, CROIC, OPM, NPM, GPM,
  EBITDA Margin, EBIT Margin, Asset Turnover,
  Inventory Turnover, Debtor Days, DPO, DSO, CCC,
  Working Capital Days, Earning Power, EVA, NOPAT

GROUP 3: GROWTH
  Sales Growth (1Y/3Y/5Y/7Y/10Y CAGR)
  Profit Growth (1Y/3Y/5Y/7Y/10Y)
  EPS Growth (1Y/3Y/5Y/7Y/10Y)
  EBITDA Growth (3Y/5Y/7Y/10Y)
  FCF Growth (3Y/5Y/7Y/10Y)
  QoQ Sales, QoQ Profits, YoY Quarterly Sales/Profit

GROUP 4: FINANCIAL HEALTH / LEVERAGE
  Debt to Equity, Net Debt/EBITDA, Interest Coverage,
  Current Ratio, Quick Ratio, Cash Ratio,
  Debt Capacity, Financial Leverage,
  Working Capital, Altman Z-Score

GROUP 5: CASH FLOW
  Operating Cash Flow, FCF, Investing CF, Financing CF,
  FCF per Share, OCF/Net Income, Capex/Sales,
  OCF to Debt, OCF to Current Liabilities

GROUP 6: DIVIDENDS & SHAREHOLDER RETURNS
  Dividend Yield, Grossed-up Yield (AUS),
  Franking %, Dividend Payout Ratio,
  Average 5yr Dividend, Share Buyback Yield,
  DRP participation

GROUP 7: TECHNICAL
  RSI (14), MACD, MACD Signal, MACD Histogram,
  DMA 50, DMA 200, Golden/Death Cross,
  Volume (1D/1W/1M avg), ATR, Bollinger Band position,
  52W High/Low, All-Time High/Low,
  Return (1D/1W/1M/3M/6M/1Y/3Y/5Y),
  Beta, Sharpe Ratio, Max Drawdown, Volatility

GROUP 8: SHAREHOLDING
  Director Holdings, Substantial Holders,
  Institutional Ownership, Retail %, Short Interest,
  Change in Holdings (1Q/3Q/1Y)

GROUP 9: ASX-SPECIFIC
  Franking Credits, AISC (miners), NTA (REITs),
  FFO Yield, WALE, Short Interest %, Index Membership,
  Capital Raise History, IPO Age, ASX Sector

GROUP 10: CUSTOM / USER-DEFINED
  User-defined formulas using any of the above metrics
```

---

## 5. Technology Stack

### Frontend
| Component | Technology | Reason |
|---|---|---|
| Framework | **Next.js 14+** (React) | SSR for SEO, fast page loads |
| Language | **TypeScript** | Type safety, maintainability |
| Styling | **TailwindCSS + shadcn/ui** | Rapid UI development |
| Charts | **TradingView Lightweight Charts** | Professional price charts (free) |
| Financial Charts | **Recharts / D3.js** | Bar/line charts for financials |
| Tables | **TanStack Table** | High-performance data tables |
| State | **Zustand** | Simple, performant state management |
| Query Cache | **TanStack Query** | API data caching |
| Forms | **React Hook Form + Zod** | Type-safe form validation |
| Auth | **NextAuth.js** | Social + email auth |
| Realtime | **Socket.io client** | Live price updates |

### Backend
| Component | Technology | Reason |
|---|---|---|
| API Framework | **FastAPI** (Python) | Async, fast, auto-docs, great for finance |
| Task Queue | **Celery + Redis** | Background data processing |
| Auth | **JWT + OAuth2** | Stateless auth |
| Caching | **Redis** | Price data, screen result caching |
| Search | **Elasticsearch** | Full-text stock search, screen execution |
| Screener Engine | **PostgreSQL + pgvector** | SQL query translation & execution |
| Financial Calc | **Pandas + NumPy** | Metric computation |
| AI Integration | **Anthropic Claude API** | Document Q&A, summaries |
| PDF Processing | **PyMuPDF + LangChain** | Annual report parsing |
| WebSockets | **FastAPI WebSockets** | Live price push |

### Data & ML
| Component | Technology |
|---|---|
| Data Pipeline | **Apache Airflow** (orchestration) |
| Data Transform | **dbt** (data build tool) |
| ML Models | **scikit-learn** (Altman Z-score, scoring models) |
| Vector Store | **pgvector** (for AI document search) |

### Database Layer
| Store | Technology | Purpose |
|---|---|---|
| Primary DB | **PostgreSQL 16** | All financial data, users, screens |
| Time-Series | **TimescaleDB** (Postgres extension) | Daily price history |
| Cache | **Redis 7** | Live prices, session data, screen results |
| Search | **Elasticsearch 8** | Stock search, screen execution |
| Object Store | **AWS S3 / Azure Blob** | Annual reports, documents, exports |

---

## 6. Data Architecture & Sources

### 6.1 Primary Data Sources

| Data Type | Source | Cost | Update Freq |
|---|---|---|---|
| EOD Price Data | **Yahoo Finance API** (free) or **ASX Market Data** | Free / ~$5K/yr | Daily |
| Intraday/Live | **Twelve Data** or **Polygon.io** | ~$200/mo | Real-time |
| Financial Statements | **Morningstar Direct API** | ~$10K/yr | Quarterly |
| OR alternative | **Wisesheets / Simplywall.st data** | Cheaper | Quarterly |
| OR alternative | **LSEG Refinitiv** | ~$30K/yr | Quarterly |
| ASX Announcements | **ASX Company Announcements API** | Free | Real-time |
| ASIC Short Data | **ASIC Aggregated Short Sales** | Free | Daily |
| Dividends | **ASX + manual scrape** | Free | As announced |
| Insider Trades | **ASIC substantial holder notices** | Free (scrape) | As filed |
| Index Composition | **ASX Index Factsheets** | Free | Quarterly |
| Sector / Industry | **GICS from data provider** | Included | Quarterly |
| ESG | **S&P Global ESG** or **MSCI** | ~$5K/yr | Annual |

### 6.2 Recommended Data Stack (Cost-optimised for startup)

**Phase 1 (MVP):**
- Yahoo Finance API (free) — EOD prices
- ASX Announcements (free official API)
- ASIC Short Data (free)
- Manual/scraped financial statements from annual reports — for top 200 ASX stocks initially
- **Total data cost: ~$0–500/mo**

**Phase 2 (Growth):**
- Upgrade to **Morningstar**, **Refinitiv**, or **FactSet** for structured financial statements
- Add **Twelve Data** for intraday/live prices
- **Total data cost: ~$2,000–5,000/mo**

**Phase 3 (Scale):**
- Full ASX market data licence
- Real-time streaming prices
- **Total data cost: ~$10,000–30,000/mo**

### 6.3 Data Coverage Scope

- **All ASX-listed companies** (~2,200 stocks)
- Initial focus: **ASX 300** for full fundamental data
- Extended to all ASX for price/technical data
- **10 years historical** financial statements
- **Daily price history** since listing (or 15 years max)

---

## 7. Database Design

### Core Tables (PostgreSQL)

```sql
-- Companies master table
companies (
  id, asx_code, company_name, gics_sector, gics_industry,
  listing_date, ipo_price, shares_outstanding, float_shares,
  financial_year_end, domicile, abn, status, is_asx200,
  is_asx300, is_reit, is_miner, is_bank, updated_at
)

-- Daily price data (TimescaleDB hypertable)
daily_prices (
  date, asx_code, open, high, low, close, volume,
  adjusted_close, vwap, trades_count
)
-- Partitioned by date, indexed by (asx_code, date)

-- Technical indicators (computed daily)
technical_indicators (
  date, asx_code,
  dma_50, dma_200, dma_50_prev, dma_200_prev,
  rsi_14, macd, macd_signal, macd_histogram,
  macd_prev, macd_signal_prev,
  atr_14, bollinger_upper, bollinger_lower, bollinger_mid,
  volume_avg_5d, volume_avg_20d, volume_avg_60d,
  high_52w, low_52w, high_alltime, low_alltime,
  return_1d, return_1w, return_1m, return_3m, return_6m,
  return_1y, return_3y, return_5y,
  beta_1y, sharpe_1y, max_drawdown_1y
)

-- Annual financials (P&L)
annual_pnl (
  asx_code, fiscal_year,
  revenue, gross_profit, operating_profit, ebitda, ebit,
  interest, depreciation, other_income, pbt, tax,
  pat, extraordinary_items, net_profit, dividend,
  material_cost, employee_cost, opm, npm, gpm, eps,
  report_date
)

-- Annual balance sheet
annual_balance_sheet (
  asx_code, fiscal_year,
  equity_capital, preference_capital, reserves,
  secured_loan, unsecured_loan, total_debt,
  gross_block, accumulated_depreciation, net_block,
  cwip, investments, current_assets, current_liabilities,
  working_capital, inventory, trade_receivables,
  trade_payables, cash_equivalents, total_assets,
  contingent_liabilities, book_value_per_share,
  face_value, shares_outstanding
)

-- Annual cash flow
annual_cashflow (
  asx_code, fiscal_year,
  cfo, investing_cf, financing_cf, net_cash_flow,
  capex, fcf, opening_cash, closing_cash
)

-- Half-year/Quarterly financials
periodic_pnl (
  asx_code, period_type, period_end_date,
  revenue, operating_profit, other_income, ebitda,
  ebit, interest, depreciation, pbt, tax,
  pat, extraordinary_items, net_profit,
  eps, equity_capital, opm, npm, gpm,
  report_date
)

-- Computed ratios (updated daily for current year)
daily_ratios (
  date, asx_code,
  -- Valuation
  market_cap, enterprise_value, pe, forward_pe, pb, ps,
  pcf, pfcf, ev_ebitda, ev_ebit, ev_sales, ev_fcf,
  peg_ratio, earnings_yield, fcf_yield,
  graham_number, ncavps, altman_z,
  -- Profitability
  roe, roa, roce, roic, croic,
  opm, npm, gpm, ebitda_margin, ebit_margin,
  asset_turnover, inventory_turnover,
  debtor_days, dpo, dso, ccc, working_capital_days,
  -- Leverage
  debt_to_equity, net_debt_ebitda, interest_coverage,
  current_ratio, quick_ratio, cash_ratio,
  -- Growth (CAGR computed annually, TTM computed daily)
  sales_growth_1y, sales_growth_3y, sales_growth_5y,
  profit_growth_1y, profit_growth_3y, profit_growth_5y,
  eps_growth_1y, eps_growth_3y, eps_growth_5y,
  -- Dividends
  dividend_yield, franking_pct, grossed_up_yield,
  dividend_payout_ratio, avg_dividend_5y,
  -- Scores
  piotroski_score, g_factor, beneish_m
)

-- Dividends
dividends (
  asx_code, ex_date, pay_date, amount_per_share,
  franking_pct, type, currency
)

-- Shareholding
shareholding (
  asx_code, snapshot_date,
  director_total_pct, institutional_pct, retail_pct,
  largest_holder, largest_holder_pct,
  top5_concentration_pct
)

-- Substantial holder notices (from ASIC/ASX)
substantial_holders (
  asx_code, holder_name, notice_date, shares_held,
  percentage, change_type, prev_percentage
)

-- Short interest (daily from ASIC)
short_interest (
  date, asx_code, shares_short, short_pct_float,
  gross_short_sales, reported_short_pct
)

-- ASX Announcements
announcements (
  id, asx_code, announced_at, headline,
  category, subcategory, document_url,
  ai_summary, ai_sentiment, ai_materiality_score,
  is_price_sensitive
)

-- Mining-specific data
mining_data (
  asx_code, report_date,
  commodity_primary, commodity_secondary,
  reserves_proven_kt, reserves_probable_kt,
  resources_measured_kt, resources_indicated_kt,
  resources_inferred_kt, aisc_per_oz, c1_cost,
  production_guidance_low, production_guidance_high,
  reserve_life_years, hedging_pct
)

-- REIT-specific data
reit_data (
  asx_code, report_date,
  ffo_per_unit, affo_per_unit, nta_per_unit,
  price_to_nta, gearing_ratio, wale_years,
  occupancy_pct, portfolio_value, property_count,
  property_type  -- retail/office/industrial/diversified
)

-- User tables
users (id, email, name, plan, created_at, stripe_customer_id)
watchlists (id, user_id, name, is_public)
watchlist_items (watchlist_id, asx_code, added_at, notes)
screens (id, user_id, name, query, is_public, run_count, last_run)
screen_results (screen_id, run_date, asx_codes_json, result_count)
portfolios (id, user_id, name, currency, benchmark)
portfolio_holdings (portfolio_id, asx_code, shares, avg_buy_price, buy_date)
alerts (id, user_id, asx_code, screen_id, condition_type, threshold, active)
user_notes (user_id, asx_code, content, updated_at)
```

---

## 8. Daily Data Pipeline

### Architecture (Apache Airflow DAGs)

```
DAILY PIPELINE (triggers at 5:00 PM AEST — after ASX close at 4:00 PM)

DAG 1: price_ingestion
  4:15 PM  → Fetch EOD prices for all 2,200 ASX stocks
  4:30 PM  → Validate & store in daily_prices (TimescaleDB)
  4:35 PM  → Compute & store technical indicators
             (DMA50, DMA200, RSI, MACD, ATR, Bollinger, Returns)

DAG 2: short_interest (ASIC publishes at ~3:30 PM AEST)
  5:00 PM  → Download ASIC aggregated short-sales CSV
  5:05 PM  → Parse & upsert into short_interest table

DAG 3: announcements_ingestion (continuous during market hours)
  Every 5 min → Poll ASX announcements API
             → Classify with AI (Claude Haiku)
             → Store + trigger alerts for watched companies

DAG 4: ratios_recomputation (most important — runs after price ingestion)
  5:30 PM  → For all stocks: recompute all CURRENT-YEAR metrics
             using latest price + most recent financial statements
             → Update daily_ratios table
             → Invalidate Redis cache for affected stocks
  
  NOTE: Historical year ratios (FY-1, FY-2, etc.) remain unchanged
        Only current-year/TTM metrics are recomputed daily.

DAG 5: quarterly_data (runs on earnings season — Feb, May, Aug, Nov)
  → Parse new half-year / quarterly results from ASX announcements
  → Trigger AI summarisation
  → Recompute all affected ratios

DAG 6: screen_alerts (runs after ratios_recomputation)
  6:30 PM  → Re-run all active user screen alerts
  6:35 PM  → Send email/push notifications for new results

DAG 7: index_composition (runs quarterly — March, June, Sep, Dec)
  → Download ASX index rebalancing announcements
  → Update index membership flags

WEEKLY:
  DAG 8: insider_trades
  → Scrape ASIC substantial holder notice database
  → Parse director trades, substantial holder changes

QUARTERLY:
  DAG 9: financial_statements
  → Ingest new annual/half-year financial statements
  → Recompute historical CAGR metrics (3Y, 5Y, 7Y, 10Y)
  → Update all growth metrics
```

### Current-Year Metrics Recomputed Daily

The following require daily recomputation because they use **current price**:
- Market Cap, Enterprise Value, all PE/PB/PS/PCF ratios
- Dividend Yield, FCF Yield, Earnings Yield, Graham Number
- 52-week position metrics (distance from high/low)
- All return metrics (1D, 1W, 1M, 3M, 6M, 1Y)
- Beta, Sharpe Ratio (rolling)
- DMA ratios (price vs DMA50/DMA200)
- RSI, MACD, ATR (technical indicators)
- Short interest % (uses updated short data)
- Altman Z-Score (uses current market values)
- EV/EBITDA (uses current EV)

---

## 9. Feature-by-Feature Design

### 9.1 Navigation Structure

```
Header:
  Logo | Search Bar (global stock search) | Login/Register
  
Main Nav:
  Feed | Screens | Explore | Tools | Watchlists | [User Menu]

Mobile:
  Bottom tab bar: Home | Screens | Search | Watchlist | Profile
```

### 9.2 Stock Search
- Instant search by **ASX code** or **company name**
- Fuzzy matching (handles typos)
- Results show: logo, code, name, price, change%, market cap
- Filter by: index, sector, size

### 9.3 Screener (Core Feature)

**Query Language:**
```sql
-- Simple example
Market cap > 500 AND
PE < 20 AND
ROE > 15 AND
Debt to equity < 0.5 AND
Dividend yield > 3 AND
Franking percentage > 80 AND
Revenue growth 3Y > 10

-- Advanced example
(Piotroski score >= 7 OR ROCE > 20) AND
FCF yield > 5 AND
Short interest < 5 AND
Market cap BETWEEN 200 AND 5000 AND
In ASX200 = Yes
```

**Supported Functions:**
- Arithmetic: `+, -, *, /`
- Comparison: `>, <, >=, <=, =, !=`
- Range: `BETWEEN x AND y`
- Set: `IN (value1, value2)`
- Logical: `AND, OR, NOT`
- Aggregates: `AVG(field, years)`, `MAX(field, periods)`

**Screen Results Page:**
- Sortable columns (any metric)
- Configurable column sets (save custom column templates)
- Quick chart preview on hover
- Export to CSV / Excel / Google Sheets
- Save query + set alert
- Share screen (public link)

### 9.4 Company Detail Page

```
[Header] ASX Code | Company Name | Sector | Index badges
[Price] Current | Change | Volume | Market Cap | 52W range

[Tab Navigation]
  Overview | P&L | Balance Sheet | Cash Flow | 
  Quarterly | Shareholding | Dividends | Announcements |
  Technical | Mining Data* | REIT Data* | Peers | AI Insights

[Overview Tab]
  - Key ratios card (PE, PB, ROE, ROCE, D/E, Div Yield, OPM)
  - 10-year financial summary chart (revenue, profit, FCF)
  - Price chart (TradingView, interactive)
  - Quick company description (AI-generated)
  - Recent announcements (last 5)
  - Upcoming events (results date, AGM)

[P&L Tab]
  - Annual table: 10 years of Revenue, EBITDA, EBIT, PAT, EPS
  - Growth rates displayed inline (3Y, 5Y CAGR)
  - Half-year breakdowns
  - OPM, NPM trend charts

[Dividends Tab]
  - All historical dividends with franking %
  - Grossed-up yield calculator (input your tax rate)
  - DRP (Dividend Reinvestment Plan) history
  - Dividend growth chart
  - Payout ratio trend

[Announcements Tab]
  - Full ASX announcement history
  - AI-categorised and summarised
  - Filter by category (earnings, capital raise, director, operational)
  - Capital raise history with dilution impact

[Mining Data Tab] (shown only for mining companies)
  - Ore reserves & resources (current + trend)
  - AISC trend
  - Production vs guidance
  - Commodity exposure
  - QAR summaries

[AI Insights Tab]
  - Q&A against annual reports (last 3 years)
  - AGM/earnings call summaries
  - Key risk factors (AI-extracted)
  - Competitive position analysis
  - Bear/bull case arguments
```

### 9.5 Watchlists
- Create multiple named watchlists
- Add notes per stock in watchlist
- Watchlist summary view (all key metrics in one table)
- Share watchlist (public link)
- Watchlist performance dashboard

### 9.6 Portfolio Tracker
- Multiple portfolios (including SMSF portfolio)
- Cost base tracking per parcel (important for CGT)
- **Dividend reinvestment** tracking
- **Franking credit** accumulation tracking
- Performance vs ASX 200 / All Ords benchmark
- Unrealised P&L + after-tax projection
- Export for tax purposes

### 9.7 Alerts System
- **Price alerts** — stock hits price level
- **Screen alerts** — new stocks enter/exit a screen
- **Announcement alerts** — any announcement for watched stock
- **Earnings alerts** — results published
- **Dividend alerts** — ex-dividend date approaching
- **Insider trade alerts** — director buys/sells
- **Short interest alerts** — short interest crosses threshold
- Delivery: Email, Push (mobile app), In-app

### 9.8 Feed (Homepage for logged-in users)
- Customised feed based on watched stocks + sectors
- ASX announcements for watched stocks
- Earnings results summaries (AI)
- Short-seller activity alerts
- Director trades for watched stocks
- Upcoming events (ex-div dates, results dates, AGMs)
- Market overview (sector heatmap, top movers, volume leaders)

### 9.9 Explore (Community Screens)
- Browse popular/featured screens
- Sort by: most used, highest returns, newest
- Categories: Value, Growth, Income, Quality, Momentum, GARP
- ASX-specific: Mining, REIT, Dividend, Franking
- Save/fork any public screen
- User profile pages (public screens per user)

### 9.10 Tools Menu
- **Screener** — the main SQL query tool
- **Comparison** — side-by-side compare 2–5 stocks
- **Stock Selector** — guided questionnaire → recommended screens
- **Dividend Calculator** — grossed-up yield, franking tax benefit
- **DCF Calculator** — interactive discounted cash flow model
- **Altman Z-Score Scanner** — all ASX stocks ranked by bankruptcy risk
- **Piotroski F-Score Scanner** — all ASX stocks scored 0–9
- **Short Interest Tracker** — most shorted ASX stocks
- **Insider Trades Feed** — all recent director/substantial holder trades
- **Capital Raise Tracker** — recent placements, rights issues, SPPs
- **IPO Tracker** — recent and upcoming ASX listings
- **Index Changes** — upcoming/recent ASX index rebalancing
- **Earnings Calendar** — upcoming results dates across ASX
- **Sector Heatmap** — market performance visualisation

---

## 10. Subscription Tiers

### Free — "Investor"
- Screen up to 10 saved queries
- 2 watchlists, up to 50 stocks
- 3 screen alerts
- Standard column set (20 metrics)
- 5-year financial history
- Basic company pages
- 5 AI insights/month
- Community screens (read-only)
- Ads displayed
- **Price: Free**

### Pro — "Active Investor" (recommended)
- Unlimited saved screens
- Unlimited watchlists
- Unlimited alerts (price, screen, announcement)
- 50+ metric columns
- 10-year financial history
- Full company pages incl. mining/REIT data
- 100 AI insights/month
- Export to Excel / CSV (unlimited)
- Portfolio tracker (unlimited portfolios)
- No ads
- **Price: AUD $29/month or $199/year**

### Premium — "Professional"
- Everything in Pro PLUS:
- API access (programmatic queries)
- Excel live-link add-in
- Google Sheets integration
- Bulk export (all ASX data)
- Custom ratio builder (user-defined formulas)
- Priority support
- White-label screener option (on request)
- **Price: AUD $99/month or $799/year**

### Enterprise (custom)
- Institutional data feeds
- Custom metrics
- White-label
- SLA support
- **Price: Custom**

---

## 11. Development Roadmap (Phases)

### Phase 1 — Foundation (Months 1–4)
**Goal: Working MVP with ASX 200 data**

- [ ] Database schema design & setup (PostgreSQL + TimescaleDB)
- [ ] EOD price ingestion pipeline (Yahoo Finance → DB)
- [ ] Technical indicator computation (DMA, RSI, MACD, Returns)
- [ ] Financial statement ingestion for ASX 200 (manual/scrape initially)
- [ ] Core ratio computation engine (50 key ratios)
- [ ] Basic React frontend — stock search + company pages
- [ ] Basic screener (10 pre-built screens, simple query builder)
- [ ] User auth (email + Google)
- [ ] Free + Pro subscription (Stripe)

**Deliverable: Beta for 20 test users**

---

### Phase 2 — Core Feature Parity with Screener.in (Months 5–8)
**Goal: Match screener.in features, ASX-adapted**

- [ ] Full 200+ metric coverage
- [ ] Advanced SQL query builder (full operator set)
- [ ] Watchlists + portfolio tracker
- [ ] Alert system (email)
- [ ] ASX Announcements ingestion + AI categorisation
- [ ] Short interest data (ASIC)
- [ ] Dividend + franking credit data
- [ ] Community screens (public sharing)
- [ ] 10-year financial history for ASX 300
- [ ] Mobile-responsive UI
- [ ] Excel/CSV export

**Deliverable: Public launch v1.0**

---

### Phase 3 — ASX Differentiation (Months 9–14)
**Goal: Surpass screener.in with ASX-unique features**

- [ ] Mining sector metrics (AISC, reserves, QAR ingestion)
- [ ] REIT sector metrics (FFO, NTA, WALE, occupancy)
- [ ] AI insights — annual report Q&A (Claude API)
- [ ] AGM/earnings call AI summaries
- [ ] Capital raise tracker
- [ ] Insider trades feed
- [ ] Franking credit calculator
- [ ] Superannuation benchmarking
- [ ] Native mobile apps (iOS + Android — React Native)
- [ ] Push notifications

**Deliverable: Market-leading ASX platform**

---

### Phase 4 — Scale & Monetisation (Months 15–24)
**Goal: 10,000 paying users, API, institutional**

- [ ] API access (REST + WebSocket)
- [ ] Google Sheets live integration
- [ ] Excel live-link add-in
- [ ] Premium data upgrade (Morningstar/Refinitiv)
- [ ] Real-time / intraday prices
- [ ] ESG scoring integration
- [ ] Quantitative screener (backtesting screens)
- [ ] DCF model builder (interactive)
- [ ] Custom ratio builder (user-defined formulas)
- [ ] White-label offering for advisers
- [ ] Institutional tier launch

---

## 12. Infrastructure & DevOps

### Cloud Architecture (AWS)

```
Route 53 (DNS)
    ↓
CloudFront CDN (static assets, caching)
    ↓
Application Load Balancer
    ├── Next.js Frontend (ECS Fargate, auto-scaling)
    └── FastAPI Backend (ECS Fargate, auto-scaling)
            ↓
        ElastiCache Redis (caching layer)
            ↓
        RDS PostgreSQL + TimescaleDB (Multi-AZ)
            ↓
        Elasticsearch (OpenSearch Service)

Separate:
    Airflow (MWAA managed) — data pipelines
    SQS + Lambda — async processing
    S3 — document storage (annual reports)
    SES — email delivery
    SNS — push notifications
```

### CI/CD
- GitHub Actions for CI
- ArgoCD for Kubernetes deployment
- Docker containers throughout
- Staging + Production environments
- Automated testing (unit + integration)

### Monitoring
- **Datadog** — APM, logs, dashboards
- **PagerDuty** — on-call alerts for data pipeline failures
- **Sentry** — frontend error tracking

---

## 13. Team Requirements

### Phase 1 MVP Team (Minimum)
| Role | Count | Notes |
|---|---|---|
| Full-Stack Developer | 1–2 | Next.js + FastAPI |
| Data Engineer | 1 | Airflow pipelines, DB design |
| Financial Data Analyst | 1 | Ratio formulas, data validation |
| Designer (UX/UI) | 1 (part-time) | Figma designs |
| DevOps | 1 (part-time) | AWS setup |

### Phase 2 Scale Team
Add: Backend specialist, Mobile developer, AI/ML engineer, Customer support

---

## 14. Estimated Costs

### Monthly Operating Costs (Phase 1 — MVP)

| Item | Monthly Cost (AUD) |
|---|---|
| AWS (RDS, ECS, ElastiCache, S3) | $300–600 |
| Yahoo Finance API | Free |
| Claude API (AI features) | $50–200 |
| Stripe (payment processing) | 1.75% + $0.30/transaction |
| Sendgrid (email) | $20 |
| Domain + SSL | $5 |
| Datadog / monitoring | $50 |
| **Total Phase 1** | **~$500–1,000/mo** |

### Monthly Operating Costs (Phase 3 — Growth)

| Item | Monthly Cost (AUD) |
|---|---|
| AWS (scaled up) | $2,000–5,000 |
| Financial data (Morningstar/Refinitiv) | $2,000–5,000 |
| Twelve Data (intraday prices) | $300 |
| Claude API (AI features) | $500–1,000 |
| ESG data | $500 |
| Support tools | $200 |
| **Total Phase 3** | **~$6,000–12,000/mo** |

### Revenue Targets
- **Break-even**: ~400 Pro subscribers ($29/mo = ~$12K MRR)
- **Sustainable**: ~1,000 Pro + 100 Premium = ~$39K MRR
- **Comparable to Screener.in**: They reached profitability at ~50,000 users (mostly free) with ~5% paying

---

## Key Differentiators Summary

| Area | Screener.in | Our ASX Screener |
|---|---|---|
| Market | India (NSE/BSE) | Australia (ASX) |
| Franking credits | ❌ | ✅ Full imputation system |
| Mining sector depth | ❌ | ✅ AISC, reserves, QAR |
| REIT metrics | ❌ | ✅ FFO, NTA, WALE |
| ASIC short data | ❌ | ✅ Daily short interest |
| ASX announcements AI | ❌ | ✅ Real-time + AI-parsed |
| Capital raise tracker | ❌ | ✅ |
| SMSF tools | ❌ | ✅ |
| ESG scoring | ❌ | ✅ |
| Backtesting | ❌ | ✅ (Phase 4) |
| API access | ❌ (free) | ✅ Premium |
| Mobile apps | Android only | ✅ iOS + Android |
| Real-time data | EOD only | ✅ Intraday (Pro) |

---

*End of Design Plan v1.0*
*Next step: Review and approve this plan, then begin Phase 1 database schema implementation.*
