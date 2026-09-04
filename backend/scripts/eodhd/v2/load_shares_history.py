"""
Share count history — loader
============================
Parses outstandingShares.annual out of the EODHD fundamentals snapshots already
on disk and writes dated observations to market.shares_history.

No API calls. The fundamentals downloader stores the full payload per stock, and
outstandingShares travels with it, so this is a parse of files you already hold.
That matters when the EODHD daily quota is routinely exhausted.

Deliberately derives nothing. Dilution metrics are computed downstream from
these observations so their definition can be revised without re-ingesting, and
so persistence (a company issuing every year) can be separated from a single
capital event later.

Usage:
    python backend/scripts/eodhd/v2/load_shares_history.py
    python backend/scripts/eodhd/v2/load_shares_history.py --dry-run
    python backend/scripts/eodhd/v2/load_shares_history.py --codes BHP CBA
    python backend/scripts/eodhd/v2/load_shares_history.py --limit 50
"""
import argparse
import gzip
import json
import logging
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv("DATABASE_URL_SYNC",
                   "postgresql://asx_user:asx_secure_2024@localhost:5432/asx_screener")
RAW_BASE = Path(os.getenv("RAW_DATA_DIR", "/opt/asx-screener/data/raw"))
SNAP_DIR = RAW_BASE / "eodhd" / "exchange=AU" / "fundamentals" / "full_snapshot"

SOURCE = "eodhd_fundamentals_annual"

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s  %(levelname)-8s %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

# BHP.AU_2026-04-28.json.gz
_FNAME = re.compile(r"^([A-Z0-9]+)\.AU_(\d{4}-\d{2}-\d{2})\.json(?:\.gz)?$")

UPSERT_SQL = """
INSERT INTO market.shares_history
    (asx_code, fiscal_date, shares, shares_mln, source, snapshot_date)
VALUES %s
ON CONFLICT (asx_code, fiscal_date, source) DO UPDATE SET
    shares        = EXCLUDED.shares,
    shares_mln    = EXCLUDED.shares_mln,
    snapshot_date = EXCLUDED.snapshot_date,
    loaded_at     = NOW()
-- A later snapshot can restate an earlier fiscal year; the newest wins.
WHERE EXCLUDED.snapshot_date >= market.shares_history.snapshot_date
"""


def latest_snapshot_per_code(codes: list[str] | None) -> dict[str, tuple[Path, date]]:
    """Newest snapshot file for each ASX code."""
    best: dict[str, tuple[Path, date]] = {}
    if not SNAP_DIR.is_dir():
        log.error(f"Snapshot directory not found: {SNAP_DIR}")
        sys.exit(1)

    wanted = {c.upper() for c in codes} if codes else None
    for path in SNAP_DIR.iterdir():
        m = _FNAME.match(path.name)
        if not m:
            continue
        code, snap_str = m.group(1), m.group(2)
        if wanted and code not in wanted:
            continue
        snap = date.fromisoformat(snap_str)
        if code not in best or snap > best[code][1]:
            best[code] = (path, snap)
    return best


def _open(path: Path):
    return gzip.open(path, "rt", encoding="utf-8") if path.suffix == ".gz" \
        else open(path, "r", encoding="utf-8")


def parse_file(path: Path, code: str, snap: date) -> list[tuple]:
    """Extract dated share counts. Returns [] rather than raising on bad input."""
    try:
        with _open(path) as f:
            payload = json.load(f)
    except Exception as exc:
        log.debug(f"  {code}: unreadable ({exc})")
        return []

    annual = ((payload.get("outstandingShares") or {}).get("annual")) or {}
    rows: list[tuple] = []
    for entry in annual.values():
        if not isinstance(entry, dict):
            continue
        d = entry.get("dateFormatted")
        if not d:
            continue
        try:
            fiscal = datetime.strptime(str(d), "%Y-%m-%d").date()
        except ValueError:
            continue

        shares = entry.get("shares")
        mln    = entry.get("sharesMln")
        try:
            shares = int(float(shares)) if shares not in (None, "") else None
        except (TypeError, ValueError):
            shares = None
        try:
            mln = float(mln) if mln not in (None, "") else None
        except (TypeError, ValueError):
            mln = None

        # A zero or negative share count is meaningless; drop rather than store a
        # value that would later read as a 100 percent reduction.
        if (shares is None or shares <= 0) and (mln is None or mln <= 0):
            continue
        rows.append((code, fiscal, shares, mln, SOURCE, snap))
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description="Load shares-outstanding history")
    ap.add_argument("--dry-run", action="store_true", help="Parse without writing")
    ap.add_argument("--codes", nargs="+", help="Limit to these ASX codes")
    ap.add_argument("--limit", type=int, help="Process at most N stocks")
    args = ap.parse_args()

    snapshots = latest_snapshot_per_code(args.codes)
    if args.limit:
        snapshots = dict(list(snapshots.items())[:args.limit])
    log.info(f"Snapshot files to read: {len(snapshots):,}  (from {SNAP_DIR})")

    all_rows: list[tuple] = []
    with_history = no_history = 0
    for code, (path, snap) in sorted(snapshots.items()):
        rows = parse_file(path, code, snap)
        if rows:
            with_history += 1
            all_rows.extend(rows)
        else:
            no_history += 1

    log.info(f"  {with_history:,} stocks with share history, {no_history:,} without")
    log.info(f"  {len(all_rows):,} dated observations parsed")
    if with_history:
        log.info(f"  average {len(all_rows) / with_history:.1f} observations per stock")

    if not all_rows:
        log.error("Nothing parsed — check the snapshot directory and file names.")
        sys.exit(1)

    if args.dry_run:
        log.info("Dry run — nothing written. Sample:")
        for r in sorted(all_rows, key=lambda x: (x[0], x[1]), reverse=True)[:10]:
            log.info(f"    {r[0]:6s} {r[1]}  shares={r[2]:,}" if r[2] else
                     f"    {r[0]:6s} {r[1]}  shares=None")
        return

    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    execute_values(cur, UPSERT_SQL, all_rows, page_size=1000)
    conn.commit()
    cur.close()
    conn.close()
    log.info(f"  ✓ {len(all_rows):,} observations upserted into market.shares_history")


if __name__ == "__main__":
    main()
