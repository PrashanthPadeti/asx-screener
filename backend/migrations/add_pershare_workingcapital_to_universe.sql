-- Add per-share and working-capital columns to screener.universe.
-- These were advertised in ALLOWED_FIELDS but never populated by the build.
-- build_screener_universe.py now computes them; this migration adds the columns
-- so the INSERT can write them. Run once before the next universe rebuild.
--
--   ocf_per_share      = cfo (AUD m) * 1e6 / shares_outstanding   → AUD per share
--   fcf_per_share      = fcf (AUD m) * 1e6 / shares_outstanding   → AUD per share
--   revenue_per_share  = revenue_ttm (raw AUD) / shares_outstanding → AUD per share
--   working_capital    = total_current_assets - total_current_liab → AUD millions
--   price_to_52w_low   = price / low_52w                          → ratio (1.0 = at low)

ALTER TABLE screener.universe
    ADD COLUMN IF NOT EXISTS ocf_per_share     DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS fcf_per_share     DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS revenue_per_share DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS working_capital   DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS price_to_52w_low  DOUBLE PRECISION;
