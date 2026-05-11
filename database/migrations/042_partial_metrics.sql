-- ============================================================
-- Migration 042: Partial metrics — pre-compute missing ratios
-- ============================================================
-- 3 metrics where component data existed but ratio not stored:
--   1. dollar_volume_avg_20d  → market.daily_metrics + screener.universe
--   2. asset_light_score      → market.yearly_metrics + screener.universe
--   3. avg_roic_3y            → market.yearly_metrics + screener.universe
--   4. avg_roic_5y            → market.yearly_metrics + screener.universe
-- ============================================================

-- ── market.daily_metrics ─────────────────────────────────────────────────────

ALTER TABLE market.daily_metrics
    ADD COLUMN IF NOT EXISTS dollar_volume_avg_20d NUMERIC(14,2);

COMMENT ON COLUMN market.daily_metrics.dollar_volume_avg_20d
    IS 'Average daily dollar turnover over 20 days (AUD millions): close × avg_volume_20d / 1,000,000. '
       'Primary liquidity risk filter — stocks < $0.5M/day are illiquid.';


-- ── market.yearly_metrics ────────────────────────────────────────────────────

ALTER TABLE market.yearly_metrics
    ADD COLUMN IF NOT EXISTS avg_roic_3y      NUMERIC(10,4),
    ADD COLUMN IF NOT EXISTS avg_roic_5y      NUMERIC(10,4),
    ADD COLUMN IF NOT EXISTS asset_light_score SMALLINT;

COMMENT ON COLUMN market.yearly_metrics.avg_roic_3y
    IS '3-year rolling average ROIC. Sustained >12-15% = durable competitive advantage.';
COMMENT ON COLUMN market.yearly_metrics.avg_roic_5y
    IS '5-year rolling average ROIC. Better signal for moat quality than single-year ROIC.';
COMMENT ON COLUMN market.yearly_metrics.asset_light_score
    IS 'Asset-light composite score 0-3: +1 if capex_intensity<5%, +1 if fcf_margin>10%, '
       '+1 if asset_turnover>0.5. Score 3 = highly asset-light (tech/software/services).';


-- ── screener.universe ─────────────────────────────────────────────────────────

ALTER TABLE screener.universe
    ADD COLUMN IF NOT EXISTS dollar_volume_avg_20d  NUMERIC(14,2),
    ADD COLUMN IF NOT EXISTS avg_roic_3y            NUMERIC(10,4),
    ADD COLUMN IF NOT EXISTS avg_roic_5y            NUMERIC(10,4),
    ADD COLUMN IF NOT EXISTS asset_light_score       SMALLINT;

COMMENT ON COLUMN screener.universe.dollar_volume_avg_20d
    IS 'Average daily dollar turnover in AUD millions (from daily_metrics latest date).';
COMMENT ON COLUMN screener.universe.avg_roic_3y
    IS '3-year average ROIC (from yearly_metrics latest FY).';
COMMENT ON COLUMN screener.universe.avg_roic_5y
    IS '5-year average ROIC (from yearly_metrics latest FY).';
COMMENT ON COLUMN screener.universe.asset_light_score
    IS 'Asset-light composite score 0-3 (from yearly_metrics latest FY).';
