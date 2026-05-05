-- Migration 033: Subscription retention tracking + audit log
-- Adds columns for 12-month data deletion policy and audit trail

-- ── Retention columns on users.users ─────────────────────────────────────────

ALTER TABLE users.users
    ADD COLUMN IF NOT EXISTS subscription_inactive_since TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS data_deletion_scheduled_at  TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS deletion_reminder_30d_sent  BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS deletion_reminder_7d_sent   BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS deletion_reminder_1d_sent   BOOLEAN DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_users_deletion_scheduled
    ON users.users (data_deletion_scheduled_at)
    WHERE data_deletion_scheduled_at IS NOT NULL;

-- ── Subscription events audit table ──────────────────────────────────────────

CREATE TABLE IF NOT EXISTS users.subscription_events (
    id               BIGSERIAL    PRIMARY KEY,
    user_id          UUID         NOT NULL REFERENCES users.users(id) ON DELETE CASCADE,
    event_type       VARCHAR(50)  NOT NULL,   -- activated | cancelled | past_due | upgraded | downgraded | restored
    old_plan         VARCHAR(30),
    new_plan         VARCHAR(30),
    stripe_event_id  VARCHAR(100),
    metadata         JSONB,
    created_at       TIMESTAMPTZ  DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sub_events_user ON users.subscription_events (user_id, created_at DESC);

-- ── Admin summary view ────────────────────────────────────────────────────────

CREATE OR REPLACE VIEW users.subscription_summary AS
SELECT
    u.id,
    u.email,
    u.name,
    u.plan,
    u.subscription_status,
    u.subscription_ends_at,
    u.billing_period,
    u.stripe_customer_id,
    u.subscription_inactive_since,
    u.data_deletion_scheduled_at,
    u.created_at,
    u.last_login_at,
    CASE
        WHEN u.data_deletion_scheduled_at IS NOT NULL
         AND u.data_deletion_scheduled_at <= NOW() + INTERVAL '30 days'
        THEN TRUE ELSE FALSE
    END AS deletion_imminent
FROM users.users u;

-- ── Cleanup function (called by scheduled job or admin) ───────────────────────
-- Deletes premium-tier data for users inactive > 12 months.
-- Portfolios, alerts, and saved screens are removed.
-- Watchlists are trimmed to free tier limit (50 items).
-- Core account (email, name, login history) is preserved.

CREATE OR REPLACE FUNCTION users.delete_expired_premium_data()
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE
    deleted_users INTEGER := 0;
    u             RECORD;
BEGIN
    FOR u IN
        SELECT id, email
        FROM users.users
        WHERE data_deletion_scheduled_at IS NOT NULL
          AND data_deletion_scheduled_at <= NOW()
          AND plan = 'free'
    LOOP
        -- Delete portfolios + transactions (cascade)
        DELETE FROM users.portfolios WHERE user_id = u.id;

        -- Delete alerts
        DELETE FROM users.alerts WHERE user_id = u.id;

        -- Trim watchlist items beyond free limit (keep 50 most recent)
        DELETE FROM users.watchlist_stocks ws
        WHERE ws.watchlist_id IN (
            SELECT id FROM users.watchlists WHERE user_id = u.id
        )
        AND ws.id NOT IN (
            SELECT ws2.id FROM users.watchlist_stocks ws2
            JOIN users.watchlists w ON w.id = ws2.watchlist_id
            WHERE w.user_id = u.id
            ORDER BY ws2.created_at DESC
            LIMIT 50
        );

        -- Clear deletion schedule (data is gone)
        UPDATE users.users
        SET data_deletion_scheduled_at = NULL,
            subscription_inactive_since = NULL
        WHERE id = u.id;

        -- Log the deletion event
        INSERT INTO users.subscription_events (user_id, event_type, old_plan, new_plan, metadata)
        VALUES (u.id, 'data_deleted', 'free', 'free', jsonb_build_object('reason', 'retention_12m'));

        deleted_users := deleted_users + 1;
    END LOOP;

    RETURN deleted_users;
END;
$$;
