-- Migration 032: ASX Indices and ETF/Managed Funds tables
-- Separate raw data tables for index constituents, ETFs and managed funds.
-- Intraday index prices stored in market.index_prices; fund info in market.funds.

-- ── ASX Indices metadata ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS market.indices (
    index_code          VARCHAR(20)  PRIMARY KEY,   -- e.g. 'ASX200', 'ASX50', 'ASX300'
    display_name        VARCHAR(100) NOT NULL,       -- e.g. 'S&P/ASX 200'
    description         TEXT,
    constituent_count   INT,
    rebalance_freq      VARCHAR(20),                 -- 'quarterly', 'monthly'
    is_active           BOOLEAN      DEFAULT TRUE,
    created_at          TIMESTAMPTZ  DEFAULT NOW(),
    updated_at          TIMESTAMPTZ  DEFAULT NOW()
);

-- ── Index daily prices / performance ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS market.index_prices (
    index_code          VARCHAR(20)  NOT NULL REFERENCES market.indices(index_code),
    price_date          DATE         NOT NULL,
    close_price         NUMERIC(12,2),
    open_price          NUMERIC(12,2),
    high_price          NUMERIC(12,2),
    low_price           NUMERIC(12,2),
    volume              BIGINT,
    return_1d           NUMERIC(8,4),
    return_1w           NUMERIC(8,4),
    return_1m           NUMERIC(8,4),
    return_3m           NUMERIC(8,4),
    return_6m           NUMERIC(8,4),
    return_1y           NUMERIC(8,4),
    return_ytd          NUMERIC(8,4),
    high_52w            NUMERIC(12,2),
    low_52w             NUMERIC(12,2),
    created_at          TIMESTAMPTZ  DEFAULT NOW(),
    PRIMARY KEY (index_code, price_date)
);

-- ── ETF & Managed Funds ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS market.funds (
    asx_code            VARCHAR(10)  PRIMARY KEY,
    fund_name           VARCHAR(200) NOT NULL,
    fund_type           VARCHAR(20)  NOT NULL,   -- 'ETF' | 'LIC' | 'MANAGED'
    asset_class         VARCHAR(50),             -- 'Australian Equities', 'Global Equities', 'Fixed Income', 'Property', 'Commodities', 'Multi-Asset'
    index_tracked       VARCHAR(100),            -- for passive ETFs
    fund_manager        VARCHAR(100),
    mer_pct             NUMERIC(6,4),            -- Management Expense Ratio %
    funds_under_mgmt_bn NUMERIC(14,2),           -- AUM in billions AUD
    inception_date      DATE,
    distribution_freq   VARCHAR(20),             -- 'quarterly', 'monthly', 'semi-annual', 'annual'
    is_hedged           BOOLEAN      DEFAULT FALSE,
    is_active           BOOLEAN      DEFAULT TRUE,
    asx_url             TEXT,
    created_at          TIMESTAMPTZ  DEFAULT NOW(),
    updated_at          TIMESTAMPTZ  DEFAULT NOW()
);

-- ── Fund daily prices / performance ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS market.fund_prices (
    asx_code            VARCHAR(10)  NOT NULL REFERENCES market.funds(asx_code),
    price_date          DATE         NOT NULL,
    close_price         NUMERIC(12,4),
    open_price          NUMERIC(12,4),
    high_price          NUMERIC(12,4),
    low_price           NUMERIC(12,4),
    volume              BIGINT,
    nav                 NUMERIC(12,4),           -- Net Asset Value (for LICs)
    nav_discount_pct    NUMERIC(6,2),            -- (price/NAV - 1) * 100
    distribution_yield  NUMERIC(8,4),            -- trailing 12M distributions / price
    return_1d           NUMERIC(8,4),
    return_1w           NUMERIC(8,4),
    return_1m           NUMERIC(8,4),
    return_3m           NUMERIC(8,4),
    return_6m           NUMERIC(8,4),
    return_1y           NUMERIC(8,4),
    return_3y_pa        NUMERIC(8,4),            -- 3-year p.a. return
    return_5y_pa        NUMERIC(8,4),            -- 5-year p.a. return
    return_ytd          NUMERIC(8,4),
    high_52w            NUMERIC(12,4),
    low_52w             NUMERIC(12,4),
    created_at          TIMESTAMPTZ  DEFAULT NOW(),
    PRIMARY KEY (asx_code, price_date)
);

-- ── Indexes ───────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_index_prices_date   ON market.index_prices (price_date DESC);
CREATE INDEX IF NOT EXISTS idx_index_prices_code   ON market.index_prices (index_code);
CREATE INDEX IF NOT EXISTS idx_fund_prices_date    ON market.fund_prices  (price_date DESC);
CREATE INDEX IF NOT EXISTS idx_fund_prices_code    ON market.fund_prices  (asx_code);
CREATE INDEX IF NOT EXISTS idx_funds_type          ON market.funds        (fund_type);
CREATE INDEX IF NOT EXISTS idx_funds_asset_class   ON market.funds        (asset_class);

-- ── Seed index metadata ───────────────────────────────────────────────────────
INSERT INTO market.indices (index_code, display_name, description, rebalance_freq) VALUES
    ('ASX20',  'S&P/ASX 20',   'Top 20 companies by float-adjusted market cap',          'quarterly'),
    ('ASX50',  'S&P/ASX 50',   'Top 50 companies by float-adjusted market cap',          'quarterly'),
    ('ASX100', 'S&P/ASX 100',  'Top 100 companies by float-adjusted market cap',         'quarterly'),
    ('ASX200', 'S&P/ASX 200',  'Top 200 companies by float-adjusted market cap',         'quarterly'),
    ('ASX300', 'S&P/ASX 300',  'Top 300 companies by float-adjusted market cap',         'quarterly'),
    ('AXJO',   'All Ordinaries','Broadest ASX measure covering ~500 largest companies',   'quarterly'),
    ('AXFJ',   'ASX Financials','GICS Financials sector index',                           'quarterly'),
    ('AXMJ',   'ASX Materials', 'GICS Materials sector index',                            'quarterly'),
    ('AXEJ',   'ASX Energy',    'GICS Energy sector index',                               'quarterly'),
    ('AXHJ',   'ASX Health Care','GICS Health Care sector index',                         'quarterly')
ON CONFLICT (index_code) DO NOTHING;
