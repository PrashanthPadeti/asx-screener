-- Migration 057: Founding Members promotion tracking
-- First 100 paying subscribers get extended access:
--   Monthly → 6 months access
--   Annual  → 3 years access
-- ─────────────────────────────────────────────────────────────────────────────

ALTER TABLE users.users
    ADD COLUMN IF NOT EXISTS is_founding_member      BOOLEAN     NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS founding_member_number  INT         DEFAULT NULL;

-- Ensure founding_member_number is unique (only non-null values, so UNIQUE partial index)
CREATE UNIQUE INDEX IF NOT EXISTS ux_founding_member_number
    ON users.users (founding_member_number)
    WHERE founding_member_number IS NOT NULL;

-- Index for fast count queries in the founding member status endpoint
CREATE INDEX IF NOT EXISTS ix_users_is_founding_member
    ON users.users (is_founding_member)
    WHERE is_founding_member = TRUE;

COMMENT ON COLUMN users.users.is_founding_member     IS 'TRUE for the first 100 paying subscribers who received extended founding-member access';
COMMENT ON COLUMN users.users.founding_member_number IS 'Sequential slot number 1-100 assigned at subscription time';
