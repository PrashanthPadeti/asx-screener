-- ============================================================
-- Migration 046 — AlphaFive: switch from monthly to weekly picks
-- pick_month column now stores the Monday of each week
-- ============================================================

-- Update views to reflect weekly cadence
-- (table and column names unchanged for backward compatibility)

DROP VIEW IF EXISTS strategy.current_picks;
DROP VIEW IF EXISTS strategy.recent_picks;

-- Current week: picks for the Monday of the current week
CREATE OR REPLACE VIEW strategy.current_picks AS
SELECT *
FROM strategy.monthly_picks
WHERE pick_month = (DATE_TRUNC('week', CURRENT_DATE))::DATE
ORDER BY rank;

-- Recent 12 weeks of picks
CREATE OR REPLACE VIEW strategy.recent_picks AS
SELECT *
FROM strategy.monthly_picks
WHERE pick_month >= (DATE_TRUNC('week', CURRENT_DATE) - INTERVAL '11 weeks')::DATE
ORDER BY pick_month DESC, rank;

-- Update table comment
COMMENT ON TABLE strategy.monthly_picks IS
  'Weekly top-5 picks from ASX200 ranked by composite factor score (AlphaFive strategy). '
  'pick_month stores the Monday date of each week.';

COMMENT ON COLUMN strategy.monthly_picks.pick_month IS
  'Monday of the week for which these picks were computed (e.g. 2026-05-19 = week of 19 May 2026).';
