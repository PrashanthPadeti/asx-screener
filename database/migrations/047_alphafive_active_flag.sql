-- ============================================================
-- Migration 047 — AlphaFive: add is_active flag to monthly_picks
-- Only the current week's picks are marked is_active = TRUE
-- All historical picks remain in the table with is_active = FALSE
-- ============================================================

ALTER TABLE strategy.monthly_picks
    ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT FALSE;

-- Mark the latest week as active
UPDATE strategy.monthly_picks
SET is_active = TRUE
WHERE pick_month = (SELECT MAX(pick_month) FROM strategy.monthly_picks);

-- Index for fast active-only queries
CREATE INDEX IF NOT EXISTS idx_monthly_picks_active
    ON strategy.monthly_picks (is_active)
    WHERE is_active = TRUE;

-- Update current_picks view to use the flag
CREATE OR REPLACE VIEW strategy.current_picks AS
SELECT *
FROM strategy.monthly_picks
WHERE is_active = TRUE
ORDER BY rank;

COMMENT ON COLUMN strategy.monthly_picks.is_active IS
  'TRUE for the current week''s picks only. All other weeks are FALSE (kept as history).';
