-- Migration 015: Pipeline support tables
-- ========================================
-- New tables required to complete the EODHD pipeline:
--   market.valuation_snapshot    — EODHD highlights + valuation (snapshot per stock)
--   market.exchange_list         — ASX exchange symbol list
--   financials.earnings_quarterly — EPS actuals vs estimates per quarter
--   screener schema              — screener.universe, screener.fundamentals (view),
--                                  screener.technicals (view)

-- ─── market.valuation_snapshot ───────────────────────────────────────────────
-- Latest EODHD-provided valuation metrics (Highlights + Valuation sections).
-- Updated weekly from fundamentals refresh. One row per stock.

CREATE TABLE IF NOT EXISTS market.valuation_snapshot (
    asx_code                        VARCHAR(10)     PRIMARY KEY,

    -- From Highlights
    market_cap                      NUMERIC(20,2),              -- AUD
    pe_ratio                        NUMERIC(12,4),
    peg_ratio                       NUMERIC(12,4),
    price_to_book                   NUMERIC(12,4),              -- PriceBookMRQ
    price_to_sales                  NUMERIC(12,4),              -- PriceSalesTTM
    dividend_yield                  NUMERIC(18,6),              -- 0.0412 = 4.12%
    dividend_per_share              NUMERIC(18,6),
    eps_ttm                         NUMERIC(18,6),
    eps_est_current_year            NUMERIC(18,6),
    eps_est_next_year               NUMERIC(18,6),
    revenue_ttm                     NUMERIC(20,2),
    gross_profit_ttm                NUMERIC(20,2),
    ebitda_ttm                      NUMERIC(20,2),
    profit_margin                   NUMERIC(18,6),              -- decimal: 0.15 = 15%
    operating_margin                NUMERIC(18,6),
    roe_ttm                         NUMERIC(18,6),
    roa_ttm                         NUMERIC(18,6),
    quarterly_earnings_growth_yoy   NUMERIC(18,6),
    quarterly_revenue_growth_yoy    NUMERIC(18,6),
    most_recent_quarter             DATE,
    wall_street_target_price        NUMERIC(12,4),
    book_value_per_share            NUMERIC(12,4),
    revenue_per_share               NUMERIC(12,4),

    -- From Valuation
    trailing_pe                     NUMERIC(12,4),
    forward_pe                      NUMERIC(12,4),
    enterprise_value                NUMERIC(20,2),
    ev_to_revenue                   NUMERIC(12,4),
    ev_to_ebitda                    NUMERIC(12,4),

    -- Metadata
    snapshot_date                   DATE,
    data_source                     VARCHAR(20)     DEFAULT 'eodhd',
    updated_at                      TIMESTAMPTZ     DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_valsnap_pe ON market.valuation_snapshot (pe_ratio);
CREATE INDEX IF NOT EXISTS idx_valsnap_yield ON market.valuation_snapshot (dividend_yield DESC);

-- ─── market.exchange_list ────────────────────────────────────────────────────
-- ASX exchange symbol list from EODHD /exchange-symbol-list/AU

CREATE TABLE IF NOT EXISTS market.exchange_list (
    asx_code        VARCHAR(10)     PRIMARY KEY,
    company_name    TEXT,
    country         VARCHAR(5),
    exchange        VARCHAR(10),
    currency        VARCHAR(5),
    stock_type      VARCHAR(30),                -- 'Common Stock', 'ETF', 'Fund', etc.
    isin            VARCHAR(20),
    snapshot_date   DATE,
    updated_at      TIMESTAMPTZ     DEFAULT NOW()
);

-- ─── financials.earnings_quarterly ───────────────────────────────────────────
-- EPS actuals vs analyst estimates from EODHD Earnings.History
-- Used for earnings surprise analysis and estimate tracking.

CREATE TABLE IF NOT EXISTS financials.earnings_quarterly (
    id                  BIGSERIAL       PRIMARY KEY,
    asx_code            VARCHAR(10)     NOT NULL,
    period_end_date     DATE            NOT NULL,
    eps_actual          NUMERIC(12,6),
    eps_estimate        NUMERIC(12,6),
    eps_difference      NUMERIC(12,6),
    surprise_pct        NUMERIC(8,4),               -- % beat/miss
    beat_miss           VARCHAR(10),                 -- 'beat', 'miss', 'met', NULL
    data_source         VARCHAR(20)     DEFAULT 'eodhd',
    loaded_at           TIMESTAMPTZ     DEFAULT NOW(),
    UNIQUE (asx_code, period_end_date)
);

CREATE INDEX IF NOT EXISTS idx_earn_q_code ON financials.earnings_quarterly (asx_code, period_end_date DESC);

-- ─── screener schema ─────────────────────────────────────────────────────────
-- The Golden Record layer. screener.universe is the single table the
-- screener website queries — one denormalised row per stock, no JOINs.

CREATE SCHEMA IF NOT EXISTS screener;
GRANT USAGE ON SCHEMA screener TO asx_user;

-- screener.universe — full denormalised golden record
-- Rebuilt nightly by build_screener_universe.py.
-- Modelled on market.screener_universe but in the screener schema.

CREATE TABLE IF NOT EXISTS screener.universe (

    -- ── Identity ─────────────────────────────────────────────────
    asx_code                VARCHAR(10)     PRIMARY KEY,
    company_name            TEXT,
    short_name              TEXT,
    sector                  TEXT,
    industry_group          TEXT,
    industry                TEXT,
    sub_industry            TEXT,
    stock_type              VARCHAR(30),
    status                  VARCHAR(20),
    listing_date            DATE,
    fiscal_year_end_month   SMALLINT,
    is_reit                 BOOLEAN,
    is_miner                BOOLEAN,
    is_asx20                BOOLEAN,
    is_asx50                BOOLEAN,
    is_asx100               BOOLEAN,
    is_asx200               BOOLEAN,
    is_asx300               BOOLEAN,
    is_all_ords             BOOLEAN,
    isin                    VARCHAR(20),
    website                 TEXT,
    description             TEXT,

    -- ── Price (latest close) ─────────────────────────────────────
    price                   NUMERIC(12,4),
    price_date              DATE,
    open                    NUMERIC(12,4),
    high_52w                NUMERIC(12,4),
    low_52w                 NUMERIC(12,4),
    volume                  BIGINT,
    avg_volume_20d          BIGINT,
    market_cap              NUMERIC(20,2),

    -- ── Valuation ratios ─────────────────────────────────────────
    pe_ratio                NUMERIC(12,4),
    forward_pe              NUMERIC(12,4),
    peg_ratio               NUMERIC(12,4),
    price_to_book           NUMERIC(12,4),
    price_to_sales          NUMERIC(12,4),
    price_to_cash_flow      NUMERIC(12,4),
    price_to_fcf            NUMERIC(12,4),
    ev                      NUMERIC(20,2),
    ev_to_ebitda            NUMERIC(12,4),
    ev_to_ebit              NUMERIC(12,4),
    ev_to_revenue           NUMERIC(12,4),
    graham_number           NUMERIC(12,4),

    -- ── Dividends & Franking ─────────────────────────────────────
    dps_ttm                 NUMERIC(12,6),
    dividend_yield          NUMERIC(8,6),
    franking_pct            NUMERIC(5,2),
    franking_credit_per_share NUMERIC(12,6),
    grossed_up_yield        NUMERIC(8,6),
    ex_div_date             DATE,
    pay_date                DATE,
    payout_ratio            NUMERIC(8,4),

    -- ── Profitability ────────────────────────────────────────────
    revenue_ttm             NUMERIC(20,2),
    gross_profit_ttm        NUMERIC(20,2),
    ebitda_ttm              NUMERIC(20,2),
    net_profit_ttm          NUMERIC(20,2),
    gross_margin            NUMERIC(8,4),
    ebitda_margin           NUMERIC(8,4),
    net_margin              NUMERIC(8,4),
    operating_margin        NUMERIC(8,4),
    roe                     NUMERIC(8,4),
    roa                     NUMERIC(8,4),
    roce                    NUMERIC(8,4),

    -- ── Income Statement (FY0 = most recent full year) ───────────
    revenue_fy0             NUMERIC(18,2),
    revenue_fy1             NUMERIC(18,2),
    revenue_fy2             NUMERIC(18,2),
    ebitda_fy0              NUMERIC(18,2),
    ebitda_fy1              NUMERIC(18,2),
    net_profit_fy0          NUMERIC(18,2),
    net_profit_fy1          NUMERIC(18,2),
    eps_fy0                 NUMERIC(10,4),
    eps_fy1                 NUMERIC(10,4),
    dps_fy0                 NUMERIC(10,4),
    dps_fy1                 NUMERIC(10,4),

    -- ── Balance Sheet (latest) ───────────────────────────────────
    total_assets            NUMERIC(18,2),
    total_equity            NUMERIC(18,2),
    total_debt              NUMERIC(18,2),
    net_debt                NUMERIC(18,2),
    cash                    NUMERIC(18,2),
    book_value_per_share    NUMERIC(12,4),
    debt_to_equity          NUMERIC(10,4),
    current_ratio           NUMERIC(10,4),

    -- ── Cash Flow (latest FY) ────────────────────────────────────
    cfo_fy0                 NUMERIC(18,2),
    capex_fy0               NUMERIC(18,2),
    fcf_fy0                 NUMERIC(18,2),
    fcf_yield               NUMERIC(8,4),

    -- ── Growth rates ─────────────────────────────────────────────
    revenue_growth_1y       NUMERIC(8,4),
    revenue_growth_3y_cagr  NUMERIC(8,4),
    earnings_growth_1y      NUMERIC(8,4),
    earnings_growth_3y_cagr NUMERIC(8,4),

    -- ── Technical (daily) ────────────────────────────────────────
    rsi_14                  NUMERIC(8,4),
    macd                    NUMERIC(12,4),
    macd_signal             NUMERIC(12,4),
    sma_20                  NUMERIC(12,4),
    sma_50                  NUMERIC(12,4),
    sma_200                 NUMERIC(12,4),
    ema_20                  NUMERIC(12,4),
    bb_upper                NUMERIC(12,4),
    bb_lower                NUMERIC(12,4),
    atr_14                  NUMERIC(12,4),
    adx_14                  NUMERIC(8,4),
    obv                     NUMERIC(20,0),

    -- ── Momentum / Returns ───────────────────────────────────────
    return_1w               NUMERIC(8,4),
    return_1m               NUMERIC(8,4),
    return_3m               NUMERIC(8,4),
    return_6m               NUMERIC(8,4),
    return_1y               NUMERIC(8,4),
    return_3y               NUMERIC(8,4),
    return_ytd              NUMERIC(8,4),
    momentum_3m             NUMERIC(8,4),
    momentum_6m             NUMERIC(8,4),
    momentum_12m            NUMERIC(8,4),
    volatility_20d          NUMERIC(8,4),
    volatility_60d          NUMERIC(8,4),
    sharpe_1y               NUMERIC(8,4),
    drawdown_from_ath       NUMERIC(8,4),

    -- ── Analyst coverage ─────────────────────────────────────────
    analyst_rating          NUMERIC(4,2),
    analyst_target_price    NUMERIC(12,4),
    analyst_upside          NUMERIC(8,4),
    analyst_strong_buy      SMALLINT,
    analyst_buy             SMALLINT,
    analyst_hold            SMALLINT,
    analyst_sell            SMALLINT,
    analyst_strong_sell     SMALLINT,

    -- ── Shares & Ownership ───────────────────────────────────────
    shares_outstanding      BIGINT,
    shares_float            BIGINT,
    percent_insiders        NUMERIC(8,4),
    percent_institutions    NUMERIC(8,4),

    -- ── Short interest (ASIC) ────────────────────────────────────
    short_pct               NUMERIC(8,4),
    short_position_shares   BIGINT,

    -- ── Metadata ─────────────────────────────────────────────────
    universe_built_at       TIMESTAMPTZ     DEFAULT NOW()
);

-- Indexes for the most common screener filter patterns
CREATE INDEX IF NOT EXISTS idx_su_sector      ON screener.universe (sector);
CREATE INDEX IF NOT EXISTS idx_su_mktcap      ON screener.universe (market_cap DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_su_pe          ON screener.universe (pe_ratio);
CREATE INDEX IF NOT EXISTS idx_su_yield       ON screener.universe (dividend_yield DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_su_rsi         ON screener.universe (rsi_14);
CREATE INDEX IF NOT EXISTS idx_su_ret1y       ON screener.universe (return_1y DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_su_roe         ON screener.universe (roe DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_su_status      ON screener.universe (status);
CREATE INDEX IF NOT EXISTS idx_su_asx200      ON screener.universe (is_asx200) WHERE is_asx200 = TRUE;

-- ─── screener.fundamentals — view ────────────────────────────────────────────
CREATE OR REPLACE VIEW screener.fundamentals AS
SELECT
    asx_code, company_name, sector, industry, stock_type, status,
    market_cap, pe_ratio, forward_pe, peg_ratio, price_to_book,
    price_to_sales, price_to_cash_flow, price_to_fcf,
    ev, ev_to_ebitda, ev_to_ebit, ev_to_revenue, graham_number,
    dps_ttm, dividend_yield, franking_pct, grossed_up_yield,
    payout_ratio,
    revenue_ttm, gross_profit_ttm, ebitda_ttm, net_profit_ttm,
    gross_margin, ebitda_margin, net_margin, operating_margin,
    roe, roa, roce,
    revenue_fy0, revenue_fy1, revenue_fy2,
    ebitda_fy0, ebitda_fy1,
    net_profit_fy0, net_profit_fy1,
    eps_fy0, eps_fy1, dps_fy0, dps_fy1,
    total_assets, total_equity, total_debt, net_debt, cash,
    book_value_per_share, debt_to_equity, current_ratio,
    cfo_fy0, capex_fy0, fcf_fy0, fcf_yield,
    revenue_growth_1y, revenue_growth_3y_cagr,
    earnings_growth_1y, earnings_growth_3y_cagr,
    analyst_rating, analyst_target_price, analyst_upside,
    shares_outstanding, percent_insiders, percent_institutions
FROM screener.universe;

-- ─── screener.technicals — view ──────────────────────────────────────────────
CREATE OR REPLACE VIEW screener.technicals AS
SELECT
    asx_code, company_name, sector, market_cap,
    price, price_date, open, high_52w, low_52w, volume, avg_volume_20d,
    rsi_14, macd, macd_signal, sma_20, sma_50, sma_200, ema_20,
    bb_upper, bb_lower, atr_14, adx_14, obv,
    return_1w, return_1m, return_3m, return_6m, return_1y, return_ytd,
    momentum_3m, momentum_6m, momentum_12m,
    volatility_20d, volatility_60d, sharpe_1y, drawdown_from_ath,
    short_pct
FROM screener.universe;

-- ─── Grant permissions ────────────────────────────────────────────────────────
GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON screener.universe TO asx_user;
GRANT SELECT ON screener.fundamentals TO asx_user;
GRANT SELECT ON screener.technicals TO asx_user;
GRANT SELECT, INSERT, UPDATE ON market.valuation_snapshot TO asx_user;
GRANT SELECT, INSERT, UPDATE ON market.exchange_list TO asx_user;
GRANT SELECT, INSERT, UPDATE ON financials.earnings_quarterly TO asx_user;
GRANT USAGE, SELECT ON SEQUENCE financials.earnings_quarterly_id_seq TO asx_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA screener
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO asx_user;
