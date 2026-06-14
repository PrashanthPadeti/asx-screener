-- Tier B: derived ratio columns on screener.universe (computed in the build from
-- the Tier A line items). Mix of x-ratios, days, decimal-% and per-share/AUD-M.
-- DOUBLE PRECISION (ADD if missing + force type) to avoid NUMERIC(8,4) overflow.

ALTER TABLE screener.universe
    ADD COLUMN IF NOT EXISTS quick_ratio                   DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS cash_ratio                    DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS debt_to_ebitda                DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS days_sales_outstanding        DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS days_inventory_outstanding    DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS inventory_turnover            DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS receivables_turnover          DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS pretax_margin                 DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS nopat                         DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS ebitda_interest_coverage      DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS equity_ratio                  DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS liabilities_to_assets         DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS fixed_asset_turnover          DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS capex_to_revenue              DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS tangible_book_value_per_share DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS cash_per_share                DOUBLE PRECISION;

ALTER TABLE screener.universe
    ALTER COLUMN quick_ratio                   TYPE DOUBLE PRECISION,
    ALTER COLUMN cash_ratio                    TYPE DOUBLE PRECISION,
    ALTER COLUMN debt_to_ebitda                TYPE DOUBLE PRECISION,
    ALTER COLUMN days_sales_outstanding        TYPE DOUBLE PRECISION,
    ALTER COLUMN days_inventory_outstanding    TYPE DOUBLE PRECISION,
    ALTER COLUMN inventory_turnover            TYPE DOUBLE PRECISION,
    ALTER COLUMN receivables_turnover          TYPE DOUBLE PRECISION,
    ALTER COLUMN pretax_margin                 TYPE DOUBLE PRECISION,
    ALTER COLUMN nopat                         TYPE DOUBLE PRECISION,
    ALTER COLUMN ebitda_interest_coverage      TYPE DOUBLE PRECISION,
    ALTER COLUMN equity_ratio                  TYPE DOUBLE PRECISION,
    ALTER COLUMN liabilities_to_assets         TYPE DOUBLE PRECISION,
    ALTER COLUMN fixed_asset_turnover          TYPE DOUBLE PRECISION,
    ALTER COLUMN capex_to_revenue              TYPE DOUBLE PRECISION,
    ALTER COLUMN tangible_book_value_per_share TYPE DOUBLE PRECISION,
    ALTER COLUMN cash_per_share                TYPE DOUBLE PRECISION;
