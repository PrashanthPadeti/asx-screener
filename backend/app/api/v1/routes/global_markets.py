"""
Global Markets endpoints.
Reads from market.global_indices, market.global_index_prices, market.fx_rates.
"""
from collections import defaultdict
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.db.session import get_db

router = APIRouter()

# FX pair display metadata (kept here to avoid a DB round-trip)
_FX_NAMES = {
    "AUDUSD": "AUD/USD",
    "AUDEUR": "AUD/EUR",
    "AUDGBP": "AUD/GBP",
    "AUDJPY": "AUD/JPY",
    "AUDCNY": "AUD/CNY",
}

_REGION_ORDER = ["US", "Europe", "Asia"]


@router.get("/")
async def get_global_markets(db: AsyncSession = Depends(get_db)):
    """
    Latest global index prices grouped by region, plus latest AUD FX rates.
    Returns empty lists if no data has been ingested yet.
    """
    def _f(v):
        return float(v) if v is not None else None

    # Latest price row per index via LATERAL join
    idx_rows = (await db.execute(text("""
        SELECT
            gi.index_code, gi.index_name, gi.region, gi.country, gi.currency,
            p.price_date::text  AS price_date,
            p.close_price, p.open_price, p.high_price, p.low_price,
            p.return_1d, p.return_1w, p.return_1m,
            p.return_3m, p.return_6m, p.return_1y, p.return_ytd,
            p.high_52w, p.low_52w
        FROM market.global_indices gi
        LEFT JOIN LATERAL (
            SELECT * FROM market.global_index_prices
            WHERE index_code = gi.index_code
            ORDER BY price_date DESC LIMIT 1
        ) p ON TRUE
        WHERE gi.is_active = TRUE
        ORDER BY gi.region, gi.index_code
    """))).mappings().all()

    # Latest FX rate per pair
    fx_rows = (await db.execute(text("""
        SELECT fx_pair, rate_date::text AS rate_date,
               rate, open_rate, high_rate, low_rate,
               return_1d, return_1w, return_1m, return_ytd
        FROM market.fx_rates
        WHERE (fx_pair, rate_date) IN (
            SELECT fx_pair, MAX(rate_date)
            FROM market.fx_rates
            GROUP BY fx_pair
        )
        ORDER BY fx_pair
    """))).mappings().all()

    # Determine as_of from the most recent index price
    as_of = None
    for r in idx_rows:
        if r["price_date"]:
            as_of = r["price_date"]
            break

    # Group indices by region in display order
    regions_map: dict[str, list] = defaultdict(list)
    for r in idx_rows:
        regions_map[r["region"]].append({
            "index_code":  r["index_code"],
            "index_name":  r["index_name"],
            "region":      r["region"],
            "country":     r["country"],
            "currency":    r["currency"],
            "price_date":  r["price_date"],
            "close_price": _f(r["close_price"]),
            "open_price":  _f(r["open_price"]),
            "high_price":  _f(r["high_price"]),
            "low_price":   _f(r["low_price"]),
            "return_1d":   _f(r["return_1d"]),
            "return_1w":   _f(r["return_1w"]),
            "return_1m":   _f(r["return_1m"]),
            "return_3m":   _f(r["return_3m"]),
            "return_6m":   _f(r["return_6m"]),
            "return_1y":   _f(r["return_1y"]),
            "return_ytd":  _f(r["return_ytd"]),
            "high_52w":    _f(r["high_52w"]),
            "low_52w":     _f(r["low_52w"]),
        })

    regions = [
        {"region": region, "indices": regions_map[region]}
        for region in _REGION_ORDER
        if region in regions_map
    ]

    fx_rates = [
        {
            "fx_pair":    r["fx_pair"],
            "name":       _FX_NAMES.get(r["fx_pair"], r["fx_pair"]),
            "rate_date":  r["rate_date"],
            "rate":       _f(r["rate"]),
            "open_rate":  _f(r["open_rate"]),
            "high_rate":  _f(r["high_rate"]),
            "low_rate":   _f(r["low_rate"]),
            "return_1d":  _f(r["return_1d"]),
            "return_1w":  _f(r["return_1w"]),
            "return_1m":  _f(r["return_1m"]),
            "return_ytd": _f(r["return_ytd"]),
        }
        for r in fx_rows
    ]

    return {
        "as_of":    as_of,
        "regions":  regions,
        "fx_rates": fx_rates,
    }
