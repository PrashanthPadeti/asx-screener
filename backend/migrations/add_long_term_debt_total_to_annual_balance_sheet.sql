-- The second long-term debt measure EODHD actually sends
-- =====================================================
-- The payload carries TWO keys, and the loader reads one of them:
--
--     longTermDebt        borrowings only
--     longTermDebtTotal   wider -- lease and similar non-current obligations
--
-- They are not synonyms and must never be substituted for one another.
-- Measured across all 1,886 cached payloads, 33,201 balance-sheet years:
--
--     neither key                13,903   42%
--     longTermDebtTotal only, =0  5,444   16%
--     longTermDebt only           4,862   15%
--     BOTH, DIFFERING             4,067   12%
--     both, equal                 2,491    8%
--     longTermDebtTotal only, !=0 2,434    7%
--
-- Where both exist they DISAGREE more often than they agree, and
-- systematically: MP1 reports 6.7m against 13.4m, 3.8m against 8.7m, 7.1m
-- against 14.2m -- roughly double, year after year, which is what a
-- lease-inclusive measure looks like beside a borrowings-only one.
--
-- Why this is a column and not a COALESCE. Piotroski F5 compares leverage in
-- year t against year t-1. Falling back from one key to the other inside a
-- single company's series would compare borrowings against
-- borrowings-plus-leases and report a leverage change that is purely an
-- artefact of which key happened to be populated that year. The definition
-- must be constant down each series, so both quantities are stored under
-- their own names and the scorer picks ONE by rule.
--
-- The rule it picks: longTermDebtTotal. On the latest consecutive pair it
-- makes F5 assessable for 1,624 companies against 648 for longTermDebt, and
-- 604 of those 648 are inside the larger set -- so the wider measure costs
-- almost no coverage and gains 976 companies. That choice is reversible
-- precisely because this column does not overwrite the other one.
--
-- A NULL here means the period did not report the field. It does not mean
-- zero. EODHD states a real zero as "0.00", which is why only_Total_zero is
-- counted separately above: 5,444 years where the source affirms no
-- non-current debt, which IS assessable, as distinct from the 13,903 where it
-- says nothing at all, which is not.
--
-- Safe to run more than once. Adding a nullable column takes no table rewrite
-- in PostgreSQL 11+.
--
--   psql -d asx_screener -f backend/migrations/add_long_term_debt_total_to_annual_balance_sheet.sql
--
-- APPLY THIS BEFORE DEPLOYING v11.2.74. deploy.sh does not run migrations,
-- and the loader's INSERT names this column: without it the next fundamentals
-- load fails.

-- The new column holds the same KIND of quantity as long_term_debt -- a
-- balance-sheet money amount in the same units -- so it takes that column's
-- type rather than a hardcoded guess. Cloning it also fails loudly if the
-- column it is modelled on has gone away.
DO $$
DECLARE col_type text;
BEGIN
    SELECT format_type(a.atttypid, a.atttypmod)
      INTO col_type
      FROM pg_attribute a
     WHERE a.attrelid = 'financials.annual_balance_sheet'::regclass
       AND a.attname  = 'long_term_debt'
       AND a.attnum   > 0
       AND NOT a.attisdropped;

    IF col_type IS NULL THEN
        RAISE EXCEPTION
            'financials.annual_balance_sheet.long_term_debt does not exist; '
            'long_term_debt_total is defined as the same measure and cannot '
            'be typed without it';
    END IF;

    EXECUTE format(
        'ALTER TABLE financials.annual_balance_sheet '
        'ADD COLUMN IF NOT EXISTS long_term_debt_total %s', col_type);
END $$;

COMMENT ON COLUMN financials.annual_balance_sheet.long_term_debt_total IS
    'Non-current debt INCLUDING lease and similar obligations, from EODHD '
    'Financials.Balance_Sheet.longTermDebtTotal. Distinct from '
    'long_term_debt (borrowings only), which it exceeds by roughly 2x where '
    'both are reported; the two disagree on 4,067 of the 6,558 years that '
    'carry both. Never substitute one for the other within a series -- '
    'Piotroski F5 compares year to year and would read the definition change '
    'as a leverage change. A NULL means the period did not report it; the '
    'source states a genuine zero as 0.00.';
