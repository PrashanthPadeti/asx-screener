-- ─────────────────────────────────────────────────────────────
--  Migration 004 — Market Supplementary Tables
--  announcements · dividends · shareholding ·
--  substantial_holders · corporate_events
-- ─────────────────────────────────────────────────────────────

-- ── market.asx_announcements ──────────────────────────────────

CREATE TABLE market.asx_announcements (
    id                      BIGSERIAL PRIMARY KEY,
    asx_code                VARCHAR(10) NOT NULL,
    announced_at            TIMESTAMPTZ NOT NULL,
    headline                VARCHAR(500) NOT NULL,

    -- ASX classification
    asx_category            VARCHAR(100),
    asx_subcategory         VARCHAR(100),

    -- AI classification (Claude Haiku)
    ai_category             VARCHAR(50),
    -- earnings | capital_raise | director_change | operational |
    -- material_event | dividend | agm | guidance | quarterly_activity |
    -- investor_presentation | other
    ai_sentiment            VARCHAR(20),    -- positive | negative | neutral
    ai_materiality          SMALLINT,       -- 1–5 (5 = most material)
    ai_summary              TEXT,
    ai_key_points           JSONB,          -- ["point1", "point2"]

    -- Document
    document_url            VARCHAR(500),
    s3_key                  VARCHAR(500),
    page_count              INTEGER,

    -- Quick-filter flags
    is_price_sensitive      BOOLEAN DEFAULT FALSE,
    is_capital_raise        BOOLEAN DEFAULT FALSE,
    is_earnings             BOOLEAN DEFAULT FALSE,
    is_director_change      BOOLEAN DEFAULT FALSE,

    -- Capital raise detail (populated when is_capital_raise = TRUE)
    raise_type              VARCHAR(50),    -- placement | rights_issue | spp | entitlement_offer
    raise_amount_aud        NUMERIC(18,2),
    raise_price             NUMERIC(12,4),
    raise_discount_pct      NUMERIC(8,4),
    new_shares_issued       BIGINT,
    dilution_pct            NUMERIC(8,4),

    processed_at            TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_ann_asx_date     ON market.asx_announcements(asx_code, announced_at DESC);
CREATE INDEX idx_ann_date         ON market.asx_announcements(announced_at DESC);
CREATE INDEX idx_ann_category     ON market.asx_announcements(ai_category);
CREATE INDEX idx_ann_capital_raise ON market.asx_announcements(is_capital_raise)
    WHERE is_capital_raise = TRUE;
CREATE INDEX idx_ann_earnings     ON market.asx_announcements(is_earnings)
    WHERE is_earnings = TRUE;

-- ── market.dividends ─────────────────────────────────────────

CREATE TABLE market.dividends (
    id                      SERIAL PRIMARY KEY,
    asx_code                VARCHAR(10) NOT NULL,
    ex_date                 DATE NOT NULL,
    record_date             DATE,
    pay_date                DATE,
    declared_date           DATE,

    amount_per_share        NUMERIC(12,6) NOT NULL,  -- AUD
    currency                VARCHAR(3) DEFAULT 'AUD',
    franking_pct            NUMERIC(6,2) DEFAULT 0,  -- 0–100
    franking_credit_per_share NUMERIC(12,6),         -- computed: amt * (franking_pct/100) * (30/70)
    grossed_up_amount       NUMERIC(12,6),            -- computed: amt + franking_credit

    dividend_type           VARCHAR(30),              -- final | interim | special | drp
    is_drp_available        BOOLEAN DEFAULT FALSE,
    drp_price               NUMERIC(12,4),

    UNIQUE (asx_code, ex_date, dividend_type)
);

CREATE INDEX idx_div_asx_date ON market.dividends(asx_code, ex_date DESC);
CREATE INDEX idx_div_ex_date  ON market.dividends(ex_date DESC);

-- Automatically compute franking credit and grossed-up amount on insert/update
CREATE OR REPLACE FUNCTION compute_dividend_grossed_up()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
    corp_tax_rate NUMERIC := 0.30;
BEGIN
    IF NEW.franking_pct > 0 THEN
        NEW.franking_credit_per_share :=
            NEW.amount_per_share * (NEW.franking_pct / 100.0) * (corp_tax_rate / (1 - corp_tax_rate));
        NEW.grossed_up_amount :=
            NEW.amount_per_share + NEW.franking_credit_per_share;
    ELSE
        NEW.franking_credit_per_share := 0;
        NEW.grossed_up_amount := NEW.amount_per_share;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_dividend_grossed_up
    BEFORE INSERT OR UPDATE ON market.dividends
    FOR EACH ROW EXECUTE FUNCTION compute_dividend_grossed_up();

-- ── market.shareholding ──────────────────────────────────────

CREATE TABLE market.shareholding (
    id                      SERIAL PRIMARY KEY,
    asx_code                VARCHAR(10) NOT NULL,
    snapshot_date           DATE NOT NULL,

    director_pct            NUMERIC(8,4),
    substantial_holders_pct NUMERIC(8,4),
    institutional_pct       NUMERIC(8,4),
    retail_pct              NUMERIC(8,4),

    top1_holder_name        VARCHAR(255),
    top1_holder_pct         NUMERIC(8,4),
    top5_concentration_pct  NUMERIC(8,4),
    top20_concentration_pct NUMERIC(8,4),

    director_pct_change     NUMERIC(8,4),
    institutional_pct_change NUMERIC(8,4),

    UNIQUE (asx_code, snapshot_date)
);

CREATE INDEX idx_shareholding_asx ON market.shareholding(asx_code, snapshot_date DESC);

-- ── market.substantial_holders ───────────────────────────────

CREATE TABLE market.substantial_holders (
    id                      BIGSERIAL PRIMARY KEY,
    asx_code                VARCHAR(10) NOT NULL,
    holder_name             VARCHAR(255) NOT NULL,
    notice_date             DATE NOT NULL,
    notice_type             VARCHAR(50),   -- initial | change | cease
    shares_held             BIGINT,
    percentage_held         NUMERIC(8,4),
    prev_percentage         NUMERIC(8,4),
    change_pct              NUMERIC(8,4),
    consideration_paid      NUMERIC(18,2),
    is_director             BOOLEAN DEFAULT FALSE,
    source_document_url     VARCHAR(500),
    UNIQUE (asx_code, holder_name, notice_date)
);

CREATE INDEX idx_subholder_asx      ON market.substantial_holders(asx_code, notice_date DESC);
CREATE INDEX idx_subholder_name     ON market.substantial_holders(holder_name);
CREATE INDEX idx_subholder_director ON market.substantial_holders(is_director)
    WHERE is_director = TRUE;

-- ── market.corporate_events ───────────────────────────────────

CREATE TABLE market.corporate_events (
    id                      SERIAL PRIMARY KEY,
    asx_code                VARCHAR(10) NOT NULL,
    event_date              DATE NOT NULL,
    event_type              VARCHAR(50) NOT NULL,
    -- earnings_release | agm | capital_raise | record_date | ex_div |
    -- pay_date | listing | halt | suspension | split | consolidation |
    -- name_change | index_addition | index_removal
    description             VARCHAR(500),
    is_confirmed            BOOLEAN DEFAULT TRUE,
    source                  VARCHAR(100)
);

CREATE INDEX idx_events_asx_date ON market.corporate_events(asx_code, event_date);
CREATE INDEX idx_events_date     ON market.corporate_events(event_date);
CREATE INDEX idx_events_type     ON market.corporate_events(event_type);
