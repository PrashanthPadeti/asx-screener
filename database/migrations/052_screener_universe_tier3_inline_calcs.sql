-- Migration 052: Add Tier 3 inline calculation columns to screener.universe
-- All computed inline from existing laterals — no new data sources needed.
--
-- price_to_52w_high  : price / 52w high  (1.0 = at high; 0.9 = 10% below)
-- price_to_52w_low   : price / 52w low   (1.0 = at low;  1.5 = 50% above)
-- fcf_per_share      : AUD per share (fcf_fy0 AUD M * 1e6 / shares)
-- ocf_per_share      : AUD per share (cfo_fy0 AUD M * 1e6 / shares)
-- revenue_per_share  : AUD per share (revenue_fy0 AUD M * 1e6 / shares)
-- working_capital    : AUD millions  (total_current_assets - total_current_liab)

ALTER TABLE screener.universe
    ADD COLUMN IF NOT EXISTS price_to_52w_high  NUMERIC(10, 4),
    ADD COLUMN IF NOT EXISTS price_to_52w_low   NUMERIC(10, 4),
    ADD COLUMN IF NOT EXISTS fcf_per_share       NUMERIC(12, 4),
    ADD COLUMN IF NOT EXISTS ocf_per_share       NUMERIC(12, 4),
    ADD COLUMN IF NOT EXISTS revenue_per_share   NUMERIC(12, 4),
    ADD COLUMN IF NOT EXISTS working_capital     NUMERIC(18, 2);

COMMENT ON COLUMN screener.universe.price_to_52w_high IS 'Price / 52-week high. 1.0 = at high, 0.9 = 10% below high.';
COMMENT ON COLUMN screener.universe.price_to_52w_low  IS 'Price / 52-week low.  1.0 = at low, 1.5 = 50% above low.';
COMMENT ON COLUMN screener.universe.fcf_per_share      IS 'Free Cash Flow per share (AUD). Derived from fcf_fy0 (AUD M).';
COMMENT ON COLUMN screener.universe.ocf_per_share      IS 'Operating Cash Flow per share (AUD). Derived from cfo_fy0 (AUD M).';
COMMENT ON COLUMN screener.universe.revenue_per_share  IS 'Revenue per share (AUD). Derived from revenue_fy0 (AUD M).';
COMMENT ON COLUMN screener.universe.working_capital    IS 'Working Capital in AUD millions (current assets - current liabilities).';
