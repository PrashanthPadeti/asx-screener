-- users.users.plan accepted any string, so a typo became a silent downgrade.
--
-- Found 8 Oct 2026: one ACTIVE subscriber held `pro_monthly`, which is not a
-- plan. `get_limits()` and `feature_level()` both fall back to free for an
-- unrecognised value -- correct, since an unknown plan must never widen
-- access -- so a paying Pro customer was served free entitlements: 1
-- portfolio, 1 watchlist, 3 alerts, no CSV export. Nothing reported it.
--
-- Neither path that writes `plan` today can produce that value: the admin
-- endpoint validates against VALID_PLANS, and the Stripe webhook maps
-- price_id to a plan and leaves it unchanged when the price is unrecognised.
-- So it predates those guards, or was written directly. The column itself has
-- never constrained what it holds.
--
-- APPLY ORDER MATTERS. This fails if any row holds a value outside the list,
-- which is the point -- but it means the data is corrected first:
--
--   SELECT plan, count(*) FROM users.users GROUP BY plan;        -- inspect
--   UPDATE users.users SET plan = 'pro' WHERE plan = 'pro_monthly';
--   \i migrations/constrain_user_plan.sql
--
-- Do not widen the list to admit a bad value. The list is the plan set in
-- app/core/plans.py; anything else is a defect to fix, not a value to allow.
-- 'admin' is deliberately absent: admin is an identity checked against
-- ADMIN_EMAILS, not a subscription, and making it assignable here would make
-- it billable by accident.

ALTER TABLE users.users
    ADD CONSTRAINT users_plan_known
    CHECK (plan IN ('free', 'pro', 'premium',
                    'enterprise_pro', 'enterprise_premium'));

COMMENT ON CONSTRAINT users_plan_known ON users.users IS
    'Plan must be one of the five defined in app/core/plans.py. Without this '
    'an unrecognised value silently resolves to free entitlements, which is '
    'indistinguishable from a free user -- observed 8 Oct 2026 as an active '
    'subscriber on pro_monthly receiving free limits.';
