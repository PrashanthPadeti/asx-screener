-- What the window defect is currently showing users
-- ==================================================
-- The sizing run found 26 active companies whose LATEST fiscal year uses a
-- positional window that is not the stated number of years. That is 1.2% of
-- the active universe, which sounds tolerable until you ask what those 26
-- actually display.
--
-- The error inflates magnitude in both directions. CAGR is
-- (end/start)^(1/years) - 1, so dividing by n when the real span is s > n
-- makes the exponent too large: a company that merely doubled over 19 years
-- (3.7% a year) is stored as 2^(1/3) - 1 = 26%. Decliners are exaggerated
-- just as hard in the other direction.
--
-- So a small count of affected companies is not the same decision as a small
-- count of affected VALUES. This query shows both: the real span behind each
-- stored figure, and the figure itself.
--
--     sudo -u postgres psql -d asx_screener -f scripts/cagr_visible_distortion.sql
--
-- Read-only.

\pset format aligned
\pset null '—'

-- ── The visible rows, with the true span beside the stored rate ─────────────
-- Only the latest fiscal year per company, because that is the row
-- screener.universe carries and therefore the only one a user can see.

WITH series AS (
    SELECT asx_code,
           fiscal_year,
           row_number() OVER (PARTITION BY asx_code
                               ORDER BY fiscal_year DESC)          AS recency,
           lag(fiscal_year, 3)  OVER w AS prior_3,
           lag(fiscal_year, 5)  OVER w AS prior_5,
           lag(fiscal_year, 7)  OVER w AS prior_7,
           lag(fiscal_year, 10) OVER w AS prior_10
      FROM financials.annual_pnl
    WINDOW w AS (PARTITION BY asx_code ORDER BY fiscal_year)
),
latest AS (
    SELECT asx_code, fiscal_year,
           fiscal_year - prior_3  AS span_3,
           fiscal_year - prior_5  AS span_5,
           fiscal_year - prior_7  AS span_7,
           fiscal_year - prior_10 AS span_10
      FROM series
     WHERE recency = 1
)
SELECT l.asx_code,
       u.company_name,
       l.fiscal_year                               AS fy,
       l.span_3, l.span_5,
       round(m.revenue_cagr_3y  * 100, 1)          AS rev_3y_pct,
       round(m.revenue_cagr_5y  * 100, 1)          AS rev_5y_pct,
       round(m.eps_cagr_3y      * 100, 1)          AS eps_3y_pct,
       round(m.net_income_cagr_3y * 100, 1)        AS ni_3y_pct
  FROM latest l
  JOIN screener.universe u
    ON u.asx_code = l.asx_code AND u.status = 'active'
  LEFT JOIN market.yearly_metrics m
    ON m.asx_code = l.asx_code AND m.fiscal_year = l.fiscal_year
 WHERE (l.span_3  IS NOT NULL AND l.span_3  <> 3)
    OR (l.span_5  IS NOT NULL AND l.span_5  <> 5)
    OR (l.span_7  IS NOT NULL AND l.span_7  <> 7)
    OR (l.span_10 IS NOT NULL AND l.span_10 <> 10)
 ORDER BY greatest(coalesce(l.span_3, 0), coalesce(l.span_5, 0)) DESC,
          l.asx_code;

-- ── How extreme are the stored rates on those rows? ─────────────────────────
-- A 3-year CAGR above ~60% a year is rare and real for a few companies; a
-- cluster of them among exactly the rows with broken windows is the signature
-- of the defect rather than of genuine compounding.

WITH series AS (
    SELECT asx_code, fiscal_year,
           row_number() OVER (PARTITION BY asx_code
                               ORDER BY fiscal_year DESC) AS recency,
           lag(fiscal_year, 3) OVER (PARTITION BY asx_code
                                      ORDER BY fiscal_year) AS prior_3
      FROM financials.annual_pnl
),
latest AS (
    SELECT asx_code, fiscal_year, fiscal_year - prior_3 AS span_3
      FROM series WHERE recency = 1 AND prior_3 IS NOT NULL
)
SELECT CASE WHEN l.span_3 = 3 THEN 'window correct'
            ELSE 'window broken' END                       AS cohort,
       count(*)                                            AS companies,
       count(m.revenue_cagr_3y)                            AS with_a_rate,
       round(avg(m.revenue_cagr_3y) * 100, 1)              AS mean_pct,
       round(max(m.revenue_cagr_3y) * 100, 1)              AS max_pct,
       count(*) FILTER (WHERE m.revenue_cagr_3y > 0.60)    AS above_60_pct
  FROM latest l
  JOIN screener.universe u
    ON u.asx_code = l.asx_code AND u.status = 'active'
  LEFT JOIN market.yearly_metrics m
    ON m.asx_code = l.asx_code AND m.fiscal_year = l.fiscal_year
 GROUP BY 1
 ORDER BY 1;
