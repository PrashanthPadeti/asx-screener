-- ============================================================
-- Migration 043: Analyst-derived metrics + quality proxy scores
-- ============================================================
-- All computable from existing data — zero new data sources.
--
-- Analyst-derived (from existing analyst_ratings buy/sell/hold counts):
--   1. analyst_count            → screener.universe
--   2. analyst_buy_pct          → screener.universe
--   3. analyst_consensus_score  → screener.universe
--
-- Quality proxy scores (from existing yearly_metrics columns):
--   4. brand_proxy_score        → market.yearly_metrics + screener.universe
--   5. capital_efficiency_score → market.yearly_metrics + screener.universe
--   6. earnings_stability_score → market.yearly_metrics + screener.universe
--
-- Admin tags (manually maintained, enables qualitative filters):
--   7. business_model_tag       → market.companies + screener.universe
--   8. commodity_exposure       → market.companies + screener.universe
-- ============================================================

-- ── market.yearly_metrics ────────────────────────────────────────────────────

ALTER TABLE market.yearly_metrics
    ADD COLUMN IF NOT EXISTS brand_proxy_score          SMALLINT,
    ADD COLUMN IF NOT EXISTS capital_efficiency_score   SMALLINT,
    ADD COLUMN IF NOT EXISTS earnings_stability_score   SMALLINT;

COMMENT ON COLUMN market.yearly_metrics.brand_proxy_score
    IS 'Pricing power / moat proxy (0–3): +1 avg_roe_5y>15%, +1 avg_roic_5y>12%, +1 fcf_margin>10%.';
COMMENT ON COLUMN market.yearly_metrics.capital_efficiency_score
    IS 'Scalability / network-effect proxy (0–3): +1 revenue_cagr_5y>10%, +1 capex_intensity<5%, +1 roic>15%.';
COMMENT ON COLUMN market.yearly_metrics.earnings_stability_score
    IS 'Earnings predictability proxy (0–3): +1 eps_volatility_5y<0.20, +1 fcf_positive_years>=4, +1 revenue_cagr_5y>0.';


-- ── market.companies (admin-maintained tags) ─────────────────────────────────

ALTER TABLE market.companies
    ADD COLUMN IF NOT EXISTS business_model_tag  VARCHAR(50),
    ADD COLUMN IF NOT EXISTS commodity_exposure   VARCHAR(100);

COMMENT ON COLUMN market.companies.business_model_tag
    IS 'Admin-maintained business model classification: SaaS, Subscription, Mining, REIT, '
       'Services, Manufacturing, Retail, Infrastructure, Biotech, etc.';
COMMENT ON COLUMN market.companies.commodity_exposure
    IS 'Admin-maintained primary commodity exposure: Gold, Iron Ore, Lithium, Copper, Coal, '
       'Oil & Gas, Agriculture, Diversified, None, etc.';


-- ── screener.universe ─────────────────────────────────────────────────────────

ALTER TABLE screener.universe
    -- Analyst-derived
    ADD COLUMN IF NOT EXISTS analyst_count              SMALLINT,
    ADD COLUMN IF NOT EXISTS analyst_buy_pct            NUMERIC(5,4),
    ADD COLUMN IF NOT EXISTS analyst_consensus_score    NUMERIC(5,4),
    -- Proxy scores
    ADD COLUMN IF NOT EXISTS brand_proxy_score          SMALLINT,
    ADD COLUMN IF NOT EXISTS capital_efficiency_score   SMALLINT,
    ADD COLUMN IF NOT EXISTS earnings_stability_score   SMALLINT,
    -- Admin tags
    ADD COLUMN IF NOT EXISTS business_model_tag         VARCHAR(50),
    ADD COLUMN IF NOT EXISTS commodity_exposure          VARCHAR(100);

COMMENT ON COLUMN screener.universe.analyst_count
    IS 'Total analyst coverage count (strong_buy+buy+hold+sell+strong_sell).';
COMMENT ON COLUMN screener.universe.analyst_buy_pct
    IS 'Fraction of analysts with Buy or Strong Buy recommendation (0–1).';
COMMENT ON COLUMN screener.universe.analyst_consensus_score
    IS 'Weighted consensus score: (SB×2+B-S-SS×2)/total. Range -2 (bearish) to +2 (bullish).';
COMMENT ON COLUMN screener.universe.brand_proxy_score
    IS 'Pricing power proxy 0–3 (from yearly_metrics latest FY).';
COMMENT ON COLUMN screener.universe.capital_efficiency_score
    IS 'Scalability proxy 0–3 (from yearly_metrics latest FY).';
COMMENT ON COLUMN screener.universe.earnings_stability_score
    IS 'Earnings predictability proxy 0–3 (from yearly_metrics latest FY).';
COMMENT ON COLUMN screener.universe.business_model_tag
    IS 'Admin-maintained business model tag (from market.companies).';
COMMENT ON COLUMN screener.universe.commodity_exposure
    IS 'Admin-maintained commodity exposure tag (from market.companies).';
