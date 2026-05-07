-- 037_global_markets.sql
-- Global market indices (US/EU/Asia) and AUD FX rates

-- Metadata for each tracked global index
CREATE TABLE IF NOT EXISTS market.global_indices (
    index_code   VARCHAR(20)  PRIMARY KEY,
    index_name   TEXT         NOT NULL,
    region       VARCHAR(50)  NOT NULL,   -- 'US', 'Europe', 'Asia'
    country      VARCHAR(50),
    currency     VARCHAR(10),
    yf_ticker    VARCHAR(30)  NOT NULL,
    is_active    BOOLEAN      DEFAULT TRUE,
    created_at   TIMESTAMPTZ  DEFAULT NOW()
);

-- Daily OHLCV + period returns for global indices
CREATE TABLE IF NOT EXISTS market.global_index_prices (
    index_code   VARCHAR(20)   NOT NULL REFERENCES market.global_indices(index_code),
    price_date   DATE          NOT NULL,
    close_price  NUMERIC(16,4),
    open_price   NUMERIC(16,4),
    high_price   NUMERIC(16,4),
    low_price    NUMERIC(16,4),
    volume       BIGINT,
    return_1d    NUMERIC(10,6),
    return_1w    NUMERIC(10,6),
    return_1m    NUMERIC(10,6),
    return_3m    NUMERIC(10,6),
    return_6m    NUMERIC(10,6),
    return_1y    NUMERIC(10,6),
    return_ytd   NUMERIC(10,6),
    high_52w     NUMERIC(16,4),
    low_52w      NUMERIC(16,4),
    PRIMARY KEY (index_code, price_date)
);

-- Daily AUD-base FX rates
CREATE TABLE IF NOT EXISTS market.fx_rates (
    fx_pair      VARCHAR(10)   NOT NULL,   -- 'AUDUSD', 'AUDEUR', etc.
    rate_date    DATE          NOT NULL,
    rate         NUMERIC(16,6) NOT NULL,
    open_rate    NUMERIC(16,6),
    high_rate    NUMERIC(16,6),
    low_rate     NUMERIC(16,6),
    return_1d    NUMERIC(10,6),
    return_1w    NUMERIC(10,6),
    return_1m    NUMERIC(10,6),
    return_ytd   NUMERIC(10,6),
    PRIMARY KEY (fx_pair, rate_date)
);

CREATE INDEX IF NOT EXISTS idx_global_index_prices_date ON market.global_index_prices (price_date DESC);
CREATE INDEX IF NOT EXISTS idx_global_index_prices_code ON market.global_index_prices (index_code);
CREATE INDEX IF NOT EXISTS idx_fx_rates_date            ON market.fx_rates (rate_date DESC);
CREATE INDEX IF NOT EXISTS idx_fx_rates_pair            ON market.fx_rates (fx_pair);
