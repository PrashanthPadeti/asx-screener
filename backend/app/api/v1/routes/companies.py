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
import logging
import json

import httpx

from app.db.session import get_db
from app.core.config import settings
from app.schemas.company import (
    CompanyListItem, CompanyDetail,
    CompanySearchResult, CompanyListResponse,
    CompanyOverview, AnnualFinancialsRow, FinancialsResponse,
    PricePoint, PricesResponse,
    DividendRecord, DividendsSummary, DividendsResponse,
    PeerStock, PeersResponse,
    HalfYearlyRow, HalfYearlyResponse,
    AnnouncementRow, AnnouncementsResponse,
)

log = logging.getLogger(__name__)

# ASX public announcements API — try multiple URL patterns (ASX changes these periodically)
_ASX_ANN_URLS = [
    "https://www.asx.com.au/asx/1/company/{code}/announcements?count={count}&market_sensitive=0",
    "https://www.asx.com.au/asx/1/security/{code}/announcements?count={count}&market_sensitive=0",
    "https://www.asx.com.au/asx/1/company/{code}/announcements?count={count}",
]
_ASX_HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "en-AU,en;q=0.9",
    "Referer":         "https://www.asx.com.au/",
    "Origin":          "https://www.asx.com.au",
}

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


# ── Company Overview (screener.universe) ──────────────────────

@router.get("/{asx_code}/overview", response_model=CompanyOverview)
async def get_company_overview(
    asx_code: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Returns all pre-computed screener.universe metrics for one company.
    Used by the Overview and Technicals tabs on the company detail page.
    """
    sql = """
        SELECT
            price, price_date, market_cap, volume, avg_volume_20d, high_52w, low_52w,
            pe_ratio, forward_pe, peg_ratio, price_to_book, price_to_sales, price_to_fcf,
            ev, ev_to_ebitda, ev_to_ebit, ev_to_revenue, graham_number, fcf_yield,
            dividend_yield, grossed_up_yield, franking_pct, dps_ttm, dps_fy0,
            payout_ratio, ex_div_date, dividend_consecutive_yrs, dividend_cagr_3y,
            gross_margin, ebitda_margin, net_margin, operating_margin,
            roe, roa, roce, avg_roe_3y,
            revenue_ttm, ebitda_ttm, net_profit_ttm,
            revenue_fy0, revenue_fy1, revenue_fy2,
            net_profit_fy0, net_profit_fy1,
            eps_fy0, eps_fy1,
            total_assets, total_equity, total_debt, net_debt, cash,
            book_value_per_share, debt_to_equity, current_ratio,
            cfo_fy0, capex_fy0, fcf_fy0,
            revenue_growth_1y, revenue_growth_3y_cagr, revenue_cagr_5y,
            earnings_growth_1y, eps_growth_3y_cagr,
            revenue_growth_yoy_q, eps_growth_yoy_q,
            revenue_growth_hoh, net_income_growth_hoh, eps_growth_hoh,
            piotroski_f_score, altman_z_score,
            short_pct, short_interest_chg_1w,
            percent_insiders, percent_institutions,
            analyst_rating, analyst_target_price, analyst_upside,
            return_1w, return_1m, return_3m, return_6m, return_1y, return_ytd,
            return_3y, return_5y, drawdown_from_ath,
            rsi_14, adx_14, macd, macd_signal,
            sma_20, sma_50, sma_200, ema_20,
            bb_upper, bb_lower, atr_14, obv,
            volatility_20d, volatility_60d, beta_1y, sharpe_1y,
            momentum_3m, momentum_6m,
            composite_score, value_score, quality_score,
            growth_score, momentum_score, income_score,
            COALESCE(pros, '{}') AS pros,
            COALESCE(cons, '{}') AS cons
        FROM screener.universe
        WHERE asx_code = :asx_code
    """
    result = await db.execute(text(sql), {"asx_code": asx_code.upper()})
    row = result.mappings().first()

    if not row:
        raise HTTPException(
            status_code=404,
            detail=f"No screener data found for {asx_code.upper()}. "
                   "Company may not be in the active universe."
        )

    return CompanyOverview(**dict(row))


# ── Company Financials (multi-year annual) ────────────────────

@router.get("/{asx_code}/financials", response_model=FinancialsResponse)
async def get_company_financials(
    asx_code: str,
    years: int = Query(7, ge=1, le=15, description="Number of fiscal years to return"),
    db: AsyncSession = Depends(get_db),
):
    """
    Multi-year annual financials from financials.annual_pnl + balance_sheet + cashflow.
    Returns up to `years` fiscal years, most recent first.
    """
    sql = """
        SELECT
            p.fiscal_year,
            p.period_end_date,
            p.revenue,
            p.gross_profit,
            p.ebitda,
            p.ebit,
            p.net_profit,
            p.eps,
            p.dps,
            p.gpm,
            p.ebitda_margin,
            p.npm,
            b.total_assets,
            b.total_equity,
            b.total_debt,
            b.net_debt,
            b.cash_equivalents,
            b.book_value_per_share,
            CASE
                WHEN b.total_equity IS NOT NULL AND b.total_equity != 0
                THEN b.total_debt / b.total_equity
                ELSE NULL
            END AS debt_to_equity,
            c.cfo,
            c.capex,
            c.fcf
        FROM financials.annual_pnl p
        LEFT JOIN financials.annual_balance_sheet b
            ON b.asx_code = p.asx_code AND b.fiscal_year = p.fiscal_year
        LEFT JOIN financials.annual_cashflow c
            ON c.asx_code = p.asx_code AND c.fiscal_year = p.fiscal_year
        WHERE p.asx_code = :asx_code
        ORDER BY p.fiscal_year DESC
        LIMIT :years
    """
    result = await db.execute(
        text(sql), {"asx_code": asx_code.upper(), "years": years}
    )
    rows = result.mappings().all()

    return FinancialsResponse(
        asx_code=asx_code.upper(),
        years=[AnnualFinancialsRow(**dict(r)) for r in rows],
    )


# ── Company Price History ─────────────────────────────────────

@router.get("/{asx_code}/prices", response_model=PricesResponse)
async def get_company_prices(
    asx_code: str,
    period: str = Query("1y", description="1m | 3m | 6m | 1y | 3y | 5y | max"),
    db: AsyncSession = Depends(get_db),
):
    """
    OHLCV price history from market.daily_prices for a given period.
    Returns ascending date order suitable for charting.
    """
    period_intervals: dict[str, str] = {
        "1w":  "7 days",
        "1m":  "1 month",
        "3m":  "3 months",
        "6m":  "6 months",
        "1y":  "1 year",
        "3y":  "3 years",
        "5y":  "5 years",
        "max": "50 years",
    }
    interval = period_intervals.get(period, "1 year")

    # interval comes from our own whitelist — safe to embed in SQL
    sql = f"""
        SELECT
            time::date            AS date,
            open::double precision,
            high::double precision,
            low::double precision,
            close::double precision,
            volume
        FROM market.daily_prices
        WHERE asx_code = :asx_code
          AND time >= NOW() - INTERVAL '{interval}'
        ORDER BY time ASC
    """
    result = await db.execute(text(sql), {"asx_code": asx_code.upper()})
    rows = result.mappings().all()

    price_points = [
        PricePoint(
            date=str(r["date"]),
            open=float(r["open"])   if r["open"]   is not None else None,
            high=float(r["high"])   if r["high"]   is not None else None,
            low=float(r["low"])     if r["low"]    is not None else None,
            close=float(r["close"]),
            volume=int(r["volume"]) if r["volume"] is not None else None,
        )
        for r in rows
    ]

    return PricesResponse(
        asx_code=asx_code.upper(),
        period=period,
        data=price_points,
    )


# ── Company Dividends ─────────────────────────────────────────

@router.get("/{asx_code}/dividends", response_model=DividendsResponse)
async def get_company_dividends(
    asx_code: str,
    limit: int = Query(40, ge=1, le=200, description="Max dividend records to return"),
    db: AsyncSession = Depends(get_db),
):
    """
    Dividend history from market.dividends + summary stats from screener.universe.
    Returns most recent `limit` dividend payments, newest first.
    """
    code = asx_code.upper()

    try:
        # ── Summary stats from screener.universe ──────────────────────────────
        summary_sql = """
            SELECT
                dividend_yield::double precision,
                grossed_up_yield::double precision,
                franking_pct::double precision,
                dps_ttm::double precision,
                dps_fy0::double precision,
                payout_ratio::double precision,
                ex_div_date,
                dividend_consecutive_yrs,
                dividend_cagr_3y::double precision
            FROM screener.universe
            WHERE asx_code = :code
        """
        summary_result = await db.execute(text(summary_sql), {"code": code})
        summary_row = summary_result.mappings().first()

        if summary_row:
            row = dict(summary_row)
            summary = DividendsSummary(
                dividend_yield=row.get("dividend_yield"),
                grossed_up_yield=row.get("grossed_up_yield"),
                franking_pct=row.get("franking_pct"),
                dps_ttm=row.get("dps_ttm"),
                dps_fy0=row.get("dps_fy0"),
                payout_ratio=row.get("payout_ratio"),
                ex_div_date=row.get("ex_div_date"),
                dividend_consecutive_yrs=row.get("dividend_consecutive_yrs"),
                dividend_cagr_3y=row.get("dividend_cagr_3y"),
            )
        else:
            summary = DividendsSummary()

        # ── Dividend history from market.dividends ────────────────────────────
        # Actual columns (v2 transform): amount_per_share, pay_date, dividend_type
        # (migration 012 used 'amount'/'payment_date'/'div_type' — v2 pipeline differs)
        history_sql = """
            SELECT
                ex_date,
                pay_date                            AS payment_date,
                record_date,
                amount_per_share::double precision  AS amount,
                NULL::double precision              AS unadjusted_value,
                franking_pct::double precision,
                dividend_type                       AS div_type,
                currency
            FROM market.dividends
            WHERE asx_code = :code
            ORDER BY ex_date DESC
            LIMIT :limit
        """
        history_result = await db.execute(text(history_sql), {"code": code, "limit": limit})
        history_rows = history_result.mappings().all()
        history = [
            DividendRecord(
                ex_date=r["ex_date"],
                payment_date=r["payment_date"],
                record_date=r["record_date"],
                amount=r["amount"],
                unadjusted_value=r["unadjusted_value"],
                franking_pct=r["franking_pct"],
                div_type=r["div_type"],
                currency=r["currency"],
            )
            for r in history_rows
        ]

        return DividendsResponse(asx_code=code, summary=summary, history=history)

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        raise HTTPException(
            status_code=500,
            detail=f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
        )


# ── Company Peers ─────────────────────────────────────────────

@router.get("/{asx_code}/peers", response_model=PeersResponse)
async def get_company_peers(
    asx_code: str,
    limit: int = Query(15, ge=5, le=30, description="Max peers to return"),
    db: AsyncSession = Depends(get_db),
):
    """
    Peer companies from screener.universe sharing the same GICS industry group.
    Falls back to GICS sector if industry group returns fewer than 3 results.
    Returns up to `limit` peers sorted by market cap descending.
    """
    code = asx_code.upper()

    # Resolve GICS industry for this stock
    meta_sql = """
        SELECT gics_industry_group, gics_sector
        FROM market.companies
        WHERE asx_code = :code
    """
    meta = (await db.execute(text(meta_sql), {"code": code})).mappings().first()
    if not meta:
        raise HTTPException(status_code=404, detail=f"Company {code} not found")

    gics_industry = meta["gics_industry_group"]
    gics_sector   = meta["gics_sector"]

    # Reusable peer SELECT — DISTINCT ON asx_code prevents duplicates from
    # companies that have multiple rows in market.companies (normalised + raw names)
    def peer_select(filter_clause: str) -> str:
        return f"""
            SELECT DISTINCT ON (u.asx_code)
                u.asx_code,
                c.company_name,
                u.market_cap, u.price,
                u.pe_ratio, u.forward_pe, u.price_to_book, u.ev_to_ebitda,
                u.dividend_yield, u.grossed_up_yield, u.franking_pct,
                u.roe, u.net_margin, u.revenue_growth_1y,
                u.return_1y, u.return_ytd,
                u.piotroski_f_score, u.debt_to_equity
            FROM screener.universe u
            JOIN market.companies c ON c.asx_code = u.asx_code
            WHERE u.asx_code != :code
              AND {filter_clause}
              AND u.status = 'active'
            ORDER BY u.asx_code, u.market_cap DESC NULLS LAST
        """

    # Try industry-level peers first
    peers_sql = f"""
        SELECT * FROM ({peer_select("c.gics_industry_group = :industry")}) sub
        ORDER BY market_cap DESC NULLS LAST
        LIMIT :limit
    """
    rows = (await db.execute(text(peers_sql), {
        "code": code, "industry": gics_industry, "limit": limit
    })).mappings().all()

    # Fall back to sector if fewer than 3 industry peers
    label = gics_industry
    if len(rows) < 3 and gics_sector:
        sector_sql = f"""
            SELECT * FROM ({peer_select("c.gics_sector = :sector")}) sub
            ORDER BY market_cap DESC NULLS LAST
            LIMIT :limit
        """
        rows = (await db.execute(text(sector_sql), {
            "code": code, "sector": gics_sector, "limit": limit
        })).mappings().all()
        label = gics_sector

    return PeersResponse(
        asx_code=code,
        gics_industry=label,
        peers=[PeerStock(**dict(r)) for r in rows],
    )


# ── Company Half-Yearly Financials ────────────────────────────

@router.get("/{asx_code}/halfyearly", response_model=HalfYearlyResponse)
async def get_company_halfyearly(
    asx_code: str,
    periods: int = Query(8, ge=2, le=20, description="Number of half-yearly periods to return"),
    db: AsyncSession = Depends(get_db),
):
    """
    Half-yearly P&L from financials.half_year_pnl.
    Returns most recent `periods` half-years (e.g. 8 = 4 years), newest first.
    """
    # market.halfyearly_metrics is populated by halfyearly_compute.py from
    # quarterly staging data.  financials.half_year_pnl is schema-only (empty).
    sql = """
        SELECT
            period_label,
            period_end_date,
            revenue::double precision,
            gross_profit::double precision,
            ebitda::double precision,
            ebit::double precision,
            net_income::double precision            AS net_profit,
            eps::double precision,
            dps::double precision,
            franking_pct::double precision          AS dps_franking_pct,
            gross_margin::double precision          AS gpm,
            ebit_margin::double precision           AS ebitda_margin,
            net_margin::double precision            AS npm,
            revenue_growth_hoh::double precision,
            net_income_growth_hoh::double precision AS net_profit_growth_hoh,
            eps_growth_hoh::double precision,
            revenue_growth_yoy::double precision,
            eps_growth_yoy::double precision
        FROM market.halfyearly_metrics
        WHERE asx_code = :code
        ORDER BY period_end_date DESC
        LIMIT :periods
    """
    result = await db.execute(
        text(sql), {"code": asx_code.upper(), "periods": periods}
    )
    rows = result.mappings().all()

    return HalfYearlyResponse(
        asx_code=asx_code.upper(),
        periods=[HalfYearlyRow(**dict(r)) for r in rows],
    )


# ── Company Announcements ─────────────────────────────────────

@router.get("/{asx_code}/announcements", response_model=AnnouncementsResponse)
async def get_company_announcements(
    asx_code: str,
    limit: int = Query(default=30, ge=1, le=100, description="Max announcements to return"),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns recent ASX announcements for a company.

    Checks market.asx_announcements (populated by daily download script) first.
    If no DB records exist for this company, falls back to a live ASX API fetch
    and caches the results for future requests.

    PDF links are direct asx.com.au URLs — publicly accessible.
    """
    code = asx_code.upper()

    # ── DB query ──────────────────────────────────────────────────────────────
    result = await db.execute(text("""
        SELECT id, asx_code, announcement_id, released_at, document_date,
               title, document_type, url,
               market_sensitive, price_sensitive, num_pages, file_size_kb
        FROM market.asx_announcements
        WHERE asx_code = :code
        ORDER BY released_at DESC NULLS LAST
        LIMIT :limit
    """), {"code": code, "limit": limit})
    rows = result.mappings().all()

    if rows:
        return AnnouncementsResponse(
            asx_code=code,
            total=len(rows),
            data=[AnnouncementRow(**dict(r)) for r in rows],
            source="db",
        )

    # ── Live fallback — try multiple ASX URL patterns ────────────────────────
    log.info(f"Announcements: DB miss for {code} — fetching live from ASX API")
    announcements = []
    async with httpx.AsyncClient(timeout=12) as client:
        for url_tpl in _ASX_ANN_URLS:
            try:
                url = url_tpl.format(code=code, count=min(limit, 20))
                resp = await client.get(url, headers=_ASX_HEADERS)
                log.info(f"Announcements: {url} → {resp.status_code}")
                if resp.status_code == 200:
                    body = resp.json()
                    # Response is either {"data": [...]} or a list directly
                    if isinstance(body, list):
                        announcements = body
                    else:
                        announcements = body.get("data", [])
                    if announcements:
                        break  # success — stop trying other URLs
            except Exception as e:
                log.warning(f"Announcements fetch failed ({url_tpl}): {e}")
                continue

    if not announcements:
        return AnnouncementsResponse(asx_code=code, total=0, data=[], source="live")

    if not announcements:
        return AnnouncementsResponse(asx_code=code, total=0, data=[], source="live")

    # Cache to DB (fire-and-forget style — use sync insert via raw asyncpg)
    insert_rows = []
    for a in announcements:
        ann_id = str(a.get("id") or "").strip()
        if not ann_id:
            continue
        url = a.get("url") or ""
        if not url and a.get("relative_url"):
            url = "https://www.asx.com.au" + a["relative_url"]
        size_kb = (int(a.get("size", 0) or 0)) // 1024 or None
        insert_rows.append({
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
            "size_kb": size_kb,
        })

    if insert_rows:
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
            """), insert_rows)
            await db.commit()
        except Exception as e:
            log.warning(f"Announcements cache write failed for {code}: {e}")
            await db.rollback()

    # Build response from live data
    live_rows = []
    seq = 0
    for a in announcements:
        ann_id = str(a.get("id") or "").strip()
        if not ann_id:
            continue
        url = a.get("url") or ""
        if not url and a.get("relative_url"):
            url = "https://www.asx.com.au" + a["relative_url"]
        seq -= 1  # fake negative IDs so they don't clash with DB rows
        live_rows.append(AnnouncementRow(
            id=seq,
            asx_code=code,
            announcement_id=ann_id,
            released_at=a.get("document_release_date"),
            document_date=a.get("document_date"),
            title=(a.get("header") or a.get("document_type") or "").strip() or None,
            document_type=(a.get("document_type") or "").strip() or None,
            url=url or None,
            market_sensitive=bool(a.get("market_sensitive", False)),
            price_sensitive=bool(a.get("price_sensitive", False)),
            num_pages=a.get("number_of_pages"),
            file_size_kb=(int(a.get("size", 0) or 0)) // 1024 or None,
        ))

    return AnnouncementsResponse(
        asx_code=code,
        total=len(live_rows),
        data=live_rows,
        source="live",
    )


# ── AI Summary ────────────────────────────────────────────────

def _fmt_pct(v) -> str:
    if v is None: return "N/A"
    return f"{v * 100:.1f}%"

def _fmt_x(v) -> str:
    if v is None or v == 0: return "N/A"
    return f"{v:.1f}x"

def _fmt_price(v) -> str:
    if v is None: return "N/A"
    return f"${v:.3f}"

def _fmt_mcap(v) -> str:
    if v is None: return "N/A"
    if v >= 1_000_000: return f"${v/1_000_000:.2f}T"
    if v >= 1_000:     return f"${v/1_000:.1f}B"
    return f"${v:.0f}M"


@router.get("/{asx_code}/ai-summary")
async def get_ai_summary(
    asx_code: str,
    refresh: bool = Query(False, description="Force regenerate even if cached"),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns a Claude-generated AI analysis for the stock.
    Cached for 24 hours per ticker. Pass ?refresh=true to force regeneration.
    Requires ANTHROPIC_API_KEY to be configured.
    """
    code = asx_code.upper()

    # ── Check 24h cache ───────────────────────────────────────
    if not refresh:
        cached = await db.execute(text("""
            SELECT verdict, sentiment, bull_case, bear_case,
                   key_catalysts, key_risks, generated_at, model_used
            FROM market.ai_summaries
            WHERE asx_code = :code
              AND generated_at > NOW() - INTERVAL '24 hours'
        """), {"code": code})
        row = cached.mappings().first()
        if row:
            return {
                "asx_code":      code,
                "verdict":       row["verdict"],
                "sentiment":     row["sentiment"],
                "bull_case":     row["bull_case"],
                "bear_case":     row["bear_case"],
                "key_catalysts": row["key_catalysts"],
                "key_risks":     row["key_risks"],
                "generated_at":  row["generated_at"].isoformat(),
                "model_used":    row["model_used"],
                "cached":        True,
            }

    # ── Verify API key configured ─────────────────────────────
    if not settings.ANTHROPIC_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="AI Insights not configured. Add ANTHROPIC_API_KEY to server .env."
        )

    # ── Fetch screener data ───────────────────────────────────
    result = await db.execute(text("""
        SELECT u.company_name, c.gics_sector, c.gics_industry_group,
               u.price, u.market_cap,
               u.pe_ratio, u.forward_pe, u.price_to_book, u.ev_to_ebitda,
               u.dividend_yield, u.grossed_up_yield, u.franking_pct, u.dps_ttm, u.payout_ratio,
               u.revenue_growth_1y, u.earnings_growth_1y, u.revenue_growth_3y_cagr,
               u.gross_margin, u.ebitda_margin, u.net_margin, u.roe, u.roa,
               u.debt_to_equity, u.current_ratio, u.net_debt,
               u.piotroski_f_score, u.altman_z_score, u.short_pct,
               u.return_1w, u.return_1m, u.return_3m, u.return_1y, u.return_3y,
               u.rsi_14, u.sma_50, u.sma_200, u.composite_score,
               u.value_score, u.quality_score, u.growth_score,
               u.momentum_score, u.income_score,
               u.revenue_growth_hoh, u.net_income_growth_hoh
        FROM screener.universe u
        JOIN market.companies c ON c.asx_code = u.asx_code
        WHERE u.asx_code = :code
    """), {"code": code})
    d = result.mappings().first()

    if not d:
        raise HTTPException(status_code=404, detail="Screener data not found for this company")

    # ── Build prompt ──────────────────────────────────────────
    above_sma50  = d["price"] and d["sma_50"]  and d["price"] > d["sma_50"]
    above_sma200 = d["price"] and d["sma_200"] and d["price"] > d["sma_200"]

    prompt = f"""You are a senior Australian equities analyst. Analyse {code} ({d['company_name'] or 'N/A'}) \
using the financial data below and provide a concise, structured investment assessment.

COMPANY DATA:
Sector: {d['gics_sector'] or 'N/A'} | Industry: {d['gics_industry_group'] or 'N/A'}
Price: {_fmt_price(d['price'])} | Market Cap: {_fmt_mcap(d['market_cap'])}

VALUATION:
P/E: {_fmt_x(d['pe_ratio'])} | Fwd P/E: {_fmt_x(d['forward_pe'])} | P/B: {_fmt_x(d['price_to_book'])} | EV/EBITDA: {_fmt_x(d['ev_to_ebitda'])}

DIVIDENDS (ASX-SPECIFIC):
Yield: {_fmt_pct(d['dividend_yield'])} | Grossed-Up Yield: {_fmt_pct(d['grossed_up_yield'])} | Franking: {f"{d['franking_pct']:.0f}%" if d['franking_pct'] is not None else 'N/A'}
DPS: {_fmt_price(d['dps_ttm'])} | Payout Ratio: {_fmt_pct(d['payout_ratio'])}

GROWTH:
Revenue (1Y): {_fmt_pct(d['revenue_growth_1y'])} | Earnings (1Y): {_fmt_pct(d['earnings_growth_1y'])} | Revenue CAGR (3Y): {_fmt_pct(d['revenue_growth_3y_cagr'])}
Revenue HoH: {_fmt_pct(d['revenue_growth_hoh'])} | Net Income HoH: {_fmt_pct(d['net_income_growth_hoh'])}

PROFITABILITY:
Gross Margin: {_fmt_pct(d['gross_margin'])} | EBITDA Margin: {_fmt_pct(d['ebitda_margin'])} | Net Margin: {_fmt_pct(d['net_margin'])}
ROE: {_fmt_pct(d['roe'])} | ROA: {_fmt_pct(d['roa'])}

BALANCE SHEET:
D/E: {_fmt_x(d['debt_to_equity'])} | Current Ratio: {_fmt_x(d['current_ratio'])} | Net Debt: {_fmt_mcap(d['net_debt'])}

QUALITY & RISK:
Piotroski F-Score: {d['piotroski_f_score'] or 'N/A'}/9 | Altman Z: {f"{d['altman_z_score']:.2f}" if d['altman_z_score'] else 'N/A'} | Short Interest: {f"{d['short_pct']:.1f}%" if d['short_pct'] else 'N/A'}

TECHNICALS:
RSI(14): {f"{d['rsi_14']:.1f}" if d['rsi_14'] else 'N/A'} | Above 50MA: {'Yes' if above_sma50 else 'No'} | Above 200MA: {'Yes' if above_sma200 else 'No'}

RETURNS:
1W: {_fmt_pct(d['return_1w'])} | 1M: {_fmt_pct(d['return_1m'])} | 3M: {_fmt_pct(d['return_3m'])} | 1Y: {_fmt_pct(d['return_1y'])} | 3Y: {_fmt_pct(d['return_3y'])}

COMPOSITE SCORES (percentile vs all ASX):
Overall: {d['composite_score'] or 'N/A'}/100 | Value: {d['value_score'] or 'N/A'} | Quality: {d['quality_score'] or 'N/A'} | Growth: {d['growth_score'] or 'N/A'} | Momentum: {d['momentum_score'] or 'N/A'} | Income: {d['income_score'] or 'N/A'}

Respond ONLY with a valid JSON object — no markdown, no explanation, just the JSON:
{{
  "verdict": "One-sentence investment verdict, max 25 words",
  "sentiment": "bullish",
  "bull_case": ["bull point 1 (max 15 words)", "bull point 2", "bull point 3"],
  "bear_case": ["bear point 1 (max 15 words)", "bear point 2", "bear point 3"],
  "key_catalysts": ["catalyst 1 (max 12 words)", "catalyst 2"],
  "key_risks": ["risk 1 (max 12 words)", "risk 2"]
}}
sentiment must be exactly one of: bullish, bearish, neutral
Mention franking credits where they add meaningful value for Australian investors."""

    # ── Call Claude ───────────────────────────────────────────
    MODEL = "claude-haiku-4-5-20251001"
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        message = client.messages.create(
            model=MODEL,
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        summary = json.loads(raw)
    except json.JSONDecodeError as e:
        log.error(f"AI summary JSON parse error for {code}: {e}\nRaw: {raw[:200]}")
        raise HTTPException(status_code=502, detail="AI response could not be parsed")
    except Exception as e:
        log.error(f"AI summary generation failed for {code}: {e}")
        raise HTTPException(status_code=502, detail=f"AI generation failed: {str(e)}")

    # Validate fields
    sentiment = summary.get("sentiment", "neutral")
    if sentiment not in ("bullish", "bearish", "neutral"):
        sentiment = "neutral"

    bull_case      = summary.get("bull_case",      [])[:5]
    bear_case      = summary.get("bear_case",      [])[:5]
    key_catalysts  = summary.get("key_catalysts",  [])[:4]
    key_risks      = summary.get("key_risks",      [])[:4]
    verdict        = summary.get("verdict", "")[:300]

    # ── Cache in DB (upsert) ──────────────────────────────────
    try:
        await db.execute(text("""
            INSERT INTO market.ai_summaries
                (asx_code, verdict, sentiment, bull_case, bear_case, key_catalysts, key_risks, model_used, generated_at)
            VALUES
                (:code, :verdict, :sentiment, :bull_case::jsonb, :bear_case::jsonb,
                 :catalysts::jsonb, :risks::jsonb, :model, NOW())
            ON CONFLICT (asx_code) DO UPDATE SET
                verdict       = EXCLUDED.verdict,
                sentiment     = EXCLUDED.sentiment,
                bull_case     = EXCLUDED.bull_case,
                bear_case     = EXCLUDED.bear_case,
                key_catalysts = EXCLUDED.key_catalysts,
                key_risks     = EXCLUDED.key_risks,
                model_used    = EXCLUDED.model_used,
                generated_at  = NOW()
        """), {
            "code":      code,
            "verdict":   verdict,
            "sentiment": sentiment,
            "bull_case": json.dumps(bull_case),
            "bear_case": json.dumps(bear_case),
            "catalysts": json.dumps(key_catalysts),
            "risks":     json.dumps(key_risks),
            "model":     MODEL,
        })
        await db.commit()
    except Exception as e:
        log.warning(f"AI summary cache write failed for {code}: {e}")
        await db.rollback()

    from datetime import datetime, timezone
    return {
        "asx_code":      code,
        "verdict":       verdict,
        "sentiment":     sentiment,
        "bull_case":     bull_case,
        "bear_case":     bear_case,
        "key_catalysts": key_catalysts,
        "key_risks":     key_risks,
        "generated_at":  datetime.now(timezone.utc).isoformat(),
        "model_used":    MODEL,
        "cached":        False,
    }
