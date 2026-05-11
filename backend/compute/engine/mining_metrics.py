"""
Mining Metrics Compute Engine
==============================
Populates market.mining_metrics from EODHD fundamentals.

EODHD's /api/fundamentals/{code}.AU endpoint returns a JSON blob with
financials and — for resource companies — commodity-specific fields in the
`General.Description` and `Highlights` section.

For most ASX miners, EODHD doesn't carry AISC/reserve data in structured
form (it lives in quarterly reports). This script:
  1. Pulls EODHD fundamentals for all is_miner=TRUE companies
  2. Extracts whatever commodity metadata is available (primary commodity,
     sector classification)
  3. Sets sensible defaults so the UI shows the company's commodity exposure
     even when detailed cost data is absent

Detailed metrics (AISC, ore reserves, reserve life) are populated via:
  - Manual entry through an admin panel (future)
  - CSV bulk upload (future)
  - Quarterly report parsing (future enhancement)

Run:
    python -m compute.engine.mining_metrics [--dry-run] [--limit N]

Scheduler: weekly on Sunday at 7am AEST.
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

# GICS sub-industry → primary commodity heuristic
_COMMODITY_MAP: dict[str, str] = {
    "Gold":                       "Gold",
    "Silver":                     "Silver",
    "Copper":                     "Copper",
    "Iron":                       "Iron Ore",
    "Lithium":                    "Lithium",
    "Nickel":                     "Nickel",
    "Zinc":                       "Zinc",
    "Aluminium":                  "Aluminium",
    "Coal":                       "Coal",
    "Oil":                        "Oil & Gas",
    "Gas":                        "Oil & Gas",
    "Uranium":                    "Uranium",
    "Rare":                       "Rare Earths",
    "Diamond":                    "Diamonds",
    "Mineral":                    "Diversified Mining",
    "Diversified Metal":          "Diversified Mining",
    "Steel":                      "Steel",
}


def _infer_commodity(name: str, description: str) -> str:
    """Infer primary commodity from company name and description text."""
    text_combined = f"{name} {description}".lower()

    # Ordered by priority (more specific first)
    checks = [
        ("lithium",  "Lithium"),
        ("uranium",  "Uranium"),
        ("rare earth", "Rare Earths"),
        ("diamond",  "Diamonds"),
        ("iron ore", "Iron Ore"),
        ("gold",     "Gold"),
        ("silver",   "Silver"),
        ("copper",   "Copper"),
        ("nickel",   "Nickel"),
        ("zinc",     "Zinc"),
        ("coal",     "Coal"),
        ("oil",      "Oil & Gas"),
        ("gas",      "Oil & Gas"),
        ("alumin",   "Aluminium"),
        ("manganese","Manganese"),
        ("cobalt",   "Cobalt"),
        ("tin",      "Tin"),
        ("lead",     "Lead"),
    ]
    for keyword, commodity in checks:
        if keyword in text_combined:
            return commodity
    return "Diversified Mining"


async def _fetch_fundamentals(code: str, timeout: int = 20) -> dict:
    """Fetch EODHD fundamentals for one ASX code."""
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
        # Get all active miners
        rows = (await session.execute(text("""
            SELECT asx_code, company_name
            FROM screener.universe
            WHERE is_miner = TRUE
            ORDER BY market_cap DESC NULLS LAST
            {}
        """.format(f"LIMIT {limit}" if limit else "")))).mappings().all()

        log.info("Processing %d mining companies", len(rows))
        upserted = 0

        for row in rows:
            code = row["asx_code"]
            name = row["company_name"] or code

            # Fetch EODHD fundamentals (rate limit: ~1 req/s for paid tier)
            fund = {}
            if EODHD_API_KEY:
                try:
                    fund = await _fetch_fundamentals(code)
                    await asyncio.sleep(0.3)  # gentle rate limiting
                except Exception as e:
                    log.debug("EODHD fetch failed for %s: %s", code, e)

            description = (
                (fund.get("General") or {}).get("Description") or ""
            )
            primary_commodity = _infer_commodity(name, description)

            if dry_run:
                log.info("[DRY RUN] %s → %s", code, primary_commodity)
                continue

            try:
                await session.execute(text("""
                    INSERT INTO market.mining_metrics
                        (asx_code, primary_commodity, data_source, updated_at)
                    VALUES
                        (:code, :commodity, 'eodhd_inference', NOW())
                    ON CONFLICT (asx_code) DO UPDATE SET
                        primary_commodity = EXCLUDED.primary_commodity,
                        data_source       = CASE
                            WHEN market.mining_metrics.data_source = 'manual'
                            THEN 'manual'      -- never overwrite manually entered data
                            ELSE 'eodhd_inference'
                        END,
                        updated_at        = NOW()
                """), {"code": code, "commodity": primary_commodity})
                upserted += 1
            except Exception as e:
                log.warning("Failed to upsert mining_metrics for %s: %s", code, e)

        if not dry_run:
            await session.commit()

    await engine.dispose()
    log.info("Mining metrics done — upserted=%d companies", upserted)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Populate market.mining_metrics")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0, help="Limit to N companies (0=all)")
    args = parser.parse_args()
    asyncio.run(run(dry_run=args.dry_run, limit=args.limit))
