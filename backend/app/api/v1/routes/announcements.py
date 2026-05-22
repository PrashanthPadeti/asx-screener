"""
ASX Screener — Announcements Routes
======================================
GET /announcements          — paginated feed with filters + tab + date range + watchlist
GET /announcements/latest   — most recent N announcements (for live ticker), deduplicated
GET /announcements/{code}   — all announcements for a specific company
"""
import logging
from datetime import date as DateType
from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.core.deps import get_current_user
from app.db.session import get_db
from app.core.cache import cache_get, cache_set, make_key, MARKET_TTL

log = logging.getLogger(__name__)
router = APIRouter()

# Known ASX document types for filter UI
DOCUMENT_TYPES = [
    "Quarterly Activities Report",
    "Half Yearly Report",
    "Annual Report",
    "Preliminary Final Report",
    "Dividend",
    "Trading Halt",
    "Merger",
    "Acquisition",
    "Placement",
    "Earnings",
    "Director Change",
    "Investor Presentation",
    "AGM",
]

# Tab → SQL WHERE fragment
TAB_FILTERS: dict[str, str] = {
    "announcements":    "a.document_type IS NOT NULL",
    "market_sensitive": "(a.market_sensitive = TRUE OR a.price_sensitive = TRUE)",
    "trading_halts":    "a.document_type ILIKE '%Trading Halt%'",
    "results":          (
        "(a.document_type ILIKE '%Quarterly%'"
        " OR a.document_type ILIKE '%Half Yearly%'"
        " OR a.document_type ILIKE '%Annual Report%'"
        " OR a.document_type ILIKE '%Preliminary Final%'"
        " OR a.document_type ILIKE '%Earnings%')"
    ),
    "dividends":        "a.document_type ILIKE '%Dividend%'",
    "capital_raisings": (
        "(a.document_type ILIKE '%Placement%'"
        " OR a.document_type ILIKE '%Capital Raising%'"
        " OR a.document_type ILIKE '%Rights Issue%'"
        " OR a.document_type ILIKE '%Entitlement%'"
        " OR a.document_type ILIKE '%SPP%')"
    ),
    "director_changes": (
        "(a.document_type ILIKE '%Director%'"
        " OR a.document_type ILIKE '%Substantial Holder%'"
        " OR a.document_type ILIKE '%Becoming a substantial%')"
    ),
}


def _row_to_dict(r) -> dict:
    return {
        "id":               r.id,
        "asx_code":         r.asx_code,
        "company_name":     r.company_name,
        "title":            r.title,
        "document_type":    r.document_type,
        "url":              r.url,
        "market_sensitive": r.market_sensitive,
        "price_sensitive":  r.price_sensitive if hasattr(r, "price_sensitive") else r.market_sensitive,
        "released_at":      r.released_at.isoformat() if r.released_at else None,
        "num_pages":        r.num_pages if hasattr(r, "num_pages") else None,
    }


# ── Feed ──────────────────────────────────────────────────────────────────────

@router.get("")
async def get_announcements(
    asx_code:       Optional[str]       = Query(None),
    sector:         Optional[str]       = Query(None),
    document_type:  Optional[str]       = Query(None),
    sensitive_only: bool                = Query(False),
    search:         Optional[str]       = Query(None),
    tab:            Optional[str]       = Query(None),          # tab-based filtering
    date_from:      Optional[DateType]  = Query(None),          # YYYY-MM-DD
    date_to:        Optional[DateType]  = Query(None),          # YYYY-MM-DD
    watchlist_only: bool                = Query(False),         # Pro+ feature
    limit:          int                 = Query(50, ge=1, le=200),
    offset:         int                 = Query(0, ge=0),
    current_user:   dict                = Depends(get_current_user),
    db:             AsyncSession        = Depends(get_db),
):
    filters = ["1=1"]
    params: dict = {"limit": limit, "offset": offset}

    # ── Tab filter ────────────────────────────────────────────────────────────
    if tab and tab in TAB_FILTERS:
        filters.append(TAB_FILTERS[tab])

    # ── Watchlist filter (Pro+) ───────────────────────────────────────────────
    if watchlist_only and current_user:
        wl_result = await db.execute(text("""
            SELECT DISTINCT wi.asx_code
            FROM users.watchlist_items wi
            JOIN users.watchlists w ON w.id = wi.watchlist_id
            WHERE w.user_id = :user_id
        """), {"user_id": current_user["id"]})
        wl_codes = [r[0] for r in wl_result.fetchall()]
        if wl_codes:
            placeholders = ", ".join([f":wl_{i}" for i in range(len(wl_codes))])
            filters.append(f"a.asx_code IN ({placeholders})")
            for i, code in enumerate(wl_codes):
                params[f"wl_{i}"] = code
        else:
            # No watchlist items → empty result
            return {
                "total": 0, "limit": limit, "offset": offset,
                "announcements": [], "document_types": DOCUMENT_TYPES,
            }

    # ── Standard filters ──────────────────────────────────────────────────────
    if asx_code:
        filters.append("a.asx_code = :asx_code")
        params["asx_code"] = asx_code.upper()
    if sector:
        filters.append("c.gics_sector = :sector")
        params["sector"] = sector
    if document_type:
        filters.append("a.document_type ILIKE :doc_type")
        params["doc_type"] = f"%{document_type}%"
    if sensitive_only:
        filters.append("(a.market_sensitive = TRUE OR a.price_sensitive = TRUE)")
    if search:
        filters.append(
            "(a.title ILIKE :search OR a.asx_code ILIKE :search OR c.company_name ILIKE :search)"
        )
        params["search"] = f"%{search}%"
    if date_from:
        filters.append("a.released_at >= :date_from")
        params["date_from"] = date_from
    if date_to:
        filters.append("a.released_at < :date_to_excl")
        params["date_to_excl"] = f"{date_to} 23:59:59"

    where = " AND ".join(filters)

    # ── Deduplicated query ────────────────────────────────────────────────────
    # DISTINCT ON (asx_code, title, released_at) eliminates duplicate filings
    # that appear when the same document is ingested more than once.
    result = await db.execute(text(f"""
        SELECT * FROM (
            SELECT DISTINCT ON (a.asx_code, a.title, a.released_at)
                a.id, a.asx_code, c.company_name, a.title,
                a.document_type, a.url,
                a.market_sensitive, a.price_sensitive,
                a.released_at, a.num_pages
            FROM market.asx_announcements a
            LEFT JOIN market.companies c ON c.asx_code = a.asx_code
            WHERE {where}
            ORDER BY a.asx_code, a.title, a.released_at, a.id
        ) deduped
        ORDER BY released_at DESC NULLS LAST
        LIMIT :limit OFFSET :offset
    """), params)
    rows = result.fetchall()

    count_result = await db.execute(text(f"""
        SELECT COUNT(*) FROM (
            SELECT DISTINCT ON (a.asx_code, a.title, a.released_at) a.id
            FROM market.asx_announcements a
            LEFT JOIN market.companies c ON c.asx_code = a.asx_code
            WHERE {where}
            ORDER BY a.asx_code, a.title, a.released_at, a.id
        ) deduped
    """), {k: v for k, v in params.items() if k not in ("limit", "offset")})
    total = count_result.scalar() or 0

    return {
        "total":          total,
        "limit":          limit,
        "offset":         offset,
        "announcements":  [_row_to_dict(r) for r in rows],
        "document_types": DOCUMENT_TYPES,
    }


# ── Latest ticker ─────────────────────────────────────────────────────────────

@router.get("/latest")
async def get_latest_announcements(
    limit: int = Query(30, ge=1, le=50),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _key = make_key("announcements", "latest", str(limit))
    cached = await cache_get(_key)
    if cached:
        return cached

    result = await db.execute(text("""
        SELECT * FROM (
            SELECT DISTINCT ON (a.asx_code, a.title, a.released_at)
                a.id, a.asx_code, c.company_name, a.title,
                a.document_type, a.url,
                a.market_sensitive, a.price_sensitive,
                a.released_at, a.num_pages
            FROM market.asx_announcements a
            LEFT JOIN market.companies c ON c.asx_code = a.asx_code
            ORDER BY a.asx_code, a.title, a.released_at, a.id
        ) deduped
        ORDER BY released_at DESC NULLS LAST
        LIMIT :limit
    """), {"limit": limit})
    rows = result.fetchall()
    data = {"announcements": [_row_to_dict(r) for r in rows]}
    await cache_set(_key, data, ttl=MARKET_TTL)
    return data


# ── By company ────────────────────────────────────────────────────────────────

@router.get("/{code}")
async def get_company_announcements(
    code: str,
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    asx_code = code.upper()
    result = await db.execute(text("""
        SELECT * FROM (
            SELECT DISTINCT ON (a.title, a.released_at)
                a.id, a.asx_code, c.company_name, a.title,
                a.document_type, a.url,
                a.market_sensitive, a.price_sensitive,
                a.released_at, a.num_pages
            FROM market.asx_announcements a
            LEFT JOIN market.companies c ON c.asx_code = a.asx_code
            WHERE a.asx_code = :code
            ORDER BY a.title, a.released_at, a.id
        ) deduped
        ORDER BY released_at DESC NULLS LAST
        LIMIT :limit OFFSET :offset
    """), {"code": asx_code, "limit": limit, "offset": offset})
    rows = result.fetchall()

    count_result = await db.execute(text("""
        SELECT COUNT(*) FROM (
            SELECT DISTINCT ON (a.title, a.released_at) a.id
            FROM market.asx_announcements a
            WHERE a.asx_code = :code
            ORDER BY a.title, a.released_at, a.id
        ) deduped
    """), {"code": asx_code})
    total = count_result.scalar() or 0

    return {"asx_code": asx_code, "total": total, "announcements": [_row_to_dict(r) for r in rows]}
