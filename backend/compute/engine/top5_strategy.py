"""
Top 5 Strategy Compute Engine
==============================
Selects the top 5 ASX200 stocks by composite factor score each month and
writes them to strategy.monthly_picks.

Scoring uses pre-computed score columns on screener.universe
(value_score, quality_score, growth_score, momentum_score, income_score,
composite_score) which are populated by compute.engine.composite_score.

Rules:
  - Only ASX200 constituents (is_asx200 = TRUE) with status = 'active'
  - Composite score must be non-null
  - Runs once per month — if picks already exist for the current month,
    the run is a no-op unless --force is passed
  - Stores exactly 5 picks (rank 1–5) per month

Usage:
    python -m compute.engine.top5_strategy [--date YYYY-MM-DD] [--force] [--dry-run]
"""

import argparse
import asyncio
import logging
import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import text

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

DATABASE_URL = os.environ.get("DATABASE_URL", "")

TOP_N = 5


async def run(
    pick_month: date | None = None,
    force: bool = False,
    dry_run: bool = False,
) -> None:
    if not DATABASE_URL:
        log.error("DATABASE_URL not set")
        sys.exit(1)

    # Normalise pick_month to 1st of month
    today = date.today()
    if pick_month is None:
        pick_month = today.replace(day=1)
    else:
        pick_month = pick_month.replace(day=1)

    engine = create_async_engine(DATABASE_URL, echo=False)
    async with AsyncSession(engine) as session:

        # ── Guard: skip if picks already exist for this month ────────────────
        if not force:
            existing = (await session.execute(
                text("SELECT COUNT(*) FROM strategy.monthly_picks WHERE pick_month = :m"),
                {"m": pick_month},
            )).scalar() or 0
            if existing > 0:
                log.info("Picks already exist for %s (%d rows) — skipping. Use --force to overwrite.", pick_month, existing)
                return

        # ── Query top N stocks from screener.universe ────────────────────────
        rows = (await session.execute(text("""
            SELECT DISTINCT ON (u.asx_code)
                u.asx_code,
                c.company_name,
                c.gics_sector       AS sector,
                c.gics_industry_group AS industry,
                u.composite_score,
                u.momentum_score,
                u.quality_score,
                u.value_score,
                u.income_score,
                u.growth_score,
                u.price,
                u.market_cap,
                u.pe_ratio,
                u.dividend_yield,
                u.grossed_up_yield,
                u.franking_pct,
                u.return_3m,
                u.return_1y,
                u.roe,
                u.piotroski_f_score
            FROM screener.universe u
            JOIN market.companies c ON c.asx_code = u.asx_code
            WHERE u.is_asx200    = TRUE
              AND u.status       = 'active'
              AND u.composite_score IS NOT NULL
            ORDER BY u.asx_code, u.composite_score DESC
        """))).mappings().all()

        # Re-sort by composite_score and take top N (DISTINCT ON needs asx_code in ORDER BY)
        rows = sorted(rows, key=lambda r: r["composite_score"] or 0, reverse=True)[:TOP_N]

        if not rows:
            log.warning("No eligible ASX200 stocks found — nothing written.")
            return

        log.info("Top %d picks for %s:", len(rows), pick_month)
        for i, r in enumerate(rows, 1):
            log.info(
                "  #%d %s %-30s  composite=%.1f  momentum=%.1f  quality=%.1f  value=%.1f",
                i, r["asx_code"],
                (r["company_name"] or "")[:30],
                r["composite_score"] or 0,
                r["momentum_score"]  or 0,
                r["quality_score"]   or 0,
                r["value_score"]     or 0,
            )

        if dry_run:
            log.info("DRY RUN — no changes written.")
            return

        # ── Upsert picks ─────────────────────────────────────────────────────
        # Delete existing picks for this month (handles --force overwrite)
        await session.execute(
            text("DELETE FROM strategy.monthly_picks WHERE pick_month = :m"),
            {"m": pick_month},
        )

        for rank, r in enumerate(rows, 1):
            await session.execute(text("""
                INSERT INTO strategy.monthly_picks (
                    pick_month, rank, asx_code, company_name,
                    sector, industry,
                    composite_score, momentum_score, quality_score,
                    value_score, income_score, growth_score,
                    price, market_cap, pe_ratio,
                    dividend_yield, grossed_up_yield, franking_pct,
                    return_3m, return_1y, roe, piotroski_f_score,
                    computed_at
                ) VALUES (
                    :pick_month, :rank, :asx_code, :company_name,
                    :sector, :industry,
                    :composite_score, :momentum_score, :quality_score,
                    :value_score, :income_score, :growth_score,
                    :price, :market_cap, :pe_ratio,
                    :dividend_yield, :grossed_up_yield, :franking_pct,
                    :return_3m, :return_1y, :roe, :piotroski_f_score,
                    NOW()
                )
            """), {
                "pick_month":      pick_month,
                "rank":            rank,
                "asx_code":        r["asx_code"],
                "company_name":    r["company_name"],
                "sector":          r["sector"],
                "industry":        r["industry"],
                "composite_score": r["composite_score"],
                "momentum_score":  r["momentum_score"],
                "quality_score":   r["quality_score"],
                "value_score":     r["value_score"],
                "income_score":    r["income_score"],
                "growth_score":    r["growth_score"],
                "price":           r["price"],
                "market_cap":      r["market_cap"],
                "pe_ratio":        r["pe_ratio"],
                "dividend_yield":  r["dividend_yield"],
                "grossed_up_yield":r["grossed_up_yield"],
                "franking_pct":    r["franking_pct"],
                "return_3m":       r["return_3m"],
                "return_1y":       r["return_1y"],
                "roe":             r["roe"],
                "piotroski_f_score": r["piotroski_f_score"],
            })

        await session.commit()
        log.info("Committed %d picks for %s", len(rows), pick_month)


# ── CLI entry point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compute monthly Top 5 picks")
    parser.add_argument("--date",    help="Pick month as YYYY-MM-DD (defaults to current month)")
    parser.add_argument("--force",   action="store_true", help="Overwrite existing picks for the month")
    parser.add_argument("--dry-run", action="store_true", help="Print picks without writing to DB")
    args = parser.parse_args()

    month = date.fromisoformat(args.date) if args.date else None
    asyncio.run(run(pick_month=month, force=args.force, dry_run=args.dry_run))
