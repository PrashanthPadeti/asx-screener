-- ─────────────────────────────────────────────────────────────
--  Migration 009 — market.screener_universe
--  The Golden Record Table: ONE row per ASX stock.
--  All ~458 metrics pre-computed and flattened for sub-10ms
--  screener queries with no JOINs.
--
--  Populated by: jobs/build_screener_universe.py
--  Runs: nightly after all compute jobs complete (Seq 7 done)
--  Also runs: after quarterly financial load (compute_yearly done)
--
--  Sources joined at build time:
--    market.companies
--    market.daily_prices             (latest row)
--    market.daily_metrics            (latest row)
--    market.weekly_metrics           (latest row)
--    market.monthly_metrics          (latest row)
--    market.yearly_metrics           (latest fiscal year)
--    market.halfyearly_metrics       (latest 2 halves)
--    market.quarterly_metrics        (latest 4 quarters)
--    financials.annual_pnl           (FY0, FY1, FY2, FY3, FY5, FY7, FY10)
--    financials.annual_balance_sheet (same years)
--    financials.annual_cashflow      (same years)
--    market.short_interest           (latest row)
--    financials.reit_data            (latest row, REITs only)
--    financials.mining_data          (latest row, miners only)
-- ─────────────────────────────────────────────────────────────

CREATE TABLE market.screener_universe (

    -- ═══════════════════════════════════════════════════════
    --  CAT 1 — STOCK IDENTITY (22 columns)
    --  Source: market.companies
    -- ═══════════════════════════════════════════════════════
    asx_code                VARCHAR(10)  PRIMARY KEY,
    company_name            TEXT,
    short_name              TEXT,
    sector                  TEXT,                    -- GICS Sector
    industry_group          TEXT,                    -- GICS Industry Group
    industry                TEXT,                    -- GICS Industry
    sub_industry            TEXT,                    -- GICS Sub-Industry
    listing_date            DATE,
    market_cap_tier         TEXT,                    -- 'large'|'mid'|'small'|'micro'
    is_active               BOOLEAN,
    is_dividend_paying      BOOLEAN,
    is_profitable           BOOLEAN,                 -- net_income > 0 latest FY
    stock_type              TEXT,                    -- 'equity'|'reit'|'lic'|'etf'|'stapled'
    isin                    VARCHAR(20),
    abn                     VARCHAR(20),
    website                 TEXT,
    employee_count          INTEGER,
    founded_year            SMALLINT,
    country_of_incorporation VARCHAR(50),
    shares_outstanding      BIGINT,
    shares_float            BIGINT,
    fiscal_year_end_month   SMALLINT,                -- 6=June, 12=December

    -- ═══════════════════════════════════════════════════════
    --  CAT 2 — PRICE & MARKET DATA (24 columns)
    --  Source: market.daily_prices (latest)
    -- ═══════════════════════════════════════════════════════
    last_price              NUMERIC(12,4),
    prev_close              NUMERIC(12,4),
    open_price              NUMERIC(12,4),
    day_high                NUMERIC(12,4),
    day_low                 NUMERIC(12,4),
    price_change            NUMERIC(10,4),           -- close - prev_close
    price_change_pct        NUMERIC(8,4),            -- daily % change
    week_52_high            NUMERIC(12,4),
    week_52_low             NUMERIC(12,4),
    week_52_high_date       DATE,
    week_52_low_date        DATE,
    ath_price               NUMERIC(12,4),           -- all-time high (adj)
    ath_date                DATE,
    atl_price               NUMERIC(12,4),           -- all-time low (adj)
    price_to_52w_high       NUMERIC(8,4),            -- close / 52w_high
    price_to_52w_low        NUMERIC(8,4),            -- close / 52w_low
    drawdown_from_ath       NUMERIC(8,4),            -- % below ATH
    market_cap              NUMERIC(18,2),           -- AUD millions
    enterprise_value        NUMERIC(18,2),           -- AUD millions
    volume                  BIGINT,
    avg_volume_10d          BIGINT,
    avg_volume_20d          BIGINT,
    avg_volume_50d          BIGINT,
    relative_volume         NUMERIC(8,4),            -- volume / avg_volume_20d

    -- ═══════════════════════════════════════════════════════
    --  CAT 3 — MOVING AVERAGES & DMA RATIOS (20 columns)
    --  Source: market.daily_metrics (latest)
    -- ═══════════════════════════════════════════════════════
    sma_5                   NUMERIC(12,4),
    sma_10                  NUMERIC(12,4),
    sma_20                  NUMERIC(12,4),
    sma_50                  NUMERIC(12,4),
    sma_100                 NUMERIC(12,4),
    sma_200                 NUMERIC(12,4),
    ema_12                  NUMERIC(12,4),
    ema_20                  NUMERIC(12,4),
    ema_26                  NUMERIC(12,4),
    ema_50                  NUMERIC(12,4),
    ema_200                 NUMERIC(12,4),
    dma20_ratio             NUMERIC(8,4),            -- close / sma_20
    dma50_ratio             NUMERIC(8,4),            -- close / sma_50  (50DMA Ratio)
    dma200_ratio            NUMERIC(8,4),            -- close / sma_200 (200DMA Ratio)
    sma_50_prev_day         NUMERIC(12,4),           -- yesterday's sma_50 (crossover detection)
    sma_200_prev_day        NUMERIC(12,4),
    above_sma20             BOOLEAN,
    above_sma50             BOOLEAN,
    above_sma100            BOOLEAN,
    above_sma200            BOOLEAN,

    -- ═══════════════════════════════════════════════════════
    --  CAT 4 — MOMENTUM & OSCILLATORS (18 columns)
    --  Source: market.daily_metrics (latest)
    -- ═══════════════════════════════════════════════════════
    rsi_7                   NUMERIC(6,2),
    rsi_14                  NUMERIC(6,2),
    rsi_21                  NUMERIC(6,2),
    macd_line               NUMERIC(10,4),
    macd_signal             NUMERIC(10,4),
    macd_hist               NUMERIC(10,4),
    macd_line_prev_day      NUMERIC(10,4),
    macd_signal_prev_day    NUMERIC(10,4),
    stoch_k                 NUMERIC(6,2),
    stoch_d                 NUMERIC(6,2),
    cci_20                  NUMERIC(10,4),
    williams_r              NUMERIC(6,2),
    roc_10                  NUMERIC(8,4),
    roc_20                  NUMERIC(8,4),
    mfi_14                  NUMERIC(6,2),
    momentum_1m             NUMERIC(8,4),
    momentum_3m             NUMERIC(8,4),
    momentum_6m             NUMERIC(8,4),

    -- ═══════════════════════════════════════════════════════
    --  CAT 5 — TREND INDICATORS (10 columns)
    --  Source: market.daily_metrics (latest)
    -- ═══════════════════════════════════════════════════════
    adx_14                  NUMERIC(6,2),
    plus_di                 NUMERIC(6,2),
    minus_di                NUMERIC(6,2),
    aroon_up                NUMERIC(6,2),
    aroon_down              NUMERIC(6,2),
    aroon_oscillator        NUMERIC(6,2),
    golden_cross            BOOLEAN,                 -- sma_50 crossed above sma_200
    death_cross             BOOLEAN,
    new_52w_high            BOOLEAN,
    new_52w_low             BOOLEAN,

    -- ═══════════════════════════════════════════════════════
    --  CAT 6 — VOLATILITY (14 columns)
    --  Source: market.daily_metrics (latest)
    -- ═══════════════════════════════════════════════════════
    atr_14                  NUMERIC(10,4),
    atr_pct                 NUMERIC(8,4),            -- ATR / close
    bb_upper                NUMERIC(12,4),
    bb_mid                  NUMERIC(12,4),
    bb_lower                NUMERIC(12,4),
    bb_pct                  NUMERIC(8,4),            -- Bollinger %B
    bb_width                NUMERIC(8,4),
    hv_20d                  NUMERIC(8,4),            -- 20-day historical vol (annualised %)
    hv_60d                  NUMERIC(8,4),
    hv_1y                   NUMERIC(8,4),
    beta_1y                 NUMERIC(8,4),
    beta_3y                 NUMERIC(8,4),
    beta_5y                 NUMERIC(8,4),
    true_range              NUMERIC(10,4),

    -- ═══════════════════════════════════════════════════════
    --  CAT 7 — VOLUME & BREADTH (8 columns)
    --  Source: market.daily_metrics (latest)
    -- ═══════════════════════════════════════════════════════
    obv                     BIGINT,
    obv_ema                 BIGINT,
    vwap                    NUMERIC(12,4),
    cmf_20                  NUMERIC(8,4),
    mfi_volume              NUMERIC(6,2),            -- MFI (separate from mfi_14 above)
    avg_volume_1w           BIGINT,
    avg_volume_1m           BIGINT,
    avg_volume_1y           BIGINT,

    -- ═══════════════════════════════════════════════════════
    --  CAT 8 — PRICE RETURNS (14 columns)
    --  Source: market.daily_metrics + monthly_metrics
    -- ═══════════════════════════════════════════════════════
    return_1d               NUMERIC(8,4),
    return_1w               NUMERIC(8,4),
    return_1m               NUMERIC(8,4),
    return_3m               NUMERIC(8,4),
    return_6m               NUMERIC(8,4),
    return_ytd              NUMERIC(8,4),
    return_1y               NUMERIC(8,4),
    return_3y               NUMERIC(8,4),
    return_5y               NUMERIC(8,4),
    return_7y               NUMERIC(8,4),
    return_10y              NUMERIC(8,4),
    price_cagr_3y           NUMERIC(8,4),
    price_cagr_5y           NUMERIC(8,4),
    price_cagr_10y          NUMERIC(8,4),

    -- ═══════════════════════════════════════════════════════
    --  CAT 9 — RISK-ADJUSTED PERFORMANCE (10 columns)
    --  Source: market.yearly_metrics (latest FY)
    -- ═══════════════════════════════════════════════════════
    sharpe_1y               NUMERIC(8,4),
    sharpe_3y               NUMERIC(8,4),
    sortino_1y              NUMERIC(8,4),
    calmar_ratio            NUMERIC(8,4),
    max_drawdown_1y         NUMERIC(8,4),
    max_drawdown_3y         NUMERIC(8,4),
    alpha_1y                NUMERIC(8,4),
    alpha_3y                NUMERIC(8,4),
    var_95_1d               NUMERIC(8,4),            -- Value at Risk 95%
    relative_strength_xjo   NUMERIC(8,4),            -- vs ASX 200 1Y return

    -- ═══════════════════════════════════════════════════════
    --  CAT 10 — INCOME STATEMENT: CURRENT FY (FY0) (24 columns)
    --  Source: financials.annual_pnl (latest fiscal_year)
    -- ═══════════════════════════════════════════════════════
    revenue                 NUMERIC(18,2),           -- AUD millions
    revenue_growth_yoy      NUMERIC(8,4),
    gross_profit            NUMERIC(18,2),
    ebitda                  NUMERIC(18,2),
    ebitda_growth_yoy       NUMERIC(8,4),
    ebit                    NUMERIC(18,2),           -- operating profit
    depreciation_amort      NUMERIC(18,2),
    interest_expense        NUMERIC(18,2),
    other_income            NUMERIC(18,2),           -- non-operating income
    pretax_income           NUMERIC(18,2),
    income_tax              NUMERIC(18,2),
    current_tax             NUMERIC(18,2),
    net_income              NUMERIC(18,2),
    net_income_growth_yoy   NUMERIC(8,4),
    extraordinary_items     NUMERIC(18,2),
    material_cost           NUMERIC(18,2),
    employee_cost           NUMERIC(18,2),
    operating_cashflow      NUMERIC(18,2),
    investing_cashflow      NUMERIC(18,2),
    financing_cashflow      NUMERIC(18,2),
    free_cashflow           NUMERIC(18,2),
    capex                   NUMERIC(18,2),
    capex_to_revenue        NUMERIC(8,4),
    dividend_paid_total     NUMERIC(18,2),

    -- ═══════════════════════════════════════════════════════
    --  CAT 10b — INCOME STATEMENT: LAST YEAR (FY1) (14 columns)
    --  Source: financials.annual_pnl (fiscal_year = latest - 1)
    -- ═══════════════════════════════════════════════════════
    revenue_fy1             NUMERIC(18,2),
    ebit_fy1                NUMERIC(18,2),
    ebitda_fy1              NUMERIC(18,2),
    net_income_fy1          NUMERIC(18,2),
    other_income_fy1        NUMERIC(18,2),
    interest_expense_fy1    NUMERIC(18,2),
    depreciation_fy1        NUMERIC(18,2),
    pretax_income_fy1       NUMERIC(18,2),
    income_tax_fy1          NUMERIC(18,2),
    eps_fy1                 NUMERIC(10,4),
    dps_fy1                 NUMERIC(10,4),
    ebit_margin_fy1         NUMERIC(8,4),            -- OPM last year
    net_margin_fy1          NUMERIC(8,4),            -- NPM last year
    gross_margin_fy1        NUMERIC(8,4),

    -- ═══════════════════════════════════════════════════════
    --  CAT 10c — INCOME STATEMENT: PRECEDING YEAR (FY2) (6 columns)
    --  Source: financials.annual_pnl (fiscal_year = latest - 2)
    -- ═══════════════════════════════════════════════════════
    revenue_fy2             NUMERIC(18,2),
    ebit_fy2                NUMERIC(18,2),
    net_income_fy2          NUMERIC(18,2),
    eps_fy2                 NUMERIC(10,4),
    ebit_margin_fy2         NUMERIC(8,4),
    net_margin_fy2          NUMERIC(8,4),

    -- ═══════════════════════════════════════════════════════
    --  CAT 10d — TTM (Trailing Twelve Months) (2 columns)
    --  Source: market.yearly_metrics or quarterly_metrics sum
    -- ═══════════════════════════════════════════════════════
    revenue_ttm             NUMERIC(18,2),
    net_income_ttm          NUMERIC(18,2),

    -- ═══════════════════════════════════════════════════════
    --  CAT 11 — MARGIN RATIOS: CURRENT FY (8 columns)
    --  Source: financials.annual_pnl (FY0) or yearly_metrics
    -- ═══════════════════════════════════════════════════════
    gross_margin            NUMERIC(8,4),
    ebitda_margin           NUMERIC(8,4),
    ebit_margin             NUMERIC(8,4),            -- OPM
    pretax_margin           NUMERIC(8,4),
    net_margin              NUMERIC(8,4),            -- NPM
    ocf_margin              NUMERIC(8,4),
    fcf_margin              NUMERIC(8,4),
    tax_rate_effective      NUMERIC(8,4),

    -- ═══════════════════════════════════════════════════════
    --  CAT 12 — BALANCE SHEET: CURRENT FY (FY0) (34 columns)
    --  Source: financials.annual_balance_sheet (latest)
    -- ═══════════════════════════════════════════════════════
    total_assets            NUMERIC(18,2),
    total_current_assets    NUMERIC(18,2),
    total_non_current_assets NUMERIC(18,2),
    cash_and_equivalents    NUMERIC(18,2),
    accounts_receivable     NUMERIC(18,2),
    inventory               NUMERIC(18,2),
    investments_lt          NUMERIC(18,2),           -- long-term investments
    gross_block             NUMERIC(18,2),           -- gross PPE before depreciation
    accumulated_depreciation NUMERIC(18,2),
    net_block               NUMERIC(18,2),           -- net PPE
    capital_wip             NUMERIC(18,2),           -- capital work in progress
    goodwill                NUMERIC(18,2),
    intangible_assets       NUMERIC(18,2),
    total_liabilities       NUMERIC(18,2),
    total_current_liabilities NUMERIC(18,2),
    total_non_current_liabilities NUMERIC(18,2),
    short_term_debt         NUMERIC(18,2),
    long_term_debt          NUMERIC(18,2),
    lease_liabilities       NUMERIC(18,2),
    trade_payables          NUMERIC(18,2),
    advance_from_customers  NUMERIC(18,2),
    contingent_liabilities  NUMERIC(18,2),
    total_equity            NUMERIC(18,2),
    equity_capital          NUMERIC(18,2),           -- paid-up share capital
    preference_capital      NUMERIC(18,2),
    reserves                NUMERIC(18,2),
    retained_earnings       NUMERIC(18,2),
    total_debt              NUMERIC(18,2),           -- short + long term debt
    net_debt                NUMERIC(18,2),           -- total_debt - cash
    working_capital         NUMERIC(18,2),
    invested_capital        NUMERIC(18,2),           -- equity + net_debt
    face_value              NUMERIC(10,4),           -- par value per share
    tangible_assets         NUMERIC(18,2),
    book_value_per_share    NUMERIC(10,4),

    -- ═══════════════════════════════════════════════════════
    --  CAT 12b — BALANCE SHEET: LAST YEAR (FY1) (3 columns)
    --  Source: financials.annual_balance_sheet (fiscal_year = latest - 1)
    -- ═══════════════════════════════════════════════════════
    total_debt_fy1          NUMERIC(18,2),
    working_capital_fy1     NUMERIC(18,2),
    net_block_fy1           NUMERIC(18,2),

    -- ═══════════════════════════════════════════════════════
    --  CAT 12c — BALANCE SHEET: HISTORICAL ACTUAL VALUES
    --  Source: financials.annual_balance_sheet (N years back)
    --  Used for: "Debt 5Years back < Current Debt" type filters
    -- ═══════════════════════════════════════════════════════
    total_debt_3y           NUMERIC(18,2),           -- debt value 3 fiscal years ago
    total_debt_5y           NUMERIC(18,2),
    total_debt_7y           NUMERIC(18,2),
    total_debt_10y          NUMERIC(18,2),
    working_capital_3y      NUMERIC(18,2),
    working_capital_5y      NUMERIC(18,2),
    working_capital_7y      NUMERIC(18,2),
    working_capital_10y     NUMERIC(18,2),
    net_block_3y            NUMERIC(18,2),
    net_block_5y            NUMERIC(18,2),
    net_block_7y            NUMERIC(18,2),

    -- ═══════════════════════════════════════════════════════
    --  CAT 13 — PER SHARE METRICS (10 columns)
    --  Source: financials.annual_pnl + yearly_metrics
    -- ═══════════════════════════════════════════════════════
    eps                     NUMERIC(10,4),
    eps_diluted             NUMERIC(10,4),
    eps_growth_yoy          NUMERIC(8,4),
    bvps                    NUMERIC(10,4),
    tbvps                   NUMERIC(10,4),           -- tangible book value per share
    dps                     NUMERIC(10,4),
    fcf_per_share           NUMERIC(10,4),
    ocf_per_share           NUMERIC(10,4),
    revenue_per_share       NUMERIC(10,4),
    net_debt_per_share      NUMERIC(10,4),

    -- ═══════════════════════════════════════════════════════
    --  CAT 14 — VALUATION RATIOS (18 columns)
    --  Source: market.yearly_metrics (latest FY)
    -- ═══════════════════════════════════════════════════════
    pe_ratio                NUMERIC(10,2),
    pe_5y_avg               NUMERIC(10,2),
    pb_ratio                NUMERIC(10,2),
    ps_ratio                NUMERIC(10,2),
    pcf_ratio               NUMERIC(10,2),
    p_fcf_ratio             NUMERIC(10,2),
    ev_ebitda               NUMERIC(10,2),
    ev_ebit                 NUMERIC(10,2),
    ev_revenue              NUMERIC(10,2),
    ev_fcf                  NUMERIC(10,2),
    peg_ratio               NUMERIC(10,4),
    earnings_yield          NUMERIC(8,4),            -- EPS / price (%)
    fcf_yield               NUMERIC(8,4),            -- FCF/share / price (%)
    dividend_yield          NUMERIC(8,4),
    franking_pct            NUMERIC(5,2),            -- 0–100
    franked_yield           NUMERIC(8,4),            -- grossed-up dividend yield
    payout_ratio            NUMERIC(8,4),
    graham_number           NUMERIC(12,4),

    -- ═══════════════════════════════════════════════════════
    --  CAT 15 — RETURN ON CAPITAL (6 columns)
    --  Source: market.yearly_metrics (latest FY)
    -- ═══════════════════════════════════════════════════════
    roe                     NUMERIC(8,4),
    roa                     NUMERIC(8,4),
    roic                    NUMERIC(8,4),
    roce                    NUMERIC(8,4),
    roae                    NUMERIC(8,4),
    roaa                    NUMERIC(8,4),

    -- ═══════════════════════════════════════════════════════
    --  CAT 16 — EFFICIENCY RATIOS (9 columns)
    --  Source: market.yearly_metrics (latest FY)
    -- ═══════════════════════════════════════════════════════
    asset_turnover          NUMERIC(8,4),
    inventory_turnover      NUMERIC(8,4),
    receivables_turnover    NUMERIC(8,4),
    receivables_days        NUMERIC(8,2),            -- DSO
    inventory_days          NUMERIC(8,2),            -- DIO
    payables_days           NUMERIC(8,2),            -- DPO
    cash_conversion_cycle   NUMERIC(8,2),
    revenue_per_employee    NUMERIC(14,2),
    capex_intensity         NUMERIC(8,4),

    -- ═══════════════════════════════════════════════════════
    --  CAT 17 — LEVERAGE & LIQUIDITY (12 columns)
    --  Source: market.yearly_metrics (latest FY)
    -- ═══════════════════════════════════════════════════════
    current_ratio           NUMERIC(8,4),
    quick_ratio             NUMERIC(8,4),
    cash_ratio              NUMERIC(8,4),
    debt_to_equity          NUMERIC(10,4),
    debt_to_assets          NUMERIC(8,4),
    debt_to_ebitda          NUMERIC(10,4),
    net_debt_to_ebitda      NUMERIC(10,4),
    net_debt_to_equity      NUMERIC(10,4),
    interest_coverage       NUMERIC(10,4),
    equity_multiplier       NUMERIC(10,4),
    lt_debt_to_capital      NUMERIC(8,4),
    altman_z_score          NUMERIC(8,4),

    -- ═══════════════════════════════════════════════════════
    --  CAT 18 — QUALITY & COMPOSITE SCORES (5 columns)
    --  Source: market.yearly_metrics (latest FY)
    -- ═══════════════════════════════════════════════════════
    piotroski_f_score       SMALLINT,
    beneish_m_score         NUMERIC(8,4),
    momentum_score          NUMERIC(6,2),            -- composite 1–100
    value_score             NUMERIC(6,2),            -- composite 1–100
    quality_score           NUMERIC(6,2),            -- composite 1–100

    -- ═══════════════════════════════════════════════════════
    --  CAT 19 — MULTI-YEAR GROWTH CAGRs (26 columns)
    --  Source: market.yearly_metrics (latest FY)
    -- ═══════════════════════════════════════════════════════
    revenue_cagr_3y         NUMERIC(8,4),            -- Sales growth 3Years
    revenue_cagr_5y         NUMERIC(8,4),            -- Sales growth 5Years
    revenue_cagr_7y         NUMERIC(8,4),            -- Sales growth 7Years
    revenue_cagr_10y        NUMERIC(8,4),            -- Sales growth 10Years
    revenue_growth_median_5y  NUMERIC(8,4),
    revenue_growth_median_10y NUMERIC(8,4),
    net_income_cagr_3y      NUMERIC(8,4),            -- Profit growth 3Years
    net_income_cagr_5y      NUMERIC(8,4),
    net_income_cagr_7y      NUMERIC(8,4),
    net_income_cagr_10y     NUMERIC(8,4),
    eps_cagr_3y             NUMERIC(8,4),            -- EPS growth 3Years
    eps_cagr_5y             NUMERIC(8,4),
    eps_cagr_7y             NUMERIC(8,4),
    eps_cagr_10y            NUMERIC(8,4),
    ebitda_cagr_3y          NUMERIC(8,4),            -- EBIDT growth 3Years
    ebitda_cagr_5y          NUMERIC(8,4),
    ebitda_cagr_7y          NUMERIC(8,4),
    ebitda_cagr_10y         NUMERIC(8,4),
    fcf_cagr_3y             NUMERIC(8,4),
    fcf_cagr_5y             NUMERIC(8,4),
    gross_profit_cagr_3y    NUMERIC(8,4),
    gross_profit_cagr_5y    NUMERIC(8,4),
    bvps_cagr_3y            NUMERIC(8,4),
    bvps_cagr_5y            NUMERIC(8,4),
    dividend_cagr_3y        NUMERIC(8,4),
    dividend_cagr_5y        NUMERIC(8,4),

    -- ═══════════════════════════════════════════════════════
    --  CAT 20 — MULTI-YEAR AVERAGES (28 columns)
    --  Source: market.yearly_metrics (latest FY)
    -- ═══════════════════════════════════════════════════════
    avg_roe_3y              NUMERIC(8,4),            -- Average ROE 3Years
    avg_roe_5y              NUMERIC(8,4),
    avg_roe_7y              NUMERIC(8,4),
    avg_roe_10y             NUMERIC(8,4),
    avg_roa_3y              NUMERIC(8,4),
    avg_roa_5y              NUMERIC(8,4),
    avg_roic_3y             NUMERIC(8,4),
    avg_roic_5y             NUMERIC(8,4),
    avg_roce_3y             NUMERIC(8,4),            -- Avg ROCE 3Years
    avg_roce_5y             NUMERIC(8,4),
    avg_roce_7y             NUMERIC(8,4),
    avg_roce_10y            NUMERIC(8,4),
    avg_gross_margin_3y     NUMERIC(8,4),
    avg_gross_margin_5y     NUMERIC(8,4),
    avg_ebitda_margin_3y    NUMERIC(8,4),
    avg_ebitda_margin_5y    NUMERIC(8,4),
    avg_operating_margin_3y  NUMERIC(8,4),
    avg_operating_margin_5y  NUMERIC(8,4),          -- OPM 5Year
    avg_operating_margin_10y NUMERIC(8,4),          -- OPM 10Year
    avg_net_margin_3y       NUMERIC(8,4),
    avg_net_margin_5y       NUMERIC(8,4),
    avg_net_margin_10y      NUMERIC(8,4),
    avg_fcf_margin_3y       NUMERIC(8,4),
    avg_fcf_margin_5y       NUMERIC(8,4),
    avg_eps_growth_3y       NUMERIC(8,4),
    avg_eps_growth_5y       NUMERIC(8,4),           -- Average Earnings 5Year
    avg_eps_growth_10y      NUMERIC(8,4),           -- Average Earnings 10Year
    avg_current_ratio_3y    NUMERIC(8,4),

    -- ═══════════════════════════════════════════════════════
    --  CAT 20b — MULTI-YEAR AVERAGE VALUES (2 columns)
    -- ═══════════════════════════════════════════════════════
    avg_ebit_5y             NUMERIC(18,2),           -- Average EBIT 5Year (AUD millions)
    avg_ebit_10y            NUMERIC(18,2),           -- Average EBIT 10Year

    -- ═══════════════════════════════════════════════════════
    --  CAT 21 — DIVIDEND & INCOME (8 columns)
    --  Source: financials.annual_pnl + yearly_metrics
    -- ═══════════════════════════════════════════════════════
    dps_ttm                 NUMERIC(10,4),           -- DPS trailing 12 months
    dividend_yield_ttm      NUMERIC(8,4),
    franked_yield_ttm       NUMERIC(8,4),
    imputation_credit_per_share NUMERIC(10,4),
    grossed_up_dps          NUMERIC(10,4),
    dps_growth_yoy          NUMERIC(8,4),
    dividend_consecutive_yrs SMALLINT,
    dividend_growth_streak  SMALLINT,               -- years of consecutive increases

    -- ═══════════════════════════════════════════════════════
    --  CAT 21b — CASH FLOW: LAST YEAR (FY1) (6 columns)
    --  Source: financials.annual_cashflow (fiscal_year = latest - 1)
    -- ═══════════════════════════════════════════════════════
    ocf_fy1                 NUMERIC(18,2),
    fcf_fy1                 NUMERIC(18,2),
    investing_cf_fy1        NUMERIC(18,2),
    financing_cf_fy1        NUMERIC(18,2),
    net_cashflow_fy1        NUMERIC(18,2),
    cash_end_fy1            NUMERIC(18,2),

    -- ═══════════════════════════════════════════════════════
    --  CAT 21c — CASH FLOW: HISTORICAL ACTUAL VALUES (15 cols)
    --  Source: financials.annual_cashflow (N years back)
    --  Used for: "FCF 3Years > FCF 5Years" type filters
    -- ═══════════════════════════════════════════════════════
    fcf_3y                  NUMERIC(18,2),           -- FCF value 3 fiscal years ago
    fcf_5y                  NUMERIC(18,2),
    fcf_7y                  NUMERIC(18,2),
    fcf_10y                 NUMERIC(18,2),
    ocf_3y                  NUMERIC(18,2),
    ocf_5y                  NUMERIC(18,2),
    ocf_7y                  NUMERIC(18,2),
    ocf_10y                 NUMERIC(18,2),
    investing_cf_3y         NUMERIC(18,2),
    investing_cf_5y         NUMERIC(18,2),
    investing_cf_7y         NUMERIC(18,2),
    investing_cf_10y        NUMERIC(18,2),
    cash_3y                 NUMERIC(18,2),
    cash_5y                 NUMERIC(18,2),
    cash_7y                 NUMERIC(18,2),

    -- ═══════════════════════════════════════════════════════
    --  CAT 22 — SHORT SELLING / ASIC DATA (5 columns)
    --  Source: market.short_interest (latest)
    -- ═══════════════════════════════════════════════════════
    short_interest_pct      NUMERIC(8,4),            -- % of float sold short
    short_interest_shares   BIGINT,
    short_interest_ratio    NUMERIC(8,4),            -- days to cover
    short_change_1w         NUMERIC(8,4),
    short_change_1m         NUMERIC(8,4),

    -- ═══════════════════════════════════════════════════════
    --  CAT 23 — ASX-SPECIFIC (12 columns)
    --  Source: financials.reit_data + financials.mining_data
    -- ═══════════════════════════════════════════════════════
    nta_per_share           NUMERIC(10,4),           -- Net Tangible Assets/share (LICs)
    nta_discount_premium    NUMERIC(8,4),            -- (price - NTA) / NTA
    nav_per_share           NUMERIC(10,4),           -- Net Asset Value/unit (REITs)
    nav_discount_premium    NUMERIC(8,4),            -- (price - NAV) / NAV
    distribution_yield      NUMERIC(8,4),            -- annualised distribution yield
    management_expense_ratio NUMERIC(8,4),           -- MER % (REITs/ETFs/LICs)
    gearing_ratio           NUMERIC(8,4),            -- REIT leverage
    wale_years              NUMERIC(6,2),            -- Weighted Avg Lease Expiry
    ore_reserve_oz          NUMERIC(18,2),           -- gold equiv oz (Mining)
    ore_resource_oz         NUMERIC(18,2),
    aisc_per_oz             NUMERIC(10,4),           -- All-In Sustaining Cost/oz
    cash_cost_per_oz        NUMERIC(10,4),

    -- ═══════════════════════════════════════════════════════
    --  CAT 24 — QUARTERLY METRICS (29 columns)
    --  Source: market.quarterly_metrics (latest 4 quarters)
    -- ═══════════════════════════════════════════════════════

    -- Latest quarter (Q1 = most recent)
    revenue_latest_q        NUMERIC(18,2),
    gross_profit_latest_q   NUMERIC(18,2),
    ebitda_latest_q         NUMERIC(18,2),
    ebit_latest_q           NUMERIC(18,2),
    net_income_latest_q     NUMERIC(18,2),
    eps_latest_q            NUMERIC(10,4),
    gross_margin_latest_q   NUMERIC(8,4),            -- GPM latest Q
    ebit_margin_latest_q    NUMERIC(8,4),            -- OPM latest Q
    net_margin_latest_q     NUMERIC(8,4),            -- NPM latest Q
    last_quarterly_result_date DATE,

    -- QoQ growth (latest vs previous quarter)
    revenue_growth_qoq      NUMERIC(8,4),
    net_income_growth_qoq   NUMERIC(8,4),

    -- YoY quarterly growth (latest Q vs same Q prior year)
    revenue_growth_yoy_q    NUMERIC(8,4),            -- YOY Quarterly sales growth
    net_income_growth_yoy_q NUMERIC(8,4),            -- YOY Quarterly profit growth

    -- Previous quarter (Q-1)
    revenue_prev_q          NUMERIC(18,2),
    net_income_prev_q       NUMERIC(18,2),
    ebit_prev_q             NUMERIC(18,2),
    eps_prev_q              NUMERIC(10,4),
    ebit_margin_prev_q      NUMERIC(8,4),

    -- 2 quarters back (Q-2)
    revenue_q2              NUMERIC(18,2),           -- Sales 2quarters back
    net_income_q2           NUMERIC(18,2),
    ebit_q2                 NUMERIC(18,2),

    -- 3 quarters back (Q-3)
    revenue_q3              NUMERIC(18,2),           -- Sales 3quarters back
    net_income_q3           NUMERIC(18,2),
    ebit_q3                 NUMERIC(18,2),

    -- Same quarter prior year (Q-4, for YoY reference)
    revenue_same_q_prior_yr NUMERIC(18,2),
    net_income_same_q_prior_yr NUMERIC(18,2),
    ebit_same_q_prior_yr    NUMERIC(18,2),
    ebit_margin_same_q_prior_yr NUMERIC(8,4),

    -- ═══════════════════════════════════════════════════════
    --  CAT 25 — INSIDER & INSTITUTIONAL HOLDING (3 columns)
    --  Source: market.companies supplementary data
    -- ═══════════════════════════════════════════════════════
    insider_holding_pct     NUMERIC(8,4),            -- director/substantial holder %
    institutional_holding_pct NUMERIC(8,4),
    insider_holding_change_1y NUMERIC(8,4),          -- ASX equivalent of "promoter change"

    -- ═══════════════════════════════════════════════════════
    --  CAT 26 — METADATA & FRESHNESS (10 columns)
    -- ═══════════════════════════════════════════════════════
    price_date              DATE,                    -- date of last_price
    fundamentals_fy         SMALLINT,                -- fiscal year of financial data used
    fundamentals_period_end DATE,                    -- period end date of financials
    financials_currency     VARCHAR(5) DEFAULT 'AUD',
    last_annual_result_date DATE,                    -- date of last annual result filing
    last_quarterly_result_date_meta DATE,            -- date of last quarterly filing
    data_source             TEXT DEFAULT 'eodhd',
    compute_version         VARCHAR(20),
    last_updated            TIMESTAMPTZ DEFAULT NOW(),
    stale_flag              BOOLEAN DEFAULT FALSE     -- TRUE if price > 3 days old
);

-- ─────────────────────────────────────────────────────────────
--  Indexes — cover all common screener filter patterns
-- ─────────────────────────────────────────────────────────────

-- Primary screener filters: fundamentals
CREATE INDEX idx_su_roe           ON market.screener_universe (roe);
CREATE INDEX idx_su_roce          ON market.screener_universe (roce);
CREATE INDEX idx_su_roic          ON market.screener_universe (roic);
CREATE INDEX idx_su_pe            ON market.screener_universe (pe_ratio);
CREATE INDEX idx_su_pb            ON market.screener_universe (pb_ratio);
CREATE INDEX idx_su_ps            ON market.screener_universe (ps_ratio);
CREATE INDEX idx_su_ev_ebitda     ON market.screener_universe (ev_ebitda);
CREATE INDEX idx_su_net_margin    ON market.screener_universe (net_margin);
CREATE INDEX idx_su_ebit_margin   ON market.screener_universe (ebit_margin);
CREATE INDEX idx_su_div_yield     ON market.screener_universe (dividend_yield);
CREATE INDEX idx_su_franked_yield ON market.screener_universe (franked_yield);
CREATE INDEX idx_su_debt_eq       ON market.screener_universe (debt_to_equity);
CREATE INDEX idx_su_piotroski     ON market.screener_universe (piotroski_f_score);
CREATE INDEX idx_su_market_cap    ON market.screener_universe (market_cap);

-- Multi-year growth filters
CREATE INDEX idx_su_rev_cagr5     ON market.screener_universe (revenue_cagr_5y);
CREATE INDEX idx_su_pat_cagr5     ON market.screener_universe (net_income_cagr_5y);
CREATE INDEX idx_su_eps_cagr5     ON market.screener_universe (eps_cagr_5y);
CREATE INDEX idx_su_avg_roce5     ON market.screener_universe (avg_roce_5y);
CREATE INDEX idx_su_avg_roe5      ON market.screener_universe (avg_roe_5y);
CREATE INDEX idx_su_price_cagr5   ON market.screener_universe (price_cagr_5y);

-- Technical filters
CREATE INDEX idx_su_rsi14         ON market.screener_universe (rsi_14);
CREATE INDEX idx_su_dma50         ON market.screener_universe (dma50_ratio);
CREATE INDEX idx_su_dma200        ON market.screener_universe (dma200_ratio);
CREATE INDEX idx_su_macd_hist     ON market.screener_universe (macd_hist);
CREATE INDEX idx_su_adx           ON market.screener_universe (adx_14);

-- Sector / industry filter
CREATE INDEX idx_su_sector        ON market.screener_universe (sector);
CREATE INDEX idx_su_industry      ON market.screener_universe (industry);
CREATE INDEX idx_su_mcap_tier     ON market.screener_universe (market_cap_tier);
CREATE INDEX idx_su_stock_type    ON market.screener_universe (stock_type);

-- Short interest
CREATE INDEX idx_su_short         ON market.screener_universe (short_interest_pct);

-- Freshness
CREATE INDEX idx_su_updated       ON market.screener_universe (last_updated DESC);

-- ─────────────────────────────────────────────────────────────
--  Composite indexes for common combined screener queries
-- ─────────────────────────────────────────────────────────────

-- Value screen: low PE + high dividend yield
CREATE INDEX idx_su_value_screen ON market.screener_universe (pe_ratio, dividend_yield, market_cap)
    WHERE is_active = TRUE;

-- Quality screen: high ROCE + low debt
CREATE INDEX idx_su_quality_screen ON market.screener_universe (avg_roce_5y, debt_to_equity)
    WHERE is_active = TRUE AND is_profitable = TRUE;

-- Growth screen: high revenue CAGR + high profit CAGR
CREATE INDEX idx_su_growth_screen ON market.screener_universe (revenue_cagr_5y, net_income_cagr_5y)
    WHERE is_active = TRUE;

-- Technical screen: RSI + DMA
CREATE INDEX idx_su_tech_screen ON market.screener_universe (rsi_14, dma50_ratio, dma200_ratio)
    WHERE is_active = TRUE;

COMMENT ON TABLE market.screener_universe IS
'Golden Record table: one row per ASX stock with ~458 pre-computed metrics.
 Rebuilt nightly by jobs/build_screener_universe.py after all compute jobs complete.
 Never query source tables for screener — always query this table.';
