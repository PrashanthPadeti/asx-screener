# ASX Screener — Compute Engine: Schedule Strategy & Metric Classification

> Version 1.0 | April 2026
> Refining WHEN each metric is computed and WHY

---

## Your Proposed Strategy — Validation

```
Your idea:
  Daily metrics    → Compute daily       ✅ Correct
  Weekly metrics   → Compute weekly      ✅ Correct
  Monthly metrics  → Compute monthly     ✅ Correct
  Half-Yearly      → Compute half-yearly ✅ Correct
  Yearly+CAGR      → Compute yearly      ✅ Correct

THIS IS THE RIGHT APPROACH.

It avoids recomputing a 10-year CAGR every single day
when the underlying data only changes once a year.
Significant savings:
  CPU time:    ~85% reduction vs computing everything daily
  DB writes:   ~90% reduction
  Compute Engine runtime: 20 min → 3-4 min on non-annual days
```

---

## What You Are Missing — The Critical Gaps

### GAP 1: The "Hybrid Metric" Problem ⚠️ (Most Important)

```
Many metrics use TWO data sources with DIFFERENT update frequencies:
  - Current Price         → changes EVERY DAY
  - Financial Data        → changes ONCE A YEAR (or half-year)

This means these metrics MUST be recomputed DAILY
even though their financial component is annual:

  PE Ratio       = Current Price   ÷  Annual EPS          → DAILY ❗
  PB Ratio       = Current Price   ÷  Annual Book Value   → DAILY ❗
  PS Ratio       = Market Cap      ÷  Annual Revenue      → DAILY ❗
  EV/EBITDA      = Enterprise Val  ÷  Annual EBITDA       → DAILY ❗
  EV/EBIT        = Enterprise Val  ÷  Annual EBIT         → DAILY ❗
  EV/Sales       = Enterprise Val  ÷  Annual Revenue      → DAILY ❗
  Dividend Yield = Annual Dividend ÷  Current Price       → DAILY ❗
  FCF Yield      = Annual FCF      ÷  Market Cap          → DAILY ❗
  Earnings Yield = Annual EPS      ÷  Current Price       → DAILY ❗
  Market Cap     = Current Price   ×  Shares Outstanding  → DAILY ❗
  Enterprise Val = Market Cap      +  Debt - Cash         → DAILY ❗
  Altman Z-Score = Financial Data  +  Market Value Equity → DAILY ❗
  Intrinsic Val  = Formula using EPS (annual)              → DAILY ❗
    comparison: Price vs Intrinsic Value                   → DAILY ❗
  Price to NTA   = Current Price   ÷  NTA per unit (REIT) → DAILY ❗
  FFO Yield      = Annual FFO      ÷  Current Price       → DAILY ❗
  Price to FCF   = Current Price   ÷  Annual FCF/share    → DAILY ❗

RULE: If Current Price is in the formula → compute DAILY
      If Market Cap or EV is in the formula → compute DAILY
```

---

### GAP 2: TTM (Trailing Twelve Months) — The "In-Between" Problem

```
ASX companies report HALF-YEARLY (not quarterly like India/USA).
Many key metrics use TTM = last 12 months of data.

TTM updates TWICE A YEAR per company (when each half-year result drops):

  Revenue TTM      = H1 FY2025 + H2 FY2025
  EBITDA TTM       = H1 + H2
  EBIT TTM         = H1 + H2
  Net Profit TTM   = H1 + H2
  EPS TTM          = EPS(H1) + EPS(H2)
  FCF TTM          = CFO(H1) + CFO(H2) - Capex(H1) - Capex(H2)
  OCF TTM          = H1 + H2

When H1 results drop (e.g. January/February for June-year companies):
  → TTM = new H1 + previous H2
  → ALL ratios using TTM MUST recompute immediately
  → PE TTM changes, EV/EBITDA changes, FCF Yield changes

This is NOT "yearly" — it happens TWICE per year, per company,
and NOT on a fixed schedule (each company has its own reporting date).

IMPLICATION: Need an EVENT-TRIGGERED recompute (see Gap 3).
```

---

### GAP 3: Event-Triggered Recomputation (Missing from Your Schedule)

```
Not all data arrives on a predictable schedule.
These events require IMMEDIATE recomputation, regardless of the timer:

  EVENT                        TRIGGERS RECOMPUTE OF:
  ────────────────────────────────────────────────────────────────
  New annual results filed   → All financial ratios for that stock
  New half-year results      → TTM metrics, QoQ growth, margins
  Capital raise completed    → Shares outstanding → EPS, BVPS, all per-share
  Stock split / consolidation→ ALL per-share metrics (immediate)
  Dividend announced         → Dividend yield, payout ratio
  Director buys/sells shares → Holding % metrics
  ASX index change           → Index membership flags (filter by index)
  Name / code change         → Company master update

  Example scenario:
  BHP announces H1 results on Feb 18, 2026 at 9:02 AM
  → At 9:05 AM, BHP's PE/EV/margins/TTM metrics are STALE
  → Cannot wait for tonight's daily run
  → Must recompute BHP metrics immediately after announcement parsed
  → Show users updated metrics within minutes of announcement
```

---

### GAP 4: ASX Reporting Calendar Reality

```
ASX ≠ India (quarterly) ≠ USA (quarterly)
ASX standard: HALF-YEARLY reporting

  ┌─────────────────────────────────────────────────────────────┐
  │ MOST ASX COMPANIES (June financial year):                    │
  │                                                              │
  │  Annual Results:   August/September (FY ended June 30)      │
  │  Half-Year Results: February/March  (HY ended Dec 31)       │
  │                                                              │
  │ EXCEPTIONS:                                                  │
  │  December year-end (banks, some miners):                    │
  │    Annual: Feb/March, Half-Year: Aug/Sep                    │
  │                                                              │
  │  Mining companies ALSO file:                                 │
  │    Quarterly Activity Reports (QARs): Jan, Apr, Jul, Oct    │
  │    These contain production data but NOT full P&L           │
  └─────────────────────────────────────────────────────────────┘

So your "Quarterly" tier should be called "Half-Yearly"
and you should add a special "QAR" tier for mining stocks.
```

---

### GAP 5: Rolling Returns Change Every Single Day

```
You listed "Weekly" and "Monthly" metrics — but returns
are ROLLING, which means they change DAILY:

  Return 1 week  = (Today's price / Price 5 days ago) - 1
    → Yesterday's denominator was 6 days ago
    → Changes EVERY DAY (it rolls forward)

  Return 1 month = (Today's price / Price 21 days ago) - 1
    → Changes EVERY DAY

  Return 3 months → Changes EVERY DAY
  Return 6 months → Changes EVERY DAY
  Return 1 year   → Changes EVERY DAY

IMPLICATION: All return metrics belong in the DAILY bucket,
not in weekly/monthly buckets.
```

---

### GAP 6: Average Ratios Over Time (Subtle)

```
Some metrics are averages that incorporate new annual data each year
AND also change daily because they use price:

  Average PE (5Y)  = Average of last 5 years' PE ratios
    → Denominator (EPS) fixed for the year
    → BUT numerator (Price) changes daily
    → So average historical PE changes daily too!

  Historical PE 3Y, 5Y, 7Y, 10Y → DAILY (price-dependent)
  Average ROE 3Y, 5Y, 10Y       → YEARLY (pure financial)
  Average ROCE 3Y, 5Y, 10Y      → YEARLY (pure financial)
  Average OPM 5Y, 10Y           → YEARLY (pure financial)
  Average Dividend 5Y           → YEARLY (pure financial)
```

---

## Revised & Complete Classification Framework

```
╔══════════════════════════════════════════════════════════════════════╗
║           COMPUTE ENGINE: 5-TIER SCHEDULE + EVENT TRIGGER           ║
╠══════════════════════════════════════════════════════════════════════╣
║                                                                      ║
║  TIER 1: DAILY  (Every trading day, 5:30 PM AEST)                   ║
║  ────────────────────────────────────────────────                   ║
║  Rule: Uses current price OR market cap OR EV in formula            ║
║                                                                      ║
║  Technical Indicators:                                               ║
║    DMA 20, DMA 50, DMA 200, EMA 12, EMA 26                          ║
║    MACD, MACD Signal, MACD Histogram                                 ║
║    RSI 14, Stochastic RSI, ADX                                       ║
║    ATR 14, Bollinger Bands (upper/mid/lower/%), Historical Vol       ║
║    Volume, Volume avg 5D/20D/60D, Volume Ratio, OBV                 ║
║    Golden Cross, Death Cross (signals)                               ║
║    52W High/Low, All-Time High/Low                                   ║
║    % from 52W High/Low, % from ATH/ATL, Range Position              ║
║    DMA 50 Ratio, DMA 200 Ratio                                       ║
║    Above DMA 50/200 (boolean)                                        ║
║                                                                      ║
║  Valuation (price × financial data):                                 ║
║    Market Cap, Enterprise Value                                      ║
║    PE Ratio (TTM), Forward PE                                        ║
║    PB Ratio, PS Ratio, PCF Ratio, PFCF Ratio                        ║
║    EV/EBITDA, EV/EBIT, EV/Sales, EV/FCF                             ║
║    PEG Ratio (uses PE + growth rate)                                 ║
║    Earnings Yield, FCF Yield, Dividend Yield                         ║
║    Grossed-up Yield (AUS: franking credits + price)                 ║
║    Price to NTA (REITs), FFO Yield (REITs)                          ║
║    Altman Z-Score (uses market value of equity)                     ║
║    Graham Number vs Current Price                                    ║
║    Intrinsic Value (price comparison component)                      ║
║    Market Cap to Sales, Market Cap to Cash Flow                     ║
║    Market Cap to Quarterly Profit                                    ║
║    Short Interest % (from ASIC daily update)                        ║
║    Short Interest Change (1W, 1M)                                    ║
║    Beta (rolling 1Y, 3Y)                                             ║
║    Sharpe Ratio (rolling 1Y), Sortino Ratio (rolling 1Y)            ║
║    Max Drawdown (rolling 1Y, 3Y)                                     ║
║                                                                      ║
║  Returns (all rolling — change every day):                           ║
║    Return 1D, 1W, 1M, 3M, 6M, 1Y, 3Y (CAGR), 5Y (CAGR)            ║
║    Historical PE 3Y avg, 5Y avg, 7Y avg, 10Y avg                    ║
║    (These use price in numerator — daily)                           ║
║                                                                      ║
║  COMPUTE TIME: ~3–5 min for all 2,200 stocks (lightweight)          ║
╠══════════════════════════════════════════════════════════════════════╣
║                                                                      ║
║  TIER 2: WEEKLY  (Every Saturday morning, 6:00 AM AEST)             ║
║  ─────────────────────────────────────────────────────              ║
║  Rule: Aggregates of daily data for the week                        ║
║                                                                      ║
║    Weekly OHLCV (Open/High/Low/Close/Volume for the week)           ║
║    Weekly price change %                                             ║
║    Weekly volume vs 4-week average                                   ║
║    Weekly RSI (using weekly candles, separate from daily RSI)        ║
║    Weekly MACD (weekly candles)                                      ║
║    New 52W highs/lows this week (summary)                           ║
║    Stocks above/below DMA 50/200 this week (market breadth)         ║
║    Sector performance summary (weekly returns by sector)            ║
║                                                                      ║
║  NOTE: Most of these are AGGREGATIONS of daily data already         ║
║  stored in daily_prices. Not new computations.                      ║
║  COMPUTE TIME: ~5–10 min                                             ║
╠══════════════════════════════════════════════════════════════════════╣
║                                                                      ║
║  TIER 3: MONTHLY  (1st Saturday of each month, 7:00 AM AEST)        ║
║  ─────────────────────────────────────────────────────────          ║
║  Rule: Aggregates and ratios best viewed on monthly basis           ║
║                                                                      ║
║    Monthly OHLCV (monthly candles)                                   ║
║    Monthly RSI, Monthly MACD                                         ║
║    Monthly return % per stock                                        ║
║    Sector monthly performance ranking                                ║
║    Monthly volume profile                                            ║
║    52-week high/low refresh (full recalculation)                    ║
║    All-time high/low refresh (full recalculation)                   ║
║                                                                      ║
║  ALSO: Monthly snapshot of computed_metrics for all stocks          ║
║  (for historical backtesting — "what was BHP's PE in March 2023?")  ║
║  Store 1 row per stock per month (end-of-month values)              ║
║                                                                      ║
║  COMPUTE TIME: ~15–20 min                                            ║
╠══════════════════════════════════════════════════════════════════════╣
║                                                                      ║
║  TIER 4: HALF-YEARLY  (Scheduled + EVENT-TRIGGERED)                 ║
║  ─────────────────────────────────────────────────────              ║
║  Rule: Financial ratios derived from half-year P&L results          ║
║                                                                      ║
║  Triggered by: New half-year results announcement on ASX            ║
║  Scheduled sweep: February 28 + August 31 (catches all reports)    ║
║                                                                      ║
║  Half-Year P&L Metrics:                                              ║
║    Revenue (H1/H2), Operating Profit, EBITDA, EBIT                  ║
║    Interest, Depreciation, PAT, Net Profit, EPS                     ║
║    GPM, OPM, NPM, EBITDA Margin                                     ║
║                                                                      ║
║  TTM (Trailing Twelve Month) Recomputation:                          ║
║    Revenue TTM = new H + prior H                                    ║
║    EBITDA TTM, EBIT TTM, Net Profit TTM, EPS TTM                    ║
║    FCF TTM, OCF TTM                                                  ║
║                                                                      ║
║  Growth vs Same Period Last Year:                                    ║
║    H1 Revenue YoY, H1 Profit YoY, H1 EPS YoY                       ║
║    H1 vs H2 (sequential growth)                                     ║
║                                                                      ║
║  Mining Quarterly Activity Reports (QARs):                           ║
║    Production volume (quarterly), AISC, C1 cost                    ║
║    Production vs guidance                                            ║
║    Triggered: January, April, July, October                         ║
║                                                                      ║
║  After Half-Year compute: RE-TRIGGER Tier 1 for affected stocks     ║
║  (because TTM changed → PE TTM, EV/EBITDA etc. must update)        ║
║  Estimated affected stocks per season: ~800-1,200                   ║
║                                                                      ║
║  COMPUTE TIME: ~30–45 min (half-year results season)                ║
╠══════════════════════════════════════════════════════════════════════╣
║                                                                      ║
║  TIER 5: YEARLY  (Annual results season + scheduled August sweep)   ║
║  ─────────────────────────────────────────────────────────────      ║
║  Rule: Pure financial data from annual reports (no price)           ║
║        AND all historical CAGR computations                         ║
║                                                                      ║
║  Pure Financial Ratios (no price):                                   ║
║    ROE, ROA, ROCE, ROIC, CROIC                                       ║
║    Gross Margin, Operating Margin, Net Margin, EBITDA Margin        ║
║    Asset Turnover, Inventory Turnover                                ║
║    Debtor Days (DSO), Days Payable (DPO), Days Inventory (DIO)      ║
║    Cash Conversion Cycle (CCC), Working Capital Days                ║
║    Debt to Equity, Net Debt/EBITDA, Interest Coverage               ║
║    Current Ratio, Quick Ratio, Cash Ratio                            ║
║    Financial Leverage, Earning Power                                 ║
║    Piotroski F-Score (9-signal scorecard)                            ║
║    Beneish M-Score (earnings manipulation)                           ║
║    Graham Number (sqrt 22.5 × EPS × BVPS — no price)               ║
║    NCAVPS (Net Current Asset Value per Share)                       ║
║    Book Value per Share, EPS (annual), FCF per Share                ║
║    REIT: FFO, AFFO, NTA, WALE, Gearing, Occupancy                   ║
║    Mining: AISC, Reserve Life, Hedging %                             ║
║                                                                      ║
║  Growth (CAGR) — All historical:                                     ║
║    Revenue Growth: 1Y, 3Y, 5Y, 7Y, 10Y, 15Y, 20Y                   ║
║    Profit Growth:  1Y, 3Y, 5Y, 7Y, 10Y, 15Y, 20Y                   ║
║    EPS Growth:     1Y, 3Y, 5Y, 7Y, 10Y, 15Y, 20Y                   ║
║    EBITDA Growth:  3Y, 5Y, 7Y, 10Y                                  ║
║    FCF Growth:     3Y, 5Y, 7Y, 10Y                                  ║
║    Market Cap Growth: 3Y, 5Y, 7Y, 10Y  ← still YEARLY (snapshot)  ║
║                                                                      ║
║  Rolling Averages (pure financial):                                  ║
║    Avg ROE: 3Y, 5Y, 7Y, 10Y                                         ║
║    Avg ROCE: 3Y, 5Y, 7Y, 10Y                                        ║
║    Avg OPM: 5Y, 10Y                                                  ║
║    Avg Dividend: 3Y, 5Y                                              ║
║    Avg Debtor Days: 3Y                                               ║
║    Avg Working Capital Days: 3Y                                      ║
║                                                                      ║
║  After Annual compute: RE-TRIGGER Tier 1 for affected stocks        ║
║  (because EPS changed → PE changes; BVPS changed → PB changes)     ║
║                                                                      ║
║  COMPUTE TIME: ~2–3 hours (full annual season recompute)            ║
╠══════════════════════════════════════════════════════════════════════╣
║                                                                      ║
║  TIER 6: EVENT-TRIGGERED  (Immediately on announcement)             ║
║  ─────────────────────────────────────────────────────────          ║
║  Rule: Corporate actions that change data immediately               ║
║        Cannot wait for scheduled run                                ║
║                                                                      ║
║  Trigger Event        What to recompute                             ║
║  ──────────────────   ─────────────────────────────────────────     ║
║  New results filed  → Tiers 4 or 5 for THAT stock only             ║
║                       Then re-trigger Tier 1 for that stock         ║
║                                                                      ║
║  Capital raise      → shares_outstanding changes                    ║
║                       → EPS, BVPS, all per-share metrics            ║
║                       → PE, PB, PS (denominator changes)            ║
║                       → Rerun Tier 1 for that stock immediately     ║
║                                                                      ║
║  Stock split (e.g.  → Adjust ALL historical prices (split factor)  ║
║  3-for-1 split)       Adjust ALL per-share metrics                  ║
║                       Rerun ALL tiers for that stock                ║
║                                                                      ║
║  Dividend announced → Update dividend record                        ║
║                       Recompute dividend yield for that stock       ║
║                       (Tier 1 update, next daily run OK)            ║
║                                                                      ║
║  Code/name change   → Update company master                         ║
║                       Update all table references                   ║
║                                                                      ║
║  COMPUTE TIME: < 2 min per stock (single-stock recompute)           ║
╚══════════════════════════════════════════════════════════════════════╝
```

---

## Complete Compute Schedule Calendar

```
DAILY (Mon–Fri, trading days only)
  4:00 PM  Market closes
  4:15 PM  Airflow: price_ingest (fetch EOD prices)
  5:00 PM  Airflow: asic_short_data (ASIC short positions)
  5:30 PM  Airflow: compute_tier1 (all price-derived metrics)
              → technical indicators
              → valuation ratios (PE, PB, EV/EBITDA etc.)
              → returns (1D through 5Y rolling)
              → short interest %
              → beta, Sharpe, Sortino
  6:15 PM  Airflow: alert_engine (re-run all screen alerts)
  6:30 PM  Notifications sent to users

WEEKLY (Every Saturday)
  6:00 AM  Airflow: compute_tier2
              → weekly OHLCV aggregates
              → weekly technical (weekly RSI, MACD)
              → market breadth summary
              → sector weekly performance

MONTHLY (1st Saturday of month)
  7:00 AM  Airflow: compute_tier3
              → monthly OHLCV
              → monthly performance summary
              → end-of-month snapshot → computed_metrics_monthly
              → 52W high/low full recalculation
              → all-time high/low refresh

HALF-YEARLY (Event-triggered + scheduled sweep)
  Scheduled sweep: March 1 + September 1 at 1:00 AM
  Event-triggered: Whenever ASX announcement = new_half_year_result
              → half-year P&L metrics for that stock
              → TTM recomputation for that stock
              → THEN trigger Tier 1 recompute for that stock
              → AI: generate half-year results summary

YEARLY (Event-triggered + annual sweep)
  Scheduled sweep: October 1 (after Aug/Sep results season) at 1:00 AM
  Event-triggered: Whenever ASX announcement = new_annual_result
              → all pure financial ratios for that stock
              → all CAGR growth rates for that stock
              → Piotroski, Beneish M-Score
              → THEN trigger Tier 1 recompute for that stock
              → AI: generate annual report summary

EVENT-TRIGGERED (any time, immediate)
  Trigger: ASX announcement = capital_raise
              → update shares_outstanding
              → recompute per-share metrics
              → trigger Tier 1 for that stock
  Trigger: ASX announcement = stock_split
              → adjust historical prices
              → rerun all tiers for that stock
  Trigger: ASX announcement = new_quarterly_activity (miners)
              → update mining metrics (AISC, production)
              → trigger Tier 1 for that stock
```

---

## Compute Engine: Revised Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                  COMPUTE ENGINE — TIERED DESIGN                      │
│                                                                      │
│  compute_tier1.py    (Daily,    ~4 min)                              │
│  compute_tier2.py    (Weekly,   ~10 min)                             │
│  compute_tier3.py    (Monthly,  ~20 min)                             │
│  compute_tier4.py    (HalfYearly, ~45 min — runs on subset)         │
│  compute_tier5.py    (Yearly,   ~2-3 hr — runs on subset)           │
│  compute_event.py    (Immediate, ~2 min per stock)                  │
│                                                                      │
│  shared/                                                             │
│    data_loader.py    (Loads data for any tier)                       │
│    formula_library.py (All metric formulas — single source)         │
│    writer.py         (Bulk write to DB, cache invalidation)          │
│    validator.py      (Post-compute sanity checks)                   │
│                                                                      │
│  KEY DESIGN: formula_library.py is the SINGLE source of truth       │
│  for every formula. Never duplicate formulas across tiers.          │
│  Each tier just calls the same formula with different data inputs.  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Metric Classification Reference Table

```
METRIC                          TIER    REASON
──────────────────────────────────────────────────────────────────────
Current price                   1-D     Raw price data
Market Cap                      1-D     Price × shares
Enterprise Value                1-D     Market cap + debt - cash
PE Ratio (TTM)                  1-D     Price ÷ EPS (hybrid)
PE Ratio Forward                1-D     Price ÷ est.EPS (hybrid)
PB Ratio                        1-D     Price ÷ Book Value (hybrid)
PS Ratio                        1-D     Market Cap ÷ Revenue (hybrid)
PCF Ratio                       1-D     Price ÷ OCF/share (hybrid)
PFCF Ratio                      1-D     Price ÷ FCF/share (hybrid)
EV/EBITDA                       1-D     EV ÷ EBITDA (hybrid)
EV/EBIT                         1-D     EV ÷ EBIT (hybrid)
EV/Sales                        1-D     EV ÷ Revenue (hybrid)
PEG Ratio                       1-D     PE ÷ growth (hybrid)
Earnings Yield                  1-D     EPS ÷ Price (hybrid)
FCF Yield                       1-D     FCF ÷ Market Cap (hybrid)
Dividend Yield                  1-D     DPS ÷ Price (hybrid)
Grossed-up Yield (AUS)          1-D     Grossed-up DPS ÷ Price
Price to NTA (REIT)             1-D     Price ÷ NTA (hybrid)
FFO Yield (REIT)                1-D     FFO ÷ Price (hybrid)
Altman Z-Score                  1-D     Has market cap component
Intrinsic Value vs Price        1-D     Price comparison
Historical PE (3Y avg)          1-D     PE uses today's price
Historical PE (5Y avg)          1-D     PE uses today's price
Historical PE (7Y avg)          1-D     PE uses today's price
Historical PE (10Y avg)         1-D     PE uses today's price
Market Cap to Sales             1-D     Market cap changes daily
Market Cap to Cash Flow         1-D     Market cap changes daily
──────────────────────────────────────────────────────────────────────
DMA 20/50/200                   1-D     Rolling average of prices
RSI 14                          1-D     Rolling price momentum
MACD, Signal, Histogram         1-D     Rolling EMA of prices
ATR 14                          1-D     Rolling volatility
Bollinger Bands (all)           1-D     Rolling std dev of prices
Stochastic RSI                  1-D     RSI of RSI
ADX                             1-D     Directional strength
OBV                             1-D     Cumulative volume×direction
52W High / 52W Low              1-D     Daily rolling window
All-Time High / Low             1-D     Expanding window
% from 52W High/Low/ATH/ATL     1-D     Uses today's price
Range Position (52W)            1-D     Position within range
Golden/Death Cross              1-D     DMA comparison
Above DMA 50/200                1-D     Boolean price vs DMA
Volume (all metrics)            1-D     Daily volume data
Return 1D, 1W, 1M, 3M, 6M      1-D     Rolling returns
Return 1Y, 3Y, 5Y               1-D     Rolling returns (CAGR)
Beta (1Y, 3Y)                   1-D     Rolling regression
Sharpe Ratio (1Y)               1-D     Rolling risk-adjusted
Sortino Ratio (1Y)              1-D     Rolling downside-adj
Max Drawdown (1Y, 3Y)           1-D     Rolling peak-to-trough
Short Interest %                1-D     ASIC daily data
Short Interest Change (1W, 1M)  1-D     Rolling change
──────────────────────────────────────────────────────────────────────
Weekly OHLCV                    2-W     Weekly aggregation
Weekly RSI                      2-W     Weekly candles
Weekly MACD                     2-W     Weekly candles
Sector weekly return            2-W     Weekly summary
──────────────────────────────────────────────────────────────────────
Monthly OHLCV                   3-M     Monthly aggregation
Monthly RSI                     3-M     Monthly candles
Monthly MACD                    3-M     Monthly candles
Monthly snapshot (all ratios)   3-M     Point-in-time snapshot
52W recalculation (full)        3-M     Full rolling window check
──────────────────────────────────────────────────────────────────────
TTM Revenue / EBITDA / PAT      4-HY    Updates with H1/H2 results
TTM EPS / OCF / FCF             4-HY    Updates with H1/H2 results
Half-year P&L metrics           4-HY    From half-year report
QoQ growth (revenue, profit)    4-HY    H1 vs H2 vs prior year
Operating leverage              4-HY    Revenue vs profit growth
Half-year OPM / NPM             4-HY    Margin this half
Mining QAR metrics (production) 4-HY    Quarterly activity report
AISC per oz                     4-HY    Quarterly activity report
Production vs guidance          4-HY    Quarterly comparison
──────────────────────────────────────────────────────────────────────
ROE, ROA, ROCE, ROIC, CROIC     5-Y     Annual P&L + BS (no price)
OPM, NPM, GPM, EBITDA Margin    5-Y     Annual P&L ratios
Asset Turnover                  5-Y     Annual (no price)
Inventory Turnover              5-Y     Annual
Debtor Days (DSO)               5-Y     Annual
Days Payable (DPO)              5-Y     Annual
Days Inventory (DIO)            5-Y     Annual
Cash Conversion Cycle (CCC)     5-Y     Annual
Working Capital Days            5-Y     Annual
Interest Coverage               5-Y     EBIT ÷ Interest (annual)
Current Ratio                   5-Y     Annual BS
Quick Ratio                     5-Y     Annual BS
Cash Ratio                      5-Y     Annual BS
Debt to Equity                  5-Y     Annual BS
Net Debt/EBITDA                 5-Y     Annual
Leverage Ratio                  5-Y     Annual BS
Piotroski F-Score               5-Y     Annual financial signals
Beneish M-Score                 5-Y     Annual financial signals
Graham Number                   5-Y     EPS × BVPS (no price)
NCAVPS                          5-Y     Current assets - liabilities
Book Value per Share            5-Y     Annual BS
EPS (annual)                    5-Y     Annual P&L
FCF per Share                   5-Y     Annual CF
OCF per Share                   5-Y     Annual CF
Earning Power                   5-Y     EBIT ÷ Assets (annual)
FFO (REIT absolute)             5-Y     Annual REIT data
AFFO (REIT)                     5-Y     Annual REIT data
NTA per unit (REIT)             5-Y     Annual REIT BS
WALE (REIT)                     5-Y     Annual REIT data
Gearing (REIT)                  5-Y     Annual REIT BS
Occupancy % (REIT)              5-Y     Annual REIT data
Revenue Growth 1Y/3Y/5Y/7Y/10Y  5-Y     Annual CAGR
Profit Growth 1Y/3Y/5Y/7Y/10Y   5-Y     Annual CAGR
EPS Growth 1Y/3Y/5Y/7Y/10Y      5-Y     Annual CAGR
EBITDA Growth 3Y/5Y/7Y/10Y      5-Y     Annual CAGR
FCF Growth 3Y/5Y/7Y/10Y         5-Y     Annual CAGR
Avg ROE 3Y/5Y/7Y/10Y            5-Y     Rolling annual avg
Avg ROCE 3Y/5Y/7Y/10Y           5-Y     Rolling annual avg
Avg OPM 5Y/10Y                  5-Y     Rolling annual avg
Avg Dividend 3Y/5Y              5-Y     Rolling annual avg
Avg Debtor Days 3Y              5-Y     Rolling annual avg
Revenue Growth 15Y/20Y          5-Y     Annual CAGR (long-term)
Profit Growth 15Y/20Y           5-Y     Annual CAGR (long-term)
──────────────────────────────────────────────────────────────────────
Shares outstanding change        6-E    Capital raise event
EPS (restated for capital raise) 6-E    Capital raise event
BVPS (restated)                  6-E    Capital raise event
Price-adjusted history           6-E    Stock split event
All per-share metrics (split)    6-E    Stock split event
```

---

## Impact on Compute Engine Performance

```
WITH YOUR TIERED APPROACH:

  Daily run (Tier 1 only):
    Metrics per stock:  ~85 (down from 544)
    Stocks:             2,200
    Run time:           3–5 minutes  ✅  (was 20 min)
    DB rows written:    2,200 (only today's row)

  Weekly run (Tier 2 only):
    Metrics per stock:  ~15
    Run time:           5–10 minutes

  Monthly run (Tier 3):
    Metrics per stock:  ~20 + snapshot
    Run time:           15–20 minutes

  Half-Year run (Tier 4):
    Metrics per stock:  ~45 (only for stocks that reported)
    Typical season:     ~600 stocks in Feb, ~800 stocks in Aug
    Run time:           20–30 minutes

  Annual run (Tier 5):
    Metrics per stock:  ~200 (all fundamental + growth)
    Run time:           1.5–2 hours
    Frequency:          Once a year (August sweep)

  Event-triggered (Tier 6):
    Single stock:       All applicable tiers
    Run time:           < 2 minutes per stock
    Frequency:          10–30 events per day on average

TOTAL DAILY COMPUTE COST REDUCTION:
  Before: 544 metrics × 2,200 stocks = 20 min daily
  After:   85 metrics × 2,200 stocks =  4 min daily  ← 80% faster
```

---

## The Dependency Chain (Order of Execution Within Each Tier)

```
WITHIN TIER 1 (Daily run — must run in this order):

  Step 1: Fetch today's prices → daily_prices table
  Step 2: Compute moving averages (DMA, EMA) — need price history
  Step 3: Compute MACD (uses EMA 12 and EMA 26 from Step 2)
  Step 4: Compute RSI (uses price changes)
  Step 5: Compute ATR, Bollinger (uses high/low/close)
  Step 6: Compute 52W levels, returns (uses price history)
  Step 7: Compute Market Cap, EV (needs today's price from Step 1)
  Step 8: Compute valuation ratios: PE, PB, EV/EBITDA etc.
          (needs Market Cap/EV from Step 7 + annual financials)
  Step 9: Compute yields (Dividend yield, FCF yield, etc.)
  Step 10: Compute Beta, Sharpe, Sortino (needs return series from Step 6)
  Step 11: Compute Altman Z-Score (needs Market Cap from Step 7)
  Step 12: Write to computed_metrics, invalidate Redis cache

WITHIN TIER 5 (Annual run — must run in this order):

  Step 1: Ingest new annual financials → annual_pnl, annual_bs, annual_cf
  Step 2: Compute pure financial ratios (ROE, ROA, margins, etc.)
  Step 3: Compute CAGR growth rates (needs multi-year history from Step 1)
  Step 4: Compute Piotroski (needs current + prior year from Steps 1-2)
  Step 5: Compute Beneish M-Score (needs multi-year from Step 1)
  Step 6: Compute averages (Avg ROE 3Y/5Y/10Y etc.)
  Step 7: Write to annual_computed (separate table from daily)
  Step 8: TRIGGER TIER 1 for all stocks with new annual data
          (because EPS changed → PE changed → must update immediately)
```

---

## Database Table Structure to Support Tiered Compute

```sql
-- Tier 1 results: one row per stock per trading day
-- (replaces single computed_metrics table with tiered tables)

CREATE TABLE market.metrics_daily (
    time        TIMESTAMPTZ NOT NULL,  -- TimescaleDB hypertable
    asx_code    VARCHAR(10) NOT NULL,
    -- ~85 columns: all price-derived metrics
    -- technical indicators, valuation ratios, returns
    PRIMARY KEY (time, asx_code)
);
SELECT create_hypertable('market.metrics_daily', 'time',
    chunk_time_interval => INTERVAL '1 month');
SELECT add_compression_policy('market.metrics_daily', INTERVAL '3 months');
-- Size: ~400 MB/year uncompressed → ~50 MB/year compressed

CREATE TABLE market.metrics_weekly (
    week_start  DATE NOT NULL,
    asx_code    VARCHAR(10) NOT NULL,
    -- ~15 columns: weekly aggregates
    PRIMARY KEY (week_start, asx_code)
);
-- Size: ~10 MB/year

CREATE TABLE market.metrics_monthly (
    month_start DATE NOT NULL,
    asx_code    VARCHAR(10) NOT NULL,
    -- ~600 columns: full snapshot of ALL metrics at month end
    -- This is for historical backtesting
    PRIMARY KEY (month_start, asx_code)
);
-- Size: ~200 MB/year

CREATE TABLE market.metrics_annual (
    fiscal_year INTEGER NOT NULL,
    asx_code    VARCHAR(10) NOT NULL,
    -- ~200 columns: all pure fundamental ratios + CAGR
    -- One row per stock per year — permanent record
    PRIMARY KEY (fiscal_year, asx_code)
);
-- Size: ~5 MB/year (tiny — only 2,200 rows per year)

CREATE TABLE market.compute_log (
    id           BIGSERIAL PRIMARY KEY,
    tier         SMALLINT NOT NULL,      -- 1,2,3,4,5,6
    asx_code     VARCHAR(10),            -- NULL = all stocks
    triggered_by VARCHAR(50),            -- 'schedule', 'announcement_id'
    started_at   TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    stocks_processed INTEGER,
    status       VARCHAR(20),
    error_msg    TEXT
);
```

---

## Summary: Your Strategy + Refinements

```
╔══════════════════════════════════════════════════════════════════════╗
║  YOUR ORIGINAL IDEA → REFINED FRAMEWORK                              ║
╠══════════════════════════════════════════════════════════════════════╣
║                                                                      ║
║  Your Idea          Refined Version          Key Addition            ║
║  ────────────────   ──────────────────────   ──────────────────────  ║
║  Daily → Daily    = Tier 1 (Daily)           Add: ALL price-hybrid  ║
║                                              metrics here too        ║
║  Weekly → Weekly  = Tier 2 (Weekly)          ✅ Same                ║
║  Monthly→ Monthly = Tier 3 (Monthly)         Add: monthly snapshot  ║
║  HalfYearly→HY    = Tier 4 (Half-Yearly)     Add: TTM recompute +  ║
║                                              re-trigger Tier 1      ║
║  Yearly → Yearly  = Tier 5 (Yearly)          Add: re-trigger Tier 1 ║
║  [MISSING]        = Tier 6 (Event-Triggered) Critical for capital  ║
║                                              raises, splits, results ║
║                                                                      ║
║  The core insight you were missing:                                  ║
║  PE, PB, EV/EBITDA etc. use annual financials BUT must recompute    ║
║  daily because PRICE (the numerator/denominator) changes daily.     ║
║                                                                      ║
║  Rule of thumb:  "Does the formula contain price or market cap?"    ║
║                  YES → Tier 1 (Daily)                                ║
║                  NO  → Tier 4/5 (when financial data changes)       ║
╚══════════════════════════════════════════════════════════════════════╝
```
