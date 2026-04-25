-- ─────────────────────────────────────────────────────────────
--  Migration 001 — Extensions & Schema Namespaces
--  Runs first: installs TimescaleDB, pgvector, creates schemas.
-- ─────────────────────────────────────────────────────────────

-- Extensions
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;
CREATE EXTENSION IF NOT EXISTS vector;           -- pgvector (AI embeddings)
CREATE EXTENSION IF NOT EXISTS pg_trgm;          -- Trigram search (company name autocomplete)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";      -- UUID generation fallback
CREATE EXTENSION IF NOT EXISTS pg_stat_statements; -- Query performance monitoring

-- Schemas
CREATE SCHEMA IF NOT EXISTS market;
CREATE SCHEMA IF NOT EXISTS financials;
CREATE SCHEMA IF NOT EXISTS users;
CREATE SCHEMA IF NOT EXISTS ai;
CREATE SCHEMA IF NOT EXISTS meta;

-- search_path so unqualified names still work in psql sessions
ALTER DATABASE asx_screener SET search_path TO market, financials, users, ai, meta, public;

-- Shared updated_at trigger function (reused across tables)
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;
