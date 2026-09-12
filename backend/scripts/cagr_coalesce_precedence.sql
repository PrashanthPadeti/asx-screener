-- Which computation actually reaches the user?
-- ============================================
-- build_screener_universe serves
--
--     COALESCE(cm.revenue_growth_3y, ym.revenue_cagr_3y) AS revenue_growth_3y_cagr
--     COALESCE(cm.profit_growth_3y,  ym.net_income_cagr_3y) AS earnings_growth_3y_cagr
--
-- and peg_ratio divides by the second of those. So the exact-horizon fix to
-- yearly_compute.cn() reaches the served column only where cm is null.
--
-- The two sides are not the same metric under two names:
--
--   ym.revenue_cagr_3y     yearly_compute.cn("revenue", 3). As of V2, requires
--                          an observation at fiscal year Y-3 exactly.
--
--   cm.revenue_growth_3y   daily_compute.calc_growth(revenues, 3), where
--                          revenues = [p["revenue"] for p in pnl if p["revenue"]]
--                          and the base is values[3] — three POSITIONS back in
--                          a list that has already dropped every year whose
--                          revenue was null or zero. Positional like the old
--                          cn(), and compacted on top, so the base year is
--                          unbounded and unrecorded.
--
-- cm is therefore strictly the weaker implementation, and COALESCE gives it
-- precedence. This measures how much of the served universe that governs.
--
--     sudo -u postgres psql -d asx_screener -f scripts/cagr_coalesce_precedence.sql
--
-- Read-only.

\pset format aligned
\pset null '—'

-- ── Precedence: who wins, and how often ─────────────────────────────────────

WITH latest AS (
    SELECT u.asx_code,
           cm.revenue_growth_3y  AS cm_rev,
           ym.revenue_cagr_3y    AS ym_rev,
           cm.profit_growth_3y   AS cm_profit,
           ym.net_income_cagr_3y AS ym_profit
      FROM screener.universe u
      LEFT JOIN LATERAL (
          SELECT revenue_growth_3y, profit_growth_3y
            FROM market.computed_metrics
           WHERE asx_code = u.asx_code
           ORDER BY time DESC LIMIT 1
      ) cm ON TRUE
      LEFT JOIN LATERAL (
          SELECT revenue_cagr_3y, net_income_cagr_3y
            FROM market.yearly_metrics
           WHERE asx_code = u.asx_code
           ORDER BY fiscal_year DESC LIMIT 1
      ) ym ON TRUE
     WHERE u.status = 'active'
)
SELECT 'revenue_growth_3y_cagr'                                   AS served_column,
       count(*)                                                   AS active_rows,
       count(cm_rev)                                              AS cm_present,
       count(ym_rev)                                              AS ym_present,
       count(*) FILTER (WHERE cm_rev IS NOT NULL
                          AND ym_rev IS NOT NULL)                  AS both,
       count(*) FILTER (WHERE cm_rev IS NOT NULL)                  AS cm_wins,
       count(*) FILTER (WHERE cm_rev IS NULL
                          AND ym_rev IS NOT NULL)                  AS ym_used,
       count(*) FILTER (WHERE cm_rev IS NULL AND ym_rev IS NULL)   AS neither
  FROM latest
UNION ALL
SELECT 'earnings_growth_3y_cagr',
       count(*),
       count(cm_profit),
       count(ym_profit),
       count(*) FILTER (WHERE cm_profit IS NOT NULL
                          AND ym_profit IS NOT NULL),
       count(*) FILTER (WHERE cm_profit IS NOT NULL),
       count(*) FILTER (WHERE cm_profit IS NULL
                          AND ym_profit IS NOT NULL),
       count(*) FILTER (WHERE cm_profit IS NULL AND ym_profit IS NULL)
  FROM latest;

-- ── Do the two implementations agree where both exist? ──────────────────────
-- Diagnostic only. Agreement does not establish shared semantics — two
-- implementations can coincide numerically and both be wrong — but wide
-- disagreement proves they are not interchangeable, which is what an
-- unexamined COALESCE assumes.

WITH latest AS (
    SELECT u.asx_code,
           cm.revenue_growth_3y AS cm_rev,
           ym.revenue_cagr_3y   AS ym_rev
      FROM screener.universe u
      LEFT JOIN LATERAL (
          SELECT revenue_growth_3y FROM market.computed_metrics
           WHERE asx_code = u.asx_code ORDER BY time DESC LIMIT 1
      ) cm ON TRUE
      LEFT JOIN LATERAL (
          SELECT revenue_cagr_3y FROM market.yearly_metrics
           WHERE asx_code = u.asx_code ORDER BY fiscal_year DESC LIMIT 1
      ) ym ON TRUE
     WHERE u.status = 'active'
       AND cm.revenue_growth_3y IS NOT NULL
       AND ym.revenue_cagr_3y   IS NOT NULL
)
SELECT count(*)                                                   AS comparable,
       count(*) FILTER (WHERE abs(cm_rev - ym_rev) < 0.005)        AS agree_within_half_pp,
       count(*) FILTER (WHERE abs(cm_rev - ym_rev) >= 0.05)        AS differ_5pp_or_more,
       count(*) FILTER (WHERE abs(cm_rev - ym_rev) >= 0.20)        AS differ_20pp_or_more,
       round(max(abs(cm_rev - ym_rev)) * 100, 1)                   AS worst_gap_pp
  FROM latest;

-- ── The widest disagreements, named ─────────────────────────────────────────
-- Where the two differ most, the served value is whichever cm happened to
-- produce. These are the rows where the COALESCE is making a silent choice
-- that materially changes what a user sees.

WITH latest AS (
    SELECT u.asx_code, u.company_name,
           cm.revenue_growth_3y AS cm_rev,
           ym.revenue_cagr_3y   AS ym_rev
      FROM screener.universe u
      LEFT JOIN LATERAL (
          SELECT revenue_growth_3y FROM market.computed_metrics
           WHERE asx_code = u.asx_code ORDER BY time DESC LIMIT 1
      ) cm ON TRUE
      LEFT JOIN LATERAL (
          SELECT revenue_cagr_3y FROM market.yearly_metrics
           WHERE asx_code = u.asx_code ORDER BY fiscal_year DESC LIMIT 1
      ) ym ON TRUE
     WHERE u.status = 'active'
       AND cm.revenue_growth_3y IS NOT NULL
       AND ym.revenue_cagr_3y   IS NOT NULL
)
SELECT asx_code, company_name,
       round(cm_rev * 100, 1) AS cm_served_pct,
       round(ym_rev * 100, 1) AS ym_ignored_pct,
       round((cm_rev - ym_rev) * 100, 1) AS gap_pp
  FROM latest
 ORDER BY abs(cm_rev - ym_rev) DESC
 LIMIT 15;
