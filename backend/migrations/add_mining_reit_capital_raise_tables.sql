-- ============================================================
-- Migration: Mining Metrics, REIT Metrics, Capital Raises
-- Run once on the database before deploying compute scripts.
-- ============================================================

-- ── Mining Metrics ────────────────────────────────────────────────────────────
-- Populated by compute/engine/mining_metrics.py (parses EODHD fundamentals
-- and quarterly report announcements for gold/copper/iron ore miners).

CREATE TABLE IF NOT EXISTS market.mining_metrics (
    asx_code            VARCHAR(10)   NOT NULL PRIMARY KEY REFERENCES market.companies(asx_code) ON DELETE CASCADE,

    -- Cost metrics (USD per oz / per tonne depending on commodity)
    aisc_per_oz         NUMERIC(10,2),   -- All-In Sustaining Cost (gold, silver) USD/oz
    cash_cost_per_oz    NUMERIC(10,2),   -- Cash cost USD/oz
    aisc_per_tonne      NUMERIC(10,2),   -- AISC for base metals USD/t

    -- Reserve & resource life
    ore_reserves_mt     NUMERIC(14,3),   -- Ore reserves (million tonnes)
    mineral_resources_mt NUMERIC(14,3),  -- Mineral resources (million tonnes)
    reserve_grade       NUMERIC(8,4),    -- Grade (g/t for gold, % for copper etc.)
    reserve_life_yrs    NUMERIC(6,1),    -- Mine/reserve life in years

    -- Production
    production_oz_ttm   NUMERIC(14,0),   -- Production trailing 12m (oz for precious metals)
    production_kt_ttm   NUMERIC(14,3),   -- Production trailing 12m (kt for base metals)
    production_guidance_low  NUMERIC(14,0),  -- Annual guidance lower bound
    production_guidance_high NUMERIC(14,0),  -- Annual guidance upper bound

    -- Capital & growth
    sustaining_capex_m  NUMERIC(10,2),   -- Sustaining capex AUD M
    growth_capex_m      NUMERIC(10,2),   -- Growth capex AUD M

    -- Commodity exposure (primary)
    primary_commodity   VARCHAR(50),     -- e.g. 'Gold', 'Copper', 'Iron Ore', 'Lithium'
    commodity_price_ref NUMERIC(12,2),   -- Spot price at last update (USD/oz or USD/t)

    -- Reporting period
    report_period       DATE,
    data_source         VARCHAR(50)  DEFAULT 'manual',
    updated_at          TIMESTAMPTZ  DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS mining_metrics_primary_commodity_idx
    ON market.mining_metrics(primary_commodity);


-- ── REIT Metrics ──────────────────────────────────────────────────────────────
-- Populated by compute/engine/reit_metrics.py (parses EODHD fundamentals
-- and half-year/annual results announcements).

CREATE TABLE IF NOT EXISTS market.reit_metrics (
    asx_code            VARCHAR(10)   NOT NULL PRIMARY KEY REFERENCES market.companies(asx_code) ON DELETE CASCADE,

    -- Funds From Operations
    ffo_per_unit        NUMERIC(10,4),   -- FFO per unit (AUD)
    affo_per_unit       NUMERIC(10,4),   -- Adjusted FFO per unit (AUD)
    price_to_ffo        NUMERIC(8,2),    -- P/FFO multiple

    -- Net Tangible Assets
    nta_per_unit        NUMERIC(10,4),   -- NTA per unit (AUD) — key REIT valuation metric
    premium_to_nta      NUMERIC(8,4),    -- (price - nta) / nta — negative = discount

    -- Portfolio metrics
    wale_yrs            NUMERIC(6,2),    -- Weighted average lease expiry (years)
    occupancy_pct       NUMERIC(6,2),    -- Portfolio occupancy %
    total_assets_bn     NUMERIC(12,3),   -- Total assets AUD B
    gla_sqm             NUMERIC(14,0),   -- Gross lettable area (sqm) for diversified/retail
    num_properties      INTEGER,         -- Number of properties in portfolio

    -- Income
    distribution_per_unit NUMERIC(10,4), -- DPU (distributions per unit, AUD)
    distribution_yield  NUMERIC(8,4),    -- Distribution yield (decimal, e.g. 0.055 = 5.5%)
    payout_of_ffo       NUMERIC(8,4),    -- Distribution / FFO

    -- Debt
    gearing_pct         NUMERIC(8,2),    -- Gearing % (debt / total assets)
    interest_cover      NUMERIC(8,2),    -- Interest coverage ratio

    -- Sector
    reit_sector         VARCHAR(50),     -- 'Office', 'Retail', 'Industrial', 'Diversified', 'Healthcare', 'Residential'

    -- Reporting period
    report_period       DATE,
    data_source         VARCHAR(50)  DEFAULT 'manual',
    updated_at          TIMESTAMPTZ  DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS reit_metrics_sector_idx
    ON market.reit_metrics(reit_sector);


-- ── Capital Raises ────────────────────────────────────────────────────────────
-- Populated by compute/engine/capital_raise_tracker.py (parses ASX
-- announcements for placement/SPP/entitlement offer keywords).

CREATE TABLE IF NOT EXISTS market.capital_raises (
    id                  BIGSERIAL     PRIMARY KEY,
    asx_code            VARCHAR(10)   NOT NULL REFERENCES market.companies(asx_code) ON DELETE CASCADE,

    -- Raise type
    raise_type          VARCHAR(30)   NOT NULL,  -- 'placement', 'spp', 'rights_issue', 'entitlement_offer', 'ipo', 'drp'

    -- Financial details (NULL = not disclosed / not yet parsed)
    amount_m            NUMERIC(12,2),            -- Total raise AUD M
    price_per_share     NUMERIC(10,4),            -- Issue price AUD
    shares_issued       BIGINT,                   -- New shares to be issued
    discount_pct        NUMERIC(6,2),             -- Discount to last close %

    -- Dates
    announcement_date   DATE          NOT NULL,
    record_date         DATE,
    settlement_date     DATE,

    -- Source
    announcement_id     VARCHAR(200),             -- EODHD/ASX announcement reference
    title               TEXT,                     -- Raw announcement headline
    url                 TEXT,

    -- De-dup guard
    UNIQUE(asx_code, announcement_date, raise_type)
);

CREATE INDEX IF NOT EXISTS capital_raises_asx_code_idx
    ON market.capital_raises(asx_code, announcement_date DESC);
CREATE INDEX IF NOT EXISTS capital_raises_date_idx
    ON market.capital_raises(announcement_date DESC);
