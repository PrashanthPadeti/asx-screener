-- Migration 023: Composite factor scores on screener.universe
-- ============================================================
-- Adds 6 SMALLINT score columns (0–100 each) computed by
-- compute/engine/composite_score.py after each universe rebuild.
--
-- Scores are percentile ranks within the active ASX universe:
--   value_score     — low PE/PB/EV·EBITDA, high FCF yield
--   quality_score   — high Piotroski, ROE, ROCE, low D/E
--   growth_score    — revenue/EPS growth, HoH acceleration
--   momentum_score  — price returns (1M, 3M, 6M), trend strength
--   income_score    — grossed-up yield, franking, consecutive years
--   composite_score — equal-weight average of the 5 factors
-- ============================================================

ALTER TABLE screener.universe
    ADD COLUMN IF NOT EXISTS value_score      SMALLINT CHECK (value_score BETWEEN 0 AND 100),
    ADD COLUMN IF NOT EXISTS quality_score    SMALLINT CHECK (quality_score BETWEEN 0 AND 100),
    ADD COLUMN IF NOT EXISTS growth_score     SMALLINT CHECK (growth_score BETWEEN 0 AND 100),
    ADD COLUMN IF NOT EXISTS momentum_score   SMALLINT CHECK (momentum_score BETWEEN 0 AND 100),
    ADD COLUMN IF NOT EXISTS income_score     SMALLINT CHECK (income_score BETWEEN 0 AND 100),
    ADD COLUMN IF NOT EXISTS composite_score  SMALLINT CHECK (composite_score BETWEEN 0 AND 100);

CREATE INDEX IF NOT EXISTS idx_universe_composite_score
    ON screener.universe (composite_score DESC NULLS LAST);

COMMENT ON COLUMN screener.universe.value_score     IS 'Percentile rank 0-100: value factor (low PE/PB, high FCF yield)';
COMMENT ON COLUMN screener.universe.quality_score   IS 'Percentile rank 0-100: quality factor (Piotroski, ROE, ROCE)';
COMMENT ON COLUMN screener.universe.growth_score    IS 'Percentile rank 0-100: growth factor (revenue/EPS growth)';
COMMENT ON COLUMN screener.universe.momentum_score  IS 'Percentile rank 0-100: momentum factor (1M/3M/6M returns)';
COMMENT ON COLUMN screener.universe.income_score    IS 'Percentile rank 0-100: income factor (grossed-up yield, franking)';
COMMENT ON COLUMN screener.universe.composite_score IS 'Composite score 0-100: equal-weight avg of 5 factor scores';
