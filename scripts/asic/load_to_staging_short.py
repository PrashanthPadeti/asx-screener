"""
ASIC Short Positions — Staging Loader
========================================
Reads the most recently downloaded ASIC CSV from the raw zone and
upserts into staging_au.short_positions.

staging_au.short_positions schema:
    report_date   DATE           (the trading date the report covers)
    asx_code      VARCHAR(10)
    short_shares  BIGINT         (gross short position in shares)
    total_issued  BIGINT         (total product / shares in issue)
    short_pct     NUMERIC(10,6)  (% of total product in issue, e.g. 1.23 = 1.23%)

ASIC CSV — two formats supported:

  Legacy format (pre-2026):
    Date,Product,Headline Stock Description,Short Position,Total Product in Issue,% of Total Product in Issue
    29/04/2026,BHP,BHP GROUP LIMITED,"1234567","3000000000","0.0412"

  New format (2026+, no Date column — date taken from filename):
    Product,Product Code,Reported Short Positions,Total Product in Issue,% of Total Product in Issue Reported as Short Positions
    BHP GROUP LIMITED,BHP,1234567,3000000000,.0412

Usage:
    python scripts/asic/load_to_staging_short.py
    python scripts/asic/load_to_staging_short.py --date 2026-04-29
    python scripts/asic/load_to_staging_short.py --file /path/to/file.csv.gz
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
INSERT INTO staging_au.short_positions
    (loaded_at, source_file, report_date, asx_code,
     short_shares, total_issued, short_pct)
VALUES %s
ON CONFLICT (report_date, asx_code) DO UPDATE SET
    loaded_at    = EXCLUDED.loaded_at,
    source_file  = EXCLUDED.source_file,
    short_shares = EXCLUDED.short_shares,
    total_issued = EXCLUDED.total_issued,
    short_pct    = EXCLUDED.short_pct
"""


def find_latest_file() -> Path | None:
    files = sorted(OUT_DIR.glob("*.csv.gz"), reverse=True)
    return files[0] if files else None


def parse_asic_date(s: str) -> date:
    return datetime.strptime(s.strip(), "%d/%m/%Y").date()


def date_from_filename(filepath: Path) -> date | None:
    """Extract date from filename like 20260513.csv.gz → 2026-05-13."""
    import re
    m = re.search(r"(\d{8})", filepath.stem)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y%m%d").date()
    except ValueError:
        return None


def load_file(filepath: Path, conn) -> int:
    """Parse the ASIC CSV and upsert into staging_au.short_positions. Returns row count."""
    log.info(f"Loading {filepath.name} → staging_au.short_positions …")

    with gzip.open(filepath, "rt", encoding="utf-8-sig") as f:
        content = f.read()

    reader = csv.DictReader(io.StringIO(content))
    headers = reader.fieldnames or []
    # Normalise header names for comparison
    headers_norm = [h.strip().strip('"') for h in headers]

    # Detect format: new format has "Product Code", legacy has "Date"
    is_new_format = "Product Code" in headers_norm
    log.info(f"  CSV format: {'new (2026+)' if is_new_format else 'legacy'} "
             f"— headers: {headers_norm[:5]}")

    # For new format, date comes from filename
    filename_date: date | None = None
    if is_new_format:
        filename_date = date_from_filename(filepath)
        if filename_date is None:
            log.error(f"  Cannot determine report date from filename: {filepath.name}")
            return 0
        log.info(f"  Report date from filename: {filename_date.isoformat()}")

    now   = datetime.now(tz=timezone.utc)
    fname = filepath.name
    rows, skipped = [], 0

    for raw in reader:
        row = {k.strip().strip('"'): v.strip().strip('"') for k, v in raw.items()}

        if is_new_format:
            asx_code = row.get("Product Code", "").strip().upper()
        else:
            asx_code = row.get("Product", "").strip().upper()

        if not asx_code or len(asx_code) > 10:
            skipped += 1
            continue

        try:
            if is_new_format:
                report_date   = filename_date
                short_shares_s = row.get("Reported Short Positions", "").replace(",", "")
                short_shares  = int(short_shares_s) if short_shares_s else None
                short_pct_s   = row.get("% of Total Product in Issue Reported as Short Positions", "").replace(",", "")
                short_pct     = float(short_pct_s) if short_pct_s else None
            else:
                report_date   = parse_asic_date(row["Date"])
                short_shares  = int(row["Short Position"].replace(",", "")) \
                                if row.get("Short Position") else None
                short_pct_s   = row.get("% of Total Product in Issue", "").replace(",", "")
                short_pct     = float(short_pct_s) if short_pct_s else None

            total_issued_s = row.get("Total Product in Issue", "").replace(",", "")
            total_issued   = int(total_issued_s) if total_issued_s else None
        except (ValueError, KeyError) as e:
            log.debug(f"  Skip {asx_code}: {e}")
            skipped += 1
            continue

        rows.append((now, fname, report_date, asx_code, short_shares, total_issued, short_pct))

    if not rows:
        log.warning("  No valid rows parsed — check CSV format")
        return 0

    cur = conn.cursor()
    execute_values(cur, UPSERT_SQL, rows, page_size=500)
    conn.commit()
    cur.close()

    log.info(f"  ✓ {len(rows):,} rows upserted | {skipped} skipped")
    return len(rows)


def main():
    parser = argparse.ArgumentParser(
        description="Load ASIC short positions into staging_au.short_positions"
    )
    parser.add_argument("--date", help="Load file for YYYY-MM-DD (default: most recent)")
    parser.add_argument("--file", help="Load a specific file path (overrides --date)")
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

    log.info("Staging load complete.")


if __name__ == "__main__":
    main()
