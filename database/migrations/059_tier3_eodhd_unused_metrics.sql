-- Migration 059: Surface EODHD data already collected but not yet used in the screener
-- eps_beat_rate_4q       : fraction of last 4 quarters where EPS actual beat estimate
-- eps_beat_rate_8q       : fraction of last 8 quarters where EPS actual beat estimate
-- consecutive_eps_beats  : count of consecutive most-recent quarters beaten (streak)
-- analyst_upside_pct     : % upside/downside from current price to analyst target price
-- short_ratio            : EODHD days-to-cover (shares short / 50d avg daily volume)
-- years_listed           : years since IPO date (company maturity proxy)

ALTER TABLE screener.universe
    ADD COLUMN IF NOT EXISTS eps_beat_rate_4q      NUMERIC(5, 4),
    ADD COLUMN IF NOT EXISTS eps_beat_rate_8q      NUMERIC(5, 4),
    ADD COLUMN IF NOT EXISTS consecutive_eps_beats SMALLINT,
    ADD COLUMN IF NOT EXISTS analyst_upside_pct    NUMERIC(10, 4),
    ADD COLUMN IF NOT EXISTS short_ratio           NUMERIC(10, 4),
    ADD COLUMN IF NOT EXISTS years_listed          NUMERIC(6, 2);
