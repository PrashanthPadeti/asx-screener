-- ─────────────────────────────────────────────────────────────
-- 061 — multibagger_potential_score (MULTIBAGGER_POTENTIAL_V1)
-- ─────────────────────────────────────────────────────────────
-- A characteristics score, not a return prediction. It answers:
--   "How strongly does this business currently exhibit characteristics
--    associated with potential long-term compounders?"
-- It does NOT answer whether the stock will return 2x, 5x or 10x, and any
-- surface that exposes it must say so.
--
-- Component weights (V1):
--   growth               25%   sustained revenue/earnings expansion
--   capital_efficiency   20%   ROIC 60 / ROCE 40 — ability to compound capital
--   earnings_stability   15%   avoids rewarding erratic one-off growth
--   margin_expansion     15%   evidence of scalability / operating leverage
--   dilution             10%   penalises growth funded by repeated issuance
--   momentum             10%   market confirmation, deliberately not dominant
--   insider_alignment     5%   supporting signal only
--
-- Components are persisted alongside the score so that when the weights change
-- (e.g. momentum to 5%) historical scores stay reproducible and explainable.

ALTER TABLE screener.universe
    ADD COLUMN IF NOT EXISTS multibagger_potential_score        NUMERIC(5,1),
    ADD COLUMN IF NOT EXISTS multibagger_version                VARCHAR(32),
    ADD COLUMN IF NOT EXISTS mb_growth_component                NUMERIC(5,1),
    ADD COLUMN IF NOT EXISTS mb_capital_efficiency_component    NUMERIC(5,1),
    ADD COLUMN IF NOT EXISTS mb_earnings_stability_component    NUMERIC(5,1),
    ADD COLUMN IF NOT EXISTS mb_margin_expansion_component      NUMERIC(5,1),
    ADD COLUMN IF NOT EXISTS mb_dilution_component              NUMERIC(5,1),
    ADD COLUMN IF NOT EXISTS mb_momentum_component              NUMERIC(5,1),
    ADD COLUMN IF NOT EXISTS mb_insider_alignment_component     NUMERIC(5,1),
    -- Share of component weight that had usable data, after the eligibility
    -- rules passed. Lets a consumer judge how much to trust the score.
    ADD COLUMN IF NOT EXISTS mb_valid_weight_pct                NUMERIC(5,1);

COMMENT ON COLUMN screener.universe.multibagger_potential_score IS
    'MULTIBAGGER_POTENTIAL_V1 (0-100). Strength of compounding CHARACTERISTICS, '
    'not a prediction of returns. NULL when eligibility rules are unmet: growth '
    'component required, plus capital efficiency or earnings stability, plus at '
    'least 70% of component weight valid.';

COMMENT ON COLUMN screener.universe.mb_valid_weight_pct IS
    'Percentage of the 100% component weight that had usable data. 100 means '
    'every component contributed; 70 is the minimum for a published score.';

-- Ranking by this score over the whole universe is the intended use, so index it.
CREATE INDEX IF NOT EXISTS idx_universe_multibagger
    ON screener.universe (multibagger_potential_score DESC NULLS LAST)
    WHERE status = 'active';
