"""
ASIC Short Position Report — Downloader
=========================================
Downloads the most recent daily aggregate short position CSV from ASIC.

Strategy: Scrape the ASIC short position reports table page to find the
actual live download links (rather than guessing URL patterns that may change).

Source page:
    https://asic.gov.au/regulatory-resources/markets/short-selling/short-position-reports-table/

Output:
    {RAW_DATA_DIR}/asic/short_positions/{YYYYMMDD}.csv.gz

Usage:
    python scripts/asic/download_short_positions.py
    python scripts/asic/download_short_positions.py --force     # re-download even if cached
    python scripts/asic/download_short_positions.py --list      # list available links without downloading
"""

import argparse
import gzip
import logging
import os
import re
from datetime import date, datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

RAW_BASE  = Path(os.getenv("RAW_DATA_DIR", "/opt/asx-screener/data/raw"))
OUT_DIR   = RAW_BASE / "asic" / "short_positions"
ASIC_BASE = "https://asic.gov.au"
TABLE_URL = (
    "https://asic.gov.au/regulatory-resources/markets/short-selling/"
    "short-position-reports-table/"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*",
    "Accept-Language": "en-AU,en;q=0.9",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ── Date parsing helpers ──────────────────────────────────────────────────────

# Matches filenames like: RR20260429-001-SSDailyAggShortPos.csv
#   or: 20260429-SSDailyAggShortPos.csv  etc.
_DATE_IN_FILENAME = re.compile(r"(\d{8})")

def date_from_filename(filename: str) -> date | None:
    """Extract YYYYMMDD date from an ASIC filename, or None."""
    m = _DATE_IN_FILENAME.search(filename)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y%m%d").date()
    except ValueError:
        return None


# ── Link scraper ──────────────────────────────────────────────────────────────

def scrape_report_links(html: str) -> list[tuple[date, str]]:
    """
    Parse ASIC short position reports table page HTML.
    Returns list of (report_date, absolute_url) sorted newest first.

    Looks for:
      - href ending in .csv
      - filename containing 'ShortPos' or 'shortpos' (case-insensitive)
      - an 8-digit date in the filename
    """
    # Find all hrefs in <a href="..."> tags
    hrefs = re.findall(r'href=["\']([^"\']+)["\']', html, re.IGNORECASE)

    results = []
    seen = set()
    for href in hrefs:
        # Must be a .csv file
        if not href.lower().endswith(".csv"):
            continue
        # Must contain 'short' somewhere in the path (catches ShortPos, shortpos, etc.)
        if "short" not in href.lower():
            continue
        # Must have a date in the filename
        filename = href.split("/")[-1]
        d = date_from_filename(filename)
        if d is None:
            continue
        # Deduplicate
        key = filename.lower()
        if key in seen:
            continue
        seen.add(key)
        # Build absolute URL
        if href.startswith("http"):
            url = href
        else:
            url = ASIC_BASE + href if href.startswith("/") else ASIC_BASE + "/" + href
        results.append((d, url))

    # Sort newest first
    results.sort(key=lambda x: x[0], reverse=True)
    return results


# ── Download ──────────────────────────────────────────────────────────────────

def local_path(d: date) -> Path:
    return OUT_DIR / f"{d.strftime('%Y%m%d')}.csv.gz"


def download_csv(report_date: date, url: str, force: bool = False) -> bool:
    """Download the CSV at `url`, save gzipped. Returns True on success."""
    dest = local_path(report_date)
    if dest.exists() and not force:
        log.info(f"  Already cached: {dest.name}")
        return True

    log.info(f"  Downloading {report_date.isoformat()} ← {url}")
    dl_headers = {**HEADERS, "Accept": "text/csv,text/plain,application/octet-stream,*/*"}

    try:
        resp = requests.get(url, headers=dl_headers, timeout=60, allow_redirects=True)
    except requests.RequestException as e:
        log.error(f"  Request error: {e}")
        return False

    if resp.status_code != 200:
        log.warning(f"  HTTP {resp.status_code}")
        return False

    content = resp.content
    first_bytes = content[:200].decode("utf-8", errors="replace")
    if first_bytes.lstrip().startswith("<"):
        log.warning("  Got HTML instead of CSV — download link may have expired")
        return False

    dest.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(dest, "wb") as f:
        f.write(content)

    size_kb = len(content) / 1024
    log.info(f"  ✓ Saved {dest.name} ({size_kb:.0f} KB, {len(content.splitlines()):,} rows)")
    return True


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Download ASIC Aggregate Short Position Reports")
    parser.add_argument("--force",      action="store_true", help="Re-download even if already cached")
    parser.add_argument("--list",       action="store_true", help="List available reports without downloading")
    parser.add_argument("--dump-html",  action="store_true", help="Dump first 3000 chars of ASIC page HTML (for debugging)")
    parser.add_argument("--dump-hrefs", action="store_true", help="Dump ALL hrefs found on ASIC page (for debugging)")
    args = parser.parse_args()

    # ── Step 1: Fetch the ASIC reports table page ──────────────────────────────
    log.info(f"Fetching ASIC reports index: {TABLE_URL}")
    try:
        resp = requests.get(TABLE_URL, headers=HEADERS, timeout=30, allow_redirects=True)
        resp.raise_for_status()
    except requests.RequestException as e:
        log.error(f"Failed to fetch ASIC reports index: {e}")
        raise SystemExit(1)

    # ── Debug modes ───────────────────────────────────────────────────────────
    if args.dump_html:
        print("=== First 3000 chars of ASIC page HTML ===")
        print(resp.text[:3000])
        return

    if args.dump_hrefs:
        all_hrefs = re.findall(r'href=["\']([^"\']+)["\']', resp.text, re.IGNORECASE)
        print(f"=== All {len(all_hrefs)} hrefs on ASIC page ===")
        for h in sorted(set(all_hrefs)):
            print(f"  {h}")
        return

    # ── Step 2: Parse CSV links from the page ─────────────────────────────────
    links = scrape_report_links(resp.text)

    if not links:
        log.error(
            "No short position CSV links found on ASIC page.\n"
            "  ASIC may have changed their page structure.\n"
            f"  Check manually: {TABLE_URL}\n"
            "  Then update scrape_report_links() in this script."
        )
        raise SystemExit(1)

    log.info(f"Found {len(links)} report link(s) on ASIC page")

    if args.list:
        for d, url in links[:20]:
            cached = " [cached]" if local_path(d).exists() else ""
            print(f"  {d.isoformat()}  {url}{cached}")
        return

    # ── Step 3: Download the most recent one (skip already-cached) ─────────────
    for report_date, url in links:
        dest = local_path(report_date)
        if dest.exists() and not args.force:
            log.info(f"Most recent already cached: {report_date.isoformat()} ({dest.name})")
            log.info("ASIC download complete (cached).")
            return

        success = download_csv(report_date, url, force=args.force)
        if success:
            log.info("ASIC download complete.")
            return
        # If this link failed, try the next one
        log.warning(f"  Skipping {report_date.isoformat()}, trying older report …")

    log.error("Could not download any ASIC short position report")
    raise SystemExit(1)


if __name__ == "__main__":
    main()
