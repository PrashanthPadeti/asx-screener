-- Edge-trigger the alerts: remember whether the condition was met last time.
--
-- Without this column an alert can only be LEVEL-triggered: the worker sees
-- "CBA is below $150" and fires, sees the same thing fifteen minutes later and
-- fires again. One user received 52 emails on 1 Oct 2026 and 29 on 2 Oct, all
-- identical, all saying CBA had fallen below $150 -- once per check cycle for
-- as long as the price stayed there. The alert was doing exactly what the code
-- said; the code said the wrong thing.
--
-- An alert is a statement about a CROSSING, not about a state. "Tell me when
-- CBA falls below $150" is answered once when it falls, and again only if it
-- recovers and falls a second time. That requires remembering the previous
-- evaluation, which is what this column is.
--
--   FALSE  the condition was not met at the last evaluation -- the alert is
--          ARMED and will fire when the condition becomes true
--   TRUE   the condition was met -- the alert has already fired for this
--          crossing and stays silent until the condition goes false again
--
-- Defaulting to FALSE arms every existing alert. The first evaluation after
-- this migration fires once for any alert whose condition is currently met,
-- then falls silent. That is the correct behaviour on the merits -- a user
-- whose threshold is currently breached should be told once -- and it is
-- preferable to defaulting TRUE, which would silently swallow the first real
-- crossing after deployment.
--
-- Apply BEFORE deploying the worker that reads it. The old worker ignores the
-- column entirely, so this is safe to run on its own and safe to leave in
-- place if the deployment is deferred.

ALTER TABLE users.alerts
    ADD COLUMN IF NOT EXISTS condition_met BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN users.alerts.condition_met IS
    'Was the alert condition met at the last evaluation? Edge-triggering: the '
    'alert fires on the FALSE->TRUE transition and re-arms when it returns to '
    'FALSE. Prevents one email per check cycle for a persistently breached '
    'threshold (observed: 52 emails in a day, 1 Oct 2026).';
