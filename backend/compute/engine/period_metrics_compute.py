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
from pathlib import Path

# The database credential lives in the environment, never in source.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.core.db import get_database_url_sync  # noqa: E402


_DEC2FLOAT = psycopg2.extensions.new_type(
    psycopg2.extensions.DECIMAL.values,
    "DEC2FLOAT",
    lambda value, curs: float(value) if value is not None else None,
)
psycopg2.extensions.register_type(_DEC2FLOAT)

load_dotenv()

DB_URL = get_database_url_sync()

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


#: The producer's source domain.
#:
#: Every code with any price history owes a row for today: COMPUTE_SQL's only
#: eligibility rule is HAVING COUNT(*) >= 1, with no date bound and no company
#: join. Unlike technical_compute this producer is not narrower than its
#: consumer, so the domain is simply what the price table holds.
#:
#: Stated as its own query against market.daily_prices rather than reusing
#: COMPUTE_SQL's projection. Deriving the expected set from the same statement
#: that produced the rows would make the comparison circular -- it would agree
#: however wrong the statement was.
SOURCE_DOMAIN_SQL = """
    SELECT DISTINCT asx_code FROM market.daily_prices ORDER BY asx_code
"""


def run(codes: list[str] | None = None, run_id: int | None = None) -> bool:
    conn = psycopg2.connect(DB_URL)
    # Prove where this process ACTUALLY connected, before any mutation.
    # An inherited environment is intent; a live connection is fact. Outside
    # a discovery run this only logs, so the nightly pipeline is unaffected.
    from compute.engine.runtime_envelope import prove as _prove_envelope
    _prove_envelope("period_metrics_compute", conn)
    # `conn.autocommit = False` used to sit here and is gone rather than moved.
    #
    # It was always redundant -- psycopg2 connections are transactional by
    # default -- and once the envelope gate runs SELECT current_database()
    # immediately above, a transaction is open and psycopg2 refuses to change
    # the session mode: "set_session cannot be used inside a transaction".
    #
    # Moving it above the gate would have worked and would have been the wrong
    # fix: the gate must be the first thing after connect, so that no statement
    # can reach a database this process has not yet proved it is allowed to
    # touch. Deleting a line that asserts the default costs nothing.
    cur = conn.cursor()

    params = {f"d_{k}": v for k, v in WINDOWS.items()}

    if codes:
        where_clause = "WHERE asx_code = ANY(%(codes)s)"
        params["codes"] = codes
    else:
        where_clause = ""

    sql = COMPUTE_SQL.format(where_clause=where_clause)

    # Derived before the write, from the source table, independently of the
    # statement that computes the values.
    today = datetime.now(timezone.utc).date()
    cur.execute(SOURCE_DOMAIN_SQL)
    expected = {(r[0], today) for r in cur.fetchall()}

    log.info("Computing period metrics%s…", f" for {codes}" if codes else " for all stocks")
    cur.execute(sql, params)
    rows = cur.fetchall()
    log.info("Fetched %d stocks from daily_prices", len(rows))

    if not rows:
        # Not a quiet exit. An empty result while the source domain is
        # populated is the most severe form of the failure this proof exists to
        # catch -- every company missed at once -- and returning here without
        # evidence used to make it indistinguishable from a clean run.
        log.error("No rows returned — nothing to upsert")
        ok = _prove(cur, run_id, expected, set(), codes,
                    {"compute_returned_rows": 0})
        conn.commit()
        conn.close()
        return ok

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

    # RETURNING, so the actual set is what PostgreSQL persisted rather than
    # what this process submitted. The conflict action is an unconditional
    # DO UPDATE, so every record comes back.
    accepted = execute_values(
        cur, UPSERT_SQL + " RETURNING asx_code, computed_date",
        records, page_size=500, fetch=True)
    conn.commit()
    written = {(code, day) for code, day in accepted}
    log.info("Upserted %d rows into market.period_metrics for %s", len(written), today)

    ok = _prove(cur, run_id, expected, written, codes,
                {"compute_returned_rows": len(rows)})
    conn.commit()
    cur.close()
    conn.close()
    return ok


def _prove(cur, run_id, expected: set, written: set, codes, details: dict) -> bool:
    """Set equality at (asx_code, computed_date).

    The date belongs in the key. Collapsed to codes, the proof would pass on a
    run that wrote nothing today, because market.period_metrics still holds
    yesterday's row for every company -- a query asking only whether the target
    "contains" each expected code is satisfied entirely by history.
    """
    from compute.engine.run_stages import StageResult, report_population

    result = StageResult(
        "period_metrics_compute",
        frozenset(expected), frozenset(written), details,
        grain="asx_code+computed_date")
    return report_population(
        cur, run_id, result, log,
        scoped_reason=("a scoped run's expected population is not the source "
                       "domain" if codes else ""))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compute period H/L/AvgVol metrics")
    parser.add_argument("--codes", nargs="+", metavar="CODE", help="Limit to specific ASX codes")
    parser.add_argument("--run-id", type=int, default=None,
                        help="Record stage evidence against this compute run")
    args = parser.parse_args()

    start = datetime.now()
    ok = run(codes=[c.upper() for c in args.codes] if args.codes else None,
             run_id=args.run_id)
    elapsed = (datetime.now() - start).total_seconds()
    log.info("Done in %.1fs", elapsed)
    # An uncovered population must be executable, not merely logged.
    sys.exit(0 if ok else 1)
