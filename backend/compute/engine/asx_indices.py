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

from compute.engine.producer_contract import ProducerFailure

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# Load .env from backend/ directory so DATABASE_URL is available when run standalone
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

DATABASE_URL  = os.environ.get("DATABASE_URL", "")
EODHD_API_KEY = os.environ.get("EODHD_API_KEY", "")

# EODHD index tickers (INDX exchange).
#
# Verified 7 Oct 2026 against EODHD's own exchange-symbol-list for INDX
# (1,679 symbols, 33 ASX-related) and by fetching each one. Two were wrong:
#
#     is_asx20   was ATOI.INDX  -- ATOI is the S&P/ASX *100*
#     is_asx100  was AOAD.INDX  -- no such symbol exists at EODHD
#
# The second is why the whole route failed every day: one 404 aborts the
# fetch loop, so all five flags fell through to the market-cap fallback.
EODHD_INDICES = {
    "is_asx20":  "ATLI.INDX",   # S&P/ASX 20   (n=20  on 7 Oct 2026)
    "is_asx50":  "AFLI.INDX",   # S&P/ASX 50   (n=50)
    "is_asx100": "ATOI.INDX",   # S&P/ASX 100  (n=100)
    "is_asx200": "AXJO.INDX",   # S&P/ASX 200  (n=199)
    "is_asx300": "AXKO.INDX",   # S&P/ASX 300  (n=290)
}

#: The source returns fewer constituents than the index name implies for the
#: two largest (199 and 290). That is the provider's view of membership and it
#: is published as-is. Truncating or padding to a round number would be
#: inventing membership, and asserting `== 200` would make a correct run fail.
#: INDEX_SIZES below is used ONLY by the market-cap fallback, which ranks.

INDEX_SIZES = {
    "is_asx20":  20,
    "is_asx50":  50,
    "is_asx100": 100,
    "is_asx200": 200,
    "is_asx300": 300,
}


async def _fetch_eodhd_constituents(ticker: str) -> set[str]:
    """Fetch constituent ASX codes from EODHD.

    The endpoint is `fundamentals/{SYMBOL}.INDX`, which returns
    `{"General": {...}, "Components": {"0": {...}, "1": {...}}}`.

    It was `v4/components/{SYMBOL}`, which returns 404 for every symbol --
    measured 7 Oct 2026 on AXJO.INDX: fundamentals 200 OK with 199
    components, v4/components 404. Every scheduled run since at least 6 Oct
    logged that 404 at WARNING and silently used the market-cap fallback.
    """
    import httpx
    url = f"https://eodhd.com/api/fundamentals/{ticker}"
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(url, params={"api_token": EODHD_API_KEY, "fmt": "json"})
        r.raise_for_status()
        data = r.json()

    return codes_from_components(data)


def codes_from_components(payload: dict) -> set[str]:
    """ASX codes out of a `fundamentals/{SYMBOL}.INDX` response.

    `Components` is a dict keyed by position — `{"0": {...}, "1": {...}}` —
    not a list. Iterating the mapping directly yields the keys "0", "1", ...,
    so this takes `.values()`. A list is tolerated in case the shape changes.

    Pure, so the parse is tested without a network call.
    """
    components = (payload or {}).get("Components") or {}
    items = components.values() if isinstance(components, dict) else components

    codes: set[str] = set()
    for item in items:
        code = (item or {}).get("Code", "")
        if code:
            # Exchange is a separate field ("AU"), but tolerate a suffixed
            # form in case that changes.
            codes.add(str(code).split(".")[0].upper())
    return codes


async def _clear_all_flags(session: AsyncSession) -> None:
    """Clear every index flag, everywhere, before any path sets them.

    Previously this lived inside the EODHD branch only -- the branch that has
    been failing -- so the market-cap fallback never cleared anything. It set
    exact ranks in `screener.universe` and then mirrored those onto matching
    codes in `market.companies`, leaving every code NOT in the universe with
    whatever flag it last held.

    Measured 7 Oct 2026, `is_asx300` in market.companies_current:

        321 = 300 correct
            +  15 in market.companies but absent from screener.universe
            +   6 delisted rows inside screener.universe

    The 6 come from the second half: the fallback's rank CTE filters
    `status = 'active'`, so delisted universe rows were never recomputed, and
    the old universe clear carried the same filter. This one does not.

    `AND is_current` on market.companies is new. Without it the clear wiped
    index flags from superseded SCD rows and the set marked them TRUE,
    rewriting history that should record what was true at the time.
    """
    await session.execute(text("""
        UPDATE screener.universe
        SET is_asx20=FALSE, is_asx50=FALSE, is_asx100=FALSE,
            is_asx200=FALSE, is_asx300=FALSE
        WHERE is_asx20 OR is_asx50 OR is_asx100 OR is_asx200 OR is_asx300
    """))
    await session.execute(text("""
        UPDATE market.companies
        SET is_asx20=FALSE, is_asx50=FALSE, is_asx100=FALSE,
            is_asx200=FALSE, is_asx300=FALSE
        WHERE is_current
          AND (is_asx20 OR is_asx50 OR is_asx100 OR is_asx200 OR is_asx300)
    """))


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

        await _clear_all_flags(session)

        for flag, codes in flag_to_codes.items():
            if not codes:
                continue
            await session.execute(
                text(f"UPDATE screener.universe SET {flag}=TRUE WHERE asx_code = ANY(:codes)"),
                {"codes": list(codes)},
            )
            await session.execute(
                text(f"UPDATE market.companies SET {flag}=TRUE "
                     f"WHERE asx_code = ANY(:codes) AND is_current"),
                {"codes": list(codes)},
            )
            log.info("Set %s=TRUE for %d stocks", flag, len(codes))

        return True

    except Exception as exc:
        log.warning("EODHD route failed: %s — falling back to market-cap approximation", exc)
        return False


async def _update_via_market_cap(session: AsyncSession, dry_run: bool) -> None:
    """Rank active stocks by market cap and mark top-N for each index tier.

    **This is not index membership.** The S&P/ASX indices are selected by an
    S&P committee with liquidity and free-float rules and are rebalanced
    quarterly; top-N-by-market-cap is a different question that happens to
    produce a similar answer. Writing it into `is_asx200` puts a proxy under a
    name that asserts membership.

    It is therefore no longer a silent fallback. Reaching it requires
    `--market-cap-approximation` explicitly, so an operator who wants a rough
    answer during a source outage can have one and knows what they asked for.
    Before 7 Oct 2026 this ran automatically on any EODHD error, and did so
    every day, logged at WARNING, for an unknown length of time.
    """
    log.warning("Using market-cap approximation for index flags — this is a "
                "PROXY, not S&P/ASX membership")
    await _clear_all_flags(session)

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

    # Mirror flags to market.companies so universe rebuilds preserve them.
    # `AND c.is_current` keeps superseded SCD rows holding what was true when
    # they were current.
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
          AND c.is_current
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


def _sync_dsn() -> str:
    """The canonical lease needs a plain psycopg2 DSN, not the asyncpg URL."""
    import os
    url = os.environ.get("DATABASE_URL_SYNC", "")
    if not url:
        url = os.environ.get("DATABASE_URL", "").replace(
            "postgresql+asyncpg://", "postgresql://")
    return url


async def run(dry_run: bool = False,
              market_cap_approximation: bool = False) -> None:
    if not DATABASE_URL:
        log.error("DATABASE_URL not set")
        sys.exit(1)

    # screener.universe is a canonical table. This writes only index
    # membership flags -- none of the 72 governed metrics -- so it stays OUT
    # of the canonical plan and its failure must never gate finalisation. But
    # it still mutates the table the driver owns, so it takes the same lease
    # and defers when a canonical execution holds it.
    from compute.engine.canonical_lease import auxiliary_lease_async

    async with auxiliary_lease_async(_sync_dsn(), why="asx_indices") as permitted:
        if not permitted:
            return

        engine = create_async_engine(DATABASE_URL, echo=False)
        async with AsyncSession(engine) as session:
            success = await _update_via_eodhd(session, dry_run)

            if not success:
                if not market_cap_approximation:
                    # Fail rather than substitute. A proxy written into
                    # is_asx200 answers a different question under the same
                    # name, and that substitution ran unnoticed because it was
                    # silent. Yesterday's flags stand, which is honest: we do
                    # not know today's membership.
                    raise ProducerFailure(
                        "asx_indices could not obtain S&P/ASX constituents "
                        "from EODHD; index flags left unchanged. Re-run with "
                        "--market-cap-approximation to write a ranked proxy "
                        "instead, knowing it is not index membership.")
                await _update_via_market_cap(session, dry_run)

            if not dry_run:
                await session.commit()
                log.info("ASX index constituent flags committed")

        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Update ASX index constituent flags")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--market-cap-approximation", action="store_true",
                        help="Write top-N-by-market-cap into the index flags "
                             "when EODHD is unavailable. This is a PROXY, not "
                             "S&P/ASX membership.")
    args = parser.parse_args()
    asyncio.run(run(dry_run=args.dry_run,
                    market_cap_approximation=args.market_cap_approximation))
