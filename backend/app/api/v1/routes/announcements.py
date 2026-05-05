"""
ASX Screener — Announcements Routes
======================================
GET /announcements          — paginated feed with filters
GET /announcements/latest   — most recent N announcements (for live ticker)
GET /announcements/{code}   — all announcements for a specific company
"""
import logging
from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.core.deps import get_current_user
from app.db.session import get_db

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
    asx_code:      Optional[str] = Query(None),
    sector:        Optional[str] = Query(None),
    document_type: Optional[str] = Query(None),
    sensitive_only: bool         = Query(False),
    search:        Optional[str] = Query(None),
    limit:         int           = Query(50, ge=1, le=200),
    offset:        int           = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    filters = ["1=1"]
    params: dict = {"limit": limit, "offset": offset}

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
        filters.append("(a.title ILIKE :search OR a.asx_code ILIKE :search OR c.company_name ILIKE :search)")
        params["search"] = f"%{search}%"

    where = " AND ".join(filters)

    result = await db.execute(text(f"""
        SELECT
            a.id, a.asx_code, c.company_name, a.title,
            a.document_type, a.url,
            a.market_sensitive, a.price_sensitive,
            a.released_at, a.num_pages
        FROM market.asx_announcements a
        LEFT JOIN market.companies c ON c.asx_code = a.asx_code
        WHERE {where}
        ORDER BY a.released_at DESC NULLS LAST
        LIMIT :limit OFFSET :offset
    """), params)
    rows = result.fetchall()

    count_result = await db.execute(text(f"""
        SELECT COUNT(*) FROM market.asx_announcements a
        LEFT JOIN market.companies c ON c.asx_code = a.asx_code
        WHERE {where}
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
    limit: int = Query(20, ge=1, le=50),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(text("""
        SELECT
            a.id, a.asx_code, c.company_name, a.title,
            a.document_type, a.url,
            a.market_sensitive, a.price_sensitive,
            a.released_at, a.num_pages
        FROM market.asx_announcements a
        LEFT JOIN market.companies c ON c.asx_code = a.asx_code
        ORDER BY a.released_at DESC NULLS LAST
        LIMIT :limit
    """), {"limit": limit})
    rows = result.fetchall()
    return {"announcements": [_row_to_dict(r) for r in rows]}


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
        SELECT
            a.id, a.asx_code, c.company_name, a.title,
            a.document_type, a.url,
            a.market_sensitive, a.price_sensitive,
            a.released_at, a.num_pages
        FROM market.asx_announcements a
        LEFT JOIN market.companies c ON c.asx_code = a.asx_code
        WHERE a.asx_code = :code
        ORDER BY a.released_at DESC NULLS LAST
        LIMIT :limit OFFSET :offset
    """), {"code": asx_code, "limit": limit, "offset": offset})
    rows = result.fetchall()

    count_result = await db.execute(text(
        "SELECT COUNT(*) FROM market.asx_announcements WHERE asx_code = :code"
    ), {"code": asx_code})
    total = count_result.scalar() or 0

    return {"asx_code": asx_code, "total": total, "announcements": [_row_to_dict(r) for r in rows]}
