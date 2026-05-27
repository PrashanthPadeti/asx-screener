"""
Heatmap Compute Engine
======================
Pre-computes the rolling 5-day and 5-week performance heatmap for all
ASX stocks and stores results in market.heatmap_cache + market.heatmap_labels.

Run once daily after the Universe Build (pipeline step 5) so the API
can serve instant reads instead of running the heavy window-function
query live on every request.

Tables written:
    market.heatmap_cache   — one row per (mode, asx_code) with p1–p5 returns
    market.heatmap_labels  — one row per mode with 5 human-readable period labels

Usage:
    python -m compute.engine.heatmap_compute
    python -m compute.engine.heatmap_compute --dry-run
"""
import argparse
import asyncio
import datetime as dt
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

try:
    from dotenv import load_dotenv
    _here = Path(__file__).resolve()
    for _candidate in [
        _here.parents[2] / ".env",
        _here.parents[2] / "backend" / ".env",
        _here.parents[3] / ".env",
    ]:
        if _candidate.exists():
            load_dotenv(_candidate)
            break
except ImportError:
    pass

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import text

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL:
    _sync = os.environ.get("DATABASE_URL_SYNC", "")
    if _sync:
        DATABASE_URL = _sync.replace("postgresql://", "postgresql+asyncpg://", 1)


# ── DDL — create tables if they don't exist ───────────────────────────────────
# asyncpg does not allow multiple statements in one execute() call,
# so each DDL statement is kept as a separate string in this list.

DDL_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS market.heatmap_cache (
        mode         VARCHAR(10)   NOT NULL,
        asx_code     VARCHAR(10)   NOT NULL,
        company_name TEXT,
        sector       TEXT,
        industry     TEXT,
        price        NUMERIC(14,4),
        market_cap   NUMERIC(22,2),
        p1           NUMERIC(12,6),
        p2           NUMERIC(12,6),
        p3           NUMERIC(12,6),
        p4           NUMERIC(12,6),
        p5           NUMERIC(12,6),
        computed_at  TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
        PRIMARY KEY (mode, asx_code)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS market.heatmap_labels (
        mode        VARCHAR(10)  PRIMARY KEY,
        label_1     VARCHAR(30),
        label_2     VARCHAR(30),
        label_3     VARCHAR(30),
        label_4     VARCHAR(30),
        label_5     VARCHAR(30),
        computed_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS heatmap_cache_sector_idx
        ON market.heatmap_cache (mode, sector)
    """,
    """
    CREATE INDEX IF NOT EXISTS heatmap_cache_mktcap_idx
        ON market.heatmap_cache (mode, market_cap DESC NULLS LAST)
    """,
]


# ── Label formatters ──────────────────────────────────────────────────────────

def _fmt_day(d) -> str:
    """'Tue 26 May' from a date-like object."""
    if d is None:
        return ""
    if isinstance(d, str):
        d = dt.date.fromisoformat(str(d))
    return d.strftime("%a %-d %b")


def _fmt_week(week_start) -> str:
    """'W/E 23 May' — the Friday of the given ISO week-start (Monday)."""
    if week_start is None:
        return ""
    if isinstance(week_start, str):
        week_start = dt.date.fromisoformat(str(week_start))
    friday = week_start + dt.timedelta(days=4)
    return friday.strftime("W/E %-d %b")


# ── SQL queries ───────────────────────────────────────────────────────────────

DAYS_SQL = text("""
    WITH six_dates AS (
        SELECT DISTINCT DATE(time) AS td
        FROM market.daily_prices
        ORDER BY td DESC
        LIMIT 6
    ),
    prices AS (
        SELECT dp.asx_code, DATE(dp.time) AS td, dp.close
        FROM market.daily_prices dp
        INNER JOIN six_dates s ON DATE(dp.time) = s.td
        WHERE dp.close > 0
    ),
    lagged AS (
        SELECT asx_code, td, close,
               LAG(close) OVER (PARTITION BY asx_code ORDER BY td) AS prev_close,
               ROW_NUMBER() OVER (PARTITION BY asx_code ORDER BY td DESC) AS rn
        FROM prices
    )
    SELECT
        u.asx_code, u.company_name, u.sector, u.industry,
        u.price, u.market_cap,
        MAX(CASE WHEN l.rn=1 AND l.prev_close>0
            THEN (l.close - l.prev_close) / l.prev_close END) AS p1,
        MAX(CASE WHEN l.rn=2 AND l.prev_close>0
            THEN (l.close - l.prev_close) / l.prev_close END) AS p2,
        MAX(CASE WHEN l.rn=3 AND l.prev_close>0
            THEN (l.close - l.prev_close) / l.prev_close END) AS p3,
        MAX(CASE WHEN l.rn=4 AND l.prev_close>0
            THEN (l.close - l.prev_close) / l.prev_close END) AS p4,
        MAX(CASE WHEN l.rn=5 AND l.prev_close>0
            THEN (l.close - l.prev_close) / l.prev_close END) AS p5
    FROM screener.universe u
    INNER JOIN lagged l ON u.asx_code = l.asx_code
    WHERE u.status = 'active' AND u.price > 0.05 AND u.market_cap > 0
    GROUP BY u.asx_code, u.company_name, u.sector, u.industry,
             u.price, u.market_cap
    ORDER BY u.market_cap DESC NULLS LAST
""")

DAYS_LABELS_SQL = text("""
    SELECT DISTINCT DATE(time) AS td
    FROM market.daily_prices
    ORDER BY td DESC
    LIMIT 5
""")

WEEKS_SQL = text("""
    WITH weekly AS (
        SELECT
            asx_code,
            DATE_TRUNC('week', time)::date AS week_start,
            (ARRAY_AGG(close ORDER BY time DESC))[1] AS week_close
        FROM market.daily_prices
        WHERE time >= NOW() - INTERVAL '9 weeks' AND close > 0
        GROUP BY asx_code, DATE_TRUNC('week', time)
    ),
    lagged AS (
        SELECT
            asx_code, week_start, week_close,
            LAG(week_close) OVER (PARTITION BY asx_code ORDER BY week_start)
                AS prev_close,
            ROW_NUMBER() OVER (PARTITION BY asx_code ORDER BY week_start DESC)
                AS rn
        FROM weekly
    )
    SELECT
        u.asx_code, u.company_name, u.sector, u.industry,
        u.price, u.market_cap,
        MAX(CASE WHEN l.rn=1 AND l.prev_close>0
            THEN (l.week_close - l.prev_close) / l.prev_close END) AS p1,
        MAX(CASE WHEN l.rn=2 AND l.prev_close>0
            THEN (l.week_close - l.prev_close) / l.prev_close END) AS p2,
        MAX(CASE WHEN l.rn=3 AND l.prev_close>0
            THEN (l.week_close - l.prev_close) / l.prev_close END) AS p3,
        MAX(CASE WHEN l.rn=4 AND l.prev_close>0
            THEN (l.week_close - l.prev_close) / l.prev_close END) AS p4,
        MAX(CASE WHEN l.rn=5 AND l.prev_close>0
            THEN (l.week_close - l.prev_close) / l.prev_close END) AS p5
    FROM screener.universe u
    INNER JOIN lagged l ON u.asx_code = l.asx_code
    WHERE u.status = 'active' AND u.price > 0.05 AND u.market_cap > 0
      AND l.rn <= 5
    GROUP BY u.asx_code, u.company_name, u.sector, u.industry,
             u.price, u.market_cap
    ORDER BY u.market_cap DESC NULLS LAST
""")

WEEKS_LABELS_SQL = text("""
    SELECT DISTINCT DATE_TRUNC('week', time)::date AS week_start
    FROM market.daily_prices
    ORDER BY week_start DESC
    LIMIT 5
""")


# ── Core compute ──────────────────────────────────────────────────────────────

async def _compute_mode(
    session: AsyncSession,
    mode: str,
    data_sql,
    labels_sql,
    label_fn,
    dry_run: bool,
) -> int:
    """Compute one mode ('days' or 'weeks'), write to DB, return row count."""
    log.info(f"[heatmap] Computing mode={mode} ...")

    rows_result   = (await session.execute(data_sql)).mappings().all()
    labels_result = (await session.execute(labels_sql)).mappings().all()

    if not rows_result:
        log.warning(f"[heatmap] No rows returned for mode={mode} — skipping write")
        return 0

    # Build labels (5 entries, pad with "" if < 5 dates available)
    key = "td" if mode == "days" else "week_start"
    raw_labels = [label_fn(r[key]) for r in labels_result]
    while len(raw_labels) < 5:
        raw_labels.append("")

    log.info(f"[heatmap] mode={mode}: {len(rows_result)} stocks | "
             f"labels={raw_labels}")

    if dry_run:
        log.info("[heatmap] dry-run — skipping DB writes")
        return len(rows_result)

    # ── Atomic swap: delete old + insert new ─────────────────────────────────
    await session.execute(
        text("DELETE FROM market.heatmap_cache WHERE mode = :mode"),
        {"mode": mode},
    )

    # Batch insert (chunk to avoid huge parameter lists)
    CHUNK = 500
    rows_list = list(rows_result)
    for i in range(0, len(rows_list), CHUNK):
        chunk = rows_list[i:i + CHUNK]
        await session.execute(
            text("""
                INSERT INTO market.heatmap_cache
                    (mode, asx_code, company_name, sector, industry,
                     price, market_cap, p1, p2, p3, p4, p5, computed_at)
                VALUES
                    (:mode, :asx_code, :company_name, :sector, :industry,
                     :price, :market_cap, :p1, :p2, :p3, :p4, :p5, NOW())
            """),
            [
                {
                    "mode":         mode,
                    "asx_code":     r["asx_code"],
                    "company_name": r["company_name"],
                    "sector":       r["sector"],
                    "industry":     r["industry"],
                    "price":        float(r["price"]) if r["price"] is not None else None,
                    "market_cap":   float(r["market_cap"]) if r["market_cap"] is not None else None,
                    "p1":           float(r["p1"]) if r["p1"] is not None else None,
                    "p2":           float(r["p2"]) if r["p2"] is not None else None,
                    "p3":           float(r["p3"]) if r["p3"] is not None else None,
                    "p4":           float(r["p4"]) if r["p4"] is not None else None,
                    "p5":           float(r["p5"]) if r["p5"] is not None else None,
                }
                for r in chunk
            ],
        )

    # Upsert labels
    await session.execute(
        text("""
            INSERT INTO market.heatmap_labels
                (mode, label_1, label_2, label_3, label_4, label_5, computed_at)
            VALUES (:mode, :l1, :l2, :l3, :l4, :l5, NOW())
            ON CONFLICT (mode) DO UPDATE SET
                label_1     = EXCLUDED.label_1,
                label_2     = EXCLUDED.label_2,
                label_3     = EXCLUDED.label_3,
                label_4     = EXCLUDED.label_4,
                label_5     = EXCLUDED.label_5,
                computed_at = EXCLUDED.computed_at
        """),
        {
            "mode": mode,
            "l1":   raw_labels[0],
            "l2":   raw_labels[1],
            "l3":   raw_labels[2],
            "l4":   raw_labels[3],
            "l5":   raw_labels[4],
        },
    )

    return len(rows_list)


# ── Public entry point ────────────────────────────────────────────────────────

async def run(dry_run: bool = False) -> None:
    """Compute both 'days' and 'weeks' heatmap and persist to DB."""
    engine = create_async_engine(DATABASE_URL, echo=False)

    try:
        async with AsyncSession(engine) as session:
            # Ensure tables exist — each statement executed separately
            # (asyncpg rejects multi-statement strings in a single execute)
            for stmt in DDL_STATEMENTS:
                await session.execute(text(stmt))
            await session.commit()

            # Compute days
            n_days = await _compute_mode(
                session, "days",
                DAYS_SQL, DAYS_LABELS_SQL, _fmt_day, dry_run,
            )

            # Compute weeks
            n_weeks = await _compute_mode(
                session, "weeks",
                WEEKS_SQL, WEEKS_LABELS_SQL, _fmt_week, dry_run,
            )

            if not dry_run:
                await session.commit()
                log.info(
                    f"[heatmap] Committed — days={n_days} rows, weeks={n_weeks} rows"
                )
            else:
                log.info(
                    f"[heatmap] dry-run complete — days={n_days}, weeks={n_weeks}"
                )

    finally:
        await engine.dispose()


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pre-compute ASX heatmap cache")
    parser.add_argument("--dry-run", action="store_true",
                        help="Compute but do not write to DB")
    args = parser.parse_args()
    asyncio.run(run(dry_run=args.dry_run))
