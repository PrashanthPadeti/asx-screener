-- Migration 024: Pros/Cons text arrays on screener.universe
-- ===========================================================
-- Stores pre-computed bullish/bearish signals for each stock.
-- Populated by compute/engine/pros_cons.py after universe rebuild.
-- Enables display on company pages without client-side computation.
-- ===========================================================

ALTER TABLE screener.universe
    ADD COLUMN IF NOT EXISTS pros TEXT[] DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS cons TEXT[] DEFAULT '{}';

COMMENT ON COLUMN screener.universe.pros IS
    'Pre-computed bullish signals (array of plain-English strings)';
COMMENT ON COLUMN screener.universe.cons IS
    'Pre-computed bearish signals (array of plain-English strings)';
