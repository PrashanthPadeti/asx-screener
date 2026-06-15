-- Migration 055: Add balance sheet signal columns to screener.universe
-- net_cash:                          true when net_debt < 0 (more cash than debt)
-- cash_to_debt:                      cash / total_debt ratio
-- fcf_to_debt:                       free cash flow / total_debt ratio
-- working_capital_to_sales:          working capital / revenue ratio
-- debt_growing_slower_than_profit:   profit growth > debt growth (1Y)
-- inventory_growing_slower_than_sales: revenue growth >= inventory growth (1Y)
-- receivables_growing_slower_than_sales: revenue growth >= receivables growth (1Y)

ALTER TABLE screener.universe
    ADD COLUMN IF NOT EXISTS net_cash                              BOOLEAN,
    ADD COLUMN IF NOT EXISTS cash_to_debt                         DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS fcf_to_debt                          DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS working_capital_to_sales             DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS debt_growing_slower_than_profit      BOOLEAN,
    ADD COLUMN IF NOT EXISTS inventory_growing_slower_than_sales  BOOLEAN,
    ADD COLUMN IF NOT EXISTS receivables_growing_slower_than_sales BOOLEAN;
