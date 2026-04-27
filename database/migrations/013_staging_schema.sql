-- Migration 013: Staging Layer Schema
-- =====================================
-- Creates the staging.* schema — a faithful DB representation of raw EODHD files.
-- Rules: append-only, no transforms, column names match EODHD fields (snake_case only),
--        every row tracks source_file, loaded_at, is_latest, is_archived.

CREATE SCHEMA IF NOT EXISTS staging;

-- ─── staging.eod_prices ───────────────────────────────────────────────────────
-- Source: /eod/{ticker}.AU (historical) and /eod/bulk-download/AU (incremental)

CREATE TABLE IF NOT EXISTS staging.eod_prices (
    id              BIGSERIAL PRIMARY KEY,
    asx_code        VARCHAR(10)    NOT NULL,
    date            DATE           NOT NULL,
    open            NUMERIC(12,4),
    high            NUMERIC(12,4),
    low             NUMERIC(12,4),
    close           NUMERIC(12,4),
    adjusted_close  NUMERIC(12,4),
    volume          BIGINT,
    source_file     TEXT           NOT NULL,
    loaded_at       TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    is_latest       BOOLEAN        NOT NULL DEFAULT TRUE,
    is_archived     BOOLEAN        NOT NULL DEFAULT FALSE,
    UNIQUE (asx_code, date, source_file)
);

CREATE INDEX IF NOT EXISTS idx_staging_eod_prices_code_date
    ON staging.eod_prices (asx_code, date DESC);
CREATE INDEX IF NOT EXISTS idx_staging_eod_prices_latest
    ON staging.eod_prices (asx_code, is_latest) WHERE is_latest = TRUE;

-- ─── staging.fundamentals ─────────────────────────────────────────────────────
-- Source: /fundamentals/{ticker}.AU — full JSON blob + indexed key fields

CREATE TABLE IF NOT EXISTS staging.fundamentals (
    id                  BIGSERIAL PRIMARY KEY,
    asx_code            VARCHAR(10)    NOT NULL,
    snapshot_date       DATE           NOT NULL,
    raw_json            JSONB          NOT NULL,
    general_code        VARCHAR(10),
    general_name        TEXT,
    general_sector      TEXT,
    general_industry    TEXT,
    updated_at_eodhd    DATE,
    source_file         TEXT           NOT NULL,
    loaded_at           TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    checksum            VARCHAR(64),
    is_latest           BOOLEAN        NOT NULL DEFAULT TRUE,
    is_archived         BOOLEAN        NOT NULL DEFAULT FALSE,
    UNIQUE (asx_code, snapshot_date, source_file)
);

CREATE INDEX IF NOT EXISTS idx_staging_fundamentals_code
    ON staging.fundamentals (asx_code, snapshot_date DESC);
CREATE INDEX IF NOT EXISTS idx_staging_fundamentals_latest
    ON staging.fundamentals (asx_code, is_latest) WHERE is_latest = TRUE;
CREATE INDEX IF NOT EXISTS idx_staging_fundamentals_checksum
    ON staging.fundamentals (checksum);

-- ─── staging.income_statement ─────────────────────────────────────────────────
-- Source: staging.fundamentals.raw_json → Financials.Income_Statement

CREATE TABLE IF NOT EXISTS staging.income_statement (
    id                          BIGSERIAL PRIMARY KEY,
    asx_code                    VARCHAR(10)    NOT NULL,
    date                        DATE           NOT NULL,
    period_type                 VARCHAR(10)    NOT NULL,   -- 'yearly' or 'quarterly'
    total_revenue               NUMERIC(20,4),
    cost_of_revenue             NUMERIC(20,4),
    gross_profit                NUMERIC(20,4),
    total_operating_expenses    NUMERIC(20,4),
    operating_income            NUMERIC(20,4),
    ebitda                      NUMERIC(20,4),
    interest_expense            NUMERIC(20,4),
    income_before_tax           NUMERIC(20,4),
    income_tax_expense          NUMERIC(20,4),
    net_income                  NUMERIC(20,4),
    eps                         NUMERIC(12,6),
    eps_diluted                 NUMERIC(12,6),
    depreciation_amortization   NUMERIC(20,4),
    source_fundamentals_id      BIGINT         REFERENCES staging.fundamentals(id),
    loaded_at                   TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    is_latest                   BOOLEAN        NOT NULL DEFAULT TRUE,
    UNIQUE (asx_code, date, period_type)
);

CREATE INDEX IF NOT EXISTS idx_staging_is_code_date
    ON staging.income_statement (asx_code, date DESC, period_type);

-- ─── staging.balance_sheet ────────────────────────────────────────────────────
-- Source: staging.fundamentals.raw_json → Financials.Balance_Sheet

CREATE TABLE IF NOT EXISTS staging.balance_sheet (
    id                              BIGSERIAL PRIMARY KEY,
    asx_code                        VARCHAR(10)    NOT NULL,
    date                            DATE           NOT NULL,
    period_type                     VARCHAR(10)    NOT NULL,
    total_assets                    NUMERIC(20,4),
    total_current_assets            NUMERIC(20,4),
    cash_and_short_term_investments NUMERIC(20,4),
    net_receivables                 NUMERIC(20,4),
    inventory                       NUMERIC(20,4),
    total_non_current_assets        NUMERIC(20,4),
    property_plant_equipment_net    NUMERIC(20,4),
    goodwill                        NUMERIC(20,4),
    intangible_assets               NUMERIC(20,4),
    total_liabilities               NUMERIC(20,4),
    total_current_liabilities       NUMERIC(20,4),
    short_long_term_debt_total      NUMERIC(20,4),
    long_term_debt                  NUMERIC(20,4),
    total_stockholder_equity        NUMERIC(20,4),
    retained_earnings               NUMERIC(20,4),
    common_stock                    NUMERIC(20,4),
    source_fundamentals_id          BIGINT         REFERENCES staging.fundamentals(id),
    loaded_at                       TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    is_latest                       BOOLEAN        NOT NULL DEFAULT TRUE,
    UNIQUE (asx_code, date, period_type)
);

CREATE INDEX IF NOT EXISTS idx_staging_bs_code_date
    ON staging.balance_sheet (asx_code, date DESC, period_type);

-- ─── staging.cash_flow ────────────────────────────────────────────────────────
-- Source: staging.fundamentals.raw_json → Financials.Cash_Flow

CREATE TABLE IF NOT EXISTS staging.cash_flow (
    id                                      BIGSERIAL PRIMARY KEY,
    asx_code                                VARCHAR(10)    NOT NULL,
    date                                    DATE           NOT NULL,
    period_type                             VARCHAR(10)    NOT NULL,
    total_cash_from_operating_activities    NUMERIC(20,4),
    capital_expenditures                    NUMERIC(20,4),
    total_cash_from_investing_activities    NUMERIC(20,4),
    total_cash_from_financing_activities    NUMERIC(20,4),
    dividends_paid                          NUMERIC(20,4),
    change_to_cash                          NUMERIC(20,4),
    free_cash_flow                          NUMERIC(20,4),
    source_fundamentals_id                  BIGINT         REFERENCES staging.fundamentals(id),
    loaded_at                               TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    is_latest                               BOOLEAN        NOT NULL DEFAULT TRUE,
    UNIQUE (asx_code, date, period_type)
);

CREATE INDEX IF NOT EXISTS idx_staging_cf_code_date
    ON staging.cash_flow (asx_code, date DESC, period_type);

-- ─── staging.earnings ─────────────────────────────────────────────────────────
-- Source: staging.fundamentals.raw_json → Earnings.History + Earnings.Trend

CREATE TABLE IF NOT EXISTS staging.earnings (
    id                      BIGSERIAL PRIMARY KEY,
    asx_code                VARCHAR(10)    NOT NULL,
    date                    DATE           NOT NULL,
    period_type             VARCHAR(10)    NOT NULL,   -- 'actual' or 'estimate'
    eps_actual              NUMERIC(12,6),
    eps_estimate            NUMERIC(12,6),
    eps_difference          NUMERIC(12,6),
    surprise_percent        NUMERIC(8,4),
    source_fundamentals_id  BIGINT         REFERENCES staging.fundamentals(id),
    loaded_at               TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    UNIQUE (asx_code, date, period_type)
);

-- ─── staging.dividends ────────────────────────────────────────────────────────
-- Source: /div/{ticker}.AU

CREATE TABLE IF NOT EXISTS staging.dividends (
    id              BIGSERIAL PRIMARY KEY,
    asx_code        VARCHAR(10)    NOT NULL,
    date            DATE           NOT NULL,   -- ex-dividend date
    dividend        NUMERIC(12,6),             -- adjusted amount
    unadjusted_value NUMERIC(12,6),
    currency        VARCHAR(5),
    source_file     TEXT           NOT NULL,
    loaded_at       TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    is_latest       BOOLEAN        NOT NULL DEFAULT TRUE,
    UNIQUE (asx_code, date, source_file)
);

CREATE INDEX IF NOT EXISTS idx_staging_dividends_code
    ON staging.dividends (asx_code, date DESC);

-- ─── staging.splits ───────────────────────────────────────────────────────────
-- Source: /splits/{ticker}.AU

CREATE TABLE IF NOT EXISTS staging.splits (
    id          BIGSERIAL PRIMARY KEY,
    asx_code    VARCHAR(10)    NOT NULL,
    date        DATE           NOT NULL,
    split       VARCHAR(20),                   -- e.g. '2:1'
    source_file TEXT           NOT NULL,
    loaded_at   TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    UNIQUE (asx_code, date, source_file)
);

-- ─── staging.exchange_symbols ─────────────────────────────────────────────────
-- Source: /exchange-symbol-list/AU

CREATE TABLE IF NOT EXISTS staging.exchange_symbols (
    id              BIGSERIAL PRIMARY KEY,
    code            VARCHAR(10)    NOT NULL,
    name            TEXT,
    country         VARCHAR(5),
    exchange        VARCHAR(10),
    currency        VARCHAR(5),
    type            VARCHAR(30),               -- 'Common Stock', 'ETF', etc.
    isin            VARCHAR(20),
    snapshot_date   DATE           NOT NULL,
    source_file     TEXT           NOT NULL,
    loaded_at       TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    is_latest       BOOLEAN        NOT NULL DEFAULT TRUE,
    UNIQUE (code, snapshot_date, source_file)
);

-- ─── staging.company_profile ──────────────────────────────────────────────────
-- Source: staging.fundamentals.raw_json → General

CREATE TABLE IF NOT EXISTS staging.company_profile (
    id                      BIGSERIAL PRIMARY KEY,
    asx_code                VARCHAR(10)    NOT NULL,
    snapshot_date           DATE           NOT NULL,
    code                    VARCHAR(10),
    type                    VARCHAR(30),
    name                    TEXT,
    exchange                VARCHAR(10),
    currency_code           VARCHAR(5),
    country_name            TEXT,
    isin                    VARCHAR(20),
    cusip                   VARCHAR(20),
    cik                     VARCHAR(20),
    employer_id_number      VARCHAR(20),
    fiscal_year_end         VARCHAR(20),   -- e.g. 'June'
    ipo_date                DATE,
    sector                  TEXT,
    industry                TEXT,
    gic_sector              TEXT,
    gic_group               TEXT,
    gic_industry            TEXT,
    gic_sub_industry        TEXT,
    description             TEXT,
    address                 TEXT,
    phone                   TEXT,
    web_url                 TEXT,
    full_time_employees     INTEGER,
    updated_at              DATE,
    source_fundamentals_id  BIGINT         REFERENCES staging.fundamentals(id),
    loaded_at               TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    is_latest               BOOLEAN        NOT NULL DEFAULT TRUE,
    UNIQUE (asx_code, snapshot_date)
);

-- ─── staging.highlights ───────────────────────────────────────────────────────
-- Source: staging.fundamentals.raw_json → Highlights

CREATE TABLE IF NOT EXISTS staging.highlights (
    id                              BIGSERIAL PRIMARY KEY,
    asx_code                        VARCHAR(10)    NOT NULL,
    snapshot_date                   DATE           NOT NULL,
    market_capitalization           NUMERIC(20,4),
    ebitda                          NUMERIC(20,4),
    pe_ratio                        NUMERIC(12,4),
    peg_ratio                       NUMERIC(12,4),
    wall_street_target_price        NUMERIC(12,4),
    book_value                      NUMERIC(12,4),
    dividend_share                  NUMERIC(12,6),
    dividend_yield                  NUMERIC(8,6),
    earnings_share                  NUMERIC(12,6),
    eps_estimate_current_year       NUMERIC(12,6),
    eps_estimate_next_year          NUMERIC(12,6),
    eps_estimate_next_quarter       NUMERIC(12,6),
    revenue_per_share_ttm           NUMERIC(12,4),
    profit_margin                   NUMERIC(8,6),
    operating_margin_ttm            NUMERIC(8,6),
    return_on_assets_ttm            NUMERIC(8,6),
    return_on_equity_ttm            NUMERIC(8,6),
    revenue_ttm                     NUMERIC(20,4),
    gross_profit_ttm                NUMERIC(20,4),
    diluted_eps_ttm                 NUMERIC(12,6),
    quarterly_earnings_growth_yoy   NUMERIC(8,6),
    quarterly_revenue_growth_yoy    NUMERIC(8,6),
    most_recent_quarter             DATE,
    source_fundamentals_id          BIGINT         REFERENCES staging.fundamentals(id),
    loaded_at                       TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    is_latest                       BOOLEAN        NOT NULL DEFAULT TRUE,
    UNIQUE (asx_code, snapshot_date)
);

-- ─── staging.valuation ────────────────────────────────────────────────────────
-- Source: staging.fundamentals.raw_json → Valuation

CREATE TABLE IF NOT EXISTS staging.valuation (
    id                          BIGSERIAL PRIMARY KEY,
    asx_code                    VARCHAR(10)    NOT NULL,
    snapshot_date               DATE           NOT NULL,
    trailing_pe                 NUMERIC(12,4),
    forward_pe                  NUMERIC(12,4),
    price_sales_ttm             NUMERIC(12,4),
    price_book_mrq              NUMERIC(12,4),
    enterprise_value            NUMERIC(20,4),
    enterprise_value_revenue    NUMERIC(12,4),
    enterprise_value_ebitda     NUMERIC(12,4),
    source_fundamentals_id      BIGINT         REFERENCES staging.fundamentals(id),
    loaded_at                   TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    is_latest                   BOOLEAN        NOT NULL DEFAULT TRUE,
    UNIQUE (asx_code, snapshot_date)
);

-- ─── staging.analyst_ratings ──────────────────────────────────────────────────
-- Source: staging.fundamentals.raw_json → AnalystRatings

CREATE TABLE IF NOT EXISTS staging.analyst_ratings (
    id                      BIGSERIAL PRIMARY KEY,
    asx_code                VARCHAR(10)    NOT NULL,
    snapshot_date           DATE           NOT NULL,
    rating                  NUMERIC(4,2),
    target_price            NUMERIC(12,4),
    strong_buy              INTEGER,
    buy                     INTEGER,
    hold                    INTEGER,
    sell                    INTEGER,
    strong_sell             INTEGER,
    source_fundamentals_id  BIGINT         REFERENCES staging.fundamentals(id),
    loaded_at               TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    is_latest               BOOLEAN        NOT NULL DEFAULT TRUE,
    UNIQUE (asx_code, snapshot_date)
);

-- ─── staging.shares_stats ─────────────────────────────────────────────────────
-- Source: staging.fundamentals.raw_json → SharesStats

CREATE TABLE IF NOT EXISTS staging.shares_stats (
    id                          BIGSERIAL PRIMARY KEY,
    asx_code                    VARCHAR(10)    NOT NULL,
    snapshot_date               DATE           NOT NULL,
    shares_outstanding          NUMERIC(20,4),
    shares_float                NUMERIC(20,4),
    percent_insiders            NUMERIC(8,4),
    percent_institutions        NUMERIC(8,4),
    shares_short                NUMERIC(20,4),
    short_ratio                 NUMERIC(8,4),
    short_percent_outstanding   NUMERIC(8,4),
    short_percent_float         NUMERIC(8,4),
    source_fundamentals_id      BIGINT         REFERENCES staging.fundamentals(id),
    loaded_at                   TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    is_latest                   BOOLEAN        NOT NULL DEFAULT TRUE,
    UNIQUE (asx_code, snapshot_date)
);

-- ─── Grant permissions ────────────────────────────────────────────────────────
GRANT USAGE  ON SCHEMA staging TO asx_user;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA staging TO asx_user;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA staging TO asx_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA staging
    GRANT SELECT, INSERT, UPDATE ON TABLES TO asx_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA staging
    GRANT USAGE, SELECT ON SEQUENCES TO asx_user;
