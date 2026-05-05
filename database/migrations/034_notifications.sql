-- Migration 034: Notification Preferences, History, and Alert SMS support
-- ============================================================

-- Add SMS channel to alerts
ALTER TABLE users.alerts
    ADD COLUMN IF NOT EXISTS via_sms BOOLEAN DEFAULT FALSE;

-- ── Notification Preferences ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users.notification_preferences (
    user_id UUID PRIMARY KEY REFERENCES users.users(id) ON DELETE CASCADE,

    -- Portfolio notifications
    portfolio_weekly_email      BOOLEAN     DEFAULT TRUE,
    portfolio_threshold_email   BOOLEAN     DEFAULT TRUE,
    portfolio_threshold_sms     BOOLEAN     DEFAULT FALSE,
    portfolio_threshold_pct     DECIMAL(5,2) DEFAULT 5.0,  -- % change to trigger

    -- Alert notifications
    alerts_email   BOOLEAN DEFAULT TRUE,
    alerts_sms     BOOLEAN DEFAULT FALSE,

    -- Announcement notifications (market-sensitive only)
    announcements_email  BOOLEAN DEFAULT FALSE,
    announcements_sms    BOOLEAN DEFAULT FALSE,

    -- Contact
    phone_number    VARCHAR(20),
    phone_verified  BOOLEAN DEFAULT FALSE,

    -- Weekly report timing (AEST)
    weekly_report_day   SMALLINT DEFAULT 1,   -- 1=Monday
    weekly_report_hour  SMALLINT DEFAULT 8,   -- 8am
    timezone            VARCHAR(50) DEFAULT 'Australia/Sydney',

    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_notif_prefs_user ON users.notification_preferences(user_id);

-- ── Notification History ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users.notification_history (
    id                BIGSERIAL PRIMARY KEY,
    user_id           UUID NOT NULL REFERENCES users.users(id) ON DELETE CASCADE,
    channel           VARCHAR(20)  NOT NULL,  -- 'email', 'sms'
    notification_type VARCHAR(60)  NOT NULL,  -- 'price_alert', 'portfolio_weekly', 'portfolio_threshold', 'announcement'
    subject           VARCHAR(255),
    recipient         VARCHAR(255),           -- email address or phone number
    status            VARCHAR(20)  DEFAULT 'pending',  -- pending, sent, failed, delivered
    error_message     TEXT,
    metadata          JSONB        DEFAULT '{}',
    attempt_count     SMALLINT     DEFAULT 1,
    sent_at           TIMESTAMPTZ,
    created_at        TIMESTAMPTZ  DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_notif_history_user       ON users.notification_history(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_notif_history_status     ON users.notification_history(status) WHERE status = 'failed';
CREATE INDEX IF NOT EXISTS idx_notif_history_type       ON users.notification_history(notification_type, created_at DESC);

-- ── Portfolio Notification Tracking ───────────────────────────────────────────
-- Tracks last sent values so we can compute delta correctly
CREATE TABLE IF NOT EXISTS users.portfolio_notification_state (
    portfolio_id    UUID PRIMARY KEY REFERENCES users.portfolios(id) ON DELETE CASCADE,
    last_value      DECIMAL(18,2),
    last_notified_at TIMESTAMPTZ,
    weekly_sent_at  TIMESTAMPTZ
);

-- ── Announcement Subscriptions ────────────────────────────────────────────────
-- Users can subscribe to announcements for specific stocks (watchlist-based)
CREATE TABLE IF NOT EXISTS users.announcement_subscriptions (
    id          BIGSERIAL PRIMARY KEY,
    user_id     UUID NOT NULL REFERENCES users.users(id) ON DELETE CASCADE,
    asx_code    VARCHAR(10) NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, asx_code)
);

CREATE INDEX IF NOT EXISTS idx_ann_subs_user ON users.announcement_subscriptions(user_id);

-- Grant permissions
GRANT SELECT, INSERT, UPDATE, DELETE ON users.notification_preferences         TO asx_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON users.notification_history             TO asx_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON users.portfolio_notification_state     TO asx_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON users.announcement_subscriptions       TO asx_user;
GRANT USAGE, SELECT ON SEQUENCE users.notification_history_id_seq             TO asx_user;
GRANT USAGE, SELECT ON SEQUENCE users.announcement_subscriptions_id_seq       TO asx_user;
