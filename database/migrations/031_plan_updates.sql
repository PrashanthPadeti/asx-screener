-- ─────────────────────────────────────────────────────────────
--  Migration 031 — Plan / Billing Updates
--  Adds billing_period, seat_limit columns to users.users
--  Updates plan values to support enterprise_pro / enterprise_premium
-- ─────────────────────────────────────────────────────────────

ALTER TABLE users.users
    ADD COLUMN IF NOT EXISTS billing_period VARCHAR(10) DEFAULT 'monthly',
    -- monthly | yearly
    ADD COLUMN IF NOT EXISTS seat_limit     SMALLINT    DEFAULT 1;
    -- 1 = individual, 5 or 10 = enterprise

-- Index for plan-based queries
CREATE INDEX IF NOT EXISTS idx_users_billing ON users.users(plan, billing_period);

-- ── Helper view for admin/manual user management ──────────────
CREATE OR REPLACE VIEW users.user_summary AS
SELECT
    id,
    email,
    name,
    plan,
    billing_period,
    seat_limit,
    subscription_status,
    subscription_ends_at,
    email_verified,
    created_at,
    last_login_at
FROM users.users
ORDER BY created_at DESC;
