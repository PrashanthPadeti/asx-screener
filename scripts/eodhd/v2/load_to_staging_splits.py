"""
Staging Load — Splits
======================
Reads per-stock split files from the Raw Zone and loads into staging.splits.
TRUNCATE + reload on full run; upsert on --codes / --from-code partial run.

Usage:
    python scripts/eodhd/v2/load_to_staging_splits.py
    python scripts/eodhd/v2/load_to_staging_splits.py --codes BHP CBA
    python scripts/eodhd/v2/load_to_staging_splits.py --from-code WBC
"""

import gzip
import json
import logging
import os
import sys
import argparse
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv()

DB_URL   = os.getenv("DATABASE_URL_SYNC",
             "postgresql://asx_user:asx_secure_2024@localhost:5432/asx_screener")
RAW_BASE = Path(os.getenv("RAW_DATA_DIR", "/opt/asx-screener/data/raw"))

EXCHANGE_DIR = RAW_BASE / "eodhd" / "exchange=AU"
SPLITS_DIR   = EXCHANGE_DIR / "splits" / "historical"
BATCH_COMMIT = 100

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)


def latest_file_for(code: str) -> Path | None:
    """Return the most recent splits file for a given ASX code."""
    files = sorted(SPLITS_DIR.glob(f"{code}.AU_*.json.gz"), reverse=True)
    return files[0] if files else None


def load_splits_file(cur, path: Path) -> int:
    """Parse one splits file and upsert into staging.splits. Returns row count."""
    stem  = path.name[:-len(".json.gz")]
    code  = stem.split("_")[0].replace(".AU", "")

    with gzip.open(path, "rt", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list) or len(data) == 0:
        return 0   # No splits for this stock — valid

    rows = []
    for item in data:
        if not isinstance(item, dict):
            continue
        dt_str = item.get("date", "")
        split  = item.get("split", "")
        if not dt_str or not split:
            continue
        try:
            from datetime import date
            ex_date = date.fromisoformat(dt_str[:10])
        except ValueError:
            continue
        rows.append((code, ex_date, split, path.name))

    if not rows:
        return 0

    execute_values(cur, """
        INSERT INTO staging.splits (asx_code, date, split, source_file)
        VALUES %s
        ON CONFLICT (asx_code, date) DO UPDATE SET
            split       = EXCLUDED.split,
            source_file = EXCLUDED.source_file,
            loaded_at   = NOW()
    """, rows)
    return len(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--codes",     nargs="+")
    parser.add_argument("--from-code", help="Resume from this code")
    parser.add_argument("--limit",     type=int)
    args = parser.parse_args()

    if not SPLITS_DIR.exists():
        log.error(f"Splits directory not found: {SPLITS_DIR}"); sys.exit(1)

    # Build file list
    if args.codes:
        files = []
        for c in args.codes:
            f = latest_file_for(c.upper())
            if f:
                files.append(f)
            else:
                log.warning(f"  No splits file found for {c}")
    else:
        # Deduplicate: one (latest) file per code
        seen = {}
        for f in sorted(SPLITS_DIR.glob("*.json.gz")):
            code = f.name.split("_")[0].replace(".AU", "")
            if code not in seen:
                seen[code] = f
        files = sorted(seen.values(), key=lambda p: p.name)

    if args.from_code:
        files = [f for f in files if f.name >= f"{args.from_code.upper()}.AU"]
    if args.limit:
        files = files[:args.limit]

    total = len(files)
    is_full_run = not args.codes and not args.from_code
    log.info(f"Loading splits for {total} stocks")

    conn = psycopg2.connect(DB_URL)
    cur  = conn.cursor()

    if is_full_run:
        cur.execute("TRUNCATE TABLE staging.splits RESTART IDENTITY")
        conn.commit()
        log.info("staging.splits truncated")

    total_rows = done = failed = 0

    for i, path in enumerate(files, 1):
        try:
            n = load_splits_file(cur, path)
            total_rows += n
            done += 1
        except Exception as e:
            conn.rollback()
            failed += 1
            log.warning(f"  {path.name}: {e}")
            continue

        if i % BATCH_COMMIT == 0:
            conn.commit()
            log.info(f"  [{i:4d}/{total}]  ok={done}  err={failed}  rows={total_rows:,}")

    conn.commit()
    cur.close()
    conn.close()
    log.info(f"DONE — {done} files  |  {total_rows:,} split events  |  {failed} errors")


if __name__ == "__main__":
    main()
