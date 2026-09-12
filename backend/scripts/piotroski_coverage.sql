-- Can the data support a faithful nine-point Piotroski F-Score?
-- ==============================================================
-- The decision this informs: implement Piotroski properly before V2 freezes,
-- or ship V2 with piotroski_f_score — and therefore quality_score, and
-- through it composite_score — explicitly unavailable.
--
-- That choice became expensive because compute_factor_score averages
-- constituent ranks with skipna=True. Suppressing a constituent does not
-- narrow a factor, it silently reweights it, so an honest suppression has to
-- darken the dependent scores across the whole universe rather than quietly
-- dropping one signal.
--
-- The requirement measured here is the exact pair:
--
--     prior.fiscal_year = latest.fiscal_year - 1
--
-- not "two annual rows exist". Accepting any two rows would rebuild the
-- positional defect this whole exercise is removing.
--
-- Three failure modes are kept apart, because they mean different things and
-- clear by different means:
--
--     period absent              the company has no Y-1 statement
--     field null                 the period exists, the observation does not
--     denominator zero or below  the observation exists, the ratio does not
--
--     sudo -u postgres psql -d asx_screener -f scripts/piotroski_coverage.sql
--
-- Read-only. It establishes whether the observations exist. It deliberately
-- does not choose the formulas: the leverage criterion is a change in a
-- leverage RATIO rather than a fall in absolute debt, and the share-issuance
-- criterion needs a defensible reading of shares_outstanding across splits.
-- Methodology comes after coverage, not from it.

\pset format aligned
\pset null '—'

CREATE TEMP VIEW piotroski_inputs AS
WITH base AS (
    SELECT u.asx_code, u.is_asx200, u.is_asx300, u.market_cap,
           (SELECT max(fiscal_year) FROM financials.annual_pnl
             WHERE asx_code = u.asx_code) AS fy
      FROM screener.universe u
     WHERE u.status = 'active'
)
SELECT b.asx_code, b.is_asx200, b.is_asx300, b.market_cap, b.fy,
       (pp.fiscal_year IS NOT NULL) AS has_prior_pnl,
       (pb.fiscal_year IS NOT NULL) AS has_prior_bs,
       cp.revenue      AS cur_rev,  pp.revenue      AS pri_rev,
       cp.net_profit   AS cur_ni,   pp.net_profit   AS pri_ni,
       cp.gross_profit AS cur_gp,   pp.gross_profit AS pri_gp,
       cb.total_assets AS cur_ta,   pb.total_assets AS pri_ta,
       cb.long_term_debt AS cur_ltd, pb.long_term_debt AS pri_ltd,
       cb.total_current_assets AS cur_ca, pb.total_current_assets AS pri_ca,
       cb.total_current_liab   AS cur_cl, pb.total_current_liab   AS pri_cl,
       cb.shares_outstanding   AS cur_sh, pb.shares_outstanding   AS pri_sh,
       cc.cfo AS cur_cfo
  FROM base b
  LEFT JOIN financials.annual_pnl cp
         ON cp.asx_code = b.asx_code AND cp.fiscal_year = b.fy
  LEFT JOIN financials.annual_pnl pp
         ON pp.asx_code = b.asx_code AND pp.fiscal_year = b.fy - 1
  LEFT JOIN financials.annual_balance_sheet cb
         ON cb.asx_code = b.asx_code AND cb.fiscal_year = b.fy
  LEFT JOIN financials.annual_balance_sheet pb
         ON pb.asx_code = b.asx_code AND pb.fiscal_year = b.fy - 1
  LEFT JOIN financials.annual_cashflow cc
         ON cc.asx_code = b.asx_code AND cc.fiscal_year = b.fy
 WHERE b.fy IS NOT NULL;

CREATE TEMP VIEW piotroski_criteria AS
SELECT *,
       -- F1 positive ROA: current net income over current assets
       (cur_ni IS NOT NULL AND cur_ta > 0)                            AS f1,
       -- F2 positive operating cash flow
       (cur_cfo IS NOT NULL)                                          AS f2,
       -- F3 ROA improved: both years, each with its OWN denominator
       (cur_ni IS NOT NULL AND pri_ni IS NOT NULL
        AND cur_ta > 0 AND pri_ta > 0)                                AS f3,
       -- F4 accruals: CFO against net income, same year
       (cur_cfo IS NOT NULL AND cur_ni IS NOT NULL)                   AS f4,
       -- F5 leverage fell: long-term debt over assets, both years
       (cur_ltd IS NOT NULL AND pri_ltd IS NOT NULL
        AND cur_ta > 0 AND pri_ta > 0)                                AS f5,
       -- F6 current ratio improved
       (cur_ca IS NOT NULL AND pri_ca IS NOT NULL
        AND cur_cl > 0 AND pri_cl > 0)                                AS f6,
       -- F7 no new shares issued
       (cur_sh IS NOT NULL AND pri_sh IS NOT NULL
        AND cur_sh > 0 AND pri_sh > 0)                                AS f7,
       -- F8 gross margin improved
       (cur_gp IS NOT NULL AND pri_gp IS NOT NULL
        AND cur_rev > 0 AND pri_rev > 0)                              AS f8,
       -- F9 asset turnover improved
       (cur_rev IS NOT NULL AND pri_rev IS NOT NULL
        AND cur_ta > 0 AND pri_ta > 0)                                AS f9
  FROM piotroski_inputs;

-- ── The exact consecutive pair, before any field is considered ──────────────

SELECT count(*)                                        AS active_with_any_pnl,
       count(*) FILTER (WHERE has_prior_pnl)           AS exact_prior_pnl_year,
       count(*) FILTER (WHERE has_prior_bs)            AS exact_prior_bs_year,
       count(*) FILTER (WHERE has_prior_pnl AND has_prior_bs)
                                                       AS both_statements,
       count(*) FILTER (WHERE NOT has_prior_pnl)       AS period_absent
  FROM piotroski_inputs;

-- ── Per-criterion evaluability ──────────────────────────────────────────────

SELECT count(*)                          AS companies,
       count(*) FILTER (WHERE f1) AS f1_roa_positive,
       count(*) FILTER (WHERE f2) AS f2_cfo_positive,
       count(*) FILTER (WHERE f3) AS f3_roa_improved,
       count(*) FILTER (WHERE f4) AS f4_accruals,
       count(*) FILTER (WHERE f5) AS f5_leverage,
       count(*) FILTER (WHERE f6) AS f6_current_ratio,
       count(*) FILTER (WHERE f7) AS f7_shares,
       count(*) FILTER (WHERE f8) AS f8_gross_margin,
       count(*) FILTER (WHERE f9) AS f9_asset_turnover,
       count(*) FILTER (WHERE f1 AND f2 AND f3 AND f4 AND f5
                          AND f6 AND f7 AND f8 AND f9) AS all_nine
  FROM piotroski_criteria;

-- ── Where the coverage actually breaks ──────────────────────────────────────
-- If nearly everything is complete except one criterion, that criterion is
-- the implementation blocker rather than "Piotroski coverage" in general.

SELECT 'complete except F5 leverage'      AS bottleneck,
       count(*) FILTER (WHERE f1 AND f2 AND f3 AND f4 AND NOT f5
                          AND f6 AND f7 AND f8 AND f9) AS companies
  FROM piotroski_criteria
UNION ALL SELECT 'complete except F6 current ratio',
       count(*) FILTER (WHERE f1 AND f2 AND f3 AND f4 AND f5
                          AND NOT f6 AND f7 AND f8 AND f9)
  FROM piotroski_criteria
UNION ALL SELECT 'complete except F7 shares',
       count(*) FILTER (WHERE f1 AND f2 AND f3 AND f4 AND f5
                          AND f6 AND NOT f7 AND f8 AND f9)
  FROM piotroski_criteria
UNION ALL SELECT 'complete except F8 gross margin',
       count(*) FILTER (WHERE f1 AND f2 AND f3 AND f4 AND f5
                          AND f6 AND f7 AND NOT f8 AND f9)
  FROM piotroski_criteria
UNION ALL SELECT 'complete except F2 operating cash flow',
       count(*) FILTER (WHERE f1 AND NOT f2 AND f3 AND f4 AND f5
                          AND f6 AND f7 AND f8 AND f9)
  FROM piotroski_criteria
 ORDER BY 2 DESC;

-- ── Missing field versus zero denominator, per input ────────────────────────
-- Among companies that DO have the exact prior year, so an absent period
-- cannot be mistaken for an absent observation.

SELECT 'prior shares_outstanding'   AS input,
       count(*) FILTER (WHERE pri_sh IS NULL)      AS field_null,
       count(*) FILTER (WHERE pri_sh IS NOT NULL
                          AND pri_sh <= 0)         AS non_positive
  FROM piotroski_criteria WHERE has_prior_bs
UNION ALL SELECT 'prior long_term_debt',
       count(*) FILTER (WHERE pri_ltd IS NULL),
       count(*) FILTER (WHERE pri_ltd IS NOT NULL AND pri_ltd < 0)
  FROM piotroski_criteria WHERE has_prior_bs
UNION ALL SELECT 'prior total_current_liab',
       count(*) FILTER (WHERE pri_cl IS NULL),
       count(*) FILTER (WHERE pri_cl IS NOT NULL AND pri_cl <= 0)
  FROM piotroski_criteria WHERE has_prior_bs
UNION ALL SELECT 'prior total_assets',
       count(*) FILTER (WHERE pri_ta IS NULL),
       count(*) FILTER (WHERE pri_ta IS NOT NULL AND pri_ta <= 0)
  FROM piotroski_criteria WHERE has_prior_bs
UNION ALL SELECT 'prior gross_profit',
       count(*) FILTER (WHERE pri_gp IS NULL), 0
  FROM piotroski_criteria WHERE has_prior_pnl
UNION ALL SELECT 'current cfo',
       count(*) FILTER (WHERE cur_cfo IS NULL), 0
  FROM piotroski_criteria
 ORDER BY 2 DESC;

-- ── By segment ──────────────────────────────────────────────────────────────
-- 65% of the universe means one thing if every liquid name is covered and
-- quite another if the majors are missing.

SELECT segment, companies, all_nine,
       round(100.0 * all_nine / nullif(companies, 0), 1) AS pct
  FROM (
    SELECT 'all active' AS segment, count(*) AS companies,
           count(*) FILTER (WHERE f1 AND f2 AND f3 AND f4 AND f5
                              AND f6 AND f7 AND f8 AND f9) AS all_nine, 1 AS ord
      FROM piotroski_criteria
    UNION ALL
    SELECT 'ASX 200', count(*),
           count(*) FILTER (WHERE f1 AND f2 AND f3 AND f4 AND f5
                              AND f6 AND f7 AND f8 AND f9), 2
      FROM piotroski_criteria WHERE is_asx200
    UNION ALL
    SELECT 'ASX 300', count(*),
           count(*) FILTER (WHERE f1 AND f2 AND f3 AND f4 AND f5
                              AND f6 AND f7 AND f8 AND f9), 3
      FROM piotroski_criteria WHERE is_asx300
    UNION ALL
    SELECT 'market cap >= $1b', count(*),
           count(*) FILTER (WHERE f1 AND f2 AND f3 AND f4 AND f5
                              AND f6 AND f7 AND f8 AND f9), 4
      FROM piotroski_criteria WHERE market_cap >= 1e9
    UNION ALL
    SELECT 'market cap < $50m', count(*),
           count(*) FILTER (WHERE f1 AND f2 AND f3 AND f4 AND f5
                              AND f6 AND f7 AND f8 AND f9), 5
      FROM piotroski_criteria WHERE market_cap < 5e7
  ) s
 ORDER BY ord;
