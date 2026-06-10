-- Add creator_plan to saved_screens for plan-based community screen filtering
ALTER TABLE screener.saved_screens
    ADD COLUMN IF NOT EXISTS creator_plan TEXT NOT NULL DEFAULT 'free';
