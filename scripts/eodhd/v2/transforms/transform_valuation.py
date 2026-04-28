"""
Transform: staging.highlights + staging.valuation → market.valuation_snapshot
==============================================================================
Merges the two staging snapshot tables into a single valuation record per stock.
staging.highlights  → market/valuation ratios, EPS, revenue, margins
staging.valuation   → trailing/forward PE, EV, EV/Revenue, EV/EBITDA

Full run: truncates market.valuation_snapshot first.
Partial run (--codes): upsert only.

Usage:
    python scripts/eodhd/v2/transforms/transform_valuation.py
    python scripts/eodhd/v2/transforms/transform_valuation.py --codes BHP CBA
"""

import logging
import os
import argparse
from datetime import date

import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv("DATABASE_URL_SYNC",
           "postgresql://asx_user:asx_secure_2024@localhost:5432/asx_screener")

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

TODAY = date.today()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--codes", nargs="+")
    args = parser.parse_args()

    is_full_run = not args.codes

    conn = psycopg2.connect(DB_URL)
    cur  = conn.cursor()

    if is_full_run:
        log.info("Full run — truncating market.valuation_snapshot …")
        cur.execute("TRUNCATE TABLE market.valuation_snapshot")
        conn.commit()

    code_filter = ""
    params = []
    if args.codes:
        placeholders = ",".join(["%s"] * len(args.codes))
        code_filter = f"WHERE h.asx_code IN ({placeholders})"
        params = [c.upper() for c in args.codes]

    cur.execute(f"""
        SELECT
            h.asx_code,
            h.market_capitalization,
            h.pe_ratio,
            h.peg_ratio,
            v.price_book_mrq,
            v.price_sales_ttm,
            h.dividend_yield,
            h.dividend_share,
            h.earnings_share,
            h.eps_estimate_current_year,
            h.eps_estimate_next_year,
            h.revenue_ttm,
            h.gross_profit_ttm,
            h.ebitda,
            h.profit_margin,
            h.operating_margin_ttm,
            h.return_on_equity_ttm,
            h.return_on_assets_ttm,
            h.quarterly_earnings_growth_yoy,
            h.quarterly_revenue_growth_yoy,
            h.most_recent_quarter,
            h.wall_street_target_price,
            h.book_value,
            h.revenue_per_share_ttm,
            v.trailing_pe,
            v.forward_pe,
            v.enterprise_value,
            v.enterprise_value_revenue,
            v.enterprise_value_ebitda,
            h.snapshot_date
        FROM staging.highlights h
        LEFT JOIN staging.valuation v ON v.asx_code = h.asx_code
        {code_filter}
        ORDER BY h.asx_code
    """, params)

    rows = cur.fetchall()
    log.info(f"Processing {len(rows):,} valuation records …")

    if rows:
        transformed = [
            (
                r[0],   # asx_code
                r[1],   # market_cap
                r[2],   # pe_ratio
                r[3],   # peg_ratio
                r[4],   # price_to_book
                r[5],   # price_to_sales
                r[6],   # dividend_yield
                r[7],   # dividend_per_share
                r[8],   # eps_ttm
                r[9],   # eps_est_current_year
                r[10],  # eps_est_next_year
                r[11],  # revenue_ttm
                r[12],  # gross_profit_ttm
                r[13],  # ebitda_ttm
                r[14],  # profit_margin
                r[15],  # operating_margin
                r[16],  # roe_ttm
                r[17],  # roa_ttm
                r[18],  # quarterly_earnings_growth_yoy
                r[19],  # quarterly_revenue_growth_yoy
                r[20],  # most_recent_quarter
                r[21],  # wall_street_target_price
                r[22],  # book_value_per_share
                r[23],  # revenue_per_share
                r[24],  # trailing_pe
                r[25],  # forward_pe
                r[26],  # enterprise_value
                r[27],  # ev_to_revenue
                r[28],  # ev_to_ebitda
                r[29] or TODAY,  # snapshot_date
            )
            for r in rows
        ]

        execute_values(cur, """
            INSERT INTO market.valuation_snapshot (
                asx_code,
                market_cap, pe_ratio, peg_ratio, price_to_book, price_to_sales,
                dividend_yield, dividend_per_share, eps_ttm,
                eps_est_current_year, eps_est_next_year,
                revenue_ttm, gross_profit_ttm, ebitda_ttm,
                profit_margin, operating_margin, roe_ttm, roa_ttm,
                quarterly_earnings_growth_yoy, quarterly_revenue_growth_yoy,
                most_recent_quarter, wall_street_target_price,
                book_value_per_share, revenue_per_share,
                trailing_pe, forward_pe, enterprise_value,
                ev_to_revenue, ev_to_ebitda,
                snapshot_date, data_source
            ) VALUES %s
            ON CONFLICT (asx_code) DO UPDATE SET
                market_cap                      = EXCLUDED.market_cap,
                pe_ratio                        = EXCLUDED.pe_ratio,
                peg_ratio                       = EXCLUDED.peg_ratio,
                price_to_book                   = EXCLUDED.price_to_book,
                price_to_sales                  = EXCLUDED.price_to_sales,
                dividend_yield                  = EXCLUDED.dividend_yield,
                dividend_per_share              = EXCLUDED.dividend_per_share,
                eps_ttm                         = EXCLUDED.eps_ttm,
                eps_est_current_year            = EXCLUDED.eps_est_current_year,
                eps_est_next_year               = EXCLUDED.eps_est_next_year,
                revenue_ttm                     = EXCLUDED.revenue_ttm,
                gross_profit_ttm                = EXCLUDED.gross_profit_ttm,
                ebitda_ttm                      = EXCLUDED.ebitda_ttm,
                profit_margin                   = EXCLUDED.profit_margin,
                operating_margin                = EXCLUDED.operating_margin,
                roe_ttm                         = EXCLUDED.roe_ttm,
                roa_ttm                         = EXCLUDED.roa_ttm,
                quarterly_earnings_growth_yoy   = EXCLUDED.quarterly_earnings_growth_yoy,
                quarterly_revenue_growth_yoy    = EXCLUDED.quarterly_revenue_growth_yoy,
                most_recent_quarter             = EXCLUDED.most_recent_quarter,
                wall_street_target_price        = EXCLUDED.wall_street_target_price,
                book_value_per_share            = EXCLUDED.book_value_per_share,
                revenue_per_share               = EXCLUDED.revenue_per_share,
                trailing_pe                     = EXCLUDED.trailing_pe,
                forward_pe                      = EXCLUDED.forward_pe,
                enterprise_value                = EXCLUDED.enterprise_value,
                ev_to_revenue                   = EXCLUDED.ev_to_revenue,
                ev_to_ebitda                    = EXCLUDED.ev_to_ebitda,
                snapshot_date                   = EXCLUDED.snapshot_date,
                updated_at                      = NOW()
        """, [t + ("eodhd",) for t in transformed], page_size=1000)

    conn.commit()
    cur.close()
    conn.close()
    log.info(f"DONE — {len(rows):,} rows upserted into market.valuation_snapshot")


if __name__ == "__main__":
    main()
