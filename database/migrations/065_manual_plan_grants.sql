-- ─────────────────────────────────────────────────────────────
--  Migration 065 — Manual plan grants survive Stripe
--
--  A courtesy or promotional grant is written into plan,
--  billing_period and subscription_ends_at. Those are the same
--  fields the Stripe webhook owns: every
--  customer.subscription.updated recomputes them from the price
--  map and the Stripe period end.
--
--  So a grant made today is undone by the customer's next
--  renewal, card update or plan change, silently, and the only
--  sign is a support ticket months later. Two grants made on
--  15 Sep 2026 -- a year of Premium for a customer charged twice
--  during the billing outage, and three years for a customer
--  compensated for the same outage -- were both exposed to this.
--
--  plan_locked_until says "a human decided this, and Stripe does
--  not get to overrule it until then". The webhook still records
--  everything factual about the subscription -- status, id,
--  whether it is live -- because that remains true and is needed
--  for billing. It just stops rewriting the entitlement.
-- ─────────────────────────────────────────────────────────────

ALTER TABLE users.users
    ADD COLUMN IF NOT EXISTS plan_locked_until TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS plan_locked_reason TEXT;

COMMENT ON COLUMN users.users.plan_locked_until IS
    'While in the future, plan/billing_period/seat_limit are held against '
    'Stripe webhook writes and subscription_ends_at is never shortened. '
    'Set by an admin grant. NULL means Stripe is authoritative, which is '
    'the normal case.';

COMMENT ON COLUMN users.users.plan_locked_reason IS
    'Why the grant was made, and by whom. Read by humans, not by code.';

-- Partial index: the lock is rare, and the webhook path asks about it on
-- every subscription event.
CREATE INDEX IF NOT EXISTS ix_users_plan_locked
    ON users.users (plan_locked_until)
    WHERE plan_locked_until IS NOT NULL;
