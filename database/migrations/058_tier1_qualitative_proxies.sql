-- Migration 058: Add Tier-1 qualitative proxy metrics
-- gross_margin_stability:       std dev of gross margin over 5Y (lower = more stable moat/pricing power)
-- revenue_predictability:       coefficient of variation of revenue growth over 5Y (lower = more predictable)
-- revenue_above_sector_median:  true when revenue CAGR 3Y exceeds sector median (market share proxy)

-- market.yearly_metrics — source for first two
ALTER TABLE market.yearly_metrics
    ADD COLUMN IF NOT EXISTS gross_margin_stability  DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS revenue_predictability  DOUBLE PRECISION;

-- screener.universe — all three
ALTER TABLE screener.universe
    ADD COLUMN IF NOT EXISTS gross_margin_stability       DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS revenue_predictability       DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS revenue_above_sector_median  BOOLEAN;
