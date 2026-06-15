-- Migration 056: Add cash flow signal columns to screener.universe
-- ocf_beats_net_income:            true when OCF >= Net Income (earnings quality gate)
-- capex_to_ocf:                    capex / OCF ratio (capex burden vs cash generation)
-- fcf_growing_faster_than_revenue: FCF growth 1Y > revenue growth 1Y (quality compounder signal)
-- ocf_positive:                    true when OCF > 0 (basic operating quality filter)
-- ocf_growing:                     true when OCF is higher than prior year

ALTER TABLE screener.universe
    ADD COLUMN IF NOT EXISTS ocf_beats_net_income            BOOLEAN,
    ADD COLUMN IF NOT EXISTS capex_to_ocf                    DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS fcf_growing_faster_than_revenue BOOLEAN,
    ADD COLUMN IF NOT EXISTS ocf_positive                    BOOLEAN,
    ADD COLUMN IF NOT EXISTS ocf_growing                     BOOLEAN;
