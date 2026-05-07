-- Migration 038: Commodities prices table
-- Stores daily OHLC + period returns for key global commodities
-- (precious metals, base metals, energy, bulk) fetched from EODHD

CREATE TABLE IF NOT EXISTS market.commodity_prices (
    commodity_code  VARCHAR(20)    NOT NULL,
    commodity_name  TEXT           NOT NULL,
    category        VARCHAR(50)    NOT NULL,   -- 'Precious Metals', 'Base Metals', 'Energy', 'Bulk'
    unit            VARCHAR(20),               -- 'USD/oz', 'USD/bbl', 'USD/t', etc.
    price_date      DATE           NOT NULL,
    close_price     NUMERIC(16, 4),
    open_price      NUMERIC(16, 4),
    high_price      NUMERIC(16, 4),
    low_price       NUMERIC(16, 4),
    return_1d       NUMERIC(10, 6),
    return_1w       NUMERIC(10, 6),
    return_1m       NUMERIC(10, 6),
    return_3m       NUMERIC(10, 6),
    return_6m       NUMERIC(10, 6),
    return_1y       NUMERIC(10, 6),
    return_ytd      NUMERIC(10, 6),
    high_52w        NUMERIC(16, 4),
    low_52w         NUMERIC(16, 4),
    PRIMARY KEY (commodity_code, price_date)
);

CREATE INDEX IF NOT EXISTS idx_commodity_prices_date
    ON market.commodity_prices (price_date DESC);

CREATE INDEX IF NOT EXISTS idx_commodity_prices_category
    ON market.commodity_prices (category, commodity_code);

COMMENT ON TABLE market.commodity_prices IS
    'Daily commodity prices fetched from EODHD .COMM exchange. Upserted nightly.';
