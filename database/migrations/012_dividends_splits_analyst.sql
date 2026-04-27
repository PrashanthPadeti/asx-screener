-- Migration 012: Raw zone support tables
-- Adds market.dividends, market.splits, market.analyst_ratings
-- These are populated by scripts/eodhd/load_fundamentals.py

-- ── market.dividends ─────────────────────────────────────────────────────────
-- Full dividend history loaded from EODHD SplitsDividends.Dividends
CREATE TABLE IF NOT EXISTS market.dividends (
    asx_code        VARCHAR(10)  NOT NULL,
    ex_date         DATE         NOT NULL,
    payment_date    DATE,
    record_date     DATE,
    declared_date   DATE,
    amount          NUMERIC(10,6),
    unadjusted_value NUMERIC(10,6),
    currency        VARCHAR(3)   DEFAULT 'AUD',
    div_type        VARCHAR(50),          -- 'Cash Dividend', 'Special Cash Dividend', etc.
    franking_pct    NUMERIC(5,2),         -- franking % if provided
    data_source     VARCHAR(20)  DEFAULT 'eodhd',
    loaded_at       TIMESTAMPTZ  DEFAULT NOW(),
    PRIMARY KEY (asx_code, ex_date)
);

CREATE INDEX idx_div_code    ON market.dividends (asx_code, ex_date DESC);
CREATE INDEX idx_div_exdate  ON market.dividends (ex_date DESC);


-- ── market.splits ─────────────────────────────────────────────────────────────
-- Stock split / reverse split history
CREATE TABLE IF NOT EXISTS market.splits (
    asx_code        VARCHAR(10)  NOT NULL,
    split_date      DATE         NOT NULL,
    ratio           NUMERIC(12,6),        -- e.g. 2.0 = 2-for-1 split, 0.5 = reverse
    data_source     VARCHAR(20)  DEFAULT 'eodhd',
    loaded_at       TIMESTAMPTZ  DEFAULT NOW(),
    PRIMARY KEY (asx_code, split_date)
);

CREATE INDEX idx_splits_code ON market.splits (asx_code, split_date DESC);


-- ── market.analyst_ratings ───────────────────────────────────────────────────
-- Latest analyst consensus per stock (snapshot, overwritten each refresh)
CREATE TABLE IF NOT EXISTS market.analyst_ratings (
    asx_code        VARCHAR(10)  NOT NULL PRIMARY KEY,
    rating          NUMERIC(4,2),         -- consensus 1=Strong Buy … 5=Strong Sell
    target_price    NUMERIC(12,4),
    strong_buy      SMALLINT,
    buy             SMALLINT,
    hold            SMALLINT,
    sell            SMALLINT,
    strong_sell     SMALLINT,
    data_source     VARCHAR(20)  DEFAULT 'eodhd',
    updated_at      TIMESTAMPTZ  DEFAULT NOW()
);


-- ── Add percent_insiders / percent_institutions to market.companies ──────────
ALTER TABLE market.companies
    ADD COLUMN IF NOT EXISTS percent_insiders      NUMERIC(6,2),
    ADD COLUMN IF NOT EXISTS percent_institutions  NUMERIC(6,2),
    ADD COLUMN IF NOT EXISTS cusip                 VARCHAR(20),
    ADD COLUMN IF NOT EXISTS fiscal_year_end_month SMALLINT;    -- 6 for June, 12 for Dec
