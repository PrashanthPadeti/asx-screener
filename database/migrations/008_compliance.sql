-- ─────────────────────────────────────────────────────────────
--  Migration 008 — Compliance & Legal
--  • marketing_emails_enabled column (Spam Act 2003)
--  • users.audit_log (NDB scheme / Privacy Act 1988)
--  • users.unsubscribe_tokens (one-click Spam Act unsubscribe)
-- ─────────────────────────────────────────────────────────────

-- ── 1. Add marketing_emails_enabled to users.users ───────────
--  Separate from email_alerts_enabled (transactional) so we
--  comply with Spam Act 2003: marketing consent must be explicit,
--  defaults to FALSE (opt-in only).

ALTER TABLE users.users
    ADD COLUMN IF NOT EXISTS marketing_emails_enabled BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN users.users.marketing_emails_enabled IS
    'Spam Act 2003: explicit consent for marketing/product-update emails. '
    'Transactional emails (alerts, receipts, resets) use email_alerts_enabled.';

-- ── 2. Audit log ─────────────────────────────────────────────
--  Records sensitive operations for Privacy Act NDB compliance
--  and internal security monitoring.

CREATE TABLE IF NOT EXISTS users.audit_log (
    id              BIGSERIAL PRIMARY KEY,
    user_id         UUID REFERENCES users.users(id) ON DELETE SET NULL,
    -- NULL = system/unauthenticated action
    action          VARCHAR(100) NOT NULL,
    -- Examples:
    --   auth.login_success | auth.login_failed | auth.logout
    --   auth.password_reset_requested | auth.password_changed
    --   auth.email_verified
    --   account.email_changed | account.name_changed
    --   account.delete_requested | account.deleted
    --   subscription.upgraded | subscription.cancelled | subscription.payment_failed
    --   prefs.alerts_toggled | prefs.marketing_toggled
    --   data.export_csv
    --   admin.user_viewed | admin.plan_overridden
    entity_type     VARCHAR(50),   -- e.g. 'user', 'subscription', 'alert'
    entity_id       VARCHAR(100),  -- UUID or other ID of the affected entity
    old_value       JSONB,         -- State before the change (PII-scrubbed)
    new_value       JSONB,         -- State after the change (PII-scrubbed)
    ip_address_hash VARCHAR(64),   -- SHA-256 hash of client IP (never raw IP)
    user_agent      VARCHAR(500),
    metadata        JSONB,         -- Any extra context (e.g. plan names, error codes)
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_user    ON users.audit_log(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_action  ON users.audit_log(action, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_created ON users.audit_log(created_at DESC);

COMMENT ON TABLE users.audit_log IS
    'Immutable audit trail for sensitive operations. Required for Privacy Act 1988 '
    'NDB scheme compliance and internal security monitoring. Rows are never updated '
    'or deleted — archive partitions after 7 years (ATO record-keeping requirement).';

-- ── 3. Unsubscribe tokens ─────────────────────────────────────
--  Spam Act 2003 requires a functional one-click unsubscribe
--  that processes within 5 business days. This table stores
--  signed tokens embedded in email footers.

CREATE TABLE IF NOT EXISTS users.unsubscribe_tokens (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users.users(id) ON DELETE CASCADE,
    token           VARCHAR(128) NOT NULL UNIQUE,
    -- HMAC-SHA256 of (user_id + type + salt) — generated server-side
    unsubscribe_type VARCHAR(30) NOT NULL DEFAULT 'all_marketing',
    -- all_marketing | alerts | digest
    used            BOOLEAN DEFAULT FALSE,
    used_at         TIMESTAMPTZ,
    expires_at      TIMESTAMPTZ NOT NULL DEFAULT NOW() + INTERVAL '1 year',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_unsub_token   ON users.unsubscribe_tokens(token) WHERE NOT used;
CREATE INDEX IF NOT EXISTS idx_unsub_user    ON users.unsubscribe_tokens(user_id);

COMMENT ON TABLE users.unsubscribe_tokens IS
    'One-click unsubscribe tokens embedded in email footers. '
    'Spam Act 2003 s.18: unsubscribe requests must be actioned within 5 business days.';

-- ── 4. Backfill: ensure existing users have the new column ────
--  New column defaults to FALSE so no action needed for existing
--  rows — but we document this explicitly for the migration log.

DO $$
BEGIN
    RAISE NOTICE 'Migration 008: marketing_emails_enabled added (default FALSE). '
                 'Existing % users default to opt-out as required by Spam Act 2003.',
                 (SELECT COUNT(*) FROM users.users);
END $$;
