"""
Market-level summary endpoints.
Dashboard reads from pre-computed snapshot tables populated by
compute/engine/market_snapshot.py after each nightly universe build.
screener.universe is never queried here — snapshot tables own market-level data.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.db.session import get_db
from app.schemas.market import (
    MarketSummary,
    MoversResponse,
    MoverStock,
    SectorsResponse,
    SectorStat,
    MarketDashboard,
    IndexSnapshot,
    DashboardStock,
    ActiveStock,
    ShortedStock,
    SectorHeatmapItem,
    ExDivStock,
)

router = APIRouter()


@router.get("/summary", response_model=MarketSummary)
async def market_summary(db: AsyncSession = Depends(get_db)):
    """
    Aggregate stats for the entire ASX universe.
    Used for the homepage stats bar.
    """
    sql = text("""
        SELECT
            COUNT(*)                                                                    AS total_stocks,
            COUNT(*) FILTER (WHERE is_asx200)                                          AS asx200_stocks,
            COUNT(*) FILTER (WHERE dividend_yield > 0)                                 AS stocks_with_dividends,
            AVG(dividend_yield) FILTER (WHERE dividend_yield > 0
                                          AND dividend_yield < 0.30)                   AS avg_dividend_yield,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY pe_ratio)
                FILTER (WHERE pe_ratio > 0 AND pe_ratio < 100)                         AS median_pe,
            SUM(market_cap) / 1000.0                                                   AS total_market_cap_bn,
            MAX(universe_built_at)                                                     AS universe_built_at
        FROM screener.universe
        WHERE status = 'Active'
    """)
    row = (await db.execute(sql)).mappings().one()
    return MarketSummary(
        total_stocks=int(row["total_stocks"] or 0),
        asx200_stocks=int(row["asx200_stocks"] or 0),
        stocks_with_dividends=int(row["stocks_with_dividends"] or 0),
        avg_dividend_yield=float(row["avg_dividend_yield"]) if row["avg_dividend_yield"] is not None else None,
        median_pe=float(row["median_pe"]) if row["median_pe"] is not None else None,
        total_market_cap_bn=float(row["total_market_cap_bn"]) if row["total_market_cap_bn"] is not None else None,
        universe_built_at=row["universe_built_at"],
    )


@router.get("/movers", response_model=MoversResponse)
async def market_movers(db: AsyncSession = Depends(get_db)):
    """
    Top 5 weekly gainers and top 5 losers.
    Filters to stocks with price > $0.10 and market cap > $50M to exclude micro-caps.
    """
    cols = """
        asx_code,
        company_name,
        sector,
        price,
        return_1w,
        return_1m,
        market_cap
    """
    base_where = """
        WHERE return_1w IS NOT NULL
          AND status = 'Active'
          AND price > 0.10
          AND market_cap > 50
    """
    gainers_sql = text(f"""
        SELECT {cols}
        FROM screener.universe
        {base_where}
        ORDER BY return_1w DESC
        LIMIT 5
    """)
    losers_sql = text(f"""
        SELECT {cols}
        FROM screener.universe
        {base_where}
        ORDER BY return_1w ASC
        LIMIT 5
    """)

    gainers_rows = (await db.execute(gainers_sql)).mappings().all()
    losers_rows  = (await db.execute(losers_sql)).mappings().all()

    def to_mover(r) -> MoverStock:
        return MoverStock(
            asx_code=r["asx_code"],
            company_name=r["company_name"],
            sector=r["sector"],
            price=float(r["price"]) if r["price"] is not None else None,
            return_1w=float(r["return_1w"]) if r["return_1w"] is not None else None,
            return_1m=float(r["return_1m"]) if r["return_1m"] is not None else None,
            market_cap=float(r["market_cap"]) if r["market_cap"] is not None else None,
        )

    return MoversResponse(
        gainers=[to_mover(r) for r in gainers_rows],
        losers=[to_mover(r) for r in losers_rows],
        period="1w",
    )


@router.get("/sectors", response_model=SectorsResponse)
async def market_sectors(db: AsyncSession = Depends(get_db)):
    """
    Per-GICS-sector aggregate stats — stock count, avg P/E, avg yield, avg 1Y return, market cap.
    Ordered by total market cap descending.
    """
    sql = text("""
        SELECT
            sector,
            COUNT(*)                                                              AS stock_count,
            AVG(pe_ratio) FILTER (WHERE pe_ratio > 0 AND pe_ratio < 100)         AS avg_pe,
            AVG(dividend_yield) FILTER (WHERE dividend_yield > 0)                AS avg_dividend_yield,
            AVG(return_1y) FILTER (WHERE return_1y IS NOT NULL)                  AS avg_return_1y,
            SUM(market_cap) / 1000.0                                             AS total_market_cap_bn
        FROM screener.universe
        WHERE status = 'Active'
          AND sector IS NOT NULL
        GROUP BY sector
        ORDER BY total_market_cap_bn DESC NULLS LAST
    """)
    rows = (await db.execute(sql)).mappings().all()
    return SectorsResponse(
        sectors=[
            SectorStat(
                sector=r["sector"],
                stock_count=int(r["stock_count"]),
                avg_pe=float(r["avg_pe"]) if r["avg_pe"] is not None else None,
                avg_dividend_yield=float(r["avg_dividend_yield"]) if r["avg_dividend_yield"] is not None else None,
                avg_return_1y=float(r["avg_return_1y"]) if r["avg_return_1y"] is not None else None,
                total_market_cap_bn=float(r["total_market_cap_bn"]) if r["total_market_cap_bn"] is not None else None,
            )
            for r in rows
        ]
    )


@router.get("/dashboard", response_model=MarketDashboard)
async def market_dashboard(db: AsyncSession = Depends(get_db)):
    """
    All-in-one market overview sourced from pre-computed snapshot tables.
    Returns the latest available snapshot date (today or most recent prior day).
    """
    # Resolve latest snapshot date available
    date_row = (await db.execute(text("""
        SELECT MAX(snapshot_date) AS latest FROM market.index_snapshots
    """))).mappings().one()
    snap_date = date_row["latest"]

    if snap_date is None:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=503,
            detail="Market snapshot not yet available. Run compute/engine/market_snapshot.py first."
        )

    # Index snapshots
    idx_rows = (await db.execute(text("""
        SELECT index_code, stock_count, gainers, losers, unchanged,
               avg_return_1w, total_market_cap_bn
        FROM market.index_snapshots
        WHERE snapshot_date = :d
    """), {"d": snap_date})).mappings().all()
    idx = {r["index_code"]: r for r in idx_rows}

    def _snap(code: str) -> IndexSnapshot:
        r = idx.get(code, {})
        return IndexSnapshot(
            stock_count=int(r.get("stock_count") or 0),
            gainers=int(r.get("gainers") or 0),
            losers=int(r.get("losers") or 0),
            unchanged=int(r.get("unchanged") or 0),
            avg_return_1w=float(r["avg_return_1w"]) if r.get("avg_return_1w") is not None else None,
            total_market_cap_bn=float(r["total_market_cap_bn"]) if r.get("total_market_cap_bn") is not None else None,
        )

    # Sector heatmap
    sector_rows = (await db.execute(text("""
        SELECT sector, stock_count, gainers, losers, avg_return_1w, total_market_cap_bn
        FROM market.sector_snapshots
        WHERE snapshot_date = :d
        ORDER BY total_market_cap_bn DESC NULLS LAST
    """), {"d": snap_date})).mappings().all()

    # Mover snapshots
    mover_rows = (await db.execute(text("""
        SELECT snapshot_type, rank, asx_code, company_name, sector,
               price, return_1w, market_cap, volume, avg_volume_20d, short_pct
        FROM market.mover_snapshots
        WHERE snapshot_date = :d
        ORDER BY snapshot_type, rank
    """), {"d": snap_date})).mappings().all()

    by_type: dict[str, list] = {"GAINER": [], "LOSER": [], "ACTIVE": [], "SHORTED": []}
    for r in mover_rows:
        by_type.setdefault(r["snapshot_type"], []).append(r)

    def _dash(r) -> DashboardStock:
        return DashboardStock(
            asx_code=r["asx_code"],
            company_name=r["company_name"],
            sector=r["sector"],
            price=float(r["price"]) if r["price"] is not None else None,
            return_1w=float(r["return_1w"]) if r["return_1w"] is not None else None,
            market_cap=float(r["market_cap"]) if r["market_cap"] is not None else None,
        )

    # Ex-div snapshots
    exdiv_rows = (await db.execute(text("""
        SELECT asx_code, company_name,
               ex_div_date::text AS ex_div_date,
               pay_date::text    AS pay_date,
               dps_ttm, dividend_yield, franking_pct
        FROM market.exdiv_snapshots
        WHERE snapshot_date = :d
        ORDER BY ex_div_date ASC
    """), {"d": snap_date})).mappings().all()

    return MarketDashboard(
        asx200=_snap("ASX200"),
        asx300=_snap("ASX300"),
        sector_heatmap=[
            SectorHeatmapItem(
                sector=r["sector"],
                stock_count=int(r["stock_count"]),
                avg_return_1w=float(r["avg_return_1w"]) if r["avg_return_1w"] is not None else None,
                total_market_cap_bn=float(r["total_market_cap_bn"]) if r["total_market_cap_bn"] is not None else None,
            )
            for r in sector_rows
        ],
        top_gainers=[_dash(r) for r in by_type["GAINER"]],
        top_losers=[_dash(r) for r in by_type["LOSER"]],
        most_active=[
            ActiveStock(
                asx_code=r["asx_code"],
                company_name=r["company_name"],
                sector=r["sector"],
                price=float(r["price"]) if r["price"] is not None else None,
                return_1w=float(r["return_1w"]) if r["return_1w"] is not None else None,
                market_cap=float(r["market_cap"]) if r["market_cap"] is not None else None,
                volume=int(r["volume"]) if r["volume"] is not None else None,
                avg_volume_20d=int(r["avg_volume_20d"]) if r["avg_volume_20d"] is not None else None,
            )
            for r in by_type["ACTIVE"]
        ],
        most_shorted=[
            ShortedStock(
                asx_code=r["asx_code"],
                company_name=r["company_name"],
                sector=r["sector"],
                price=float(r["price"]) if r["price"] is not None else None,
                return_1w=float(r["return_1w"]) if r["return_1w"] is not None else None,
                market_cap=float(r["market_cap"]) if r["market_cap"] is not None else None,
                short_pct=float(r["short_pct"]) if r["short_pct"] is not None else None,
            )
            for r in by_type["SHORTED"]
        ],
        upcoming_exdiv=[
            ExDivStock(
                asx_code=r["asx_code"],
                company_name=r["company_name"],
                ex_div_date=r["ex_div_date"],
                pay_date=r["pay_date"],
                dps_ttm=float(r["dps_ttm"]) if r["dps_ttm"] is not None else None,
                dividend_yield=float(r["dividend_yield"]) if r["dividend_yield"] is not None else None,
                franking_pct=float(r["franking_pct"]) if r["franking_pct"] is not None else None,
            )
            for r in exdiv_rows
        ],
        period="1w",
        universe_built_at=snap_date.isoformat() if snap_date else None,
    )
