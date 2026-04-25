# ASX Screener — Master Metric Compute Tags Reference

> Version 1.0 | April 2026
> Definitive reference: WHEN each metric is computed and WHY

---

## 1. Compute Tag Definitions

```
TAG   FULL NAME         RUNS WHEN                    FREQUENCY
───   ─────────────────────────────────────────────────────────
D   = Daily            Every ASX trading day          ~252/yr
W   = Weekly           Every Friday close (weekend)   ~52/yr
M   = Monthly          Last trading day of month      12/yr
Q   = Quarterly        Jan/Apr/Jul/Oct (mining QARs)  4/yr
HY  = Half-Yearly      Feb & Aug results season       2/yr
Y   = Yearly           Aug/Sep/Oct annual results     1/yr
E   = Event-Triggered  Immediately on corporate event Varies
```

---

## 2. The Cascading Schedule (Rollup Logic)

```
Your logic is exactly right:

  DAILY RUN (Mon–Fri):         compute all  D
  WEEKEND RUN (Saturday):      compute all  D  +  W
  MONTH-END RUN:               compute all  D  +  W  +  M
  QUARTERLY RUN (mining):      compute all  D  +  W  +  M  +  Q
  HALF-YEAR RUN (Feb/Aug):     compute all  D  +  W  +  M  +  Q  +  HY
  YEAR-END RUN (Oct sweep):    compute all  D  +  W  +  M  +  Q  +  HY  +  Y
  EVENT RUN (immediate):       compute all  E  → then re-run D for that stock

WHY THE ROLLUP MAKES SENSE:
  ┌──────────────────────────────────────────────────────────────┐
  │ Monthly RSI needs this month's weekly candles (W)           │
  │ → Month-end batch must run W before M                       │
  │                                                              │
  │ CAGR metrics need the latest annual financials (Y)          │
  │ → Year-end batch must run HY before Y (TTM feeds into Y)   │
  │                                                              │
  │ After Y runs → D must re-run for hybrid price metrics       │
  │ (new EPS → PE ratio must update same day)                   │
  └──────────────────────────────────────────────────────────────┘

CASCADING EXECUTION ORDER within each batch:
  Always:  D → W → M → Q → HY → Y
  Never run a higher tier before completing the lower tier(s) first.
```

---

## 3. Multiple Compute Tags — Explained

```
Some metrics have MULTIPLE tags because they have:
  (a) A base data component   → updated on one schedule
  (b) A price component       → updated daily

  Example: Dividend Yield = Annual Dividend ÷ Current Price
    Dividend (source): changes when new dividend announced  → E tag
    Price (source):    changes every trading day            → D tag
    → Dividend Yield needs BOTH: D (daily recompute) + E (on dividend event)

TAG COMBINATIONS USED:
  D       = Pure price/technical metric (no financials)
  Y       = Pure annual fundamental (no price)
  HY      = Pure half-year fundamental (no price)
  Q       = Pure quarterly (mining QAR data)
  D+HY    = Uses price (daily) + TTM from half-year financials
  D+Y     = Uses price (daily) + annual financials
  D+Y+E   = Daily price + annual data + immediate on corporate event
  Y+E     = Annual compute + immediate on new annual results
  HY+E    = Half-year compute + immediate on new HY results
  Q+E     = Quarterly compute + immediate on new QAR
  W       = Weekly aggregate of daily data
  M       = Monthly aggregate of daily/weekly data
```

---

## 4. Complete Metric Compute Tags — All 544+ Metrics

### 4.1 PRICE & TECHNICAL METRICS

```
METRIC                              TAG     REASON
──────────────────────────────────────────────────────────────────
Current price                       D       EOD price from exchange
High price (day)                    D       Daily from price feed
Low price (day)                     D       Daily from price feed
Volume                              D       Daily from price feed
Value traded (AUD)                  D       Daily from price feed
VWAP                                D       Daily computation
Return over 1 day                   D       (Today - Yesterday) / Yesterday
Return over 1 week                  D       Rolling 5-day window (shifts daily)
Return over 1 month                 D       Rolling 21-day window
Return over 3 months                D       Rolling 63-day window
Return over 6 months                D       Rolling 126-day window
Return over 1 year                  D       Rolling 252-day window
Return over 3 years (CAGR)          D       Rolling 756-day CAGR
Return over 5 years (CAGR)          D       Rolling 1260-day CAGR
DMA 50                              D       50-day moving average (rolling)
DMA 200                             D       200-day moving average (rolling)
DMA 20                              D       20-day moving average
DMA 50 previous day                 D       Yesterday's DMA50 (for crossover)
DMA 200 previous day                D       Yesterday's DMA200
EMA 12                              D       12-period EWM
EMA 26                              D       26-period EWM
50DMA Ratio                         D       Price / DMA50
200DMA Ratio                        D       Price / DMA200
MACD                                D       EMA12 - EMA26
MACD Signal                         D       9-period EWM of MACD
MACD Histogram                      D       MACD - Signal
MACD Previous Day                   D       Yesterday's MACD
MACD Signal Previous Day            D       Yesterday's Signal
RSI (14)                            D       14-period RSI
Stochastic RSI                      D       RSI of RSI
ADX (14)                            D       Average Directional Index
ATR (14)                            D       Average True Range
Bollinger Upper (20,2)              D       20DMA + 2×StdDev
Bollinger Lower (20,2)              D       20DMA - 2×StdDev
Bollinger Mid (20)                  D       20-day MA
Bollinger % Position                D       (Price-Lower)/(Upper-Lower)
Historical Volatility (20D)         D       Annualised 20-day log return StdDev
Volume 1 week average               D       5-day rolling avg volume
Volume 1 month average              D       21-day rolling avg volume
Volume Ratio                        D       Today / 20D avg volume
OBV (On-Balance Volume)             D       Cumulative vol × price direction
High price 52 weeks                 D       Rolling 252-day high
Low price 52 weeks                  D       Rolling 252-day low
High price all time                 M       Full history high (monthly refresh)
Low price all time                  M       Full history low (monthly refresh)
Dis from 52w High                   D       (Price / 52W High) - 1
Dis from 52w Low                    D       (Price / 52W Low) - 1
Dis from All Time High              D       (Price / ATH) - 1
Dis from All Time Low               D       (Price / ATL) - 1
52W Index (range position)          D       (P - 52WL) / (52WH - 52WL)
52WHvsALLTIME                       D       52W High / All-Time High
AlltimeHvs52WH                      D       All-Time High / 52W High
Up from 52w low                     D       % above 52W low
Down from 52w high                  D       % below 52W high
From 52w high                       D       Distance from 52W high
New 52W High (signal)               D       Boolean: today = 52W high
New 52W Low (signal)                D       Boolean: today = 52W low
Golden Cross (signal)               D       DMA50 crossed above DMA200 today
Death Cross (signal)                D       DMA50 crossed below DMA200 today
Above DMA 50 (boolean)              D       Price > DMA50
Above DMA 200 (boolean)             D       Price > DMA200
Beta (1 year)                       D       Rolling 252-day vs XJO
Beta (3 year)                       D       Rolling 756-day vs XJO
Is SME                              Y+E     Static company attribute
Is not SME                          Y+E     Static company attribute

── WEEKLY AGGREGATES ─────────────────────────────────────────────
Weekly Open / High / Low / Close    W       Week's OHLCV
Weekly Volume                       W       Sum of week's volume
Weekly Return %                     W       Friday close vs prev Friday close
Weekly RSI                          W       RSI on weekly candles
Weekly MACD                         W       MACD on weekly candles
Weekly MACD Signal                  W       MACD signal on weekly candles
Weekly Volume vs 4W avg             W       This week vs 4-week avg

── MONTHLY AGGREGATES ────────────────────────────────────────────
Monthly Open / High / Low / Close   M       Month's OHLCV
Monthly Volume                      M       Sum of month's volume
Monthly Return %                    M       Month close vs prior month close
Monthly RSI                         M       RSI on monthly candles
Monthly MACD                        M       MACD on monthly candles
```

---

### 4.2 VALUATION RATIOS (Price × Financial Data — mostly D+Y or D+HY)

```
METRIC                              TAG     REASON
──────────────────────────────────────────────────────────────────
Market Capitalization               D       Price × shares (price changes daily)
Enterprise Value                    D       Market Cap + Debt - Cash
Number of equity shares             Y+E     From annual BS; changes on raise/split
Face value                          Y+E     From company master; rarely changes

Price to Earning (PE TTM)           D+HY    Price changes daily; EPS from TTM
PE Ratio (annual)                   D+Y     Price daily; annual EPS yearly
Price to Quarterly Earning          D+HY    Price daily; half-year EPS → HY
Forward PE                          D+Y     Price daily; forward EPS yearly
Industry PE                         D       Avg PE of GICS industry (price-based)
Industry PBV                        D       Avg PBV of GICS industry
Historical PE 3Y avg                Y       Avg of past 3 year-end PE values
Historical PE 5Y avg                Y       Avg of past 5 year-end PE values
Historical PE 7Y avg                Y       Avg of past 7 year-end PE values
Historical PE 10Y avg               Y       Avg of past 10 year-end PE values

Price to book value (PB)            D+Y     Price daily; Book Value annual
Book value                          Y+E     From annual BS; updates annually
Book value preceding year           Y       Prior year's annual BS
Book value 3 years back             Y       3yr ago annual BS
Book value 5 years back             Y       5yr ago annual BS
Book value 10 years back            Y       10yr ago annual BS
BVvsCMP                             D+Y     Book Value vs Current Market Price

Price to Sales (PS)                 D+HY    Price daily; Revenue TTM
Price to Cash Flow (PCF)            D+HY    Price daily; OCF TTM
Price to Free Cash Flow (PFCF)      D+HY    Price daily; FCF TTM
Free Cash Flow Yield                D+HY    FCF TTM / Market Cap
Market Capt to Cash Flow            D+HY    Market Cap / OCF TTM
Price to Sales (Market Cap/Sales)   D+HY    Market Cap / Revenue TTM
SalesP                              D+HY    Sales / Price (inverse of PS)

EV/EBITDA                           D+HY    EV daily; EBITDA from TTM
EV/EBIT                             D+HY    EV daily; EBIT from TTM
Enterprise Value to EBIT            D+HY    Same as above
EV/Sales                            D+HY    EV daily; Revenue TTM

Earnings yield                      D+HY    EPS TTM / Price
PEG Ratio                           D+Y     PE / EPS growth rate (annual)
InvestR                             D+Y     Investment return ratio

Dividend yield                      D+E     Annual div / Price; D=price, E=new div
Grossed-up Yield (AUS franking)     D+E     Grossed-up div / Price
Dividend Payout Ratio               HY+Y    Dividends paid / Net Profit
Average 5years dividend             Y       Rolling 5yr avg DPS
Average dividend payout 3years      Y       Rolling 3yr avg payout ratio

Market Cap to Sales                 D+HY    Market Cap / Revenue TTM
Market Cap to quarterly profit      D+HY    Market Cap / HY Profit
EVEBITDA                            D+HY    EV / EBITDA TTM (same as EV/EBITDA)

Graham Number                       Y       sqrt(22.5 × EPS × BVPS) — no price
Graham (Graham Number metric)       Y       Same formula
NCAVPS                              Y       (Current Assets - Total Liab) / Shares
Intrinsic Value                     Y       EPS × (8.5 + 2×growth)
```

---

### 4.3 PROFITABILITY RATIOS

```
METRIC                              TAG     REASON
──────────────────────────────────────────────────────────────────
Return on equity (ROE)              Y       Net Profit / Equity — annual only
Return on assets (ROA)              Y       Net Profit / Assets — annual only
Return on capital employed (ROCE)   Y       EBIT / Capital Employed — annual
Return on invested capital (ROIC)   Y       NOPAT / Invested Capital — annual
CROIC                               Y       FCF / Invested Capital — annual
Earning Power                       Y       EBIT / Total Assets — annual

OPM (Operating Profit Margin)       HY+Y    EBIT / Revenue — updates each result
NPM (Net Profit Margin)             HY+Y    Net Profit / Revenue
GPM (Gross Profit Margin)           HY+Y    Gross Profit / Revenue
EBITDA Margin                       HY+Y    EBITDA / Revenue
EBIT Margin                         HY+Y    EBIT / Revenue

Average return on equity 3Y         Y       3yr rolling avg ROE
Average return on equity 5Y         Y       5yr rolling avg ROE
Average return on equity 7Y         Y       7yr rolling avg ROE
Average return on equity 10Y        Y       10yr rolling avg ROE
Return on equity 5years growth      Y       ROE CAGR over 5 years
Return on assets 3years             Y       3yr rolling avg ROA
Return on assets 5years             Y       5yr avg ROA
Average return on capital employed 3Y  Y    3yr avg ROCE
Average return on capital employed 5Y  Y    5yr avg ROCE
Average return on capital employed 7Y  Y    7yr avg ROCE
Average return on capital employed 10Y Y    10yr avg ROCE
ROCE3yr avg                         Y       Same as above (3yr)
OPM 5Year                           Y       5yr avg OPM
OPM 10Year                          Y       10yr avg OPM
```

---

### 4.4 EFFICIENCY RATIOS

```
METRIC                              TAG     REASON
──────────────────────────────────────────────────────────────────
Asset Turnover Ratio                Y       Revenue / Total Assets — annual
Inventory turnover ratio            Y       COGS / Avg Inventory — annual
Receivables Turnover                Y       Revenue / Receivables — annual
Payables Turnover                   Y       Purchases / Payables — annual
Working Capital Turnover            Y       Revenue / Working Capital — annual

Debtor days (DSO)                   Y       Receivables / (Revenue/365) — annual
Days Receivable Outstanding         Y       Same as Debtor Days
Days Payable Outstanding (DPO)      Y       Payables / (Revenue/365) — annual
Days Inventory Outstanding (DIO)    Y       Inventory / (Revenue/365) — annual
Cash Conversion Cycle (CCC)         Y       DSO + DIO - DPO — annual
Working Capital Days                Y       Working Capital / (Revenue/365)

Average debtor days 3years          Y       3yr rolling avg DSO
Debtor days 3years back             Y       DSO from 3 years ago
Debtor days 5years back             Y       DSO from 5 years ago
Average Working Capital Days 3years Y       3yr rolling avg WC days

Inventory turnover ratio 3Y back    Y       Inv turnover from 3yr ago
Inventory turnover ratio 5Y back    Y       Inv turnover from 5yr ago
Inventory turnover ratio 7Y back    Y       Inv turnover from 7yr ago
Inventory turnover ratio 10Y back   Y       Inv turnover from 10yr ago
```

---

### 4.5 LEVERAGE & FINANCIAL HEALTH

```
METRIC                              TAG     REASON
──────────────────────────────────────────────────────────────────
Debt to equity                      Y+E     Total Debt / Equity — annual + on raise
Net Debt to Equity                  Y+E     Net Debt / Equity
Debt to Assets                      Y       Total Debt / Total Assets — annual
Net Debt to EBITDA                  HY+Y    Net Debt / EBITDA TTM
Financial leverage                  Y       Total Assets / Equity — annual
Leverage                            Y       Same as above
Interest Coverage Ratio             HY+Y    EBIT / Interest — TTM
Interest Coverage                   HY+Y    Same
DRATIO                              Y       Debt Ratio = Total Debt / Assets
Working Capital to Sales ratio      HY+Y    Working Capital / Revenue TTM
Debt Capacity                       Y       Computed from FCF coverage
Debt To Profit                      HY+Y    Total Debt / Net Profit TTM
Total Capital Employed              Y       Equity + Long-term Debt — annual
debtplus                            Y       Debt + Contingent Liabilities
Net worth                           Y       Equity Capital + Reserves
Mkt Cap To Debt Cap                 D+Y     Market Cap / Total Debt
cash debt contingent liab by mcap   D+Y     (Cash - Debt - Cont.Liab) / MCap
Cash by market cap                  D+Y     Cash Equivalents / Market Cap

Current ratio                       Y+E     Current Assets / Current Liab — annual
Quick ratio                         Y+E     (CA - Inventory) / CL — annual
Cash Ratio                          Y+E     Cash / Current Liabilities — annual
```

---

### 4.6 GROWTH METRICS

```
METRIC                              TAG     REASON
──────────────────────────────────────────────────────────────────
── ANNUAL P&L GROWTH (computed once per year) ─────────────────────
Sales growth 3Years (Revenue CAGR)  Y       3yr CAGR from annual P&L
Sales growth 5Years                 Y       5yr CAGR
Sales growth 7Years                 Y       7yr CAGR
Sales growth 10Years                Y       10yr CAGR
Sales growth 10years median         Y       Median annual growth over 10yr
Sales growth 5years median          Y       Median annual growth over 5yr

Profit growth 3Years                Y       Net Profit 3yr CAGR
Profit growth 5Years                Y       Net Profit 5yr CAGR
Profit growth 7Years                Y       Net Profit 7yr CAGR
Profit growth 10Years               Y       Net Profit 10yr CAGR

EPS growth 3Years                   Y       EPS 3yr CAGR
EPS growth 5Years                   Y       EPS 5yr CAGR
EPS growth 7Years                   Y       EPS 7yr CAGR
EPS growth 10Years                  Y       EPS 10yr CAGR

EBIDT growth 3Years                 Y       EBITDA 3yr CAGR
EBIDT growth 5Years                 Y       EBITDA 5yr CAGR
EBIDT growth 7Years                 Y       EBITDA 7yr CAGR
EBIDT growth 10Years                Y       EBITDA 10yr CAGR

── HALF-YEAR / PERIOD GROWTH ──────────────────────────────────────
Sales growth (period-on-period)     HY      H1 vs H1 prior year (YoY)
Profit growth (period-on-period)    HY      H1 vs H1 prior year (YoY)
QoQ Profits                         HY      H1 vs H2 (sequential)
QoQ Sales                           HY      H1 vs H2 (sequential)
YOY Quarterly sales growth          HY      Current HY vs same HY last year
YOY Quarterly profit growth         HY      Current HY vs same HY last year
Operating profit growth             HY      Current vs prior HY
Sales preceding 12months            HY      TTM Revenue
Net profit preceding 12months       HY      TTM Net Profit
Expected quarterly sales growth     HY+Y    Analyst consensus estimate
Expected quarterly sales            HY+Y    Forward estimate
Expected quarterly operating profit HY+Y    Forward estimate
Expected quarterly net profit       HY+Y    Forward estimate
Expected quarterly EPS              HY+Y    Forward estimate

── MARKET CAP GROWTH (uses historical market cap snapshots) ────────
Market Capitalization 3years back   M       Stored from monthly snapshot
Market Capitalization 5years back   M       Stored from monthly snapshot
Market Capitalization 7years back   M       Stored from monthly snapshot
Market Capitalization 10years back  M       Stored from monthly snapshot
(Growth rate computed from these snapshots)

── CHANGE IN HOLDINGS ─────────────────────────────────────────────
Change in promoter holding          HY+Y    From annual/HY shareholder data
Change in promoter holding 3Years   Y       3yr change in director holding
Change in FII holding               HY      Institutional holding HY change
Change in FII holding 3Years        Y       3yr change in institutional
Change in DII holding               HY      Domestic inst. holding HY change
Change in DII holding 3Years        Y       3yr change in domestic inst.
```

---

### 4.7 CASH FLOW METRICS

```
METRIC                              TAG     REASON
──────────────────────────────────────────────────────────────────
── RECENT (TTM / LAST YEAR) ────────────────────────────────────────
Cash from operations last year      Y+HY    From annual + TTM update
Free cash flow last year            Y+HY    CFO - Capex — annual + TTM
Cash from investing last year       Y+HY    Annual + TTM
Cash from financing last year       Y+HY    Annual + TTM
Net cash flow last year             Y+HY    Annual + TTM
Cash beginning of last year         Y       From annual CF statement
Cash end of last year               Y       From annual CF statement
Free Cash Flow (FCF) per Share      Y+HY    FCF / Shares — annual + TTM
OCF / Net Income (Quality ratio)    Y+HY    Cash earnings quality
OCF Margin                          Y+HY    OCF / Revenue

── PRECEDING YEAR ──────────────────────────────────────────────────
Cash from operations preceding year Y       From prior annual CF
Free cash flow preceding year       Y       Prior year FCF
Cash from investing preceding year  Y       Prior annual CF
Cash from financing preceding year  Y       Prior annual CF
Net cash flow preceding year        Y       Prior annual CF
Cash beginning of preceding year    Y       Prior annual CF
Cash end of preceding year          Y       Prior annual CF

── HISTORICAL (MULTI-YEAR CAGR / AVERAGES) ─────────────────────────
Free cash flow 3 years              Y       FCF 3yr CAGR
Free cash flow 5 years              Y       FCF 5yr CAGR
Free cash flow 7 years              Y       FCF 7yr CAGR
Free cash flow 10 years             Y       FCF 10yr CAGR
Operating cash flow 3 years         Y       OCF 3yr CAGR
Operating cash flow 5 years         Y       OCF 5yr CAGR
Operating cash flow 7 years         Y       OCF 7yr CAGR
Operating cash flow 10 years        Y       OCF 10yr CAGR
Investing cash flow 3/5/7/10 years  Y       Investing CF CAGR
Cash 3 Years back                   Y       Closing cash 3yr ago
Cash 5 Years back                   Y       Closing cash 5yr ago
Cash 7 Years back                   Y       Closing cash 7yr ago
Capex to Sales                      Y+HY    Capex / Revenue — annual + TTM
OCF to Debt                         Y+HY    OCF / Total Debt — annual + TTM
```

---

### 4.8 ANNUAL P&L METRICS

```
METRIC                              TAG     REASON
──────────────────────────────────────────────────────────────────
Sales (Revenue) — current year      HY+Y    Computed from TTM / annual
Operating profit — current          HY+Y    From TTM / annual
EBIT — current                      HY+Y    TTM EBIT
EBIDT — current                     HY+Y    TTM EBITDA
Depreciation — current              HY+Y    TTM Depreciation
Interest — current                  HY+Y    TTM Interest
Other income — current              HY+Y    TTM Other Income
Profit before tax — current         HY+Y    TTM PBT
Tax — current                       HY+Y    TTM Tax
Current Tax                         HY+Y    Current portion of tax
Profit after tax — current          HY+Y    TTM PAT
Extraordinary items — current       HY+Y    TTM extraordinary items
Net Profit — current                HY+Y    TTM Net Profit
EPS — current                       HY+Y    TTM EPS
OPM — current                       HY+Y    TTM Operating Margin
NPM — current                       HY+Y    TTM Net Margin
Return on capital employed          Y       Annual ROCE
Change in promoter holding          HY      HY update

── LAST YEAR ─────────────────────────────────────────────────────
Sales last year                     Y       Prior fiscal year revenue
Operating profit last year          Y       Prior year EBIT
Other income last year              Y       Prior year
EBIDT last year                     Y       Prior year EBITDA
Depreciation last year              Y       Prior year
EBIT last year                      Y       Prior year
Interest last year                  Y       Prior year
Profit before tax last year         Y       Prior year PBT
Tax last year                       Y       Prior year tax
Profit after tax last year          Y       Prior year PAT
Extraordinary items last year       Y       Prior year
Net Profit last year                Y       Prior year net profit
Dividend last year                  Y       Prior year dividends paid
Material cost last year             Y       Prior year material cost
Employee cost last year             Y       Prior year employee cost
OPM last year                       Y       Prior year OPM
NPM last year                       Y       Prior year NPM
EPS last year                       Y       Prior year EPS

── PRECEDING YEAR ────────────────────────────────────────────────
Sales preceding year                Y       2 years back P&L
Operating profit preceding year     Y       2yr back
[all preceding year fields]         Y       Same pattern: 2yr back

── HISTORICAL ────────────────────────────────────────────────────
Average Earnings 5Year              Y       Avg Net Profit 5yr
Average Earnings 10Year             Y       Avg Net Profit 10yr
Average EBIT 5Year                  Y       Avg EBIT 5yr
Average EBIT 10Year                 Y       Avg EBIT 10yr

TTM Result Date                     HY+Y    Date of most recent result
Last annual result date             Y       Date of last full-year result
```

---

### 4.9 HALF-YEAR / QUARTERLY P&L METRICS
*(Note: ASX = Half-Yearly reporting. "Quarter" below = Half-Year for most ASX stocks)*

```
METRIC                              TAG     REASON
──────────────────────────────────────────────────────────────────
Sales latest quarter (H1/H2)        HY      From latest half-year result
Profit after tax latest quarter     HY      Latest HY PAT
Operating profit latest quarter     HY      Latest HY EBIT
Other income latest quarter         HY      Latest HY
EBIDT latest quarter                HY      Latest HY EBITDA
Depreciation latest quarter         HY      Latest HY
EBIT latest quarter                 HY      Latest HY EBIT
Interest latest quarter             HY      Latest HY
Profit before tax latest quarter    HY      Latest HY PBT
Tax latest quarter                  HY      Latest HY
Extraordinary items latest quarter  HY      Latest HY
Net Profit latest quarter           HY      Latest HY Net Profit
Equity Capital latest quarter       HY+E    Latest HY; E=capital raise
GPM latest quarter                  HY      Gross margin latest HY
OPM latest quarter                  HY      Operating margin latest HY
NPM latest quarter                  HY      Net margin latest HY
EPS latest quarter                  HY      EPS for latest HY

Sales 2 quarters back               HY      Prior HY revenue
Sales 3 quarters back               HY      3rd prior HY (1.5yr back)
Operating profit 2 quarters back    HY      Prior HY EBIT
Operating profit 3 quarters back    HY      3rd prior HY
Net profit 2 quarters back          HY      Prior HY profit
Net profit 3 quarters back          HY      3rd prior HY

YOY Quarterly sales growth          HY      vs same HY last year
YOY Quarterly profit growth         HY      vs same HY last year
Sales growth (H-o-H)                HY      vs prior HY
Profit growth (H-o-H)               HY      vs prior HY
Operating profit growth             HY      EBIT vs prior HY
QoQ Profits (sequential)            HY      H1 vs H2
QoQ Sales (sequential)              HY      H1 vs H2

Last result date                    HY      Date of most recent HY result

── PRECEDING HALF ────────────────────────────────────────────────
Sales preceding quarter             HY      Previous half-year revenue
Operating profit preceding quarter  HY      Previous HY EBIT
[all preceding quarter fields]      HY      Same pattern

── FORWARD ESTIMATES ─────────────────────────────────────────────
Expected quarterly sales growth     HY+Y    Analyst forward estimates
Expected quarterly sales            HY+Y    Forward estimate
Expected quarterly operating profit HY+Y    Forward estimate
Expected quarterly net profit       HY+Y    Forward estimate
Expected quarterly EPS              HY+Y    Forward estimate
```

---

### 4.10 BALANCE SHEET METRICS

```
METRIC                              TAG     REASON
──────────────────────────────────────────────────────────────────
── CURRENT YEAR ──────────────────────────────────────────────────
Debt (Total)                        Y+E     Annual BS; E=capital raise
Equity capital                      Y+E     Annual BS; E=capital raise
Preference capital                  Y+E     Annual BS
Reserves                            Y       Annual BS
Secured loan                        Y       Annual BS
Unsecured loan                      Y       Annual BS
Balance sheet total (Total Assets)  Y       Annual BS
Gross block (PP&E gross)            Y       Annual BS
Accumulated depreciation            Y       Annual BS
Net block (PP&E net)                Y       Annual BS
Capital work in progress            Y       Annual BS
Investments                         Y       Annual BS
Current assets                      Y+E     Annual BS; E=capital raise
Current liabilities                 Y       Annual BS
Working capital                     Y+E     Current assets - Current liab
Lease liabilities                   Y       Annual BS
Inventory                           Y       Annual BS
Trade receivables                   Y       Annual BS
Face value                          Y+E     Per share; E=split
Cash Equivalents                    Y+HY    Updated with HY results
Advance from Customers              Y       Annual BS
Trade Payables                      Y       Annual BS
Book value of unquoted investments  Y       Annual BS
Market value of quoted investments  D+Y     Quoted investments use daily prices
Contingent liabilities              Y       Annual BS
Total Assets                        Y+E     Annual BS; E=capital raise
Revaluation reserve                 Y       Annual BS

── PRECEDING YEAR ────────────────────────────────────────────────
Debt preceding year                 Y       Prior year BS
Number of equity shares preceding   Y       Prior year shares
Working capital preceding year      Y       Prior year WC
Net block preceding year            Y       Prior year PP&E net
Gross block preceding year          Y       Prior year PP&E gross
[All other preceding year BS]       Y       Prior year annual BS
Book value preceding year           Y       Prior year BVPS

── HISTORICAL ────────────────────────────────────────────────────
Number of equity shares 10y back    Y       10yr ago shares
Book value 3 years back             Y       3yr ago BVPS
Book value 5 years back             Y       5yr ago BVPS
Book value 10 years back            Y       10yr ago BVPS
```

---

### 4.11 SHAREHOLDER / OWNERSHIP METRICS

```
METRIC                              TAG     REASON
──────────────────────────────────────────────────────────────────
Promoter holding (Director %)       HY+Y+E  Updated with results + disclosures
Public holding                      HY+Y    Updated with results
FII holding (Institutional %)       HY+Y    Updated with results
DII holding (Domestic Inst %)       HY+Y    Updated with results
Number of Shareholders              HY+Y    Updated with results
Unpledged promoter holding          HY+Y+E  From substantial holder notices
Pledged percentage                  HY+Y+E  From results/disclosures
Exports percentage                  Y       From annual report
Exports percentage 3Y back          Y       3yr ago value
Exports percentage 5Y back          Y       5yr ago value
Number of Shareholders preceding Q  HY      Prior HY shareholder count
Number of Shareholders 1year back   Y       1yr ago shareholder count
Credit rating                       E       Updated on rating change (event)
Change in FII holding               HY      HY change in institutional %
Change in DII holding               HY      HY change in domestic inst %
Change in FII holding 3Years        Y       3yr change
Change in DII holding 3Years        Y       3yr change
```

---

### 4.12 COMPOSITE SCORES & ADVANCED METRICS

```
METRIC                              TAG     REASON
──────────────────────────────────────────────────────────────────
Piotroski score                     Y       9-signal annual scorecard
G Factor                            Y       Growth quality factor (annual)
Altman Z Score                      D+Y     Has market cap (daily) + annual data
Beneish M Score                     Y       Earnings manipulation (annual)
FallRatio                           D       Price sensitivity to market falls
Graham Number vs Price              D+Y     Price vs Graham Number (daily)
NCAVPS                              Y       Net Current Asset Value — annual
PB X PE                             D+Y     PB × PE (Lynch metric — daily price)
Earning Power                       Y       EBIT / Assets — annual
EVA (Economic Value Added)          Y       NOPAT - (Capital × WACC)
ROCE3yr avg                         Y       3yr avg ROCE
Leverage ratio                      Y       Assets / Equity — annual
Financial leverage                  Y       Same as above
Intrinsic Value                     Y       Formula-based (no price in formula)
```

---

### 4.13 USER-DEFINED / ADVANCED RATIOS (from User Ratios.txt)

```
METRIC                              TAG     REASON
──────────────────────────────────────────────────────────────────
52w Index                           D       52W range position
FallRatio                           D       Price fall sensitivity
InvestR                             D+Y     Investment return ratio
SalesP                              D+HY    Sales / Price
DRATIO                              Y       Debt ratio
Debt Capacity                       Y       FCF-based debt capacity
Debt To Profit                      HY+Y    Debt / Profit TTM
debtplus                            Y       Debt + contingent liabilities
Total Capital Employed              Y       Equity + LT Debt
CROIC                               Y       Cash return on invested capital
Mkt Cap To Debt Cap                 D+Y     Market Cap / Debt Cap
cash debt contingent liab by mcap   D+Y     (Cash-Debt-ContLiab)/MCap
Cash by market cap                  D+Y     Cash / Market Cap
Net worth                           Y       Equity + Reserves
Dividend Payout                     HY+Y    Dividends / Net Profit
Dividend Payout Ratio               HY+Y    Same
Free Cash Flow Yield                D+HY    FCF / Market Cap
Price to Cash Flow                  D+HY    Price / OCF per share
Market Cap to quarterly profit      D+HY    MCap / HY Profit
Market Capt to Cash Flow            D+HY    MCap / OCF TTM
Average 5years dividend             Y       5yr avg DPS
Working Capital to Sales ratio      HY+Y    WC / Revenue TTM
```

---

### 4.14 ASX-SPECIFIC METRICS (Enhancements)

```
METRIC                              TAG     REASON
──────────────────────────────────────────────────────────────────
── FRANKING CREDITS (Australian only) ────────────────────────────
Franking %                          HY+Y+E  From dividend announcement
Franking credit per share           D+E     Computed from DPS × franking %
Grossed-up dividend per share       D+E     DPS + franking credit
Grossed-up yield                    D+E     Grossed-up DPS / Price
Effective yield (at 30% tax)        D+E     Tax-adjusted yield
DRP participation %                 Y       Dividend reinvestment plan

── SHORT SELLING (ASIC data) ─────────────────────────────────────
Short interest %                    D       Daily ASIC data
Short interest shares               D       Number of shares short
Short interest change 1 week        D       vs 5 trading days ago
Short interest change 1 month       D       vs 21 trading days ago
Short interest trend                D       Increasing / Decreasing

── ASX INDEX MEMBERSHIP ──────────────────────────────────────────
In ASX 20 (boolean)                 Q+E     Quarterly index rebalance + events
In ASX 50 (boolean)                 Q+E     Quarterly + event
In ASX 100 (boolean)                Q+E     Quarterly + event
In ASX 200 (boolean)                Q+E     Quarterly + event
In ASX 300 (boolean)                Q+E     Quarterly + event
In All Ordinaries (boolean)         Q+E     Quarterly + event
In Small Ordinaries (boolean)       Q+E     Quarterly + event
IPO age (years since listing)       Y       Annual update

── MINING-SPECIFIC (ASX-unique) ─────────────────────────────────
AISC per oz (All-in sustaining cost) Q+E   Quarterly activity report
C1 cost per oz                      Q+E     Quarterly activity report
Production this quarter             Q+E     Quarterly activity report
Production vs guidance %            Q+E     Quarterly activity report
Reserve life years                  Y       From annual reserves statement
Proven reserves (kt / oz)           Y       Annual reserves statement
Probable reserves (kt / oz)         Y       Annual reserves statement
Total reserves (kt / oz)            Y       Annual reserves statement
Total resources (kt / oz)           Y       Annual resources statement
Hedging % of production             Q+Y     Updated with QAR + annual
NAV per share (miners)              Y       Net Asset Value / Shares
Price to NAV                        D+Y     Price / NAV per share

── REIT-SPECIFIC (ASX-unique) ────────────────────────────────────
FFO (Funds From Operations)         HY+Y    Half-year + annual
FFO per unit                        HY+Y    FFO / Units on issue
AFFO per unit (Adjusted FFO)        HY+Y    Adjusted FFO per unit
NTA per unit (Net Tangible Assets)  HY+Y    From half-year + annual BS
Price to NTA                        D+HY    Price / NTA (price changes daily)
FFO yield                           D+HY    FFO per unit / Unit price
AFFO yield                          D+HY    AFFO per unit / Unit price
Gearing ratio                       HY+Y    Debt / Total Assets (REIT method)
WALE (Weighted Avg Lease Expiry)    HY+Y    From property report
Occupancy %                         HY+Y    From property report
Cap rate                            HY+Y    From property report
Portfolio value                     HY+Y    Total portfolio value
Property count                      HY+Y    Number of properties

── ESG METRICS ────────────────────────────────────────────────────
ESG score                           Y       Annual from S&P/MSCI
Environmental score                 Y       Annual
Social score                        Y       Annual
Governance score                    Y       Annual
Carbon intensity                    Y       Annual from sustainability report
Net-zero commitment (boolean)       Y+E     Updated on announcement
```

---

## 5. Compute Tag Summary Count

```
TAG DISTRIBUTION ACROSS ALL METRICS:

  D     (Daily only):              ~75 metrics   (14%)
  D+Y   (Daily price + Annual):    ~40 metrics   (7%)
  D+HY  (Daily price + TTM/HY):    ~35 metrics   (6%)
  D+E   (Daily + Event):           ~10 metrics   (2%)
  D+Y+E (Daily + Annual + Event):  ~5 metrics    (1%)
  ──────────────────────────────────────────────────
  TOTAL "MUST RUN DAILY":          ~165 metrics  (30%)

  HY    (Half-Yearly):             ~60 metrics   (11%)
  HY+Y  (Half-year + Annual):      ~35 metrics   (6%)
  HY+E  (Half-year + Event):       ~10 metrics   (2%)
  ──────────────────────────────────────────────────
  TOTAL "HALF-YEARLY":             ~105 metrics  (19%)

  Y     (Yearly only):             ~180 metrics  (33%)
  Y+E   (Yearly + Event):          ~15 metrics   (3%)
  ──────────────────────────────────────────────────
  TOTAL "YEARLY":                  ~195 metrics  (36%)

  W     (Weekly aggregate):        ~15 metrics   (3%)
  M     (Monthly aggregate):       ~15 metrics   (3%)
  Q     (Quarterly - mining):      ~12 metrics   (2%)
  Q+E   (Quarterly + Event):       ~10 metrics   (2%)
  E     (Pure event-triggered):    ~5 metrics    (1%)
  ──────────────────────────────────────────────────
  TOTAL ALL METRICS:               ~544 metrics  (100%)
```

---

## 6. Cascading Schedule with Actual Metrics Count

```
╔══════════════════════════════════════════════════════════════════════╗
║  BATCH          COMPUTES        METRICS    EST. STOCKS  RUNTIME     ║
╠══════════════════════════════════════════════════════════════════════╣
║  Daily          D only          ~165       2,200        3–5 min     ║
║  Weekend        D + W           ~180       2,200        8–12 min    ║
║  Month-end      D + W + M       ~195       2,200        15–20 min   ║
║  Qtr (mining)   D + W + M + Q   ~207       ~400 miners  20–25 min   ║
║  Half-Year      D+W+M+Q+HY      ~312       ~1,200*      45–60 min   ║
║  Year-end       ALL TAGS        ~507       2,200        2–3 hours   ║
║  Event          E + D for 1 stk ~165       1 stock      < 2 min     ║
╠══════════════════════════════════════════════════════════════════════╣
║  * ~1,200 stocks typically report in each half-year season          ║
╚══════════════════════════════════════════════════════════════════════╝

EXECUTION ORDER (always lower tier before higher):
  D first → then W → then M → then Q → then HY → then Y
  Reason: Higher tiers may use outputs of lower tiers as inputs.
  Example: Monthly metrics use daily price history (D must be current)
```

---

## 7. The Compute Tag in the Database

```sql
-- Reference table: every metric defined with its compute tags
CREATE TABLE meta.metric_definitions (
    metric_id           SERIAL PRIMARY KEY,
    metric_key          VARCHAR(100) NOT NULL UNIQUE,  -- e.g. 'pe_ratio'
    metric_name         VARCHAR(200) NOT NULL,          -- Display name
    category            VARCHAR(50),                    -- valuation, profitability, etc.
    compute_tags        TEXT[]  NOT NULL,               -- e.g. ARRAY['D','HY']
    primary_tag         VARCHAR(5) NOT NULL,            -- Most frequent tag
    formula             TEXT,                           -- Human-readable formula
    formula_code        TEXT,                           -- Python formula reference
    data_sources        TEXT[],                         -- e.g. ARRAY['price','annual_pnl']
    unit                VARCHAR(30),                    -- %, AUD, ratio, etc.
    display_decimals    SMALLINT DEFAULT 2,
    is_asx_specific     BOOLEAN DEFAULT FALSE,
    is_screener_enabled BOOLEAN DEFAULT TRUE,           -- Available in screener query
    is_active           BOOLEAN DEFAULT TRUE,
    notes               TEXT
);

-- Sample records:
INSERT INTO meta.metric_definitions VALUES
(1, 'pe_ratio',      'Price to Earnings',   'valuation',      ARRAY['D','HY'], 'D',
 'Price / EPS TTM', 'ValuationStage.pe_ratio', ARRAY['price','half_year_pnl'],
 'ratio', 2, FALSE, TRUE, TRUE, 'Recompute daily; EPS source is TTM'),

(2, 'roe',           'Return on Equity',    'profitability',  ARRAY['Y'],      'Y',
 'Net Profit / Equity', 'ProfitabilityStage.roe', ARRAY['annual_pnl','annual_bs'],
 '%', 2, FALSE, TRUE, TRUE, 'Pure annual metric; no price dependency'),

(3, 'grossed_up_yield','Grossed-up Yield',  'dividends',      ARRAY['D','E'],  'D',
 '(DPS + Franking Credit) / Price', 'ASXSpecificStage.grossed_up_yield',
 ARRAY['price','dividends'], '%', 2, TRUE, TRUE, TRUE, 'AUS franking credit metric');
```

---

## 8. Compute Engine: Tag-Based Execution Logic

```python
# compute_engine/scheduler.py

COMPUTE_SCHEDULE = {
    'daily':       ['D'],
    'weekend':     ['D', 'W'],
    'month_end':   ['D', 'W', 'M'],
    'quarterly':   ['D', 'W', 'M', 'Q'],
    'half_yearly': ['D', 'W', 'M', 'Q', 'HY'],
    'yearly':      ['D', 'W', 'M', 'Q', 'HY', 'Y'],
    'event':       ['E'],   # + re-run D for affected stocks
}

def get_metrics_for_schedule(schedule_type: str) -> list[MetricDefinition]:
    """Return all metrics that should compute in this batch."""
    tags_to_run = COMPUTE_SCHEDULE[schedule_type]
    return db.query("""
        SELECT * FROM meta.metric_definitions
        WHERE is_active = TRUE
          AND compute_tags && %(tags)s::text[]
        ORDER BY
          -- Execute in dependency order: D first, then W, M, Q, HY, Y
          CASE WHEN 'D' = ANY(compute_tags) THEN 1
               WHEN 'W' = ANY(compute_tags) THEN 2
               WHEN 'M' = ANY(compute_tags) THEN 3
               WHEN 'Q' = ANY(compute_tags) THEN 4
               WHEN 'HY'= ANY(compute_tags) THEN 5
               WHEN 'Y' = ANY(compute_tags) THEN 6
               ELSE 7 END
    """, tags=tags_to_run)


def run_compute_for_schedule(schedule_type: str, compute_date: date,
                              asx_codes: list[str] = None):
    """
    Main entry point for any scheduled compute batch.
    asx_codes: if None, run for all stocks. If specified, run for subset (event mode).
    """
    if asx_codes is None:
        asx_codes = get_all_active_asx_codes()

    metrics = get_metrics_for_schedule(schedule_type)
    ctx     = DataLoader(compute_date, asx_codes).load_for_tags(
                  COMPUTE_SCHEDULE[schedule_type]
              )

    results = {}
    for metric in metrics:
        try:
            value = formula_library.compute(metric.formula_code, ctx, asx_codes)
            results[metric.metric_key] = value
        except Exception as e:
            log.error(f"Failed to compute {metric.metric_key}: {e}")
            results[metric.metric_key] = None  # Graceful degradation

    # Write all results to appropriate table
    writer.write(compute_date, asx_codes, results, schedule_type)
    writer.invalidate_redis_cache(asx_codes)
    log_compute_run(schedule_type, compute_date, len(asx_codes), 'success')
```

---

*Next: `10_Frontend_Wireframes.md` — UI/UX design for all major pages*
