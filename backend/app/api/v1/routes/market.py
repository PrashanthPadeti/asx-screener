"""
Market-level summary endpoints — used by the homepage and market dashboard.
All data sourced from screener.universe (end-of-day, nightly batch).
"""
import asyncio
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
        gics_sector AS sector,
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
            gics_sector                                                           AS sector,
            COUNT(*)                                                              AS stock_count,
            AVG(pe_ratio) FILTER (WHERE pe_ratio > 0 AND pe_ratio < 100)         AS avg_pe,
            AVG(dividend_yield) FILTER (WHERE dividend_yield > 0)                AS avg_dividend_yield,
            AVG(return_1y) FILTER (WHERE return_1y IS NOT NULL)                  AS avg_return_1y,
            SUM(market_cap) / 1000.0                                             AS total_market_cap_bn
        FROM screener.universe
        WHERE status = 'Active'
          AND gics_sector IS NOT NULL
        GROUP BY gics_sector
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
    All-in-one market overview: index snapshots, sector heatmap, movers,
    volume leaders, most shorted, and upcoming ex-dividend dates.
    """
    mover_cols = """
        asx_code, company_name,
        gics_sector AS sector,
        price, return_1w, market_cap
    """
    base_filter = """
        status = 'Active'
        AND price > 0.05
        AND market_cap > 20
        AND return_1w IS NOT NULL
    """

    (
        asx200_rows,
        asx300_rows,
        sector_rows,
        gainers_rows,
        losers_rows,
        active_rows,
        shorted_rows,
        exdiv_rows,
        built_row,
    ) = await asyncio.gather(
        db.execute(text(f"""
            SELECT
                COUNT(*)                                        AS stock_count,
                COUNT(*) FILTER (WHERE return_1w > 0)          AS gainers,
                COUNT(*) FILTER (WHERE return_1w < 0)          AS losers,
                COUNT(*) FILTER (WHERE return_1w = 0)          AS unchanged,
                AVG(return_1w)                                 AS avg_return_1w,
                SUM(market_cap) / 1000.0                       AS total_market_cap_bn
            FROM screener.universe
            WHERE status = 'Active' AND is_asx200 = TRUE
        """)),
        db.execute(text(f"""
            SELECT
                COUNT(*)                                        AS stock_count,
                COUNT(*) FILTER (WHERE return_1w > 0)          AS gainers,
                COUNT(*) FILTER (WHERE return_1w < 0)          AS losers,
                COUNT(*) FILTER (WHERE return_1w = 0)          AS unchanged,
                AVG(return_1w)                                 AS avg_return_1w,
                SUM(market_cap) / 1000.0                       AS total_market_cap_bn
            FROM screener.universe
            WHERE status = 'Active' AND is_asx300 = TRUE
        """)),
        db.execute(text("""
            SELECT
                gics_sector                                                AS sector,
                COUNT(*)                                                   AS stock_count,
                AVG(return_1w) FILTER (WHERE return_1w IS NOT NULL)        AS avg_return_1w,
                SUM(market_cap) / 1000.0                                   AS total_market_cap_bn
            FROM screener.universe
            WHERE status = 'Active' AND gics_sector IS NOT NULL
            GROUP BY gics_sector
            ORDER BY total_market_cap_bn DESC NULLS LAST
        """)),
        db.execute(text(f"""
            SELECT {mover_cols}
            FROM screener.universe
            WHERE {base_filter}
            ORDER BY return_1w DESC NULLS LAST
            LIMIT 10
        """)),
        db.execute(text(f"""
            SELECT {mover_cols}
            FROM screener.universe
            WHERE {base_filter}
            ORDER BY return_1w ASC NULLS LAST
            LIMIT 10
        """)),
        db.execute(text("""
            SELECT
                asx_code, company_name,
                gics_sector AS sector,
                price, return_1w, market_cap,
                volume, avg_volume_20d
            FROM screener.universe
            WHERE status = 'Active'
              AND volume IS NOT NULL
              AND volume > 0
              AND price > 0.05
            ORDER BY volume DESC NULLS LAST
            LIMIT 10
        """)),
        db.execute(text("""
            SELECT
                asx_code, company_name,
                gics_sector AS sector,
                price, return_1w, market_cap,
                short_pct
            FROM screener.universe
            WHERE status = 'Active'
              AND short_pct IS NOT NULL
              AND short_pct > 0
              AND market_cap > 50
            ORDER BY short_pct DESC NULLS LAST
            LIMIT 10
        """)),
        db.execute(text("""
            SELECT
                asx_code, company_name,
                ex_div_date::text  AS ex_div_date,
                pay_date::text     AS pay_date,
                dps_ttm,
                dividend_yield,
                franking_pct
            FROM screener.universe
            WHERE status = 'Active'
              AND ex_div_date IS NOT NULL
              AND ex_div_date BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '14 days'
            ORDER BY ex_div_date ASC
            LIMIT 30
        """)),
        db.execute(text("""
            SELECT MAX(universe_built_at) AS universe_built_at
            FROM screener.universe
        """)),
    )

    def _snap(row) -> IndexSnapshot:
        r = row.mappings().one()
        return IndexSnapshot(
            stock_count=int(r["stock_count"] or 0),
            gainers=int(r["gainers"] or 0),
            losers=int(r["losers"] or 0),
            unchanged=int(r["unchanged"] or 0),
            avg_return_1w=float(r["avg_return_1w"]) if r["avg_return_1w"] is not None else None,
            total_market_cap_bn=float(r["total_market_cap_bn"]) if r["total_market_cap_bn"] is not None else None,
        )

    def _dash(r) -> DashboardStock:
        return DashboardStock(
            asx_code=r["asx_code"],
            company_name=r["company_name"],
            sector=r["sector"],
            price=float(r["price"]) if r["price"] is not None else None,
            return_1w=float(r["return_1w"]) if r["return_1w"] is not None else None,
            market_cap=float(r["market_cap"]) if r["market_cap"] is not None else None,
        )

    built_at = built_row.mappings().one()["universe_built_at"]

    return MarketDashboard(
        asx200=_snap(asx200_rows),
        asx300=_snap(asx300_rows),
        sector_heatmap=[
            SectorHeatmapItem(
                sector=r["sector"],
                stock_count=int(r["stock_count"]),
                avg_return_1w=float(r["avg_return_1w"]) if r["avg_return_1w"] is not None else None,
                total_market_cap_bn=float(r["total_market_cap_bn"]) if r["total_market_cap_bn"] is not None else None,
            )
            for r in sector_rows.mappings().all()
        ],
        top_gainers=[_dash(r) for r in gainers_rows.mappings().all()],
        top_losers=[_dash(r) for r in losers_rows.mappings().all()],
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
            for r in active_rows.mappings().all()
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
            for r in shorted_rows.mappings().all()
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
            for r in exdiv_rows.mappings().all()
        ],
        period="1w",
        universe_built_at=built_at,
    )
