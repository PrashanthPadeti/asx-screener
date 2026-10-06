-- Acceptance gate for v11.2.10 -- companies currentness.
--
-- Read-only. Raises on the first violated property, so a failure is an exit
-- code rather than a number to be read off a terminal. Run AFTER deploy.sh
-- and AFTER migrations/refresh_companies_current_view.sql.
--
--     psql "$DATABASE_URL_SYNC" -v ON_ERROR_STOP=1 \
--          -f scripts/diagnostics/accept_companies_currency.sql
--
-- The expected values are written as literals on purpose. A gate that derives
-- its expectation from the same query it is checking agrees with itself by
-- construction; these three numbers were measured on production on 7 Oct 2026
-- before the fix (3,737 / 8 / ~115) and after it (2,147 / 4 / 200).

\echo '== 7. the view carries every column of its table =='

DO $$
DECLARE
    missing text;
BEGIN
    SELECT string_agg(column_name, ', ' ORDER BY column_name) INTO missing
      FROM (SELECT column_name FROM information_schema.columns
             WHERE table_schema = 'market' AND table_name = 'companies'
            EXCEPT
            SELECT column_name FROM information_schema.columns
             WHERE table_schema = 'market' AND table_name = 'companies_current') q;

    IF missing IS NOT NULL THEN
        RAISE EXCEPTION
            'companies_current is missing column(s): %. The view enumerates '
            'its columns and drifts whenever one is added to the table; it '
            'was two behind for as long as business_model_tag and '
            'commodity_exposure have existed.', missing;
    END IF;
END $$;

DO $$
DECLARE
    n int;
BEGIN
    SELECT count(*) INTO n FROM information_schema.columns
     WHERE table_schema = 'market' AND table_name = 'companies_current';
    IF n <> 52 THEN
        RAISE EXCEPTION 'companies_current has % columns, expected 52', n;
    END IF;

    -- Named explicitly: the set-difference check above passes if BOTH the
    -- table and the view lose a column, which is exactly how the drift went
    -- unnoticed the first time.
    PERFORM 1 FROM information_schema.columns
     WHERE table_schema = 'market' AND table_name = 'companies_current'
       AND column_name = 'business_model_tag';
    IF NOT FOUND THEN
        RAISE EXCEPTION 'companies_current lacks business_model_tag';
    END IF;

    PERFORM 1 FROM information_schema.columns
     WHERE table_schema = 'market' AND table_name = 'companies_current'
       AND column_name = 'commodity_exposure';
    IF NOT FOUND THEN
        RAISE EXCEPTION 'companies_current lacks commodity_exposure';
    END IF;
END $$;

\echo '== 8. the three behavioural assertions: 2147 / 4 / 200 =='

DO $$
DECLARE
    companies int;
    alerts    int;
    sweep     int;
BEGIN
    SELECT count(*) INTO companies
      FROM market.companies_current WHERE status = 'active';
    IF companies <> 2147 THEN
        RAISE EXCEPTION
            'company list total is %, expected 2147 (pre-fix: 3737). A change '
            'here is not necessarily a regression -- companies list and '
            'delist -- but it must be explained before the release is '
            'accepted, not after.', companies;
    END IF;

    SELECT count(*) INTO alerts
      FROM users.alerts a
      JOIN users.users u                          ON u.id = a.user_id
      LEFT JOIN screener.universe s               ON s.asx_code = a.asx_code
      LEFT JOIN market.companies_current c        ON c.asx_code = a.asx_code
      LEFT JOIN users.notification_preferences np ON np.user_id = a.user_id
     WHERE a.is_active = TRUE;
    IF alerts <> 4 THEN
        RAISE EXCEPTION
            'the active-alert join returns % rows, expected 4 (pre-fix: 8). '
            'Under edge-triggering each duplicated row carries the same '
            'condition_met snapshot, so a fan-out here is two emails per '
            'crossing.', alerts;
    END IF;

    SELECT count(*) INTO sweep FROM (
        SELECT u.asx_code FROM screener.universe u
        LEFT JOIN market.companies_current c ON c.asx_code = u.asx_code
        ORDER BY u.market_cap DESC NULLS LAST LIMIT 200) x;
    IF sweep <> 200 THEN
        RAISE EXCEPTION
            'the announcement sweep covers % codes, expected 200 (pre-fix: '
            '~115). LIMIT counts rows, so a fanned-out join silently shrinks '
            'the population rather than failing.', sweep;
    END IF;
END $$;

\echo '== 9. one row per code, and that count is the served count =='

DO $$
DECLARE
    rows_   int;
    codes_  int;
BEGIN
    SELECT count(*), count(DISTINCT asx_code) INTO rows_, codes_
      FROM market.companies_current WHERE status = 'active';

    IF rows_ <> codes_ THEN
        RAISE EXCEPTION
            'companies_current returns % rows for % distinct codes. The '
            'partial unique index idx_companies_current_code should make this '
            'impossible; if it fires, the SCD invariant itself is broken and '
            'the view is not a remedy.', rows_, codes_;
    END IF;

    IF rows_ <> 2147 THEN
        RAISE EXCEPTION 'expected 2147 rows and codes, got %', rows_;
    END IF;
END $$;

\echo 'ACCEPTED: companies currentness, steps 7-9'
