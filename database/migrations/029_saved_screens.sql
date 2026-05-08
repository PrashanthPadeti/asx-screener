-- Migration 029: Saved screens
-- Users can save custom screener filters, share publicly or keep private

CREATE TABLE IF NOT EXISTS screener.saved_screens (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID        NOT NULL REFERENCES users.users(id) ON DELETE CASCADE,
    name         VARCHAR(120) NOT NULL,
    description  TEXT,
    filters      JSONB       NOT NULL DEFAULT '[]',
    sort_by      VARCHAR(60) NOT NULL DEFAULT 'market_cap',
    sort_dir     VARCHAR(4)  NOT NULL DEFAULT 'desc',
    is_public    BOOLEAN     NOT NULL DEFAULT FALSE,
    use_count    INTEGER     NOT NULL DEFAULT 0,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_saved_screens_user    ON screener.saved_screens (user_id);
CREATE INDEX IF NOT EXISTS idx_saved_screens_public  ON screener.saved_screens (is_public, use_count DESC) WHERE is_public = TRUE;
