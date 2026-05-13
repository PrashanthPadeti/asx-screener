"""
Commodities endpoints.
Reads from market.commodity_prices — latest price per commodity, grouped by category.
"""
from collections import defaultdict
from datetime import date, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.db.session import get_db
from app.core.cache import cache_get, cache_set, make_key, STATIC_TTL

router = APIRouter()

_CATEGORY_ORDER = ["Precious Metals", "Base Metals", "Energy", "Bulk"]


@router.get("/")
async def get_commodities(db: AsyncSession = Depends(get_db)):
    """
    Latest commodity prices grouped by category.
    Returns empty list if no data has been ingested yet.
    """
    _key = make_key("commodities", "latest")
    cached = await cache_get(_key)
    if cached:
        return cached

    def _f(v):
        return float(v) if v is not None else None

    rows = (await db.execute(text("""
        SELECT DISTINCT ON (commodity_code)
            commodity_code, commodity_name, category, unit,
            price_date::text AS price_date,
            close_price, open_price, high_price, low_price,
            return_1d, return_1w, return_1m, return_3m,
            return_6m, return_1y, return_ytd,
            high_52w, low_52w
        FROM market.commodity_prices
        ORDER BY commodity_code, price_date DESC
    """))).mappings().all()

    as_of = None
    if rows:
        as_of = rows[0]["price_date"]

    groups: dict[str, list] = defaultdict(list)
    for r in rows:
        groups[r["category"]].append({
            "commodity_code": r["commodity_code"],
            "commodity_name": r["commodity_name"],
            "category":       r["category"],
            "unit":           r["unit"],
            "price_date":     r["price_date"],
            "close_price":    _f(r["close_price"]),
            "open_price":     _f(r["open_price"]),
            "high_price":     _f(r["high_price"]),
            "low_price":      _f(r["low_price"]),
            "return_1d":      _f(r["return_1d"]),
            "return_1w":      _f(r["return_1w"]),
            "return_1m":      _f(r["return_1m"]),
            "return_3m":      _f(r["return_3m"]),
            "return_6m":      _f(r["return_6m"]),
            "return_1y":      _f(r["return_1y"]),
            "return_ytd":     _f(r["return_ytd"]),
            "high_52w":       _f(r["high_52w"]),
            "low_52w":        _f(r["low_52w"]),
        })

    categories = [
        {"category": cat, "commodities": groups[cat]}
        for cat in _CATEGORY_ORDER
        if cat in groups
    ]

    result = {
        "as_of":      as_of,
        "categories": categories,
    }
    await cache_set(_key, result, ttl=STATIC_TTL)
    return result


@router.get("/{commodity_code}")
async def get_commodity_detail(
    commodity_code: str,
    days: int = Query(365, ge=30, le=1825),
    db: AsyncSession = Depends(get_db),
):
    """Detail + price history for a single commodity."""
    def _f(v):
        return float(v) if v is not None else None

    commodity_code = commodity_code.upper()

    # Latest row (includes name/category/unit embedded in table)
    latest = (await db.execute(text("""
        SELECT DISTINCT ON (commodity_code)
            commodity_code, commodity_name, category, unit,
            price_date::text, close_price, open_price, high_price, low_price,
            return_1d, return_1w, return_1m, return_3m,
            return_6m, return_1y, return_ytd, high_52w, low_52w
        FROM market.commodity_prices
        WHERE commodity_code = :code
        ORDER BY commodity_code, price_date DESC
    """), {"code": commodity_code})).mappings().first()

    if not latest:
        raise HTTPException(status_code=404, detail=f"Commodity {commodity_code!r} not found")

    # Price history
    start = date.today() - timedelta(days=days)
    hist_rows = (await db.execute(text("""
        SELECT price_date::text AS price_date, close_price
        FROM market.commodity_prices
        WHERE commodity_code = :code AND price_date >= :start
        ORDER BY price_date ASC
    """), {"code": commodity_code, "start": start})).mappings().all()

    return {
        "commodity_code": latest["commodity_code"],
        "commodity_name": latest["commodity_name"],
        "category":       latest["category"],
        "unit":           latest["unit"],
        "price_date":     latest["price_date"],
        "close_price":    _f(latest["close_price"]),
        "open_price":     _f(latest["open_price"]),
        "high_price":     _f(latest["high_price"]),
        "low_price":      _f(latest["low_price"]),
        "return_1d":      _f(latest["return_1d"]),
        "return_1w":      _f(latest["return_1w"]),
        "return_1m":      _f(latest["return_1m"]),
        "return_3m":      _f(latest["return_3m"]),
        "return_6m":      _f(latest["return_6m"]),
        "return_1y":      _f(latest["return_1y"]),
        "return_ytd":     _f(latest["return_ytd"]),
        "high_52w":       _f(latest["high_52w"]),
        "low_52w":        _f(latest["low_52w"]),
        "history": [
            {"date": r["price_date"], "close": _f(r["close_price"])}
            for r in hist_rows
        ],
    }
