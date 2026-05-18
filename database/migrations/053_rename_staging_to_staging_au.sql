-- Migration 053: Rename staging schema to staging_au
--
-- Architecture change: per-market staging schemas replace the single shared
-- staging.* schema. ASX Screener's staging schema is renamed to staging_au.*
-- to align with the multi-project platform architecture.
--
-- All tables and their data are preserved. Only the schema name changes.
--
-- Run ONCE on the server. Coordinate with code deployment — scripts must be
-- updated to reference staging_au.* before or at the same time as this runs.

-- Step 1: Rename the schema
ALTER SCHEMA staging RENAME TO staging_au;

-- Step 2: Update DB role grants
--   Remove access to old schema name, grant access to new schema name

REVOKE ALL PRIVILEGES ON SCHEMA staging_au FROM screener_au_app;

GRANT USAGE  ON SCHEMA staging_au                       TO screener_au_app;
GRANT SELECT, INSERT, UPDATE, DELETE
      ON ALL TABLES IN SCHEMA staging_au                TO screener_au_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA staging_au
      GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES    TO screener_au_app;

-- Step 3: Verify rename succeeded
-- SELECT schema_name FROM information_schema.schemata WHERE schema_name = 'staging_au';
-- Expected: one row returned

-- Step 4: Verify tables are intact
-- SELECT table_name FROM information_schema.tables WHERE table_schema = 'staging_au' ORDER BY table_name;
-- Expected: same tables as before (eod_prices, short_positions, shares_stats, etc.)
