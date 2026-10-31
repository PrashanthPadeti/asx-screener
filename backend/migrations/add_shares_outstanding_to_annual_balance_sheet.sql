-- Per-year share count on the annual balance sheet
-- ================================================
-- EODHD carries commonStockSharesOutstanding in Financials.Balance_Sheet.
-- load_fundamentals asked the Income_Statement payload for it and received
-- None on every row of every year, so financials.annual_pnl.shares_used has
-- been NULL for all 2,113 active companies since the beginning.
--
-- Nothing consumed that column, so nothing failed. What it did was make the
-- Piotroski F-Score's F7 criterion (no new shares issued) unevaluable for the
-- entire universe. That withheld the score -- correctly -- which left ten of
-- thirty-one preset screens, nine of them Premium, returning nothing since
-- they shipped.
--
-- market.companies.shares_outstanding already exists and is NOT a substitute:
-- it is a single current snapshot from SharesStats with no history, and F7
-- needs two consecutive years.
--
-- Safe to run more than once. Adding a nullable column takes no table rewrite
-- in PostgreSQL 11+, so this does not lock the table for any meaningful time.
--
--   psql -d asx_screener -f backend/migrations/add_shares_outstanding_to_annual_balance_sheet.sql
--
-- APPLY THIS BEFORE DEPLOYING v11.2.73. deploy.sh does not run migrations,
-- and the loader's INSERT names this column: without it the next fundamentals
-- load fails. The column is nullable and unread until v11.2.74, so applying
-- it early is harmless.

ALTER TABLE financials.annual_balance_sheet
    ADD COLUMN IF NOT EXISTS shares_outstanding BIGINT;

COMMENT ON COLUMN financials.annual_balance_sheet.shares_outstanding IS
    'Common shares outstanding at the period end, from EODHD '
    'Financials.Balance_Sheet.commonStockSharesOutstanding. Populated from '
    'v11.2.73. Two consecutive years are required by Piotroski F7; a NULL '
    'means the period was not reported, never that no shares exist.';
