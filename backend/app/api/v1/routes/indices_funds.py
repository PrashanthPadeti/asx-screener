"""
Indices and ETF/Managed Funds endpoints.
Reads from market.indices, market.index_prices, market.funds, market.fund_prices.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.db.session import get_db
from app.schemas.indices_funds import IndicesResponse, IndexPrice, FundsResponse, FundRow

router = APIRouter()


# ── Indices ───────────────────────────────────────────────────────────────────

@router.get("/indices", response_model=IndicesResponse)
async def get_indices(db: AsyncSession = Depends(get_db)):
    """
    Latest daily performance for all active ASX indices.
    Falls back to empty list if index_prices table has no data yet.
    """
    # Latest date that has benchmark index data (ASX200 as canonical)
    date_row = (await db.execute(text(
        "SELECT MAX(price_date) AS latest FROM market.index_prices WHERE index_code = 'ASX200'"
    ))).mappings().fetchone()
    as_of = date_row["latest"] if date_row and date_row["latest"] else None

    if as_of is None:
        # Fallback: any date in the table
        date_row2 = (await db.execute(text(
            "SELECT MAX(price_date) AS latest FROM market.index_prices"
        ))).mappings().fetchone()
        as_of = date_row2["latest"] if date_row2 and date_row2["latest"] else None

    if as_of is None:
        # No data yet — return metadata only, no price info
        meta_rows = (await db.execute(text(
            "SELECT index_code, display_name, description, constituent_count, rebalance_freq "
            "FROM market.indices WHERE is_active = TRUE ORDER BY index_code"
        ))).mappings().all()
        return IndicesResponse(
            indices=[
                IndexPrice(
                    index_code=r["index_code"],
                    display_name=r["display_name"],
                )
                for r in meta_rows
            ],
            as_of=None,
        )

    rows = (await db.execute(text("""
        SELECT
            i.index_code,
            i.display_name,
            p.price_date::text     AS price_date,
            p.close_price,
            p.return_1d,
            p.return_1w,
            p.return_1m,
            p.return_3m,
            p.return_6m,
            p.return_1y,
            p.return_ytd,
            p.high_52w,
            p.low_52w
        FROM market.indices i
        LEFT JOIN LATERAL (
            SELECT * FROM market.index_prices
            WHERE index_code = i.index_code
            ORDER BY price_date DESC
            LIMIT 1
        ) p ON TRUE
        WHERE i.is_active = TRUE
        ORDER BY
            CASE i.index_code
                WHEN 'ASX200' THEN 1
                WHEN 'ASX300' THEN 2
                WHEN 'ASX100' THEN 3
                WHEN 'ASX50'  THEN 4
                WHEN 'ASX20'  THEN 5
                WHEN 'AXJO'   THEN 6
                ELSE 99
            END
    """))).mappings().all()

    def _f(v): return float(v) if v is not None else None

    return IndicesResponse(
        indices=[
            IndexPrice(
                index_code=r["index_code"],
                display_name=r["display_name"],
                price_date=r["price_date"],
                close_price=_f(r["close_price"]),
                return_1d=_f(r["return_1d"]),
                return_1w=_f(r["return_1w"]),
                return_1m=_f(r["return_1m"]),
                return_3m=_f(r["return_3m"]),
                return_6m=_f(r["return_6m"]),
                return_1y=_f(r["return_1y"]),
                return_ytd=_f(r["return_ytd"]),
                high_52w=_f(r["high_52w"]),
                low_52w=_f(r["low_52w"]),
            )
            for r in rows
        ],
        as_of=as_of.isoformat() if as_of else None,
    )


@router.get("/indices/{index_code}/history")
async def get_index_history(
    index_code: str,
    days: int = Query(365, ge=30, le=1825),
    db: AsyncSession = Depends(get_db),
):
    """
    Historical daily close prices for a specific index (up to 5 years).
    Returns a list of {date, close_price, return_1d} ordered ascending.
    """
    rows = (await db.execute(text("""
        SELECT price_date::text AS price_date, close_price, return_1d
        FROM market.index_prices
        WHERE index_code = :code
          AND price_date >= CURRENT_DATE - :days * INTERVAL '1 day'
        ORDER BY price_date ASC
    """), {"code": index_code.upper(), "days": days})).mappings().all()

    def _f(v): return float(v) if v is not None else None

    return {
        "index_code": index_code.upper(),
        "history": [
            {
                "date": r["price_date"],
                "close": _f(r["close_price"]),
                "return_1d": _f(r["return_1d"]),
            }
            for r in rows
        ],
    }


# ── ETF / Managed Funds ───────────────────────────────────────────────────────

@router.get("/funds", response_model=FundsResponse)
async def get_funds(
    fund_type: str = Query(None, pattern="^(ETF|LIC|MANAGED)$"),
    asset_class: str = Query(None),
    sort: str = Query("funds_under_mgmt_bn", pattern="^(funds_under_mgmt_bn|return_1y|return_ytd|distribution_yield|mer_pct)$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    limit: int = Query(50, ge=5, le=200),
    db: AsyncSession = Depends(get_db),
):
    """
    ETF and managed fund list with latest price data.
    Optional filters: fund_type, asset_class.
    """
    date_row = (await db.execute(text(
        "SELECT MAX(price_date) AS latest FROM market.fund_prices"
    ))).mappings().fetchone()
    as_of = date_row["latest"] if date_row else None

    where_clauses = ["f.is_active = TRUE"]
    params: dict = {"lim": limit}

    if fund_type:
        where_clauses.append("f.fund_type = :fund_type")
        params["fund_type"] = fund_type
    if asset_class:
        where_clauses.append("f.asset_class ILIKE :asset_class")
        params["asset_class"] = f"%{asset_class}%"

    where_sql = " AND ".join(where_clauses)
    order_dir = "DESC" if order == "desc" else "ASC"

    price_join = ""
    price_cols = ""
    if as_of:
        params["d"] = as_of
        price_join = "LEFT JOIN market.fund_prices p ON p.asx_code = f.asx_code AND p.price_date = :d"
        price_cols = """,
            p.price_date::text     AS price_date,
            p.close_price,
            p.return_1d,
            p.return_1w,
            p.return_1m,
            p.return_1y,
            p.return_ytd,
            p.distribution_yield,
            p.nav_discount_pct,
            p.high_52w,
            p.low_52w"""

    sort_expr = f"p.{sort}" if as_of and sort not in ("mer_pct", "funds_under_mgmt_bn") else f"f.{sort}"

    sql = f"""
        SELECT
            f.asx_code, f.fund_name, f.fund_type, f.asset_class,
            f.index_tracked, f.fund_manager, f.mer_pct,
            f.funds_under_mgmt_bn, f.distribution_freq, f.is_hedged
            {price_cols}
        FROM market.funds f
        {price_join}
        WHERE {where_sql}
        ORDER BY {sort_expr} {order_dir} NULLS LAST
        LIMIT :lim
    """

    rows = (await db.execute(text(sql), params)).mappings().all()

    def _f(v): return float(v) if v is not None else None
    def _b(v): return bool(v) if v is not None else None

    fund_list = [
        FundRow(
            asx_code=r["asx_code"],
            fund_name=r["fund_name"],
            fund_type=r["fund_type"],
            asset_class=r.get("asset_class"),
            index_tracked=r.get("index_tracked"),
            fund_manager=r.get("fund_manager"),
            mer_pct=_f(r.get("mer_pct")),
            funds_under_mgmt_bn=_f(r.get("funds_under_mgmt_bn")),
            distribution_freq=r.get("distribution_freq"),
            is_hedged=_b(r.get("is_hedged")),
            close_price=_f(r.get("close_price")),
            return_1d=_f(r.get("return_1d")),
            return_1w=_f(r.get("return_1w")),
            return_1m=_f(r.get("return_1m")),
            return_1y=_f(r.get("return_1y")),
            return_ytd=_f(r.get("return_ytd")),
            distribution_yield=_f(r.get("distribution_yield")),
            nav_discount_pct=_f(r.get("nav_discount_pct")),
            high_52w=_f(r.get("high_52w")),
            low_52w=_f(r.get("low_52w")),
            price_date=r.get("price_date"),
        )
        for r in rows
    ]

    return FundsResponse(
        funds=fund_list,
        total=len(fund_list),
        as_of=as_of.isoformat() if as_of else None,
    )


@router.get("/funds/{asx_code}")
async def get_fund_detail(asx_code: str, db: AsyncSession = Depends(get_db)):
    """
    Fund metadata + last 12 months of daily price history.
    """
    meta = (await db.execute(text("""
        SELECT asx_code, fund_name, fund_type, asset_class, index_tracked,
               fund_manager, mer_pct, funds_under_mgmt_bn,
               distribution_freq, is_hedged, inception_date::text AS inception_date, asx_url
        FROM market.funds
        WHERE asx_code = :code AND is_active = TRUE
    """), {"code": asx_code.upper()})).mappings().fetchone()

    if not meta:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Fund {asx_code.upper()} not found")

    hist = (await db.execute(text("""
        SELECT price_date::text AS price_date, close_price, return_1d,
               distribution_yield, nav_discount_pct
        FROM market.fund_prices
        WHERE asx_code = :code
          AND price_date >= CURRENT_DATE - INTERVAL '365 days'
        ORDER BY price_date ASC
    """), {"code": asx_code.upper()})).mappings().all()

    def _f(v): return float(v) if v is not None else None

    return {
        "asx_code": meta["asx_code"],
        "fund_name": meta["fund_name"],
        "fund_type": meta["fund_type"],
        "asset_class": meta["asset_class"],
        "index_tracked": meta["index_tracked"],
        "fund_manager": meta["fund_manager"],
        "mer_pct": _f(meta["mer_pct"]),
        "funds_under_mgmt_bn": _f(meta["funds_under_mgmt_bn"]),
        "distribution_freq": meta["distribution_freq"],
        "is_hedged": meta["is_hedged"],
        "inception_date": meta["inception_date"],
        "asx_url": meta["asx_url"],
        "history": [
            {
                "date": r["price_date"],
                "close": _f(r["close_price"]),
                "return_1d": _f(r["return_1d"]),
                "distribution_yield": _f(r["distribution_yield"]),
                "nav_discount_pct": _f(r["nav_discount_pct"]),
            }
            for r in hist
        ],
    }
