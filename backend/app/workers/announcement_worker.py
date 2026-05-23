"""
ASX Screener — Announcement Worker
====================================
Fetches recent ASX announcements from EODHD for all companies in the
screener universe and stores them in market.asx_announcements.

Validation rules
----------------
1. Official ASX filings (URL contains asx.com.au):
   - Always accepted — source is authoritative and mapping is guaranteed.
   - source_type = 'asx_filing', source_label = 'ASX'

2. Market news articles (non-ASX URLs):
   - Only accepted if the article is demonstrably about the target company.
   - Relevance check: ASX code OR significant company-name words must appear
     in the title. Items that fail this check are dropped silently.
   - source_type = 'market_news', source_label = <domain-based label>

3. Structured company filings (non-ASX URL, known doc type):
   - Accepted if doc_type is a recognised filing category (not "General"/"News").
   - Relevance check still applied.
   - source_type = 'company_filing', source_label = 'Company Filing'

Also sends notification emails/SMS to subscribed users when market-sensitive
announcements are filed.

Runs every 10 minutes via APScheduler.
"""
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx
from sqlalchemy import text

from app.db.session import AsyncSessionLocal
from app.core.config import settings

log = logging.getLogger(__name__)

EODHD_BASE = "https://eodhd.com/api"

# Doc types that indicate a structured company filing (not general news)
FILING_DOC_TYPES = {
    "quarterly activities report", "half yearly report", "annual report",
    "preliminary final report", "dividend", "trading halt",
    "trading halt lifting", "merger", "acquisition", "placement",
    "earnings", "results", "investor presentation", "agm", "rights issue",
    "entitlement offer", "director", "substantial holder", "capital raising",
}

# News domains → display labels
NEWS_DOMAIN_LABELS: dict[str, str] = {
    "finance.yahoo.com":       "Yahoo Finance",
    "marketwatch.com":         "MarketWatch",
    "reuters.com":             "Reuters",
    "bloomberg.com":           "Bloomberg",
    "afr.com":                 "AFR",
    "smh.com.au":              "SMH",
    "theaustralian.com.au":    "The Australian",
    "abc.net.au":              "ABC News",
    "businessinsider.com":     "Business Insider",
    "fool.com":                "Motley Fool",
    "benzinga.com":            "Benzinga",
    "seekingalpha.com":        "Seeking Alpha",
    "wsj.com":                 "WSJ",
    "ft.com":                  "Financial Times",
    "cnbc.com":                "CNBC",
    "investing.com":           "Investing.com",
}

# Common company-name suffixes to strip when doing relevance checks
_COMPANY_SUFFIXES = (
    " limited", " ltd", " group", " corporation", " corp",
    " pty", " holdings", " inc", " plc", " nv", " sa",
)


def _classify_source(url: Optional[str], doc_type: str) -> tuple[str, str]:
    """
    Classify a news item by source.

    Returns (source_type, source_label):
      - ('asx_filing',     'ASX')             — official exchange filing
      - ('company_filing', 'Company Filing')   — structured filing via news API
      - ('market_news',    '<site name>')      — general market news article
    """
    if not url:
        # No URL → treat as ASX filing (direct API data)
        return "asx_filing", "ASX"

    url_lower = url.lower()

    # Official ASX filing
    if "asx.com.au" in url_lower or "announcements.asx.com.au" in url_lower:
        return "asx_filing", "ASX"

    # Structured filing with a recognised doc type
    dt_lower = (doc_type or "").lower()
    is_filing_type = any(ft in dt_lower for ft in FILING_DOC_TYPES)
    if is_filing_type and "general" not in dt_lower and "news" not in dt_lower:
        # Look up domain label first
        for domain, label in NEWS_DOMAIN_LABELS.items():
            if domain in url_lower:
                # From a news site despite having a filing doc_type → still news
                return "market_news", label
        return "company_filing", "Company Filing"

    # General market news
    for domain, label in NEWS_DOMAIN_LABELS.items():
        if domain in url_lower:
            return "market_news", label

    return "market_news", "Finance News"


def _is_company_relevant(title: str, asx_code: str, company_name: str) -> bool:
    """
    Return True if the article title is demonstrably about the given company.

    Checks (in order):
      1. ASX code appears in the title (e.g. "(CBA)" or "CBA:").
      2. Significant words from the company name appear in the title.
         'Significant' = longer than 3 chars, not a common stop word.
    """
    title_lower = title.lower()
    code_lower  = asx_code.lower()

    # 1. Ticker present in title
    if code_lower in title_lower:
        return True

    # 2. Company name words present in title
    if company_name:
        clean = company_name.lower()
        for suffix in _COMPANY_SUFFIXES:
            clean = clean.replace(suffix, "")

        stop_words = {"the", "and", "for", "new", "inc", "pty", "ltd", "group"}
        name_words = [
            w for w in clean.split()
            if len(w) > 3 and w not in stop_words
        ]
        if name_words and any(w in title_lower for w in name_words):
            return True

    return False


def _is_sensitive(doc_type: str, title: str) -> bool:
    sensitive_types = {
        "quarterly activities report", "half yearly report",
        "preliminary final report", "annual report",
        "dividend", "trading halt", "trading halt lifting",
        "merger", "acquisition", "placement", "earnings", "results",
    }
    dt_lower    = (doc_type or "").lower()
    title_lower = title.lower()
    keywords    = [
        "dividend", "results", "profit", "loss", "halt", "acquisition",
        "merger", "placement", "ipo", "earnings", "quarterly",
    ]
    return (
        any(s in dt_lower for s in sensitive_types) or
        any(k in title_lower for k in keywords)
    )


# ── Main worker ───────────────────────────────────────────────────────────────

async def fetch_announcements() -> None:
    async with AsyncSessionLocal() as db:
        try:
            await _run(db)
        except Exception as e:
            log.error(f"Announcement worker error: {e}", exc_info=True)
        finally:
            try:
                await db.execute(text("""
                    INSERT INTO meta.job_heartbeat (job_id, last_run_at, run_count)
                    VALUES ('asx_announcements', NOW(), 1)
                    ON CONFLICT (job_id) DO UPDATE SET
                        last_run_at = NOW(),
                        run_count   = meta.job_heartbeat.run_count + 1
                """))
                await db.commit()
            except Exception as hb_err:
                log.debug(f"Heartbeat write failed: {hb_err}")


async def _run(db) -> None:
    if not settings.EODHD_API_KEY:
        log.debug("EODHD_API_KEY not set — skipping announcement fetch")
        return

    # Fetch top 200 ASX codes by market cap, including company names for
    # relevance validation of market-news articles.
    result = await db.execute(text("""
        SELECT u.asx_code, COALESCE(c.company_name, '') AS company_name
        FROM screener.universe u
        LEFT JOIN market.companies c ON c.asx_code = u.asx_code
        ORDER BY u.market_cap DESC NULLS LAST
        LIMIT 200
    """))
    companies: dict[str, str] = {r.asx_code: r.company_name for r in result.fetchall()}

    if not companies:
        return

    inserted  = 0
    skipped   = 0
    sensitive_new: list[dict] = []

    async with httpx.AsyncClient(timeout=30) as client:
        for code, company_name in companies.items():
            try:
                resp = await client.get(
                    f"{EODHD_BASE}/news",
                    params={
                        "s":         f"{code}.AU",
                        "api_token": settings.EODHD_API_KEY,
                        "fmt":       "json",
                        "limit":     10,
                        "offset":    0,
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

                    try:
                        date_str = item.get("date") or item.get("datetime")
                        released_at = (
                            datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                            if date_str else datetime.now(timezone.utc)
                        )
                    except Exception:
                        released_at = datetime.now(timezone.utc)

                    # ── Source classification ─────────────────────────────
                    source_type, source_label = _classify_source(url, doc_type)

                    # ── Company relevance validation ──────────────────────
                    # For market news and company filings from news sites,
                    # validate the article is genuinely about this company.
                    # Official ASX filings (asx.com.au) are always trusted.
                    if source_type != "asx_filing":
                        if not _is_company_relevant(title, code, company_name):
                            skipped += 1
                            log.debug(
                                f"Skipped [{code}] '{title[:60]}' "
                                f"(not relevant, source: {source_label})"
                            )
                            continue

                    sensitive = _is_sensitive(doc_type, title)

                    result2 = await db.execute(text("""
                        INSERT INTO market.asx_announcements
                            (asx_code, announcement_id, title, document_type,
                             url, market_sensitive, released_at,
                             source_type, source_label)
                        VALUES
                            (:code, :ann_id, :title, :doc_type,
                             :url, :sensitive, :released_at,
                             :source_type, :source_label)
                        ON CONFLICT (asx_code, announcement_id) DO UPDATE
                            SET source_type  = EXCLUDED.source_type,
                                source_label = EXCLUDED.source_label
                        RETURNING id, (xmax = 0) AS is_new_insert
                    """), {
                        "code":         code,
                        "ann_id":       ann_id or f"{code}_{released_at.isoformat()}",
                        "title":        title,
                        "doc_type":     doc_type,
                        "url":          url,
                        "sensitive":    sensitive,
                        "released_at":  released_at,
                        "source_type":  source_type,
                        "source_label": source_label,
                    })
                    row2 = result2.fetchone()
                    # xmax = 0 means genuine INSERT; non-zero means ON CONFLICT UPDATE
                    # Only count/notify for brand-new announcements, not re-seen ones
                    if row2 and row2.is_new_insert:
                        inserted += 1
                        if sensitive:
                            sensitive_new.append({
                                "asx_code":  code,
                                "title":     title,
                                "doc_type":  doc_type,
                                "url":       url,
                            })

            except Exception as e:
                log.debug(f"Failed to fetch announcements for {code}: {e}")
                continue

    await db.commit()
    log.info(
        f"Announcement worker: {inserted} inserted, "
        f"{skipped} skipped (irrelevant), "
        f"{len(sensitive_new)} market-sensitive"
    )

    if sensitive_new:
        await _notify_subscribers(db, sensitive_new)


async def _notify_subscribers(db, announcements: list[dict]) -> None:
    from app.services.notification_service import send_announcement_notification

    for ann in announcements:
        code = ann["asx_code"]

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
