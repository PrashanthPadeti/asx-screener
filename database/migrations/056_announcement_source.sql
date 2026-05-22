-- ============================================================
-- 056 — Add source_type + source_label to asx_announcements
-- ============================================================
-- source_type: 'asx_filing' | 'company_filing' | 'market_news'
-- source_label: human-readable label shown in the UI
-- ============================================================

ALTER TABLE market.asx_announcements
    ADD COLUMN IF NOT EXISTS source_type  VARCHAR(20)  DEFAULT 'market_news',
    ADD COLUMN IF NOT EXISTS source_label VARCHAR(80)  DEFAULT 'Finance News';

-- Backfill existing rows: guess from URL pattern
UPDATE market.asx_announcements
SET
    source_type  = CASE
        WHEN url ILIKE '%asx.com.au%' THEN 'asx_filing'
        WHEN document_type IS NOT NULL
         AND document_type NOT ILIKE '%general%'
         AND document_type NOT ILIKE '%news%'   THEN 'company_filing'
        ELSE 'market_news'
    END,
    source_label = CASE
        WHEN url ILIKE '%asx.com.au%'           THEN 'ASX'
        WHEN url ILIKE '%finance.yahoo.com%'    THEN 'Yahoo Finance'
        WHEN url ILIKE '%marketwatch.com%'      THEN 'MarketWatch'
        WHEN url ILIKE '%reuters.com%'          THEN 'Reuters'
        WHEN url ILIKE '%bloomberg.com%'        THEN 'Bloomberg'
        WHEN url ILIKE '%afr.com%'              THEN 'AFR'
        WHEN url ILIKE '%smh.com.au%'           THEN 'SMH'
        WHEN url ILIKE '%theaustralian.com.au%' THEN 'The Australian'
        WHEN url ILIKE '%abc.net.au%'           THEN 'ABC News'
        WHEN url ILIKE '%fool.com%'             THEN 'Motley Fool'
        WHEN url ILIKE '%benzinga.com%'         THEN 'Benzinga'
        WHEN url ILIKE '%seekingalpha.com%'     THEN 'Seeking Alpha'
        WHEN document_type IS NOT NULL
         AND document_type NOT ILIKE '%general%'
         AND document_type NOT ILIKE '%news%'   THEN 'Company Filing'
        ELSE 'Finance News'
    END
WHERE source_type = 'market_news';   -- only touch the default rows

-- Index for filtering by source_type
CREATE INDEX IF NOT EXISTS idx_asx_announcements_source_type
    ON market.asx_announcements (source_type, released_at DESC);
