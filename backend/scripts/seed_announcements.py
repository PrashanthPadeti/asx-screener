"""
One-shot script: fetch recent ASX announcements for top 100 companies
and cache them into market.asx_announcements.

Run: python scripts/seed_announcements.py
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

ASX_ANN_URLS = [
    "https://www.asx.com.au/asx/1/company/{code}/announcements?count=20&market_sensitive=0",
    "https://www.asx.com.au/asx/1/security/{code}/announcements?count=20&market_sensitive=0",
    "https://www.asx.com.au/asx/1/company/{code}/announcements?count=20",
]
ASX_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.asx.com.au/",
}


async def fetch_for_code(client: httpx.AsyncClient, code: str) -> list:
    for url_tpl in ASX_ANN_URLS:
        try:
            resp = await client.get(url_tpl.format(code=code), headers=ASX_HEADERS, timeout=10)
            if resp.status_code == 200:
                body = resp.json()
                items = body if isinstance(body, list) else body.get("data", [])
                if items:
                    return items
        except Exception as e:
            log.debug(f"{code}: {e}")
    return []


async def main():
    async with AsyncSessionLocal() as db:
        # Get top 100 by market cap
        result = await db.execute(text("""
            SELECT asx_code FROM screener.universe
            ORDER BY market_cap DESC NULLS LAST
            LIMIT 100
        """))
        codes = [r.asx_code for r in result.fetchall()]

    log.info(f"Seeding announcements for {len(codes)} companies...")
    total_inserted = 0

    async with httpx.AsyncClient() as client:
        for i, code in enumerate(codes):
            items = await fetch_for_code(client, code)
            if not items:
                log.info(f"[{i+1}/{len(codes)}] {code}: no data")
                continue

            rows = []
            for a in items:
                ann_id = str(a.get("id") or "").strip()
                if not ann_id:
                    continue
                url = a.get("url") or ""
                if not url and a.get("relative_url"):
                    url = "https://www.asx.com.au" + a["relative_url"]
                rows.append({
                    "code":    code,
                    "ann_id":  ann_id,
                    "rel_at":  a.get("document_release_date"),
                    "doc_dt":  a.get("document_date"),
                    "title":   (a.get("header") or a.get("document_type") or "").strip(),
                    "dtype":   (a.get("document_type") or "").strip(),
                    "url":     url,
                    "mkt_sen": bool(a.get("market_sensitive", False)),
                    "prc_sen": bool(a.get("price_sensitive", False)),
                    "pages":   a.get("number_of_pages"),
                    "size_kb": (int(a.get("size", 0) or 0)) // 1024 or None,
                })

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
                        log.info(f"[{i+1}/{len(codes)}] {code}: inserted {len(rows)} announcements")
                    except Exception as e:
                        log.warning(f"{code}: DB insert failed — {e}")
                        await db.rollback()

            await asyncio.sleep(0.3)  # polite rate limit

    log.info(f"Done — {total_inserted} announcements seeded")


if __name__ == "__main__":
    asyncio.run(main())
