"""
ASX Screener — Download Announcements
======================================
Fetches recent company announcements from the public ASX API
and upserts to market.asx_announcements.

Run daily after market close (~18:30 AEST = 08:30 UTC).

Default mode: ASX 200 companies (~200 codes, ~1 min to run).
Use --asx300 or --all for broader coverage.
Use --codes for ad-hoc / testing.

Schedule (cron — daily 08:30 UTC = 18:30 AEST):
  30 8 * * 1-5  cd /opt/asx-screener && \\
    asx-venv/bin/python scripts/asx/download_announcements.py \\
    >> logs/download_announcements.log 2>&1

Usage:
    python scripts/asx/download_announcements.py
    python scripts/asx/download_announcements.py --codes CBA BHP ANZ
    python scripts/asx/download_announcements.py --asx300
    python scripts/asx/download_announcements.py --all
    python scripts/asx/download_announcements.py --count 50
    python scripts/asx/download_announcements.py --dry-run
"""

import argparse
import logging
import os
import time

import psycopg2
import psycopg2.extensions
from psycopg2.extras import execute_values
import requests
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv(
    "DATABASE_URL_SYNC",
    "postgresql://asx_user:asx_secure_2024@localhost:5432/asx_screener"
)

# ASX public API — no auth required
ASX_ANN_URL = (
    "https://www.asx.com.au/asx/1/company/{code}/announcements"
    "?count={count}&market_sensitive=false"
)
ASX_BASE_URL = "https://www.asx.com.au"

# Be polite: 4 requests/sec
REQUEST_DELAY   = 0.25
REQUEST_TIMEOUT = 12

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": "ASX-Screener/1.0 (research)",
    "Accept":     "application/json",
}


def get_codes(conn, mode: str, explicit_codes: list[str] | None) -> list[str]:
    """Return list of ASX codes to process, ordered alphabetically."""
    if explicit_codes:
        return [c.upper().strip() for c in explicit_codes]

    cur = conn.cursor()

    # Try index-filtered modes first; fall back to all active if flags not populated
    if mode == "asx200":
        cur.execute("""
            SELECT DISTINCT asx_code FROM screener.universe
            WHERE is_asx200 = true AND status = 'active' ORDER BY asx_code
        """)
        codes = [r[0] for r in cur.fetchall()]
        if not codes:
            log.warning("is_asx200 flags not populated — falling back to all active companies")
            mode = "all"

    if mode == "asx300":
        cur.execute("""
            SELECT DISTINCT asx_code FROM screener.universe
            WHERE is_asx300 = true AND status = 'active' ORDER BY asx_code
        """)
        codes = [r[0] for r in cur.fetchall()]
        if not codes:
            log.warning("is_asx300 flags not populated — falling back to all active companies")
            mode = "all"

    if mode == "all":
        cur.execute("""
            SELECT DISTINCT asx_code FROM screener.universe
            WHERE status = 'active' ORDER BY asx_code
        """)
        codes = [r[0] for r in cur.fetchall()]

    cur.close()
    return codes


def fetch_announcements(code: str, count: int) -> list[dict]:
    """Call ASX public API for one company. Returns raw announcement dicts."""
    url = ASX_ANN_URL.format(code=code, count=count)
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT, headers=_HEADERS)
        if resp.status_code == 404:
            return []          # company not found / delisted
        if resp.status_code == 200:
            return resp.json().get("data", [])
        log.warning(f"  {code}: HTTP {resp.status_code}")
        return []
    except requests.RequestException as e:
        log.warning(f"  {code}: request error — {e}")
        return []


def _build_rows(code: str, announcements: list[dict]) -> list[tuple]:
    rows = []
    for a in announcements:
        ann_id = str(a.get("id") or "").strip()
        if not ann_id:
            continue

        # PDF URL
        url = a.get("url") or ""
        if not url:
            rel = a.get("relative_url") or ""
            url = (ASX_BASE_URL + rel) if rel else ""

        # File size → KB
        size_bytes = a.get("size") or 0
        size_kb    = int(size_bytes) // 1024 if size_bytes else None

        rows.append((
            code,
            ann_id,
            a.get("document_release_date"),      # TIMESTAMPTZ string
            a.get("document_date"),               # DATE string
            (a.get("header") or a.get("document_type") or "").strip(),
            (a.get("document_type") or "").strip(),
            url,
            bool(a.get("market_sensitive", False)),
            bool(a.get("price_sensitive",  False)),
            a.get("number_of_pages"),
            size_kb,
        ))
    return rows


def upsert_announcements(conn, code: str, announcements: list[dict]) -> int:
    """Upsert parsed announcements. Returns number of rows affected."""
    rows = _build_rows(code, announcements)
    if not rows:
        return 0

    SQL = """
        INSERT INTO market.asx_announcements
            (asx_code, announcement_id, released_at, document_date,
             title, document_type, url,
             market_sensitive, price_sensitive, num_pages, file_size_kb)
        VALUES %s
        ON CONFLICT (asx_code, announcement_id) DO UPDATE SET
            released_at      = EXCLUDED.released_at,
            title            = EXCLUDED.title,
            document_type    = EXCLUDED.document_type,
            url              = EXCLUDED.url,
            market_sensitive = EXCLUDED.market_sensitive,
            price_sensitive  = EXCLUDED.price_sensitive,
            num_pages        = EXCLUDED.num_pages,
            file_size_kb     = EXCLUDED.file_size_kb
    """
    cur = conn.cursor()
    execute_values(cur, SQL, rows, page_size=100)
    n = cur.rowcount
    conn.commit()
    cur.close()
    return n


def main():
    parser = argparse.ArgumentParser(description="Download ASX company announcements")
    parser.add_argument("--codes",    nargs="+", help="Specific ASX codes (overrides mode)")
    parser.add_argument("--asx300",   action="store_true", help="Process ASX 300 companies")
    parser.add_argument("--all",      action="store_true", dest="all_codes",
                        help="Process all active companies (~1,800)")
    parser.add_argument("--count",    type=int, default=20,
                        help="Announcements per company (default: 20)")
    parser.add_argument("--dry-run",  action="store_true",
                        help="Fetch but do not write to DB")
    args = parser.parse_args()

    mode = "asx300" if args.asx300 else ("all" if args.all_codes else "asx200")

    conn = psycopg2.connect(DB_URL)
    try:
        codes = get_codes(conn, mode, args.codes)
        log.info(f"Processing {len(codes):,} companies — mode={mode}, count={args.count}")

        total_fetched  = 0
        total_upserted = 0
        errors         = 0

        for i, code in enumerate(codes, 1):
            anns = fetch_announcements(code, args.count)
            total_fetched += len(anns)

            if not args.dry_run:
                n = upsert_announcements(conn, code, anns)
                total_upserted += n
            else:
                n = len(anns)

            if anns:
                sensitive = sum(1 for a in anns if a.get("market_sensitive"))
                log.info(
                    f"  [{i}/{len(codes)}] {code}: "
                    f"{len(anns)} fetched, {n} upserted"
                    + (f", {sensitive} market-sensitive" if sensitive else "")
                )
            else:
                log.debug(f"  [{i}/{len(codes)}] {code}: no announcements")

            time.sleep(REQUEST_DELAY)

        suffix = " (dry-run)" if args.dry_run else ""
        log.info(
            f"Done{suffix}. "
            f"{total_fetched:,} fetched, {total_upserted:,} upserted "
            f"across {len(codes):,} companies. Errors: {errors}"
        )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
