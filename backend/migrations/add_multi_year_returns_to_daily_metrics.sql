-- The multi-year returns move to the engine that computes the other windows.
--
-- market.daily_metrics carries return_1d/5d/1w/20d/1m/60d/3m/6m/1y/ytd and
-- stops there. The longer horizons lived in two other places:
--
--   return_3y/5y/7y/10y/15y   market.yearly_metrics, via
--                             yearly_compute.price_return(), whose price_at()
--                             anchors with NO grace bound (a three-year return
--                             could measure eight), ends at the fiscal period
--                             end rather than today, and has no
--                             corporate-action withholding. It published
--                             return_3y = 1449.0 for JNS on 28 Oct 2026 --
--                             +144,900% -- beside a return_1y of +247%.
--
--   return_2y/4y/6y/8y/9y     nowhere. No producer exists. They are
--                             filterable, sortable and shown on the company
--                             page; screener.universe is upserted, so a
--                             column absent from the SET list keeps whatever
--                             was last written to it by code that is gone.
--
-- Both groups now compute in technical_compute through one anchor rule, one
-- grace bound and one withholding path, which is why they need storage here.
--
-- DOUBLE PRECISION, matching every other return column in this table.
-- Deliberately not NUMERIC(n,4): these are fractions, a consolidation can
-- produce a legitimately enormous one, and this project has already had a
-- NUMERIC overflow abort a compute run. A column type must not be the thing
-- that decides whether a true number can be stored.
--
-- Nullable, no default. An absent return is absent -- there is no price near
-- the window's start, or the window spans a corporate action we cannot
-- adjust out -- and v11.2.63 makes that absence explicit in metric_states
-- rather than in the numeric column. A default of 0 would be a return of 0%,
-- which is a claim, not a silence.

ALTER TABLE market.daily_metrics
    ADD COLUMN IF NOT EXISTS return_2y  DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS return_3y  DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS return_4y  DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS return_5y  DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS return_6y  DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS return_7y  DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS return_8y  DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS return_9y  DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS return_10y DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS return_15y DOUBLE PRECISION;

COMMENT ON COLUMN market.daily_metrics.return_3y IS
    'Calendar three-year price return, anchored on the last close at or '
    'before date - 3 years and within the declared grace. NULL where no such '
    'close exists or the window spans an unreconciled corporate action; the '
    'reason is in metric_states. Replaces market.yearly_metrics.return_3y, '
    'which was anchored without a grace bound and ended at the fiscal period '
    'end.';
