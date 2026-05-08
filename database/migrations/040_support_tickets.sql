-- Support tickets schema
CREATE SCHEMA IF NOT EXISTS support;

CREATE TABLE IF NOT EXISTS support.tickets (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    ticket_number    INTEGER     GENERATED ALWAYS AS IDENTITY,
    user_id          UUID        REFERENCES users.users(id) ON DELETE SET NULL,
    name             VARCHAR(200) NOT NULL,
    email            VARCHAR(255) NOT NULL,
    phone            VARCHAR(50),
    category         VARCHAR(50)  NOT NULL DEFAULT 'general',
    subject          VARCHAR(300) NOT NULL,
    description      TEXT        NOT NULL,
    attachments      JSONB       NOT NULL DEFAULT '[]',
    status           VARCHAR(20)  NOT NULL DEFAULT 'open',
    priority         VARCHAR(10)  NOT NULL DEFAULT 'normal',
    resolution_notes TEXT,
    resolved_by      VARCHAR(200),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at      TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_support_tickets_status   ON support.tickets (status);
CREATE INDEX IF NOT EXISTS idx_support_tickets_email    ON support.tickets (email);
CREATE INDEX IF NOT EXISTS idx_support_tickets_user_id  ON support.tickets (user_id) WHERE user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_support_tickets_created  ON support.tickets (created_at DESC);
