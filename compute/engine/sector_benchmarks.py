"""
ASX Screener — Sector Benchmarks Engine
=========================================
Computes median + P25/P75 benchmark statistics per GICS sector
from screener.universe and writes to market.sector_benchmarks.

Run weekly after build_screener_universe.py + composite_score.py.
The Peers tab uses this table to show "vs sector" context.

Usage:
    python compute/engine/sector_benchmarks.py
    python compute/engine/sector_benchmarks.py --dry-run
"""

import argparse
import logging
import os
from datetime import datetime, timezone

import psycopg2
import psycopg2.extensions
from psycopg2.extras import execute_values
import pandas as pd
import numpy as np
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv(
    "DATABASE_URL_SYNC",
    "postgresql://asx_user:asx_secure_2024@localhost:5432/asx_screener"
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

_DEC2FLOAT = psycopg2.extensions.new_type(
    psycopg2.extensions.DECIMAL.values, "DEC2FLOAT",
    lambda v, c: float(v) if v is not None else None,
)
psycopg2.extensions.register_type(_DEC2FLOAT)

COLS = [
    "gics_sector",
    "pe_ratio", "price_to_book", "ev_to_ebitda",
    "dividend_yield", "grossed_up_yield", "franking_pct",
    "roe", "net_margin", "gross_margin", "ebitda_margin",
    "revenue_growth_1y", "earnings_growth_1y",
    "debt_to_equity", "current_ratio",
    "return_1y", "return_ytd",
    "market_cap",
]


def _med(s: pd.Series) -> float | None:
    v = s.dropna()
    return float(np.median(v)) if len(v) >= 3 else None


def _pct(s: pd.Series, q: float) -> float | None:
    v = s.dropna()
    return float(np.percentile(v, q * 100)) if len(v) >= 3 else None


def run(conn, dry_run: bool = False) -> int:
    cur = conn.cursor()
    col_list = ", ".join(COLS)
    cur.execute(f"""
        SELECT {col_list}
        FROM screener.universe
        WHERE status = 'active'
          AND price IS NOT NULL
          AND gics_sector IS NOT NULL
    """)
    rows = cur.fetchall()
    cur.close()

    df = pd.DataFrame(rows, columns=COLS)
    log.info(f"Loaded {len(df):,} stocks across {df['gics_sector'].nunique()} sectors")

    for col in COLS[1:]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Exclude nonsensical PE values
    df.loc[df["pe_ratio"] <= 0, "pe_ratio"]  = np.nan
    df.loc[df["pe_ratio"] > 200, "pe_ratio"] = np.nan

    now = datetime.now(tz=timezone.utc)
    upsert_rows = []

    for sector, grp in df.groupby("gics_sector"):
        n = len(grp)
        if n < 2:
            continue

        row = (
            sector,
            n,
            # PE
            _pct(grp["pe_ratio"], 0.25),
            _med(grp["pe_ratio"]),
            _pct(grp["pe_ratio"], 0.75),
            # PB
            _pct(grp["price_to_book"], 0.25),
            _med(grp["price_to_book"]),
            _pct(grp["price_to_book"], 0.75),
            # EV/EBITDA
            _pct(grp["ev_to_ebitda"], 0.25),
            _med(grp["ev_to_ebitda"]),
            _pct(grp["ev_to_ebitda"], 0.75),
            # Dividends
            _med(grp["dividend_yield"]),
            _med(grp["grossed_up_yield"]),
            _med(grp["franking_pct"]),
            # ROE
            _pct(grp["roe"], 0.25),
            _med(grp["roe"]),
            _pct(grp["roe"], 0.75),
            # Net margin
            _pct(grp["net_margin"], 0.25),
            _med(grp["net_margin"]),
            _pct(grp["net_margin"], 0.75),
            # Other margins
            _med(grp["gross_margin"]),
            _med(grp["ebitda_margin"]),
            # Growth
            _med(grp["revenue_growth_1y"]),
            _med(grp["earnings_growth_1y"]),
            # Leverage
            _med(grp["debt_to_equity"]),
            _med(grp["current_ratio"]),
            # Returns
            _med(grp["return_1y"]),
            _med(grp["return_ytd"]),
            # Market cap
            _med(grp["market_cap"]),
            # updated_at
            now,
        )
        upsert_rows.append(row)
        log.info(f"  {sector:40s}  n={n:4d}  PE_median={row[3]}")

    if dry_run:
        log.info(f"Dry-run — would write {len(upsert_rows)} sector rows.")
        return len(upsert_rows)

    UPSERT_SQL = """
        INSERT INTO market.sector_benchmarks (
            gics_sector, stock_count,
            pe_ratio_p25, pe_ratio_median, pe_ratio_p75,
            price_to_book_p25, price_to_book_median, price_to_book_p75,
            ev_to_ebitda_p25, ev_to_ebitda_median, ev_to_ebitda_p75,
            dividend_yield_median, grossed_up_yield_median, franking_pct_median,
            roe_p25, roe_median, roe_p75,
            net_margin_p25, net_margin_median, net_margin_p75,
            gross_margin_median, ebitda_margin_median,
            revenue_growth_1y_median, earnings_growth_1y_median,
            debt_to_equity_median, current_ratio_median,
            return_1y_median, return_ytd_median,
            market_cap_median,
            updated_at
        ) VALUES %s
        ON CONFLICT (gics_sector) DO UPDATE SET
            stock_count              = EXCLUDED.stock_count,
            pe_ratio_p25             = EXCLUDED.pe_ratio_p25,
            pe_ratio_median          = EXCLUDED.pe_ratio_median,
            pe_ratio_p75             = EXCLUDED.pe_ratio_p75,
            price_to_book_p25        = EXCLUDED.price_to_book_p25,
            price_to_book_median     = EXCLUDED.price_to_book_median,
            price_to_book_p75        = EXCLUDED.price_to_book_p75,
            ev_to_ebitda_p25         = EXCLUDED.ev_to_ebitda_p25,
            ev_to_ebitda_median      = EXCLUDED.ev_to_ebitda_median,
            ev_to_ebitda_p75         = EXCLUDED.ev_to_ebitda_p75,
            dividend_yield_median    = EXCLUDED.dividend_yield_median,
            grossed_up_yield_median  = EXCLUDED.grossed_up_yield_median,
            franking_pct_median      = EXCLUDED.franking_pct_median,
            roe_p25                  = EXCLUDED.roe_p25,
            roe_median               = EXCLUDED.roe_median,
            roe_p75                  = EXCLUDED.roe_p75,
            net_margin_p25           = EXCLUDED.net_margin_p25,
            net_margin_median        = EXCLUDED.net_margin_median,
            net_margin_p75           = EXCLUDED.net_margin_p75,
            gross_margin_median      = EXCLUDED.gross_margin_median,
            ebitda_margin_median     = EXCLUDED.ebitda_margin_median,
            revenue_growth_1y_median = EXCLUDED.revenue_growth_1y_median,
            earnings_growth_1y_median= EXCLUDED.earnings_growth_1y_median,
            debt_to_equity_median    = EXCLUDED.debt_to_equity_median,
            current_ratio_median     = EXCLUDED.current_ratio_median,
            return_1y_median         = EXCLUDED.return_1y_median,
            return_ytd_median        = EXCLUDED.return_ytd_median,
            market_cap_median        = EXCLUDED.market_cap_median,
            updated_at               = NOW()
    """

    cur = conn.cursor()
    execute_values(cur, UPSERT_SQL, upsert_rows, page_size=50)
    conn.commit()
    cur.close()

    log.info(f"  ✓ {len(upsert_rows)} sector benchmarks written to market.sector_benchmarks")
    return len(upsert_rows)


def main():
    parser = argparse.ArgumentParser(description="Compute sector benchmark statistics")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    conn = psycopg2.connect(DB_URL)
    try:
        n = run(conn, dry_run=args.dry_run)
    finally:
        conn.close()

    log.info(f"Sector benchmarks complete — {n} sectors processed.")


if __name__ == "__main__":
    main()
