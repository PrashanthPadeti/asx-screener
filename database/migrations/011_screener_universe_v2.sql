-- Migration 011: Recreate market.screener_universe
-- Column names aligned exactly to build_screener_universe.py output dict.
-- Run after: DROP TABLE IF EXISTS market.screener_universe CASCADE;

CREATE TABLE market.screener_universe (

    -- ── Identity ─────────────────────────────────────────────
    asx_code                VARCHAR(10)  PRIMARY KEY,
    company_name            TEXT,
    sector                  TEXT,
    industry                TEXT,
    sub_industry            TEXT,
    gics_code               TEXT,
    listing_date            DATE,
    is_active               BOOLEAN      DEFAULT TRUE,
    is_foreign              BOOLEAN      DEFAULT FALSE,
    description             TEXT,
    website                 TEXT,
    employee_count          INTEGER,
    asx_300                 BOOLEAN      DEFAULT FALSE,
    asx_200                 BOOLEAN      DEFAULT FALSE,
    asx_100                 BOOLEAN      DEFAULT FALSE,
    asx_50                  BOOLEAN      DEFAULT FALSE,
    asx_20                  BOOLEAN      DEFAULT FALSE,
    market_cap_group        TEXT,

    -- ── Price & Volume ────────────────────────────────────────
    last_price              NUMERIC(12,4),
    last_price_date         DATE,
    open                    NUMERIC(12,4),
    high                    NUMERIC(12,4),
    low                     NUMERIC(12,4),
    volume                  BIGINT,
    volume_avg_20d          BIGINT,
    volume_avg_52w          BIGINT,
    relative_volume         NUMERIC(8,4),

    -- ── Market Cap & Valuation ────────────────────────────────
    market_cap              NUMERIC(18,2),
    enterprise_value        NUMERIC(18,2),
    shares_outstanding      BIGINT,
    free_float              BIGINT,
    pe_ratio                NUMERIC(12,4),
    pe_ratio_forward        NUMERIC(12,4),
    pb_ratio                NUMERIC(12,4),
    ps_ratio                NUMERIC(12,4),
    ev_ebitda               NUMERIC(12,4),
    ev_ebit                 NUMERIC(12,4),
    ev_revenue              NUMERIC(12,4),
    ev_fcf                  NUMERIC(12,4),
    peg_ratio               NUMERIC(12,4),
    price_to_fcf            NUMERIC(12,4),
    price_to_book           NUMERIC(12,4),
    price_to_tangible_book  NUMERIC(12,4),
    dividend_yield          NUMERIC(8,4),
    franking_pct            NUMERIC(6,2),
    grossed_up_yield        NUMERIC(8,4),
    payout_ratio            NUMERIC(8,4),
    earnings_yield          NUMERIC(8,4),
    fcf_yield               NUMERIC(8,4),

    -- ── Income Statement FY0 ──────────────────────────────────
    revenue                 NUMERIC(18,2),
    gross_profit            NUMERIC(18,2),
    ebitda                  NUMERIC(18,2),
    ebit                    NUMERIC(18,2),
    net_income              NUMERIC(18,2),
    eps                     NUMERIC(10,4),
    eps_diluted             NUMERIC(10,4),
    dps                     NUMERIC(10,4),
    dps_franking_pct        NUMERIC(6,2),
    depreciation            NUMERIC(18,2),
    interest_expense        NUMERIC(18,2),
    tax_expense             NUMERIC(18,2),
    other_income            NUMERIC(18,2),
    extraordinary_items     NUMERIC(18,2),
    material_cost           NUMERIC(18,2),
    employee_cost           NUMERIC(18,2),

    -- ── Income Statement FY-1 ─────────────────────────────────
    revenue_fy1             NUMERIC(18,2),
    gross_profit_fy1        NUMERIC(18,2),
    ebitda_fy1              NUMERIC(18,2),
    ebit_fy1                NUMERIC(18,2),
    net_income_fy1          NUMERIC(18,2),
    eps_fy1                 NUMERIC(10,4),
    dps_fy1                 NUMERIC(10,4),

    -- ── Income Statement FY-2 ─────────────────────────────────
    revenue_fy2             NUMERIC(18,2),
    ebit_fy2                NUMERIC(18,2),
    net_income_fy2          NUMERIC(18,2),
    eps_fy2                 NUMERIC(10,4),

    -- ── N-Year Actual Values ──────────────────────────────────
    revenue_3y              NUMERIC(18,2),
    revenue_5y              NUMERIC(18,2),
    revenue_7y              NUMERIC(18,2),
    revenue_10y             NUMERIC(18,2),
    net_income_3y           NUMERIC(18,2),
    net_income_5y           NUMERIC(18,2),
    net_income_7y           NUMERIC(18,2),
    net_income_10y          NUMERIC(18,2),
    eps_3y                  NUMERIC(10,4),
    eps_5y                  NUMERIC(10,4),
    eps_7y                  NUMERIC(10,4),
    eps_10y                 NUMERIC(10,4),

    -- ── Margins FY0 ───────────────────────────────────────────
    gross_margin            NUMERIC(8,4),
    ebitda_margin           NUMERIC(8,4),
    ebit_margin             NUMERIC(8,4),
    net_margin              NUMERIC(8,4),
    tax_rate                NUMERIC(8,4),

    -- ── Margins FY-1 ──────────────────────────────────────────
    gross_margin_fy1        NUMERIC(8,4),
    ebit_margin_fy1         NUMERIC(8,4),
    net_margin_fy1          NUMERIC(8,4),

    -- ── Margins FY-2 ──────────────────────────────────────────
    ebit_margin_fy2         NUMERIC(8,4),
    net_margin_fy2          NUMERIC(8,4),

    -- ── Multi-year Average Margins ────────────────────────────
    gross_margin_avg_3y     NUMERIC(8,4),
    gross_margin_avg_5y     NUMERIC(8,4),
    opm_avg_3y              NUMERIC(8,4),
    opm_avg_5y              NUMERIC(8,4),
    opm_avg_7y              NUMERIC(8,4),
    opm_avg_10y             NUMERIC(8,4),
    npm_avg_3y              NUMERIC(8,4),
    npm_avg_5y              NUMERIC(8,4),

    -- ── Balance Sheet ─────────────────────────────────────────
    total_assets            NUMERIC(18,2),
    total_liabilities       NUMERIC(18,2),
    total_equity            NUMERIC(18,2),
    current_assets          NUMERIC(18,2),
    current_liabilities     NUMERIC(18,2),
    cash                    NUMERIC(18,2),
    total_debt              NUMERIC(18,2),
    long_term_debt          NUMERIC(18,2),
    short_term_debt         NUMERIC(18,2),
    net_debt                NUMERIC(18,2),
    working_capital         NUMERIC(18,2),
    inventory               NUMERIC(18,2),
    receivables             NUMERIC(18,2),
    payables                NUMERIC(18,2),
    goodwill                NUMERIC(18,2),
    intangibles             NUMERIC(18,2),
    fixed_assets            NUMERIC(18,2),
    gross_block             NUMERIC(18,2),
    net_block               NUMERIC(18,2),
    accumulated_depreciation NUMERIC(18,2),
    capital_wip             NUMERIC(18,2),
    lease_liabilities       NUMERIC(18,2),
    equity_capital          NUMERIC(18,2),
    preference_capital      NUMERIC(18,2),
    reserves                NUMERIC(18,2),
    trade_payables          NUMERIC(18,2),
    advance_from_customers  NUMERIC(18,2),
    contingent_liabilities  NUMERIC(18,2),
    face_value              NUMERIC(10,4),
    investments             NUMERIC(18,2),
    book_value_per_share    NUMERIC(10,4),
    tangible_book_value     NUMERIC(18,2),
    tangible_bvps           NUMERIC(10,4),

    -- ── Historical Balance Sheet ──────────────────────────────
    total_debt_3y           NUMERIC(18,2),
    total_debt_5y           NUMERIC(18,2),
    total_debt_7y           NUMERIC(18,2),
    total_debt_10y          NUMERIC(18,2),
    working_capital_3y      NUMERIC(18,2),
    working_capital_5y      NUMERIC(18,2),
    working_capital_7y      NUMERIC(18,2),
    net_block_3y            NUMERIC(18,2),
    net_block_5y            NUMERIC(18,2),
    net_block_7y            NUMERIC(18,2),

    -- ── Cash Flow ─────────────────────────────────────────────
    cfo                     NUMERIC(18,2),
    cfi                     NUMERIC(18,2),
    cff                     NUMERIC(18,2),
    fcf                     NUMERIC(18,2),
    capex                   NUMERIC(18,2),
    closing_cash            NUMERIC(18,2),

    -- ── Historical Cash Flow ──────────────────────────────────
    fcf_3y                  NUMERIC(18,2),
    fcf_5y                  NUMERIC(18,2),
    fcf_7y                  NUMERIC(18,2),
    fcf_10y                 NUMERIC(18,2),
    ocf_3y                  NUMERIC(18,2),
    ocf_5y                  NUMERIC(18,2),
    ocf_7y                  NUMERIC(18,2),
    ocf_10y                 NUMERIC(18,2),
    cash_3y                 NUMERIC(18,2),
    cash_5y                 NUMERIC(18,2),
    cash_7y                 NUMERIC(18,2),

    -- ── Efficiency ────────────────────────────────────────────
    asset_turnover          NUMERIC(8,4),
    inventory_turnover      NUMERIC(8,4),
    receivables_turnover    NUMERIC(8,4),
    days_sales_outstanding  NUMERIC(8,2),
    days_inventory_outstanding NUMERIC(8,2),
    cash_conversion_cycle   NUMERIC(8,2),
    capex_to_sales          NUMERIC(8,4),
    capex_to_cfo            NUMERIC(8,4),
    fcf_to_net_income       NUMERIC(8,4),

    -- ── Leverage ──────────────────────────────────────────────
    debt_to_equity          NUMERIC(10,4),
    debt_to_assets          NUMERIC(8,4),
    debt_to_ebitda          NUMERIC(10,4),
    net_debt_to_ebitda      NUMERIC(10,4),
    interest_coverage       NUMERIC(10,4),
    current_ratio           NUMERIC(8,4),
    quick_ratio             NUMERIC(8,4),
    cash_ratio              NUMERIC(8,4),

    -- ── Profitability / Returns ───────────────────────────────
    roe                     NUMERIC(8,4),
    roa                     NUMERIC(8,4),
    roic                    NUMERIC(8,4),
    roce                    NUMERIC(8,4),
    roe_avg_3y              NUMERIC(8,4),
    roe_avg_5y              NUMERIC(8,4),
    roe_avg_7y              NUMERIC(8,4),
    roe_avg_10y             NUMERIC(8,4),
    roa_avg_3y              NUMERIC(8,4),
    roa_avg_5y              NUMERIC(8,4),
    roic_avg_3y             NUMERIC(8,4),
    roic_avg_5y             NUMERIC(8,4),
    roce_avg_3y             NUMERIC(8,4),
    roce_avg_5y             NUMERIC(8,4),
    roce_avg_7y             NUMERIC(8,4),
    roce_avg_10y            NUMERIC(8,4),

    -- ── Growth (1Y) ───────────────────────────────────────────
    revenue_growth_1y       NUMERIC(8,4),
    net_income_growth_1y    NUMERIC(8,4),
    ebit_growth_1y          NUMERIC(8,4),
    eps_growth_1y           NUMERIC(8,4),
    ebitda_growth_1y        NUMERIC(8,4),
    fcf_growth_1y           NUMERIC(8,4),
    dps_growth_1y           NUMERIC(8,4),

    -- ── CAGR ─────────────────────────────────────────────────
    revenue_cagr_3y         NUMERIC(8,4),
    revenue_cagr_5y         NUMERIC(8,4),
    revenue_cagr_7y         NUMERIC(8,4),
    revenue_cagr_10y        NUMERIC(8,4),
    net_income_cagr_3y      NUMERIC(8,4),
    net_income_cagr_5y      NUMERIC(8,4),
    net_income_cagr_7y      NUMERIC(8,4),
    net_income_cagr_10y     NUMERIC(8,4),
    eps_cagr_3y             NUMERIC(8,4),
    eps_cagr_5y             NUMERIC(8,4),
    eps_cagr_7y             NUMERIC(8,4),
    eps_cagr_10y            NUMERIC(8,4),
    ebitda_cagr_3y          NUMERIC(8,4),
    ebitda_cagr_5y          NUMERIC(8,4),
    fcf_cagr_3y             NUMERIC(8,4),
    fcf_cagr_5y             NUMERIC(8,4),
    gross_profit_cagr_3y    NUMERIC(8,4),
    gross_profit_cagr_5y    NUMERIC(8,4),
    bvps_cagr_3y            NUMERIC(8,4),
    bvps_cagr_5y            NUMERIC(8,4),
    dividend_cagr_3y        NUMERIC(8,4),
    dividend_cagr_5y        NUMERIC(8,4),
    price_cagr_1y           NUMERIC(8,4),
    price_cagr_3y           NUMERIC(8,4),
    price_cagr_5y           NUMERIC(8,4),

    -- ── EPS Growth Averages ───────────────────────────────────
    eps_growth_avg_3y       NUMERIC(8,4),
    eps_growth_avg_5y       NUMERIC(8,4),
    eps_growth_avg_7y       NUMERIC(8,4),
    eps_growth_avg_10y      NUMERIC(8,4),

    -- ── Quality Scores ────────────────────────────────────────
    piotroski_score         SMALLINT,
    altman_z_score          NUMERIC(8,4),
    beneish_m_score         NUMERIC(8,4),
    accruals_ratio          NUMERIC(8,4),

    -- ── Risk Metrics ──────────────────────────────────────────
    beta                    NUMERIC(8,4),
    alpha_1y                NUMERIC(8,4),
    volatility_1y           NUMERIC(8,4),
    volatility_3y           NUMERIC(8,4),
    sharpe_1y               NUMERIC(8,4),
    sharpe_3y               NUMERIC(8,4),
    sortino_1y              NUMERIC(8,4),
    max_drawdown_1y         NUMERIC(8,4),
    max_drawdown_3y         NUMERIC(8,4),
    max_drawdown_5y         NUMERIC(8,4),
    calmar_ratio            NUMERIC(8,4),

    -- ── Price Performance ─────────────────────────────────────
    return_1d               NUMERIC(8,4),
    return_5d               NUMERIC(8,4),
    return_1m               NUMERIC(8,4),
    return_3m               NUMERIC(8,4),
    return_6m               NUMERIC(8,4),
    return_1y               NUMERIC(8,4),
    return_ytd              NUMERIC(8,4),
    return_3y               NUMERIC(8,4),
    return_5y               NUMERIC(8,4),

    -- ── 52w / ATH ─────────────────────────────────────────────
    high_52w                NUMERIC(12,4),
    low_52w                 NUMERIC(12,4),
    pct_from_52w_high       NUMERIC(8,4),
    pct_from_52w_low        NUMERIC(8,4),
    all_time_high           NUMERIC(12,4),
    all_time_low            NUMERIC(12,4),
    pct_from_ath            NUMERIC(8,4),
    pct_from_atl            NUMERIC(8,4),

    -- ── Daily Technicals ──────────────────────────────────────
    sma_5                   NUMERIC(12,4),
    sma_10                  NUMERIC(12,4),
    sma_20                  NUMERIC(12,4),
    sma_50                  NUMERIC(12,4),
    sma_100                 NUMERIC(12,4),
    sma_200                 NUMERIC(12,4),
    ema_9                   NUMERIC(12,4),
    ema_20                  NUMERIC(12,4),
    ema_50                  NUMERIC(12,4),
    ema_200                 NUMERIC(12,4),
    sma_50_prev             NUMERIC(12,4),
    sma_200_prev            NUMERIC(12,4),
    dma_50_ratio            NUMERIC(8,4),
    dma_200_ratio           NUMERIC(8,4),
    price_to_sma20          NUMERIC(8,4),
    macd_line               NUMERIC(10,6),
    macd_signal             NUMERIC(10,6),
    macd_hist               NUMERIC(10,6),
    macd_line_prev          NUMERIC(10,6),
    macd_signal_prev        NUMERIC(10,6),
    rsi_7                   NUMERIC(6,2),
    rsi_14                  NUMERIC(6,2),
    rsi_21                  NUMERIC(6,2),
    stoch_k                 NUMERIC(6,2),
    stoch_d                 NUMERIC(6,2),
    bb_upper                NUMERIC(12,4),
    bb_mid                  NUMERIC(12,4),
    bb_lower                NUMERIC(12,4),
    bb_pct                  NUMERIC(8,4),
    bb_width                NUMERIC(8,4),
    adx                     NUMERIC(6,2),
    di_plus                 NUMERIC(6,2),
    di_minus                NUMERIC(6,2),
    cci                     NUMERIC(10,4),
    williams_r              NUMERIC(6,2),
    roc_10                  NUMERIC(8,4),
    roc_20                  NUMERIC(8,4),
    atr_14                  NUMERIC(10,4),
    obv                     BIGINT,
    vwap_20d                NUMERIC(12,4),
    cmf_20                  NUMERIC(8,4),
    mfi_14                  NUMERIC(6,2),
    aroon_up                NUMERIC(6,2),
    aroon_down              NUMERIC(6,2),

    -- ── Daily Signals ─────────────────────────────────────────
    golden_cross            BOOLEAN,
    death_cross             BOOLEAN,
    above_sma20             BOOLEAN,
    above_sma50             BOOLEAN,
    above_sma200            BOOLEAN,
    rsi_overbought          BOOLEAN,
    rsi_oversold            BOOLEAN,
    macd_bullish_cross      BOOLEAN,
    macd_bearish_cross      BOOLEAN,

    -- ── Weekly Technicals ─────────────────────────────────────
    rsi_14_weekly           NUMERIC(6,2),
    macd_line_weekly        NUMERIC(10,6),
    macd_signal_weekly      NUMERIC(10,6),
    adx_weekly              NUMERIC(6,2),
    stoch_k_weekly          NUMERIC(6,2),
    bb_pct_weekly           NUMERIC(8,4),
    aroon_up_weekly         NUMERIC(6,2),
    aroon_down_weekly       NUMERIC(6,2),
    weekly_return           NUMERIC(8,4),
    return_4w               NUMERIC(8,4),
    return_13w              NUMERIC(8,4),
    return_52w              NUMERIC(8,4),

    -- ── Monthly Technicals ────────────────────────────────────
    rsi_14_monthly          NUMERIC(6,2),
    bb_pct_monthly          NUMERIC(8,4),
    volatility_1m           NUMERIC(8,4),
    volatility_3m           NUMERIC(8,4),
    volatility_12m          NUMERIC(8,4),

    -- ── Half-Yearly ───────────────────────────────────────────
    revenue_h1              NUMERIC(18,2),
    ebit_h1                 NUMERIC(18,2),
    net_income_h1           NUMERIC(18,2),
    eps_h1                  NUMERIC(10,4),
    dps_h1                  NUMERIC(10,4),
    gross_margin_h1         NUMERIC(8,4),
    ebit_margin_h1          NUMERIC(8,4),
    net_margin_h1           NUMERIC(8,4),
    revenue_growth_hoh      NUMERIC(8,4),
    revenue_growth_yoy_h    NUMERIC(8,4),
    net_income_growth_hoh   NUMERIC(8,4),
    net_income_growth_yoy_h NUMERIC(8,4),
    eps_growth_hoh          NUMERIC(8,4),
    eps_growth_yoy_h        NUMERIC(8,4),

    -- ── Quarterly Embedding ───────────────────────────────────
    revenue_latest_q        NUMERIC(18,2),
    ebit_latest_q           NUMERIC(18,2),
    net_income_latest_q     NUMERIC(18,2),
    eps_latest_q            NUMERIC(10,4),
    gross_margin_latest_q   NUMERIC(8,4),
    ebit_margin_latest_q    NUMERIC(8,4),
    net_margin_latest_q     NUMERIC(8,4),
    revenue_growth_qoq      NUMERIC(8,4),
    revenue_growth_yoy_q    NUMERIC(8,4),
    net_income_growth_qoq   NUMERIC(8,4),
    net_income_growth_yoy_q NUMERIC(8,4),
    eps_growth_yoy_q        NUMERIC(8,4),
    revenue_prev_q          NUMERIC(18,2),
    net_income_prev_q       NUMERIC(18,2),
    ebit_margin_prev_q      NUMERIC(8,4),
    revenue_q2              NUMERIC(18,2),
    net_income_q2           NUMERIC(18,2),
    revenue_same_q_prior_yr    NUMERIC(18,2),
    net_income_same_q_prior_yr NUMERIC(18,2),
    eps_same_q_prior_yr        NUMERIC(10,4),

    -- ── Short Interest ────────────────────────────────────────
    short_position          NUMERIC(18,2),
    short_pct_of_float      NUMERIC(8,4),
    short_pct_change_1w     NUMERIC(8,4),
    short_pct_change_4w     NUMERIC(8,4),

    -- ── Mining ────────────────────────────────────────────────
    ore_reserve_mt          NUMERIC(14,2),
    mineral_resource_mt     NUMERIC(14,2),
    aisc_per_oz             NUMERIC(10,2),
    production_oz           NUMERIC(14,2),
    reserve_life_years      NUMERIC(6,2),
    commodity_primary       TEXT,
    development_stage       TEXT,

    -- ── REIT ──────────────────────────────────────────────────
    nta_per_unit            NUMERIC(10,4),
    distribution_yield      NUMERIC(8,4),
    distribution_per_unit   NUMERIC(10,4),
    funds_from_operations   NUMERIC(18,2),
    gearing_ratio           NUMERIC(8,4),
    wale_years              NUMERIC(6,2),
    occupancy_rate          NUMERIC(6,4),
    property_sector         TEXT,

    -- ── Metadata ─────────────────────────────────────────────
    last_updated            TIMESTAMPTZ  DEFAULT NOW(),
    build_version           VARCHAR(30)
);

-- Core screener indexes
CREATE INDEX idx_su_sector        ON market.screener_universe (sector)         WHERE is_active;
CREATE INDEX idx_su_industry      ON market.screener_universe (industry)        WHERE is_active;
CREATE INDEX idx_su_market_cap    ON market.screener_universe (market_cap DESC) WHERE is_active;
CREATE INDEX idx_su_pe            ON market.screener_universe (pe_ratio)        WHERE is_active;
CREATE INDEX idx_su_roe           ON market.screener_universe (roe DESC)        WHERE is_active;
CREATE INDEX idx_su_revenue       ON market.screener_universe (revenue DESC)    WHERE is_active;
CREATE INDEX idx_su_rev_growth    ON market.screener_universe (revenue_cagr_5y) WHERE is_active;
CREATE INDEX idx_su_eps_growth    ON market.screener_universe (eps_cagr_5y)     WHERE is_active;
CREATE INDEX idx_su_div_yield     ON market.screener_universe (dividend_yield DESC) WHERE is_active;
CREATE INDEX idx_su_piotroski     ON market.screener_universe (piotroski_score DESC) WHERE is_active;
CREATE INDEX idx_su_rsi14         ON market.screener_universe (rsi_14)          WHERE is_active;
CREATE INDEX idx_su_52w_high      ON market.screener_universe (pct_from_52w_high DESC) WHERE is_active;
CREATE INDEX idx_su_golden_cross  ON market.screener_universe (golden_cross)    WHERE is_active AND golden_cross;
CREATE INDEX idx_su_above_sma200  ON market.screener_universe (above_sma200)    WHERE is_active;

-- Composite indexes for common screener patterns
CREATE INDEX idx_su_value   ON market.screener_universe (pe_ratio, dividend_yield, market_cap) WHERE is_active;
CREATE INDEX idx_su_quality ON market.screener_universe (roe, piotroski_score, debt_to_equity) WHERE is_active;
CREATE INDEX idx_su_growth  ON market.screener_universe (revenue_cagr_5y, eps_cagr_5y, net_income_cagr_5y) WHERE is_active;
CREATE INDEX idx_su_tech    ON market.screener_universe (rsi_14, adx, macd_hist) WHERE is_active;

COMMENT ON TABLE market.screener_universe IS
    'Golden Record: one denormalized row per ASX stock. '
    'Rebuilt nightly by jobs/build_screener_universe.py. '
    'All screener queries hit this table only — no JOINs at query time.';
