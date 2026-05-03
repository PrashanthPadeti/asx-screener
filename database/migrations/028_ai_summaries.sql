-- Migration 028: AI Summaries cache table
-- Stores Claude-generated stock analysis, refreshed every 24h

CREATE TABLE IF NOT EXISTS market.ai_summaries (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asx_code        VARCHAR(10)  NOT NULL,
    verdict         TEXT,                     -- one-line investment verdict
    sentiment       VARCHAR(20),              -- bullish | bearish | neutral
    bull_case       JSONB        DEFAULT '[]',
    bear_case       JSONB        DEFAULT '[]',
    key_catalysts   JSONB        DEFAULT '[]',
    key_risks       JSONB        DEFAULT '[]',
    model_used      VARCHAR(60)  DEFAULT 'claude-3-5-haiku-20241022',
    generated_at    TIMESTAMPTZ  DEFAULT NOW(),
    CONSTRAINT ai_summaries_code_unique UNIQUE (asx_code)
);

CREATE INDEX IF NOT EXISTS idx_ai_summaries_code ON market.ai_summaries (asx_code);
CREATE INDEX IF NOT EXISTS idx_ai_summaries_generated ON market.ai_summaries (generated_at);
