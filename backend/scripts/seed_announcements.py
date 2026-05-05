"""
One-shot script: seed market.asx_announcements via Markit Digital API
(the same backend the ASX website uses; works from cloud IPs unlike the ASX v1 API).

Run: cd /opt/asx-screener/backend && /opt/asx-venv/bin/python scripts/seed_announcements.py
"""
import asyncio
import logging
import re
import sys
import os
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
from sqlalchemy import text
from app.db.session import AsyncSessionLocal

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

# Markit Digital API — actual backend used by asx.com.au
MARKIT_URL = "https://asx.api.markitdigital.com/asx-research/1.0/companies/{code}/announcements"

MARKIT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "application/json",
    "Origin": "https://www.asx.com.au",
    "Referer": "https://www.asx.com.au/",
}


def parse_iso(dt_str: str | None):
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except Exception:
        return None


def parse_file_size_kb(size_str: str | None) -> float | None:
    """Convert '176KB' / '1.2MB' to kilobytes."""
    if not size_str:
        return None
    m = re.match(r"([\d.]+)\s*(KB|MB|GB)?", size_str.strip(), re.IGNORECASE)
    if not m:
        return None
    val = float(m.group(1))
    unit = (m.group(2) or "KB").upper()
    if unit == "MB":
        val *= 1024
    elif unit == "GB":
        val *= 1024 * 1024
    return round(val, 1)


async def fetch_markit(client: httpx.AsyncClient, code: str) -> list:
    """Fetch announcements from Markit Digital API.

    Response shape:
      {"data": {"displayName": "...", "issueType": "CS", "items": [
        {"announcementType": "...", "date": "2026-05-04T04:11:25.000Z",
         "documentKey": "2924-03084633-3A692621", "fileSize": "176KB",
         "headline": "...", "isPriceSensitive": false, "url": ""}
      ]}}
    """
    try:
        resp = await client.get(
            MARKIT_URL.format(code=code),
            params={"count": 20},
            headers=MARKIT_HEADERS,
            timeout=10,
        )
        if resp.status_code == 200:
            body = resp.json()
            data = body.get("data", {}) if isinstance(body, dict) else {}
            items = data.get("items", []) if isinstance(data, dict) else []
            return [a for a in items if isinstance(a, dict)]
    except Exception as e:
        log.debug(f"Markit {code}: {e}")
    return []


def parse_item(a: dict, code: str) -> dict | None:
    ann_id = (a.get("documentKey") or "").strip()
    if not ann_id:
        return None
    url = (a.get("url") or "").strip()
    if not url:
        # Construct PDF link from documentKey: "2924-03084633-3A692621"
        url = f"https://www.asx.com.au/asx/1/company/{code}/announcements/{ann_id}"
    return {
        "code":    code,
        "ann_id":  ann_id,
        "rel_at":  parse_iso(a.get("date")),
        "doc_dt":  parse_iso(a.get("date")),
        "title":   (a.get("headline") or a.get("announcementType") or "").strip(),
        "dtype":   (a.get("announcementType") or "").strip(),
        "url":     url,
        "mkt_sen": bool(a.get("isPriceSensitive", False)),
        "prc_sen": bool(a.get("isPriceSensitive", False)),
        "pages":   None,
        "size_kb": parse_file_size_kb(a.get("fileSize")),
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
        for i, code in enumerate(codes):
            items = await fetch_markit(client, code)

            if not items:
                failed += 1
                if failed <= 5:
                    log.info(f"[{i+1}/{len(codes)}] {code}: no data")
                elif failed == 6:
                    log.info("Suppressing further 'no data' messages...")
                continue

            rows = [r for a in items if (r := parse_item(a, code))]

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
