-- Record the currency the financial statements are stated in
-- ==========================================================
-- Found 30 Sep 2026. EODHD states two currencies per fundamentals file and
-- only one of them is about the numbers:
--
--     General.CurrencyCode              AUD    the LISTING currency
--     Income_Statement currency_symbol  USD    the STATEMENTS
--
-- Nothing recorded the second one, so foreign-denominated figures were loaded
-- into columns that mean AUD and compared directly against AUD peers. 160 ASX
-- companies report in a foreign currency -- 89 USD, 39 NZD, 16 CAD, and a tail
-- -- and BHP, the largest company on the exchange, is one of them.
--
-- This column is what lets applicability gate 1b fire. Without it the gate is
-- correct and inert: it can only suppress a mismatch it can see.
--
-- NULL is meaningful and is NOT a default of 'AUD'. 1,016 of 2,019 codes state
-- no currency at all because they have no financial statements, and "we do not
-- know" must stay distinguishable from "we know it is AUD". Defaulting would
-- assert something the source never said -- the same mistake, one level down.
--
-- Safe to re-run.

ALTER TABLE staging_au.fundamentals
    ADD COLUMN IF NOT EXISTS reporting_currency TEXT;

COMMENT ON COLUMN staging_au.fundamentals.reporting_currency IS
    'Currency the financial statements are stated in, from EODHD''s '
    'per-section Financials.*.currency_symbol -- NOT General.CurrencyCode, '
    'which is the listing currency and reads AUD for USD reporters like BHP. '
    'NULL means the source stated none, which is not the same as AUD.';

ALTER TABLE screener.universe
    ADD COLUMN IF NOT EXISTS reporting_currency TEXT;

COMMENT ON COLUMN screener.universe.reporting_currency IS
    'Carried from staging_au.fundamentals. Drives applicability gate 1b: '
    'metrics mixing an AUD market quantity with a statement quantity '
    '(pe_ratio, price_to_book, price_to_sales, peg_ratio, ev_ebitda, '
    'ev_ebit, altman_z_score, book_value_per_share) are NOT_MEANINGFUL with '
    'cause unit_mismatch when this is set and differs from AUD. Ratios of '
    'two statement figures are unaffected -- their units cancel.';

CREATE INDEX IF NOT EXISTS idx_universe_reporting_currency
    ON screener.universe (reporting_currency)
    WHERE reporting_currency IS NOT NULL AND reporting_currency <> 'AUD';
