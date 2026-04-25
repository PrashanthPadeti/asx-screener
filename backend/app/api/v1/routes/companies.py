"""
ASX Screener — Companies API Routes
GET /api/v1/companies         — List all companies (paginated, filterable)
GET /api/v1/companies/search  — Autocomplete search by name or ASX code
GET /api/v1/companies/{code}  — Full company detail
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import Optional
import math

from app.db.session import get_db
from app.schemas.company import (
    CompanyListItem, CompanyDetail,
    CompanySearchResult, CompanyListResponse
)

router = APIRouter()


# ── List Companies ────────────────────────────────────────────

@router.get("", response_model=CompanyListResponse)
async def list_companies(
    page:       int            = Query(1, ge=1),
    page_size:  int            = Query(50, ge=1, le=200),
    sector:     Optional[str]  = Query(None, description="Filter by GICS sector"),
    is_reit:    Optional[bool] = Query(None),
    is_miner:   Optional[bool] = Query(None),
    is_asx200:  Optional[bool] = Query(None),
    status:     str            = Query("active"),
    sort_by:    str            = Query("asx_code", description="asx_code | company_name"),
    sort_dir:   str            = Query("asc", description="asc | desc"),
    db: AsyncSession = Depends(get_db),
):
    # Build WHERE clauses
    filters = ["status = :status"]
    params: dict = {"status": status}

    if sector:
        filters.append("gics_sector = :sector")
        params["sector"] = sector
    if is_reit is not None:
        filters.append("is_reit = :is_reit")
        params["is_reit"] = is_reit
    if is_miner is not None:
        filters.append("is_miner = :is_miner")
        params["is_miner"] = is_miner
    if is_asx200 is not None:
        filters.append("is_asx200 = :is_asx200")
        params["is_asx200"] = is_asx200

    where = " AND ".join(filters)

    # Validate sort column (whitelist to prevent SQL injection)
    valid_sort = {"asx_code", "company_name", "gics_sector", "listing_date"}
    if sort_by not in valid_sort:
        sort_by = "asx_code"
    sort_dir = "DESC" if sort_dir.lower() == "desc" else "ASC"

    # Count total
    count_sql = f"SELECT COUNT(*) FROM market.companies WHERE {where}"
    result = await db.execute(text(count_sql), params)
    total = result.scalar()

    # Fetch page
    offset = (page - 1) * page_size
    params["limit"] = page_size
    params["offset"] = offset

    data_sql = f"""
        SELECT
            asx_code, company_name, gics_sector, gics_industry_group,
            is_reit, is_miner, is_asx200, status, listing_date
        FROM market.companies
        WHERE {where}
        ORDER BY {sort_by} {sort_dir}
        LIMIT :limit OFFSET :offset
    """
    result = await db.execute(text(data_sql), params)
    rows = result.mappings().all()

    return CompanyListResponse(
        data=[CompanyListItem(**dict(r)) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=math.ceil(total / page_size),
    )


# ── Search / Autocomplete ─────────────────────────────────────

@router.get("/search", response_model=list[CompanySearchResult])
async def search_companies(
    q:    str = Query(..., min_length=1, description="ASX code or company name"),
    limit: int = Query(10, ge=1, le=30),
    db: AsyncSession = Depends(get_db),
):
    """
    Fast autocomplete using pg_trgm similarity for name search.
    Exact ASX code match is boosted to the top.
    """
    sql = """
        SELECT asx_code, company_name, gics_sector, is_reit, is_miner
        FROM market.companies
        WHERE status = 'active'
          AND (
              asx_code ILIKE :code_query
              OR company_name ILIKE :name_query
              OR similarity(company_name, :q) > 0.15
          )
        ORDER BY
            CASE WHEN asx_code ILIKE :code_query THEN 0 ELSE 1 END,
            similarity(company_name, :q) DESC,
            asx_code ASC
        LIMIT :limit
    """
    result = await db.execute(text(sql), {
        "q": q,
        "code_query": f"{q}%",
        "name_query": f"%{q}%",
        "limit": limit,
    })
    rows = result.mappings().all()
    return [CompanySearchResult(**dict(r)) for r in rows]


# ── Company Detail ────────────────────────────────────────────

@router.get("/{asx_code}", response_model=CompanyDetail)
async def get_company(
    asx_code: str,
    db: AsyncSession = Depends(get_db),
):
    sql = """
        SELECT *
        FROM market.companies
        WHERE asx_code = :asx_code
    """
    result = await db.execute(text(sql), {"asx_code": asx_code.upper()})
    row = result.mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail=f"Company {asx_code.upper()} not found")

    return CompanyDetail(**dict(row))
