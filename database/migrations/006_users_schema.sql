-- ─────────────────────────────────────────────────────────────
--  Migration 006 — users Schema
--  users · watchlists · portfolios · saved_screens · alerts
-- ─────────────────────────────────────────────────────────────

-- ── users.users ───────────────────────────────────────────────

CREATE TABLE users.users (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email                   VARCHAR(255) NOT NULL UNIQUE,
    name                    VARCHAR(255),
    avatar_url              VARCHAR(500),
    plan                    VARCHAR(20) NOT NULL DEFAULT 'free',
    -- free | pro | premium | enterprise

    -- Auth
    password_hash           VARCHAR(255),
    email_verified          BOOLEAN DEFAULT FALSE,
    email_verified_at       TIMESTAMPTZ,

    -- OAuth
    google_id               VARCHAR(100) UNIQUE,

    -- Billing
    stripe_customer_id      VARCHAR(100) UNIQUE,
    subscription_status     VARCHAR(30) DEFAULT 'inactive',
    subscription_ends_at    TIMESTAMPTZ,

    -- Preferences
    default_currency        VARCHAR(3) DEFAULT 'AUD',
    default_columns         JSONB,
    timezone                VARCHAR(50) DEFAULT 'Australia/Sydney',
    email_alerts_enabled    BOOLEAN DEFAULT TRUE,
    push_alerts_enabled     BOOLEAN DEFAULT TRUE,

    -- Usage limits
    screens_saved           INTEGER DEFAULT 0,
    screens_limit           INTEGER DEFAULT 10,
    watchlist_items         INTEGER DEFAULT 0,
    watchlist_limit         INTEGER DEFAULT 50,

    last_login_at           TIMESTAMPTZ,
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    updated_at              TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_users_email  ON users.users(email);
CREATE INDEX idx_users_stripe ON users.users(stripe_customer_id);
CREATE INDEX idx_users_plan   ON users.users(plan);

CREATE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON users.users
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ── users.watchlists & watchlist_items ────────────────────────

CREATE TABLE users.watchlists (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                 UUID NOT NULL REFERENCES users.users(id) ON DELETE CASCADE,
    name                    VARCHAR(100) NOT NULL,
    description             VARCHAR(500),
    is_public               BOOLEAN DEFAULT FALSE,
    public_slug             VARCHAR(100) UNIQUE,
    item_count              INTEGER DEFAULT 0,
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    updated_at              TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE users.watchlist_items (
    id                      BIGSERIAL PRIMARY KEY,
    watchlist_id            UUID NOT NULL REFERENCES users.watchlists(id) ON DELETE CASCADE,
    asx_code                VARCHAR(10) NOT NULL,
    added_at                TIMESTAMPTZ DEFAULT NOW(),
    notes                   TEXT,
    target_price            NUMERIC(12,4),
    sort_order              INTEGER DEFAULT 0,
    UNIQUE (watchlist_id, asx_code)
);

CREATE INDEX idx_watchlist_user   ON users.watchlists(user_id);
CREATE INDEX idx_wl_items_list    ON users.watchlist_items(watchlist_id);
CREATE INDEX idx_wl_items_asx     ON users.watchlist_items(asx_code);

-- ── users.portfolios & portfolio_transactions ─────────────────

CREATE TABLE users.portfolios (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                 UUID NOT NULL REFERENCES users.users(id) ON DELETE CASCADE,
    name                    VARCHAR(100) NOT NULL,
    description             VARCHAR(500),
    currency                VARCHAR(3) DEFAULT 'AUD',
    benchmark               VARCHAR(20) DEFAULT 'XJO',
    is_smsf                 BOOLEAN DEFAULT FALSE,
    created_at              TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE users.portfolio_transactions (
    id                      BIGSERIAL PRIMARY KEY,
    portfolio_id            UUID NOT NULL REFERENCES users.portfolios(id) ON DELETE CASCADE,
    asx_code                VARCHAR(10) NOT NULL,
    transaction_type        VARCHAR(20) NOT NULL,
    -- buy | sell | drp | split | consolidation | dividend | spinoff
    transaction_date        DATE NOT NULL,
    shares                  NUMERIC(18,4) NOT NULL,
    price_per_share         NUMERIC(12,4) NOT NULL,
    brokerage               NUMERIC(10,2) DEFAULT 0,
    total_cost              NUMERIC(18,2),
    notes                   VARCHAR(500),

    -- Dividend transactions
    franking_credit_amt     NUMERIC(10,4),
    is_drp                  BOOLEAN DEFAULT FALSE,

    created_at              TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_portfolio_user ON users.portfolios(user_id);
CREATE INDEX idx_ptxn_portfolio ON users.portfolio_transactions(portfolio_id, transaction_date DESC);
CREATE INDEX idx_ptxn_asx      ON users.portfolio_transactions(asx_code);

-- ── users.saved_screens ───────────────────────────────────────

CREATE TABLE users.saved_screens (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                 UUID NOT NULL REFERENCES users.users(id) ON DELETE CASCADE,
    name                    VARCHAR(200) NOT NULL,
    description             VARCHAR(1000),
    query_json              JSONB NOT NULL,    -- Structured filter list (source of truth)
    query_sql               TEXT,              -- Compiled SQL (cached, regenerated as needed)
    default_columns         JSONB,
    default_sort_col        VARCHAR(100),
    default_sort_dir        VARCHAR(4) DEFAULT 'DESC',

    -- Community sharing
    is_public               BOOLEAN DEFAULT FALSE,
    public_slug             VARCHAR(100) UNIQUE,
    tags                    TEXT[],
    likes_count             INTEGER DEFAULT 0,
    run_count               INTEGER DEFAULT 0,
    fork_of_screen_id       UUID REFERENCES users.saved_screens(id),

    -- Alert integration
    has_alert               BOOLEAN DEFAULT FALSE,
    last_run_at             TIMESTAMPTZ,
    last_result_count       INTEGER,

    created_at              TIMESTAMPTZ DEFAULT NOW(),
    updated_at              TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_screens_user   ON users.saved_screens(user_id);
CREATE INDEX idx_screens_public ON users.saved_screens(is_public, likes_count DESC)
    WHERE is_public = TRUE;
CREATE INDEX idx_screens_tags   ON users.saved_screens USING GIN(tags);
CREATE INDEX idx_screens_slug   ON users.saved_screens(public_slug)
    WHERE public_slug IS NOT NULL;

-- ── users.alerts & alert_triggers ────────────────────────────

CREATE TABLE users.alerts (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                 UUID NOT NULL REFERENCES users.users(id) ON DELETE CASCADE,
    alert_type              VARCHAR(30) NOT NULL,
    -- price_above | price_below | metric_above | metric_below |
    -- screen_match | screen_exit | new_announcement | earnings_released |
    -- ex_div | short_interest_above | short_interest_increase

    asx_code                VARCHAR(10),
    metric_key              VARCHAR(100),
    threshold_value         NUMERIC(18,4),
    screen_id               UUID REFERENCES users.saved_screens(id) ON DELETE CASCADE,

    via_email               BOOLEAN DEFAULT TRUE,
    via_push                BOOLEAN DEFAULT TRUE,
    is_active               BOOLEAN DEFAULT TRUE,
    repeat_mode             VARCHAR(20) DEFAULT 'every_time',
    -- once | every_time | daily_max

    last_triggered_at       TIMESTAMPTZ,
    trigger_count           INTEGER DEFAULT 0,
    created_at              TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE users.alert_triggers (
    id                      BIGSERIAL PRIMARY KEY,
    alert_id                UUID NOT NULL REFERENCES users.alerts(id) ON DELETE CASCADE,
    triggered_at            TIMESTAMPTZ DEFAULT NOW(),
    trigger_value           NUMERIC(18,4),   -- Actual value that triggered the alert
    trigger_data            JSONB,
    notification_sent       BOOLEAN DEFAULT FALSE,
    notification_sent_at    TIMESTAMPTZ
);

CREATE INDEX idx_alerts_user    ON users.alerts(user_id);
CREATE INDEX idx_alerts_active  ON users.alerts(is_active, asx_code) WHERE is_active = TRUE;
CREATE INDEX idx_alerts_screen  ON users.alerts(screen_id) WHERE screen_id IS NOT NULL;
CREATE INDEX idx_triggers_alert ON users.alert_triggers(alert_id, triggered_at DESC);

-- ── users.user_notes ─────────────────────────────────────────

CREATE TABLE users.user_notes (
    id          BIGSERIAL PRIMARY KEY,
    user_id     UUID NOT NULL REFERENCES users.users(id) ON DELETE CASCADE,
    asx_code    VARCHAR(10) NOT NULL,
    content     TEXT,
    updated_at  TIMESTAMPTZ DEFAULT NOW(),
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (user_id, asx_code)
);

-- ── users.user_custom_ratios ──────────────────────────────────

CREATE TABLE users.user_custom_ratios (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES users.users(id) ON DELETE CASCADE,
    name        VARCHAR(100) NOT NULL,
    formula     TEXT NOT NULL,
    description VARCHAR(500),
    is_public   BOOLEAN DEFAULT FALSE,
    validated   BOOLEAN DEFAULT FALSE,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (user_id, name)
);
