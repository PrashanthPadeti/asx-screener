"""
ASX Screener — Announcement Worker
====================================
Fetches recent ASX announcements from EODHD for all companies in the
screener universe and stores them in market.asx_announcements.

Also sends notification emails/SMS to subscribed users when
market-sensitive announcements are filed.

Runs every 10 minutes via APScheduler.
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx
from sqlalchemy import text

from app.db.session import AsyncSessionLocal
from app.core.config import settings

log = logging.getLogger(__name__)

EODHD_BASE = "https://eodhd.com/api"


async def fetch_announcements() -> None:
    async with AsyncSessionLocal() as db:
        try:
            await _run(db)
        except Exception as e:
            log.error(f"Announcement worker error: {e}", exc_info=True)


async def _run(db) -> None:
    if not settings.EODHD_API_KEY:
        log.debug("EODHD_API_KEY not set — skipping announcement fetch")
        return

    # Get top 200 ASX codes by market cap to keep API calls manageable
    result = await db.execute(text("""
        SELECT asx_code FROM screener.universe
        ORDER BY market_cap DESC NULLS LAST
        LIMIT 200
    """))
    codes = [r.asx_code for r in result.fetchall()]

    if not codes:
        return

    inserted = 0
    market_sensitive_new = []

    async with httpx.AsyncClient(timeout=30) as client:
        for code in codes:
            try:
                resp = await client.get(
                    f"{EODHD_BASE}/news",
                    params={
                        "s":           f"{code}.AU",
                        "api_token":   settings.EODHD_API_KEY,
                        "fmt":         "json",
                        "limit":       10,
                        "offset":      0,
                    },
                )
                if resp.status_code != 200:
                    continue
                items = resp.json()
                if not isinstance(items, list):
                    continue

                for item in items:
                    ann_id   = str(item.get("id") or item.get("link", ""))[:100]
                    title    = (item.get("title") or "")[:500]
                    doc_type = (item.get("type") or "General")[:100]
                    url      = item.get("link") or item.get("url")
                    date_str = item.get("date") or item.get("datetime")

                    try:
                        released_at = datetime.fromisoformat(date_str.replace("Z", "+00:00")) if date_str else datetime.now(timezone.utc)
                    except Exception:
                        released_at = datetime.now(timezone.utc)

                    sensitive = _is_sensitive(doc_type, title)

                    result2 = await db.execute(text("""
                        INSERT INTO market.asx_announcements
                            (asx_code, announcement_id, title, document_type,
                             url, market_sensitive, released_at)
                        VALUES (:code, :ann_id, :title, :doc_type, :url, :sensitive, :released_at)
                        ON CONFLICT (asx_code, announcement_id) DO NOTHING
                        RETURNING id
                    """), {
                        "code":       code,
                        "ann_id":     ann_id or f"{code}_{released_at.isoformat()}",
                        "title":      title,
                        "doc_type":   doc_type,
                        "url":        url,
                        "sensitive":  sensitive,
                        "released_at": released_at,
                    })
                    if result2.fetchone():
                        inserted += 1
                        if sensitive:
                            market_sensitive_new.append({
                                "asx_code":  code,
                                "title":     title,
                                "doc_type":  doc_type,
                                "url":       url,
                            })

            except Exception as e:
                log.debug(f"Failed to fetch announcements for {code}: {e}")
                continue

    await db.commit()
    log.info(f"Announcement worker: inserted {inserted} new announcements, {len(market_sensitive_new)} market-sensitive")

    # Send notifications for market-sensitive announcements
    if market_sensitive_new:
        await _notify_subscribers(db, market_sensitive_new)


def _is_sensitive(doc_type: str, title: str) -> bool:
    sensitive_types = {
        "Quarterly Activities Report",
        "Half Yearly Report",
        "Preliminary Final Report",
        "Annual Report",
        "Dividend",
        "Trading Halt",
        "Trading Halt Lifting",
        "Merger",
        "Acquisition",
        "Placement",
        "Earnings",
        "Results",
    }
    dt_lower = doc_type.lower()
    title_lower = title.lower()
    keywords = ["dividend", "results", "profit", "loss", "halt", "acquisition",
                "merger", "placement", "ipo", "earnings", "quarterly"]
    return (
        any(s.lower() in dt_lower for s in sensitive_types) or
        any(k in title_lower for k in keywords)
    )


async def _notify_subscribers(db, announcements: list[dict]) -> None:
    from app.services.notification_service import send_announcement_notification

    for ann in announcements:
        code = ann["asx_code"]

        # Get users subscribed to this stock (via watchlist or explicit subscription)
        result = await db.execute(text("""
            SELECT DISTINCT
                u.id        AS user_id,
                u.email,
                u.name,
                c.company_name,
                np.announcements_email,
                np.announcements_sms,
                np.phone_number
            FROM users.users u
            JOIN users.notification_preferences np ON np.user_id = u.id
            LEFT JOIN market.companies c ON c.asx_code = :code
            WHERE u.subscription_status = 'active'
              AND (np.announcements_email = TRUE OR np.announcements_sms = TRUE)
              AND (
                EXISTS (
                    SELECT 1 FROM users.watchlist_items wi
                    JOIN users.watchlists w ON w.id = wi.watchlist_id
                    WHERE w.user_id = u.id AND wi.asx_code = :code
                )
                OR EXISTS (
                    SELECT 1 FROM users.announcement_subscriptions asub
                    WHERE asub.user_id = u.id AND asub.asx_code = :code
                )
              )
        """), {"code": code})
        subscribers = result.fetchall()

        for sub in subscribers:
            await send_announcement_notification(
                db=db,
                user_id=str(sub.user_id),
                email=sub.email if sub.announcements_email else None,
                phone=sub.phone_number if sub.announcements_sms else None,
                asx_code=code,
                company_name=sub.company_name,
                title=ann["title"],
                doc_type=ann["doc_type"],
                url=ann.get("url"),
                via_email=bool(sub.announcements_email),
                via_sms=bool(sub.announcements_sms),
            )

    await db.commit()
