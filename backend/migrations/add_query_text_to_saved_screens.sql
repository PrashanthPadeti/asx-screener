-- Add query_text column to saved_screens for Query Mode saved queries
-- Existing rows get NULL (they are filter-based screens, not query-based)
ALTER TABLE screener.saved_screens
    ADD COLUMN IF NOT EXISTS query_text TEXT;
