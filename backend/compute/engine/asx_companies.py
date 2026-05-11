"""
ASX Companies List Updater
===========================
Syncs the full list of ASX-listed securities into market.companies.

Data sources (in priority order):
  1. EODHD exchange-symbol-list/AU  — full ASX listing with code, name, type, ISIN
  2. ASX public API                 — fallback if EODHD unavailable

What it does:
  - INSERTs new companies (not yet in DB)
  - UPDATEs existing rows: company_name, isin, company_type, status → active
  - Marks companies no longer in the exchange list as status = 'delisted'
    (only if the API returned ≥ 500 records — safety guard against bad responses)

Run:
    python -m compute.engine.asx_companies [--dry-run] [--source eodhd|asx]

Scheduler: daily at 06:00 AEST (after nightly data ingestion).
"""
import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path
from datetime import date

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import httpx
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import text

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

DATABASE_URL  = os.environ.get("DATABASE_URL", "")
EODHD_API_KEY = os.environ.get("EODHD_API_KEY", "")

# EODHD company type → internal label mapping
_TYPE_MAP: dict[str, str] = {
    "Common Stock": "common_stock",
    "ETF":          "etf",
    "Fund":         "fund",
    "FUND":         "fund",
    "Preferred Stock": "preferred_stock",
    "Warrant":      "warrant",
    "Note":         "note",
    "Bond":         "bond",
}

# Minimum records from API before we'll mark anything as delisted
_MIN_RECORDS_FOR_DELIST = 500


async def _fetch_eodhd(timeout: int = 60) -> list[dict]:
    """Fetch full ASX listing from EODHD exchange-symbol-list API."""
    if not EODHD_API_KEY:
        log.info("EODHD_API_KEY not set — skipping EODHD source")
        return []

    url = "https://eodhd.com/api/exchange-symbol-list/AU"
    params = {"api_token": EODHD_API_KEY, "fmt": "json"}

    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        data = r.json()

    log.info("EODHD returned %d symbols for AU exchange", len(data))
    return data


async def _fetch_asx_fallback(timeout: int = 30) -> list[dict]:
    """
    Fallback: ASX's own public code/company list.
    Returns a minimal list with just Code + Name + Type.
    """
    # ASX provides a CSV of all listed entities
    url = "https://www.asx.com.au/asx/research/ASXListedCompanies.csv"
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; ASXScreener/1.0)",
        "Accept": "text/csv,*/*",
    }
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        r = await client.get(url, headers=headers)
        r.raise_for_status()
        text_body = r.text

    # CSV format:  "Company name","ASX code","GICS industry group"
    # First 3 lines are headers/metadata
    rows = []
    lines = text_body.splitlines()
    for line in lines[3:]:           # skip header rows
        parts = line.split('","')
        if len(parts) < 2:
            continue
        name = parts[0].lstrip('"').strip()
        code = parts[1].strip()
        gics = parts[2].rstrip('"').strip() if len(parts) > 2 else ""
        if not code or len(code) > 6:
            continue
        rows.append({
            "Code":     code,
            "Name":     name,
            "Type":     "Common Stock",
            "Isin":     None,
            "GicsGroup": gics,
        })

    log.info("ASX CSV fallback returned %d symbols", len(rows))
    return rows


def _normalise(raw: list[dict]) -> list[dict]:
    """
    Normalise raw records from either source into a consistent shape:
      { asx_code, company_name, isin, company_type, gics_industry_group }
    Filters to valid ASX codes only (2-6 uppercase chars, no dots).
    """
    out = []
    seen: set[str] = set()
    for item in raw:
        code = (item.get("Code") or "").strip().upper()
        # Remove exchange suffix if present (e.g. "BHP.AU" → "BHP")
        if "." in code:
            code = code.split(".")[0]
        # Basic validity: 2-6 uppercase alpha chars only
        if not code or not code.isalpha() or not (2 <= len(code) <= 6):
            continue
        if code in seen:
            continue
        seen.add(code)

        raw_type = item.get("Type") or "Common Stock"
        out.append({
            "asx_code":           code,
            "company_name":       (item.get("Name") or "").strip()[:200],
            "isin":               (item.get("Isin") or None),
            "company_type":       _TYPE_MAP.get(raw_type, raw_type[:30].lower()),
            "gics_industry_group": (item.get("GicsGroup") or None),
        })

    log.info("Normalised to %d valid ASX codes", len(out))
    return out


async def run(dry_run: bool = False, source: str = "auto") -> None:
    if not DATABASE_URL:
        log.error("DATABASE_URL not set")
        sys.exit(1)

    # ── Fetch data ───────────────────────────────────────────────────────────
    raw: list[dict] = []

    if source in ("auto", "eodhd"):
        try:
            raw = await _fetch_eodhd()
        except Exception as exc:
            log.warning("EODHD fetch failed: %s", exc)

    if not raw and source in ("auto", "asx"):
        try:
            raw = await _fetch_asx_fallback()
        except Exception as exc:
            log.error("ASX fallback fetch also failed: %s", exc)
            return

    if not raw:
        log.error("No data obtained — aborting")
        return

    records = _normalise(raw)

    if not records:
        log.error("No valid records after normalisation — aborting")
        return

    if dry_run:
        log.info("[DRY RUN] Would upsert %d companies into market.companies", len(records))
        for r in records[:10]:
            log.info("  %s | %s | %s", r["asx_code"], r["company_name"], r["company_type"])
        log.info("  ... (showing first 10)")
        return

    engine = create_async_engine(DATABASE_URL, echo=False)
    today  = date.today().isoformat()

    async with AsyncSession(engine) as session:
        # ── Fetch existing codes in one query ────────────────────────────────
        existing_rows = (await session.execute(text(
            "SELECT asx_code FROM market.companies"
        ))).scalars().all()
        existing_codes: set[str] = set(existing_rows)
        log.info("DB has %d existing companies", len(existing_codes))

        new_records     = [r for r in records if r["asx_code"] not in existing_codes]
        update_records  = [r for r in records if r["asx_code"] in existing_codes]

        # ── INSERT new companies ──────────────────────────────────────────────
        # Note: isin intentionally excluded — the companies_isin_key unique
        # constraint means EODHD's ISINs (which can duplicate across codes)
        # would cause conflicts. ISIN is populated by the dedicated data pipeline.
        insert_sql = text("""
            INSERT INTO market.companies
                (asx_code, company_name, company_type, status, updated_at)
            VALUES
                (:asx_code, :company_name, :company_type, 'active', NOW())
        """)
        for i in range(0, len(new_records), 200):
            batch = new_records[i:i+200]
            for row in batch:
                await session.execute(insert_sql, {
                    "asx_code":     row["asx_code"],
                    "company_name": row["company_name"],
                    "company_type": row["company_type"],
                })
        log.info("Inserted %d new companies", len(new_records))

        # ── UPDATE existing companies ─────────────────────────────────────────
        # Only update company_name, company_type, status — never touch isin
        update_sql = text("""
            UPDATE market.companies SET
                company_name = :company_name,
                company_type = COALESCE(:company_type, company_type),
                status       = 'active',
                updated_at   = NOW()
            WHERE asx_code = :asx_code
        """)
        for i in range(0, len(update_records), 200):
            batch = update_records[i:i+200]
            for row in batch:
                await session.execute(update_sql, {
                    "asx_code":     row["asx_code"],
                    "company_name": row["company_name"],
                    "company_type": row["company_type"],
                })
        log.info("Updated %d existing companies", len(update_records))

        # ── Delist companies no longer in the exchange list ───────────────────
        if len(records) >= _MIN_RECORDS_FOR_DELIST:
            active_codes = [r["asx_code"] for r in records]
            delist_result = await session.execute(text("""
                UPDATE market.companies
                SET status = 'delisted', updated_at = NOW()
                WHERE status = 'active'
                  AND asx_code != ALL(:codes)
            """), {"codes": active_codes})
            delisted = delist_result.rowcount
            if delisted:
                log.info("Marked %d companies as delisted (not in exchange list)", delisted)
        else:
            log.warning(
                "Only %d records from API — skipping delist step (threshold: %d)",
                len(records), _MIN_RECORDS_FOR_DELIST
            )

        # ── Update GICS industry group where available from ASX CSV ──────────
        gics_updates = [r for r in records if r.get("gics_industry_group")]
        if gics_updates:
            gics_sql = text("""
                UPDATE market.companies
                SET gics_industry_group = :gics, updated_at = NOW()
                WHERE asx_code = :asx_code
                  AND gics_industry_group IS NULL
            """)
            for row in gics_updates:
                await session.execute(gics_sql, {
                    "asx_code": row["asx_code"],
                    "gics": row["gics_industry_group"],
                })
            log.info("Updated GICS industry group for %d companies (null fill only)", len(gics_updates))

        await session.commit()

    await engine.dispose()

    # ── Summary ───────────────────────────────────────────────────────────────
    log.info(
        "Done — upserted %d companies into market.companies (source: %s, date: %s)",
        len(records), source, today,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sync ASX company list into market.companies")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing to DB")
    parser.add_argument("--source", choices=["auto", "eodhd", "asx"], default="auto",
                        help="Data source (default: auto — try EODHD then ASX fallback)")
    args = parser.parse_args()
    asyncio.run(run(dry_run=args.dry_run, source=args.source))
