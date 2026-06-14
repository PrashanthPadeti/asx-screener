-- Historical income-statement level columns on screener.universe.
-- One value per fiscal-year offset (now / last yr / 3 / 5 / 7 / 10 years back),
-- for Sales (revenue), Gross Profit, Pre-tax Profit (PBT) and Net Profit.
-- Stored in AUD millions (annual_pnl is already in millions).
--
-- NOTE: these columns may already exist in the table as a narrow NUMERIC(8,4)
-- (max 9999.9999), which overflows on large-cap values (e.g. BHP gross profit
-- ~30,000 M). So we ADD if missing AND force the type to DOUBLE PRECISION.
-- Both statements are idempotent.

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

-- Force wide type in case the columns pre-existed as NUMERIC(8,4).
ALTER TABLE screener.universe
    ALTER COLUMN gross_profit_fy0  TYPE DOUBLE PRECISION,
    ALTER COLUMN gross_profit_fy1  TYPE DOUBLE PRECISION,
    ALTER COLUMN gross_profit_fy3  TYPE DOUBLE PRECISION,
    ALTER COLUMN gross_profit_fy5  TYPE DOUBLE PRECISION,
    ALTER COLUMN gross_profit_fy7  TYPE DOUBLE PRECISION,
    ALTER COLUMN gross_profit_fy10 TYPE DOUBLE PRECISION,
    ALTER COLUMN pbt_fy0           TYPE DOUBLE PRECISION,
    ALTER COLUMN pbt_fy1           TYPE DOUBLE PRECISION,
    ALTER COLUMN pbt_fy3           TYPE DOUBLE PRECISION,
    ALTER COLUMN pbt_fy5           TYPE DOUBLE PRECISION,
    ALTER COLUMN pbt_fy7           TYPE DOUBLE PRECISION,
    ALTER COLUMN pbt_fy10          TYPE DOUBLE PRECISION,
    ALTER COLUMN revenue_fy3       TYPE DOUBLE PRECISION,
    ALTER COLUMN revenue_fy5       TYPE DOUBLE PRECISION,
    ALTER COLUMN revenue_fy7       TYPE DOUBLE PRECISION,
    ALTER COLUMN revenue_fy10      TYPE DOUBLE PRECISION,
    ALTER COLUMN net_profit_fy3    TYPE DOUBLE PRECISION,
    ALTER COLUMN net_profit_fy5    TYPE DOUBLE PRECISION,
    ALTER COLUMN net_profit_fy7    TYPE DOUBLE PRECISION,
    ALTER COLUMN net_profit_fy10   TYPE DOUBLE PRECISION;
