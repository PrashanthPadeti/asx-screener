"""
ASIC Short Position Report — Loader
======================================
Reads the most recently downloaded ASIC CSV from the raw zone and
upserts into market.short_interest (TimescaleDB hypertable).

market.short_interest schema:
    time                    TIMESTAMPTZ  (the trading date the report covers)
    asx_code                VARCHAR(10)
    gross_short_position    BIGINT       (shares sold short)
    total_product_short_pct NUMERIC(8,4) (% of total shares — e.g., 1.23 means 1.23%)
    gross_short_sales       BIGINT       (NULL — ASIC report doesn't include daily sales)
    reported_short_pct      NUMERIC(8,4) (same as total_product_short_pct for ASIC data)

ASIC CSV format (one row example):
    Date,Product,Headline Stock Description,Short Position,Total Product in Issue,% of Total Product in Issue
    29/04/2026,BHP,BHP GROUP LIMITED,"1234567","3000000000","0.0412"

Note: The "% of Total Product in Issue" value is in percent (0.0412 = 0.0412%, NOT 4.12%).
      ASIC expresses this as a very small decimal for large-cap stocks.

Usage:
    python scripts/asic/load_short_positions.py
    python scripts/asic/load_short_positions.py --date 2026-04-29
    python scripts/asic/load_short_positions.py --file /path/to/file.csv.gz
"""

import argparse
import csv
import gzip
import io
import logging
import os
from datetime import date, datetime, timezone
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv()

DB_URL   = os.getenv("DATABASE_URL_SYNC",
             "postgresql://asx_user:asx_secure_2024@localhost:5432/asx_screener")
RAW_BASE = Path(os.getenv("RAW_DATA_DIR", "/opt/asx-screener/data/raw"))
OUT_DIR  = RAW_BASE / "asic" / "short_positions"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

UPSERT_SQL = """
INSERT INTO market.short_interest
    (time, asx_code, gross_short_position, total_product_short_pct,
     gross_short_sales, reported_short_pct)
VALUES %s
ON CONFLICT (time, asx_code) DO UPDATE SET
    gross_short_position    = EXCLUDED.gross_short_position,
    total_product_short_pct = EXCLUDED.total_product_short_pct,
    reported_short_pct      = EXCLUDED.reported_short_pct
"""


def find_latest_file() -> Path | None:
    """Return the most recent .csv.gz file in the raw zone, or None."""
    files = sorted(OUT_DIR.glob("*.csv.gz"), reverse=True)
    return files[0] if files else None


def parse_asic_date(s: str) -> datetime:
    """Parse ASIC date string 'DD/MM/YYYY' → UTC datetime at midnight."""
    d = datetime.strptime(s.strip(), "%d/%m/%Y")
    return d.replace(tzinfo=timezone.utc)


def load_file(filepath: Path, conn) -> int:
    """Parse the ASIC CSV and upsert into market.short_interest. Returns row count."""
    log.info(f"Loading {filepath.name} …")

    with gzip.open(filepath, "rt", encoding="utf-8-sig") as f:
        content = f.read()

    reader = csv.DictReader(io.StringIO(content))

    rows = []
    skipped = 0

    for raw in reader:
        # Normalise column names (ASIC CSV may have quoted headers with spaces)
        row = {k.strip().strip('"'): v.strip().strip('"') for k, v in raw.items()}

        asx_code = row.get("Product", "").strip().upper()
        if not asx_code:
            skipped += 1
            continue

        # Skip non-equity rows (ETFs, warrants etc. sometimes appear with codes > 4 chars)
        # but allow 3-4 char ASX equity codes
        if len(asx_code) > 5:
            skipped += 1
            continue

        try:
            report_time       = parse_asic_date(row["Date"])
            gross_short_pos   = int(row["Short Position"].replace(",", "")) if row.get("Short Position") else None
            short_pct_str     = row.get("% of Total Product in Issue", "").replace(",", "")
            short_pct         = float(short_pct_str) if short_pct_str else None
        except (ValueError, KeyError) as e:
            log.debug(f"  Skipping row {asx_code}: {e}")
            skipped += 1
            continue

        rows.append((
            report_time,
            asx_code,
            gross_short_pos,
            short_pct,      # total_product_short_pct
            None,           # gross_short_sales (not in ASIC aggregated CSV)
            short_pct,      # reported_short_pct (same source for ASIC)
        ))

    if not rows:
        log.warning("  No valid rows parsed from CSV")
        return 0

    cur = conn.cursor()
    execute_values(cur, UPSERT_SQL, rows, page_size=500)
    conn.commit()
    cur.close()

    log.info(f"  ✓ {len(rows):,} rows upserted | {skipped} skipped")
    return len(rows)


def main():
    parser = argparse.ArgumentParser(description="Load ASIC short positions into market.short_interest")
    parser.add_argument(
        "--date",
        help="Load the file for this date YYYY-MM-DD (default: most recent file)",
    )
    parser.add_argument(
        "--file",
        help="Load a specific file path (overrides --date)",
    )
    args = parser.parse_args()

    if args.file:
        filepath = Path(args.file)
    elif args.date:
        d = date.fromisoformat(args.date)
        filepath = OUT_DIR / f"{d.strftime('%Y%m%d')}.csv.gz"
    else:
        filepath = find_latest_file()

    if filepath is None or not filepath.exists():
        log.error(f"No file found: {filepath}")
        raise SystemExit(1)

    conn = psycopg2.connect(DB_URL)
    try:
        n = load_file(filepath, conn)
    finally:
        conn.close()

    if n == 0:
        log.error("No rows loaded — check CSV format")
        raise SystemExit(1)

    log.info("ASIC load complete.")


if __name__ == "__main__":
    main()
