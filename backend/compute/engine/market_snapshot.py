"""
Market Snapshot Engine
======================
Computes daily market-level aggregates from screener.universe and writes them
to dedicated market snapshot tables. Run once daily after the universe build.

Tables written:
    market.index_snapshots   — ASX200 / ASX300 aggregate stats
    market.sector_snapshots  — per-sector performance
    market.mover_snapshots   — top 10 gainers, losers, most active, most shorted
    market.exdiv_snapshots   — upcoming ex-dividend dates (next 14 days)

Usage:
    python -m compute.engine.market_snapshot [--date YYYY-MM-DD] [--dry-run]
"""
import argparse
import asyncio
import logging
import os
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import text

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

DATABASE_URL = os.environ.get("DATABASE_URL", "")

TOP_N = 10
EXDIV_DAYS = 14


async def run(snapshot_date: date, dry_run: bool = False) -> None:
    if not DATABASE_URL:
        log.error("DATABASE_URL not set")
        sys.exit(1)

    engine = create_async_engine(DATABASE_URL, echo=False)
    async with AsyncSession(engine) as session:
        log.info("Snapshot date: %s  dry_run=%s", snapshot_date, dry_run)

        # ── 1. Index snapshots ────────────────────────────────────────────────
        for index_code, flag_col in [("ASX200", "is_asx200"), ("ASX300", "is_asx300")]:
            row = (await session.execute(text(f"""
                SELECT
                    COUNT(*)                                        AS stock_count,
                    COUNT(*) FILTER (WHERE return_1w > 0)          AS gainers,
                    COUNT(*) FILTER (WHERE return_1w < 0)          AS losers,
                    COUNT(*) FILTER (WHERE return_1w = 0 OR return_1w IS NULL) AS unchanged,
                    AVG(return_1w)                                 AS avg_return_1w,
                    SUM(market_cap) / 1000.0                       AS total_market_cap_bn
                FROM screener.universe
                WHERE {flag_col} = TRUE
                  AND status = 'active'
            """))).mappings().one()

            log.info("%s: %d stocks, gainers=%d, losers=%d, avg_1w=%.2f%%",
                     index_code,
                     row["stock_count"] or 0,
                     row["gainers"] or 0,
                     row["losers"] or 0,
                     (row["avg_return_1w"] or 0) * 100)

            if not dry_run:
                await session.execute(text("""
                    INSERT INTO market.index_snapshots
                        (snapshot_date, index_code, stock_count, gainers, losers, unchanged,
                         avg_return_1w, total_market_cap_bn)
                    VALUES
                        (:d, :ic, :sc, :g, :l, :u, :r1w, :mcap)
                    ON CONFLICT (snapshot_date, index_code) DO UPDATE SET
                        stock_count         = EXCLUDED.stock_count,
                        gainers             = EXCLUDED.gainers,
                        losers              = EXCLUDED.losers,
                        unchanged           = EXCLUDED.unchanged,
                        avg_return_1w       = EXCLUDED.avg_return_1w,
                        total_market_cap_bn = EXCLUDED.total_market_cap_bn,
                        created_at          = NOW()
                """), {
                    "d":    snapshot_date,
                    "ic":   index_code,
                    "sc":   row["stock_count"],
                    "g":    row["gainers"],
                    "l":    row["losers"],
                    "u":    row["unchanged"],
                    "r1w":  row["avg_return_1w"],
                    "mcap": row["total_market_cap_bn"],
                })

        # ── 2. Sector snapshots ───────────────────────────────────────────────
        sector_rows = (await session.execute(text("""
            SELECT
                sector,
                COUNT(*)                                                   AS stock_count,
                COUNT(*) FILTER (WHERE return_1w > 0)                     AS gainers,
                COUNT(*) FILTER (WHERE return_1w < 0)                     AS losers,
                AVG(return_1w) FILTER (WHERE return_1w IS NOT NULL)        AS avg_return_1w,
                SUM(market_cap) / 1000.0                                   AS total_market_cap_bn
            FROM screener.universe
            WHERE status = 'active'
              AND sector IS NOT NULL
            GROUP BY sector
            ORDER BY total_market_cap_bn DESC NULLS LAST
        """))).mappings().all()

        log.info("Sectors: %d", len(sector_rows))

        if not dry_run:
            for r in sector_rows:
                await session.execute(text("""
                    INSERT INTO market.sector_snapshots
                        (snapshot_date, sector, stock_count, gainers, losers,
                         avg_return_1w, total_market_cap_bn)
                    VALUES (:d, :s, :sc, :g, :l, :r1w, :mcap)
                    ON CONFLICT (snapshot_date, sector) DO UPDATE SET
                        stock_count         = EXCLUDED.stock_count,
                        gainers             = EXCLUDED.gainers,
                        losers              = EXCLUDED.losers,
                        avg_return_1w       = EXCLUDED.avg_return_1w,
                        total_market_cap_bn = EXCLUDED.total_market_cap_bn,
                        created_at          = NOW()
                """), {
                    "d":    snapshot_date,
                    "s":    r["sector"],
                    "sc":   r["stock_count"],
                    "g":    r["gainers"],
                    "l":    r["losers"],
                    "r1w":  r["avg_return_1w"],
                    "mcap": r["total_market_cap_bn"],
                })

        # ── 3. Mover snapshots ────────────────────────────────────────────────
        mover_base = """
            asx_code, company_name, sector,
            price, return_1w, market_cap,
            volume, avg_volume_20d, short_pct
        """
        liquid_filter = """
            status = 'active'
            AND price > 0.05
            AND market_cap > 20
        """

        movers: dict[str, list] = {}

        movers["GAINER"] = (await session.execute(text(f"""
            SELECT {mover_base}
            FROM screener.universe
            WHERE {liquid_filter} AND return_1w IS NOT NULL
            ORDER BY return_1w DESC NULLS LAST
            LIMIT {TOP_N}
        """))).mappings().all()

        movers["LOSER"] = (await session.execute(text(f"""
            SELECT {mover_base}
            FROM screener.universe
            WHERE {liquid_filter} AND return_1w IS NOT NULL
            ORDER BY return_1w ASC NULLS LAST
            LIMIT {TOP_N}
        """))).mappings().all()

        movers["ACTIVE"] = (await session.execute(text(f"""
            SELECT {mover_base}
            FROM screener.universe
            WHERE {liquid_filter} AND volume IS NOT NULL AND volume > 0
            ORDER BY volume DESC NULLS LAST
            LIMIT {TOP_N}
        """))).mappings().all()

        movers["SHORTED"] = (await session.execute(text(f"""
            SELECT {mover_base}
            FROM screener.universe
            WHERE {liquid_filter} AND short_pct IS NOT NULL AND short_pct > 0
              AND market_cap > 50
            ORDER BY short_pct DESC NULLS LAST
            LIMIT {TOP_N}
        """))).mappings().all()

        for snap_type, rows in movers.items():
            log.info("%-8s: %d rows", snap_type, len(rows))
            if not dry_run:
                for rank, r in enumerate(rows, start=1):
                    await session.execute(text("""
                        INSERT INTO market.mover_snapshots
                            (snapshot_date, snapshot_type, rank, asx_code, company_name,
                             sector, price, return_1w, volume, avg_volume_20d,
                             short_pct, market_cap)
                        VALUES
                            (:d, :st, :rk, :code, :name, :sec, :px, :r1w,
                             :vol, :avg_vol, :shrt, :mcap)
                        ON CONFLICT (snapshot_date, snapshot_type, rank) DO UPDATE SET
                            asx_code       = EXCLUDED.asx_code,
                            company_name   = EXCLUDED.company_name,
                            sector         = EXCLUDED.sector,
                            price          = EXCLUDED.price,
                            return_1w      = EXCLUDED.return_1w,
                            volume         = EXCLUDED.volume,
                            avg_volume_20d = EXCLUDED.avg_volume_20d,
                            short_pct      = EXCLUDED.short_pct,
                            market_cap     = EXCLUDED.market_cap,
                            created_at     = NOW()
                    """), {
                        "d":       snapshot_date,
                        "st":      snap_type,
                        "rk":      rank,
                        "code":    r["asx_code"],
                        "name":    r["company_name"],
                        "sec":     r["sector"],
                        "px":      r["price"],
                        "r1w":     r["return_1w"],
                        "vol":     r["volume"],
                        "avg_vol": r["avg_volume_20d"],
                        "shrt":    r["short_pct"],
                        "mcap":    r["market_cap"],
                    })

        # ── 4. Ex-dividend snapshots ──────────────────────────────────────────
        from datetime import timedelta
        cutoff = snapshot_date + timedelta(days=EXDIV_DAYS)
        exdiv_rows = (await session.execute(text("""
            SELECT
                asx_code, company_name,
                ex_div_date, pay_date,
                dps_ttm, dividend_yield, franking_pct
            FROM screener.universe
            WHERE status = 'active'
              AND ex_div_date IS NOT NULL
              AND ex_div_date BETWEEN :today AND :cutoff
            ORDER BY ex_div_date ASC
            LIMIT 50
        """), {"today": snapshot_date, "cutoff": cutoff})).mappings().all()

        log.info("Ex-div upcoming: %d stocks", len(exdiv_rows))

        if not dry_run:
            # Clear today's exdiv snapshot before reinserting (window shifts daily)
            await session.execute(text("""
                DELETE FROM market.exdiv_snapshots WHERE snapshot_date = :d
            """), {"d": snapshot_date})
            for r in exdiv_rows:
                await session.execute(text("""
                    INSERT INTO market.exdiv_snapshots
                        (snapshot_date, asx_code, company_name, ex_div_date,
                         pay_date, dps_ttm, dividend_yield, franking_pct)
                    VALUES (:d, :code, :name, :exd, :pay, :dps, :dy, :fp)
                    ON CONFLICT (snapshot_date, asx_code) DO UPDATE SET
                        ex_div_date    = EXCLUDED.ex_div_date,
                        pay_date       = EXCLUDED.pay_date,
                        dps_ttm        = EXCLUDED.dps_ttm,
                        dividend_yield = EXCLUDED.dividend_yield,
                        franking_pct   = EXCLUDED.franking_pct,
                        created_at     = NOW()
                """), {
                    "d":    snapshot_date,
                    "code": r["asx_code"],
                    "name": r["company_name"],
                    "exd":  r["ex_div_date"],
                    "pay":  r["pay_date"],
                    "dps":  r["dps_ttm"],
                    "dy":   r["dividend_yield"],
                    "fp":   r["franking_pct"],
                })

        if not dry_run:
            await session.commit()
            log.info("Committed snapshot for %s", snapshot_date)
        else:
            log.info("[DRY RUN] No data written")

    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ASX Market Snapshot")
    parser.add_argument("--date", default=str(date.today()), help="Snapshot date YYYY-MM-DD (default: today)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(run(date.fromisoformat(args.date), dry_run=args.dry_run))
