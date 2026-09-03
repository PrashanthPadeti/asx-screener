-- ─────────────────────────────────────────────────────────────
-- 062 — Margin expansion magnitude
-- ─────────────────────────────────────────────────────────────
-- The existing gross_margin_expanding / operating_margin_expanding booleans
-- were NULL for every stock because they compared computed_metrics.gpm/opm
-- (current period) against the yearly average, and those current-period margin
-- columns are unpopulated. The historical averages they needed were present all
-- along in market.yearly_metrics.
--
-- Two problems with a boolean alone, beyond the broken dependency:
--   19.9% -> 20.0%  (+0.1pp) and 12% -> 20% (+8.0pp) are both merely "true",
--   yet only one is evidence of operating leverage.
-- So the magnitude is stored, and the flag derived from it.
--
-- V1 definition: 3-year average minus 5-year average, in percentage points.
-- The windows overlap — the 5Y average already contains the latest three years
-- — so this understates the true change. It is a directionally sound proxy, not
-- a clean before/after. A later version comparing years 0-2 against years 3-4
-- would be sharper, and needs per-year margin history rather than the averages.
--
-- NULL propagates deliberately: a missing average yields a NULL magnitude and a
-- NULL flag, never a manufactured 0 that would read as "no expansion".

ALTER TABLE screener.universe
    ADD COLUMN IF NOT EXISTS gross_margin_expansion     NUMERIC(10,4),
    ADD COLUMN IF NOT EXISTS operating_margin_expansion NUMERIC(10,4);

COMMENT ON COLUMN screener.universe.gross_margin_expansion IS
    'avg_gross_margin_3y - avg_gross_margin_5y, in percentage points. Positive '
    'means the recent three years averaged a higher gross margin than the five '
    'year window. NULL when either average is missing.';

COMMENT ON COLUMN screener.universe.operating_margin_expansion IS
    'avg_operating_margin_3y - avg_operating_margin_5y, in percentage points. '
    'NULL when either average is missing.';
