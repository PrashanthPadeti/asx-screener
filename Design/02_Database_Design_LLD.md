# ASX Screener — Database Design (LLD)

> Version 1.0 | April 2026
> Database: PostgreSQL 16 + TimescaleDB extension

---

## 1. Database Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                    POSTGRESQL DATABASE: asx_screener                 │
│                                                                       │
│  SCHEMA: market          SCHEMA: financials      SCHEMA: users       │
│  ─────────────────        ──────────────────      ──────────────      │
│  companies               annual_pnl              users               │
│  daily_prices ①          annual_balance_sheet    subscriptions       │
│  technical_indicators    annual_cashflow         watchlists          │
│  computed_metrics ①      half_year_pnl           watchlist_items     │
│  short_interest ①        half_year_cashflow      portfolios          │
│  asx_announcements       quarterly_activity      portfolio_txns      │
│  dividends               mining_data             saved_screens       │
│  shareholding            reit_data               screen_run_history  │
│  substantial_holders     bank_data               alerts              │
│  index_membership        sector_pe_history       alert_triggers      │
│  corporate_events                                user_notes          │
│                          SCHEMA: ai              user_custom_ratios  │
│                          ──────────────                              │
│                          document_chunks                             │
│                          ai_insights                                 │
│                          concall_summaries                           │
│                                                                       │
│  ① = TimescaleDB Hypertable (time-series, auto-partitioned)          │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. Schema: market

### 2.1 companies — Master Reference Table

```sql
CREATE TABLE market.companies (
    id                      SERIAL PRIMARY KEY,
    asx_code                VARCHAR(10)  NOT NULL UNIQUE,
    isin                    VARCHAR(12)  UNIQUE,
    company_name            VARCHAR(255) NOT NULL,
    short_name              VARCHAR(100),

    -- Classification
    gics_sector             VARCHAR(100),
    gics_industry_group     VARCHAR(100),
    gics_industry           VARCHAR(100),
    gics_sub_industry       VARCHAR(100),
    asx_sector              VARCHAR(100),          -- ASX's own sector classification
    company_type            VARCHAR(50),           -- 'ordinary', 'reit', 'etf', 'lic', 'stapled'

    -- ASX-specific flags
    is_reit                 BOOLEAN DEFAULT FALSE,
    is_miner                BOOLEAN DEFAULT FALSE,
    is_bank                 BOOLEAN DEFAULT FALSE,
    is_insurer              BOOLEAN DEFAULT FALSE,
    is_asx20                BOOLEAN DEFAULT FALSE,
    is_asx50                BOOLEAN DEFAULT FALSE,
    is_asx100               BOOLEAN DEFAULT FALSE,
    is_asx200               BOOLEAN DEFAULT FALSE,
    is_asx300               BOOLEAN DEFAULT FALSE,
    is_all_ords             BOOLEAN DEFAULT FALSE,
    is_small_ords           BOOLEAN DEFAULT FALSE,

    -- Listing info
    listing_date            DATE,
    ipo_price               NUMERIC(12,4),
    delisting_date          DATE,
    delisting_reason        VARCHAR(100),
    status                  VARCHAR(20) DEFAULT 'active',  -- active, suspended, delisted

    -- Financial year end
    financial_year_end      INTEGER DEFAULT 6,  -- month number (6=June for most ASX)

    -- Share structure
    shares_outstanding      BIGINT,
    shares_float            BIGINT,
    face_value              NUMERIC(10,4),

    -- Company details
    website                 VARCHAR(255),
    abn                     VARCHAR(20),
    acn                     VARCHAR(20),
    domicile                VARCHAR(100) DEFAULT 'Australia',
    state                   VARCHAR(50),

    -- Primary commodity (miners only)
    primary_commodity       VARCHAR(100),
    secondary_commodity     VARCHAR(100),

    -- Metadata
    description             TEXT,
    logo_url                VARCHAR(500),
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    updated_at              TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_companies_asx_code     ON market.companies(asx_code);
CREATE INDEX idx_companies_gics_sector  ON market.companies(gics_sector);
CREATE INDEX idx_companies_status       ON market.companies(status);
CREATE INDEX idx_companies_is_asx200    ON market.companies(is_asx200) WHERE is_asx200 = TRUE;
CREATE INDEX idx_companies_is_miner     ON market.companies(is_miner)  WHERE is_miner  = TRUE;
CREATE INDEX idx_companies_is_reit      ON market.companies(is_reit)   WHERE is_reit   = TRUE;
```

---

### 2.2 daily_prices — TimescaleDB Hypertable

```sql
CREATE TABLE market.daily_prices (
    time                    TIMESTAMPTZ NOT NULL,    -- Partition key (date at market close)
    asx_code                VARCHAR(10)  NOT NULL,
    open                    NUMERIC(12,4),
    high                    NUMERIC(12,4),
    low                     NUMERIC(12,4),
    close                   NUMERIC(12,4) NOT NULL,
    adjusted_close          NUMERIC(12,4),           -- Dividend/split adjusted
    volume                  BIGINT,
    value_traded            NUMERIC(18,2),           -- AUD value traded
    trades_count            INTEGER,
    vwap                    NUMERIC(12,4),
    data_source             VARCHAR(30) DEFAULT 'yahoo',
    PRIMARY KEY (time, asx_code)
);

-- Convert to TimescaleDB hypertable (partition by week)
SELECT create_hypertable('market.daily_prices', 'time',
    chunk_time_interval => INTERVAL '1 week',
    if_not_exists => TRUE
);

-- Compress chunks older than 3 months (up to 98% size reduction)
ALTER TABLE market.daily_prices SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'asx_code',
    timescaledb.compress_orderby   = 'time DESC'
);
SELECT add_compression_policy('market.daily_prices', INTERVAL '3 months');

CREATE INDEX idx_daily_prices_asx_time ON market.daily_prices(asx_code, time DESC);

-- Continuous aggregate: weekly OHLCV (pre-computed, auto-refreshed)
CREATE MATERIALIZED VIEW market.weekly_prices
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 week', time)  AS week,
    asx_code,
    first(open, time)            AS open,
    max(high)                    AS high,
    min(low)                     AS low,
    last(close, time)            AS close,
    last(adjusted_close, time)   AS adjusted_close,
    sum(volume)                  AS volume,
    sum(value_traded)            AS value_traded
FROM market.daily_prices
GROUP BY week, asx_code;

SELECT add_continuous_aggregate_policy('market.weekly_prices',
    start_offset => INTERVAL '3 weeks',
    end_offset   => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 day'
);

-- Continuous aggregate: monthly OHLCV
CREATE MATERIALIZED VIEW market.monthly_prices
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 month', time) AS month,
    asx_code,
    first(open, time)            AS open,
    max(high)                    AS high,
    min(low)                     AS low,
    last(close, time)            AS close,
    last(adjusted_close, time)   AS adjusted_close,
    sum(volume)                  AS volume
FROM market.daily_prices
GROUP BY month, asx_code;
```

---

### 2.3 technical_indicators — Computed Daily

```sql
CREATE TABLE market.technical_indicators (
    time                    TIMESTAMPTZ NOT NULL,
    asx_code                VARCHAR(10)  NOT NULL,

    -- Moving Averages
    dma_20                  NUMERIC(12,4),
    dma_50                  NUMERIC(12,4),
    dma_200                 NUMERIC(12,4),
    dma_50_prev             NUMERIC(12,4),    -- Previous day (for crossover detection)
    dma_200_prev            NUMERIC(12,4),
    ema_12                  NUMERIC(12,4),
    ema_26                  NUMERIC(12,4),

    -- MACD
    macd                    NUMERIC(12,6),
    macd_signal             NUMERIC(12,6),
    macd_histogram          NUMERIC(12,6),
    macd_prev               NUMERIC(12,6),
    macd_signal_prev        NUMERIC(12,6),

    -- Momentum
    rsi_14                  NUMERIC(6,2),     -- 0–100
    stoch_rsi               NUMERIC(6,2),
    adx_14                  NUMERIC(6,2),     -- Average Directional Index

    -- Volatility
    atr_14                  NUMERIC(12,4),    -- Average True Range
    bollinger_upper         NUMERIC(12,4),    -- 2 std dev above 20-DMA
    bollinger_lower         NUMERIC(12,4),
    bollinger_mid           NUMERIC(12,4),
    bollinger_pct           NUMERIC(6,4),     -- Position within bands (0–1)
    historical_volatility_20 NUMERIC(8,4),   -- 20-day annualised volatility

    -- Volume
    volume                  BIGINT,
    volume_avg_5d           BIGINT,
    volume_avg_20d          BIGINT,
    volume_avg_60d          BIGINT,
    volume_ratio            NUMERIC(8,4),     -- Today / 20d avg
    obv                     BIGINT,           -- On-Balance Volume

    -- 52-Week & All-Time Levels
    high_52w                NUMERIC(12,4),
    low_52w                 NUMERIC(12,4),
    high_all_time           NUMERIC(12,4),
    low_all_time            NUMERIC(12,4),
    pct_from_52w_high       NUMERIC(8,4),     -- Negative = below high
    pct_from_52w_low        NUMERIC(8,4),     -- Positive = above low
    pct_from_ath            NUMERIC(8,4),
    pct_from_atl            NUMERIC(8,4),
    range_52w_position      NUMERIC(6,4),     -- 0=at 52w low, 1=at 52w high
    dma_50_ratio            NUMERIC(8,4),     -- Price / DMA50
    dma_200_ratio           NUMERIC(8,4),

    -- Returns
    return_1d               NUMERIC(10,6),    -- As decimal (0.05 = 5%)
    return_1w               NUMERIC(10,6),
    return_1m               NUMERIC(10,6),
    return_3m               NUMERIC(10,6),
    return_6m               NUMERIC(10,6),
    return_1y               NUMERIC(10,6),
    return_3y               NUMERIC(10,6),    -- Annualised CAGR
    return_5y               NUMERIC(10,6),    -- Annualised CAGR

    -- Signals (boolean flags)
    golden_cross            BOOLEAN,          -- DMA50 crossed above DMA200 today
    death_cross             BOOLEAN,          -- DMA50 crossed below DMA200 today
    new_52w_high            BOOLEAN,
    new_52w_low             BOOLEAN,
    above_dma_50            BOOLEAN,
    above_dma_200           BOOLEAN,

    PRIMARY KEY (time, asx_code)
);

SELECT create_hypertable('market.technical_indicators', 'time',
    chunk_time_interval => INTERVAL '1 month'
);
SELECT add_compression_policy('market.technical_indicators', INTERVAL '6 months');

CREATE INDEX idx_tech_asx_time ON market.technical_indicators(asx_code, time DESC);
```

---

### 2.4 computed_metrics — The Core Screener Table

```sql
-- This is the table the screener queries against.
-- Populated entirely by the Compute Engine (daily).
-- One row per stock per day (only today's row for active screener;
-- historical rows retained for trend analysis).

CREATE TABLE market.computed_metrics (
    time                    TIMESTAMPTZ NOT NULL,
    asx_code                VARCHAR(10)  NOT NULL,

    -- ═══════════════════════════════════════════
    -- VALUATION
    -- ═══════════════════════════════════════════
    market_cap              NUMERIC(18,2),    -- AUD millions
    enterprise_value        NUMERIC(18,2),    -- AUD millions
    pe_ratio                NUMERIC(12,4),    -- Trailing 12-month
    pe_forward              NUMERIC(12,4),    -- Forward (analyst estimates)
    pb_ratio                NUMERIC(12,4),    -- Price / Book
    ps_ratio                NUMERIC(12,4),    -- Price / Sales
    pcf_ratio               NUMERIC(12,4),    -- Price / Operating Cash Flow
    pfcf_ratio              NUMERIC(12,4),    -- Price / Free Cash Flow
    ev_ebitda               NUMERIC(12,4),
    ev_ebit                 NUMERIC(12,4),
    ev_sales                NUMERIC(12,4),
    ev_fcf                  NUMERIC(12,4),
    peg_ratio               NUMERIC(12,4),
    earnings_yield          NUMERIC(10,6),    -- EPS / Price
    fcf_yield               NUMERIC(10,6),    -- FCF / Market Cap
    dividend_yield          NUMERIC(10,6),    -- Div / Price
    grossed_up_yield        NUMERIC(10,6),    -- (Div + Franking credit) / Price
    graham_number           NUMERIC(12,4),
    ncavps                  NUMERIC(12,4),    -- Net Current Asset Value per Share
    pb_x_pe                 NUMERIC(12,4),    -- PB × PE (Lynch metric)

    -- ═══════════════════════════════════════════
    -- PROFITABILITY
    -- ═══════════════════════════════════════════
    roe                     NUMERIC(10,6),    -- Return on Equity
    roa                     NUMERIC(10,6),    -- Return on Assets
    roce                    NUMERIC(10,6),    -- Return on Capital Employed
    roic                    NUMERIC(10,6),    -- Return on Invested Capital
    croic                   NUMERIC(10,6),    -- Cash Return on Invested Capital
    opm                     NUMERIC(10,6),    -- Operating Profit Margin
    npm                     NUMERIC(10,6),    -- Net Profit Margin
    gpm                     NUMERIC(10,6),    -- Gross Profit Margin
    ebitda_margin           NUMERIC(10,6),
    ebit_margin             NUMERIC(10,6),
    earning_power           NUMERIC(10,6),    -- EBIT / Total Assets

    -- ═══════════════════════════════════════════
    -- EFFICIENCY
    -- ═══════════════════════════════════════════
    asset_turnover          NUMERIC(10,6),
    inventory_turnover      NUMERIC(10,6),
    receivables_turnover    NUMERIC(10,6),
    payables_turnover       NUMERIC(10,6),
    working_capital_turnover NUMERIC(10,6),
    debtor_days             NUMERIC(10,2),    -- DSO
    dpo                     NUMERIC(10,2),    -- Days Payable Outstanding
    dio                     NUMERIC(10,2),    -- Days Inventory Outstanding
    cash_conversion_cycle   NUMERIC(10,2),    -- DSO + DIO - DPO
    working_capital_days    NUMERIC(10,2),

    -- ═══════════════════════════════════════════
    -- GROWTH (historical CAGR, computed from financial statements)
    -- ═══════════════════════════════════════════
    revenue_growth_1y       NUMERIC(10,6),
    revenue_growth_3y       NUMERIC(10,6),    -- 3Y CAGR
    revenue_growth_5y       NUMERIC(10,6),
    revenue_growth_7y       NUMERIC(10,6),
    revenue_growth_10y      NUMERIC(10,6),
    profit_growth_1y        NUMERIC(10,6),
    profit_growth_3y        NUMERIC(10,6),
    profit_growth_5y        NUMERIC(10,6),
    profit_growth_7y        NUMERIC(10,6),
    profit_growth_10y       NUMERIC(10,6),
    eps_growth_1y           NUMERIC(10,6),
    eps_growth_3y           NUMERIC(10,6),
    eps_growth_5y           NUMERIC(10,6),
    eps_growth_7y           NUMERIC(10,6),
    eps_growth_10y          NUMERIC(10,6),
    ebitda_growth_3y        NUMERIC(10,6),
    ebitda_growth_5y        NUMERIC(10,6),
    fcf_growth_3y           NUMERIC(10,6),
    fcf_growth_5y           NUMERIC(10,6),
    mcap_growth_3y          NUMERIC(10,6),
    mcap_growth_5y          NUMERIC(10,6),
    roe_avg_3y              NUMERIC(10,6),
    roe_avg_5y              NUMERIC(10,6),
    roe_avg_7y              NUMERIC(10,6),
    roe_avg_10y             NUMERIC(10,6),
    roce_avg_3y             NUMERIC(10,6),
    roce_avg_5y             NUMERIC(10,6),
    roce_avg_7y             NUMERIC(10,6),
    roce_avg_10y            NUMERIC(10,6),
    opm_avg_5y              NUMERIC(10,6),
    opm_avg_10y             NUMERIC(10,6),

    -- Quarterly growth (YoY)
    rev_qoq_growth          NUMERIC(10,6),    -- Quarter vs same quarter last year
    profit_qoq_growth       NUMERIC(10,6),
    rev_sequential_growth   NUMERIC(10,6),    -- Current qtr vs prev qtr
    profit_sequential_growth NUMERIC(10,6),

    -- ═══════════════════════════════════════════
    -- FINANCIAL HEALTH / LEVERAGE
    -- ═══════════════════════════════════════════
    debt_to_equity          NUMERIC(10,4),
    net_debt_to_ebitda      NUMERIC(10,4),
    net_debt_to_equity      NUMERIC(10,4),
    debt_to_assets          NUMERIC(10,4),
    interest_coverage       NUMERIC(10,4),    -- EBIT / Interest
    current_ratio           NUMERIC(10,4),
    quick_ratio             NUMERIC(10,4),
    cash_ratio              NUMERIC(10,4),
    working_capital         NUMERIC(18,2),    -- AUD millions
    financial_leverage      NUMERIC(10,4),    -- Assets / Equity
    debt_capacity           NUMERIC(18,2),
    leverage_ratio          NUMERIC(10,4),

    -- ═══════════════════════════════════════════
    -- CASH FLOW
    -- ═══════════════════════════════════════════
    fcf                     NUMERIC(18,2),    -- AUD millions, TTM
    fcf_per_share           NUMERIC(12,4),
    ocf_to_net_income       NUMERIC(10,4),    -- Cash conversion quality
    capex_to_sales          NUMERIC(10,6),
    ocf_to_debt             NUMERIC(10,6),
    ocf_margin              NUMERIC(10,6),

    -- ═══════════════════════════════════════════
    -- DIVIDENDS
    -- ═══════════════════════════════════════════
    dividend_per_share      NUMERIC(10,4),    -- Last 12 months, AUD
    franking_pct            NUMERIC(6,2),     -- 0–100
    grossed_up_dividend     NUMERIC(10,4),    -- DPS + franking credit value
    dividend_payout_ratio   NUMERIC(10,6),
    dividend_avg_5y         NUMERIC(10,4),
    dividend_growth_3y      NUMERIC(10,6),

    -- ═══════════════════════════════════════════
    -- SCORES & COMPOSITE METRICS
    -- ═══════════════════════════════════════════
    piotroski_score         SMALLINT,         -- 0–9
    g_factor                NUMERIC(10,4),
    altman_z_score          NUMERIC(10,4),
    beneish_m_score         NUMERIC(10,4),
    beta_1y                 NUMERIC(8,4),
    beta_3y                 NUMERIC(8,4),
    sharpe_1y               NUMERIC(8,4),
    sortino_1y              NUMERIC(8,4),
    max_drawdown_1y         NUMERIC(8,4),     -- Percentage (negative)
    max_drawdown_3y         NUMERIC(8,4),
    fall_ratio              NUMERIC(8,4),

    -- ═══════════════════════════════════════════
    -- PER-SHARE METRICS
    -- ═══════════════════════════════════════════
    eps_ttm                 NUMERIC(12,4),    -- Trailing 12 months
    eps_last_year           NUMERIC(12,4),
    eps_preceding_year      NUMERIC(12,4),
    book_value_per_share    NUMERIC(12,4),

    -- ═══════════════════════════════════════════
    -- SHAREHOLDING (from quarterly snapshots)
    -- ═══════════════════════════════════════════
    director_holding_pct    NUMERIC(8,4),
    institutional_pct       NUMERIC(8,4),
    retail_pct              NUMERIC(8,4),
    short_interest_pct      NUMERIC(8,4),     -- From ASIC (daily)
    short_interest_change_1w NUMERIC(8,4),
    short_interest_change_1m NUMERIC(8,4),

    -- ═══════════════════════════════════════════
    -- ASX-SPECIFIC
    -- ═══════════════════════════════════════════
    -- Mining
    aisc_per_oz             NUMERIC(12,2),    -- All-in sustaining cost (gold miners)
    reserve_life_years      NUMERIC(8,2),
    nav_per_share           NUMERIC(12,4),    -- Net Asset Value (miners/REITs)

    -- REIT
    ffo_per_unit            NUMERIC(12,4),    -- Funds From Operations
    affo_per_unit           NUMERIC(12,4),    -- Adjusted FFO
    nta_per_unit            NUMERIC(12,4),    -- Net Tangible Assets
    price_to_nta            NUMERIC(10,4),    -- Premium/discount to NTA
    gearing_ratio           NUMERIC(8,4),     -- REIT-specific leverage
    wale_years              NUMERIC(8,2),     -- Weighted Avg Lease Expiry
    occupancy_pct           NUMERIC(8,4),
    ffo_yield               NUMERIC(10,6),

    -- Advanced valuation
    ev_per_employee         NUMERIC(12,2),
    mcap_to_sales           NUMERIC(10,4),
    mcap_to_cashflow        NUMERIC(10,4),
    mcap_to_quarterly_profit NUMERIC(10,4),
    intrinsic_value         NUMERIC(12,4),    -- Graham/DCF derived
    price_to_intrinsic_value NUMERIC(10,4),

    -- Sales, EPS reference (TTM — for screener filters)
    revenue_ttm             NUMERIC(18,2),    -- AUD millions
    ebitda_ttm              NUMERIC(18,2),
    ebit_ttm                NUMERIC(18,2),
    net_profit_ttm          NUMERIC(18,2),
    eps_ttm_ref             NUMERIC(12,4),

    -- Metadata
    compute_version         VARCHAR(20),      -- Version of compute engine
    computed_at             TIMESTAMPTZ DEFAULT NOW(),

    PRIMARY KEY (time, asx_code)
);

SELECT create_hypertable('market.computed_metrics', 'time',
    chunk_time_interval => INTERVAL '1 month'
);
SELECT add_compression_policy('market.computed_metrics', INTERVAL '6 months');

-- Primary screener index — covers the most common filter columns
CREATE INDEX idx_cm_screener ON market.computed_metrics(time DESC, asx_code)
    INCLUDE (market_cap, pe_ratio, pb_ratio, roe, roce, debt_to_equity,
             dividend_yield, revenue_growth_3y, profit_growth_3y,
             piotroski_score, altman_z_score, short_interest_pct);

CREATE INDEX idx_cm_asx_time ON market.computed_metrics(asx_code, time DESC);
```

---

### 2.5 short_interest — Daily ASIC Data (TimescaleDB)

```sql
CREATE TABLE market.short_interest (
    time                    TIMESTAMPTZ NOT NULL,
    asx_code                VARCHAR(10)  NOT NULL,
    gross_short_position    BIGINT,           -- Number of shares short
    total_product_short_pct NUMERIC(8,4),     -- % of issued capital
    gross_short_sales       BIGINT,           -- Shares sold short that day
    reported_short_pct      NUMERIC(8,4),
    PRIMARY KEY (time, asx_code)
);

SELECT create_hypertable('market.short_interest', 'time',
    chunk_time_interval => INTERVAL '1 month'
);
```

---

### 2.6 asx_announcements

```sql
CREATE TABLE market.asx_announcements (
    id                      BIGSERIAL PRIMARY KEY,
    asx_code                VARCHAR(10) NOT NULL,
    announced_at            TIMESTAMPTZ NOT NULL,
    headline                VARCHAR(500) NOT NULL,

    -- ASX Classification
    asx_category            VARCHAR(100),     -- e.g. 'Periodic Reports'
    asx_subcategory         VARCHAR(100),

    -- AI Classification (Claude Haiku)
    ai_category             VARCHAR(50),
    -- Values: earnings, capital_raise, director_change, operational,
    --         material_event, dividend, agm, guidance, quarterly_activity,
    --         investor_presentation, other

    ai_sentiment            VARCHAR(20),      -- positive, negative, neutral
    ai_materiality          SMALLINT,         -- 1–5 (5 = most material)
    ai_summary              TEXT,             -- 2–3 sentence summary
    ai_key_points           JSONB,            -- ["point1", "point2", ...]

    -- Document
    document_url            VARCHAR(500),
    s3_key                  VARCHAR(500),     -- Stored copy in S3
    page_count              INTEGER,

    -- Flags
    is_price_sensitive      BOOLEAN DEFAULT FALSE,
    is_capital_raise        BOOLEAN DEFAULT FALSE,
    is_earnings             BOOLEAN DEFAULT FALSE,
    is_director_change      BOOLEAN DEFAULT FALSE,

    -- Capital raise details (if applicable)
    raise_type              VARCHAR(50),      -- placement, rights_issue, spp, ent_offer
    raise_amount_aud        NUMERIC(18,2),
    raise_price             NUMERIC(12,4),
    raise_discount_pct      NUMERIC(8,4),
    new_shares_issued       BIGINT,
    dilution_pct            NUMERIC(8,4),

    processed_at            TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_announcements_asx_date ON market.asx_announcements(asx_code, announced_at DESC);
CREATE INDEX idx_announcements_date     ON market.asx_announcements(announced_at DESC);
CREATE INDEX idx_announcements_category ON market.asx_announcements(ai_category);
CREATE INDEX idx_announcements_capital  ON market.asx_announcements(is_capital_raise)
    WHERE is_capital_raise = TRUE;
```

---

### 2.7 dividends

```sql
CREATE TABLE market.dividends (
    id                      SERIAL PRIMARY KEY,
    asx_code                VARCHAR(10) NOT NULL,
    ex_date                 DATE NOT NULL,
    record_date             DATE,
    pay_date                DATE,
    declared_date           DATE,

    -- Amount
    amount_per_share        NUMERIC(12,6) NOT NULL,   -- AUD
    currency                VARCHAR(3) DEFAULT 'AUD',
    franking_pct            NUMERIC(6,2) DEFAULT 0,   -- 0–100
    franking_credit_per_share NUMERIC(12,6),          -- Computed
    grossed_up_amount       NUMERIC(12,6),             -- Computed

    -- Type
    dividend_type           VARCHAR(30),               -- final, interim, special, drp
    is_drp_available        BOOLEAN DEFAULT FALSE,
    drp_price               NUMERIC(12,4),

    UNIQUE (asx_code, ex_date, dividend_type)
);

CREATE INDEX idx_dividends_asx_date ON market.dividends(asx_code, ex_date DESC);
CREATE INDEX idx_dividends_exdate   ON market.dividends(ex_date DESC);
```

---

### 2.8 shareholding

```sql
CREATE TABLE market.shareholding (
    id                      SERIAL PRIMARY KEY,
    asx_code                VARCHAR(10) NOT NULL,
    snapshot_date           DATE NOT NULL,           -- Usually quarterly with annual report

    -- Holdings breakdown (%)
    director_pct            NUMERIC(8,4),
    substantial_holders_pct NUMERIC(8,4),            -- All holders > 5%
    institutional_pct       NUMERIC(8,4),
    retail_pct              NUMERIC(8,4),

    -- Top holders
    top1_holder_name        VARCHAR(255),
    top1_holder_pct         NUMERIC(8,4),
    top5_concentration_pct  NUMERIC(8,4),
    top20_concentration_pct NUMERIC(8,4),

    -- Changes vs prior snapshot
    director_pct_change     NUMERIC(8,4),
    institutional_pct_change NUMERIC(8,4),

    UNIQUE (asx_code, snapshot_date)
);
```

---

### 2.9 substantial_holders — Director & >5% Holder Notices

```sql
CREATE TABLE market.substantial_holders (
    id                      BIGSERIAL PRIMARY KEY,
    asx_code                VARCHAR(10) NOT NULL,
    holder_name             VARCHAR(255) NOT NULL,
    notice_date             DATE NOT NULL,
    notice_type             VARCHAR(50),    -- 'initial', 'change', 'cease'
    shares_held             BIGINT,
    percentage_held         NUMERIC(8,4),
    prev_percentage         NUMERIC(8,4),
    change_pct              NUMERIC(8,4),   -- Computed: percentage - prev_percentage
    consideration_paid      NUMERIC(18,2),
    is_director             BOOLEAN DEFAULT FALSE,
    source_document_url     VARCHAR(500),
    UNIQUE (asx_code, holder_name, notice_date)
);

CREATE INDEX idx_substantial_asx      ON market.substantial_holders(asx_code, notice_date DESC);
CREATE INDEX idx_substantial_holder   ON market.substantial_holders(holder_name);
CREATE INDEX idx_substantial_director ON market.substantial_holders(is_director)
    WHERE is_director = TRUE;
```

---

### 2.10 corporate_events

```sql
CREATE TABLE market.corporate_events (
    id                      SERIAL PRIMARY KEY,
    asx_code                VARCHAR(10) NOT NULL,
    event_date              DATE NOT NULL,
    event_type              VARCHAR(50) NOT NULL,
    -- Types: earnings_release, agm, capital_raise, record_date,
    --        ex_div, pay_date, listing, halt, suspension, split,
    --        consolidation, name_change, index_addition, index_removal
    description             VARCHAR(500),
    is_confirmed            BOOLEAN DEFAULT TRUE,
    source                  VARCHAR(100)
);

CREATE INDEX idx_events_asx_date  ON market.corporate_events(asx_code, event_date);
CREATE INDEX idx_events_date      ON market.corporate_events(event_date);
CREATE INDEX idx_events_type      ON market.corporate_events(event_type);
```

---

## 3. Schema: financials

### 3.1 annual_pnl — Profit & Loss

```sql
CREATE TABLE financials.annual_pnl (
    id                      SERIAL PRIMARY KEY,
    asx_code                VARCHAR(10) NOT NULL,
    fiscal_year             INTEGER NOT NULL,         -- e.g. 2024 = FY ending June 2024
    period_end_date         DATE NOT NULL,
    report_date             DATE,                     -- Date ASX announcement filed

    -- Income Statement
    revenue                 NUMERIC(18,2),            -- AUD millions
    cost_of_sales           NUMERIC(18,2),
    gross_profit            NUMERIC(18,2),
    other_income            NUMERIC(18,2),
    operating_expenses      NUMERIC(18,2),
    ebitda                  NUMERIC(18,2),
    depreciation            NUMERIC(18,2),
    amortisation            NUMERIC(18,2),
    ebit                    NUMERIC(18,2),
    interest_expense        NUMERIC(18,2),
    interest_income         NUMERIC(18,2),
    pbt                     NUMERIC(18,2),            -- Profit Before Tax
    tax                     NUMERIC(18,2),
    pat                     NUMERIC(18,2),            -- Profit After Tax
    minority_interest       NUMERIC(18,2),
    net_profit              NUMERIC(18,2),            -- Attributable to shareholders
    extraordinary_items     NUMERIC(18,2),
    dividend_paid           NUMERIC(18,2),
    material_cost           NUMERIC(18,2),
    employee_cost           NUMERIC(18,2),

    -- Derived margins (stored for performance)
    opm                     NUMERIC(10,6),            -- EBIT / Revenue
    npm                     NUMERIC(10,6),            -- Net Profit / Revenue
    gpm                     NUMERIC(10,6),
    ebitda_margin           NUMERIC(10,6),

    -- Per share
    eps                     NUMERIC(12,4),
    eps_diluted             NUMERIC(12,4),
    shares_used             BIGINT,                   -- Weighted avg shares for EPS

    -- Metadata
    currency                VARCHAR(3) DEFAULT 'AUD',
    is_restated             BOOLEAN DEFAULT FALSE,
    data_source             VARCHAR(50),

    UNIQUE (asx_code, fiscal_year)
);

CREATE INDEX idx_pnl_asx_year ON financials.annual_pnl(asx_code, fiscal_year DESC);
```

---

### 3.2 annual_balance_sheet

```sql
CREATE TABLE financials.annual_balance_sheet (
    id                      SERIAL PRIMARY KEY,
    asx_code                VARCHAR(10) NOT NULL,
    fiscal_year             INTEGER NOT NULL,
    period_end_date         DATE NOT NULL,

    -- Assets
    cash_equivalents        NUMERIC(18,2),
    trade_receivables       NUMERIC(18,2),
    inventory               NUMERIC(18,2),
    other_current_assets    NUMERIC(18,2),
    total_current_assets    NUMERIC(18,2),
    gross_block             NUMERIC(18,2),            -- Property, plant, equipment (gross)
    accumulated_depreciation NUMERIC(18,2),
    net_block               NUMERIC(18,2),            -- PP&E net
    cwip                    NUMERIC(18,2),            -- Capital work in progress
    goodwill                NUMERIC(18,2),
    intangibles             NUMERIC(18,2),
    investments             NUMERIC(18,2),
    other_non_current       NUMERIC(18,2),
    total_assets            NUMERIC(18,2),

    -- Liabilities
    trade_payables          NUMERIC(18,2),
    advance_from_customers  NUMERIC(18,2),
    short_term_debt         NUMERIC(18,2),
    other_current_liab      NUMERIC(18,2),
    total_current_liab      NUMERIC(18,2),
    long_term_debt          NUMERIC(18,2),
    lease_liabilities       NUMERIC(18,2),
    contingent_liabilities  NUMERIC(18,2),
    other_non_current_liab  NUMERIC(18,2),
    total_liabilities       NUMERIC(18,2),

    -- Equity
    equity_capital          NUMERIC(18,2),
    preference_capital      NUMERIC(18,2),
    reserves                NUMERIC(18,2),
    retained_earnings       NUMERIC(18,2),
    minority_interest_bs    NUMERIC(18,2),
    total_equity            NUMERIC(18,2),

    -- Derived
    total_debt              NUMERIC(18,2),            -- Short + Long term debt
    net_debt                NUMERIC(18,2),            -- Total debt - Cash
    working_capital         NUMERIC(18,2),            -- Current assets - Current liab
    book_value_per_share    NUMERIC(12,4),
    face_value              NUMERIC(10,4),
    shares_outstanding      BIGINT,

    -- Metadata
    is_restated             BOOLEAN DEFAULT FALSE,
    data_source             VARCHAR(50),

    UNIQUE (asx_code, fiscal_year)
);

CREATE INDEX idx_bs_asx_year ON financials.annual_balance_sheet(asx_code, fiscal_year DESC);
```

---

### 3.3 annual_cashflow

```sql
CREATE TABLE financials.annual_cashflow (
    id                      SERIAL PRIMARY KEY,
    asx_code                VARCHAR(10) NOT NULL,
    fiscal_year             INTEGER NOT NULL,
    period_end_date         DATE NOT NULL,

    -- Cash Flow Statement
    net_income              NUMERIC(18,2),
    depreciation_amort      NUMERIC(18,2),
    working_capital_changes NUMERIC(18,2),
    other_operating         NUMERIC(18,2),
    cfo                     NUMERIC(18,2),            -- Cash From Operations

    capex                   NUMERIC(18,2),            -- Capital expenditure (negative)
    acquisitions            NUMERIC(18,2),
    disposals               NUMERIC(18,2),
    investment_purchases    NUMERIC(18,2),
    other_investing         NUMERIC(18,2),
    cfi                     NUMERIC(18,2),            -- Cash From Investing

    dividends_paid          NUMERIC(18,2),
    debt_raised             NUMERIC(18,2),
    debt_repaid             NUMERIC(18,2),
    equity_raised           NUMERIC(18,2),
    buybacks                NUMERIC(18,2),
    other_financing         NUMERIC(18,2),
    cff                     NUMERIC(18,2),            -- Cash From Financing

    net_change_in_cash      NUMERIC(18,2),
    opening_cash            NUMERIC(18,2),
    closing_cash            NUMERIC(18,2),
    fcf                     NUMERIC(18,2),            -- FCF = CFO + Capex

    is_restated             BOOLEAN DEFAULT FALSE,
    data_source             VARCHAR(50),

    UNIQUE (asx_code, fiscal_year)
);

CREATE INDEX idx_cf_asx_year ON financials.annual_cashflow(asx_code, fiscal_year DESC);
```

---

### 3.4 half_year_pnl — Half-Year Periods (ASX Standard)

```sql
CREATE TABLE financials.half_year_pnl (
    id                      SERIAL PRIMARY KEY,
    asx_code                VARCHAR(10) NOT NULL,
    period_end_date         DATE NOT NULL,
    period_label            VARCHAR(20) NOT NULL,     -- e.g. '1H FY2024', '2H FY2024'
    report_date             DATE,

    revenue                 NUMERIC(18,2),
    gross_profit            NUMERIC(18,2),
    other_income            NUMERIC(18,2),
    ebitda                  NUMERIC(18,2),
    depreciation            NUMERIC(18,2),
    ebit                    NUMERIC(18,2),
    interest_expense        NUMERIC(18,2),
    pbt                     NUMERIC(18,2),
    tax                     NUMERIC(18,2),
    pat                     NUMERIC(18,2),
    net_profit              NUMERIC(18,2),
    extraordinary_items     NUMERIC(18,2),
    equity_capital          NUMERIC(18,2),
    eps                     NUMERIC(12,4),
    opm                     NUMERIC(10,6),
    npm                     NUMERIC(10,6),
    gpm                     NUMERIC(10,6),

    UNIQUE (asx_code, period_end_date)
);

CREATE INDEX idx_halfyear_asx ON financials.half_year_pnl(asx_code, period_end_date DESC);
```

---

### 3.5 mining_data — Quarterly Activity + Reserves

```sql
CREATE TABLE financials.mining_data (
    id                      SERIAL PRIMARY KEY,
    asx_code                VARCHAR(10) NOT NULL,
    report_date             DATE NOT NULL,
    report_type             VARCHAR(30),              -- 'reserves', 'qar', 'annual'

    -- Commodity
    primary_commodity       VARCHAR(100),
    secondary_commodity     VARCHAR(100),

    -- Ore Reserves (tonnes & grade)
    reserves_proven_kt      NUMERIC(18,2),
    reserves_probable_kt    NUMERIC(18,2),
    total_reserves_kt       NUMERIC(18,2),
    reserves_grade          NUMERIC(10,4),
    reserves_contained_oz   NUMERIC(18,2),            -- For gold: contained ounces

    -- Resources
    resources_measured_kt   NUMERIC(18,2),
    resources_indicated_kt  NUMERIC(18,2),
    resources_inferred_kt   NUMERIC(18,2),
    total_resources_kt      NUMERIC(18,2),

    -- Production (quarterly)
    production_qty          NUMERIC(18,2),
    production_unit         VARCHAR(20),              -- 'koz', 'kt', 'bbl'
    production_guidance_low NUMERIC(18,2),
    production_guidance_high NUMERIC(18,2),

    -- Costs
    aisc_per_oz             NUMERIC(12,2),            -- All-in sustaining cost AUD
    c1_cost_per_oz          NUMERIC(12,2),
    operating_cost_per_t    NUMERIC(12,2),

    -- Life of mine
    reserve_life_years      NUMERIC(8,2),
    mine_life_years         NUMERIC(8,2),

    -- Hedging
    hedged_oz               NUMERIC(18,2),
    hedging_pct             NUMERIC(8,4),
    hedge_price             NUMERIC(12,2),

    UNIQUE (asx_code, report_date, report_type)
);
```

---

### 3.6 reit_data

```sql
CREATE TABLE financials.reit_data (
    id                      SERIAL PRIMARY KEY,
    asx_code                VARCHAR(10) NOT NULL,
    report_date             DATE NOT NULL,
    period_label            VARCHAR(20),

    -- Core REIT Metrics
    ffo                     NUMERIC(18,2),            -- Funds From Operations (AUD M)
    ffo_per_unit            NUMERIC(12,4),
    affo                    NUMERIC(18,2),            -- Adjusted FFO
    affo_per_unit           NUMERIC(12,4),

    -- NTA
    nta_total               NUMERIC(18,2),            -- Net Tangible Assets (AUD M)
    nta_per_unit            NUMERIC(12,4),
    intangibles_written_off NUMERIC(18,2),

    -- Portfolio
    portfolio_value         NUMERIC(18,2),            -- AUD millions
    property_count          INTEGER,
    property_type           VARCHAR(50),              -- retail/office/industrial/mixed
    geographic_split        JSONB,                    -- {"AU": 80, "NZ": 20}

    -- Leverage
    gearing_ratio           NUMERIC(8,4),             -- Debt / Total Assets
    look_through_gearing    NUMERIC(8,4),

    -- Leasing
    wale_years              NUMERIC(8,2),             -- Weighted Avg Lease Expiry
    wale_by_income          NUMERIC(8,2),
    occupancy_pct           NUMERIC(8,4),
    cap_rate                NUMERIC(8,4),

    -- Interest rate risk
    fixed_rate_debt_pct     NUMERIC(8,4),
    weighted_avg_debt_cost  NUMERIC(8,4),
    weighted_avg_debt_term  NUMERIC(8,2),

    UNIQUE (asx_code, report_date)
);
```

---

## 4. Schema: users

### 4.1 users

```sql
CREATE TABLE users.users (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email                   VARCHAR(255) NOT NULL UNIQUE,
    name                    VARCHAR(255),
    avatar_url              VARCHAR(500),
    plan                    VARCHAR(20) NOT NULL DEFAULT 'free',
    -- Plans: free, pro, premium, enterprise

    -- Auth
    password_hash           VARCHAR(255),             -- Null if OAuth-only
    email_verified          BOOLEAN DEFAULT FALSE,
    email_verified_at       TIMESTAMPTZ,

    -- OAuth
    google_id               VARCHAR(100) UNIQUE,

    -- Billing
    stripe_customer_id      VARCHAR(100) UNIQUE,
    subscription_status     VARCHAR(30) DEFAULT 'inactive',
    subscription_ends_at    TIMESTAMPTZ,

    -- Preferences
    default_currency        VARCHAR(3) DEFAULT 'AUD',
    default_columns         JSONB,                    -- Saved column preferences
    timezone                VARCHAR(50) DEFAULT 'Australia/Sydney',
    email_alerts_enabled    BOOLEAN DEFAULT TRUE,
    push_alerts_enabled     BOOLEAN DEFAULT TRUE,

    -- Usage limits (enforced by API)
    screens_saved           INTEGER DEFAULT 0,
    screens_limit           INTEGER DEFAULT 10,       -- Free: 10, Pro: unlimited
    watchlist_items         INTEGER DEFAULT 0,
    watchlist_limit         INTEGER DEFAULT 50,

    -- Metadata
    last_login_at           TIMESTAMPTZ,
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    updated_at              TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_users_email  ON users.users(email);
CREATE INDEX idx_users_stripe ON users.users(stripe_customer_id);
CREATE INDEX idx_users_plan   ON users.users(plan);
```

---

### 4.2 watchlists & watchlist_items

```sql
CREATE TABLE users.watchlists (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                 UUID NOT NULL REFERENCES users.users(id) ON DELETE CASCADE,
    name                    VARCHAR(100) NOT NULL,
    description             VARCHAR(500),
    is_public               BOOLEAN DEFAULT FALSE,
    public_slug             VARCHAR(100) UNIQUE,
    item_count              INTEGER DEFAULT 0,
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    updated_at              TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE users.watchlist_items (
    id                      BIGSERIAL PRIMARY KEY,
    watchlist_id            UUID NOT NULL REFERENCES users.watchlists(id) ON DELETE CASCADE,
    asx_code                VARCHAR(10) NOT NULL,
    added_at                TIMESTAMPTZ DEFAULT NOW(),
    notes                   TEXT,
    target_price            NUMERIC(12,4),
    UNIQUE (watchlist_id, asx_code)
);

CREATE INDEX idx_watchlist_user ON users.watchlists(user_id);
CREATE INDEX idx_wl_items_list  ON users.watchlist_items(watchlist_id);
CREATE INDEX idx_wl_items_code  ON users.watchlist_items(asx_code);
```

---

### 4.3 portfolios & portfolio_transactions

```sql
CREATE TABLE users.portfolios (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                 UUID NOT NULL REFERENCES users.users(id) ON DELETE CASCADE,
    name                    VARCHAR(100) NOT NULL,
    description             VARCHAR(500),
    currency                VARCHAR(3) DEFAULT 'AUD',
    benchmark               VARCHAR(20) DEFAULT 'XJO',  -- ASX200 index code
    is_smsf                 BOOLEAN DEFAULT FALSE,
    created_at              TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE users.portfolio_transactions (
    id                      BIGSERIAL PRIMARY KEY,
    portfolio_id            UUID NOT NULL REFERENCES users.portfolios(id) ON DELETE CASCADE,
    asx_code                VARCHAR(10) NOT NULL,
    transaction_type        VARCHAR(20) NOT NULL,     -- buy, sell, drp, split, dividend
    transaction_date        DATE NOT NULL,
    shares                  NUMERIC(18,4) NOT NULL,   -- Decimal for DRP
    price_per_share         NUMERIC(12,4) NOT NULL,
    brokerage               NUMERIC(10,2) DEFAULT 0,
    total_cost              NUMERIC(18,2),            -- Computed: shares*price+brokerage
    notes                   VARCHAR(500),

    -- For dividend transactions
    franking_credit_amt     NUMERIC(10,4),
    is_drp                  BOOLEAN DEFAULT FALSE,

    created_at              TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_portfolio_user   ON users.portfolios(user_id);
CREATE INDEX idx_portfolio_txn    ON users.portfolio_transactions(portfolio_id, transaction_date DESC);
CREATE INDEX idx_portfolio_asx    ON users.portfolio_transactions(asx_code);
```

---

### 4.4 saved_screens

```sql
CREATE TABLE users.saved_screens (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                 UUID NOT NULL REFERENCES users.users(id) ON DELETE CASCADE,
    name                    VARCHAR(200) NOT NULL,
    description             VARCHAR(1000),
    query_text              TEXT NOT NULL,            -- Raw user query string
    query_sql               TEXT,                     -- Compiled SQL (cached)
    default_columns         JSONB,                    -- Column preferences for results
    default_sort_col        VARCHAR(100),
    default_sort_dir        VARCHAR(4) DEFAULT 'DESC',

    -- Community
    is_public               BOOLEAN DEFAULT FALSE,
    public_slug             VARCHAR(100) UNIQUE,
    tags                    TEXT[],                   -- ['value', 'dividend', 'asx200']
    likes_count             INTEGER DEFAULT 0,
    run_count               INTEGER DEFAULT 0,
    fork_of_screen_id       UUID REFERENCES users.saved_screens(id),

    -- Alert
    has_alert               BOOLEAN DEFAULT FALSE,
    last_run_at             TIMESTAMPTZ,
    last_result_count       INTEGER,

    created_at              TIMESTAMPTZ DEFAULT NOW(),
    updated_at              TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_screens_user    ON users.saved_screens(user_id);
CREATE INDEX idx_screens_public  ON users.saved_screens(is_public) WHERE is_public = TRUE;
CREATE INDEX idx_screens_tags    ON users.saved_screens USING GIN(tags);
CREATE INDEX idx_screens_slug    ON users.saved_screens(public_slug) WHERE public_slug IS NOT NULL;
```

---

### 4.5 alerts & alert_triggers

```sql
CREATE TABLE users.alerts (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                 UUID NOT NULL REFERENCES users.users(id) ON DELETE CASCADE,
    alert_type              VARCHAR(30) NOT NULL,
    -- Types: price_above, price_below, screen_match, screen_exit,
    --        new_announcement, earnings_released, ex_div, insider_trade,
    --        short_interest_above, short_interest_increase

    -- For stock-level alerts
    asx_code                VARCHAR(10),
    threshold_value         NUMERIC(18,4),

    -- For screen alerts
    screen_id               UUID REFERENCES users.saved_screens(id) ON DELETE CASCADE,

    -- Delivery
    via_email               BOOLEAN DEFAULT TRUE,
    via_push                BOOLEAN DEFAULT TRUE,
    is_active               BOOLEAN DEFAULT TRUE,

    last_triggered_at       TIMESTAMPTZ,
    trigger_count           INTEGER DEFAULT 0,
    created_at              TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE users.alert_triggers (
    id                      BIGSERIAL PRIMARY KEY,
    alert_id                UUID NOT NULL REFERENCES users.alerts(id) ON DELETE CASCADE,
    triggered_at            TIMESTAMPTZ DEFAULT NOW(),
    trigger_data            JSONB,                    -- What caused the trigger
    notification_sent       BOOLEAN DEFAULT FALSE,
    notification_sent_at    TIMESTAMPTZ
);

CREATE INDEX idx_alerts_user    ON users.alerts(user_id);
CREATE INDEX idx_alerts_active  ON users.alerts(is_active) WHERE is_active = TRUE;
CREATE INDEX idx_alerts_screen  ON users.alerts(screen_id) WHERE screen_id IS NOT NULL;
```

---

### 4.6 user_notes

```sql
CREATE TABLE users.user_notes (
    id                      BIGSERIAL PRIMARY KEY,
    user_id                 UUID NOT NULL REFERENCES users.users(id) ON DELETE CASCADE,
    asx_code                VARCHAR(10) NOT NULL,
    content                 TEXT,
    attachments             JSONB,                    -- S3 keys for uploaded files
    updated_at              TIMESTAMPTZ DEFAULT NOW(),
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (user_id, asx_code)
);
```

---

### 4.7 user_custom_ratios

```sql
CREATE TABLE users.user_custom_ratios (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                 UUID NOT NULL REFERENCES users.users(id) ON DELETE CASCADE,
    name                    VARCHAR(100) NOT NULL,
    formula                 TEXT NOT NULL,
    -- e.g. "(revenue_ttm - cost_of_sales) / total_assets"
    description             VARCHAR(500),
    is_public               BOOLEAN DEFAULT FALSE,
    validated               BOOLEAN DEFAULT FALSE,    -- Has formula been validated
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (user_id, name)
);
```

---

## 5. Schema: ai

```sql
CREATE TABLE ai.document_chunks (
    id                      BIGSERIAL PRIMARY KEY,
    asx_code                VARCHAR(10) NOT NULL,
    document_type           VARCHAR(50),              -- annual_report, concall, presentation
    document_year           INTEGER,
    s3_key                  VARCHAR(500),
    chunk_index             INTEGER,
    chunk_text              TEXT NOT NULL,
    embedding               vector(1536),             -- pgvector embedding
    page_number             INTEGER,
    section_heading         VARCHAR(500),
    created_at              TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_chunks_asx      ON ai.document_chunks(asx_code, document_year DESC);
CREATE INDEX idx_chunks_vector   ON ai.document_chunks USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

CREATE TABLE ai.ai_insights (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asx_code                VARCHAR(10) NOT NULL,
    user_id                 UUID REFERENCES users.users(id),
    question                TEXT,
    answer                  TEXT NOT NULL,
    model_used              VARCHAR(50),
    source_chunks           INTEGER[],                -- chunk IDs used
    is_public               BOOLEAN DEFAULT FALSE,
    created_at              TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE ai.concall_summaries (
    id                      SERIAL PRIMARY KEY,
    asx_code                VARCHAR(10) NOT NULL,
    event_date              DATE NOT NULL,
    event_type              VARCHAR(50),              -- 'results_call', 'agm', 'investor_day'
    summary_text            TEXT,
    key_points              JSONB,                    -- ["point1", "point2"]
    sentiment               VARCHAR(20),
    guidance_updated        BOOLEAN DEFAULT FALSE,
    guidance_direction      VARCHAR(20),              -- 'up', 'down', 'maintained', 'withdrawn'
    s3_transcript_key       VARCHAR(500),
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (asx_code, event_date, event_type)
);
```

---

## 6. Key Database Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Primary DB | PostgreSQL 16 | ACID, rich SQL, ecosystem |
| Time-series | TimescaleDB extension | Auto-partitioning, compression, continuous aggregates |
| Price partitioning | Weekly chunks | Balance between chunk overhead and query parallelism |
| Compression policy | After 3 months | Active data stays uncompressed, old data saves 90%+ space |
| UUIDs for user tables | `gen_random_uuid()` | No sequential ID leakage, safe for public URLs |
| JSONB for flexible data | `ai_key_points`, `geographic_split` | Schema flexibility without sacrificing queryability |
| pgvector | In-database embeddings | No separate vector DB needed; SQL joins work naturally |
| Separate schemas | `market`, `financials`, `users`, `ai` | Logical separation, easier permission management |
| Computed metrics stored | Yes (denormalised) | Screener speed — no on-the-fly joins needed |
| Growth rates stored | Yes | Pre-compute CAGR — complex, CPU-intensive at query time |

---

## 7. Estimated Storage Requirements

| Table | Rows (3 years) | Storage |
|---|---|---|
| daily_prices | 2,200 stocks × 750 days = 1.65M rows | ~600 MB raw, ~50 MB compressed |
| technical_indicators | 1.65M rows | ~1 GB raw, ~80 MB compressed |
| computed_metrics | 1.65M rows | ~2 GB raw, ~150 MB compressed |
| annual_pnl | 2,200 × 10 years = 22K rows | ~30 MB |
| annual_balance_sheet | 22K rows | ~30 MB |
| annual_cashflow | 22K rows | ~20 MB |
| half_year_pnl | 44K rows | ~40 MB |
| asx_announcements | ~500K rows | ~2 GB (with AI summaries) |
| document_chunks + vectors | ~5M rows | ~10 GB |
| **Total (3 years)** | | **~15–20 GB** |

At Phase 3 scale (10 years, full ASX): ~100–150 GB — well within a single PostgreSQL instance.

---

*Next: See `03_Data_Pipeline_LLD.md` for the ingestion pipeline design*
