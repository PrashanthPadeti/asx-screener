-- Tier A: surface income-statement & balance-sheet line items into screener.universe.
-- All AUD millions (financials.* are stored in millions). DOUBLE PRECISION
-- (ADD if missing, then force type) to avoid the NUMERIC(8,4) overflow class.

ALTER TABLE screener.universe
    ADD COLUMN IF NOT EXISTS cogs                      DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS ebit                      DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS income_tax_expense        DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS interest_expense          DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS depreciation              DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS trade_receivables         DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS inventory                 DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS goodwill                  DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS intangibles               DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS ppe_net                   DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS total_current_assets      DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS total_current_liabilities DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS total_liabilities         DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS long_term_debt            DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS retained_earnings         DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS cfi                       DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS dividends_paid            DOUBLE PRECISION;

ALTER TABLE screener.universe
    ALTER COLUMN cogs                      TYPE DOUBLE PRECISION,
    ALTER COLUMN ebit                      TYPE DOUBLE PRECISION,
    ALTER COLUMN income_tax_expense        TYPE DOUBLE PRECISION,
    ALTER COLUMN interest_expense          TYPE DOUBLE PRECISION,
    ALTER COLUMN depreciation              TYPE DOUBLE PRECISION,
    ALTER COLUMN trade_receivables         TYPE DOUBLE PRECISION,
    ALTER COLUMN inventory                 TYPE DOUBLE PRECISION,
    ALTER COLUMN goodwill                  TYPE DOUBLE PRECISION,
    ALTER COLUMN intangibles               TYPE DOUBLE PRECISION,
    ALTER COLUMN ppe_net                   TYPE DOUBLE PRECISION,
    ALTER COLUMN total_current_assets      TYPE DOUBLE PRECISION,
    ALTER COLUMN total_current_liabilities TYPE DOUBLE PRECISION,
    ALTER COLUMN total_liabilities         TYPE DOUBLE PRECISION,
    ALTER COLUMN long_term_debt            TYPE DOUBLE PRECISION,
    ALTER COLUMN retained_earnings         TYPE DOUBLE PRECISION,
    ALTER COLUMN cfi                       TYPE DOUBLE PRECISION,
    ALTER COLUMN dividends_paid            TYPE DOUBLE PRECISION;
