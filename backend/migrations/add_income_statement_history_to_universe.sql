-- Add historical income-statement level columns to screener.universe.
-- One value per fiscal-year offset (now / last yr / 3 / 5 / 7 / 10 years back),
-- for Sales (revenue), Gross Profit, Pre-tax Profit (PBT) and Net Profit.
-- All stored in AUD millions (annual_pnl is already in millions).
-- Sparse by nature — many ASX small/mid-caps lack 7-10 years of history.
--
-- Populated by build_screener_universe.py via pnl0/pnl1/pnl3/pnl5/pnl7/pnl10
-- LATERAL joins on financials.annual_pnl. Run once before the next rebuild.

ALTER TABLE screener.universe
    ADD COLUMN IF NOT EXISTS gross_profit_fy0  DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS gross_profit_fy1  DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS gross_profit_fy3  DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS gross_profit_fy5  DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS gross_profit_fy7  DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS gross_profit_fy10 DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS pbt_fy0           DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS pbt_fy1           DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS pbt_fy3           DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS pbt_fy5           DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS pbt_fy7           DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS pbt_fy10          DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS revenue_fy3       DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS revenue_fy5       DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS revenue_fy7       DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS revenue_fy10      DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS net_profit_fy3    DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS net_profit_fy5    DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS net_profit_fy7    DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS net_profit_fy10   DOUBLE PRECISION;
