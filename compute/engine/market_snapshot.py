"""
ASX Screener — Market Snapshot Engine
======================================
Pre-computes daily market-level aggregates into 4 snapshot tables.
Run once per day, after build_screener_universe.py completes.

Output tables (all idempotent — safe to re-run for same date):
  market.index_snapshots   — ASX200 / ASX300 breadth stats
  market.sector_snapshots  — per-GICS sector aggregates
  market.mover_snapshots   — GAINER, LOSER, ACTIVE, BUYING, SELLING
  market.exdiv_snapshots   — stocks with ex-div dates in the next 14 days

Usage:
    python compute/engine/market_snapshot.py
    python compute/engine/market_snapshot.py --date 2026-05-10
"""

import argparse
import logging
import os
from datetime import date, datetime

import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv(
    "DATABASE_URL_SYNC",
    "postgresql://asx_user:asx_secure_2024@localhost:5432/asx_screener",
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# How many stocks to keep per snapshot type
TOP_N = 10
# Ex-div lookahead window (days)
EXDIV_DAYS = 14


# ─── helpers ──────────────────────────────────────────────────────────────────

def _f(v) -> float | None:
    return float(v) if v is not None else None

def _i(v) -> int | None:
    return int(v) if v is not None else None


# ─── 1. Index snapshots ───────────────────────────────────────────────────────

def compute_index_snapshots(cur, snap_date: date) -> int:
    """ASX200 and ASX300 breadth stats from screener.universe."""
    rows = []
    for index_code, flag_col in [("ASX200", "is_asx200"), ("ASX300", "is_asx300")]:
        cur.execute(f"""
            SELECT
                COUNT(*)                                                        AS stock_count,
                COUNT(*) FILTER (WHERE return_1w > 0)                          AS gainers,
                COUNT(*) FILTER (WHERE return_1w < 0)                          AS losers,
                COUNT(*) FILTER (WHERE return_1w = 0 OR return_1w IS NULL)     AS unchanged,
                ROUND(AVG(return_1w) FILTER (WHERE return_1w IS NOT NULL)::numeric, 4)
                                                                               AS avg_return_1w,
                ROUND((SUM(market_cap) / 1000.0)::numeric, 2)                 AS total_market_cap_bn
            FROM screener.universe
            WHERE {flag_col} = TRUE
              AND status = 'active'
        """)
        r = cur.fetchone()
        rows.append((
            snap_date, index_code,
            _i(r[0]), _i(r[1]), _i(r[2]), _i(r[3]),
            _f(r[4]), _f(r[5]),
        ))

    execute_values(cur, """
        INSERT INTO market.index_snapshots
            (snapshot_date, index_code, stock_count, gainers, losers, unchanged,
             avg_return_1w, total_market_cap_bn)
        VALUES %s
        ON CONFLICT (snapshot_date, index_code) DO UPDATE SET
            stock_count         = EXCLUDED.stock_count,
            gainers             = EXCLUDED.gainers,
            losers              = EXCLUDED.losers,
            unchanged           = EXCLUDED.unchanged,
            avg_return_1w       = EXCLUDED.avg_return_1w,
            total_market_cap_bn = EXCLUDED.total_market_cap_bn
    """, rows)
    return len(rows)


# ─── 2. Sector snapshots ──────────────────────────────────────────────────────

def compute_sector_snapshots(cur, snap_date: date) -> int:
    """Per-GICS sector breadth stats."""
    cur.execute("""
        SELECT
            sector,
            COUNT(*)                                                        AS stock_count,
            COUNT(*) FILTER (WHERE return_1w > 0)                          AS gainers,
            COUNT(*) FILTER (WHERE return_1w < 0)                          AS losers,
            ROUND(AVG(return_1w) FILTER (WHERE return_1w IS NOT NULL)::numeric, 4)
                                                                           AS avg_return_1w,
            ROUND((SUM(market_cap) / 1000.0)::numeric, 2)                 AS total_market_cap_bn
        FROM screener.universe
        WHERE sector IS NOT NULL
          AND status = 'active'
        GROUP BY sector
        ORDER BY SUM(market_cap) DESC NULLS LAST
    """)
    rows = [
        (snap_date, r[0], _i(r[1]), _i(r[2]), _i(r[3]), _f(r[4]), _f(r[5]))
        for r in cur.fetchall()
    ]
    if not rows:
        return 0

    execute_values(cur, """
        INSERT INTO market.sector_snapshots
            (snapshot_date, sector, stock_count, gainers, losers,
             avg_return_1w, total_market_cap_bn)
        VALUES %s
        ON CONFLICT (snapshot_date, sector) DO UPDATE SET
            stock_count         = EXCLUDED.stock_count,
            gainers             = EXCLUDED.gainers,
            losers              = EXCLUDED.losers,
            avg_return_1w       = EXCLUDED.avg_return_1w,
            total_market_cap_bn = EXCLUDED.total_market_cap_bn
    """, rows)
    return len(rows)


# ─── 3. Mover snapshots ───────────────────────────────────────────────────────

def compute_mover_snapshots(cur, snap_date: date) -> int:
    """Top gainers, losers, most-active, heavy-buying, heavy-selling."""

    # Base filter shared by all types
    BASE = """
        WHERE price > 0.10
          AND market_cap > 50
          AND status = 'active'
    """

    QUERIES = {
        "GAINER": f"""
            SELECT asx_code, company_name, sector, price, return_1w,
                   market_cap, volume, avg_volume_20d, short_pct
            FROM screener.universe
            {BASE}
              AND return_1w IS NOT NULL AND return_1w > 0
            ORDER BY return_1w DESC
            LIMIT {TOP_N}
        """,
        "LOSER": f"""
            SELECT asx_code, company_name, sector, price, return_1w,
                   market_cap, volume, avg_volume_20d, short_pct
            FROM screener.universe
            {BASE}
              AND return_1w IS NOT NULL AND return_1w < 0
            ORDER BY return_1w ASC
            LIMIT {TOP_N}
        """,
        "ACTIVE": f"""
            SELECT asx_code, company_name, sector, price, return_1w,
                   market_cap, volume, avg_volume_20d, short_pct
            FROM screener.universe
            {BASE}
              AND volume IS NOT NULL
            ORDER BY volume DESC
            LIMIT {TOP_N}
        """,
        "BUYING": f"""
            SELECT asx_code, company_name, sector, price, return_1w,
                   market_cap, volume, avg_volume_20d, short_pct
            FROM screener.universe
            {BASE}
              AND volume IS NOT NULL AND avg_volume_20d IS NOT NULL
              AND avg_volume_20d > 10000
              AND volume > avg_volume_20d * 2
              AND return_1w > 0
            ORDER BY volume DESC
            LIMIT {TOP_N}
        """,
        "SELLING": f"""
            SELECT asx_code, company_name, sector, price, return_1w,
                   market_cap, volume, avg_volume_20d, short_pct
            FROM screener.universe
            {BASE}
              AND volume IS NOT NULL AND avg_volume_20d IS NOT NULL
              AND avg_volume_20d > 10000
              AND volume > avg_volume_20d * 2
              AND return_1w < 0
            ORDER BY volume DESC
            LIMIT {TOP_N}
        """,
    }

    # Delete today's rows first (idempotent)
    cur.execute("DELETE FROM market.mover_snapshots WHERE snapshot_date = %s", (snap_date,))

    all_rows = []
    for snap_type, sql in QUERIES.items():
        cur.execute(sql)
        for rank, r in enumerate(cur.fetchall(), 1):
            all_rows.append((
                snap_date, snap_type, rank,
                r[0], r[1], r[2],          # asx_code, company_name, sector
                _f(r[3]),                   # price
                _f(r[4]),                   # return_1w
                _f(r[5]),                   # market_cap
                _i(r[6]),                   # volume
                _i(r[7]),                   # avg_volume_20d
                _f(r[8]),                   # short_pct
            ))

    if all_rows:
        execute_values(cur, """
            INSERT INTO market.mover_snapshots
                (snapshot_date, snapshot_type, rank,
                 asx_code, company_name, sector,
                 price, return_1w, market_cap,
                 volume, avg_volume_20d, short_pct)
            VALUES %s
        """, all_rows)

    return len(all_rows)


# ─── 4. Ex-div snapshots ──────────────────────────────────────────────────────

def compute_exdiv_snapshots(cur, snap_date: date) -> int:
    """Stocks with confirmed ex-div dates in the next EXDIV_DAYS days."""

    cur.execute("DELETE FROM market.exdiv_snapshots WHERE snapshot_date = %s", (snap_date,))

    # Use market.dividends for confirmed upcoming ex-dates.
    # Join screener.universe for yield/dps/franking context.
    # DISTINCT ON asx_code keeps only the soonest upcoming date per stock.
    cur.execute("""
        SELECT DISTINCT ON (d.asx_code)
            d.asx_code,
            c.company_name,
            d.ex_date,
            d.payment_date             AS pay_date,
            u.dps_ttm,
            u.dividend_yield,
            u.franking_pct
        FROM market.dividends d
        INNER JOIN screener.universe u ON u.asx_code = d.asx_code
        LEFT JOIN market.companies_current c ON c.asx_code = d.asx_code
        WHERE d.ex_date BETWEEN %s AND %s + %s
          AND u.status = 'active'
        ORDER BY d.asx_code, d.ex_date ASC
    """, (snap_date, snap_date, EXDIV_DAYS))

    rows = []
    for r in cur.fetchall():
        rows.append((
            snap_date,
            r[0],            # asx_code
            r[1],            # company_name
            r[2],            # ex_div_date
            r[3],            # pay_date
            _f(r[4]),        # dps_ttm
            _f(r[5]),        # dividend_yield
            _f(r[6]),        # franking_pct
        ))

    if rows:
        execute_values(cur, """
            INSERT INTO market.exdiv_snapshots
                (snapshot_date, asx_code, company_name,
                 ex_div_date, pay_date,
                 dps_ttm, dividend_yield, franking_pct)
            VALUES %s
            ON CONFLICT (snapshot_date, asx_code) DO UPDATE SET
                ex_div_date    = EXCLUDED.ex_div_date,
                pay_date       = EXCLUDED.pay_date,
                dps_ttm        = EXCLUDED.dps_ttm,
                dividend_yield = EXCLUDED.dividend_yield,
                franking_pct   = EXCLUDED.franking_pct
        """, rows)

    return len(rows)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--date",
        help="Snapshot date YYYY-MM-DD (default: today)",
        default=None,
    )
    args = parser.parse_args()

    snap_date = (
        datetime.strptime(args.date, "%Y-%m-%d").date()
        if args.date
        else date.today()
    )

    log.info(f"Market snapshot — {snap_date}")

    conn = psycopg2.connect(DB_URL)
    cur  = conn.cursor()

    try:
        n = compute_index_snapshots(cur, snap_date)
        conn.commit()
        log.info(f"  index_snapshots    : {n} rows")

        n = compute_sector_snapshots(cur, snap_date)
        conn.commit()
        log.info(f"  sector_snapshots   : {n} rows")

        n = compute_mover_snapshots(cur, snap_date)
        conn.commit()
        log.info(f"  mover_snapshots    : {n} rows")

        n = compute_exdiv_snapshots(cur, snap_date)
        conn.commit()
        log.info(f"  exdiv_snapshots    : {n} rows")

    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

    log.info("DONE")


if __name__ == "__main__":
    main()
