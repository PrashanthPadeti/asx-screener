-- Migration 054: Add profit-based signal columns to screener.universe
-- operating_margin_expanding: current OPM above 3Y average (margin expansion signal)
-- gross_margin_expanding:     current gross margin above 3Y average
-- fcf_conversion:             FCF / Net Profit ratio (real cash vs reported earnings)
-- eps_beats_revenue_growth:   EPS growth > revenue growth (operating leverage signal)
-- operating_leverage:         EBITDA growth minus revenue growth in pp (decimal)

ALTER TABLE screener.universe
    ADD COLUMN IF NOT EXISTS operating_margin_expanding BOOLEAN,
    ADD COLUMN IF NOT EXISTS gross_margin_expanding      BOOLEAN,
    ADD COLUMN IF NOT EXISTS fcf_conversion              DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS eps_beats_revenue_growth    BOOLEAN,
    ADD COLUMN IF NOT EXISTS operating_leverage          DOUBLE PRECISION;
