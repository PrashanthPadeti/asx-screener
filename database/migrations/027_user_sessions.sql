-- ─────────────────────────────────────────────────────────────
--  Migration 027 — User Sessions (Refresh Tokens)
--  Adds users.sessions for opaque refresh token storage.
--  users.users already exists from migration 006.
-- ─────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS users.sessions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users.users(id) ON DELETE CASCADE,
    refresh_token   VARCHAR(512) NOT NULL UNIQUE,   -- opaque UUID token
    user_agent      VARCHAR(500),
    ip_address      INET,
    expires_at      TIMESTAMPTZ NOT NULL,
    revoked         BOOLEAN DEFAULT FALSE,
    revoked_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_sessions_user    ON users.sessions(user_id);
CREATE INDEX idx_sessions_token   ON users.sessions(refresh_token) WHERE NOT revoked;
CREATE INDEX idx_sessions_expires ON users.sessions(expires_at)    WHERE NOT revoked;
