-- Migration 029: Anomaly flags table
-- Stores unusual stock patterns detected by compute/engine/anomaly_detect.py

CREATE TABLE IF NOT EXISTS market.anomalies (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    asx_code     VARCHAR(10) NOT NULL,
    flag_type    VARCHAR(60) NOT NULL,   -- e.g. PRICE_EARNINGS_DIVERGENCE
    description  TEXT        NOT NULL,   -- human-readable explanation
    severity     VARCHAR(10) DEFAULT 'medium', -- low | medium | high
    is_active    BOOLEAN     DEFAULT TRUE,
    detected_at  TIMESTAMPTZ DEFAULT NOW(),
    resolved_at  TIMESTAMPTZ,
    CONSTRAINT anomalies_code_type_unique UNIQUE (asx_code, flag_type)
);

CREATE INDEX IF NOT EXISTS idx_anomalies_code    ON market.anomalies (asx_code);
CREATE INDEX IF NOT EXISTS idx_anomalies_active  ON market.anomalies (is_active) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_anomalies_type    ON market.anomalies (flag_type);
