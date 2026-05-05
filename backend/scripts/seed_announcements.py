"""
One-shot script: seed market.asx_announcements using the companies API
live-fetch pathway (same as company page Documents tab, which works in browser).

Since the ASX blocks direct server-side requests, this script calls the
internal announcements endpoint for each top company which handles caching.

Run: /opt/asx-venv/bin/python scripts/seed_announcements.py
"""
import asyncio
import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
from sqlalchemy import text
from app.db.session import AsyncSessionLocal

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

# Alternative ASX announcement APIs — try newer endpoints
ASX_ANN_URLS = [
    # New ASX API format (2024+)
    "https://asx.api.markitdigital.com/asx-research/1.0/companies/{code}/announcements?count=20",
    # Backup: old v1 without query params
    "https://www.asx.com.au/asx/1/company/{code}/announcements?count=20",
    "https://www.asx.com.au/asx/1/security/{code}/announcements?count=20",
]

ASX_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-AU,en;q=0.9",
    "Referer": "https://www.asx.com.au/markets/company/",
    "Origin": "https://www.asx.com.au",
    "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
}

MARKIT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "application/json",
    "Origin": "https://www.asx.com.au",
    "Referer": "https://www.asx.com.au/",
}


async def fetch_markit(client: httpx.AsyncClient, code: str) -> list:
    """Try the Markit Digital API used by the ASX website."""
    try:
        resp = await client.get(
            f"https://asx.api.markitdigital.com/asx-research/1.0/companies/{code}/announcements",
            params={"count": 20, "pageSize": 20},
            headers=MARKIT_HEADERS,
            timeout=10,
        )
        if resp.status_code == 200:
            body = resp.json()
            data = body.get("data", {}) if isinstance(body, dict) else {}
            if isinstance(data, dict):
                items = data.get("announcementSummaries", []) or data.get("announcements", [])
            elif isinstance(data, list):
                items = data
            else:
                items = []
            if items and not isinstance(items[0], dict):
                log.warning(f"Markit {code}: item type={type(items[0])}, data keys={list(data.keys()) if isinstance(data, dict) else 'n/a'}, sample={str(items[:2])[:400]}")
                return []
            return items
    except Exception as e:
        log.debug(f"Markit {code}: {e}")
    return []


async def parse_markit_item(a: dict, code: str) -> dict | None:
    ann_id = str(a.get("id") or a.get("documentId") or "").strip()
    if not ann_id:
        return None
    url = a.get("url") or a.get("documentUrl") or ""
    if not url and a.get("relativeUrl"):
        url = "https://www.asx.com.au" + a["relativeUrl"]
    return {
        "code":    code,
        "ann_id":  ann_id,
        "rel_at":  a.get("documentReleaseDate") or a.get("document_release_date"),
        "doc_dt":  a.get("documentDate") or a.get("document_date"),
        "title":   (a.get("header") or a.get("documentType") or a.get("document_type") or "").strip(),
        "dtype":   (a.get("documentType") or a.get("document_type") or "").strip(),
        "url":     url,
        "mkt_sen": bool(a.get("marketSensitive") or a.get("market_sensitive", False)),
        "prc_sen": bool(a.get("priceSensitive") or a.get("price_sensitive", False)),
        "pages":   a.get("numberOfPages") or a.get("number_of_pages"),
        "size_kb": None,
    }


async def main():
    async with AsyncSessionLocal() as db:
        result = await db.execute(text("""
            SELECT asx_code FROM screener.universe
            ORDER BY market_cap DESC NULLS LAST
            LIMIT 200
        """))
        codes = [r.asx_code for r in result.fetchall()]

    log.info(f"Seeding announcements for {len(codes)} companies via Markit Digital API...")
    total_inserted = 0
    failed = 0

    async with httpx.AsyncClient(follow_redirects=True) as client:
        # Probe first company to log raw response shape
        if codes:
            probe = await client.get(
                f"https://asx.api.markitdigital.com/asx-research/1.0/companies/{codes[0]}/announcements",
                params={"count": 5},
                headers=MARKIT_HEADERS,
                timeout=10,
            )
            log.info(f"PROBE {codes[0]} status={probe.status_code}")
            log.info(f"PROBE body (first 800 chars): {probe.text[:800]}")

        for i, code in enumerate(codes):
            items = await fetch_markit(client, code)

            if not items:
                failed += 1
                if failed <= 5:
                    log.info(f"[{i+1}/{len(codes)}] {code}: no data")
                elif failed == 6:
                    log.info("Suppressing further 'no data' messages...")
                continue

            rows = []
            for a in items:
                row = await parse_markit_item(a, code)
                if row:
                    rows.append(row)

            if rows:
                async with AsyncSessionLocal() as db:
                    try:
                        await db.execute(text("""
                            INSERT INTO market.asx_announcements
                                (asx_code, announcement_id, released_at, document_date,
                                 title, document_type, url,
                                 market_sensitive, price_sensitive, num_pages, file_size_kb)
                            VALUES
                                (:code, :ann_id, :rel_at, :doc_dt,
                                 :title, :dtype, :url,
                                 :mkt_sen, :prc_sen, :pages, :size_kb)
                            ON CONFLICT (asx_code, announcement_id) DO NOTHING
                        """), rows)
                        await db.commit()
                        total_inserted += len(rows)
                        log.info(f"[{i+1}/{len(codes)}] {code}: +{len(rows)}")
                    except Exception as e:
                        log.warning(f"{code}: DB error — {e}")
                        await db.rollback()

            await asyncio.sleep(0.2)

    log.info(f"Done — {total_inserted} announcements seeded ({failed} companies had no data)")


if __name__ == "__main__":
    asyncio.run(main())
