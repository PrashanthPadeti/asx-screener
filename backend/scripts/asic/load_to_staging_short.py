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

ASIC CSV format (current — RR{YYYYMMDD}-001-SSDailyAggShortPos.csv):
    Product,Product Code,Reported Short Positions,Total Product in Issue,% of Total Product in Issue Reported as Short Positions
    3D ENERGI LTD ORDINARY,TDO,181029,524226804,.03453257

Note there is NO date column — the report date comes from the filename
(YYYYMMDD.csv.gz), which is how the downloader names each file.

Usage:
    python scripts/asic/load_to_staging_short.py
    python scripts/asic/load_to_staging_short.py --date 2026-04-29
    python scripts/asic/load_to_staging_short.py --file /path/to/file.csv.gz
    python scripts/asic/load_to_staging_short.py --all      # load every cached file
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


def date_from_filename(filepath: Path) -> date:
    """ASIC files are named YYYYMMDD.csv.gz — the report date is the stem."""
    stem = filepath.name.split(".")[0]
    return datetime.strptime(stem, "%Y%m%d").date()


def _first(row: dict, *names: str) -> str:
    """Return the first non-empty value among `names` (tolerates header changes)."""
    for n in names:
        v = row.get(n)
        if v:
            return v
    return ""


def load_file(filepath: Path, conn) -> int:
    """Parse the ASIC CSV and upsert into staging_au.short_positions. Returns row count."""
    log.info(f"Loading {filepath.name} → staging_au.short_positions …")

    try:
        report_date = date_from_filename(filepath)
    except ValueError:
        log.error(f"  Cannot derive report date from filename: {filepath.name}")
        return 0

    with gzip.open(filepath, "rt", encoding="utf-8-sig") as f:
        content = f.read()

    reader = csv.DictReader(io.StringIO(content))
    now    = datetime.now(tz=timezone.utc)
    fname  = filepath.name

    rows, skipped = [], 0

    for raw in reader:
        row = {k.strip().strip('"'): v.strip().strip('"')
               for k, v in raw.items() if k is not None}

        # Current ASIC format puts the ticker in "Product Code"; "Product" is the
        # full company name.  Older exports used "Product" for the code.
        asx_code = _first(row, "Product Code", "ASX Code", "Product").upper()
        if not asx_code or len(asx_code) > 10:
            skipped += 1
            continue

        try:
            short_shares_s = _first(row, "Reported Short Positions", "Short Position",
                                    "Short Positions").replace(",", "")
            short_shares   = int(short_shares_s) if short_shares_s else None

            total_issued_s = _first(row, "Total Product in Issue").replace(",", "")
            total_issued   = int(total_issued_s) if total_issued_s else None

            short_pct_s = _first(
                row,
                "% of Total Product in Issue Reported as Short Positions",
                "% of Total Product in Issue",
            ).replace(",", "").replace("%", "")
            short_pct = float(short_pct_s) if short_pct_s else None
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
    parser.add_argument("--all",  action="store_true",
                        help="Load every cached file (use after a backfill)")
    args = parser.parse_args()

    if args.all:
        filepaths = sorted(OUT_DIR.glob("*.csv.gz"))
        if not filepaths:
            log.error(f"No files found in {OUT_DIR}")
            raise SystemExit(1)
    elif args.file:
        filepaths = [Path(args.file)]
    elif args.date:
        d = date.fromisoformat(args.date)
        filepaths = [OUT_DIR / f"{d.strftime('%Y%m%d')}.csv.gz"]
    else:
        latest = find_latest_file()
        filepaths = [latest] if latest else []

    filepaths = [p for p in filepaths if p and p.exists()]
    if not filepaths:
        log.error("No file found to load")
        raise SystemExit(1)

    total, failed = 0, 0
    conn = psycopg2.connect(DB_URL)
    try:
        for fp in filepaths:
            n = load_file(fp, conn)
            total += n
            if n == 0:
                failed += 1
    finally:
        conn.close()

    if total == 0:
        log.error("No rows loaded — check CSV format")
        raise SystemExit(1)

    if failed:
        log.warning(f"{failed} of {len(filepaths)} file(s) produced no rows")
    log.info(f"Staging load complete — {total:,} rows from {len(filepaths)} file(s).")


if __name__ == "__main__":
    main()
