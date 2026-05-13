-- ─────────────────────────────────────────────────────────────────────────────
--  Migration 046 — Market Cap Tier flags on screener.universe
--
--  Adds 6 boolean flag columns (is_mega, is_large, is_mid, is_small,
--  is_micro, is_nano) and properly populates the existing market_cap_tier
--  TEXT column — which was defined in 009 but never set by the universe build.
--
--  Thresholds (raw AUD dollars, matching screener.universe.market_cap):
--    Mega   ≥ $50B   : market_cap >= 50_000_000_000
--    Large  $10B–50B : market_cap >= 10_000_000_000 AND < 50_000_000_000
--    Mid    $2B–10B  : market_cap >= 2_000_000_000  AND < 10_000_000_000
--    Small  $300M–2B : market_cap >= 300_000_000    AND < 2_000_000_000
--    Micro  $50M–300M: market_cap >= 50_000_000     AND < 300_000_000
--    Nano   < $50M   : market_cap > 0               AND < 50_000_000
-- ─────────────────────────────────────────────────────────────────────────────

-- 1. Add all columns (idempotent — market_cap_tier may not exist in production)
ALTER TABLE screener.universe
    ADD COLUMN IF NOT EXISTS market_cap_tier TEXT,
    ADD COLUMN IF NOT EXISTS is_mega  BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS is_large BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS is_mid   BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS is_small BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS is_micro BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS is_nano  BOOLEAN NOT NULL DEFAULT FALSE;

-- 2. Backfill boolean flags + market_cap_tier TEXT from current market_cap
UPDATE screener.universe
SET
    is_mega  = (market_cap IS NOT NULL AND market_cap >= 50000000000),
    is_large = (market_cap IS NOT NULL AND market_cap >= 10000000000 AND market_cap < 50000000000),
    is_mid   = (market_cap IS NOT NULL AND market_cap >= 2000000000  AND market_cap < 10000000000),
    is_small = (market_cap IS NOT NULL AND market_cap >= 300000000   AND market_cap < 2000000000),
    is_micro = (market_cap IS NOT NULL AND market_cap >= 50000000    AND market_cap < 300000000),
    is_nano  = (market_cap IS NOT NULL AND market_cap > 0            AND market_cap < 50000000),
    market_cap_tier = CASE
        WHEN market_cap >= 50000000000                              THEN 'mega'
        WHEN market_cap >= 10000000000 AND market_cap < 50000000000 THEN 'large'
        WHEN market_cap >= 2000000000  AND market_cap < 10000000000 THEN 'mid'
        WHEN market_cap >= 300000000   AND market_cap < 2000000000  THEN 'small'
        WHEN market_cap >= 50000000    AND market_cap < 300000000   THEN 'micro'
        WHEN market_cap > 0                                         THEN 'nano'
        ELSE NULL
    END
WHERE market_cap IS NOT NULL;

-- 3. Partial indexes for fast cap-tier filtering
CREATE INDEX IF NOT EXISTS idx_universe_market_cap_tier ON screener.universe (market_cap_tier);
CREATE INDEX IF NOT EXISTS idx_universe_is_mega  ON screener.universe (is_mega)  WHERE is_mega  = TRUE;
CREATE INDEX IF NOT EXISTS idx_universe_is_large ON screener.universe (is_large) WHERE is_large = TRUE;
CREATE INDEX IF NOT EXISTS idx_universe_is_mid   ON screener.universe (is_mid)   WHERE is_mid   = TRUE;
CREATE INDEX IF NOT EXISTS idx_universe_is_small ON screener.universe (is_small) WHERE is_small = TRUE;
CREATE INDEX IF NOT EXISTS idx_universe_is_micro ON screener.universe (is_micro) WHERE is_micro = TRUE;
CREATE INDEX IF NOT EXISTS idx_universe_is_nano  ON screener.universe (is_nano)  WHERE is_nano  = TRUE;

-- 4. Verify
SELECT
    market_cap_tier,
    COUNT(*)      AS stocks,
    is_mega  OR is_large OR is_mid OR is_small OR is_micro OR is_nano AS flag_set
FROM screener.universe
WHERE market_cap IS NOT NULL AND market_cap > 0
GROUP BY 1, 3
ORDER BY MIN(market_cap) DESC NULLS LAST;
