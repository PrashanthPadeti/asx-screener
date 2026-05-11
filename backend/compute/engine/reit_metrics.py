"""
REIT Metrics Compute Engine
=============================
Populates market.reit_metrics from EODHD fundamentals + screener.universe.

For ASX REITs, many metrics (NTA, WALE, occupancy, FFO) are disclosed in
half-year and annual results announcements. This script:
  1. Pulls EODHD fundamentals for all is_reit=TRUE companies
  2. Extracts price_to_book (proxy for P/NTA before NTA data is confirmed)
  3. Infers REIT sector from company name / GICS classification
  4. Pulls distribution yield from screener.universe (dividend_yield field)

Detailed FFO and WALE data is populated via:
  - Manual entry through an admin panel (future)
  - Half-yearly financials parsing (future enhancement)

Run:
    python -m compute.engine.reit_metrics [--dry-run] [--limit N]

Scheduler: weekly on Sunday at 7:30am AEST.
"""
import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import httpx
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import text

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

DATABASE_URL  = os.environ.get("DATABASE_URL", "")
EODHD_API_KEY = os.environ.get("EODHD_API_KEY", "")

# Name → REIT sector heuristics
_SECTOR_MAP: list[tuple[str, str]] = [
    ("office",        "Office"),
    ("commercial",    "Office"),
    ("industrial",    "Industrial"),
    ("logistics",     "Industrial"),
    ("warehouse",     "Industrial"),
    ("retail",        "Retail"),
    ("shopping",      "Retail"),
    ("centre",        "Retail"),
    ("mall",          "Retail"),
    ("hotel",         "Hospitality"),
    ("hospitality",   "Hospitality"),
    ("childcare",     "Social Infrastructure"),
    ("healthcare",    "Healthcare"),
    ("medical",       "Healthcare"),
    ("hospital",      "Healthcare"),
    ("residential",   "Residential"),
    ("apartment",     "Residential"),
    ("rural",         "Rural"),
    ("agriculture",   "Rural"),
    ("storage",       "Self Storage"),
    ("data centre",   "Data Centre"),
    ("data center",   "Data Centre"),
]


def _infer_reit_sector(name: str, description: str) -> str:
    text_combined = f"{name} {description}".lower()
    for keyword, sector in _SECTOR_MAP:
        if keyword in text_combined:
            return sector
    return "Diversified"


async def _fetch_fundamentals(code: str, timeout: int = 20) -> dict:
    url = f"https://eodhd.com/api/fundamentals/{code}.AU"
    params = {"api_token": EODHD_API_KEY, "fmt": "json"}
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.get(url, params=params)
        if r.status_code != 200:
            return {}
        return r.json()


async def run(dry_run: bool = False, limit: int = 0) -> None:
    if not DATABASE_URL:
        log.error("DATABASE_URL not set")
        sys.exit(1)

    engine = create_async_engine(DATABASE_URL, echo=False)

    async with AsyncSession(engine) as session:
        rows = (await session.execute(text("""
            SELECT u.asx_code, u.company_name,
                   u.dividend_yield, u.price_to_book, u.price
            FROM screener.universe u
            WHERE u.is_reit = TRUE
            ORDER BY u.market_cap DESC NULLS LAST
            {}
        """.format(f"LIMIT {limit}" if limit else "")))).mappings().all()

        log.info("Processing %d REIT companies", len(rows))
        upserted = 0

        for row in rows:
            code    = row["asx_code"]
            name    = row["company_name"] or code
            div_yield = float(row["dividend_yield"]) if row["dividend_yield"] else None
            ptb       = float(row["price_to_book"])  if row["price_to_book"]  else None

            # Fetch EODHD fundamentals for sector inference
            fund        = {}
            description = ""
            if EODHD_API_KEY:
                try:
                    fund = await _fetch_fundamentals(code)
                    description = (fund.get("General") or {}).get("Description") or ""
                    await asyncio.sleep(0.3)
                except Exception as e:
                    log.debug("EODHD fetch failed for %s: %s", code, e)

            reit_sector = _infer_reit_sector(name, description)

            # price_to_book ≈ P/NTA for REITs (NTA ≈ book value)
            # premium_to_nta = (P - NTA) / NTA ≈ (P/B - 1)
            premium_to_nta = (ptb - 1.0) if ptb is not None else None

            if dry_run:
                log.info("[DRY RUN] %s → %s | dist_yield=%.2f%% | P/B=%.2fx",
                         code, reit_sector,
                         (div_yield or 0) * 100,
                         ptb or 0)
                continue

            try:
                await session.execute(text("""
                    INSERT INTO market.reit_metrics
                        (asx_code, reit_sector, distribution_yield,
                         premium_to_nta, data_source, updated_at)
                    VALUES
                        (:code, :sector, :dist_yield,
                         :premium_to_nta, 'eodhd_inference', NOW())
                    ON CONFLICT (asx_code) DO UPDATE SET
                        reit_sector        = EXCLUDED.reit_sector,
                        distribution_yield = COALESCE(EXCLUDED.distribution_yield,
                                                      market.reit_metrics.distribution_yield),
                        premium_to_nta     = COALESCE(EXCLUDED.premium_to_nta,
                                                      market.reit_metrics.premium_to_nta),
                        data_source        = CASE
                            WHEN market.reit_metrics.data_source = 'manual'
                            THEN 'manual'
                            ELSE 'eodhd_inference'
                        END,
                        updated_at         = NOW()
                """), {
                    "code":           code,
                    "sector":         reit_sector,
                    "dist_yield":     div_yield,
                    "premium_to_nta": premium_to_nta,
                })
                upserted += 1
            except Exception as e:
                log.warning("Failed to upsert reit_metrics for %s: %s", code, e)

        if not dry_run:
            await session.commit()

    await engine.dispose()
    log.info("REIT metrics done — upserted=%d companies", upserted)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Populate market.reit_metrics")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    asyncio.run(run(dry_run=args.dry_run, limit=args.limit))
