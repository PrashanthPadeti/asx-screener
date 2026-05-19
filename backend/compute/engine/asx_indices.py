"""
ASX Index Constituent Updater
==============================
Updates is_asx20 / is_asx50 / is_asx100 / is_asx200 / is_asx300 flags in
screener.universe.

Strategy (in priority order):
  1. EODHD API — exact constituent lists if EODHD_API_KEY is set
  2. Market-cap approximation — rank active stocks by market_cap and take top N

Run daily after the universe build (prices / market caps must be fresh).

Usage:
    python -m compute.engine.asx_indices [--dry-run]
"""
import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import text

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# Load .env from backend/ directory so DATABASE_URL is available when run standalone
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

DATABASE_URL  = os.environ.get("DATABASE_URL", "")
EODHD_API_KEY = os.environ.get("EODHD_API_KEY", "")

# EODHD index tickers (INDX exchange)
EODHD_INDICES = {
    "is_asx20":  "ATOI.INDX",   # S&P/ASX 20
    "is_asx50":  "AFLI.INDX",   # S&P/ASX 50
    "is_asx100": "AOAD.INDX",   # S&P/ASX 100
    "is_asx200": "AXJO.INDX",   # S&P/ASX 200
    "is_asx300": "AXKO.INDX",   # S&P/ASX 300
}

INDEX_SIZES = {
    "is_asx20":  20,
    "is_asx50":  50,
    "is_asx100": 100,
    "is_asx200": 200,
    "is_asx300": 300,
}


async def _fetch_eodhd_constituents(ticker: str) -> set[str]:
    """Fetch constituent ASX codes from EODHD."""
    import httpx
    url = f"https://eodhd.com/api/v4/components/{ticker}"
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(url, params={"api_token": EODHD_API_KEY, "fmt": "json"})
        r.raise_for_status()
        data = r.json()
    codes: set[str] = set()
    for item in data:
        code = item.get("Code", "")
        if code:
            # EODHD returns codes like "BHP.AU" — strip exchange suffix
            codes.add(code.split(".")[0].upper())
    return codes


async def _update_via_eodhd(session: AsyncSession, dry_run: bool) -> bool:
    """Try updating flags via EODHD. Returns True on success."""
    if not EODHD_API_KEY:
        log.info("EODHD_API_KEY not set — skipping EODHD route")
        return False

    try:
        # Fetch each index
        flag_to_codes: dict[str, set[str]] = {}
        for flag, ticker in EODHD_INDICES.items():
            codes = await _fetch_eodhd_constituents(ticker)
            if not codes:
                log.warning("EODHD returned 0 codes for %s — aborting EODHD route", ticker)
                return False
            flag_to_codes[flag] = codes
            log.info("EODHD %s (%s): %d constituents", flag, ticker, len(codes))

        if dry_run:
            for flag, codes in flag_to_codes.items():
                log.info("[DRY RUN] Would set %s=TRUE for %d stocks", flag, len(codes))
            return True

        # Reset all flags in both tables first
        await session.execute(text("""
            UPDATE screener.universe
            SET is_asx20=FALSE, is_asx50=FALSE, is_asx100=FALSE,
                is_asx200=FALSE, is_asx300=FALSE
            WHERE status = 'active'
        """))
        await session.execute(text("""
            UPDATE market.companies
            SET is_asx20=FALSE, is_asx50=FALSE, is_asx100=FALSE,
                is_asx200=FALSE, is_asx300=FALSE
        """))

        for flag, codes in flag_to_codes.items():
            if not codes:
                continue
            await session.execute(
                text(f"UPDATE screener.universe SET {flag}=TRUE WHERE asx_code = ANY(:codes)"),
                {"codes": list(codes)},
            )
            await session.execute(
                text(f"UPDATE market.companies SET {flag}=TRUE WHERE asx_code = ANY(:codes)"),
                {"codes": list(codes)},
            )
            log.info("Set %s=TRUE for %d stocks", flag, len(codes))

        return True

    except Exception as exc:
        log.warning("EODHD route failed: %s — falling back to market-cap approximation", exc)
        return False


async def _update_via_market_cap(session: AsyncSession, dry_run: bool) -> None:
    """Fallback: rank active stocks by market cap, mark top-N for each index tier."""
    log.info("Using market-cap approximation for index flags")

    if dry_run:
        for flag, n in INDEX_SIZES.items():
            log.info("[DRY RUN] Would mark top %d stocks by market_cap as %s", n, flag)
        return

    # Single pass: compute rank once, set all flags in screener.universe
    await session.execute(text("""
        WITH ranked AS (
            SELECT asx_code,
                   ROW_NUMBER() OVER (ORDER BY market_cap DESC NULLS LAST) AS rn
            FROM screener.universe
            WHERE status = 'active'
              AND market_cap IS NOT NULL
              AND market_cap > 0
        )
        UPDATE screener.universe u
        SET
            is_asx20  = (r.rn <=  20),
            is_asx50  = (r.rn <=  50),
            is_asx100 = (r.rn <= 100),
            is_asx200 = (r.rn <= 200),
            is_asx300 = (r.rn <= 300)
        FROM ranked r
        WHERE u.asx_code = r.asx_code
    """))

    # Mirror flags to market.companies so universe rebuilds preserve them
    await session.execute(text("""
        UPDATE market.companies c
        SET
            is_asx20  = u.is_asx20,
            is_asx50  = u.is_asx50,
            is_asx100 = u.is_asx100,
            is_asx200 = u.is_asx200,
            is_asx300 = u.is_asx300
        FROM screener.universe u
        WHERE c.asx_code = u.asx_code
          AND u.status = 'active'
    """))

    counts = (await session.execute(text("""
        SELECT
            COUNT(*) FILTER (WHERE is_asx20)  AS n20,
            COUNT(*) FILTER (WHERE is_asx50)  AS n50,
            COUNT(*) FILTER (WHERE is_asx100) AS n100,
            COUNT(*) FILTER (WHERE is_asx200) AS n200,
            COUNT(*) FILTER (WHERE is_asx300) AS n300
        FROM screener.universe
        WHERE status = 'active'
    """))).mappings().one()
    log.info("Flags set — ASX20:%d  ASX50:%d  ASX100:%d  ASX200:%d  ASX300:%d",
             counts["n20"], counts["n50"], counts["n100"], counts["n200"], counts["n300"])


async def run(dry_run: bool = False) -> None:
    if not DATABASE_URL:
        log.error("DATABASE_URL not set")
        sys.exit(1)

    engine = create_async_engine(DATABASE_URL, echo=False)
    async with AsyncSession(engine) as session:
        success = await _update_via_eodhd(session, dry_run)
        if not success:
            await _update_via_market_cap(session, dry_run)

        if not dry_run:
            await session.commit()
            log.info("ASX index constituent flags committed")

    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Update ASX index constituent flags")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(run(dry_run=args.dry_run))
