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
    python -m compute.engine.market_snapshot --backfill-days 30
"""
import argparse
import asyncio
import logging
import os
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# Load .env before reading DATABASE_URL so the script works when run directly.
# Search in the project root AND backend/ — the file lives in one or the other
# depending on how the server was deployed.
try:
    from dotenv import load_dotenv
    _here = Path(__file__).resolve()
    for _candidate in [
        _here.parents[2] / ".env",           # /opt/asx-screener/.env  (root)
        _here.parents[2] / "backend" / ".env", # /opt/asx-screener/backend/.env
        _here.parents[3] / ".env",            # one level higher, just in case
    ]:
        if _candidate.exists():
            load_dotenv(_candidate)
            break
except ImportError:
    pass  # dotenv not installed — rely on env vars already being set

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import text

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# Resolve async DATABASE_URL.
# Prefer the explicit async form; fall back to deriving it from DATABASE_URL_SYNC
# (which period_metrics_compute.py also uses) by swapping the driver prefix.
DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL:
    _sync = os.environ.get("DATABASE_URL_SYNC", "")
    if _sync:
        DATABASE_URL = _sync.replace("postgresql://", "postgresql+asyncpg://", 1)

TOP_N = 10
EXDIV_DAYS = 14

# The stage contract lives in snapshot_stages, which imports nothing
# third-party, so its properties can be asserted on any machine rather
# than only where SQLAlchemy is installed.
from compute.engine.snapshot_stages import (  # noqa: E402
    REQUIRED_STAGES, RETURN_PERIODS, SnapshotIncomplete, incomplete_stages,
)


async def _available_return_columns(session) -> set:
    """Which of RETURN_PERIODS' columns screener.universe actually has."""
    wanted = [col for _, col in RETURN_PERIODS]
    rows = (await session.execute(text("""
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'screener' AND table_name = 'universe'
          AND column_name = ANY(:cols)
    """), {"cols": wanted})).scalars().all()
    return set(rows)


async def run(snapshot_date: date, dry_run: bool = False) -> None:
    if not DATABASE_URL:
        log.error("DATABASE_URL not set")
        sys.exit(1)

    engine = create_async_engine(DATABASE_URL, echo=False)
    async with AsyncSession(engine) as session:
        log.info("Snapshot date: %s  dry_run=%s", snapshot_date, dry_run)

        #: rows written per stage, so the run can report what it actually did
        #: rather than that it reached the end.
        written: dict = {}

        # ── 1. Index snapshots ────────────────────────────────────────────────
        for index_code, flag_col in [("ASX200", "is_asx200"), ("ASX300", "is_asx300")]:
            row = (await session.execute(text(f"""
                SELECT
                    COUNT(*)                                        AS stock_count,
                    COUNT(*) FILTER (WHERE return_1w > 0)          AS gainers,
                    COUNT(*) FILTER (WHERE return_1w < 0)          AS losers,
                    -- Strictly flat. This FILTER used to read
                    --     return_1w = 0 OR return_1w IS NULL
                    -- which reported a company we have no return for as a
                    -- company whose price did not move. Unknown is not zero,
                    -- and the page has no way to tell them apart once they
                    -- are summed into one integer.
                    COUNT(*) FILTER (WHERE return_1w = 0)          AS unchanged,
                    COUNT(*) FILTER (WHERE return_1w IS NULL)      AS no_return,
                    AVG(return_1w)                                 AS avg_return_1w,
                    SUM(market_cap) / 1000.0                       AS total_market_cap_bn
                FROM screener.universe
                WHERE {flag_col} = TRUE
                  AND status = 'active'
            """))).mappings().one()

            # index_snapshots has no column for "we do not know", so there is
            # nowhere truthful to put these. Today the count is 0 for both
            # indices. If that changes, the run refuses rather than folding
            # them into `unchanged` -- which is exactly the destruction the
            # FILTER above was just repaired to stop. The fix when it fires is
            # a `no_return` column, not a wider FILTER.
            if (row["no_return"] or 0) > 0:
                raise SnapshotIncomplete(
                    f"{index_code}: {row['no_return']} of {row['stock_count']} "
                    f"constituents have no return_1w, and index_snapshots has "
                    f"no column to record that. Add one rather than counting "
                    f"them as unchanged.")

            log.info("%s: %d stocks, gainers=%d, losers=%d, avg_1w=%.2f%%",
                     index_code,
                     row["stock_count"] or 0,
                     row["gainers"] or 0,
                     row["losers"] or 0,
                     (row["avg_return_1w"] or 0) * 100)

            # Counted where the stage PRODUCES its row, not where it writes it.
            # Nesting this inside `if not dry_run` made the outcome line report
            # index=0, sector=0 on a dry run that had just computed 2 index
            # rows and 12 sector rows, while movers and ex-div -- counted
            # outside their write guards -- reported honestly. An instrument
            # that reads zero for work that happened is the same failure the
            # rest of this file exists to fix, one level up.
            written["index"] = written.get("index", 0) + 1

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

        # Committed HERE, not at the end of the run.
        #
        # This is the five-month bug. Every stage wrote into one session with a
        # single commit after stage 4, and stage 3's per-query handler called
        # session.rollback() on failure -- discarding stages 1 and 2 along with
        # the statement it meant to undo. The first mover query asks for
        # `return_1d`, a column screener.universe has never had, so the
        # rollback fired on EVERY run. Movers and ex-div, written after it,
        # committed normally. The result was two fresh outputs, two frozen at
        # 30 May 2026, and a log line saying the snapshot was committed.
        #
        # A stage that has finished its work owns its own transaction.
        if not dry_run:
            await session.commit()
            log.info("Committed index snapshots (%d rows)", written.get("index", 0))

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
        written["sector"] = len(sector_rows)

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

        if not dry_run:
            await session.commit()
            log.info("Committed sector snapshots (%d rows)", written.get("sector", 0))

        # ── 3. Mover snapshots ────────────────────────────────────────────────
        # Per-period base: select the relevant return column aliased as period_return
        liquid_filter = """
            status = 'active'
            AND price > 0.05
            AND market_cap > 20
        """

        # Period H/L column names in market.period_metrics
        period_hl_cols = {
            "1D": ("high_1d", "low_1d"),
            "1W": ("high_1w", "low_1w"),
            "1M": ("high_1m", "low_1m"),
            "3M": ("high_3m", "low_3m"),
        }

        # Use the most-recently-computed period_metrics date (avoids CURRENT_DATE race
        # when the nightly jobs run in different orders or near midnight).
        pm_date_subq = "(SELECT MAX(computed_date) FROM market.period_metrics)"

        movers: dict[str, list] = {}
        failed_movers: list = []

        # Compute gainers/losers for each period separately.
        # LEFT JOIN period_metrics so period_high/period_low are included in the snapshot row.
        #
        # Periods are filtered to columns that EXIST before any statement runs.
        # The previous version discovered a missing column by executing the
        # query and catching the error -- and `return_1d` has never existed, so
        # that handler fired on every run. A column that cannot exist is not a
        # runtime failure to be caught; it is a fact to be established first.
        available = await _available_return_columns(session)
        periods = [(s, c) for s, c in RETURN_PERIODS if c in available]
        for snap_suffix, ret_col in RETURN_PERIODS:
            if ret_col not in available:
                log.info("Skipping %s movers: screener.universe has no %s",
                         snap_suffix, ret_col)
        if not periods:
            raise SnapshotIncomplete(
                f"none of {[c for _, c in RETURN_PERIODS]} exist on "
                f"screener.universe; no mover period can be computed")

        for snap_suffix, ret_col in periods:
            ph_col, pl_col = period_hl_cols[snap_suffix]
            for snap_kind, order in [("GAINER", "DESC"), ("LOSER", "ASC")]:
                snap_type = f"{snap_kind}_{snap_suffix}"
                try:
                    # A SAVEPOINT, not the whole transaction. This handler used
                    # to call session.rollback(), which discards EVERY
                    # uncommitted write in the session -- stages 1 and 2
                    # included. A handler that means "undo this statement" must
                    # not be able to undo somebody else's work, whatever the
                    # commit boundaries around it happen to be today.
                    async with session.begin_nested():
                        rows = (await session.execute(text(f"""
                            SELECT u.asx_code, u.company_name, u.sector,
                                   u.price, u.{ret_col} AS period_return, u.market_cap,
                                   u.volume, u.avg_volume_20d, u.short_pct,
                                   pm.{ph_col} AS period_high,
                                   pm.{pl_col} AS period_low
                            FROM screener.universe u
                            LEFT JOIN market.period_metrics pm
                                   ON pm.asx_code = u.asx_code
                                  AND pm.computed_date = {pm_date_subq}
                            WHERE {liquid_filter} AND u.{ret_col} IS NOT NULL
                            ORDER BY u.{ret_col} {order} NULLS LAST
                            LIMIT {TOP_N}
                        """))).mappings().all()
                    movers[snap_type] = rows
                except Exception as e:
                    log.warning("Skipping %s: %s", snap_type, e)
                    movers[snap_type] = []
                    failed_movers.append(snap_type)

        # Keep legacy GAINER/LOSER (1W) for backwards compat
        movers["GAINER"] = movers.get("GAINER_1W", [])
        movers["LOSER"]  = movers.get("LOSER_1W",  [])

        # Volume panels: use 1W H/L (consistent with return_1w displayed in those rows)
        ph_col_1w, pl_col_1w = period_hl_cols["1W"]
        vol_base = f"""
            u.asx_code, u.company_name, u.sector,
            u.price, u.return_1w AS period_return, u.market_cap,
            u.volume, u.avg_volume_20d, u.short_pct,
            pm.{ph_col_1w} AS period_high,
            pm.{pl_col_1w} AS period_low
        """
        vol_join = f"""
            LEFT JOIN market.period_metrics pm
                   ON pm.asx_code = u.asx_code
                  AND pm.computed_date = {pm_date_subq}
        """

        movers["ACTIVE"] = (await session.execute(text(f"""
            SELECT {vol_base}
            FROM screener.universe u {vol_join}
            WHERE {liquid_filter} AND u.volume IS NOT NULL AND u.volume > 0
            ORDER BY u.volume DESC NULLS LAST
            LIMIT {TOP_N}
        """))).mappings().all()

        # Heavy buying: volume surge + price rising
        movers["BUYING"] = (await session.execute(text(f"""
            SELECT {vol_base}
            FROM screener.universe u {vol_join}
            WHERE {liquid_filter}
              AND u.volume IS NOT NULL AND u.avg_volume_20d IS NOT NULL AND u.avg_volume_20d > 0
              AND u.return_1w > 0
              AND u.volume::float / u.avg_volume_20d >= 1.5
            ORDER BY u.volume::float / u.avg_volume_20d DESC NULLS LAST
            LIMIT {TOP_N}
        """))).mappings().all()

        # Heavy selling: volume surge + price falling
        movers["SELLING"] = (await session.execute(text(f"""
            SELECT {vol_base}
            FROM screener.universe u {vol_join}
            WHERE {liquid_filter}
              AND u.volume IS NOT NULL AND u.avg_volume_20d IS NOT NULL AND u.avg_volume_20d > 0
              AND u.return_1w < 0
              AND u.volume::float / u.avg_volume_20d >= 1.5
            ORDER BY u.volume::float / u.avg_volume_20d DESC NULLS LAST
            LIMIT {TOP_N}
        """))).mappings().all()

        for snap_type, rows in movers.items():
            log.info("%-12s: %d rows", snap_type, len(rows))
            written["movers"] = written.get("movers", 0) + len(rows)
            if not dry_run:
                for rank, r in enumerate(rows, start=1):
                    # period_return is the aliased return column (return_1d/1w/1m/3m)
                    # stored in the return_1w column for query consistency
                    period_ret = r.get("period_return") if r.get("period_return") is not None \
                                 else r.get("return_1w")
                    await session.execute(text("""
                        INSERT INTO market.mover_snapshots
                            (snapshot_date, snapshot_type, rank, asx_code, company_name,
                             sector, price, return_1w, volume, avg_volume_20d,
                             short_pct, market_cap, period_high, period_low)
                        VALUES
                            (:d, :st, :rk, :code, :name, :sec, :px, :r1w,
                             :vol, :avg_vol, :shrt, :mcap, :ph, :pl)
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
                            period_high    = EXCLUDED.period_high,
                            period_low     = EXCLUDED.period_low,
                            created_at     = NOW()
                    """), {
                        "d":       snapshot_date,
                        "st":      snap_type,
                        "rk":      rank,
                        "code":    r["asx_code"],
                        "name":    r["company_name"],
                        "sec":     r["sector"],
                        "px":      r["price"],
                        "r1w":     period_ret,
                        "vol":     r["volume"],
                        "avg_vol": r["avg_volume_20d"],
                        "shrt":    r["short_pct"],
                        "mcap":    r["market_cap"],
                        "ph":      r.get("period_high"),
                        "pl":      r.get("period_low"),
                    })

        # ── 4. Ex-dividend snapshots ──────────────────────────────────────────
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

        written["exdiv"] = len(exdiv_rows)

        if not dry_run:
            await session.commit()
            log.info("Committed movers and ex-div for %s", snapshot_date)
        else:
            log.info("[DRY RUN] No data written")

        # ── What the run actually produced ────────────────────────────────────
        # Reached-the-end is not succeeded. The old engine logged "Committed
        # snapshot for <date>" after writing two of its four outputs and
        # discarding the other two, and every health signal above it agreed:
        # the heartbeat incremented, no failure was recorded, and the page
        # served 30 May figures for five months.
        #
        # Raised AFTER the commit on purpose. Whatever succeeded is real and
        # worth keeping; what must not survive is the claim that the run was
        # clean.
        log.info("Stage outcomes: %s", ", ".join(
            f"{stage}={written.get(stage, 0)}"
            for stage in ("index", "sector", "movers", "exdiv")))
        if failed_movers:
            log.warning("Mover snapshots that failed: %s", ", ".join(failed_movers))

        if not dry_run:
            empty = incomplete_stages(written)
            if empty:
                raise SnapshotIncomplete(
                    f"snapshot for {snapshot_date} wrote nothing for: "
                    f"{', '.join(empty)}. Outputs present: "
                    + ", ".join(f"{k}={v}" for k, v in sorted(written.items()))
                    + ". The run is recorded as failed rather than reporting "
                      "success for a partial snapshot.")

    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ASX Market Snapshot")
    parser.add_argument("--date", default=None, help="Snapshot date YYYY-MM-DD (default: today)")
    parser.add_argument("--backfill-days", type=int, default=None,
                        help="Run for each of the last N calendar days (overrides --date)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.backfill_days:
        today = date.today()
        dates = [today - timedelta(days=i) for i in range(args.backfill_days - 1, -1, -1)]
        async def backfill():
            for d in dates:
                log.info("=== Backfilling %s ===", d)
                await run(d, dry_run=args.dry_run)
        asyncio.run(backfill())
    else:
        snapshot_date = date.fromisoformat(args.date) if args.date else date.today()
        asyncio.run(run(snapshot_date, dry_run=args.dry_run))
