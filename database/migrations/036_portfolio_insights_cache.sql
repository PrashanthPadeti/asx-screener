-- Migration 036: Portfolio AI Insights cache
-- Stores Claude-generated insights per portfolio with holdings fingerprint
-- for cache invalidation when positions change significantly.

CREATE TABLE IF NOT EXISTS users.portfolio_insights (
    id              SERIAL PRIMARY KEY,
    portfolio_id    UUID        NOT NULL REFERENCES users.portfolios(id) ON DELETE CASCADE,
    user_id         UUID        NOT NULL,
    -- Fingerprint of holdings at generation time (sorted code+qty+avg_cost hash)
    holdings_hash   TEXT        NOT NULL,
    -- Snapshot metrics used to rebuild the response without re-calling Claude
    total_value     NUMERIC(14,2),
    total_cost      NUMERIC(14,2),
    total_return_pct NUMERIC(8,2),
    annual_income   NUMERIC(14,2),
    portfolio_yield NUMERIC(8,2),
    top3_concentration NUMERIC(6,2),
    num_holdings    INT,
    sector_allocation_json JSONB,
    holdings_json   JSONB,
    -- The insights blob returned by Claude
    insights_json   JSONB        NOT NULL,
    -- Cache lifecycle
    generated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMPTZ NOT NULL DEFAULT NOW() + INTERVAL '7 days',
    UNIQUE (portfolio_id)
);

CREATE INDEX IF NOT EXISTS idx_portfolio_insights_portfolio
    ON users.portfolio_insights (portfolio_id);

CREATE INDEX IF NOT EXISTS idx_portfolio_insights_user
    ON users.portfolio_insights (user_id);

COMMENT ON TABLE users.portfolio_insights IS
    'Cached AI-generated portfolio insights. Cache is valid while holdings_hash matches and expires_at is in the future.';
