-- market.companies_current had drifted two columns behind its own table.
--
-- `market.companies` is SCD Type 2: an attribute change closes the old row
-- (is_current = FALSE) and opens a new one. 4,459 rows describe 2,579 codes,
-- and 1,878 codes carry at least one superseded row. Any query reading the
-- base table without `is_current` therefore returns roughly 1.7 rows per
-- company. `market.companies_current` exists to be the thing consumers read
-- instead -- and the universe builder, technical_compute and daily_compute
-- already do.
--
-- But the view enumerates its columns, and it was created before
-- `business_model_tag` and `commodity_exposure` were added to the table. It
-- kept serving 50 of 52 columns, correctly and silently, for as long as those
-- columns have existed. Nothing failed, because a view that is missing a
-- column is not an error until someone selects it -- and the only consumer
-- that wanted those two read the base table directly, with its own
-- `is_current = TRUE` predicate, so it never noticed.
--
-- That is why this migration exists at all: the serving layer is being moved
-- onto the view, and `/companies/{code}` does `SELECT *`. A view two columns
-- short would have quietly narrowed the company detail payload.
--
-- Columns are enumerated rather than `SELECT *` because CREATE OR REPLACE
-- VIEW requires the existing columns to keep their name, type and position;
-- enumeration guarantees that regardless of the base table's physical column
-- order. The two new columns are appended, which CREATE OR REPLACE permits.
--
-- Drift will recur the next time a column is added to the table. It is caught
-- by tests/test_companies_current_covers_the_table.py rather than prevented
-- here, because no view definition can prevent it.

CREATE OR REPLACE VIEW market.companies_current AS
SELECT id,
       asx_code,
       isin,
       company_name,
       short_name,
       gics_sector,
       gics_industry_group,
       gics_industry,
       gics_sub_industry,
       asx_sector,
       company_type,
       is_reit,
       is_miner,
       is_bank,
       is_insurer,
       is_asx20,
       is_asx50,
       is_asx100,
       is_asx200,
       is_asx300,
       is_all_ords,
       is_small_ords,
       listing_date,
       ipo_price,
       delisting_date,
       delisting_reason,
       status,
       financial_year_end,
       shares_outstanding,
       shares_float,
       face_value,
       website,
       abn,
       acn,
       domicile,
       state,
       primary_commodity,
       secondary_commodity,
       description,
       logo_url,
       employee_count,
       created_at,
       updated_at,
       percent_insiders,
       percent_institutions,
       cusip,
       fiscal_year_end_month,
       valid_from,
       valid_to,
       is_current,
       -- appended: present on market.companies, absent from this view until now
       business_model_tag,
       commodity_exposure
  FROM market.companies
 WHERE is_current = true;

COMMENT ON VIEW market.companies_current IS
    'One row per ASX code: the current record in the SCD Type 2 history held '
    'by market.companies. Every read of company identity or classification '
    'goes through this view. Reading market.companies directly returns '
    'superseded rows as well -- ~1.7 rows per code -- which inflates counts, '
    'consumes LIMIT budget and makes any single-row fetch an arbitrary choice '
    'between the current and a historical record.';
