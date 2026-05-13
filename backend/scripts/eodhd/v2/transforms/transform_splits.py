"""
Transform: staging.splits → market.splits
==========================================
Parses EODHD split ratio strings ('2:1', '1:10', etc.) into decimal ratios:
  '2:1'  → 2.0  (2-for-1 forward split)
  '1:10' → 0.1  (1-for-10 reverse split)
  '3:2'  → 1.5

Upserts into market.splits.

Full run: truncates market.splits first.
Partial run (--codes): upsert only.

Usage:
    python scripts/eodhd/v2/transforms/transform_splits.py
    python scripts/eodhd/v2/transforms/transform_splits.py --codes BHP CBA
"""

import logging
import os
import argparse

import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv("DATABASE_URL_SYNC",
           "postgresql://asx_user:asx_secure_2024@localhost:5432/asx_screener")

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)


def parse_ratio(split_str: str | None) -> float | None:
    """Parse split ratio string to decimal.
    Handles: '2:1', '1:10', '1.000000/5.000000', '2.0/1.0', '2.0'
    '2:1'              → 2.0  (2-for-1 forward split)
    '1:10'             → 0.1  (reverse split)
    '1.000000/5.000000'→ 0.2  (1-for-5 reverse split, EODHD format)
    """
    if not split_str:
        return None
    s = str(split_str).strip()
    sep = ":" if ":" in s else "/" if "/" in s else None
    if sep:
        parts = s.split(sep)
        try:
            num, den = float(parts[0]), float(parts[1])
            return round(num / den, 6) if den != 0 else None
        except (ValueError, IndexError):
            return None
    try:
        return float(s)
    except ValueError:
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--codes", nargs="+")
    args = parser.parse_args()

    is_full_run = not args.codes

    conn = psycopg2.connect(DB_URL)
    cur  = conn.cursor()

    if is_full_run:
        log.info("Full run — truncating market.splits …")
        cur.execute("TRUNCATE TABLE market.splits")
        conn.commit()

    if args.codes:
        placeholders = ",".join(["%s"] * len(args.codes))
        cur.execute(f"""
            SELECT asx_code, date, split
            FROM staging.splits
            WHERE asx_code IN ({placeholders})
            ORDER BY asx_code, date
        """, [c.upper() for c in args.codes])
    else:
        cur.execute("""
            SELECT asx_code, date, split
            FROM staging.splits
            ORDER BY asx_code, date
        """)

    rows = cur.fetchall()
    log.info(f"Processing {len(rows):,} split records …")

    ok = skipped = 0
    transformed = []
    for asx_code, split_date, split_str in rows:
        ratio = parse_ratio(split_str)
        if ratio is None:
            log.warning(f"  {asx_code} {split_date}: cannot parse ratio '{split_str}'")
            skipped += 1
            continue
        transformed.append((asx_code, split_date, ratio, "eodhd"))
        ok += 1

    if transformed:
        execute_values(cur, """
            INSERT INTO market.splits
                (asx_code, split_date, ratio, data_source)
            VALUES %s
            ON CONFLICT (asx_code, split_date) DO UPDATE SET
                ratio       = EXCLUDED.ratio,
                data_source = EXCLUDED.data_source,
                loaded_at   = NOW()
        """, transformed, page_size=2000)

    conn.commit()
    cur.close()
    conn.close()
    log.info(f"DONE — {ok} rows upserted | {skipped} skipped (unparseable ratio)")


if __name__ == "__main__":
    main()
