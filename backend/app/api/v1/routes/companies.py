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
    CompanySearchResult, CompanyListResponse,
    CompanyOverview, AnnualFinancialsRow, FinancialsResponse,
    PricePoint, PricesResponse,
    DividendRecord, DividendsSummary, DividendsResponse,
    PeerStock, PeersResponse,
    HalfYearlyRow, HalfYearlyResponse,
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
            short_pct, percent_insiders, percent_institutions,
            analyst_rating, analyst_target_price, analyst_upside,
            return_1w, return_1m, return_3m, return_6m, return_1y, return_ytd,
            return_3y, return_5y, drawdown_from_ath,
            rsi_14, adx_14, macd, macd_signal,
            sma_20, sma_50, sma_200, ema_20,
            bb_upper, bb_lower, atr_14, obv,
            volatility_20d, volatility_60d, beta_1y, sharpe_1y,
            momentum_3m, momentum_6m
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
    sql = """
        SELECT
            period_label,
            period_end_date,
            (revenue / 1000000)::double precision           AS revenue,
            (gross_profit / 1000000)::double precision      AS gross_profit,
            (ebitda / 1000000)::double precision            AS ebitda,
            (ebit / 1000000)::double precision              AS ebit,
            (net_profit / 1000000)::double precision        AS net_profit,
            eps::double precision,
            dps::double precision,
            dps_franking_pct::double precision,
            gpm::double precision,
            opm::double precision               AS ebitda_margin,
            npm::double precision
        FROM financials.half_year_pnl
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
