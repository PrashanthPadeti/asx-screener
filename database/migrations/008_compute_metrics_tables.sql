-- ─────────────────────────────────────────────────────────────
--  Migration 008 — Compute Metrics Tables
--  Separate table per compute frequency so jobs never touch
--  each other's data during compute runs.
--
--  Execution sequence (each depends on prior being complete):
--    Seq 2  market.yearly_metrics
--    Seq 3  market.halfyearly_metrics
--    Seq 4  market.quarterly_metrics
--    Seq 5  market.monthly_metrics
--    Seq 6  market.weekly_metrics
--    Seq 7  market.daily_metrics   ← TimescaleDB hypertable
--
--  Source tables (raw, never modified by compute):
--    financials.annual_pnl
--    financials.annual_balance_sheet
--    financials.annual_cashflow
--    financials.half_year_pnl
--    market.daily_prices
-- ─────────────────────────────────────────────────────────────


-- ═════════════════════════════════════════════════════════════
--  SEQ 2  market.yearly_metrics
--  One row per (asx_code, fiscal_year).
--  Recomputed quarterly when new annual results arrive
--  (Feb / May / Aug / Nov earnings seasons).
--  Contains: computed ratios, CAGRs, multi-year averages.
--  Does NOT duplicate raw financials (those stay in financials.*)
-- ═════════════════════════════════════════════════════════════

CREATE TABLE market.yearly_metrics (
    asx_code                VARCHAR(10)  NOT NULL,
    fiscal_year             SMALLINT     NOT NULL,   -- e.g. 2024
    period_end_date         DATE         NOT NULL,   -- e.g. 2024-06-30
    price_at_compute        NUMERIC(12,4),           -- closing price used for ratio calcs

    -- ── Market Size ───────────────────────────────────────────
    market_cap              NUMERIC(18,2),           -- AUD millions
    enterprise_value        NUMERIC(18,2),           -- AUD millions
    shares_outstanding      BIGINT,

    -- ── Valuation Ratios ──────────────────────────────────────
    pe_ratio                NUMERIC(10,2),
    pb_ratio                NUMERIC(10,2),
    ps_ratio                NUMERIC(10,2),
    pcf_ratio               NUMERIC(10,2),           -- price / OCF per share
    p_fcf_ratio             NUMERIC(10,2),           -- price / FCF per share
    ev_ebitda               NUMERIC(10,2),
    ev_ebit                 NUMERIC(10,2),
    ev_revenue              NUMERIC(10,2),
    ev_fcf                  NUMERIC(10,2),
    peg_ratio               NUMERIC(10,4),
    earnings_yield          NUMERIC(8,4),            -- EPS / price (%)
    fcf_yield               NUMERIC(8,4),            -- FCF/share / price (%)
    graham_number           NUMERIC(12,4),           -- √(22.5 × EPS × BVPS)
    ncavps                  NUMERIC(12,4),           -- Net Current Asset Value per share
    pe_5y_avg               NUMERIC(10,2),           -- 5-year average P/E

    -- ── Per Share ─────────────────────────────────────────────
    eps                     NUMERIC(10,4),
    eps_diluted             NUMERIC(10,4),
    bvps                    NUMERIC(10,4),           -- book value per share
    tbvps                   NUMERIC(10,4),           -- tangible book value per share
    dps                     NUMERIC(10,4),           -- dividends per share
    dps_grossed_up          NUMERIC(10,4),           -- DPS grossed up with franking credit
    franking_pct            NUMERIC(5,2),            -- 0–100
    fcf_per_share           NUMERIC(10,4),
    ocf_per_share           NUMERIC(10,4),
    revenue_per_share       NUMERIC(10,4),
    net_debt_per_share      NUMERIC(10,4),

    -- ── Dividend Metrics ──────────────────────────────────────
    dividend_yield          NUMERIC(8,4),            -- DPS / price (%)
    franked_yield           NUMERIC(8,4),            -- grossed-up yield (%)
    payout_ratio            NUMERIC(8,4),            -- DPS / EPS
    dividend_cagr_3y        NUMERIC(8,4),
    dividend_cagr_5y        NUMERIC(8,4),
    dividend_consecutive_yrs SMALLINT,               -- years of uninterrupted dividends

    -- ── Return on Capital ─────────────────────────────────────
    -- NUMERIC(18,6): ASX small-caps can have extreme ratios — use wide type throughout
    roe                     NUMERIC(18,6),           -- net_income / avg_equity
    roa                     NUMERIC(18,6),           -- net_income / avg_assets
    roic                    NUMERIC(18,6),           -- EBIT(1-t) / invested_capital
    roce                    NUMERIC(18,6),           -- EBIT / capital_employed
    roae                    NUMERIC(18,6),           -- return on average equity
    roaa                    NUMERIC(18,6),           -- return on average assets
    croic                   NUMERIC(18,6),           -- cash ROIC (FCF / invested_capital)

    -- ── Margin Ratios ─────────────────────────────────────────
    gross_margin            NUMERIC(18,6),
    ebitda_margin           NUMERIC(18,6),
    ebit_margin             NUMERIC(18,6),           -- operating profit margin (OPM)
    pretax_margin           NUMERIC(18,6),
    net_margin              NUMERIC(18,6),
    ocf_margin              NUMERIC(18,6),
    fcf_margin              NUMERIC(18,6),
    tax_rate_effective      NUMERIC(18,6),

    -- ── Efficiency ────────────────────────────────────────────
    asset_turnover          NUMERIC(18,6),
    inventory_turnover      NUMERIC(18,6),
    receivables_turnover    NUMERIC(18,6),
    receivables_days        NUMERIC(18,6),           -- DSO
    inventory_days          NUMERIC(18,6),           -- DIO
    payables_days           NUMERIC(18,6),           -- DPO
    cash_conversion_cycle   NUMERIC(18,6),
    capex_intensity         NUMERIC(18,6),           -- capex / revenue
    revenue_per_employee    NUMERIC(18,2),

    -- ── Leverage & Liquidity ──────────────────────────────────
    current_ratio           NUMERIC(18,6),
    quick_ratio             NUMERIC(18,6),
    cash_ratio              NUMERIC(18,6),
    debt_to_equity          NUMERIC(18,6),
    debt_to_assets          NUMERIC(18,6),
    debt_to_ebitda          NUMERIC(18,6),
    net_debt_to_ebitda      NUMERIC(18,6),
    net_debt_to_equity      NUMERIC(18,6),
    interest_coverage       NUMERIC(18,6),
    equity_multiplier       NUMERIC(18,6),
    lt_debt_to_capital      NUMERIC(18,6),

    -- ── Quality Scores ────────────────────────────────────────
    piotroski_f_score       SMALLINT,               -- 0–9
    altman_z_score          NUMERIC(18,6),
    beneish_m_score         NUMERIC(18,6),

    -- ── 1-Year Growth (YoY) ───────────────────────────────────
    revenue_growth_1y       NUMERIC(18,6),
    gross_profit_growth_1y  NUMERIC(18,6),
    ebitda_growth_1y        NUMERIC(18,6),
    ebit_growth_1y          NUMERIC(18,6),
    net_income_growth_1y    NUMERIC(18,6),
    eps_growth_1y           NUMERIC(18,6),
    ocf_growth_1y           NUMERIC(18,6),
    fcf_growth_1y           NUMERIC(18,6),
    bvps_growth_1y          NUMERIC(18,6),

    -- ── Multi-Year Revenue CAGR ───────────────────────────────
    revenue_cagr_3y         NUMERIC(18,6),
    revenue_cagr_5y         NUMERIC(18,6),
    revenue_cagr_7y         NUMERIC(18,6),
    revenue_cagr_10y        NUMERIC(18,6),
    revenue_growth_median_5y  NUMERIC(18,6),        -- median annual growth over 5Y
    revenue_growth_median_10y NUMERIC(18,6),

    -- ── Multi-Year Net Income CAGR ────────────────────────────
    net_income_cagr_3y      NUMERIC(18,6),
    net_income_cagr_5y      NUMERIC(18,6),
    net_income_cagr_7y      NUMERIC(18,6),
    net_income_cagr_10y     NUMERIC(18,6),

    -- ── Multi-Year EPS CAGR ───────────────────────────────────
    eps_cagr_3y             NUMERIC(18,6),
    eps_cagr_5y             NUMERIC(18,6),
    eps_cagr_7y             NUMERIC(18,6),
    eps_cagr_10y            NUMERIC(18,6),

    -- ── Multi-Year EBITDA CAGR ────────────────────────────────
    ebitda_cagr_3y          NUMERIC(18,6),
    ebitda_cagr_5y          NUMERIC(18,6),
    ebitda_cagr_7y          NUMERIC(18,6),
    ebitda_cagr_10y         NUMERIC(18,6),

    -- ── Multi-Year FCF & Other CAGRs ──────────────────────────
    fcf_cagr_3y             NUMERIC(18,6),
    fcf_cagr_5y             NUMERIC(18,6),
    gross_profit_cagr_3y    NUMERIC(18,6),
    gross_profit_cagr_5y    NUMERIC(18,6),
    bvps_cagr_3y            NUMERIC(18,6),
    bvps_cagr_5y            NUMERIC(18,6),

    -- ── Price Return CAGR (vs price at fiscal year end) ───────
    price_cagr_1y           NUMERIC(18,6),
    price_cagr_3y           NUMERIC(18,6),
    price_cagr_5y           NUMERIC(18,6),
    price_cagr_7y           NUMERIC(18,6),
    price_cagr_10y          NUMERIC(18,6),

    -- ── Multi-Year Averages: ROE ──────────────────────────────
    avg_roe_3y              NUMERIC(18,6),
    avg_roe_5y              NUMERIC(18,6),
    avg_roe_7y              NUMERIC(18,6),
    avg_roe_10y             NUMERIC(18,6),

    -- ── Multi-Year Averages: ROA ──────────────────────────────
    avg_roa_3y              NUMERIC(18,6),
    avg_roa_5y              NUMERIC(18,6),

    -- ── Multi-Year Averages: ROIC ─────────────────────────────
    avg_roic_3y             NUMERIC(18,6),
    avg_roic_5y             NUMERIC(18,6),

    -- ── Multi-Year Averages: ROCE ─────────────────────────────
    avg_roce_3y             NUMERIC(18,6),
    avg_roce_5y             NUMERIC(18,6),
    avg_roce_7y             NUMERIC(18,6),
    avg_roce_10y            NUMERIC(18,6),

    -- ── Multi-Year Averages: Margins ──────────────────────────
    avg_gross_margin_3y         NUMERIC(18,6),
    avg_gross_margin_5y         NUMERIC(18,6),
    avg_ebitda_margin_3y        NUMERIC(18,6),
    avg_ebitda_margin_5y        NUMERIC(18,6),
    avg_operating_margin_3y     NUMERIC(18,6),      -- OPM 3Y
    avg_operating_margin_5y     NUMERIC(18,6),      -- OPM 5Y
    avg_operating_margin_10y    NUMERIC(18,6),      -- OPM 10Y
    avg_net_margin_3y           NUMERIC(18,6),
    avg_net_margin_5y           NUMERIC(18,6),
    avg_net_margin_10y          NUMERIC(18,6),
    avg_fcf_margin_3y           NUMERIC(18,6),
    avg_fcf_margin_5y           NUMERIC(18,6),

    -- ── Multi-Year Averages: EPS Growth ───────────────────────
    avg_eps_growth_3y       NUMERIC(18,6),
    avg_eps_growth_5y       NUMERIC(18,6),          -- "Average Earnings 5Year"
    avg_eps_growth_10y      NUMERIC(18,6),          -- "Average Earnings 10Year"

    -- ── Multi-Year Averages: EBIT ─────────────────────────────
    avg_ebit_5y             NUMERIC(18,2),          -- average EBIT value AUD millions
    avg_ebit_10y            NUMERIC(18,2),

    -- ── Risk & Performance ────────────────────────────────────
    beta_1y                 NUMERIC(18,6),
    beta_3y                 NUMERIC(18,6),
    beta_5y                 NUMERIC(18,6),
    volatility_1y           NUMERIC(18,6),          -- annualised historical vol
    volatility_3y           NUMERIC(18,6),
    sharpe_1y               NUMERIC(18,6),
    sharpe_3y               NUMERIC(18,6),
    sortino_1y              NUMERIC(18,6),
    max_drawdown_1y         NUMERIC(18,6),
    max_drawdown_3y         NUMERIC(18,6),
    calmar_ratio            NUMERIC(18,6),
    alpha_1y                NUMERIC(18,6),
    alpha_3y                NUMERIC(18,6),

    -- ── Metadata ──────────────────────────────────────────────
    compute_version         VARCHAR(20),
    computed_at             TIMESTAMPTZ DEFAULT NOW(),

    PRIMARY KEY (asx_code, fiscal_year)
);

CREATE INDEX idx_ym_roe      ON market.yearly_metrics (fiscal_year, roe);
CREATE INDEX idx_ym_roce     ON market.yearly_metrics (fiscal_year, roce);
CREATE INDEX idx_ym_pe       ON market.yearly_metrics (fiscal_year, pe_ratio);
CREATE INDEX idx_ym_revenue  ON market.yearly_metrics (fiscal_year, revenue_cagr_5y);
CREATE INDEX idx_ym_computed ON market.yearly_metrics (computed_at DESC);


-- ═════════════════════════════════════════════════════════════
--  SEQ 3  market.halfyearly_metrics
--  One row per (asx_code, period_end_date).
--  ASX companies report half-yearly (1H and 2H each fiscal year).
--  Recomputed quarterly after each reporting season.
-- ═════════════════════════════════════════════════════════════

CREATE TABLE market.halfyearly_metrics (
    asx_code                VARCHAR(10)  NOT NULL,
    period_end_date         DATE         NOT NULL,
    fiscal_year             SMALLINT     NOT NULL,
    half                    SMALLINT     NOT NULL,   -- 1 = first half, 2 = second half
    period_label            VARCHAR(20),             -- e.g. '1H FY2024'

    -- ── Income (AUD millions) ──────────────────────────────────
    revenue                 NUMERIC(18,2),
    gross_profit            NUMERIC(18,2),
    ebitda                  NUMERIC(18,2),
    ebit                    NUMERIC(18,2),
    net_income              NUMERIC(18,2),
    other_income            NUMERIC(18,2),
    interest_expense        NUMERIC(18,2),
    tax                     NUMERIC(18,2),
    depreciation            NUMERIC(18,2),

    -- ── Per Share ─────────────────────────────────────────────
    eps                     NUMERIC(10,4),
    dps                     NUMERIC(10,4),
    franking_pct            NUMERIC(5,2),

    -- ── Margins ───────────────────────────────────────────────
    gross_margin            NUMERIC(8,4),
    ebit_margin             NUMERIC(8,4),            -- OPM
    net_margin              NUMERIC(8,4),            -- NPM

    -- ── Period-over-Period Growth ─────────────────────────────
    revenue_growth_hoh      NUMERIC(8,4),            -- vs previous half
    revenue_growth_yoy      NUMERIC(8,4),            -- vs same half prior year
    net_income_growth_hoh   NUMERIC(8,4),
    net_income_growth_yoy   NUMERIC(8,4),
    eps_growth_hoh          NUMERIC(8,4),
    eps_growth_yoy          NUMERIC(8,4),

    -- ── Metadata ──────────────────────────────────────────────
    compute_version         VARCHAR(20),
    computed_at             TIMESTAMPTZ DEFAULT NOW(),

    PRIMARY KEY (asx_code, period_end_date)
);

CREATE INDEX idx_hym_asx ON market.halfyearly_metrics (asx_code, period_end_date DESC);
CREATE INDEX idx_hym_fy  ON market.halfyearly_metrics (fiscal_year, half);


-- ═════════════════════════════════════════════════════════════
--  SEQ 4  market.quarterly_metrics
--  One row per (asx_code, fiscal_year, quarter).
--  EODHD provides quarterly data even for ASX companies.
--  Used for quarterly trend analysis and QoQ growth.
-- ═════════════════════════════════════════════════════════════

CREATE TABLE market.quarterly_metrics (
    asx_code                VARCHAR(10)  NOT NULL,
    fiscal_year             SMALLINT     NOT NULL,
    quarter                 SMALLINT     NOT NULL,   -- 1, 2, 3, 4
    period_end_date         DATE,
    period_label            VARCHAR(20),             -- e.g. 'Q1 FY2024'

    -- ── Income (AUD millions) ──────────────────────────────────
    revenue                 NUMERIC(18,2),
    gross_profit            NUMERIC(18,2),
    ebitda                  NUMERIC(18,2),
    ebit                    NUMERIC(18,2),
    other_income            NUMERIC(18,2),
    interest_expense        NUMERIC(18,2),
    depreciation            NUMERIC(18,2),
    tax                     NUMERIC(18,2),
    net_income              NUMERIC(18,2),
    extraordinary_items     NUMERIC(18,2),
    equity_capital          NUMERIC(18,2),

    -- ── Per Share ─────────────────────────────────────────────
    eps                     NUMERIC(10,4),

    -- ── Margins ───────────────────────────────────────────────
    -- NUMERIC(18,6): small-caps can have extreme margin swings
    gross_margin            NUMERIC(18,6),           -- GPM
    ebit_margin             NUMERIC(18,6),           -- OPM
    net_margin              NUMERIC(18,6),           -- NPM

    -- ── QoQ Growth (vs previous quarter) ─────────────────────
    revenue_growth_qoq      NUMERIC(18,6),
    net_income_growth_qoq   NUMERIC(18,6),
    ebit_growth_qoq         NUMERIC(18,6),

    -- ── YoY Growth (vs same quarter prior year) ───────────────
    revenue_growth_yoy      NUMERIC(18,6),
    net_income_growth_yoy   NUMERIC(18,6),
    ebit_growth_yoy         NUMERIC(18,6),
    eps_growth_yoy          NUMERIC(18,6),

    -- ── Metadata ──────────────────────────────────────────────
    compute_version         VARCHAR(20),
    computed_at             TIMESTAMPTZ DEFAULT NOW(),

    PRIMARY KEY (asx_code, fiscal_year, quarter)
);

CREATE INDEX idx_qm_asx ON market.quarterly_metrics (asx_code, fiscal_year DESC, quarter DESC);
CREATE INDEX idx_qm_period ON market.quarterly_metrics (period_end_date DESC);


-- ═════════════════════════════════════════════════════════════
--  SEQ 5  market.monthly_metrics
--  One row per (asx_code, month_date) — first calendar day of month.
--  Computed from daily_prices on the last trading day of each month.
--  Contains price-based momentum, volatility, and monthly returns.
-- ═════════════════════════════════════════════════════════════

CREATE TABLE market.monthly_metrics (
    asx_code                VARCHAR(10)  NOT NULL,
    month_date              DATE         NOT NULL,   -- first day of month e.g. 2024-06-01
    close                   NUMERIC(12,4),
    volume_avg              BIGINT,
    market_cap              NUMERIC(18,2),

    -- ── Returns ───────────────────────────────────────────────
    -- NUMERIC(18,6): ASX small-caps can have extreme multi-year returns (>9999%)
    monthly_return          NUMERIC(18,6),
    return_3m               NUMERIC(18,6),
    return_6m               NUMERIC(18,6),
    return_12m              NUMERIC(18,6),
    return_ytd              NUMERIC(18,6),

    -- ── Momentum ──────────────────────────────────────────────
    momentum_3m             NUMERIC(18,6),           -- 3-month price change %
    momentum_6m             NUMERIC(18,6),
    momentum_12m            NUMERIC(18,6),
    relative_strength_xjo   NUMERIC(18,6),           -- vs ASX 200

    -- ── Volatility ────────────────────────────────────────────
    volatility_1m           NUMERIC(18,6),           -- annualised, based on daily returns in month
    volatility_3m           NUMERIC(18,6),
    volatility_12m          NUMERIC(18,6),

    -- ── Technical (monthly bars) ──────────────────────────────
    rsi_14                  NUMERIC(6,2),
    macd_line               NUMERIC(10,4),
    macd_signal             NUMERIC(10,4),
    macd_hist               NUMERIC(10,4),
    bb_pct                  NUMERIC(18,6),
    bb_width                NUMERIC(18,6),

    -- ── Price Levels ──────────────────────────────────────────
    sma_12m                 NUMERIC(12,4),           -- 12-month SMA
    price_to_52w_high       NUMERIC(18,6),
    drawdown_from_ath       NUMERIC(18,6),

    -- ── Metadata ──────────────────────────────────────────────
    compute_version         VARCHAR(20),
    computed_at             TIMESTAMPTZ DEFAULT NOW(),

    PRIMARY KEY (asx_code, month_date)
);

CREATE INDEX idx_mm_asx ON market.monthly_metrics (asx_code, month_date DESC);
CREATE INDEX idx_mm_month ON market.monthly_metrics (month_date DESC);


-- ═════════════════════════════════════════════════════════════
--  SEQ 6  market.weekly_metrics
--  One row per (asx_code, week_date) — Monday of each week.
--  Computed from daily_prices every Monday morning.
-- ═════════════════════════════════════════════════════════════

CREATE TABLE market.weekly_metrics (
    asx_code                VARCHAR(10)  NOT NULL,
    week_date               DATE         NOT NULL,   -- Monday of the week
    open                    NUMERIC(12,4),
    high                    NUMERIC(12,4),
    low                     NUMERIC(12,4),
    close                   NUMERIC(12,4),
    volume                  BIGINT,
    market_cap              NUMERIC(18,2),

    -- ── Returns ───────────────────────────────────────────────
    -- NUMERIC(18,6): ASX small-caps can have extreme multi-year returns (>9999%)
    weekly_return           NUMERIC(18,6),
    return_4w               NUMERIC(18,6),           -- 4-week return
    return_13w              NUMERIC(18,6),           -- 13-week (quarter) return
    return_52w              NUMERIC(18,6),           -- 52-week return

    -- ── Trend ─────────────────────────────────────────────────
    adx_14                  NUMERIC(6,2),
    plus_di                 NUMERIC(6,2),
    minus_di                NUMERIC(6,2),
    aroon_up                NUMERIC(6,2),
    aroon_down              NUMERIC(6,2),

    -- ── Momentum (weekly bars) ────────────────────────────────
    rsi_14                  NUMERIC(6,2),
    rsi_7                   NUMERIC(6,2),
    macd_line               NUMERIC(10,4),
    macd_signal             NUMERIC(10,4),
    macd_hist               NUMERIC(10,4),
    stoch_k                 NUMERIC(6,2),
    stoch_d                 NUMERIC(6,2),
    cci_20                  NUMERIC(10,4),
    williams_r              NUMERIC(6,2),

    -- ── Moving Averages (on weekly bars) ──────────────────────
    sma_10w                 NUMERIC(12,4),           -- 10-week SMA ≈ 50DMA
    sma_20w                 NUMERIC(12,4),           -- 20-week SMA ≈ 100DMA
    sma_40w                 NUMERIC(12,4),           -- 40-week SMA ≈ 200DMA
    ema_13w                 NUMERIC(12,4),
    ema_26w                 NUMERIC(12,4),

    -- ── Volatility ────────────────────────────────────────────
    atr_14                  NUMERIC(10,4),
    bb_upper                NUMERIC(12,4),
    bb_lower                NUMERIC(12,4),
    bb_pct                  NUMERIC(18,6),
    bb_width                NUMERIC(18,6),

    -- ── Volume ────────────────────────────────────────────────
    volume_avg_4w           BIGINT,
    relative_volume         NUMERIC(18,6),
    obv                     BIGINT,

    -- ── Signals ───────────────────────────────────────────────
    golden_cross            BOOLEAN,
    death_cross             BOOLEAN,
    above_sma10w            BOOLEAN,
    above_sma40w            BOOLEAN,

    -- ── Metadata ──────────────────────────────────────────────
    compute_version         VARCHAR(20),
    computed_at             TIMESTAMPTZ DEFAULT NOW(),

    PRIMARY KEY (asx_code, week_date)
);

CREATE INDEX idx_wm_asx  ON market.weekly_metrics (asx_code, week_date DESC);
CREATE INDEX idx_wm_week ON market.weekly_metrics (week_date DESC);


-- ═════════════════════════════════════════════════════════════
--  SEQ 7  market.daily_metrics
--  One row per (asx_code, date).
--  TimescaleDB hypertable — high volume, nightly compute.
--  Replaces market.technical_indicators with full indicator set.
-- ═════════════════════════════════════════════════════════════

CREATE TABLE market.daily_metrics (
    asx_code                VARCHAR(10)  NOT NULL,
    date                    DATE         NOT NULL,
    close                   NUMERIC(12,4),
    adj_close               NUMERIC(12,4),
    volume                  BIGINT,
    market_cap              NUMERIC(18,2),           -- close × shares_outstanding

    -- ── Returns ───────────────────────────────────────────────
    daily_return            NUMERIC(10,6),           -- (close - prev_close) / prev_close
    log_return              NUMERIC(10,6),           -- ln(close / prev_close)
    gap_pct                 NUMERIC(8,4),            -- (open - prev_close) / prev_close

    -- ── Simple Moving Averages ────────────────────────────────
    sma_5                   NUMERIC(12,4),
    sma_10                  NUMERIC(12,4),
    sma_20                  NUMERIC(12,4),
    sma_50                  NUMERIC(12,4),
    sma_100                 NUMERIC(12,4),
    sma_200                 NUMERIC(12,4),

    -- ── Exponential Moving Averages ───────────────────────────
    ema_9                   NUMERIC(12,4),
    ema_12                  NUMERIC(12,4),
    ema_20                  NUMERIC(12,4),
    ema_26                  NUMERIC(12,4),
    ema_50                  NUMERIC(12,4),
    ema_200                 NUMERIC(12,4),

    -- ── DMA Ratios ────────────────────────────────────────────
    dma20_ratio             NUMERIC(8,4),            -- close / sma_20
    dma50_ratio             NUMERIC(8,4),            -- close / sma_50
    dma200_ratio            NUMERIC(8,4),            -- close / sma_200

    -- ── Previous Day MAs (for crossover detection) ────────────
    sma_50_prev             NUMERIC(12,4),
    sma_200_prev            NUMERIC(12,4),

    -- ── MACD ──────────────────────────────────────────────────
    macd_line               NUMERIC(10,4),           -- ema_12 - ema_26
    macd_signal             NUMERIC(10,4),           -- 9-period EMA of MACD line
    macd_hist               NUMERIC(10,4),           -- macd_line - macd_signal
    macd_line_prev          NUMERIC(10,4),           -- previous day
    macd_signal_prev        NUMERIC(10,4),

    -- ── RSI ───────────────────────────────────────────────────
    rsi_7                   NUMERIC(6,2),
    rsi_14                  NUMERIC(6,2),
    rsi_21                  NUMERIC(6,2),

    -- ── Stochastic ────────────────────────────────────────────
    stoch_k                 NUMERIC(6,2),            -- %K (14,3,3)
    stoch_d                 NUMERIC(6,2),            -- %D

    -- ── Bollinger Bands (20, 2σ) ──────────────────────────────
    bb_upper                NUMERIC(12,4),
    bb_mid                  NUMERIC(12,4),
    bb_lower                NUMERIC(12,4),
    bb_pct                  NUMERIC(8,4),            -- %B position within bands
    bb_width                NUMERIC(8,4),            -- band width / mid

    -- ── Trend ─────────────────────────────────────────────────
    adx_14                  NUMERIC(6,2),
    plus_di                 NUMERIC(6,2),
    minus_di                NUMERIC(6,2),
    cci_20                  NUMERIC(10,4),
    williams_r              NUMERIC(6,2),
    roc_10                  NUMERIC(8,4),            -- Rate of Change
    roc_20                  NUMERIC(8,4),

    -- ── Volatility ────────────────────────────────────────────
    atr_14                  NUMERIC(10,4),
    atr_pct                 NUMERIC(8,4),            -- atr_14 / close
    true_range              NUMERIC(10,4),
    hv_20d                  NUMERIC(8,4),            -- 20-day historical volatility (annualised)
    hv_60d                  NUMERIC(8,4),

    -- ── Volume ────────────────────────────────────────────────
    obv                     BIGINT,
    obv_ema                 BIGINT,
    vwap                    NUMERIC(12,4),           -- rolling 20-day VWAP
    cmf_20                  NUMERIC(8,4),            -- Chaikin Money Flow
    mfi_14                  NUMERIC(6,2),            -- Money Flow Index
    volume_avg_5d           BIGINT,
    volume_avg_20d          BIGINT,
    volume_avg_50d          BIGINT,
    relative_volume         NUMERIC(8,4),            -- volume / avg_20d

    -- ── 52-Week & All-Time Levels ─────────────────────────────
    high_52w                NUMERIC(12,4),
    low_52w                 NUMERIC(12,4),
    ath_price               NUMERIC(12,4),           -- all-time high (adjusted)
    atl_price               NUMERIC(12,4),           -- all-time low (adjusted)
    pct_from_52w_high       NUMERIC(8,4),
    pct_from_52w_low        NUMERIC(8,4),
    pct_from_ath            NUMERIC(8,4),            -- drawdown from ATH

    -- ── Price Signals ─────────────────────────────────────────
    above_sma20             BOOLEAN,
    above_sma50             BOOLEAN,
    above_sma100            BOOLEAN,
    above_sma200            BOOLEAN,
    golden_cross            BOOLEAN,                 -- sma_50 crossed above sma_200
    death_cross             BOOLEAN,
    new_52w_high            BOOLEAN,
    new_52w_low             BOOLEAN,
    new_ath                 BOOLEAN,

    -- ── Returns ───────────────────────────────────────────────
    return_1w               NUMERIC(8,4),
    return_1m               NUMERIC(8,4),
    return_3m               NUMERIC(8,4),
    return_6m               NUMERIC(8,4),
    return_ytd              NUMERIC(8,4),
    return_1y               NUMERIC(8,4),

    -- ── Metadata ──────────────────────────────────────────────
    compute_version         VARCHAR(20),
    computed_at             TIMESTAMPTZ DEFAULT NOW(),

    PRIMARY KEY (asx_code, date)
);

-- Convert to TimescaleDB hypertable, partitioned by date (1 week chunks)
SELECT create_hypertable(
    'market.daily_metrics', 'date',
    chunk_time_interval => INTERVAL '1 week',
    if_not_exists       => TRUE
);

ALTER TABLE market.daily_metrics SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'asx_code',
    timescaledb.compress_orderby   = 'date DESC'
);
SELECT add_compression_policy('market.daily_metrics', INTERVAL '3 months');

CREATE INDEX idx_dm_asx_date   ON market.daily_metrics (asx_code, date DESC);
CREATE INDEX idx_dm_rsi        ON market.daily_metrics (date DESC, rsi_14);
CREATE INDEX idx_dm_macd       ON market.daily_metrics (date DESC, macd_hist);
CREATE INDEX idx_dm_dma50      ON market.daily_metrics (date DESC, dma50_ratio);
CREATE INDEX idx_dm_dma200     ON market.daily_metrics (date DESC, dma200_ratio);
CREATE INDEX idx_dm_signals    ON market.daily_metrics (date DESC, above_sma200, golden_cross);
