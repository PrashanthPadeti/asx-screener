"""
Commodities endpoints.
Reads from market.commodity_prices — latest price per commodity, grouped by category.
"""
from collections import defaultdict
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.db.session import get_db

router = APIRouter()

_CATEGORY_ORDER = ["Precious Metals", "Base Metals", "Energy", "Bulk"]


@router.get("/")
async def get_commodities(db: AsyncSession = Depends(get_db)):
    """
    Latest commodity prices grouped by category.
    Returns empty list if no data has been ingested yet.
    """
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

    return {
        "as_of":      as_of,
        "categories": categories,
    }
