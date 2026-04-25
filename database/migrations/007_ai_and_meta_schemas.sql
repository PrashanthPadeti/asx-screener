-- ─────────────────────────────────────────────────────────────
--  Migration 007 — ai & meta Schemas
--  document_chunks (pgvector) · ai_insights · concall_summaries
--  meta.metric_definitions · meta.compute_log
-- ─────────────────────────────────────────────────────────────

-- ── ai.document_chunks ───────────────────────────────────────

CREATE TABLE ai.document_chunks (
    id                      BIGSERIAL PRIMARY KEY,
    asx_code                VARCHAR(10) NOT NULL,
    document_type           VARCHAR(50),
    -- annual_report | half_year_report | concall | presentation | prospectus
    document_year           INTEGER,
    document_period         VARCHAR(20),   -- e.g. 'FY2025', '1H FY2026'
    s3_key                  VARCHAR(500),
    chunk_index             INTEGER,
    chunk_text              TEXT NOT NULL,
    embedding               vector(1536),  -- pgvector: OpenAI/Claude embedding
    token_count             INTEGER,
    page_number             INTEGER,
    section_heading         VARCHAR(500),
    created_at              TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_chunks_asx    ON ai.document_chunks(asx_code, document_year DESC);
-- IVFFlat index for approximate nearest-neighbour search (cosine similarity)
CREATE INDEX idx_chunks_vector ON ai.document_chunks
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- ── ai.ai_insights ───────────────────────────────────────────

CREATE TABLE ai.ai_insights (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asx_code        VARCHAR(10) NOT NULL,
    user_id         UUID REFERENCES users.users(id) ON DELETE SET NULL,
    question        TEXT,
    answer          TEXT NOT NULL,
    model_used      VARCHAR(50),
    source_chunk_ids BIGINT[],
    input_tokens    INTEGER,
    output_tokens   INTEGER,
    is_public       BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_insights_asx  ON ai.ai_insights(asx_code, created_at DESC);
CREATE INDEX idx_insights_user ON ai.ai_insights(user_id) WHERE user_id IS NOT NULL;

-- ── ai.concall_summaries ─────────────────────────────────────

CREATE TABLE ai.concall_summaries (
    id                      SERIAL PRIMARY KEY,
    asx_code                VARCHAR(10) NOT NULL,
    event_date              DATE NOT NULL,
    event_type              VARCHAR(50),
    -- results_call | agm | investor_day | site_visit
    summary_text            TEXT,
    key_points              JSONB,   -- ["point1", "point2"]
    sentiment               VARCHAR(20),
    guidance_updated        BOOLEAN DEFAULT FALSE,
    guidance_direction      VARCHAR(20),   -- up | down | maintained | withdrawn
    s3_transcript_key       VARCHAR(500),
    model_used              VARCHAR(50),
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (asx_code, event_date, event_type)
);

CREATE INDEX idx_concall_asx ON ai.concall_summaries(asx_code, event_date DESC);

-- ────────────────────────────────────────────────────────────
--  meta Schema — Metric definitions + Compute logging
-- ────────────────────────────────────────────────────────────

-- ── meta.metric_definitions ──────────────────────────────────
-- Single source of truth for all 544+ metrics:
-- keys, display names, formulas, compute tags, categories.

CREATE TABLE meta.metric_definitions (
    metric_id           SERIAL PRIMARY KEY,
    metric_key          VARCHAR(100) NOT NULL UNIQUE,  -- matches column name in computed_metrics
    metric_name         VARCHAR(200) NOT NULL,
    category            VARCHAR(50),
    -- valuation | profitability | growth | financial_health | cash_flow |
    -- dividends | technical | scores | per_share | shareholding |
    -- asx_mining | asx_reit | asx_specific

    -- Compute schedule
    compute_tags        TEXT[] NOT NULL,  -- e.g. ARRAY['D','HY'] or ARRAY['Y']
    primary_tag         VARCHAR(5) NOT NULL,  -- single most-frequent tag (D/W/M/Q/HY/Y/E)

    -- Formula documentation
    formula             TEXT,            -- Human-readable formula
    formula_code        TEXT,            -- Python expression (used by compute engine)
    data_sources        TEXT[],          -- ARRAY['daily_prices','annual_balance_sheet']

    -- Display
    unit                VARCHAR(30),     -- AUD | % | x | days | score | years | oz
    display_decimals    SMALLINT DEFAULT 2,
    display_format      VARCHAR(20) DEFAULT 'number',  -- number | percent | currency | ratio

    -- Feature flags
    is_asx_specific     BOOLEAN DEFAULT FALSE,
    is_screener_enabled BOOLEAN DEFAULT TRUE,   -- Available as screener filter
    is_chart_enabled    BOOLEAN DEFAULT TRUE,   -- Show historical chart on company page
    is_active           BOOLEAN DEFAULT TRUE,

    -- Plan gating
    min_plan            VARCHAR(20) DEFAULT 'free',  -- free | pro | premium

    notes               TEXT
);

CREATE INDEX idx_metric_category ON meta.metric_definitions(category);
CREATE INDEX idx_metric_tags     ON meta.metric_definitions USING GIN(compute_tags);
CREATE INDEX idx_metric_active   ON meta.metric_definitions(is_active) WHERE is_active = TRUE;

-- ── meta.compute_log ─────────────────────────────────────────
-- Tracks every compute engine run for monitoring and debugging.

CREATE TABLE meta.compute_log (
    id                  BIGSERIAL PRIMARY KEY,
    run_id              UUID DEFAULT gen_random_uuid(),
    schedule_type       VARCHAR(20) NOT NULL,
    -- daily | weekend | month_end | quarterly | half_yearly | yearly | event
    triggered_by        VARCHAR(50) DEFAULT 'scheduler',  -- scheduler | event | manual
    asx_codes           TEXT[],   -- NULL = all stocks; specific array = event-triggered subset

    started_at          TIMESTAMPTZ DEFAULT NOW(),
    finished_at         TIMESTAMPTZ,
    duration_seconds    NUMERIC(10,2),

    stocks_processed    INTEGER DEFAULT 0,
    stocks_failed       INTEGER DEFAULT 0,
    metrics_computed    INTEGER DEFAULT 0,

    status              VARCHAR(20) DEFAULT 'running',
    -- running | completed | failed | partial
    error_message       TEXT,
    compute_version     VARCHAR(20)
);

CREATE INDEX idx_compute_log_started ON meta.compute_log(started_at DESC);
CREATE INDEX idx_compute_log_status  ON meta.compute_log(status);

-- ── meta.data_load_log ────────────────────────────────────────
-- Tracks Airflow DAG runs for data ingestion.

CREATE TABLE meta.data_load_log (
    id              BIGSERIAL PRIMARY KEY,
    dag_id          VARCHAR(100) NOT NULL,
    run_date        DATE NOT NULL,
    started_at      TIMESTAMPTZ DEFAULT NOW(),
    finished_at     TIMESTAMPTZ,
    status          VARCHAR(20) DEFAULT 'running',
    rows_loaded     INTEGER,
    rows_failed     INTEGER,
    error_message   TEXT,
    UNIQUE (dag_id, run_date)
);

CREATE INDEX idx_load_log_dag  ON meta.data_load_log(dag_id, run_date DESC);
CREATE INDEX idx_load_log_date ON meta.data_load_log(run_date DESC);
