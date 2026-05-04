-- Migration 030: Market daily snapshot tables
-- Pre-computed daily market data. Populated by compute/engine/market_snapshot.py
-- after the nightly universe build. Universe table remains stock-level only.

-- ── Index-level snapshots (ASX200, ASX300) ───────────────────────────────────
CREATE TABLE IF NOT EXISTS market.index_snapshots (
    snapshot_date       DATE        NOT NULL,
    index_code          VARCHAR(20) NOT NULL,   -- 'ASX200' | 'ASX300'
    stock_count         INT,
    gainers             INT,
    losers              INT,
    unchanged           INT,
    avg_return_1w       NUMERIC(8,4),
    total_market_cap_bn NUMERIC(14,2),
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (snapshot_date, index_code)
);

-- ── Sector-level snapshots ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS market.sector_snapshots (
    snapshot_date       DATE         NOT NULL,
    sector              VARCHAR(100) NOT NULL,
    stock_count         INT,
    gainers             INT,
    losers              INT,
    avg_return_1w       NUMERIC(8,4),
    total_market_cap_bn NUMERIC(14,2),
    created_at          TIMESTAMPTZ  DEFAULT NOW(),
    PRIMARY KEY (snapshot_date, sector)
);

-- ── Per-stock ranked lists ────────────────────────────────────────────────────
-- snapshot_type: GAINER | LOSER | ACTIVE | SHORTED
CREATE TABLE IF NOT EXISTS market.mover_snapshots (
    snapshot_date  DATE         NOT NULL,
    snapshot_type  VARCHAR(20)  NOT NULL,
    rank           SMALLINT     NOT NULL,
    asx_code       VARCHAR(10)  NOT NULL,
    company_name   VARCHAR(200),
    sector         VARCHAR(100),
    price          NUMERIC(12,4),
    return_1w      NUMERIC(8,4),
    volume         BIGINT,
    avg_volume_20d BIGINT,
    short_pct      NUMERIC(6,2),
    market_cap     NUMERIC(16,2),
    created_at     TIMESTAMPTZ  DEFAULT NOW(),
    PRIMARY KEY (snapshot_date, snapshot_type, rank)
);

-- ── Upcoming ex-dividend dates ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS market.exdiv_snapshots (
    snapshot_date  DATE         NOT NULL,
    asx_code       VARCHAR(10)  NOT NULL,
    company_name   VARCHAR(200),
    ex_div_date    DATE,
    pay_date       DATE,
    dps_ttm        NUMERIC(10,4),
    dividend_yield NUMERIC(8,4),
    franking_pct   NUMERIC(5,2),
    created_at     TIMESTAMPTZ  DEFAULT NOW(),
    PRIMARY KEY (snapshot_date, asx_code)
);

-- Indexes for fast latest-date lookups
CREATE INDEX IF NOT EXISTS idx_index_snapshots_date   ON market.index_snapshots  (snapshot_date DESC);
CREATE INDEX IF NOT EXISTS idx_sector_snapshots_date  ON market.sector_snapshots  (snapshot_date DESC);
CREATE INDEX IF NOT EXISTS idx_mover_snapshots_date   ON market.mover_snapshots   (snapshot_date DESC, snapshot_type);
CREATE INDEX IF NOT EXISTS idx_exdiv_snapshots_date   ON market.exdiv_snapshots   (snapshot_date DESC);
CREATE INDEX IF NOT EXISTS idx_mover_snapshots_code   ON market.mover_snapshots   (asx_code);
