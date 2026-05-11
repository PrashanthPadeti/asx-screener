"""
Capital Raise Tracker
======================
Scans market.asx_announcements for capital raise keywords and populates
market.capital_raises with structured records.

Detects:
  - Placement (institutional)
  - Share Purchase Plan (SPP)
  - Rights Issue / Entitlement Offer
  - Initial Public Offering (IPO)
  - Dividend Reinvestment Plan (DRP) new issuances

Run:
    python -m compute.engine.capital_raise_tracker [--dry-run] [--days N]

Scheduler: daily at 7:30am AEST (after announcement fetch at 10-min intervals).
"""
import argparse
import asyncio
import logging
import re
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import text
import os

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

DATABASE_URL = os.environ.get("DATABASE_URL", "")

# ── Keyword patterns ──────────────────────────────────────────────────────────
# Each entry: (raise_type, list_of_regex_patterns)
# Patterns match against lowercased announcement title.

_PATTERNS: list[tuple[str, list[str]]] = [
    ("placement", [
        r"\bplacement\b",
        r"\binstitutional\s+placement\b",
        r"\bprivate\s+placement\b",
    ]),
    ("spp", [
        r"\bshare\s+purchase\s+plan\b",
        r"\bspp\b",
    ]),
    ("rights_issue", [
        r"\brights\s+issue\b",
        r"\brights\s+offer(?:ing)?\b",
        r"\bentitlement\s+offer\b",
        r"\brenounceable\s+offer\b",
        r"\bnon[\-\s]renounceable\b",
        r"\bpro[\-\s]rata\s+issue\b",
    ]),
    ("entitlement_offer", [
        r"\baccelerated\s+entitlement\s+offer\b",
        r"\binstitutional\s+entitlement\s+offer\b",
        r"\bretail\s+entitlement\s+offer\b",
    ]),
    ("ipo", [
        r"\binitial\s+public\s+offer(?:ing)?\b",
        r"\bipo\b",
        r"\bprospectus\b",
    ]),
    ("drp", [
        r"\bdividend\s+reinvestment\s+plan\b",
        r"\bdrp\b",
    ]),
]

_COMPILED: list[tuple[str, list[re.Pattern]]] = [
    (rtype, [re.compile(p, re.IGNORECASE) for p in patterns])
    for rtype, patterns in _PATTERNS
]


def _detect_raise_type(title: str) -> str | None:
    """Return the raise type if the title matches any pattern, else None."""
    for rtype, compiled in _COMPILED:
        for pat in compiled:
            if pat.search(title):
                return rtype
    return None


def _extract_amount(title: str) -> float | None:
    """
    Try to extract the raise amount in AUD millions from the title.
    Handles: '$50M', '$1.2 billion', 'A$100m', '$500,000' etc.
    """
    # Match patterns like $50M, $1.2B, $500K
    m = re.search(
        r"(?:A\$|\$|AUD\s*)(\d[\d,\.]*)\s*(?:(million|m|bn|billion|b|k|thousand))?",
        title,
        re.IGNORECASE,
    )
    if not m:
        return None
    try:
        raw = float(m.group(1).replace(",", ""))
        unit = (m.group(2) or "").lower()
        if unit in ("billion", "bn", "b"):
            return raw * 1000
        if unit in ("thousand", "k"):
            return raw / 1000
        if unit in ("million", "m", ""):
            # If no unit and value > 100,000 assume it's dollars not millions
            if not unit and raw > 100_000:
                return raw / 1_000_000
            return raw
        return raw
    except (ValueError, AttributeError):
        return None


def _extract_price(title: str) -> float | None:
    """
    Try to extract issue price from title.
    Handles: 'at $0.25 per share', 'at 25 cents', 'at A$1.20'
    """
    # cents pattern
    m = re.search(r"\bat\s+(\d+(?:\.\d+)?)\s+cents?\b", title, re.IGNORECASE)
    if m:
        try:
            return float(m.group(1)) / 100
        except ValueError:
            pass

    # dollar pattern
    m = re.search(r"\bat\s+(?:A\$|\$)(\d+(?:\.\d+)?)\s+per\s+(?:share|unit|new\s+share)", title, re.IGNORECASE)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass

    return None


async def run(dry_run: bool = False, days: int = 3) -> None:
    if not DATABASE_URL:
        log.error("DATABASE_URL not set")
        sys.exit(1)

    engine = create_async_engine(DATABASE_URL, echo=False)
    cutoff = date.today() - timedelta(days=days)

    async with AsyncSession(engine) as session:
        # Fetch recent announcements
        rows = (await session.execute(text("""
            SELECT ann.id, ann.asx_code, ann.title, ann.document_date, ann.url
            FROM market.asx_announcements ann
            WHERE ann.document_date >= :cutoff
            ORDER BY ann.document_date DESC
        """), {"cutoff": cutoff})).mappings().all()

        log.info("Scanning %d announcements since %s", len(rows), cutoff)

        found = 0
        inserted = 0

        for r in rows:
            title = r["title"] or ""
            rtype = _detect_raise_type(title)
            if not rtype:
                continue

            found += 1
            amount    = _extract_amount(title)
            price     = _extract_price(title)
            ann_date  = r["document_date"]
            asx_code  = r["asx_code"]

            if dry_run:
                log.info("[DRY RUN] %s | %s | %s | amt=%.1fM | price=$%.4f",
                         asx_code, rtype, ann_date,
                         amount or 0, price or 0)
                continue

            try:
                result = await session.execute(text("""
                    INSERT INTO market.capital_raises
                        (asx_code, raise_type, amount_m, price_per_share,
                         announcement_date, announcement_id, title, url)
                    VALUES
                        (:code, :rtype, :amount, :price,
                         :ann_date, :ann_id, :title, :url)
                    ON CONFLICT (asx_code, announcement_date, raise_type) DO NOTHING
                """), {
                    "code":     asx_code,
                    "rtype":    rtype,
                    "amount":   amount,
                    "price":    price,
                    "ann_date": ann_date,
                    "ann_id":   str(r["id"]),
                    "title":    title[:500],
                    "url":      r["url"],
                })
                if result.rowcount:
                    inserted += 1
            except Exception as e:
                log.warning("Failed to insert capital raise for %s: %s", asx_code, e)

        if not dry_run:
            await session.commit()

    await engine.dispose()
    log.info("Capital raise tracker done — found=%d, inserted=%d, days=%d",
             found, inserted, days)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scan announcements for capital raises")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--days", type=int, default=3,
                        help="How many days back to scan (default: 3)")
    args = parser.parse_args()
    asyncio.run(run(dry_run=args.dry_run, days=args.days))
