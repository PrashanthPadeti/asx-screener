-- What does "every declared constituent" cost?
-- ============================================
-- compute_factor no longer averages whatever is non-null. A declared
-- constituent that is absent makes the factor unavailable, because a score
-- computed without it is a different model under the same name.
--
-- That rule is right, and its blast radius is unmeasured. Most factor
-- constituents are NOT governed, so they carry no assessment and the engine
-- cannot tell "not meaningful for this company" from "missing":
--
--     momentum   return_1m/3m/6m, rsi_14, adx_14   none governed
--     value      fcf_yield                          not governed
--
-- For a governed constituent the observation gate can rule NOT_MEANINGFUL and
-- the model reweights — a company with negative earnings has no meaningful
-- P/E, and that is a statement about the company rather than a gap. For an
-- ungoverned one there is no such gate, so a NaN refuses.
--
-- This measures, per factor, how many active companies have every declared
-- constituent present, against how many carry a score today.
--
--     sudo -u postgres psql -d asx_screener -f scripts/factor_strictness_sizing.sql
--
-- Read-only. It does not decide anything: whether a large drop is the correct
-- blast radius or an argument for governing more constituents is a product
-- judgement, and the answer probably differs per factor.

\pset format aligned
\pset null '—'

-- ── Complete coverage per factor, against what is scored today ──────────────

WITH active AS (
    SELECT * FROM screener.universe WHERE status = 'active'
)
SELECT 'value' AS factor, count(*) AS active_rows,
       count(*) FILTER (WHERE pe_ratio IS NOT NULL
                          AND price_to_book IS NOT NULL
                          AND ev_to_ebitda IS NOT NULL
                          AND fcf_yield IS NOT NULL
                          AND price_to_sales IS NOT NULL) AS all_present,
       count(value_score)                                 AS scored_today
  FROM active
UNION ALL
SELECT 'quality (V2)', count(*),
       count(*) FILTER (WHERE roe IS NOT NULL
                          AND roce IS NOT NULL
                          AND altman_z_score IS NOT NULL
                          AND debt_to_equity IS NOT NULL
                          AND net_margin IS NOT NULL),
       count(quality_score)
  FROM active
UNION ALL
SELECT 'growth', count(*),
       count(*) FILTER (WHERE revenue_growth_1y IS NOT NULL
                          AND earnings_growth_1y IS NOT NULL
                          AND eps_growth_3y_cagr IS NOT NULL
                          AND revenue_growth_hoh IS NOT NULL
                          AND eps_growth_hoh IS NOT NULL
                          AND revenue_cagr_5y IS NOT NULL),
       count(growth_score)
  FROM active
UNION ALL
SELECT 'momentum', count(*),
       count(*) FILTER (WHERE return_1m IS NOT NULL
                          AND return_3m IS NOT NULL
                          AND return_6m IS NOT NULL
                          AND rsi_14 IS NOT NULL
                          AND adx_14 IS NOT NULL),
       count(momentum_score)
  FROM active
UNION ALL
SELECT 'income', count(*),
       count(*) FILTER (WHERE grossed_up_yield IS NOT NULL
                          AND dividend_yield IS NOT NULL
                          AND franking_pct IS NOT NULL
                          AND dividend_consecutive_yrs IS NOT NULL
                          AND dividend_cagr_3y IS NOT NULL
                          AND payout_ratio IS NOT NULL),
       count(income_score)
  FROM active;

-- ── Which constituent is doing the excluding ────────────────────────────────
-- If one signal accounts for most of the loss, governing it — so the
-- observation gate can rule NOT_MEANINGFUL and the model reweight — is a
-- different and much cheaper answer than accepting the drop.

WITH active AS (
    SELECT * FROM screener.universe WHERE status = 'active'
)
SELECT 'value'   AS factor, 'pe_ratio'       AS constituent, TRUE AS governed,
       count(*) FILTER (WHERE pe_ratio IS NULL)        AS null_rows FROM active
UNION ALL SELECT 'value', 'price_to_book',  TRUE,
       count(*) FILTER (WHERE price_to_book IS NULL)   FROM active
UNION ALL SELECT 'value', 'ev_to_ebitda',   TRUE,
       count(*) FILTER (WHERE ev_to_ebitda IS NULL)    FROM active
UNION ALL SELECT 'value', 'fcf_yield',      FALSE,
       count(*) FILTER (WHERE fcf_yield IS NULL)       FROM active
UNION ALL SELECT 'value', 'price_to_sales', TRUE,
       count(*) FILTER (WHERE price_to_sales IS NULL)  FROM active
UNION ALL SELECT 'momentum', 'return_1m',   FALSE,
       count(*) FILTER (WHERE return_1m IS NULL)       FROM active
UNION ALL SELECT 'momentum', 'return_3m',   FALSE,
       count(*) FILTER (WHERE return_3m IS NULL)       FROM active
UNION ALL SELECT 'momentum', 'return_6m',   FALSE,
       count(*) FILTER (WHERE return_6m IS NULL)       FROM active
UNION ALL SELECT 'momentum', 'rsi_14',      FALSE,
       count(*) FILTER (WHERE rsi_14 IS NULL)          FROM active
UNION ALL SELECT 'momentum', 'adx_14',      FALSE,
       count(*) FILTER (WHERE adx_14 IS NULL)          FROM active
UNION ALL SELECT 'income', 'grossed_up_yield', TRUE,
       count(*) FILTER (WHERE grossed_up_yield IS NULL) FROM active
UNION ALL SELECT 'income', 'dividend_consecutive_yrs', FALSE,
       count(*) FILTER (WHERE dividend_consecutive_yrs IS NULL) FROM active
UNION ALL SELECT 'income', 'dividend_cagr_3y', FALSE,
       count(*) FILTER (WHERE dividend_cagr_3y IS NULL) FROM active
UNION ALL SELECT 'growth', 'eps_growth_hoh', FALSE,
       count(*) FILTER (WHERE eps_growth_hoh IS NULL)  FROM active
UNION ALL SELECT 'growth', 'revenue_cagr_5y', FALSE,
       count(*) FILTER (WHERE revenue_cagr_5y IS NULL) FROM active
 ORDER BY 1, 4 DESC;

-- ── How much is one signal short of complete? ───────────────────────────────
-- Companies that would score under a "n-1 of n" policy but not under strict.
-- Not a proposal — a measurement of how sharp the cliff is.

WITH active AS (
    SELECT * FROM screener.universe WHERE status = 'active'
), counted AS (
    SELECT (pe_ratio IS NOT NULL)::int + (price_to_book IS NOT NULL)::int
         + (ev_to_ebitda IS NOT NULL)::int + (fcf_yield IS NOT NULL)::int
         + (price_to_sales IS NOT NULL)::int AS value_present,
           (return_1m IS NOT NULL)::int + (return_3m IS NOT NULL)::int
         + (return_6m IS NOT NULL)::int + (rsi_14 IS NOT NULL)::int
         + (adx_14 IS NOT NULL)::int        AS momentum_present
      FROM active
)
SELECT 'value' AS factor, value_present AS constituents_present, count(*)
  FROM counted GROUP BY 1, 2
UNION ALL
SELECT 'momentum', momentum_present, count(*)
  FROM counted GROUP BY 1, 2
 ORDER BY 1, 2 DESC;
