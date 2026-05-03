-- Migration 026 — ASX Announcements
-- Stores company announcements fetched daily from the public ASX API.
-- Indexed for fast per-company chronological lookup.

CREATE TABLE IF NOT EXISTS market.asx_announcements (
    id               SERIAL PRIMARY KEY,
    asx_code         TEXT        NOT NULL,
    announcement_id  TEXT        NOT NULL,   -- ASX-assigned document ID
    released_at      TIMESTAMPTZ,            -- document_release_date (with timezone)
    document_date    DATE,                   -- date on document itself
    title            TEXT,                   -- announcement header/subject
    document_type    TEXT,                   -- e.g. "Quarterly Activities Report"
    url              TEXT,                   -- full PDF URL on asx.com.au
    market_sensitive BOOLEAN     DEFAULT false,
    price_sensitive  BOOLEAN     DEFAULT false,
    num_pages        INT,
    file_size_kb     INT,
    created_at       TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (asx_code, announcement_id)
);

CREATE INDEX IF NOT EXISTS idx_ann_code_date
    ON market.asx_announcements (asx_code, released_at DESC NULLS LAST);

CREATE INDEX IF NOT EXISTS idx_ann_sensitive
    ON market.asx_announcements (released_at DESC NULLS LAST)
    WHERE market_sensitive = true;

CREATE INDEX IF NOT EXISTS idx_ann_type
    ON market.asx_announcements (asx_code, document_type);

GRANT SELECT, INSERT, UPDATE ON market.asx_announcements TO asx_user;
GRANT USAGE, SELECT ON SEQUENCE market.asx_announcements_id_seq TO asx_user;

COMMENT ON TABLE market.asx_announcements IS
    'ASX company announcements fetched daily from the public ASX API (asx.com.au).';
COMMENT ON COLUMN market.asx_announcements.announcement_id IS
    'ASX-assigned document ID — unique per company announcement.';
COMMENT ON COLUMN market.asx_announcements.market_sensitive IS
    'True when ASX flagged this announcement as market-sensitive.';
COMMENT ON COLUMN market.asx_announcements.price_sensitive IS
    'True when ASX flagged this announcement as price-sensitive (subset of market_sensitive).';
