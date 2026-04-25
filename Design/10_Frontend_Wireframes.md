# Document 10 — Frontend Wireframes
# ASX Screener Platform — UI/UX Design
# All Major Pages · ASCII Wireframes · Next.js 14 / React

---

## Table of Contents

1. [Design System & Navigation Shell](#1-design-system--navigation-shell)
2. [Home / Dashboard Feed](#2-home--dashboard-feed)
3. [Stock Screener — Query Builder](#3-stock-screener--query-builder)
4. [Screener Results Page](#4-screener-results-page)
5. [Company Detail Page](#5-company-detail-page)
   - 5a. Overview Tab
   - 5b. Financials Tab
   - 5c. Technicals Tab
   - 5d. Peers Tab
   - 5e. AI Insights Tab
6. [Watchlist Manager](#6-watchlist-manager)
7. [Portfolio Tracker](#7-portfolio-tracker)
8. [Alerts Manager](#8-alerts-manager)
9. [Community Screens Explorer](#9-community-screens-explorer)
10. [Search (Global)](#10-search-global)
11. [Authentication Pages](#11-authentication-pages)
12. [Account & Settings](#12-account--settings)
13. [Mobile Responsive Breakpoints](#13-mobile-responsive-breakpoints)
14. [Component Library Summary](#14-component-library-summary)
15. [Next.js Route Map](#15-nextjs-route-map)

---

## 1. Design System & Navigation Shell

### Color Palette

```
PRIMARY      #0F4C81   ASX Blue (Navy)
ACCENT       #00A86B   Growth Green
DANGER       #E53E3E   Loss Red / Alert
WARNING      #F6AD55   Orange (caution metrics)
SURFACE      #0D1117   Page background (dark default)
CARD         #161B22   Card background
BORDER       #30363D   Subtle border
TEXT_PRIMARY #E6EDF3   Primary text
TEXT_MUTED   #8B949E   Secondary text
TEXT_LINK    #58A6FF   Link / interactive
GOLD         #FFD700   Franking credit highlight
```

### Typography

```
Font Family:   Inter (UI) + JetBrains Mono (numbers/code)
Heading H1:    24px / Bold
Heading H2:    20px / SemiBold
Heading H3:    16px / SemiBold
Body:          14px / Regular
Caption:       12px / Regular
Numbers:       JetBrains Mono 14px (all financial data)
```

---

### Global Navigation Shell (Desktop — 1280px+)

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  TOPBAR                                                                         │
│ ┌─────────────────────────────────────────────────────────────────────────────┐ │
│ │ [🦘 ASXScreener]  [Search stocks, metrics, screens...        🔍]  [Login] [▶]│ │
│ │                   ← 480px search bar →                      [Sign Up Free]   │ │
│ └─────────────────────────────────────────────────────────────────────────────┘ │
│  NAVBAR (sticky)                                                                 │
│ ┌─────────────────────────────────────────────────────────────────────────────┐ │
│ │  Feed   Screener   Tools ▾   Watchlists   Portfolio   Community   Alerts    │ │
│ │  ───                                                               🔔 (3)   │ │
│ └─────────────────────────────────────────────────────────────────────────────┘ │
│  MARKET TICKER (scrolling)                                                       │
│ ┌─────────────────────────────────────────────────────────────────────────────┐ │
│ │ XJO ▲ 7,842.3 +0.42%  BHP ▲ $45.20 +1.2%  CBA ▼ $118.40 -0.3%  →→→      │ │
│ └─────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                  │
│  [PAGE CONTENT AREA — changes per route]                                         │
│                                                                                  │
│  FOOTER                                                                          │
│ ┌─────────────────────────────────────────────────────────────────────────────┐ │
│ │  © 2026 ASXScreener Pty Ltd  |  ABN 12 345 678 901  |  Privacy  |  Terms   │ │
│ │  Data: ASX, Yahoo Finance, ASIC  |  Not financial advice                    │ │
│ └─────────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Tools Dropdown Menu

```
             ┌─────────────────────────┐
Tools ▾ ───► │  📊  Ratio Explorer      │
             │  📈  Charting Studio     │
             │  🧮  Formula Builder     │
             │  🏆  Piotroski Scanner   │
             │  💰  Franking Calculator │
             │  🏗️  Capital Raise Tracker│
             │  📋  ASIC Short Monitor  │
             │  🤖  AI Analyst          │
             └─────────────────────────┘
```

---

## 2. Home / Dashboard Feed

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  FEED PAGE                                                                       │
│                                                                                  │
│  ┌─── LEFT SIDEBAR (260px) ──────────┐  ┌─── MAIN FEED (flex) ───────────────┐  │
│  │                                    │  │                                     │  │
│  │  MARKET OVERVIEW                   │  │  ┌─── TODAY'S HIGHLIGHTS ────────┐  │  │
│  │  ┌────────────────────────────┐    │  │  │  Monday 20 April 2026          │  │  │
│  │  │ S&P/ASX 200   7,842  ▲0.4% │    │  │  │                                │  │  │
│  │  │ S&P/ASX 300   7,621  ▲0.3% │    │  │  │  📈 52 Stocks hit 52W High     │  │  │
│  │  │ All Ords      8,012  ▲0.5% │    │  │  │  📉 18 Stocks hit 52W Low      │  │  │
│  │  │ Small Ords    3,201  ▼0.1% │    │  │  │  💰 8 Dividend Ex-Dates Today  │  │  │
│  │  └────────────────────────────┘    │  │  │  🏗️  3 Capital Raises Active    │  │  │
│  │                                    │  │  │  📋  ASIC Short ↑ on 12 stocks │  │  │
│  │  SECTORS TODAY                     │  │  └────────────────────────────────┘  │  │
│  │  ┌────────────────────────────┐    │  │                                     │  │
│  │  │ ██ Materials     +1.8%     │    │  │  ┌─── TRENDING SCREENS ───────────┐  │  │
│  │  │ ██ Financials    +0.5%     │    │  │  │  🔥 "ASX Value Traps" — 847 runs│  │  │
│  │  │ ██ Energy        +0.3%     │    │  │  │  🔥 "High Franking + Growth"    │  │  │
│  │  │ ░░ Tech          -0.2%     │    │  │  │  🔥 "Piotroski Score ≥ 8"       │  │  │
│  │  │ ░░ Healthcare    -0.8%     │    │  │  │  🔥 "Miners: AISC < Gold Price" │  │  │
│  │  │ ██ REITs         +1.1%     │    │  │  │  [Browse All Community Screens] │  │  │
│  │  └────────────────────────────┘    │  │  └────────────────────────────────┘  │  │
│  │                                    │  │                                     │  │
│  │  QUICK LINKS                       │  │  ┌─── ANNOUNCEMENTS FEED ─────────┐  │  │
│  │  ┌────────────────────────────┐    │  │  │  [All] [Results] [Dividends]    │  │  │
│  │  │ 📌 My Watchlist (12)       │    │  │  │       [Capital Raises] [Other]  │  │  │
│  │  │ 📌 My Saved Screens (5)    │    │  │  │                                 │  │  │
│  │  │ 📌 Active Alerts (3)       │    │  │  │  ┌─────────────────────────┐   │  │  │
│  │  └────────────────────────────┘    │  │  │  │ CBA  09:32  📊 Half Year │   │  │  │
│  │                                    │  │  │  │ Revenue $27.8B ▲4.2%    │   │  │  │
│  │  TOP MOVERS (ASX200)               │  │  │  │ NPAT $5.1B ▲2.8%        │   │  │  │
│  │  ┌────────────────────────────┐    │  │  │  │ DPS 225¢ (70% franked)   │   │  │  │
│  │  │ GAINERS         LOSERS     │    │  │  │  │ [View Announcement] [AI] │   │  │  │
│  │  │ GOR  +12.4%    SOM  -8.2% │    │  │  │  └─────────────────────────┘   │  │  │
│  │  │ RIO  +4.1%     GXY  -5.1% │    │  │  │                                 │  │  │
│  │  │ WDS  +3.8%     PLS  -4.9% │    │  │  │  ┌─────────────────────────┐   │  │  │
│  │  │ NEM  +3.2%     LYC  -3.7% │    │  │  │  │ BHP  08:15  💰 Dividend │   │  │  │
│  │  │ WBC  +2.9%     QAN  -3.2% │    │  │  │  │ Int. Div 87¢ AUD        │   │  │  │
│  │  └────────────────────────────┘    │  │  │  │ Franking: 100% (124.3¢) │   │  │  │
│  │                                    │  │  │  │ Ex-Date: 28 Apr 2026    │   │  │  │
│  │  MOST SHORTED (ASIC)              │  │  │  │ [Add to Calendar]       │   │  │  │
│  │  ┌────────────────────────────┐    │  │  │  └─────────────────────────┘   │  │  │
│  │  │ GXY   18.4% short          │    │  │  │                                 │  │  │
│  │  │ LYC   14.2% short          │    │  │  │  ┌─────────────────────────┐   │  │  │
│  │  │ PLS   13.8% short ▲ (new)  │    │  │  │  │ ZIP  07:45  🏗️ Cap Raise │   │  │  │
│  │  │ NIC   11.2% short          │    │  │  │  │ $150M Placement @ $2.10 │   │  │  │
│  │  └────────────────────────────┘    │  │  │  │ 7.5% disc. to last close│   │  │  │
│  │                                    │  │  │  │ [View Details]          │   │  │  │
│  └────────────────────────────────────┘  │  │  └─────────────────────────┘   │  │  │
│                                          │  │  [Load More Announcements ↓]    │  │  │
│                                          │  └─────────────────────────────────┘  │  │
│                                          │                                     │  │
│                                          │  ┌─── MY WATCHLIST SNAPSHOT ──────┐  │  │
│                                          │  │  [Only shown when logged in]    │  │  │
│                                          │  │                                 │  │  │
│                                          │  │  Ticker  Price   Day%   52W%    │  │  │
│                                          │  │  BHP    $45.20  +1.2%  +22.4%  │  │  │
│                                          │  │  CBA   $118.40  -0.3%  +14.1%  │  │  │
│                                          │  │  WDS    $28.70  +3.8%  -12.3%  │  │  │
│                                          │  │  [Manage Watchlist →]           │  │  │
│                                          │  └─────────────────────────────────┘  │  │
│                                          └─────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Stock Screener — Query Builder

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  SCREENER  /screener                                                             │
│                                                                                  │
│  ┌─── QUERY BUILDER ──────────────────────────────────────────────────────────┐  │
│  │                                                                              │  │
│  │  [📋 My Screens ▾]  [🌐 Community ▾]  [📤 Share]  [💾 Save Screen]         │  │
│  │                                                                              │  │
│  │  ┌─── FILTER MODE TOGGLE ─────────────────────────────────────────────┐    │  │
│  │  │  ● Visual Builder    ○ SQL Mode    ○ Natural Language (AI)  [PRO]   │    │  │
│  │  └────────────────────────────────────────────────────────────────────┘    │  │
│  │                                                                              │  │
│  │  ══════════ VISUAL FILTER BUILDER ══════════                                │  │
│  │                                                                              │  │
│  │  ┌─── FILTER ROW 1 ──────────────────────────────────────────────────┐    │  │
│  │  │ [Metric ▾          ] [Operator ▾] [Value      ] [AND/OR] [+ Add] [×]│    │  │
│  │  │  Market Cap (Cr.)     ≥            500                               │    │  │
│  │  └────────────────────────────────────────────────────────────────────┘    │  │
│  │                                                                              │  │
│  │  ┌─── FILTER ROW 2 ──────────────────────────────────────────────────┐    │  │
│  │  │ [Metric ▾          ] [Operator ▾] [Value      ] [AND/OR] [+ Add] [×]│    │  │
│  │  │  PE Ratio             ≤            20                                │    │  │
│  │  └────────────────────────────────────────────────────────────────────┘    │  │
│  │                                                                              │  │
│  │  ┌─── FILTER ROW 3 ──────────────────────────────────────────────────┐    │  │
│  │  │ [Metric ▾          ] [Operator ▾] [Value      ] [AND/OR] [+ Add] [×]│    │  │
│  │  │  Dividend Yield (%)   ≥            3.5                               │    │  │
│  │  └────────────────────────────────────────────────────────────────────┘    │  │
│  │                                                                              │  │
│  │  ┌─── FILTER ROW 4 ──────────────────────────────────────────────────┐    │  │
│  │  │ [Metric ▾          ] [Operator ▾] [Value      ] [AND/OR] [+ Add] [×]│    │  │
│  │  │  Franking %           =            100                               │    │  │
│  │  └────────────────────────────────────────────────────────────────────┘    │  │
│  │                                                                              │  │
│  │  [+ Add Filter]  [+ Add Filter Group]  [Clear All]                          │  │
│  │                                                                              │  │
│  │  ┌─── METRIC PICKER (shown when clicking Metric dropdown) ────────────┐    │  │
│  │  │  🔍 Search metrics...                                               │    │  │
│  │  │  ─────────────────────────────────────────────────────────         │    │  │
│  │  │  VALUATION         PROFITABILITY       GROWTH                       │    │  │
│  │  │  ○ PE Ratio        ○ ROE               ○ Revenue Growth 1Y          │    │  │
│  │  │  ○ PB Ratio        ○ ROA               ○ EPS Growth 1Y              │    │  │
│  │  │  ○ PS Ratio        ○ ROCE              ○ Revenue CAGR 5Y            │    │  │
│  │  │  ○ EV/EBITDA       ○ ROIC              ○ Profit CAGR 5Y             │    │  │
│  │  │  ○ EV/Revenue      ○ Net Margin        ○ Dividend Growth 3Y         │    │  │
│  │  │  ○ Dividend Yield  ○ Gross Margin      ─────────────────────────    │    │  │
│  │  │  ○ Grossed-Up Yld  ○ EBITDA Margin     ASX SPECIFIC 🦘              │    │  │
│  │  │  ─────────────────────────────────────────────────────             │    │  │
│  │  │  TECHNICAL         FINANCIAL HEALTH    ○ Franking %                 │    │  │
│  │  │  ○ RSI (14)        ○ Debt/Equity       ○ Grossed-Up Yield           │    │  │
│  │  │  ○ 52W High %      ○ Interest Cover    ○ AISC (miners)  ⛏️          │    │  │
│  │  │  ○ EMA 200         ○ Current Ratio     ○ FFO Yield (REITs) 🏢       │    │  │
│  │  │  ○ MACD Signal     ○ Quick Ratio       ○ NTA Discount/Prem          │    │  │
│  │  │  ○ ATR %           ○ Altman Z-Score    ○ ASIC Short %               │    │  │
│  │  │  ○ Beta            ○ Piotroski Score   ○ Index (ASX200/300)         │    │  │
│  │  └─────────────────────────────────────────────────────────────────────┘    │  │
│  │                                                                              │  │
│  └──────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                  │
│  ┌─── UNIVERSE FILTERS ────────────────────────────────────────────────────┐    │
│  │                                                                           │    │
│  │  INDEX:    [All ▾] [ASX20] [ASX50] [ASX100] [ASX200] [ASX300] [Small]   │    │
│  │  SECTOR:   [All ▾] [Materials] [Financials] [Energy] [Tech] [REITs] ...  │    │
│  │  TYPE:     [All ▾] [Miners ⛏️] [REITs 🏢] [Banks 🏦] [LICs] [ETFs]     │    │
│  │  MKTCAP:   [○ All  ○ Nano <$10M  ○ Micro <$100M  ○ Small  ○ Mid  ○ Lg]  │    │
│  │  EXCHANGE: [● ASX  ○ NSX  ○ Chi-X]                                       │    │
│  │                                                                           │    │
│  └───────────────────────────────────────────────────────────────────────────┘    │
│                                                                                  │
│  ┌─── SQL MODE (when toggled) ────────────────────────────────────────────┐    │
│  │  -- Write your screen in SQL-like syntax                                 │    │
│  │  SELECT ticker, company_name, market_cap, pe_ratio,                      │    │
│  │         dividend_yield, franking_pct, grossed_up_yield                   │    │
│  │  FROM   asx_screener                                                      │    │
│  │  WHERE  market_cap >= 500                                                 │    │
│  │    AND  pe_ratio <= 20                                                    │    │
│  │    AND  dividend_yield >= 3.5                                             │    │
│  │    AND  franking_pct = 100                                                │    │
│  │  ORDER BY grossed_up_yield DESC                                           │    │
│  │  LIMIT 100                                                                │    │
│  │                                                           [▶ Run Screen]  │    │
│  └─────────────────────────────────────────────────────────────────────────┘    │
│                                                                                  │
│  ┌─── AI NATURAL LANGUAGE MODE [PRO] ──────────────────────────────────────┐    │
│  │  🤖 Describe what you're looking for in plain English:                    │    │
│  │  ┌───────────────────────────────────────────────────────────────┐       │    │
│  │  │ "ASX200 companies with strong dividends, fully franked, low   │       │    │
│  │  │  debt, and consistent profit growth over 5 years"             │       │    │
│  │  └───────────────────────────────────────────────────────────────┘       │    │
│  │  [🤖 Generate Filters]   ← Claude Haiku converts to filter rows           │    │
│  └─────────────────────────────────────────────────────────────────────────┘    │
│                                                                                  │
│  ┌─── SORT & COLUMNS ──────────────────────────────────────────────────────┐    │
│  │  Sort by: [Grossed-Up Yield ▾] [↓ Desc]                                  │    │
│  │  Columns: [+ Add Column]  PE  PB  DivYield  FrankingPct  ROE  DebtEq   │    │
│  │           [Grossed-Up Yield ×] [Market Cap ×] [52W Chg ×]               │    │
│  └─────────────────────────────────────────────────────────────────────────┘    │
│                                                                                  │
│  [▶ RUN SCREEN — 2,200 stocks]          Last run: 20 Apr 2026, 6:31 PM AEST     │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Screener Results Page

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  SCREENER RESULTS                                                                │
│                                                                                  │
│  ┌─── RESULT SUMMARY BAR ────────────────────────────────────────────────────┐  │
│  │  ✅ 47 stocks match your screen  (from 2,200 ASX stocks)                   │  │
│  │  Data as of: 20 Apr 2026, 4:00 PM AEST                                     │  │
│  │  [📤 Export CSV] [💾 Save Screen] [📤 Share Link] [🔔 Set Alert on Screen]  │  │
│  └────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                  │
│  ┌─── QUICK FILTER CHIPS ────────────────────────────────────────────────────┐  │
│  │  Market Cap ≥ 500Cr ×  |  PE ≤ 20 ×  |  Div ≥ 3.5% ×  |  100% Franked × │  │
│  │  [+ Add Filter]                                                             │  │
│  └────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                  │
│  ┌─── RESULTS TABLE ──────────────────────────────────────────────────────────┐  │
│  │                                                                              │  │
│  │  [☐] Ticker  Company              Sector      MktCap  PE    DivYld  G-Up   │  │
│  │             Name                             ($M)         %      Yld%  ▲▼  │  │
│  │  ─────────────────────────────────────────────────────────────────────────  │  │
│  │  [☐] WBC   Westpac Banking       Financials  92,410  11.2   6.8%  9.71%   │  │
│  │  [☐] ANZ   ANZ Group Holdings    Financials  84,210  10.8   6.5%  9.29%   │  │
│  │  [☐] NAB   National Aust. Bank   Financials  99,340  12.1   6.2%  8.86%   │  │
│  │  [☐] BEN   Bendigo & Adelaide    Financials  5,210   9.8    6.0%  8.57%   │  │
│  │  [☐] NHF   nib Holdings          Healthcare  2,840   16.2   5.8%  8.29%   │  │
│  │  [☐] SOL   Washington H Soul P   Industrials 6,120   14.1   5.5%  7.86%   │  │
│  │  [☐] BHP   BHP Group             Materials   218,400 12.4   5.2%  7.43%   │  │
│  │  [☐] RIO   Rio Tinto             Materials   192,310 10.2   5.0%  7.14%   │  │
│  │  ...                                                                        │  │
│  │  ─────────────────────────────────────────────────────────────────────────  │  │
│  │  Showing 1–25 of 47  [← Prev]  [1] [2]  [Next →]                          │  │
│  │                                                                              │  │
│  │  COLUMN HEADERS: click to sort ▲▼ | drag to reorder | right-click to hide  │  │
│  │                                                                              │  │
│  └──────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                  │
│  ┌─── OPTIONAL: CHART VIEW TOGGLE ──────────────────────────────────────────┐  │
│  │  [≡ Table View] [▦ Card View] [📊 Scatter Plot]                           │  │
│  │                                                                             │  │
│  │  SCATTER PLOT (PE Ratio vs Grossed-Up Yield):                              │  │
│  │  10% ┤                   ●WBC                                              │  │
│  │   9% ┤            ●ANZ ●NAB                                                │  │
│  │   8% ┤      ●BEN                                                           │  │
│  │   7% ┤                                 ●BHP                                │  │
│  │   6% ┤                                                                     │  │
│  │      └──────────────────────────────────────────                           │  │
│  │       8x      10x      12x      14x      16x      PE Ratio                 │  │
│  └─────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                  │
│  ┌─── BULK ACTIONS (shown when ≥1 row selected) ─────────────────────────────┐  │
│  │  ☑ 3 selected:  [+ Add to Watchlist ▾]  [Set Bulk Alert]  [Compare]       │  │
│  └────────────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. Company Detail Page

### Route: `/stocks/[ticker]`

---

### 5a. Overview Tab

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  BHP GROUP LIMITED  (BHP)  ·  ASX200 · S&P/ASX 50  ·  Materials                │
│                                                                                  │
│  ┌─── PRICE HERO ────────────────────────────────────────────────────────────┐  │
│  │                                                                              │  │
│  │  $45.20  ▲ $0.54 (+1.22%)  ·  Today  ·  AEST 4:00 PM                      │  │
│  │                                                                              │  │
│  │  [1D] [1W] [1M] [3M] [YTD] [1Y] [3Y] [5Y] [10Y] [MAX]  [📊 vs XJO]        │  │
│  │                                                                              │  │
│  │  ▲$50                                                                       │  │
│  │  ────── ╭──╮╭──╮                                                            │  │
│  │         │  ││  │╭──╮  ╭──╮                     BHP ─────                   │  │
│  │  ──────╯    ╰╯  ╰╯  │  │╭╯╭──╮  ╭────╮  ╭──── XJO ·····                  │  │
│  │                       ╰──╯ ╰╯  ╰──╯    ╰╯                                  │  │
│  │  ▼$35                                                                       │  │
│  │  Jan 26                Apr 26                         ▲ $45.20              │  │
│  │  ────────────────── Volume (millions) ─────────────────────────────         │  │
│  │  ███████ ████ ██ █████ ████ ████████ ███ ██████ █████ ████████████         │  │
│  │                                                                              │  │
│  └──────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                  │
│  ┌─── TAB BAR ───────────────────────────────────────────────────────────────┐  │
│  │  [Overview ●] [Financials] [Technicals] [Peers] [AI Insights 🤖] [News]   │  │
│  └────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                  │
│  ┌─── LEFT COLUMN (60%) ──────────────┐  ┌─── RIGHT COLUMN (40%) ──────────┐  │
│  │                                     │  │                                   │  │
│  │  KEY METRICS                         │  │  QUICK ACTIONS                   │  │
│  │  ┌─────────────────────────────┐    │  │  ┌─────────────────────────┐    │  │
│  │  │  Market Cap    $218.4B      │    │  │  │ [+ Add to Watchlist]    │    │  │
│  │  │  Enterprise V  $231.2B      │    │  │  │ [🔔 Set Alert]          │    │  │
│  │  │  52W High      $52.30       │    │  │  │ [📊 Add to Portfolio]   │    │  │
│  │  │  52W Low       $36.80       │    │  │  └─────────────────────────┘    │  │
│  │  │  Avg Vol (3M)  18.2M        │    │  │                                   │  │
│  │  │  Beta          0.82         │    │  │  DIVIDEND SNAPSHOT               │  │
│  │  └─────────────────────────────┘    │  │  ┌─────────────────────────┐    │  │
│  │                                     │  │  │ Div Yield      5.2%     │    │  │
│  │  VALUATION METRICS                  │  │  │ 💛 Grossed-Up  7.43%    │    │  │
│  │  ┌─────────────────────────────┐    │  │  │ Franking       100%     │    │  │
│  │  │  PE (TTM)       12.4x       │    │  │  │ Last DPS       $1.18    │    │  │
│  │  │  PB Ratio        1.8x       │    │  │  │ Frequency      Semi-Ann │    │  │
│  │  │  PS Ratio        1.9x       │    │  │  │ Ex-Date        28 Apr   │    │  │
│  │  │  EV/EBITDA       7.2x       │    │  │  │ Pay-Date       15 May   │    │  │
│  │  │  EV/EBIT         9.8x       │    │  │  │ Payout Ratio   64.2%    │    │  │
│  │  │  Graham Num    $48.30       │    │  │  └─────────────────────────┘    │  │
│  │  │  NCAVPS        -$3.10       │    │  │                                   │  │
│  │  └─────────────────────────────┘    │  │  ASX SPECIFIC (MINING) ⛏️        │  │
│  │                                     │  │  ┌─────────────────────────┐    │  │
│  │  PROFITABILITY                      │  │  │ AISC (FY26)   $1,847/oz │    │  │
│  │  ┌─────────────────────────────┐    │  │  │ Gold Price    $3,210/oz │    │  │
│  │  │  ROE            18.4%       │    │  │  │ AISC Margin   $1,363/oz │    │  │
│  │  │  ROA             8.2%       │    │  │  │ Production    247M t    │    │  │
│  │  │  ROCE           14.1%       │    │  │  │ Reserves      8.2B t    │    │  │
│  │  │  ROIC           11.8%       │    │  │  │ Reserve Life  33 yrs    │    │  │
│  │  │  Net Margin     15.3%       │    │  │  └─────────────────────────┘    │  │
│  │  │  EBITDA Margin  32.1%       │    │  │                                   │  │
│  │  │  Gross Margin   41.8%       │    │  │  QUALITY SCORES                  │  │
│  │  └─────────────────────────────┘    │  │  ┌─────────────────────────┐    │  │
│  │                                     │  │  │ Piotroski   7/9  🟢     │    │  │
│  │  GROWTH (YoY)                       │  │  │ Altman Z    3.4  🟢     │    │  │
│  │  ┌─────────────────────────────┐    │  │  │ Beneish M  -2.8  🟢     │    │  │
│  │  │  Revenue        +4.2%       │    │  │  │ Sharpe (1Y) 0.82        │    │  │
│  │  │  EBITDA         +6.8%       │    │  │  │ Max Drawdn -22.4%       │    │  │
│  │  │  Net Profit     +2.1%       │    │  │  └─────────────────────────┘    │  │
│  │  │  EPS            +3.4%       │    │  │                                   │  │
│  │  │  Revenue CAGR5Y +3.8%       │    │  │  SHORT INTEREST (ASIC)           │  │
│  │  │  Div CAGR 3Y    +5.2%       │    │  │  ┌─────────────────────────┐    │  │
│  │  └─────────────────────────────┘    │  │  │ Short % Float   2.1%    │    │  │
│  │                                     │  │  │ Trend         → Stable  │    │  │
│  │  CAPITAL RAISE HISTORY              │  │  │ vs Sector     Below avg │    │  │
│  │  ┌─────────────────────────────┐    │  │  └─────────────────────────┘    │  │
│  │  │ No recent capital raises    │    │  │                                   │  │
│  │  └─────────────────────────────┘    │  │  ANALYST CONSENSUS [PRO]         │  │
│  │                                     │  │  ┌─────────────────────────┐    │  │
│  └─────────────────────────────────────┘  │  │ 🔒 Upgrade to Pro       │    │  │
│                                           │  └─────────────────────────┘    │  │
│                                           └──────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

### 5b. Financials Tab

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  BHP  FINANCIALS                                                                 │
│                                                                                  │
│  [P&L] [Balance Sheet] [Cash Flow] [Ratios] [Segments]                          │
│                                                                                  │
│  Period: [Annual ●] [Half-Year]   Show: [5 Years ●] [10 Years] [All]            │
│  Currency: [AUD ●] [USD]                                                         │
│                                                                                  │
│  ┌─── PROFIT & LOSS ($M AUD) ─────────────────────────────────────────────────┐  │
│  │                                                                               │  │
│  │  Metric                  FY22      FY23      FY24      FY25      FY26        │  │
│  │  ──────────────────────────────────────────────────────────────────          │  │
│  │  Revenue              $65,098   $54,324   $55,647   $56,812   $59,124       │  │
│  │    YoY %                            -16.6%   +2.4%    +2.1%    +4.1%       │  │
│  │  Gross Profit         $29,412   $22,481   $24,211   $24,981   $24,706       │  │
│  │  Gross Margin %         45.2%     41.4%     43.5%     44.0%     41.8%       │  │
│  │  EBITDA               $28,712   $22,010   $20,811   $18,241   $18,984       │  │
│  │  EBITDA Margin %        44.1%     40.5%     37.4%     32.1%     32.1%       │  │
│  │  EBIT                 $21,344   $16,812   $15,412   $14,881   $15,204       │  │
│  │  Interest Expense     ($1,201)  ($1,412)  ($1,380)  ($1,290)  ($1,184)      │  │
│  │  PBT                  $20,143   $15,400   $14,032   $13,591   $14,020       │  │
│  │  Tax Expense          ($5,682)  ($4,412)  ($3,984)  ($3,998)  ($4,103)      │  │
│  │  Net Profit           $14,461   $10,988   $10,048    $9,593    $9,917       │  │
│  │  Net Margin %           22.2%     20.2%     18.1%     16.9%     16.8%       │  │
│  │  EPS (basic)           $2.876    $2.184    $2.008    $1.914    $2.018       │  │
│  │  DPS                   $2.240    $1.700    $1.560    $1.500    $1.180*      │  │
│  │  Franking %              100%      100%      100%      100%      100%       │  │
│  │  Grossed-Up DPS        $3.200    $2.429    $2.229    $2.143    $1.686       │  │
│  │  ──────────────────────────────────────────────────────────────────          │  │
│  │  * Interim only (FY26 full year not yet reported)                            │  │
│  │                                                                               │  │
│  │  [📊 Chart This Data]  [📥 Download CSV]                                     │  │
│  └───────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                  │
│  ┌─── INTERACTIVE CHART ──────────────────────────────────────────────────────┐  │
│  │  Show: [Revenue] [EBITDA ●] [Net Profit] [EPS] [DPS] [Grossed-Up DPS]      │  │
│  │                                                                               │  │
│  │  $30B ┤  ████                                                                │  │
│  │  $25B ┤  ████ ████                                                           │  │
│  │  $20B ┤  ████ ████ ████ ████ ████                                            │  │
│  │  $15B ┤                                                                       │  │
│  │       └─FY22──FY23──FY24──FY25──FY26──                                       │  │
│  └───────────────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

### 5c. Technicals Tab

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  BHP  TECHNICALS                                                                 │
│                                                                                  │
│  ┌─── PRICE ACTION INDICATORS ───────────────────────────────────────────────┐  │
│  │                                                                              │  │
│  │  MOVING AVERAGES          VALUE      vs PRICE   SIGNAL                      │  │
│  │  SMA 20                  $43.82      Below       🟢 Bullish                 │  │
│  │  SMA 50                  $41.24      Below       🟢 Bullish                 │  │
│  │  SMA 200                 $42.18      Below       🟢 Bullish                 │  │
│  │  EMA 20                  $44.01      Below       🟢 Bullish                 │  │
│  │  EMA 50                  $41.98      Below       🟢 Bullish                 │  │
│  │  EMA 200                 $42.80      Below       🟢 Bullish                 │  │
│  │                                                                              │  │
│  │  MOMENTUM                 VALUE      SIGNAL                                 │  │
│  │  RSI (14)                  62.4      🟡 Neutral (40–70)                     │  │
│  │  MACD                     +0.48      🟢 Bullish (above signal)              │  │
│  │  MACD Signal              +0.21      —                                       │  │
│  │  Stochastic %K             71.2      🟡 Approaching overbought              │  │
│  │  Williams %R              -28.4      🟡 Neutral                             │  │
│  │  MFI (14)                  58.2      🟡 Neutral                             │  │
│  │                                                                              │  │
│  │  VOLATILITY               VALUE                                             │  │
│  │  ATR (14)                  $1.42                                             │  │
│  │  ATR % of Price             3.1%                                             │  │
│  │  Bollinger Upper          $47.82                                             │  │
│  │  Bollinger Lower          $39.14                                             │  │
│  │  Bollinger %B               0.71     🟡 Upper half                          │  │
│  │  Historical Vol (30d)      22.4%                                             │  │
│  │                                                                              │  │
│  │  PERFORMANCE               1D      1W      1M      3M      6M      1Y       │  │
│  │  Absolute Return         +1.2%   +4.8%  +12.4%  -2.1%  +18.2%  +22.8%     │  │
│  │  vs XJO (Alpha)          +0.8%   +3.2%   +9.1%  -4.4%  +12.8%  +10.2%     │  │
│  │  Sharpe (1Y)               0.82                                              │  │
│  │  Sortino (1Y)              1.14                                              │  │
│  │  Max Drawdown (1Y)       -22.4%                                              │  │
│  │                                                                              │  │
│  │  VOLUME                   VALUE                                             │  │
│  │  Today Vol             18.4M shares                                          │  │
│  │  3M Avg Vol            18.2M shares                                          │  │
│  │  Vol Ratio Today         1.01x (normal)                                      │  │
│  │  OBV Trend             → Accumulation                                        │  │
│  │                                                                              │  │
│  └──────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                  │
│  ┌─── 52-WEEK PRICE BAND ────────────────────────────────────────────────────┐  │
│  │                                                                               │  │
│  │  $36.80                  $45.20 ▲              $52.30                        │  │
│  │  52W Low                 Current               52W High                      │  │
│  │  └──────────────────────────●────────────────────┘                           │  │
│  │                             ▲ Currently 56% of 52W range                     │  │
│  └───────────────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

### 5d. Peers Tab

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  BHP  PEER COMPARISON                                                            │
│  Sector: Materials  |  [Edit Peers +]                                            │
│                                                                                  │
│  ┌─── PEER TABLE ──────────────────────────────────────────────────────────────┐  │
│  │                                                                               │  │
│  │           BHP    ●    RIO        FMG        MIN        S32        NEM        │  │
│  │  ─────────────────────────────────────────────────────────────────           │  │
│  │  Price    $45.20     $128.40    $22.80    $48.10     $5.82     $112.30       │  │
│  │  MktCap   218.4B     192.3B     69.2B     14.2B      10.4B      52.8B       │  │
│  │  PE TTM   12.4x      10.2x      7.8x      15.2x      8.4x       22.1x       │  │
│  │  PB        1.8x       1.4x       1.9x       2.1x      0.9x        2.4x      │  │
│  │  EV/EBITDA 7.2x       6.8x       4.9x       8.1x      4.2x       11.4x      │  │
│  │  Div Yld   5.2%       5.0%       9.8%       4.1%       6.2%        1.8%     │  │
│  │  G-Up Yld  7.4%       7.1%      14.0%       5.9%       8.9%        2.6%     │  │
│  │  Franking  100%       100%       100%       100%       100%         N/A      │  │
│  │  ROE       18.4%      17.2%      28.4%      12.1%      14.8%       8.2%     │  │
│  │  Net Mgn   16.8%      18.2%      28.1%       9.4%      11.2%      10.4%     │  │
│  │  DebtEq     0.42       0.38       0.21       0.94       0.62       0.88     │  │
│  │  AISC    $1,847/t   $2,102/t  $1,654/t  $3,841/t  $2,201/t  $1,284/oz     │  │
│  │  52W Chg  +22.8%     +18.4%    +31.2%    -12.4%     +8.2%     +41.2%      │  │
│  │  ─────────────────────────────────────────────────────────────────           │  │
│  │                  Sector Median: PE 10.8x | ROE 17.0% | Div 5.1%            │  │
│  └───────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                  │
│  ┌─── SECTOR RANK (BHP vs All Materials, n=142) ─────────────────────────────┐  │
│  │  PE Ratio   ████████░░░░░░░░  Rank 42/142  (cheaper = better 🟢)           │  │
│  │  ROE        ██████████░░░░░░  Rank 28/142  🟢                               │  │
│  │  Div Yield  ██████████░░░░░░  Rank 31/142  🟢                               │  │
│  │  Debt/Eq    ███████░░░░░░░░░  Rank 55/142  🟡                               │  │
│  └────────────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

### 5e. AI Insights Tab

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  BHP  AI INSIGHTS  🤖  [PRO FEATURE]                                            │
│  Powered by Claude · Updated: 20 Apr 2026                                        │
│                                                                                  │
│  ┌─── AI SUMMARY ────────────────────────────────────────────────────────────┐  │
│  │  📝 BHP GROUP — ANALYST SNAPSHOT                                            │  │
│  │                                                                               │  │
│  │  BHP is Australia's largest diversified miner with primary exposure to iron   │  │
│  │  ore, copper, and met coal. The company trades at 12.4x PE, a discount to    │  │
│  │  the global mining sector median of 14.8x, supported by a 100%-franked       │  │
│  │  5.2% dividend yield (grossed-up: 7.4%) — attractive for Australian          │  │
│  │  superannuation investors.                                                    │  │
│  │                                                                               │  │
│  │  STRENGTHS: Balance sheet strength (Debt/Equity 0.42), consistent franked    │  │
│  │  dividends, exposure to copper thematic (EV transition).                     │  │
│  │                                                                               │  │
│  │  RISKS: Iron ore price dependence (~50% EBITDA), China demand uncertainty,   │  │
│  │  ESG pressure from thermal coal legacy, FX headwinds (AUD/USD).              │  │
│  │                                                                               │  │
│  │  Based on FY26 half-year results filed 19 Feb 2026.                          │  │
│  │  ⚠️ This is AI-generated analysis, not financial advice.                     │  │
│  └───────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                  │
│  ┌─── ASK THE ANNUAL REPORT 📄 ──────────────────────────────────────────────┐  │
│  │  Reports indexed: FY26 H1, FY25 Annual, FY24 Annual, FY23 Annual           │  │
│  │                                                                               │  │
│  │  ┌──────────────────────────────────────────────────────────────────────┐   │  │
│  │  │  Ask anything about BHP's reports...                                  │   │  │
│  │  │  e.g. "What is BHP's copper production guidance for FY27?"           │   │  │
│  │  └──────────────────────────────────────────────────────────────────────┘   │  │
│  │  [Ask →]                                                                      │  │
│  │                                                                               │  │
│  │  SAMPLE QUESTIONS:                                                            │  │
│  │  "What did management say about China demand outlook?"                        │  │
│  │  "What is the ESG performance vs prior year?"                                │  │
│  │  "What are the key capital expenditure plans for FY27?"                      │  │
│  └───────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                  │
│  ┌─── RECENT ANNOUNCEMENTS (AI CLASSIFIED) ──────────────────────────────────┐  │
│  │  📊 Results    19 Feb 2026  H1 FY26 Results — Revenue $29.8B (Beat +2.1%)   │  │
│  │  💰 Dividend   19 Feb 2026  Interim DPS $0.59 (100% franked)                │  │
│  │  📰 Operations 08 Jan 2026  Dec Qtr Production Report — Iron Ore 78.4Mt     │  │
│  │  🏗️  Strategy   12 Dec 2025  Copper growth strategy update (Escondida)       │  │
│  └────────────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 6. Watchlist Manager

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  WATCHLISTS  /watchlists                                                         │
│                                                                                  │
│  ┌─── LEFT: WATCHLIST SELECTOR ──┐  ┌─── RIGHT: WATCHLIST CONTENTS ──────────┐  │
│  │                                │  │                                          │  │
│  │  📋 My Watchlists              │  │  📋 "Big 4 Banks + Dividends"  [Edit ✏️] [×]│  │
│  │  ─────────────────────────     │  │  12 stocks  ·  Last updated: today       │  │
│  │                                │  │                                           │  │
│  │  ● Big 4 Banks + Dividends (12)│  │  [+ Add Stock]  [🔔 Alerts]  [📤 Export] │  │
│  │    Mining Thematic (8)         │  │                                           │  │
│  │    REIT Income (6)             │  │  ┌─── WATCHLIST TABLE ────────────────┐  │  │
│  │    High Franking (15)          │  │  │                           52W              │  │
│  │    Watchlist 5 (4)             │  │  │  Ticker  Price   Day%  G-Up Yld  Chg  │  │
│  │                                │  │  │  ──────────────────────────────────  │  │
│  │  [+ New Watchlist]             │  │  │  CBA    $118.40 -0.3%  8.04%  +14% │  │
│  │                                │  │  │  WBC     $26.80 +0.8%  9.71%   +8% │  │
│  │  IMPORT/EXPORT                 │  │  │  ANZ     $29.40 +0.4%  9.29%  +11% │  │
│  │  [📥 Import CSV]               │  │  │  NAB     $35.20 +0.2%  8.86%  +12% │  │
│  │  [📤 Export All]               │  │  │  BEN     $11.20 -0.1%  8.57%   +4% │  │
│  │                                │  │  │  BOQ      $6.80 +1.1%  7.43%   -2% │  │
│  └────────────────────────────────┘  │  │  ...                                 │  │
│                                      │  └──────────────────────────────────────┘  │
│                                      │                                           │  │
│                                      │  WATCHLIST STATS                          │  │
│                                      │  ┌───────────────────────────────────┐  │  │
│                                      │  │ Avg Grossed-Up Yield    8.97%     │  │
│                                      │  │ Avg PE                  11.2x     │  │
│                                      │  │ Avg 52W Return         +9.4%      │  │
│                                      │  │ Total Market Cap        $592B     │  │
│                                      │  └───────────────────────────────────┘  │  │
│                                      └───────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 7. Portfolio Tracker

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  PORTFOLIO TRACKER  /portfolio                                                   │
│  [PRO FEATURE]                                                                   │
│                                                                                  │
│  ┌─── PORTFOLIO SELECTOR ────────────────────────────────────────────────────┐  │
│  │  [● My Super Portfolio]  [SMSF Account]  [Trading Account]  [+ New]        │  │
│  └────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                  │
│  ┌─── PORTFOLIO OVERVIEW ─────────────────────────────────────────────────────┐  │
│  │                                                                               │  │
│  │  Total Value         $142,840.20    ▲ $2,140.80 (+1.52%) Today              │  │
│  │  Total Cost Basis    $118,200.00                                              │  │
│  │  Total Gain/Loss     +$24,640.20  (+20.85%)    [Unrealised]                 │  │
│  │  Realised Gain FY26   +$4,820.00              [Tax Year: FY26]              │  │
│  │  Income (FY26)        +$7,240.00  (dividends received + franking credits)   │  │
│  │                                                                               │  │
│  │  [1D] [1W] [1M] [3M] [YTD] [1Y] [All]         ● Portfolio  ····· XJO        │  │
│  │  ────────────────────────────────────────────────────────────────────         │  │
│  │  $145K ┤                                                  ╭──────             │  │
│  │  $130K ┤                              ╭────────────────────                   │  │
│  │  $118K ┼ ────────────────────────────                                         │  │
│  │        └── Jan 26 ──── Feb 26 ──── Mar 26 ──── Apr 26 ───                    │  │
│  └───────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                  │
│  ┌─── HOLDINGS TABLE ────────────────────────────────────────────────────────┐  │
│  │                                                                               │  │
│  │  Ticker  Qty    Avg Cost  Price    Value     Gain/Loss    Weight  Yield      │  │
│  │  ──────────────────────────────────────────────────────────────────          │  │
│  │  CBA    200    $104.20  $118.40  $23,680   +$2,840 +13.6%  16.6%  5.7%      │  │
│  │  BHP    500     $36.40   $45.20  $22,600   +$4,400 +24.2%  15.8%  5.2%      │  │
│  │  WBC    800     $22.10   $26.80  $21,440   +$3,760 +21.3%  15.0%  6.8%      │  │
│  │  RIO    150     $98.20  $128.40  $19,260   +$4,530 +30.8%  13.5%  5.0%      │  │
│  │  ANZ    600     $25.20   $29.40  $17,640   +$2,520 +16.7%  12.3%  6.5%      │  │
│  │  GOZ     2K      $3.20    $3.82   $7,640   +$1,240 +19.4%   5.3%  6.8%      │  │
│  │  ...                                                                          │  │
│  │  CASH                                        $7,100                  5.0%    │  │
│  │  ─────────────────────────────────────────────────────────────────────        │  │
│  │  TOTAL                          $142,840  +$24,640 +20.85%         5.38%    │  │
│  │                                                                               │  │
│  │  [+ Add Trade]  [📥 Import Trades CSV]  [📤 Export]                          │  │
│  └───────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                  │
│  ┌─── SECTOR ALLOCATION ──────┐  ┌─── INCOME CALENDAR ──────────────────────┐  │
│  │                              │  │                                            │  │
│  │  ██ Financials  43.9%        │  │  Apr ▐ CBA ex-div 28 Apr  $0.59×200=$118 │  │
│  │  ██ Materials   29.3%        │  │  May ▐ BHP pay-div 15 May $0.59×500=$295 │  │
│  │  ██ REITs        5.3%        │  │  Jun ▐ WBC ex-div 12 Jun  $0.92×800=$736 │  │
│  │  ░░ Cash         5.0%        │  │                                            │  │
│  │  ██ Other       16.5%        │  │  FY26 Est. Income: $7,840 + $3,360 frank  │  │
│  │                              │  │  Grossed-Up Income: $11,200               │  │
│  └──────────────────────────────┘  └────────────────────────────────────────────┘  │
│                                                                                  │
│  ┌─── TAX SUMMARY (FY26) [PRO] ───────────────────────────────────────────────┐  │
│  │  Dividends Received          $7,240    Franking Credits   $3,103           │  │
│  │  Realised Capital Gains      $4,820    CGT Discount (50%) $2,410           │  │
│  │  Net Capital Gains           $2,410    (held > 12 months)                  │  │
│  │                                                                               │  │
│  │  ⚠️ Tax estimate only — consult your accountant or tax professional.          │  │
│  └───────────────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 8. Alerts Manager

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  ALERTS  /alerts                          🔔 3 Active Alerts Triggered Today     │
│                                                                                  │
│  ┌─── ALERT CATEGORIES ──────────────────────────────────────────────────────┐  │
│  │  [All (12)] [Price (4)] [Metric (5)] [Screener (2)] [Announcement (1)]     │  │
│  └────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                  │
│  ┌─── TRIGGERED TODAY ────────────────────────────────────────────────────────┐  │
│  │  🔴 TRIGGERED                                                                │  │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │  │
│  │  │ 🏷️  BHP  |  Price Alert  |  09:42 AM                                 │   │  │
│  │  │ BHP crossed above $45.00 ✅                                          │   │  │
│  │  │ Current: $45.20  ·  Target was: $45.00                               │   │  │
│  │  │ [View BHP]  [Snooze 7d]  [Delete]                                    │   │  │
│  │  └─────────────────────────────────────────────────────────────────────┘   │  │
│  │                                                                               │  │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │  │
│  │  │ 🏷️  ANZ  |  Metric Alert  |  06:35 PM (post-compute)                 │   │  │
│  │  │ PE Ratio dropped below 11x ✅                                        │   │  │
│  │  │ Current PE: 10.8x  ·  Threshold: 11.0x                               │   │  │
│  │  │ [View ANZ]  [Snooze 7d]  [Delete]                                    │   │  │
│  │  └─────────────────────────────────────────────────────────────────────┘   │  │
│  └───────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                  │
│  ┌─── ALL ALERTS ─────────────────────────────────────────────────────────────┐  │
│  │                                                                               │  │
│  │  [+ Create Alert]                                                             │  │
│  │                                                                               │  │
│  │  ● Active   BHP   Price above $45.00           🟢 Triggered                 │  │
│  │  ● Active   ANZ   PE Ratio below 11x           🟢 Triggered                 │  │
│  │  ● Active   WBC   Grossed-Up Yield above 10%   ⏳ Watching ($9.71%)         │  │
│  │  ● Active   CBA   52W High breakout             ⏳ Watching                  │  │
│  │  ● Active   —     Screener "High Frank Value"   ⏳ New match: 0 today       │  │
│  │  ○ Paused   RIO   Price below $100.00           ⏸ Paused                   │  │
│  │                                                                               │  │
│  └───────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                  │
│  ┌─── CREATE NEW ALERT ───────────────────────────────────────────────────────┐  │
│  │  Type:   [● Price Alert] [○ Metric Alert] [○ Screener Alert] [○ Announce.] │  │
│  │  Stock:  [BHP                    ]                                           │  │
│  │  When:   Price  [crosses above ▾]  [$             ]                          │  │
│  │  Notify: [✅ Email]  [✅ Push]  [○ SMS]                                      │  │
│  │  Repeat: [○ Once  ● Every time  ○ Daily max]                                │  │
│  │                                  [Save Alert]                                │  │
│  └───────────────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 9. Community Screens Explorer

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  COMMUNITY SCREENS  /screens                                                     │
│                                                                                  │
│  ┌─── FEATURED SCREENS ──────────────────────────────────────────────────────┐  │
│  │  🏆 Staff Picks  |  🔥 Trending  |  ⭐ Top Rated  |  🆕 New                │  │
│  └────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                  │
│  ┌─── SEARCH & FILTER ───────────────────────────────────────────────────────┐  │
│  │  [🔍 Search screens...        ]  Tag: [All ▾] [Dividends] [Value] [Growth] │  │
│  │                                        [Miners] [REITs] [Technical]        │  │
│  └────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                  │
│  ┌─── SCREEN CARDS GRID ──────────────────────────────────────────────────────┐  │
│  │                                                                               │  │
│  │  ┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐  │  │
│  │  │ 💰 HIGH FRANKING     │  │ ⛏️  AISC vs GOLD     │  │ 🏢 REIT DEEP VALUE  │  │
│  │  │ VALUE SCREEN         │  │ MARGIN PLAY          │  │                      │  │
│  │  │                      │  │                      │  │                      │  │
│  │  │ by @dividendhunter   │  │ by @miningpro        │  │ by @reitincome       │  │
│  │  │ ⭐ 4.8  847 runs     │  │ ⭐ 4.6  521 runs     │  │ ⭐ 4.4  312 runs     │  │
│  │  │ 🏷️ Dividends Value   │  │ 🏷️ Mining ASX       │  │ 🏷️ REITs Income      │  │
│  │  │                      │  │                      │  │                      │  │
│  │  │ Filters:             │  │ Filters:             │  │ Filters:             │  │
│  │  │ PE ≤ 15              │  │ AISC < Commodity Px  │  │ NTA Discount > 5%   │  │
│  │  │ Div Yld ≥ 4%         │  │ Reserve Life > 10yr  │  │ FFO Yield > 6%      │  │
│  │  │ Franking = 100%      │  │ Debt/Eq < 0.5        │  │ WALE > 5yr          │  │
│  │  │ Debt/Eq < 0.5        │  │ Mkt Cap > $500M      │  │ Occupancy > 95%     │  │
│  │  │                      │  │                      │  │                      │  │
│  │  │ 23 stocks match      │  │ 8 stocks match       │  │ 12 stocks match     │  │
│  │  │ [▶ Run] [👁 Preview]  │  │ [▶ Run] [👁 Preview] │  │ [▶ Run] [👁 Preview]│  │
│  │  └─────────────────────┘  └─────────────────────┘  └─────────────────────┘  │  │
│  │                                                                               │  │
│  │  ┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐  │  │
│  │  │ 📊 PIOTROSKI ≥ 8    │  │ 📉 MOST SHORTED      │  │ 🚀 MOMENTUM + VALUE  │  │
│  │  │ QUALITY STOCKS      │  │ REVERSAL WATCH       │  │                      │  │
│  │  │                      │  │                      │  │                      │  │
│  │  │ by @qualityinvestor  │  │ by @contrarian_au    │  │ by @quanttrader      │  │
│  │  │ ⭐ 4.7  688 runs     │  │ ⭐ 4.2  428 runs     │  │ ⭐ 4.5  502 runs     │  │
│  │  │ 🏷️ Quality Scores   │  │ 🏷️ Short ASIC        │  │ 🏷️ Technical Value   │  │
│  │  │                      │  │                      │  │                      │  │
│  │  │ Piotroski ≥ 8        │  │ ASIC Short > 10%     │  │ EMA50 crossover ↑   │  │
│  │  │ ROE > 15%            │  │ Short ↑ 3 days       │  │ RSI 40–60           │  │
│  │  │ Debt/Eq < 0.4        │  │ Price near 52W Low   │  │ PE < Sector         │  │
│  │  │ FCF Yield > 5%       │  │ FCF positive         │  │ ROE > 12%           │  │
│  │  │                      │  │                      │  │                      │  │
│  │  │ 31 stocks match      │  │ 14 stocks match      │  │ 19 stocks match     │  │
│  │  │ [▶ Run] [👁 Preview]  │  │ [▶ Run] [👁 Preview] │  │ [▶ Run] [👁 Preview]│  │
│  │  └─────────────────────┘  └─────────────────────┘  └─────────────────────┘  │  │
│  │                                                                               │  │
│  │  [Load More Screens ↓]                                                        │  │
│  └───────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                  │
│  ┌─── PUBLISH YOUR SCREEN ────────────────────────────────────────────────────┐  │
│  │  💡 Share your screens with the ASX investing community.                     │  │
│  │  Build a screen → [Save] → check "Make Public" → it appears here.            │  │
│  │  Earn reputation points when others run your screen.  [Learn More →]         │  │
│  └───────────────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 10. Search (Global)

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  GLOBAL SEARCH  (triggered by clicking search bar or pressing /)                 │
│                                                                                  │
│  ┌─── SEARCH OVERLAY (full-width modal) ──────────────────────────────────────┐  │
│  │                                                                               │  │
│  │  [🔍 Search ASX stocks, metrics, screens...              ] [×]               │  │
│  │                                                                               │  │
│  │  ─── TYPING "bhp" ────────────────────────────────────────────────────────   │  │
│  │                                                                               │  │
│  │  STOCKS                                                                       │  │
│  │  ┌─────────────────────────────────────────────────────────────────────┐    │  │
│  │  │  BHP  BHP Group Limited          $45.20  ▲+1.22%   Materials       │    │  │
│  │  │  BHP  (also trades as: BHPB, BHP.AX)                               │    │  │
│  │  └─────────────────────────────────────────────────────────────────────┘    │  │
│  │                                                                               │  │
│  │  METRICS CONTAINING "bhp"                                                    │  │
│  │  (no results — type "PE ratio" instead)                                       │  │
│  │                                                                               │  │
│  │  ─── TYPING "pe ratio" ────────────────────────────────────────────────────   │  │
│  │                                                                               │  │
│  │  METRICS                                                                      │  │
│  │  ┌─────────────────────────────────────────────────────────────────────┐    │  │
│  │  │  📊  PE Ratio (TTM)         Price / Earnings (Trailing 12 Month)    │    │  │
│  │  │  📊  PE Ratio (Forward)     Price / Forward EPS Estimate [PRO]      │    │  │
│  │  │  📊  PEG Ratio              PE / EPS Growth Rate                    │    │  │
│  │  └─────────────────────────────────────────────────────────────────────┘    │  │
│  │                                                                               │  │
│  │  SCREENS WITH "PE"                                                            │  │
│  │  ┌─────────────────────────────────────────────────────────────────────┐    │  │
│  │  │  📋  "Low PE + High Franking"    by @valueinvestor  847 runs        │    │  │
│  │  │  📋  "PE < 10 Profitable Cos"   by @deepvalue      412 runs        │    │  │
│  │  └─────────────────────────────────────────────────────────────────────┘    │  │
│  │                                                                               │  │
│  │  KEYBOARD:  ↑↓ Navigate  ·  Enter to select  ·  Esc to close               │  │
│  └───────────────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 11. Authentication Pages

### Login Page

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                                                                  │
│                          [🦘 ASXScreener]                                        │
│                                                                                  │
│              ┌─────────────────────────────────────────────┐                    │
│              │                                               │                    │
│              │           Sign in to ASXScreener              │                    │
│              │                                               │                    │
│              │  Email                                         │                    │
│              │  [email@example.com                       ]   │                    │
│              │                                               │                    │
│              │  Password                                      │                    │
│              │  [••••••••••••••••                        ]   │                    │
│              │                              [Forgot? →]      │                    │
│              │                                               │                    │
│              │  [          Sign In          ]                │                    │
│              │                                               │                    │
│              │  ────────── or ──────────                     │                    │
│              │                                               │                    │
│              │  [G  Continue with Google   ]                 │                    │
│              │                                               │                    │
│              │  Don't have an account?  [Sign Up Free →]     │                    │
│              └─────────────────────────────────────────────┘                    │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Sign Up Page

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                          [🦘 ASXScreener]                                        │
│                                                                                  │
│              ┌─────────────────────────────────────────────┐                    │
│              │  Create Your Free Account                     │                    │
│              │                                               │                    │
│              │  Full Name                                     │                    │
│              │  [                                        ]   │                    │
│              │  Email                                         │                    │
│              │  [                                        ]   │                    │
│              │  Password (min 8 chars)                        │                    │
│              │  [                                        ]   │                    │
│              │                                               │                    │
│              │  Plan:                                         │                    │
│              │  ┌─────────────────────────────────────┐      │                    │
│              │  │ ● Free      $0/mo  — Basic screener │      │                    │
│              │  │ ○ Pro      $29/mo  — All metrics    │      │                    │
│              │  │ ○ Premium  $99/mo  — API + AI       │      │                    │
│              │  └─────────────────────────────────────┘      │                    │
│              │                                               │                    │
│              │  [✅] I agree to Terms of Service & Privacy   │                    │
│              │  [✅] I understand this is not financial advice│                    │
│              │                                               │                    │
│              │  [          Create Account          ]         │                    │
│              │                                               │                    │
│              │  Already have an account? [Sign In →]         │                    │
│              └─────────────────────────────────────────────┘                    │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 12. Account & Settings

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  ACCOUNT SETTINGS  /settings                                                     │
│                                                                                  │
│  ┌─── LEFT MENU ──────────────┐  ┌─── RIGHT CONTENT PANEL ─────────────────────┐ │
│  │                             │  │                                               │ │
│  │  👤 Profile                 │  │  👤 PROFILE                                   │ │
│  │  🔔 Notifications           │  │  ─────────────────────────────────────────   │ │
│  │  🔑 Security                │  │  Display Name    [                      ]    │ │
│  │  💳 Subscription            │  │  Email           [                      ]    │ │
│  │  📊 API Access   [PRO]      │  │  Avatar          [Upload Photo]               │ │
│  │  🎨 Preferences             │  │  Timezone        [Australia/Sydney      ▾]   │ │
│  │  🔗 Connected Apps          │  │  Currency        [AUD ▾]                     │ │
│  │                             │  │                                               │ │
│  │  ─────────────────          │  │  [Save Profile]                               │ │
│  │  📖 Help & Docs             │  │                                               │ │
│  │  💬 Support Chat            │  │  ─────────────────────────────────────────   │ │
│  │  🚪 Sign Out                │  │  SUBSCRIPTION                                 │ │
│  │                             │  │  Current Plan:  🟢 PRO  ($29/mo)             │ │
│  │                             │  │  Next billing:  20 May 2026                  │ │
│  │                             │  │  [Upgrade to Premium]  [Cancel Plan]         │ │
│  │                             │  │                                               │ │
│  │                             │  │  ─────────────────────────────────────────   │ │
│  │                             │  │  API ACCESS  [PRO+]                           │ │
│  │                             │  │  API Key:  asx_live_sk_•••••••••••••xyz      │ │
│  │                             │  │  [Reveal] [Regenerate]                        │ │
│  │                             │  │  Calls today:  1,240 / 10,000               │ │
│  │                             │  │  Docs: api.asxscreener.com.au                 │ │
│  └─────────────────────────────┘  └───────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 13. Mobile Responsive Breakpoints

### Mobile (375px) — Company Card Stack

```
┌──────────────────────────────┐
│ 🦘 ASXScreener    🔍  ☰      │
├──────────────────────────────┤
│ XJO 7,842 ▲0.4%  →→→        │
├──────────────────────────────┤
│                              │
│  BHP Group Ltd               │
│  $45.20  ▲ +1.22%            │
│  ─────────────────────────── │
│  Mkt Cap  $218.4B            │
│  PE        12.4x             │
│  Div Yld    5.2%  (100% fkd) │
│  G-Up Yld   7.4% 💛          │
│  Piotroski  7/9  🟢          │
│                              │
│  [Chart] [Financials] [AI]   │
│                              │
├──────────────────────────────┤
│ [Screener] [Watch] [Portfolio]│
│ [Feed]              [Alerts] │
└──────────────────────────────┘
```

### Mobile Screener (Simplified)

```
┌──────────────────────────────┐
│  SCREENER                 ←  │
├──────────────────────────────┤
│ [+ Add Filter]               │
│                              │
│ ┌──────────────────────────┐ │
│ │ PE Ratio  ≤  20       [×]│ │
│ └──────────────────────────┘ │
│ ┌──────────────────────────┐ │
│ │ Div Yield ≥ 3.5%     [×]│ │
│ └──────────────────────────┘ │
│ ┌──────────────────────────┐ │
│ │ Franking  = 100%      [×]│ │
│ └──────────────────────────┘ │
│                              │
│ [▶ Run — 2,200 stocks]        │
│                              │
│ ── 47 results ──────────     │
│ WBC  $26.80  9.71% G-Up ▶   │
│ ANZ  $29.40  9.29% G-Up ▶   │
│ NAB  $35.20  8.86% G-Up ▶   │
│ ...                          │
└──────────────────────────────┘
```

### Tablet (768px) — Two Column Layout

```
┌────────────────────────────────────────────────────────────────┐
│ 🦘 ASXScreener    [🔍 Search]         Feed Screener  Watch  ☰  │
├────────────────────────────────────────────────────────────────┤
│  XJO 7,842 ▲0.4%   BHP ▲1.2%   CBA ▼0.3%   →→→              │
├────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────┐  ┌─────────────────────────────────┐  │
│  │  MARKET OVERVIEW     │  │  TODAY'S HIGHLIGHTS              │  │
│  │  XJO  7842  ▲0.4%   │  │  📈 52 at 52W High               │  │
│  │  Materials  +1.8%   │  │  💰 8 Dividend Ex-Dates          │  │
│  │  Financials +0.5%   │  │  🏗️  3 Capital Raises            │  │
│  └─────────────────────┘  └─────────────────────────────────┘  │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  ANNOUNCEMENTS FEED                                       │  │
│  │  CBA  📊 Half Year — Revenue $27.8B ▲4.2%  [View] [AI]   │  │
│  │  BHP  💰 Dividend — 87¢, 100% Franked  Ex: 28 Apr        │  │
│  └──────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────┘
```

---

## 14. Component Library Summary

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  REUSABLE REACT COMPONENTS                                                       │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  DATA DISPLAY                                                                    │
│  ├─ <MetricCard>      Single metric with label/value/trend                       │
│  ├─ <MetricBadge>     Inline metric chip (PE: 12.4x)                            │
│  ├─ <PriceHero>       Large price + chart hero section                           │
│  ├─ <SparkLine>       Tiny inline trend chart                                    │
│  ├─ <OHLCChart>       Full TradingView-style price chart                         │
│  ├─ <FinancialTable>  Multi-year financial statement table                       │
│  ├─ <PeerTable>       Side-by-side peer comparison                               │
│  ├─ <ScatterPlot>     Two-metric scatter with hover labels                       │
│  ├─ <SectorBar>       Horizontal sector allocation bar                           │
│  └─ <HeatMap>         Sector/index colour-coded grid                            │
│                                                                                  │
│  ASX SPECIFIC                                                                    │
│  ├─ <FrankingBadge>   Gold 💛 badge showing grossed-up yield                    │
│  ├─ <MiningMetrics>   AISC, reserves, production panel                           │
│  ├─ <REITMetrics>     FFO, NTA, WALE, occupancy panel                           │
│  ├─ <ShortInterest>   ASIC short % with trend indicator                          │
│  └─ <CapRaiseTag>     Placement/rights offer banner                              │
│                                                                                  │
│  SCREENER BUILDER                                                                │
│  ├─ <FilterRow>       Metric + Operator + Value + Remove                         │
│  ├─ <MetricPicker>    Grouped dropdown/search for all 544 metrics                │
│  ├─ <OperatorSelect>  ≥, ≤, =, >, <, between, in list                           │
│  ├─ <ResultTable>     Sortable/configurable screener output                      │
│  └─ <SQLEditor>       Monaco-based SQL mode editor                               │
│                                                                                  │
│  USER INTERACTION                                                                │
│  ├─ <AlertForm>       Price/metric/screener alert creation                       │
│  ├─ <WatchlistPicker> Add to watchlist dropdown                                  │
│  ├─ <SearchModal>     Global cmd+K search overlay                                │
│  ├─ <NotifBell>       Alert bell with unread count                               │
│  └─ <ProGate>         Blurred content + upgrade prompt                           │
│                                                                                  │
│  LAYOUT                                                                          │
│  ├─ <TopBar>          Logo + search + auth                                       │
│  ├─ <NavBar>          Primary navigation                                         │
│  ├─ <MarketTicker>    Scrolling live price strip                                 │
│  ├─ <Sidebar>         Left collapsible panel                                     │
│  └─ <TabBar>          In-page tab navigation                                     │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 15. Next.js Route Map

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  NEXT.JS 14 APP ROUTER STRUCTURE                                                 │
│                                                                                  │
│  app/                                                                            │
│  ├── layout.tsx                  ← Root layout (TopBar, NavBar, Ticker)          │
│  ├── page.tsx                    ← / (Feed/Dashboard)                            │
│  ├── loading.tsx                                                                 │
│  ├── error.tsx                                                                   │
│  │                                                                               │
│  ├── screener/                                                                   │
│  │   ├── page.tsx                ← /screener (Query Builder)                    │
│  │   └── results/page.tsx        ← /screener/results                            │
│  │                                                                               │
│  ├── stocks/                                                                     │
│  │   └── [ticker]/               ← /stocks/BHP                                  │
│  │       ├── page.tsx            ← Overview tab (default)                       │
│  │       ├── financials/page.tsx ← /stocks/BHP/financials                      │
│  │       ├── technicals/page.tsx ← /stocks/BHP/technicals                      │
│  │       ├── peers/page.tsx      ← /stocks/BHP/peers                           │
│  │       ├── ai/page.tsx         ← /stocks/BHP/ai (PRO)                        │
│  │       └── news/page.tsx       ← /stocks/BHP/news                            │
│  │                                                                               │
│  ├── watchlists/                                                                 │
│  │   ├── page.tsx                ← /watchlists                                  │
│  │   └── [id]/page.tsx           ← /watchlists/123                             │
│  │                                                                               │
│  ├── portfolio/                                                                  │
│  │   ├── page.tsx                ← /portfolio (PRO)                             │
│  │   └── [id]/page.tsx           ← /portfolio/123                              │
│  │                                                                               │
│  ├── alerts/                                                                     │
│  │   └── page.tsx                ← /alerts                                      │
│  │                                                                               │
│  ├── screens/                                                                    │
│  │   ├── page.tsx                ← /screens (Community)                         │
│  │   └── [slug]/page.tsx         ← /screens/high-franking-value                │
│  │                                                                               │
│  ├── tools/                                                                      │
│  │   ├── franking-calculator/    ← /tools/franking-calculator                  │
│  │   ├── short-monitor/          ← /tools/short-monitor                         │
│  │   ├── capital-raises/         ← /tools/capital-raises                        │
│  │   ├── ratio-explorer/         ← /tools/ratio-explorer                        │
│  │   └── ai-analyst/             ← /tools/ai-analyst (PRO)                     │
│  │                                                                               │
│  ├── (auth)/                                                                     │
│  │   ├── login/page.tsx          ← /login                                       │
│  │   ├── signup/page.tsx         ← /signup                                      │
│  │   └── forgot/page.tsx         ← /forgot-password                            │
│  │                                                                               │
│  ├── settings/                                                                   │
│  │   └── page.tsx                ← /settings                                   │
│  │                                                                               │
│  └── api/                                                                        │
│      ├── screener/route.ts        ← POST /api/screener                          │
│      ├── stocks/[ticker]/route.ts ← GET /api/stocks/BHP                        │
│      ├── search/route.ts          ← GET /api/search?q=bhp                      │
│      ├── watchlists/route.ts      ← CRUD /api/watchlists                       │
│      ├── alerts/route.ts          ← CRUD /api/alerts                           │
│      └── ai/chat/route.ts         ← POST /api/ai/chat (PRO)                   │
│                                                                                  │
│  KEY IMPLEMENTATION NOTES                                                        │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │  ● Server Components by default → SEO-friendly, fast initial load        │   │
│  │  ● Client Components ('use client') for: charts, screener builder,       │   │
│  │    real-time price ticker, search overlay, alert forms                   │   │
│  │  ● SWR or React Query for client-side data fetching + caching            │   │
│  │  ● next/image for all logos and company assets                           │   │
│  │  ● Middleware for auth protection (watchlists, portfolio, PRO routes)    │   │
│  │  ● generateMetadata() for SEO on each stock page                         │   │
│  │  ● generateStaticParams() for ISR on top-200 stock pages                 │   │
│  │  ● Streaming (Suspense) for AI insights tab                              │   │
│  └──────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Summary

| Document | Coverage |
|---|---|
| Navigation Shell | TopBar, NavBar, Ticker, Tools dropdown |
| Feed / Dashboard | Market overview, announcements, movers, shorts |
| Screener Builder | Visual mode, SQL mode, AI mode, universe filters |
| Screener Results | Table, scatter plot, bulk actions, export |
| Company — Overview | Price hero, key metrics, dividends, quality scores |
| Company — Financials | P&L table 5Y, interactive chart, balance sheet tabs |
| Company — Technicals | Moving averages, momentum, volatility, 52W band |
| Company — Peers | Side-by-side table, sector rank bars |
| Company — AI Insights | Summary, annual report Q&A, announcement feed |
| Watchlists | Multi-list selector, holdings table, stats panel |
| Portfolio Tracker | Holdings, performance chart, sector allocation, income |
| Alerts Manager | Triggered alerts, create alert form |
| Community Screens | Card grid, publish flow, search/filter |
| Global Search | Overlay, stocks + metrics + screens results |
| Auth Pages | Login, Sign Up (plan selection) |
| Settings | Profile, subscription, API access |
| Mobile Wireframes | 375px, 768px breakpoints |
| Component Library | 30+ named reusable React components |
| Next.js Route Map | Full app router tree with ISR/SSR strategy |

---

*Next: `11_API_Design.md` — FastAPI endpoints, request/response schemas, authentication middleware, rate limiting*
