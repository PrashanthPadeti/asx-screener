"""
ASIC Short Positions — Transform
====================================
staging.short_positions → market.short_positions

Computes the week-over-week (WoW) change in short interest % for each stock
and writes the result to market.short_positions.

Logic:
  1. Find the most recent report_date in staging.short_positions.
  2. For each (asx_code, report_date) in that snapshot, find the prior
     snapshot (the most recent date BEFORE the current one, ≤ 14 days prior).
  3. Compute: short_pct_chg_1w = current.short_pct - prior.short_pct
  4. Upsert into market.short_positions.

Also back-fills market.short_interest from the staging data so both tables
remain consistent (market.short_interest is the TimescaleDB hypertable used
by the existing short_pct join in build_screener_universe.py).

Usage:
    python scripts/asic/transforms/transform_short.py
    python scripts/asic/transforms/transform_short.py --date 2026-04-29
"""

import argparse
import logging
import os
from datetime import date
from pathlib import Path

import psycopg2
import psycopg2.extensions
from psycopg2.extras import execute_values
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

# Cast NUMERIC → float
_DEC2FLOAT = psycopg2.extensions.new_type(
    psycopg2.extensions.DECIMAL.values,
    "DEC2FLOAT",
    lambda v, c: float(v) if v is not None else None,
)
psycopg2.extensions.register_type(_DEC2FLOAT)


UPSERT_MARKET_SQL = """
INSERT INTO market.short_positions
    (report_date, asx_code, short_pct, short_shares, short_pct_chg_1w, updated_at)
VALUES %s
ON CONFLICT (report_date, asx_code) DO UPDATE SET
    short_pct         = EXCLUDED.short_pct,
    short_shares      = EXCLUDED.short_shares,
    short_pct_chg_1w  = EXCLUDED.short_pct_chg_1w,
    updated_at        = NOW()
"""

# Back-fill market.short_interest (used by existing golden record join)
UPSERT_SI_SQL = """
INSERT INTO market.short_interest
    (time, asx_code, gross_short_position, total_product_short_pct,
     gross_short_sales, reported_short_pct)
VALUES %s
ON CONFLICT (time, asx_code) DO UPDATE SET
    gross_short_position    = EXCLUDED.gross_short_position,
    total_product_short_pct = EXCLUDED.total_product_short_pct,
    reported_short_pct      = EXCLUDED.reported_short_pct
"""


def get_report_date(conn, explicit_date: str | None) -> date | None:
    """Return the report_date to process: explicit or most recent in staging."""
    cur = conn.cursor()
    if explicit_date:
        target = date.fromisoformat(explicit_date)
        cur.execute(
            "SELECT COUNT(*) FROM staging.short_positions WHERE report_date = %s",
            (target,)
        )
        cnt = cur.fetchone()[0]
        cur.close()
        if cnt == 0:
            log.error(f"No staging rows for date {target}")
            return None
        return target

    cur.execute("SELECT MAX(report_date) FROM staging.short_positions")
    row = cur.fetchone()
    cur.close()
    return row[0] if row else None


def transform(conn, report_date: date) -> int:
    """
    Build market.short_positions rows for `report_date` and upsert.
    Returns number of rows written.
    """
    cur = conn.cursor()

    # ── Load current snapshot ──────────────────────────────────────────────────
    cur.execute("""
        SELECT asx_code, short_pct, short_shares
        FROM   staging.short_positions
        WHERE  report_date = %s
    """, (report_date,))
    current = {r[0]: (r[1], r[2]) for r in cur.fetchall()}

    if not current:
        log.warning(f"No staging rows for {report_date}")
        cur.close()
        return 0

    log.info(f"Processing {len(current):,} stocks for {report_date}")

    # ── Find prior report date (most recent before this one, ≤ 14 days back) ──
    cur.execute("""
        SELECT DISTINCT report_date
        FROM   staging.short_positions
        WHERE  report_date < %s
          AND  report_date >= %s - INTERVAL '14 days'
        ORDER  BY report_date DESC
        LIMIT  1
    """, (report_date, report_date))
    prior_row = cur.fetchone()
    prior_date = prior_row[0] if prior_row else None

    prior: dict[str, float] = {}
    if prior_date:
        cur.execute("""
            SELECT asx_code, short_pct
            FROM   staging.short_positions
            WHERE  report_date = %s
        """, (prior_date,))
        prior = {r[0]: r[1] for r in cur.fetchall()}
        log.info(f"  Prior snapshot: {prior_date} ({len(prior):,} stocks)")
    else:
        log.info("  No prior snapshot found — chg_1w will be NULL for all rows")

    cur.close()

    # ── Build rows ────────────────────────────────────────────────────────────
    from datetime import datetime, timezone
    now = datetime.now(tz=timezone.utc)

    market_rows = []
    si_rows     = []

    for asx_code, (short_pct, short_shares) in current.items():
        chg_1w = None
        if prior and asx_code in prior and prior[asx_code] is not None and short_pct is not None:
            chg_1w = round(short_pct - prior[asx_code], 6)

        market_rows.append((
            report_date, asx_code, short_pct, short_shares, chg_1w, now,
        ))
        si_rows.append((
            now.replace(
                year=report_date.year, month=report_date.month, day=report_date.day,
                hour=0, minute=0, second=0, microsecond=0
            ),
            asx_code,
            short_shares,      # gross_short_position
            short_pct,         # total_product_short_pct
            None,              # gross_short_sales (not in ASIC aggregated CSV)
            short_pct,         # reported_short_pct
        ))

    # ── Upsert market.short_positions ─────────────────────────────────────────
    cur = conn.cursor()
    execute_values(cur, UPSERT_MARKET_SQL, market_rows, page_size=500)

    # ── Back-fill market.short_interest ────────────────────────────────────────
    execute_values(cur, UPSERT_SI_SQL, si_rows, page_size=500)

    conn.commit()
    cur.close()

    log.info(f"  ✓ {len(market_rows):,} rows → market.short_positions")
    log.info(f"  ✓ {len(si_rows):,} rows → market.short_interest (back-fill)")
    return len(market_rows)


def main():
    parser = argparse.ArgumentParser(
        description="Transform staging.short_positions → market.short_positions"
    )
    parser.add_argument(
        "--date",
        help="Report date to process YYYY-MM-DD (default: most recent in staging)"
    )
    args = parser.parse_args()

    conn = psycopg2.connect(DB_URL)
    try:
        report_date = get_report_date(conn, args.date)
        if report_date is None:
            log.error("No short position data found in staging")
            raise SystemExit(1)

        log.info(f"Transforming short positions for report date: {report_date}")
        n = transform(conn, report_date)
        if n == 0:
            log.error("No rows written — check staging data")
            raise SystemExit(1)
    finally:
        conn.close()

    log.info("Transform complete.")


if __name__ == "__main__":
    main()
