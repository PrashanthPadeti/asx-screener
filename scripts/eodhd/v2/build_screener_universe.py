"""
Build Screener Universe — Golden Record
========================================
Builds screener.universe from all transform-layer tables.

One denormalised row per stock, covering:
  - Identity & classification (from market.companies_current)
  - Price & market cap       (from market.daily_prices latest close +
                               market.valuation_snapshot)
  - Valuation ratios         (from market.valuation_snapshot)
  - Dividends                (from market.dividends latest + valuation_snapshot)
  - Profitability / margins  (from market.valuation_snapshot)
  - Financials FY0/FY1       (from financials.annual_pnl + balance_sheet + cashflow)
  - Analyst ratings          (from market.analyst_ratings)
  - Shares / ownership       (from market.companies + shares_stats staging)
  - EPS                      (from financials.earnings_quarterly + annual_pnl)

Run nightly after all transforms complete.

Usage:
    python scripts/eodhd/v2/build_screener_universe.py
    python scripts/eodhd/v2/build_screener_universe.py --codes BHP CBA
"""

import logging
import os
import argparse
from datetime import date

import psycopg2
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv("DATABASE_URL_SYNC",
           "postgresql://asx_user:asx_secure_2024@localhost:5432/asx_screener")

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)


UPSERT_SQL = """
INSERT INTO screener.universe (
    -- Identity
    asx_code, company_name, sector, industry_group, industry, sub_industry,
    stock_type, status, fiscal_year_end_month,
    is_reit, is_miner,
    is_asx20, is_asx50, is_asx100, is_asx200, is_asx300, is_all_ords,
    isin, website, description,

    -- Price
    price, price_date, market_cap,
    high_52w, low_52w,

    -- Valuation (from valuation_snapshot)
    pe_ratio, forward_pe, peg_ratio, price_to_book, price_to_sales,
    ev, ev_to_ebitda, ev_to_revenue,

    -- Dividends
    dividend_yield, dps_ttm, ex_div_date,

    -- Profitability (TTM from valuation_snapshot)
    revenue_ttm, gross_profit_ttm, ebitda_ttm,
    profit_margin, operating_margin, roe, roa,

    -- EPS
    eps_fy0, eps_fy1,

    -- Income Statement FY0 / FY1 (from annual_pnl)
    revenue_fy0, revenue_fy1,
    ebitda_fy0, ebitda_fy1,
    net_profit_fy0, net_profit_fy1,

    -- Balance Sheet (latest FY)
    total_assets, total_equity, total_debt, net_debt, cash,
    book_value_per_share, debt_to_equity, current_ratio,

    -- Cash Flow (latest FY)
    cfo_fy0, capex_fy0, fcf_fy0,

    -- Analyst
    analyst_rating, analyst_target_price,
    analyst_strong_buy, analyst_buy, analyst_hold, analyst_sell, analyst_strong_sell,

    -- Shares
    shares_outstanding,

    universe_built_at
)
SELECT
    c.asx_code,
    c.company_name,
    c.gics_sector,
    c.gics_industry_group,
    c.gics_industry,
    c.gics_sub_industry,
    c.company_type,
    c.status,
    c.fiscal_year_end_month,
    c.is_reit,
    c.is_miner,
    c.is_asx20,  c.is_asx50,  c.is_asx100,
    c.is_asx200, c.is_asx300, c.is_all_ords,
    c.isin,
    c.website,
    c.description,

    -- Latest close price
    dp.close        AS price,
    dp.price_date   AS price_date,
    vs.market_cap,
    dp.high_52w,
    dp.low_52w,

    -- Valuation
    vs.pe_ratio,
    vs.forward_pe,
    vs.peg_ratio,
    vs.price_to_book,
    vs.price_to_sales,
    vs.enterprise_value,
    vs.ev_to_ebitda,
    vs.ev_to_revenue,

    -- Dividends
    vs.dividend_yield,
    vs.dividend_per_share,
    div_latest.ex_date,

    -- Profitability TTM
    vs.revenue_ttm,
    vs.gross_profit_ttm,
    vs.ebitda_ttm,
    vs.profit_margin,
    vs.operating_margin,
    vs.roe_ttm,
    vs.roa_ttm,

    -- EPS (FY0 = most recent, FY1 = one year prior)
    pnl0.eps    AS eps_fy0,
    pnl1.eps    AS eps_fy1,

    -- Revenue / EBITDA / Net Profit FY0, FY1
    pnl0.revenue    AS revenue_fy0,
    pnl1.revenue    AS revenue_fy1,
    pnl0.ebitda     AS ebitda_fy0,
    pnl1.ebitda     AS ebitda_fy1,
    pnl0.net_profit AS net_profit_fy0,
    pnl1.net_profit AS net_profit_fy1,

    -- Balance Sheet (latest FY)
    bs0.total_assets,
    bs0.total_equity,
    bs0.total_debt,
    bs0.net_debt,
    bs0.cash_equivalents,
    bs0.book_value_per_share,
    CASE WHEN bs0.total_equity <> 0 AND bs0.total_equity IS NOT NULL
         THEN ROUND(bs0.total_debt / bs0.total_equity, 4) END,
    CASE WHEN bs0.total_current_liab <> 0 AND bs0.total_current_liab IS NOT NULL
         THEN ROUND(bs0.total_current_assets / bs0.total_current_liab, 4) END,

    -- Cash Flow latest FY
    cf0.cfo     AS cfo_fy0,
    cf0.capex   AS capex_fy0,
    cf0.fcf     AS fcf_fy0,

    -- Analyst
    ar.rating,
    ar.target_price,
    ar.strong_buy, ar.buy, ar.hold, ar.sell, ar.strong_sell,

    -- Shares
    ss.shares_outstanding,

    NOW()

FROM market.companies_current c

-- Latest close price + 52w high/low via subquery
LEFT JOIN LATERAL (
    SELECT
        close,
        DATE(time AT TIME ZONE 'Australia/Sydney') AS price_date,
        MAX(high) OVER (PARTITION BY asx_code ORDER BY time
            ROWS BETWEEN 251 PRECEDING AND CURRENT ROW) AS high_52w,
        MIN(low)  OVER (PARTITION BY asx_code ORDER BY time
            ROWS BETWEEN 251 PRECEDING AND CURRENT ROW) AS low_52w
    FROM market.daily_prices
    WHERE asx_code = c.asx_code
    ORDER BY time DESC
    LIMIT 1
) dp ON TRUE

LEFT JOIN market.valuation_snapshot vs ON vs.asx_code = c.asx_code

-- Latest ex-dividend date
LEFT JOIN LATERAL (
    SELECT ex_date FROM market.dividends
    WHERE asx_code = c.asx_code
    ORDER BY ex_date DESC
    LIMIT 1
) div_latest ON TRUE

-- FY0 = most recent full year P&L
LEFT JOIN LATERAL (
    SELECT fiscal_year, revenue, ebitda, net_profit, eps
    FROM financials.annual_pnl
    WHERE asx_code = c.asx_code
    ORDER BY fiscal_year DESC
    LIMIT 1
) pnl0 ON TRUE

-- FY1 = second most recent
LEFT JOIN LATERAL (
    SELECT fiscal_year, revenue, ebitda, net_profit, eps
    FROM financials.annual_pnl
    WHERE asx_code = c.asx_code
    ORDER BY fiscal_year DESC
    LIMIT 1 OFFSET 1
) pnl1 ON TRUE

-- Balance Sheet latest FY
LEFT JOIN LATERAL (
    SELECT total_assets, total_equity, total_debt, net_debt,
           cash_equivalents, book_value_per_share,
           total_current_assets, total_current_liab
    FROM financials.annual_balance_sheet
    WHERE asx_code = c.asx_code
    ORDER BY fiscal_year DESC
    LIMIT 1
) bs0 ON TRUE

-- Cash Flow latest FY
LEFT JOIN LATERAL (
    SELECT cfo, capex, fcf
    FROM financials.annual_cashflow
    WHERE asx_code = c.asx_code
    ORDER BY fiscal_year DESC
    LIMIT 1
) cf0 ON TRUE

LEFT JOIN market.analyst_ratings ar ON ar.asx_code = c.asx_code

-- Shares outstanding from staging (most recently loaded)
LEFT JOIN LATERAL (
    SELECT shares_outstanding::BIGINT
    FROM staging.shares_stats
    WHERE asx_code = c.asx_code
    LIMIT 1
) ss ON TRUE

{code_filter}

ON CONFLICT (asx_code) DO UPDATE SET
    company_name            = EXCLUDED.company_name,
    sector                  = EXCLUDED.sector,
    industry_group          = EXCLUDED.industry_group,
    industry                = EXCLUDED.industry,
    sub_industry            = EXCLUDED.sub_industry,
    stock_type              = EXCLUDED.stock_type,
    status                  = EXCLUDED.status,
    fiscal_year_end_month   = EXCLUDED.fiscal_year_end_month,
    is_reit                 = EXCLUDED.is_reit,
    is_miner                = EXCLUDED.is_miner,
    is_asx20                = EXCLUDED.is_asx20,
    is_asx50                = EXCLUDED.is_asx50,
    is_asx100               = EXCLUDED.is_asx100,
    is_asx200               = EXCLUDED.is_asx200,
    is_asx300               = EXCLUDED.is_asx300,
    is_all_ords             = EXCLUDED.is_all_ords,
    isin                    = EXCLUDED.isin,
    website                 = EXCLUDED.website,
    description             = EXCLUDED.description,
    price                   = EXCLUDED.price,
    price_date              = EXCLUDED.price_date,
    market_cap              = EXCLUDED.market_cap,
    high_52w                = EXCLUDED.high_52w,
    low_52w                 = EXCLUDED.low_52w,
    pe_ratio                = EXCLUDED.pe_ratio,
    forward_pe              = EXCLUDED.forward_pe,
    peg_ratio               = EXCLUDED.peg_ratio,
    price_to_book           = EXCLUDED.price_to_book,
    price_to_sales          = EXCLUDED.price_to_sales,
    ev                      = EXCLUDED.ev,
    ev_to_ebitda            = EXCLUDED.ev_to_ebitda,
    ev_to_revenue           = EXCLUDED.ev_to_revenue,
    dividend_yield          = EXCLUDED.dividend_yield,
    dps_ttm                 = EXCLUDED.dps_ttm,
    ex_div_date             = EXCLUDED.ex_div_date,
    revenue_ttm             = EXCLUDED.revenue_ttm,
    gross_profit_ttm        = EXCLUDED.gross_profit_ttm,
    ebitda_ttm              = EXCLUDED.ebitda_ttm,
    profit_margin           = EXCLUDED.profit_margin,
    operating_margin        = EXCLUDED.operating_margin,
    roe                     = EXCLUDED.roe,
    roa                     = EXCLUDED.roa,
    eps_fy0                 = EXCLUDED.eps_fy0,
    eps_fy1                 = EXCLUDED.eps_fy1,
    revenue_fy0             = EXCLUDED.revenue_fy0,
    revenue_fy1             = EXCLUDED.revenue_fy1,
    ebitda_fy0              = EXCLUDED.ebitda_fy0,
    ebitda_fy1              = EXCLUDED.ebitda_fy1,
    net_profit_fy0          = EXCLUDED.net_profit_fy0,
    net_profit_fy1          = EXCLUDED.net_profit_fy1,
    total_assets            = EXCLUDED.total_assets,
    total_equity            = EXCLUDED.total_equity,
    total_debt              = EXCLUDED.total_debt,
    net_debt                = EXCLUDED.net_debt,
    cash                    = EXCLUDED.cash,
    book_value_per_share    = EXCLUDED.book_value_per_share,
    debt_to_equity          = EXCLUDED.debt_to_equity,
    current_ratio           = EXCLUDED.current_ratio,
    cfo_fy0                 = EXCLUDED.cfo_fy0,
    capex_fy0               = EXCLUDED.capex_fy0,
    fcf_fy0                 = EXCLUDED.fcf_fy0,
    analyst_rating          = EXCLUDED.analyst_rating,
    analyst_target_price    = EXCLUDED.analyst_target_price,
    analyst_strong_buy      = EXCLUDED.analyst_strong_buy,
    analyst_buy             = EXCLUDED.analyst_buy,
    analyst_hold            = EXCLUDED.analyst_hold,
    analyst_sell            = EXCLUDED.analyst_sell,
    analyst_strong_sell     = EXCLUDED.analyst_strong_sell,
    shares_outstanding      = EXCLUDED.shares_outstanding,
    universe_built_at       = NOW()
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--codes", nargs="+")
    args = parser.parse_args()

    conn = psycopg2.connect(DB_URL)
    cur  = conn.cursor()

    if args.codes:
        placeholders = ",".join(["%s"] * len(args.codes))
        code_filter = f"WHERE c.asx_code IN ({placeholders})"
        params = [c.upper() for c in args.codes]
    else:
        code_filter = ""
        params = []

    sql = UPSERT_SQL.format(code_filter=code_filter)

    log.info(f"Building screener.universe {'for ' + str(args.codes) if args.codes else '(all stocks)'}…")
    cur.execute(sql, params)
    n = cur.rowcount
    conn.commit()

    cur.close()
    conn.close()
    log.info(f"DONE — {n:,} rows upserted into screener.universe")


if __name__ == "__main__":
    main()
