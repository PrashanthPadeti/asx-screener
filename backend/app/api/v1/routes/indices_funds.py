"""
Indices and ETF/Managed Funds endpoints.
Reads from market.indices, market.index_prices, market.funds, market.fund_prices.
"""
from collections import defaultdict
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.db.session import get_db
from app.schemas.indices_funds import (
    IndicesResponse, IndexPrice,
    FundsResponse, FundRow,
    IndexConstituentRow, IndexSectorBreakdown, IndexPrimaryETF, IndexDetailResponse,
)

router = APIRouter()

# ── Index hardcoded metadata ──────────────────────────────────────────────────

INDEX_META: dict[str, dict] = {
    "ASX20": {
        "display_name": "S&P/ASX 20",
        "description": (
            "The S&P/ASX 20 measures the performance of Australia's 20 largest companies "
            "by float-adjusted market capitalisation. It represents the blue-chip tier of "
            "the Australian equity market and is dominated by the major banks, miners, "
            "and diversified financial groups."
        ),
        "eligibility": (
            "Must be a constituent of the S&P/ASX 50. Ranked by float-adjusted market "
            "capitalisation. Must meet liquidity and public float requirements set by "
            "S&P Dow Jones Indices and reviewed quarterly."
        ),
        "methodology": (
            "Float-adjusted market capitalisation weighted. Individual stock weight capped "
            "at index rebalance. Reviewed and rebalanced quarterly by S&P Dow Jones Indices."
        ),
        "rebalance_freq": "Quarterly",
        "primary_etf": "ILC",
        "primary_etf_name": "iShares S&P/ASX 20 ETF",
        "primary_etf_mer": 0.0024,
        "market_coverage": "Top 20 companies — approximately 50% of ASX total market capitalisation",
    },
    "ASX50": {
        "display_name": "S&P/ASX 50",
        "description": (
            "Tracks the 50 largest ASX-listed companies by float-adjusted market "
            "capitalisation. A broad large-cap benchmark often used by institutional "
            "investors seeking exposure to Australia's leading companies across all sectors."
        ),
        "eligibility": (
            "Must be in the S&P/ASX 100. Ranked by float-adjusted market capitalisation. "
            "Companies must meet minimum float and liquidity thresholds as defined by "
            "S&P Dow Jones Indices."
        ),
        "methodology": "Float-adjusted market capitalisation weighted, quarterly rebalance.",
        "rebalance_freq": "Quarterly",
        "primary_etf": "SFY",
        "primary_etf_name": "SPDR S&P/ASX 50 Fund",
        "primary_etf_mer": 0.0029,
        "market_coverage": "Top 50 companies — approximately 65% of ASX total market capitalisation",
    },
    "ASX100": {
        "display_name": "S&P/ASX 100",
        "description": (
            "Covers the 100 largest ASX-listed companies. Widely used as a mid-to-large "
            "cap benchmark and the investable universe for many active Australian equity "
            "managers. Provides significantly broader exposure than the ASX 50."
        ),
        "eligibility": (
            "Must be a constituent of the S&P/ASX 200. Ranked by float-adjusted market "
            "capitalisation within the top 100. Quarterly review by S&P Dow Jones Indices."
        ),
        "methodology": "Float-adjusted market capitalisation weighted, quarterly rebalance.",
        "rebalance_freq": "Quarterly",
        "primary_etf": "IOO",
        "primary_etf_name": "iShares S&P/ASX 100 ETF",
        "primary_etf_mer": 0.0024,
        "market_coverage": "Top 100 companies — approximately 80% of ASX total market capitalisation",
    },
    "ASX200": {
        "display_name": "S&P/ASX 200",
        "description": (
            "Australia's primary institutional investable benchmark. Covers approximately "
            "200 large and mid-cap companies representing roughly 80% of Australian equity "
            "market capitalisation. Widely used as the performance benchmark for Australian "
            "equity funds and the basis for most index products."
        ),
        "eligibility": (
            "Australian-domiciled companies listed on the ASX meeting float-adjusted market "
            "capitalisation and annual traded value thresholds set by S&P Dow Jones Indices. "
            "Constituents must meet minimum float (≥30%) and liquidity requirements. "
            "Reviewed and rebalanced quarterly in March, June, September, and December."
        ),
        "methodology": (
            "Float-adjusted market capitalisation weighted. No individual stock weight cap "
            "for standard index. Rebalanced quarterly. Total return variant (AXJO) includes "
            "reinvested dividends."
        ),
        "rebalance_freq": "Quarterly",
        "primary_etf": "STW",
        "primary_etf_name": "SPDR S&P/ASX 200 Fund",
        "primary_etf_mer": 0.0013,
        "market_coverage": "~200 companies — approximately 80% of ASX total market capitalisation",
    },
    "ASX300": {
        "display_name": "S&P/ASX 300",
        "description": (
            "Extends the ASX 200 to include the next 100 smaller companies, providing "
            "exposure to Australia's small and mid-cap segment. Used by managers seeking "
            "broader Australian equity exposure beyond the large-cap universe."
        ),
        "eligibility": (
            "Australian-domiciled companies meeting S&P Dow Jones float-adjusted market "
            "capitalisation and liquidity thresholds, ranked within the top 300. "
            "The additional ~100 constituents beyond the ASX 200 are typically smaller, "
            "less liquid companies. Reviewed quarterly."
        ),
        "methodology": "Float-adjusted market capitalisation weighted, quarterly rebalance.",
        "rebalance_freq": "Quarterly",
        "primary_etf": "VAS",
        "primary_etf_name": "Vanguard Australian Shares ETF",
        "primary_etf_mer": 0.0007,
        "market_coverage": "~300 companies — approximately 85% of ASX total market capitalisation",
    },
    "AXJO": {
        "display_name": "S&P/ASX 200 Accumulation",
        "description": (
            "The total return version of the S&P/ASX 200 index, incorporating reinvestment "
            "of dividends. Provides a more accurate measure of total investor return than "
            "the price-only ASX 200. This is the standard benchmark used by Australian "
            "superannuation funds and managed equity funds."
        ),
        "eligibility": "Identical constituents to the S&P/ASX 200 index.",
        "methodology": (
            "Float-adjusted market capitalisation weighted with gross dividends reinvested "
            "on ex-dividend date. Used as the standard performance benchmark for Australian "
            "equity funds, as it captures the full return including the franking-enhanced "
            "dividend income that characterises Australian equities."
        ),
        "rebalance_freq": "Quarterly",
        "primary_etf": "STW",
        "primary_etf_name": "SPDR S&P/ASX 200 Fund",
        "primary_etf_mer": 0.0013,
        "market_coverage": "Same universe as ASX 200 — total return (accumulation) basis",
    },
    "AXFJ": {
        "display_name": "S&P/ASX 200 Financials",
        "description": (
            "Measures the performance of ASX 200 companies classified in the GICS Financials "
            "sector. Includes the major banks (CBA, NAB, ANZ, WBC), diversified financial "
            "companies, insurance groups (QBE, IAG, SUN), REITs, and investment platforms. "
            "The largest sector within the ASX 200 by market capitalisation."
        ),
        "eligibility": (
            "Must be a constituent of the S&P/ASX 200 and classified in GICS Sector 40 "
            "(Financials) by S&P Dow Jones Indices. GICS classification is reviewed annually."
        ),
        "methodology": "Float-adjusted market capitalisation weighted within the Financials sector.",
        "rebalance_freq": "Quarterly",
        "primary_etf": "OZF",
        "primary_etf_name": "BetaShares S&P/ASX 200 Financials Sector ETF",
        "primary_etf_mer": 0.0034,
        "market_coverage": "ASX 200 Financials sector — approximately 28–32% of ASX 200 by weight",
    },
    "AXMJ": {
        "display_name": "S&P/ASX 200 Materials",
        "description": (
            "Tracks ASX 200 companies in the GICS Materials sector, covering diversified "
            "miners (BHP, RIO, South32), gold miners (Newmont, Evolution), steel producers, "
            "chemicals, and packaging companies. Australia's largest and most globally "
            "significant sector, driven by commodity price cycles."
        ),
        "eligibility": (
            "Must be a constituent of the S&P/ASX 200 and classified in GICS Sector 15 "
            "(Materials) by S&P Dow Jones Indices."
        ),
        "methodology": "Float-adjusted market capitalisation weighted within the Materials sector.",
        "rebalance_freq": "Quarterly",
        "primary_etf": "OZR",
        "primary_etf_name": "BetaShares S&P/ASX 200 Resources Sector ETF",
        "primary_etf_mer": 0.0034,
        "market_coverage": "ASX 200 Materials sector — approximately 18–22% of ASX 200 by weight",
    },
    "AXEJ": {
        "display_name": "S&P/ASX 200 Energy",
        "description": (
            "Measures performance of ASX 200 companies in the GICS Energy sector, including "
            "oil and gas producers (Woodside, Santos, Beach Energy), LNG projects, and energy "
            "equipment and services companies. A relatively small but highly cyclical sector "
            "sensitive to global oil and gas prices."
        ),
        "eligibility": (
            "Must be a constituent of the S&P/ASX 200 and classified in GICS Sector 10 "
            "(Energy) by S&P Dow Jones Indices."
        ),
        "methodology": "Float-adjusted market capitalisation weighted within the Energy sector.",
        "rebalance_freq": "Quarterly",
        "primary_etf": None,
        "primary_etf_name": None,
        "primary_etf_mer": None,
        "market_coverage": "ASX 200 Energy sector — approximately 3–6% of ASX 200 by weight",
    },
    "AXHJ": {
        "display_name": "S&P/ASX 200 Health Care",
        "description": (
            "Tracks ASX 200 companies classified in the GICS Health Care sector. Dominated "
            "by CSL Limited (plasma therapies and vaccines), complemented by Cochlear "
            "(hearing implants), Resmed (sleep apnea devices), Sonic Healthcare (pathology), "
            "and a range of biotech, pharmaceutical, and aged care companies."
        ),
        "eligibility": (
            "Must be a constituent of the S&P/ASX 200 and classified in GICS Sector 35 "
            "(Health Care) by S&P Dow Jones Indices."
        ),
        "methodology": "Float-adjusted market capitalisation weighted within the Health Care sector.",
        "rebalance_freq": "Quarterly",
        "primary_etf": "OZH",
        "primary_etf_name": "BetaShares S&P/ASX 200 Health Care Sector ETF",
        "primary_etf_mer": 0.0034,
        "market_coverage": "ASX 200 Health Care sector — approximately 9–12% of ASX 200 by weight",
    },
}

# Map index_code → screener.universe boolean flag
INDEX_UNIVERSE_FLAG: dict[str, str | None] = {
    "ASX20":  "is_asx20",
    "ASX50":  "is_asx50",
    "ASX100": "is_asx100",
    "ASX200": "is_asx200",
    "ASX300": "is_asx300",
    "AXJO":   "is_asx200",  # accumulation index, same constituents as ASX200
    "AXFJ":   None,
    "AXMJ":   None,
    "AXEJ":   None,
    "AXHJ":   None,
}

# Sector names used in screener.universe for sector indices
INDEX_GICS_SECTOR: dict[str, str] = {
    "AXFJ": "Financials",
    "AXMJ": "Materials",
    "AXEJ": "Energy",
    "AXHJ": "Health Care",
}


# ── Indices list ──────────────────────────────────────────────────────────────

@router.get("/indices", response_model=IndicesResponse)
async def get_indices(db: AsyncSession = Depends(get_db)):
    """Latest daily performance for all active ASX indices."""
    date_row = (await db.execute(text(
        "SELECT MAX(price_date) AS latest FROM market.index_prices WHERE index_code = 'ASX200'"
    ))).mappings().fetchone()
    as_of = date_row["latest"] if date_row and date_row["latest"] else None

    if as_of is None:
        date_row2 = (await db.execute(text(
            "SELECT MAX(price_date) AS latest FROM market.index_prices"
        ))).mappings().fetchone()
        as_of = date_row2["latest"] if date_row2 and date_row2["latest"] else None

    if as_of is None:
        meta_rows = (await db.execute(text(
            "SELECT index_code, display_name FROM market.indices WHERE is_active = TRUE ORDER BY index_code"
        ))).mappings().all()
        return IndicesResponse(
            indices=[IndexPrice(index_code=r["index_code"], display_name=r["display_name"]) for r in meta_rows],
            as_of=None,
        )

    rows = (await db.execute(text("""
        SELECT
            i.index_code, i.display_name,
            p.price_date::text AS price_date,
            p.close_price, p.return_1d, p.return_1w, p.return_1m,
            p.return_3m, p.return_6m, p.return_1y, p.return_ytd,
            p.high_52w, p.low_52w
        FROM market.indices i
        LEFT JOIN LATERAL (
            SELECT * FROM market.index_prices
            WHERE index_code = i.index_code
            ORDER BY price_date DESC LIMIT 1
        ) p ON TRUE
        WHERE i.is_active = TRUE
        ORDER BY
            CASE i.index_code
                WHEN 'ASX200' THEN 1 WHEN 'ASX300' THEN 2 WHEN 'ASX100' THEN 3
                WHEN 'ASX50'  THEN 4 WHEN 'ASX20'  THEN 5 WHEN 'AXJO'   THEN 6
                ELSE 99
            END
    """))).mappings().all()

    def _f(v): return float(v) if v is not None else None

    return IndicesResponse(
        indices=[
            IndexPrice(
                index_code=r["index_code"], display_name=r["display_name"],
                price_date=r["price_date"], close_price=_f(r["close_price"]),
                return_1d=_f(r["return_1d"]), return_1w=_f(r["return_1w"]),
                return_1m=_f(r["return_1m"]), return_3m=_f(r["return_3m"]),
                return_6m=_f(r["return_6m"]), return_1y=_f(r["return_1y"]),
                return_ytd=_f(r["return_ytd"]), high_52w=_f(r["high_52w"]),
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
    """Historical daily close prices for a specific index (up to 5 years)."""
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
            {"date": r["price_date"], "close": _f(r["close_price"]), "return_1d": _f(r["return_1d"])}
            for r in rows
        ],
    }


@router.get("/indices/{index_code}", response_model=IndexDetailResponse)
async def get_index_detail(index_code: str, db: AsyncSession = Depends(get_db)):
    """
    Comprehensive index detail: metadata, latest performance, constituents with
    estimated weights, sector breakdown.
    """
    code = index_code.upper()
    meta = INDEX_META.get(code)
    if not meta:
        raise HTTPException(status_code=404, detail=f"Index '{code}' not found")

    def _f(v): return float(v) if v is not None else None

    # Latest price snapshot
    price_row = (await db.execute(text("""
        SELECT close_price, return_1d, return_1w, return_1m, return_3m,
               return_6m, return_1y, return_ytd, high_52w, low_52w,
               price_date::text AS price_date
        FROM market.index_prices
        WHERE index_code = :code
        ORDER BY price_date DESC LIMIT 1
    """), {"code": code})).mappings().fetchone()

    # Constituents
    flag_col = INDEX_UNIVERSE_FLAG.get(code)
    if flag_col:
        constituent_rows = (await db.execute(text(f"""
            SELECT u.asx_code, COALESCE(c.company_name, u.asx_code) AS company_name,
                   u.sector, u.market_cap, u.price,
                   u.return_1w AS return_1d, u.return_1y, u.pe_ratio, u.dividend_yield, u.franking_pct
            FROM screener.universe u
            LEFT JOIN market.companies c ON c.asx_code = u.asx_code
            WHERE u.{flag_col} = TRUE AND u.market_cap IS NOT NULL
            ORDER BY u.market_cap DESC NULLS LAST
        """))).mappings().all()
    else:
        sector_name = INDEX_GICS_SECTOR.get(code, "")
        constituent_rows = (await db.execute(text("""
            SELECT u.asx_code, COALESCE(c.company_name, u.asx_code) AS company_name,
                   u.sector, u.market_cap, u.price,
                   u.return_1w AS return_1d, u.return_1y, u.pe_ratio, u.dividend_yield, u.franking_pct
            FROM screener.universe u
            LEFT JOIN market.companies c ON c.asx_code = u.asx_code
            WHERE u.is_asx200 = TRUE AND u.sector = :sector AND u.market_cap IS NOT NULL
            ORDER BY u.market_cap DESC NULLS LAST
        """), {"sector": sector_name})).mappings().all()

    total_mcap = sum(float(r["market_cap"]) for r in constituent_rows if r["market_cap"])

    constituents: list[IndexConstituentRow] = []
    for r in constituent_rows:
        mc = _f(r["market_cap"])
        weight = round(mc / total_mcap * 100, 4) if total_mcap and mc else None
        constituents.append(IndexConstituentRow(
            asx_code=r["asx_code"],
            company_name=r["company_name"],
            sector=r["sector"],
            market_cap=mc,
            weight_pct=weight,
            price=_f(r["price"]),
            return_1d=_f(r["return_1d"]),
            return_1y=_f(r["return_1y"]),
            pe_ratio=_f(r["pe_ratio"]),
            dividend_yield=_f(r["dividend_yield"]),
            franking_pct=_f(r["franking_pct"]),
        ))

    # Sector breakdown
    sector_map: dict[str, dict] = defaultdict(lambda: {"count": 0, "market_cap_bn": 0.0, "weight_pct": 0.0})
    for c in constituents:
        s = c.sector or "Other"
        sector_map[s]["count"] += 1
        sector_map[s]["market_cap_bn"] += (c.market_cap or 0) / 1000
        sector_map[s]["weight_pct"] += (c.weight_pct or 0)
    sector_breakdown = [
        IndexSectorBreakdown(sector=s, count=v["count"],
                             market_cap_bn=round(v["market_cap_bn"], 2),
                             weight_pct=round(v["weight_pct"], 2))
        for s, v in sorted(sector_map.items(), key=lambda x: -x[1]["weight_pct"])
    ]

    # Price snapshot
    price_obj = None
    if price_row and price_row["close_price"]:
        price_obj = IndexPrice(
            index_code=code, display_name=meta["display_name"],
            price_date=price_row["price_date"],
            close_price=_f(price_row["close_price"]),
            return_1d=_f(price_row["return_1d"]), return_1w=_f(price_row["return_1w"]),
            return_1m=_f(price_row["return_1m"]), return_3m=_f(price_row["return_3m"]),
            return_6m=_f(price_row["return_6m"]), return_1y=_f(price_row["return_1y"]),
            return_ytd=_f(price_row["return_ytd"]),
            high_52w=_f(price_row["high_52w"]), low_52w=_f(price_row["low_52w"]),
        )

    etf_code = meta.get("primary_etf")
    etf_obj = IndexPrimaryETF(
        asx_code=etf_code,
        name=meta.get("primary_etf_name"),
        mer_pct=meta.get("primary_etf_mer"),
    ) if etf_code else None

    return IndexDetailResponse(
        index_code=code,
        display_name=meta["display_name"],
        description=meta.get("description"),
        eligibility=meta.get("eligibility"),
        methodology=meta.get("methodology"),
        rebalance_freq=meta.get("rebalance_freq"),
        market_coverage=meta.get("market_coverage"),
        primary_etf=etf_obj,
        price=price_obj,
        constituents=constituents,
        total_market_cap_bn=round(total_mcap / 1000, 1) if total_mcap else None,
        constituent_count=len(constituents),
        sector_breakdown=sector_breakdown,
    )


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
    """ETF and managed fund list with latest price data."""
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
            p.price_date::text AS price_date, p.close_price,
            p.return_1d, p.return_1w, p.return_1m, p.return_1y, p.return_ytd,
            p.distribution_yield, p.nav_discount_pct, p.high_52w, p.low_52w"""

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

    return FundsResponse(
        funds=[
            FundRow(
                asx_code=r["asx_code"], fund_name=r["fund_name"], fund_type=r["fund_type"],
                asset_class=r.get("asset_class"), index_tracked=r.get("index_tracked"),
                fund_manager=r.get("fund_manager"), mer_pct=_f(r.get("mer_pct")),
                funds_under_mgmt_bn=_f(r.get("funds_under_mgmt_bn")),
                distribution_freq=r.get("distribution_freq"), is_hedged=_b(r.get("is_hedged")),
                close_price=_f(r.get("close_price")), return_1d=_f(r.get("return_1d")),
                return_1w=_f(r.get("return_1w")), return_1m=_f(r.get("return_1m")),
                return_1y=_f(r.get("return_1y")), return_ytd=_f(r.get("return_ytd")),
                distribution_yield=_f(r.get("distribution_yield")),
                nav_discount_pct=_f(r.get("nav_discount_pct")),
                high_52w=_f(r.get("high_52w")), low_52w=_f(r.get("low_52w")),
                price_date=r.get("price_date"),
            )
            for r in rows
        ],
        total=len(rows),
        as_of=as_of.isoformat() if as_of else None,
    )


@router.get("/funds/{asx_code}/similar")
async def get_similar_funds(asx_code: str, db: AsyncSession = Depends(get_db)):
    """Return 5 funds in the same asset class."""
    code = asx_code.upper()
    fund = (await db.execute(text(
        "SELECT asset_class FROM market.funds WHERE asx_code = :code AND is_active = TRUE"
    ), {"code": code})).mappings().fetchone()

    if not fund:
        raise HTTPException(status_code=404, detail=f"Fund {code} not found")

    rows = (await db.execute(text("""
        SELECT f.asx_code, f.fund_name, f.fund_type, f.asset_class,
               f.index_tracked, f.fund_manager, f.mer_pct, f.funds_under_mgmt_bn,
               f.distribution_freq, f.is_hedged,
               p.close_price, p.return_1y, p.return_ytd, p.distribution_yield,
               p.nav_discount_pct, p.price_date::text AS price_date
        FROM market.funds f
        LEFT JOIN LATERAL (
            SELECT close_price, return_1y, return_ytd, distribution_yield,
                   nav_discount_pct, price_date
            FROM market.fund_prices
            WHERE asx_code = f.asx_code
            ORDER BY price_date DESC LIMIT 1
        ) p ON TRUE
        WHERE f.is_active = TRUE
          AND f.asset_class = :ac
          AND f.asx_code != :code
        ORDER BY f.funds_under_mgmt_bn DESC NULLS LAST
        LIMIT 5
    """), {"ac": fund["asset_class"], "code": code})).mappings().all()

    def _f(v): return float(v) if v is not None else None

    return {
        "similar": [
            FundRow(
                asx_code=r["asx_code"], fund_name=r["fund_name"], fund_type=r["fund_type"],
                asset_class=r.get("asset_class"), index_tracked=r.get("index_tracked"),
                fund_manager=r.get("fund_manager"), mer_pct=_f(r.get("mer_pct")),
                funds_under_mgmt_bn=_f(r.get("funds_under_mgmt_bn")),
                distribution_freq=r.get("distribution_freq"),
                close_price=_f(r.get("close_price")), return_1y=_f(r.get("return_1y")),
                return_ytd=_f(r.get("return_ytd")), distribution_yield=_f(r.get("distribution_yield")),
                nav_discount_pct=_f(r.get("nav_discount_pct")), price_date=r.get("price_date"),
            )
            for r in rows
        ]
    }


@router.get("/funds/{asx_code}")
async def get_fund_detail(
    asx_code: str,
    days: int = Query(365, ge=30, le=1825),
    db: AsyncSession = Depends(get_db),
):
    """Fund metadata + historical price data (default 1 year, up to 5 years)."""
    code = asx_code.upper()
    meta = (await db.execute(text("""
        SELECT asx_code, fund_name, fund_type, asset_class, index_tracked,
               fund_manager, mer_pct, funds_under_mgmt_bn,
               distribution_freq, is_hedged, inception_date::text AS inception_date, asx_url
        FROM market.funds
        WHERE asx_code = :code AND is_active = TRUE
    """), {"code": code})).mappings().fetchone()

    if not meta:
        raise HTTPException(status_code=404, detail=f"Fund {code} not found")

    hist = (await db.execute(text("""
        SELECT price_date::text AS price_date, close_price, return_1d,
               distribution_yield, nav_discount_pct, nav
        FROM market.fund_prices
        WHERE asx_code = :code
          AND price_date >= CURRENT_DATE - :days * INTERVAL '1 day'
        ORDER BY price_date ASC
    """), {"code": code, "days": days})).mappings().all()

    # Latest snapshot for key metrics
    latest = (await db.execute(text("""
        SELECT close_price, return_1d, return_1w, return_1m, return_1y,
               return_ytd, return_3y_pa, return_5y_pa,
               distribution_yield, nav_discount_pct, high_52w, low_52w,
               price_date::text AS price_date
        FROM market.fund_prices
        WHERE asx_code = :code
        ORDER BY price_date DESC LIMIT 1
    """), {"code": code})).mappings().fetchone()

    def _f(v): return float(v) if v is not None else None

    return {
        "asx_code":            meta["asx_code"],
        "fund_name":           meta["fund_name"],
        "fund_type":           meta["fund_type"],
        "asset_class":         meta["asset_class"],
        "index_tracked":       meta["index_tracked"],
        "fund_manager":        meta["fund_manager"],
        "mer_pct":             _f(meta["mer_pct"]),
        "funds_under_mgmt_bn": _f(meta["funds_under_mgmt_bn"]),
        "distribution_freq":   meta["distribution_freq"],
        "is_hedged":           meta["is_hedged"],
        "inception_date":      meta["inception_date"],
        "asx_url":             meta["asx_url"],
        "latest": {
            "price_date":          latest["price_date"] if latest else None,
            "close_price":         _f(latest["close_price"]) if latest else None,
            "return_1d":           _f(latest["return_1d"]) if latest else None,
            "return_1w":           _f(latest["return_1w"]) if latest else None,
            "return_1m":           _f(latest["return_1m"]) if latest else None,
            "return_1y":           _f(latest["return_1y"]) if latest else None,
            "return_ytd":          _f(latest["return_ytd"]) if latest else None,
            "return_3y_pa":        _f(latest["return_3y_pa"]) if latest else None,
            "return_5y_pa":        _f(latest["return_5y_pa"]) if latest else None,
            "distribution_yield":  _f(latest["distribution_yield"]) if latest else None,
            "nav_discount_pct":    _f(latest["nav_discount_pct"]) if latest else None,
            "high_52w":            _f(latest["high_52w"]) if latest else None,
            "low_52w":             _f(latest["low_52w"]) if latest else None,
        } if latest else None,
        "history": [
            {
                "date":              r["price_date"],
                "close":             _f(r["close_price"]),
                "return_1d":         _f(r["return_1d"]),
                "distribution_yield": _f(r["distribution_yield"]),
                "nav_discount_pct":  _f(r["nav_discount_pct"]),
            }
            for r in hist
        ],
    }
