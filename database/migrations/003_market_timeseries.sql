-- ─────────────────────────────────────────────────────────────
--  Migration 003 — TimescaleDB Hypertables
--  daily_prices · technical_indicators · computed_metrics
--  short_interest
-- ─────────────────────────────────────────────────────────────

-- ── market.daily_prices ───────────────────────────────────────

CREATE TABLE market.daily_prices (
    time                    TIMESTAMPTZ  NOT NULL,   -- Market close time (AEST)
    asx_code                VARCHAR(10)  NOT NULL,
    open                    NUMERIC(12,4),
    high                    NUMERIC(12,4),
    low                     NUMERIC(12,4),
    close                   NUMERIC(12,4) NOT NULL,
    adjusted_close          NUMERIC(12,4),           -- Dividend/split adjusted
    volume                  BIGINT,
    value_traded            NUMERIC(18,2),           -- AUD value
    trades_count            INTEGER,
    vwap                    NUMERIC(12,4),
    data_source             VARCHAR(30) DEFAULT 'yahoo',
    PRIMARY KEY (time, asx_code)
);

SELECT create_hypertable('market.daily_prices', 'time',
    chunk_time_interval => INTERVAL '1 week',
    if_not_exists => TRUE
);

ALTER TABLE market.daily_prices SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'asx_code',
    timescaledb.compress_orderby   = 'time DESC'
);
SELECT add_compression_policy('market.daily_prices', INTERVAL '3 months');

CREATE INDEX idx_daily_prices_asx_time ON market.daily_prices(asx_code, time DESC);

-- Continuous aggregate: weekly OHLCV
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
GROUP BY week, asx_code
WITH NO DATA;

SELECT add_continuous_aggregate_policy('market.weekly_prices',
    start_offset      => INTERVAL '3 weeks',
    end_offset        => INTERVAL '1 hour',
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
GROUP BY month, asx_code
WITH NO DATA;

SELECT add_continuous_aggregate_policy('market.monthly_prices',
    start_offset      => INTERVAL '2 months',
    end_offset        => INTERVAL '1 day',
    schedule_interval => INTERVAL '1 week'
);

-- ── market.technical_indicators ───────────────────────────────

CREATE TABLE market.technical_indicators (
    time                        TIMESTAMPTZ NOT NULL,
    asx_code                    VARCHAR(10) NOT NULL,

    -- Moving averages
    dma_20                      NUMERIC(12,4),
    dma_50                      NUMERIC(12,4),
    dma_200                     NUMERIC(12,4),
    dma_50_prev                 NUMERIC(12,4),
    dma_200_prev                NUMERIC(12,4),
    ema_12                      NUMERIC(12,4),
    ema_26                      NUMERIC(12,4),

    -- MACD
    macd                        NUMERIC(12,6),
    macd_signal                 NUMERIC(12,6),
    macd_histogram              NUMERIC(12,6),
    macd_prev                   NUMERIC(12,6),
    macd_signal_prev            NUMERIC(12,6),

    -- Momentum
    rsi_14                      NUMERIC(6,2),
    stoch_rsi                   NUMERIC(6,2),
    adx_14                      NUMERIC(6,2),

    -- Volatility
    atr_14                      NUMERIC(12,4),
    bollinger_upper             NUMERIC(12,4),
    bollinger_lower             NUMERIC(12,4),
    bollinger_mid               NUMERIC(12,4),
    bollinger_pct               NUMERIC(6,4),
    historical_volatility_20    NUMERIC(8,4),

    -- Volume
    volume                      BIGINT,
    volume_avg_5d               BIGINT,
    volume_avg_20d              BIGINT,
    volume_avg_60d              BIGINT,
    volume_ratio                NUMERIC(8,4),
    obv                         BIGINT,

    -- 52-week / All-time levels
    high_52w                    NUMERIC(12,4),
    low_52w                     NUMERIC(12,4),
    high_all_time               NUMERIC(12,4),
    low_all_time                NUMERIC(12,4),
    pct_from_52w_high           NUMERIC(8,4),
    pct_from_52w_low            NUMERIC(8,4),
    pct_from_ath                NUMERIC(8,4),
    pct_from_atl                NUMERIC(8,4),
    range_52w_position          NUMERIC(6,4),
    dma_50_ratio                NUMERIC(8,4),
    dma_200_ratio               NUMERIC(8,4),

    -- Returns (as decimal, e.g. 0.05 = 5%)
    return_1d                   NUMERIC(10,6),
    return_1w                   NUMERIC(10,6),
    return_1m                   NUMERIC(10,6),
    return_3m                   NUMERIC(10,6),
    return_6m                   NUMERIC(10,6),
    return_1y                   NUMERIC(10,6),
    return_3y                   NUMERIC(10,6),
    return_5y                   NUMERIC(10,6),

    -- Signals
    golden_cross                BOOLEAN,
    death_cross                 BOOLEAN,
    new_52w_high                BOOLEAN,
    new_52w_low                 BOOLEAN,
    above_dma_50                BOOLEAN,
    above_dma_200               BOOLEAN,

    PRIMARY KEY (time, asx_code)
);

SELECT create_hypertable('market.technical_indicators', 'time',
    chunk_time_interval => INTERVAL '1 month',
    if_not_exists => TRUE
);

ALTER TABLE market.technical_indicators SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'asx_code',
    timescaledb.compress_orderby   = 'time DESC'
);
SELECT add_compression_policy('market.technical_indicators', INTERVAL '6 months');

CREATE INDEX idx_tech_asx_time ON market.technical_indicators(asx_code, time DESC);

-- ── market.computed_metrics ───────────────────────────────────
-- Core screener table — one row per stock per trading day.
-- Populated entirely by the Compute Engine after market close.

CREATE TABLE market.computed_metrics (
    time                        TIMESTAMPTZ NOT NULL,
    asx_code                    VARCHAR(10) NOT NULL,

    -- ── Valuation ─────────────────────────────────────────────
    market_cap                  NUMERIC(18,2),   -- AUD millions
    enterprise_value            NUMERIC(18,2),
    pe_ratio                    NUMERIC(12,4),
    pe_forward                  NUMERIC(12,4),
    pb_ratio                    NUMERIC(12,4),
    ps_ratio                    NUMERIC(12,4),
    pcf_ratio                   NUMERIC(12,4),
    pfcf_ratio                  NUMERIC(12,4),
    ev_ebitda                   NUMERIC(12,4),
    ev_ebit                     NUMERIC(12,4),
    ev_sales                    NUMERIC(12,4),
    ev_fcf                      NUMERIC(12,4),
    peg_ratio                   NUMERIC(12,4),
    earnings_yield              NUMERIC(10,6),
    fcf_yield                   NUMERIC(10,6),
    dividend_yield              NUMERIC(10,6),
    grossed_up_yield            NUMERIC(10,6),
    graham_number               NUMERIC(12,4),
    ncavps                      NUMERIC(12,4),
    pb_x_pe                     NUMERIC(12,4),

    -- ── Profitability ─────────────────────────────────────────
    roe                         NUMERIC(10,6),
    roa                         NUMERIC(10,6),
    roce                        NUMERIC(10,6),
    roic                        NUMERIC(10,6),
    croic                       NUMERIC(10,6),
    opm                         NUMERIC(10,6),
    npm                         NUMERIC(10,6),
    gpm                         NUMERIC(10,6),
    ebitda_margin               NUMERIC(10,6),
    ebit_margin                 NUMERIC(10,6),
    earning_power               NUMERIC(10,6),

    -- ── Efficiency ───────────────────────────────────────────
    asset_turnover              NUMERIC(10,6),
    inventory_turnover          NUMERIC(10,6),
    receivables_turnover        NUMERIC(10,6),
    payables_turnover           NUMERIC(10,6),
    working_capital_turnover    NUMERIC(10,6),
    debtor_days                 NUMERIC(10,2),
    dpo                         NUMERIC(10,2),
    dio                         NUMERIC(10,2),
    cash_conversion_cycle       NUMERIC(10,2),
    working_capital_days        NUMERIC(10,2),

    -- ── Growth ───────────────────────────────────────────────
    revenue_growth_1y           NUMERIC(10,6),
    revenue_growth_3y           NUMERIC(10,6),
    revenue_growth_5y           NUMERIC(10,6),
    revenue_growth_7y           NUMERIC(10,6),
    revenue_growth_10y          NUMERIC(10,6),
    profit_growth_1y            NUMERIC(10,6),
    profit_growth_3y            NUMERIC(10,6),
    profit_growth_5y            NUMERIC(10,6),
    profit_growth_7y            NUMERIC(10,6),
    profit_growth_10y           NUMERIC(10,6),
    eps_growth_1y               NUMERIC(10,6),
    eps_growth_3y               NUMERIC(10,6),
    eps_growth_5y               NUMERIC(10,6),
    eps_growth_7y               NUMERIC(10,6),
    eps_growth_10y              NUMERIC(10,6),
    ebitda_growth_3y            NUMERIC(10,6),
    ebitda_growth_5y            NUMERIC(10,6),
    fcf_growth_3y               NUMERIC(10,6),
    fcf_growth_5y               NUMERIC(10,6),
    mcap_growth_3y              NUMERIC(10,6),
    mcap_growth_5y              NUMERIC(10,6),
    roe_avg_3y                  NUMERIC(10,6),
    roe_avg_5y                  NUMERIC(10,6),
    roe_avg_7y                  NUMERIC(10,6),
    roe_avg_10y                 NUMERIC(10,6),
    roce_avg_3y                 NUMERIC(10,6),
    roce_avg_5y                 NUMERIC(10,6),
    roce_avg_7y                 NUMERIC(10,6),
    roce_avg_10y                NUMERIC(10,6),
    opm_avg_5y                  NUMERIC(10,6),
    opm_avg_10y                 NUMERIC(10,6),
    rev_qoq_growth              NUMERIC(10,6),
    profit_qoq_growth           NUMERIC(10,6),
    rev_sequential_growth       NUMERIC(10,6),
    profit_sequential_growth    NUMERIC(10,6),

    -- ── Financial Health ─────────────────────────────────────
    debt_to_equity              NUMERIC(10,4),
    net_debt_to_ebitda          NUMERIC(10,4),
    net_debt_to_equity          NUMERIC(10,4),
    debt_to_assets              NUMERIC(10,4),
    interest_coverage           NUMERIC(10,4),
    current_ratio               NUMERIC(10,4),
    quick_ratio                 NUMERIC(10,4),
    cash_ratio                  NUMERIC(10,4),
    working_capital             NUMERIC(18,2),
    financial_leverage          NUMERIC(10,4),
    debt_capacity               NUMERIC(18,2),
    leverage_ratio              NUMERIC(10,4),

    -- ── Cash Flow ────────────────────────────────────────────
    fcf                         NUMERIC(18,2),   -- AUD millions TTM
    fcf_per_share               NUMERIC(12,4),
    ocf_to_net_income           NUMERIC(10,4),
    capex_to_sales              NUMERIC(10,6),
    ocf_to_debt                 NUMERIC(10,6),
    ocf_margin                  NUMERIC(10,6),

    -- ── Dividends ────────────────────────────────────────────
    dividend_per_share          NUMERIC(10,4),
    franking_pct                NUMERIC(6,2),
    grossed_up_dividend         NUMERIC(10,4),
    dividend_payout_ratio       NUMERIC(10,6),
    dividend_avg_5y             NUMERIC(10,4),
    dividend_growth_3y          NUMERIC(10,6),

    -- ── Quality Scores ───────────────────────────────────────
    piotroski_score             SMALLINT,
    g_factor                    NUMERIC(10,4),
    altman_z_score              NUMERIC(10,4),
    beneish_m_score             NUMERIC(10,4),
    beta_1y                     NUMERIC(8,4),
    beta_3y                     NUMERIC(8,4),
    sharpe_1y                   NUMERIC(8,4),
    sortino_1y                  NUMERIC(8,4),
    max_drawdown_1y             NUMERIC(8,4),
    max_drawdown_3y             NUMERIC(8,4),
    fall_ratio                  NUMERIC(8,4),

    -- ── Per Share ────────────────────────────────────────────
    eps_ttm                     NUMERIC(12,4),
    eps_last_year               NUMERIC(12,4),
    eps_preceding_year          NUMERIC(12,4),
    book_value_per_share        NUMERIC(12,4),

    -- ── Shareholding ─────────────────────────────────────────
    director_holding_pct        NUMERIC(8,4),
    institutional_pct           NUMERIC(8,4),
    retail_pct                  NUMERIC(8,4),
    short_interest_pct          NUMERIC(8,4),
    short_interest_change_1w    NUMERIC(8,4),
    short_interest_change_1m    NUMERIC(8,4),

    -- ── ASX-Specific: Mining ──────────────────────────────────
    aisc_per_oz                 NUMERIC(12,2),
    reserve_life_years          NUMERIC(8,2),
    nav_per_share               NUMERIC(12,4),

    -- ── ASX-Specific: REIT ───────────────────────────────────
    ffo_per_unit                NUMERIC(12,4),
    affo_per_unit               NUMERIC(12,4),
    nta_per_unit                NUMERIC(12,4),
    price_to_nta                NUMERIC(10,4),
    gearing_ratio               NUMERIC(8,4),
    wale_years                  NUMERIC(8,2),
    occupancy_pct               NUMERIC(8,4),
    ffo_yield                   NUMERIC(10,6),

    -- ── Advanced Valuation ───────────────────────────────────
    ev_per_employee             NUMERIC(12,2),
    mcap_to_sales               NUMERIC(10,4),
    mcap_to_cashflow            NUMERIC(10,4),
    mcap_to_quarterly_profit    NUMERIC(10,4),
    intrinsic_value             NUMERIC(12,4),
    price_to_intrinsic_value    NUMERIC(10,4),

    -- ── TTM Reference Values (for screener filters) ───────────
    revenue_ttm                 NUMERIC(18,2),
    ebitda_ttm                  NUMERIC(18,2),
    ebit_ttm                    NUMERIC(18,2),
    net_profit_ttm              NUMERIC(18,2),
    eps_ttm_ref                 NUMERIC(12,4),

    -- ── Compute Metadata ─────────────────────────────────────
    compute_version             VARCHAR(20),
    computed_at                 TIMESTAMPTZ DEFAULT NOW(),

    PRIMARY KEY (time, asx_code)
);

SELECT create_hypertable('market.computed_metrics', 'time',
    chunk_time_interval => INTERVAL '1 month',
    if_not_exists => TRUE
);

ALTER TABLE market.computed_metrics SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'asx_code',
    timescaledb.compress_orderby   = 'time DESC'
);
SELECT add_compression_policy('market.computed_metrics', INTERVAL '6 months');

-- Primary screener index — covers most common filter columns
CREATE INDEX idx_cm_screener ON market.computed_metrics(time DESC, asx_code)
    INCLUDE (market_cap, pe_ratio, pb_ratio, roe, roce, debt_to_equity,
             dividend_yield, grossed_up_yield, franking_pct,
             revenue_growth_3y, profit_growth_3y,
             piotroski_score, altman_z_score, short_interest_pct);

CREATE INDEX idx_cm_asx_time ON market.computed_metrics(asx_code, time DESC);

-- ── market.short_interest ─────────────────────────────────────
-- Loaded daily from ASIC short-sales CSV (published with 2-day lag)

CREATE TABLE market.short_interest (
    time                        TIMESTAMPTZ NOT NULL,
    asx_code                    VARCHAR(10) NOT NULL,
    gross_short_position        BIGINT,
    total_product_short_pct     NUMERIC(8,4),
    gross_short_sales           BIGINT,
    reported_short_pct          NUMERIC(8,4),
    PRIMARY KEY (time, asx_code)
);

SELECT create_hypertable('market.short_interest', 'time',
    chunk_time_interval => INTERVAL '1 month',
    if_not_exists => TRUE
);

ALTER TABLE market.short_interest SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'asx_code',
    timescaledb.compress_orderby   = 'time DESC'
);
SELECT add_compression_policy('market.short_interest', INTERVAL '3 months');

CREATE INDEX idx_short_asx_time ON market.short_interest(asx_code, time DESC);
