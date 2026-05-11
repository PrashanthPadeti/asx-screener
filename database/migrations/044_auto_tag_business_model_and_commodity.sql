-- ============================================================
-- Migration 044: Auto-tag business_model_tag + commodity_exposure
-- ============================================================
-- Rule-based population of the two admin tag columns added in Migration 043.
-- Source signals: gics_sector, gics_sub_industry (from EODHD fundamentals).
--
-- Coverage:
--   business_model_tag  → all sectors; NULL only for 'Other' sector with no sub-industry
--   commodity_exposure  → Materials + Energy stocks get commodity; all others → 'None'
--
-- Admin override: UPDATE market.companies SET business_model_tag = 'X'
--   WHERE asx_code = 'Y' AND is_current = TRUE
--   (this script uses WHERE business_model_tag IS NULL so manual fixes survive re-runs)
-- ============================================================


-- ── Step 1: business_model_tag ────────────────────────────────────────────────

UPDATE market.companies
SET business_model_tag = CASE

    -- ── Real Estate / REITs ─────────────────────────────────────────────────
    WHEN gics_sub_industry ILIKE '%reit%'                               THEN 'REIT'
    WHEN gics_sector = 'Real Estate'                                    THEN 'Real Estate'

    -- ── Financials ──────────────────────────────────────────────────────────
    WHEN gics_sub_industry ILIKE '%bank%'                               THEN 'Banking'
    WHEN gics_sub_industry ILIKE '%insurance%'                          THEN 'Insurance'
    WHEN gics_sector = 'Financials'                                     THEN 'Financial Services'

    -- ── Technology ──────────────────────────────────────────────────────────
    WHEN gics_sector = 'Technology'
         AND gics_sub_industry ILIKE '%software%'                       THEN 'SaaS'
    WHEN gics_sector = 'Technology'                                     THEN 'Technology'

    -- ── Communication Services ──────────────────────────────────────────────
    WHEN gics_sub_industry ILIKE '%telecom%'                            THEN 'Telco'
    WHEN gics_sub_industry ILIKE '%software%'
         AND gics_sector = 'Communication Services'                     THEN 'Technology'
    WHEN gics_sub_industry ILIKE '%internet%'
         AND gics_sector = 'Communication Services'                     THEN 'Technology'
    WHEN gics_sub_industry ILIKE '%interactive%'
         AND gics_sector = 'Communication Services'                     THEN 'Technology'
    WHEN gics_sub_industry ILIKE '%entertainment%'
         AND gics_sector = 'Communication Services'                     THEN 'Media'
    WHEN gics_sub_industry ILIKE '%media%'
         AND gics_sector = 'Communication Services'                     THEN 'Media'
    WHEN gics_sector = 'Communication Services'                         THEN 'Media'

    -- ── Healthcare ──────────────────────────────────────────────────────────
    WHEN gics_sub_industry ILIKE '%biotech%'                            THEN 'Biotech'
    WHEN gics_sub_industry ILIKE '%pharma%'                             THEN 'Biotech'
    WHEN gics_sector = 'Healthcare'                                     THEN 'Healthcare'

    -- ── Energy ──────────────────────────────────────────────────────────────
    WHEN gics_sector = 'Energy'
         AND gics_sub_industry ILIKE '%renewable%'                      THEN 'Infrastructure'
    WHEN gics_sector = 'Energy'
         AND gics_sub_industry IN (
             'Oil & Gas Equipment & Services',
             'Oil & Gas Storage & Transportation'
         )                                                              THEN 'Services'
    WHEN gics_sector = 'Energy'
         AND gics_sub_industry = 'Coal & Consumable Fuels'              THEN 'Mining'
    WHEN gics_sector = 'Energy'                                         THEN 'Oil & Gas'

    -- ── Materials ───────────────────────────────────────────────────────────
    WHEN gics_sector = 'Materials'
         AND gics_sub_industry IN (
             'Specialty Chemicals', 'Commodity Chemicals',
             'Diversified Chemicals', 'Fertilizers & Agricultural Chemicals',
             'Industrial Gases'
         )                                                              THEN 'Manufacturing'
    WHEN gics_sector = 'Materials'
         AND gics_sub_industry IN (
             'Paper & Plastic Packaging Products & Materials',
             'Forest Products', 'Paper Products',
             'Construction Materials', 'Aluminum'
         )                                                              THEN 'Manufacturing'
    WHEN gics_sector = 'Materials'                                      THEN 'Mining'

    -- ── Industrials ─────────────────────────────────────────────────────────
    WHEN gics_sub_industry ILIKE '%airline%'                            THEN 'Services'
    WHEN gics_sub_industry ILIKE '%airport%'                            THEN 'Infrastructure'
    WHEN gics_sub_industry ILIKE '%infrastructure%'                     THEN 'Infrastructure'
    WHEN gics_sub_industry ILIKE '%pipeline%'                           THEN 'Infrastructure'
    WHEN gics_sub_industry ILIKE '%railroad%'                           THEN 'Infrastructure'
    WHEN gics_sub_industry ILIKE '%port%'                               THEN 'Infrastructure'
    WHEN gics_sub_industry ILIKE '%construction%'                       THEN 'Construction'
    WHEN gics_sector = 'Industrials'                                    THEN 'Services'

    -- ── Consumer ────────────────────────────────────────────────────────────
    WHEN gics_sub_industry ILIKE '%retail%'                             THEN 'Retail'
    WHEN gics_sub_industry ILIKE '%restaurant%'                         THEN 'Retail'
    WHEN gics_sub_industry ILIKE '%hotel%'                              THEN 'Services'
    WHEN gics_sub_industry ILIKE '%casino%'                             THEN 'Services'
    WHEN gics_sub_industry ILIKE '%food%'                               THEN 'Manufacturing'
    WHEN gics_sub_industry ILIKE '%beverage%'                           THEN 'Manufacturing'
    WHEN gics_sector = 'Consumer Discretionary'                         THEN 'Services'
    WHEN gics_sector = 'Consumer Staples'                               THEN 'Retail'

    -- ── Utilities ───────────────────────────────────────────────────────────
    WHEN gics_sector = 'Utilities'                                      THEN 'Infrastructure'

    -- ── Fallback ────────────────────────────────────────────────────────────
    ELSE NULL

END
WHERE is_current = TRUE
  AND business_model_tag IS NULL;


-- ── Step 2: commodity_exposure ────────────────────────────────────────────────

UPDATE market.companies
SET commodity_exposure = CASE

    -- ── Specific sub-industries (Materials + Energy sectors) ─────────────────
    WHEN gics_sub_industry = 'Gold'
         OR gics_sub_industry ILIKE '%gold mining%'                     THEN 'Gold'
    WHEN gics_sub_industry = 'Silver'                                   THEN 'Silver'
    WHEN gics_sub_industry = 'Copper'                                   THEN 'Copper'
    WHEN gics_sub_industry = 'Aluminum'                                 THEN 'Aluminium'
    WHEN gics_sub_industry = 'Steel'                                    THEN 'Iron Ore'
    WHEN gics_sub_industry = 'Precious Metals & Minerals'               THEN 'Precious Metals'
    WHEN gics_sub_industry = 'Diversified Metals & Mining'              THEN 'Diversified'
    WHEN gics_sub_industry = 'Coal & Consumable Fuels'                  THEN 'Coal'
    WHEN gics_sub_industry ILIKE '%oil & gas%'                          THEN 'Oil & Gas'
    WHEN gics_sub_industry ILIKE '%oil%gas%'                            THEN 'Oil & Gas'
    WHEN gics_sub_industry ILIKE '%lithium%'                            THEN 'Lithium'
    WHEN gics_sub_industry ILIKE '%uranium%'                            THEN 'Uranium'
    WHEN gics_sub_industry ILIKE '%nickel%'                             THEN 'Nickel'
    WHEN gics_sub_industry = 'Fertilizers & Agricultural Chemicals'     THEN 'Agriculture'

    -- ── Sector-level fallbacks ────────────────────────────────────────────────
    WHEN gics_sector = 'Energy'
         AND gics_sub_industry = 'Renewable Electricity'                THEN 'None'
    WHEN gics_sector = 'Energy'                                         THEN 'Oil & Gas'
    WHEN gics_sector = 'Materials'
         AND gics_sub_industry IN (
             'Specialty Chemicals', 'Commodity Chemicals',
             'Diversified Chemicals', 'Industrial Gases',
             'Paper & Plastic Packaging Products & Materials',
             'Forest Products', 'Paper Products',
             'Construction Materials'
         )                                                              THEN 'None'
    WHEN gics_sector = 'Materials'                                      THEN 'Diversified'

    -- ── All other sectors ─────────────────────────────────────────────────────
    ELSE 'None'

END
WHERE is_current = TRUE
  AND commodity_exposure IS NULL;


-- ── Verify ────────────────────────────────────────────────────────────────────

SELECT
    business_model_tag,
    COUNT(*) AS companies
FROM market.companies
WHERE is_current = TRUE
GROUP BY 1
ORDER BY 2 DESC;

SELECT
    commodity_exposure,
    COUNT(*) AS companies
FROM market.companies
WHERE is_current = TRUE
GROUP BY 1
ORDER BY 2 DESC;
