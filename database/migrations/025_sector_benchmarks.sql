-- Migration 025: Sector benchmark statistics table
-- ==================================================
-- market.sector_benchmarks stores the median, 25th and 75th percentile
-- for key valuation/profitability/growth metrics per GICS sector.
-- Rebuilt weekly by compute/engine/sector_benchmarks.py.
-- Used by the Peers tab to show "vs sector" percentile context.
-- ==================================================

CREATE TABLE IF NOT EXISTS market.sector_benchmarks (
    gics_sector             TEXT        NOT NULL,
    stock_count             INT,                        -- active stocks in this sector

    -- Valuation
    pe_ratio_p25            NUMERIC(10,4),
    pe_ratio_median         NUMERIC(10,4),
    pe_ratio_p75            NUMERIC(10,4),

    price_to_book_p25       NUMERIC(10,4),
    price_to_book_median    NUMERIC(10,4),
    price_to_book_p75       NUMERIC(10,4),

    ev_to_ebitda_p25        NUMERIC(10,4),
    ev_to_ebitda_median     NUMERIC(10,4),
    ev_to_ebitda_p75        NUMERIC(10,4),

    -- Dividends
    dividend_yield_median   NUMERIC(10,4),
    grossed_up_yield_median NUMERIC(10,4),
    franking_pct_median     NUMERIC(10,4),

    -- Profitability
    roe_p25                 NUMERIC(10,4),
    roe_median              NUMERIC(10,4),
    roe_p75                 NUMERIC(10,4),

    net_margin_p25          NUMERIC(10,4),
    net_margin_median       NUMERIC(10,4),
    net_margin_p75          NUMERIC(10,4),

    gross_margin_median     NUMERIC(10,4),
    ebitda_margin_median    NUMERIC(10,4),

    -- Growth
    revenue_growth_1y_median    NUMERIC(10,4),
    earnings_growth_1y_median   NUMERIC(10,4),

    -- Leverage
    debt_to_equity_median   NUMERIC(10,4),
    current_ratio_median    NUMERIC(10,4),

    -- Returns
    return_1y_median        NUMERIC(10,4),
    return_ytd_median       NUMERIC(10,4),

    -- Market
    market_cap_median       NUMERIC(18,4),

    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (gics_sector)
);

GRANT SELECT ON market.sector_benchmarks TO asx_user;
GRANT INSERT, UPDATE ON market.sector_benchmarks TO asx_user;

COMMENT ON TABLE market.sector_benchmarks IS
    'Weekly-rebuilt GICS sector benchmark statistics (median / P25 / P75) from screener.universe';
