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
from datetime import date, datetime, timedelta, timezone
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
# ASIC Sitecore search API — used as fallback when HTML scraping finds 0 links
# The page is JS-rendered; this endpoint sometimes returns the file metadata as JSON.
ASIC_SEARCH_URL = (
    "https://asic.gov.au/sxa/search/results/"
    "?s=SSDailyAggShortPos&p=5&o=DateDescending&f="
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

def scrape_links_via_json_api() -> list[tuple[date, str]]:
    """
    Fallback: try ASIC's Sitecore search JSON endpoint.
    Returns list of (report_date, url) or [] if unavailable.
    """
    try:
        resp = requests.get(
            ASIC_SEARCH_URL,
            headers={**HEADERS, "Accept": "application/json, text/javascript, */*"},
            timeout=20,
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        results = data.get("Results", []) or data.get("results", [])
        links: list[tuple[date, str]] = []
        for item in results:
            url = item.get("Url") or item.get("url") or item.get("Path") or ""
            if not url.lower().endswith(".csv"):
                continue
            if "short" not in url.lower():
                continue
            filename = url.split("/")[-1]
            d = date_from_filename(filename)
            if d is None:
                continue
            abs_url = url if url.startswith("http") else ASIC_BASE + url
            links.append((d, abs_url))
        links.sort(key=lambda x: x[0], reverse=True)
        return links
    except Exception as e:
        log.debug(f"JSON API fallback failed: {e}")
        return []


def business_days_back(n: int) -> list[date]:
    """Return the last `n` weekdays (Mon-Fri) before today, newest first."""
    days, d = [], date.today()
    while len(days) < n:
        d -= timedelta(days=1)
        if d.weekday() < 5:   # Mon-Fri
            days.append(d)
    return days


def main():
    parser = argparse.ArgumentParser(description="Download ASIC Aggregate Short Position Reports")
    parser.add_argument("--force",      action="store_true", help="Re-download even if already cached")
    parser.add_argument("--list",       action="store_true", help="List available reports without downloading")
    parser.add_argument("--url",        help="Provide the direct CSV URL to download (bypass scraping)")
    parser.add_argument("--dump-html",  action="store_true", help="Dump first 3000 chars of ASIC page HTML (for debugging)")
    parser.add_argument("--dump-hrefs", action="store_true", help="Dump ALL hrefs found on ASIC page (for debugging)")
    args = parser.parse_args()

    # ── Direct URL mode ───────────────────────────────────────────────────────
    if args.url:
        filename = args.url.split("/")[-1].split("?")[0]
        d = date_from_filename(filename)
        if d is None:
            log.error(f"Could not extract date from URL filename: {filename}")
            raise SystemExit(1)
        success = download_csv(d, args.url, force=args.force)
        if not success:
            raise SystemExit(1)
        log.info("ASIC download complete (direct URL).")
        return

    # ── Step 1: Fetch the ASIC reports table page ──────────────────────────────
    log.info(f"Fetching ASIC reports index: {TABLE_URL}")
    resp_text = ""
    try:
        resp = requests.get(TABLE_URL, headers=HEADERS, timeout=30, allow_redirects=True)
        resp.raise_for_status()
        resp_text = resp.text
    except requests.RequestException as e:
        log.warning(f"Failed to fetch ASIC reports page: {e}")

    # ── Debug modes ───────────────────────────────────────────────────────────
    if args.dump_html:
        print("=== First 3000 chars of ASIC page HTML ===")
        print(resp_text[:3000])
        return

    if args.dump_hrefs:
        all_hrefs = re.findall(r'href=["\']([^"\']+)["\']', resp_text, re.IGNORECASE)
        print(f"=== All {len(all_hrefs)} hrefs on ASIC page ===")
        for h in sorted(set(all_hrefs)):
            print(f"  {h}")
        return

    # ── Step 2a: Parse CSV links from the HTML page ───────────────────────────
    links = scrape_report_links(resp_text) if resp_text else []

    # ── Step 2b: Fallback — try ASIC JSON search API ─────────────────────────
    if not links:
        log.warning(
            "No CSV links found in HTML (ASIC page is JS-rendered). "
            "Trying JSON search API fallback…"
        )
        links = scrape_links_via_json_api()

    if not links:
        log.warning(
            "JSON API also returned no links. "
            "Use --url <direct_csv_url> to manually specify the download URL.\n"
            f"  Find the latest report at: {TABLE_URL}"
        )
        # Still exit 0 (not 1) so the pipeline continues if data was already cached.
        # If no cached file exists, the next step (load_to_staging) will fail clearly.
        if not args.force:
            latest = max(OUT_DIR.glob("*.csv.gz"), default=None, key=lambda p: p.name)
            if latest:
                log.info(f"Using cached file: {latest.name} — pipeline will proceed.")
                return
        log.error("No cached file and no download possible — pipeline cannot continue.")
        raise SystemExit(1)

    log.info(f"Found {len(links)} report link(s)")

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
        log.warning(f"  Skipping {report_date.isoformat()}, trying older report …")

    log.error(
        "Could not download any ASIC short position report.\n"
        f"  Use --url <direct_csv_url> to manually specify the download URL.\n"
        f"  Find the latest report at: {TABLE_URL}"
    )
    raise SystemExit(1)


if __name__ == "__main__":
    main()
