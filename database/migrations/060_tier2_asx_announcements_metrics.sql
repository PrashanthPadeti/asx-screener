-- Migration 060: Tier-2 signals derived from market.asx_announcements
-- (ASX's free public announcements API, already ingested daily)
-- capital_raise_count_1y       : count of placement/rights-issue/entitlement/SPP filings in trailing 12mo
-- recent_capital_raise         : true if a capital raise happened in the last 90 days
-- trading_halt_count_1y        : count of trading-halt filings in trailing 12mo
-- director_change_count_1y     : count of director/substantial-holder-change filings in trailing 12mo
-- days_since_last_announcement : days since the most recent disclosure of any type
-- announcement_count_1y        : total disclosure volume in trailing 12mo

ALTER TABLE screener.universe
    ADD COLUMN IF NOT EXISTS capital_raise_count_1y       SMALLINT,
    ADD COLUMN IF NOT EXISTS recent_capital_raise         BOOLEAN,
    ADD COLUMN IF NOT EXISTS trading_halt_count_1y        SMALLINT,
    ADD COLUMN IF NOT EXISTS director_change_count_1y     SMALLINT,
    ADD COLUMN IF NOT EXISTS days_since_last_announcement INTEGER,
    ADD COLUMN IF NOT EXISTS announcement_count_1y        SMALLINT;
