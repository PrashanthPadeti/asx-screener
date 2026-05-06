"""
ASX Screener — Period Metrics Compute Engine
=============================================
Pre-computes period H/L/AvgVol for all instruments from market.daily_prices
and upserts into market.period_metrics.

Periods: 1D, 1W, 1M, 3M, 6M, 1Y, 52W

Run daily after market close (after price ingest):
    python compute/engine/period_metrics_compute.py
    python compute/engine/period_metrics_compute.py --codes BHP CBA
"""

import os
import sys
import logging
import argparse
from datetime import datetime, timezone

import psycopg2
import psycopg2.extensions
from psycopg2.extras import execute_values
from dotenv import load_dotenv

_DEC2FLOAT = psycopg2.extensions.new_type(
    psycopg2.extensions.DECIMAL.values,
    "DEC2FLOAT",
    lambda value, curs: float(value) if value is not None else None,
)
psycopg2.extensions.register_type(_DEC2FLOAT)

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


# Calendar-day lookbacks for each period window
WINDOWS = {
    "1d":  3,    # last 3 cal days — catches Mon after a weekend
    "1w":  7,
    "1m":  35,
    "3m":  100,
    "6m":  185,
    "1y":  365,
    "52w": 364,  # exactly 52 × 7
}

# SQL: single-pass aggregation — all windows in one query per stock batch
COMPUTE_SQL = """
    SELECT
        asx_code,
        -- 1D
        MAX(high)  FILTER (WHERE time >= CURRENT_DATE - %(d_1d)s)                AS high_1d,
        MIN(low)   FILTER (WHERE time >= CURRENT_DATE - %(d_1d)s)                AS low_1d,
        ROUND(AVG(volume) FILTER (WHERE time >= CURRENT_DATE - %(d_1d)s))::BIGINT AS avg_volume_1d,
        -- 1W
        MAX(high)  FILTER (WHERE time >= CURRENT_DATE - %(d_1w)s)                AS high_1w,
        MIN(low)   FILTER (WHERE time >= CURRENT_DATE - %(d_1w)s)                AS low_1w,
        ROUND(AVG(volume) FILTER (WHERE time >= CURRENT_DATE - %(d_1w)s))::BIGINT AS avg_volume_1w,
        -- 1M
        MAX(high)  FILTER (WHERE time >= CURRENT_DATE - %(d_1m)s)                AS high_1m,
        MIN(low)   FILTER (WHERE time >= CURRENT_DATE - %(d_1m)s)                AS low_1m,
        ROUND(AVG(volume) FILTER (WHERE time >= CURRENT_DATE - %(d_1m)s))::BIGINT AS avg_volume_1m,
        -- 3M
        MAX(high)  FILTER (WHERE time >= CURRENT_DATE - %(d_3m)s)                AS high_3m,
        MIN(low)   FILTER (WHERE time >= CURRENT_DATE - %(d_3m)s)                AS low_3m,
        ROUND(AVG(volume) FILTER (WHERE time >= CURRENT_DATE - %(d_3m)s))::BIGINT AS avg_volume_3m,
        -- 6M
        MAX(high)  FILTER (WHERE time >= CURRENT_DATE - %(d_6m)s)                AS high_6m,
        MIN(low)   FILTER (WHERE time >= CURRENT_DATE - %(d_6m)s)                AS low_6m,
        ROUND(AVG(volume) FILTER (WHERE time >= CURRENT_DATE - %(d_6m)s))::BIGINT AS avg_volume_6m,
        -- 1Y
        MAX(high)  FILTER (WHERE time >= CURRENT_DATE - %(d_1y)s)                AS high_1y,
        MIN(low)   FILTER (WHERE time >= CURRENT_DATE - %(d_1y)s)                AS low_1y,
        ROUND(AVG(volume) FILTER (WHERE time >= CURRENT_DATE - %(d_1y)s))::BIGINT AS avg_volume_1y,
        -- 52W
        MAX(high)  FILTER (WHERE time >= CURRENT_DATE - %(d_52w)s)               AS high_52w,
        MIN(low)   FILTER (WHERE time >= CURRENT_DATE - %(d_52w)s)               AS low_52w,
        ROUND(AVG(volume) FILTER (WHERE time >= CURRENT_DATE - %(d_52w)s))::BIGINT AS avg_volume_52w
    FROM market.daily_prices
    {where_clause}
    GROUP BY asx_code
    HAVING COUNT(*) >= 1
"""

UPSERT_SQL = """
    INSERT INTO market.period_metrics (
        asx_code, computed_date,
        high_1d,  low_1d,  avg_volume_1d,
        high_1w,  low_1w,  avg_volume_1w,
        high_1m,  low_1m,  avg_volume_1m,
        high_3m,  low_3m,  avg_volume_3m,
        high_6m,  low_6m,  avg_volume_6m,
        high_1y,  low_1y,  avg_volume_1y,
        high_52w, low_52w, avg_volume_52w
    ) VALUES %s
    ON CONFLICT (asx_code, computed_date) DO UPDATE SET
        high_1d  = EXCLUDED.high_1d,  low_1d  = EXCLUDED.low_1d,  avg_volume_1d  = EXCLUDED.avg_volume_1d,
        high_1w  = EXCLUDED.high_1w,  low_1w  = EXCLUDED.low_1w,  avg_volume_1w  = EXCLUDED.avg_volume_1w,
        high_1m  = EXCLUDED.high_1m,  low_1m  = EXCLUDED.low_1m,  avg_volume_1m  = EXCLUDED.avg_volume_1m,
        high_3m  = EXCLUDED.high_3m,  low_3m  = EXCLUDED.low_3m,  avg_volume_3m  = EXCLUDED.avg_volume_3m,
        high_6m  = EXCLUDED.high_6m,  low_6m  = EXCLUDED.low_6m,  avg_volume_6m  = EXCLUDED.avg_volume_6m,
        high_1y  = EXCLUDED.high_1y,  low_1y  = EXCLUDED.low_1y,  avg_volume_1y  = EXCLUDED.avg_volume_1y,
        high_52w = EXCLUDED.high_52w, low_52w = EXCLUDED.low_52w, avg_volume_52w = EXCLUDED.avg_volume_52w
"""


def run(codes: list[str] | None = None):
    conn = psycopg2.connect(DB_URL)
    conn.autocommit = False
    cur = conn.cursor()

    params = {f"d_{k}": v for k, v in WINDOWS.items()}

    if codes:
        where_clause = "WHERE asx_code = ANY(%(codes)s)"
        params["codes"] = codes
    else:
        where_clause = ""

    sql = COMPUTE_SQL.format(where_clause=where_clause)

    log.info("Computing period metrics%s…", f" for {codes}" if codes else " for all stocks")
    cur.execute(sql, params)
    rows = cur.fetchall()
    log.info("Fetched %d stocks from daily_prices", len(rows))

    if not rows:
        log.warning("No rows returned — nothing to upsert")
        conn.close()
        return

    today = datetime.now(timezone.utc).date()
    records = [
        (
            r[0],    # asx_code
            today,   # computed_date
            r[1], r[2], r[3],    # 1d
            r[4], r[5], r[6],    # 1w
            r[7], r[8], r[9],    # 1m
            r[10], r[11], r[12], # 3m
            r[13], r[14], r[15], # 6m
            r[16], r[17], r[18], # 1y
            r[19], r[20], r[21], # 52w
        )
        for r in rows
    ]

    execute_values(cur, UPSERT_SQL, records, page_size=500)
    conn.commit()
    log.info("Upserted %d rows into market.period_metrics for %s", len(records), today)
    cur.close()
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compute period H/L/AvgVol metrics")
    parser.add_argument("--codes", nargs="+", metavar="CODE", help="Limit to specific ASX codes")
    args = parser.parse_args()

    start = datetime.now()
    run(codes=[c.upper() for c in args.codes] if args.codes else None)
    elapsed = (datetime.now() - start).total_seconds()
    log.info("Done in %.1fs", elapsed)
