"""
ASIC Short Position Ingestion
==============================
Scrapes the ASIC short position reports table page to discover the real
download URLs (which contain media IDs that change per file), downloads the
latest CSV, and syncs short_pct into screener.universe.

ASIC table page:
  https://asic.gov.au/regulatory-resources/markets/short-selling/short-position-reports-table/

Usage:
    python -m compute.engine.short_positions [--date YYYY-MM-DD] [--dry-run]
"""
import argparse
import asyncio
import csv
import io
import logging
import os
import re
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import httpx
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import text

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

DATABASE_URL = os.environ.get("DATABASE_URL", "")

ASIC_TABLE_URL = (
    "https://asic.gov.au/regulatory-resources/markets/short-selling/"
    "short-position-reports-table/"
)
MAX_LOOKBACK_DAYS = 10

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,*/*",
    "Referer": "https://www.asic.gov.au/",
}


async def _discover_csv_urls() -> list[tuple[date, str]]:
    """
    Scrape the ASIC short position reports table page and extract
    (report_date, csv_url) pairs. Returns list sorted newest-first.
    """
    async with httpx.AsyncClient(timeout=30, follow_redirects=True,
                                  headers=BROWSER_HEADERS) as client:
        r = await client.get(ASIC_TABLE_URL)
        r.raise_for_status()

    # Links look like: href="/media/12345/aggregate-short-positions-08052026.csv"
    pattern = re.compile(
        r'href=["\']([^"\']*aggregate-short-positions-(\d{8})\.csv)["\']',
        re.IGNORECASE,
    )
    results: list[tuple[date, str]] = []
    for m in pattern.finditer(r.text):
        href, date_str = m.group(1), m.group(2)
        try:
            # date_str is DDMMYYYY
            d = date(int(date_str[4:8]), int(date_str[2:4]), int(date_str[0:2]))
        except ValueError:
            continue
        url = href if href.startswith("http") else f"https://www.asic.gov.au{href}"
        results.append((d, url))

    results.sort(key=lambda x: x[0], reverse=True)
    log.info("Discovered %d ASIC short position links on table page", len(results))
    return results


async def _fetch_report(target_date: date) -> tuple[date, list[dict]] | None:
    """
    Discover CSV links from the ASIC table page, download the most recent
    one on or before target_date.
    """
    try:
        links = await _discover_csv_urls()
    except Exception as exc:
        log.warning("Could not scrape ASIC table page: %s", exc)
        return None

    cutoff = target_date - timedelta(days=MAX_LOOKBACK_DAYS)
    candidates = [(d, url) for d, url in links if cutoff <= d <= target_date]
    if not candidates:
        log.warning("No ASIC links found between %s and %s", cutoff, target_date)
        return None

    dl_headers = {**BROWSER_HEADERS, "Accept": "text/csv,application/octet-stream,*/*"}
    async with httpx.AsyncClient(timeout=60, follow_redirects=True,
                                  headers=dl_headers) as client:
        for d, url in candidates:
            try:
                log.info("Downloading: %s", url)
                r = await client.get(url)
                ct = r.headers.get("content-type", "")
                if r.status_code == 200 and "html" not in ct and len(r.content) > 500:
                    rows = _parse_csv(r.text, d)
                    if rows:
                        log.info("Got ASIC short report for %s: %d rows", d, len(rows))
                        return d, rows
                    log.debug("No parseable rows in %s (ct=%s)", url, ct)
                else:
                    log.debug("Skipping %s — status=%s ct=%s size=%d",
                              url, r.status_code, ct, len(r.content))
            except Exception as exc:
                log.debug("Failed %s: %s", url, exc)

    return None


def _parse_csv(content: str, report_date: date) -> list[dict]:
    """Parse ASIC short position CSV into list of dicts."""
    rows = []
    reader = csv.DictReader(io.StringIO(content))
    for row in reader:
        code = (row.get("ASX Code") or row.get("ASX code") or "").strip().upper()
        if not code or len(code) > 10:
            continue
        try:
            short_shares = int(str(row.get("Short Positions") or "0").replace(",", "") or 0)
            total_issued = int(str(row.get("Total Product in Issue") or "0").replace(",", "") or 0)
            pct_raw = str(row.get("%") or row.get("Percent") or "0").replace(",", "").replace("%", "").strip()
            short_pct = float(pct_raw) if pct_raw else (
                (short_shares / total_issued * 100) if total_issued > 0 else 0.0
            )
        except (ValueError, ZeroDivisionError):
            continue
        rows.append({
            "report_date":  report_date,
            "asx_code":     code,
            "short_shares": short_shares,
            "total_issued": total_issued,
            "short_pct":    round(short_pct, 6),
        })
    return rows


async def run(target_date: date | None = None, dry_run: bool = False) -> None:
    if not DATABASE_URL:
        log.error("DATABASE_URL not set")
        sys.exit(1)

    target_date = target_date or date.today()

    result = await _fetch_report(target_date)
    if result is None:
        log.warning("Could not download any ASIC short report")
        return

    report_date, rows = result
    if dry_run:
        log.info("[DRY RUN] Would load %d rows for %s", len(rows), report_date)
        if rows:
            log.info("Sample: %s", rows[:3])
        return

    engine = create_async_engine(DATABASE_URL, echo=False)
    async with AsyncSession(engine) as session:

        # 1. Stage
        for r in rows:
            await session.execute(text("""
                INSERT INTO staging_au.short_positions
                    (report_date, asx_code, short_shares, total_issued, short_pct, source_file)
                VALUES (:d, :code, :ss, :ti, :pct, :src)
                ON CONFLICT (report_date, asx_code) DO UPDATE SET
                    short_shares=EXCLUDED.short_shares,
                    total_issued=EXCLUDED.total_issued,
                    short_pct=EXCLUDED.short_pct
            """), {"d": r["report_date"], "code": r["asx_code"], "ss": r["short_shares"],
                   "ti": r["total_issued"], "pct": r["short_pct"],
                   "src": f"asic-{report_date}"})
        log.info("Staged %d rows for %s", len(rows), report_date)

        # 2. Promote to market.short_positions with WoW change
        await session.execute(text("""
            INSERT INTO market.short_positions
                (report_date, asx_code, short_pct, short_shares, short_pct_chg_1w)
            SELECT s.report_date, s.asx_code, s.short_pct, s.short_shares,
                   s.short_pct - prev.short_pct
            FROM staging_au.short_positions s
            LEFT JOIN LATERAL (
                SELECT short_pct FROM market.short_positions p
                WHERE p.asx_code=s.asx_code AND p.report_date < s.report_date
                ORDER BY p.report_date DESC LIMIT 1
            ) prev ON TRUE
            WHERE s.report_date = :d
            ON CONFLICT (report_date, asx_code) DO UPDATE SET
                short_pct=EXCLUDED.short_pct,
                short_shares=EXCLUDED.short_shares,
                short_pct_chg_1w=EXCLUDED.short_pct_chg_1w,
                updated_at=NOW()
        """), {"d": report_date})

        # 3. Sync into screener.universe
        await session.execute(text("""
            UPDATE screener.universe u
            SET short_pct=sp.short_pct, short_interest_chg_1w=sp.short_pct_chg_1w
            FROM market.short_positions sp
            WHERE sp.asx_code=u.asx_code AND sp.report_date=:d
        """), {"d": report_date})

        updated = (await session.execute(text(
            "SELECT COUNT(*) FROM screener.universe WHERE short_pct IS NOT NULL AND short_pct > 0"
        ))).scalar()
        log.info("short_pct populated for %d stocks", updated)

        await session.commit()
        log.info("Committed short positions for %s", report_date)

    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest ASIC short position data")
    parser.add_argument("--date", default=None, help="Target date YYYY-MM-DD")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    target = date.fromisoformat(args.date) if args.date else None
    asyncio.run(run(target_date=target, dry_run=args.dry_run))
