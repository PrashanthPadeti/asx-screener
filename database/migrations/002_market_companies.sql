-- ─────────────────────────────────────────────────────────────
--  Migration 002 — market.companies (Master Reference Table)
-- ─────────────────────────────────────────────────────────────

CREATE TABLE market.companies (
    id                      SERIAL PRIMARY KEY,
    asx_code                VARCHAR(10)  NOT NULL UNIQUE,
    isin                    VARCHAR(12)  UNIQUE,
    company_name            VARCHAR(255) NOT NULL,
    short_name              VARCHAR(100),

    -- GICS Classification
    gics_sector             VARCHAR(100),
    gics_industry_group     VARCHAR(100),
    gics_industry           VARCHAR(100),
    gics_sub_industry       VARCHAR(100),
    asx_sector              VARCHAR(100),
    company_type            VARCHAR(50),   -- ordinary, reit, etf, lic, stapled

    -- ASX Index membership flags (updated quarterly)
    is_reit                 BOOLEAN DEFAULT FALSE,
    is_miner                BOOLEAN DEFAULT FALSE,
    is_bank                 BOOLEAN DEFAULT FALSE,
    is_insurer              BOOLEAN DEFAULT FALSE,
    is_asx20                BOOLEAN DEFAULT FALSE,
    is_asx50                BOOLEAN DEFAULT FALSE,
    is_asx100               BOOLEAN DEFAULT FALSE,
    is_asx200               BOOLEAN DEFAULT FALSE,
    is_asx300               BOOLEAN DEFAULT FALSE,
    is_all_ords             BOOLEAN DEFAULT FALSE,
    is_small_ords           BOOLEAN DEFAULT FALSE,

    -- Listing info
    listing_date            DATE,
    ipo_price               NUMERIC(12,4),
    delisting_date          DATE,
    delisting_reason        VARCHAR(100),
    status                  VARCHAR(20) DEFAULT 'active',  -- active, suspended, delisted

    -- Financial year end (month number; 6 = June for most ASX companies)
    financial_year_end      INTEGER DEFAULT 6,

    -- Share structure
    shares_outstanding      BIGINT,
    shares_float            BIGINT,
    face_value              NUMERIC(10,4),

    -- Company details
    website                 VARCHAR(255),
    abn                     VARCHAR(20),
    acn                     VARCHAR(20),
    domicile                VARCHAR(100) DEFAULT 'Australia',
    state                   VARCHAR(50),

    -- Miners only
    primary_commodity       VARCHAR(100),
    secondary_commodity     VARCHAR(100),

    -- Misc
    description             TEXT,
    logo_url                VARCHAR(500),
    employee_count          INTEGER,

    created_at              TIMESTAMPTZ DEFAULT NOW(),
    updated_at              TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_companies_asx_code    ON market.companies(asx_code);
CREATE INDEX idx_companies_status      ON market.companies(status);
CREATE INDEX idx_companies_gics_sector ON market.companies(gics_sector);
CREATE INDEX idx_companies_is_asx200   ON market.companies(is_asx200) WHERE is_asx200 = TRUE;
CREATE INDEX idx_companies_is_miner    ON market.companies(is_miner)  WHERE is_miner  = TRUE;
CREATE INDEX idx_companies_is_reit     ON market.companies(is_reit)   WHERE is_reit   = TRUE;

-- Trigram index for company name search / autocomplete
CREATE INDEX idx_companies_name_trgm ON market.companies
    USING GIN (company_name gin_trgm_ops);

-- Auto-update updated_at
CREATE TRIGGER trg_companies_updated_at
    BEFORE UPDATE ON market.companies
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ── market.index_membership ──────────────────────────────────
-- Tracks historical index composition changes (quarterly rebalances)

CREATE TABLE market.index_membership (
    id                      SERIAL PRIMARY KEY,
    asx_code                VARCHAR(10) NOT NULL,
    index_code              VARCHAR(20) NOT NULL,  -- XJO, XFL, XTO, etc.
    index_name              VARCHAR(100),
    effective_date          DATE NOT NULL,
    action                  VARCHAR(10) NOT NULL,  -- added, removed
    weight_pct              NUMERIC(8,4),
    UNIQUE (asx_code, index_code, effective_date, action)
);

CREATE INDEX idx_index_membership_code  ON market.index_membership(asx_code);
CREATE INDEX idx_index_membership_index ON market.index_membership(index_code, effective_date DESC);
