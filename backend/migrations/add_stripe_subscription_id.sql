-- Migration: add stripe_subscription_id to users.users
-- Run once on the server:
--   sudo -u postgres psql asx_screener -f /opt/asx-screener/backend/migrations/add_stripe_subscription_id.sql

ALTER TABLE users.users
    ADD COLUMN IF NOT EXISTS stripe_subscription_id VARCHAR(100);

CREATE INDEX IF NOT EXISTS idx_users_stripe_subscription_id
    ON users.users (stripe_subscription_id)
    WHERE stripe_subscription_id IS NOT NULL;
