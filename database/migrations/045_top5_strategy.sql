-- ============================================================
-- Migration 045 — ASX Top 5 Strategy
-- Monthly algo-ranked top 5 picks from ASX200
-- ============================================================

CREATE SCHEMA IF NOT EXISTS strategy;

-- Monthly picks table
CREATE TABLE IF NOT EXISTS strategy.monthly_picks (
    id              SERIAL          PRIMARY KEY,
    pick_month      DATE            NOT NULL,   -- always 1st of month, e.g. 2026-05-01
    rank            SMALLINT        NOT NULL CHECK (rank BETWEEN 1 AND 10),
    asx_code        VARCHAR(10)     NOT NULL,
    company_name    VARCHAR(200),
    sector          VARCHAR(100),
    industry        VARCHAR(200),

    -- Composite + component scores (0–100 percentile rank within ASX200)
    composite_score NUMERIC(6,2),
    momentum_score  NUMERIC(6,2),
    quality_score   NUMERIC(6,2),
    value_score     NUMERIC(6,2),
    income_score    NUMERIC(6,2),
    growth_score    NUMERIC(6,2),

    -- Snapshot metrics at time of pick
    price           NUMERIC(12,4),
    market_cap      NUMERIC(18,2),
    pe_ratio        NUMERIC(10,2),
    dividend_yield  NUMERIC(8,4),
    grossed_up_yield NUMERIC(8,4),
    franking_pct    NUMERIC(6,2),
    return_3m       NUMERIC(8,4),
    return_1y       NUMERIC(8,4),
    roe             NUMERIC(8,4),
    piotroski_f_score SMALLINT,

    computed_at     TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    UNIQUE (pick_month, rank)
);

CREATE INDEX IF NOT EXISTS idx_monthly_picks_month   ON strategy.monthly_picks (pick_month DESC);
CREATE INDEX IF NOT EXISTS idx_monthly_picks_code    ON strategy.monthly_picks (asx_code);
CREATE INDEX IF NOT EXISTS idx_monthly_picks_month_code ON strategy.monthly_picks (pick_month, asx_code);

-- Convenience view: current month only
CREATE OR REPLACE VIEW strategy.current_picks AS
SELECT *
FROM strategy.monthly_picks
WHERE pick_month = DATE_TRUNC('month', CURRENT_DATE)::DATE
ORDER BY rank;

-- Convenience view: latest 12 months, grouped
CREATE OR REPLACE VIEW strategy.recent_picks AS
SELECT *
FROM strategy.monthly_picks
WHERE pick_month >= (DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '11 months')::DATE
ORDER BY pick_month DESC, rank;

COMMENT ON TABLE strategy.monthly_picks IS
  'Monthly top-5 picks from ASX200 ranked by composite factor score (value+quality+growth+momentum+income).';
