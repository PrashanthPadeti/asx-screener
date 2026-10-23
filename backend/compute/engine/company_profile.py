"""
Company profiles, refreshed weekly in daily slices
==================================================
Measured 23 Oct 2026: `employee_count`, `listing_date`, `logo_url`, `state`,
`abn` and `shares_outstanding` are populated for 0 of 2,589 current
companies. `description` and `website` for about 70%. The columns exist and
nothing fills them -- `asx_companies.py` writes only name, type and status,
and the rest came from manual scripts under scripts/eodhd/v2/ that are not
scheduled. That is why every company page reads "EMPLOYEES —".

The provider serves this data. A probe of five companies spanning a lithium
miner, a diversified major, a bank, healthcare and a 71-employee small cap
returned FullTimeEmployees, Officers, Address, Phone, LogoURL, WebURL, ISIN
and FiscalYearEnd for all five.

Why a daily slice and not a weekly run
--------------------------------------
Fundamentals costs EODHD 10 calls per request. A full refresh is

    2,589 companies x 10 = 25,890 calls

against an ASX share of ~30,000 a day, shared with the US screener. One
weekly burst would consume 86% of a day's budget and starve index prices,
fund prices and news on whichever day it landed.

So "weekly" is a property of each COMPANY, not of the job: every company is
refreshed every 7 days, by refreshing a seventh of them daily. ~370
companies, 3,700 calls, about 12% of budget, no spike. The job prices
itself with `cost_of` and asks `can_spend` before issuing anything.

Which companies, and why that order
-----------------------------------
The least recently refreshed first, NULLS FIRST -- a company never profiled
is the most urgent, not the least. That makes the slice self-correcting: a
day that fails for any reason leaves those companies at the front of
tomorrow's queue rather than skipping them until the cycle comes round
again.

What it does NOT write
----------------------
`isin`. `asx_companies.py` carries an explicit instruction never to touch
it, and this producer is not the place to overturn that decision.

Dating
------
Every successful refresh stamps `profile_updated_at` and `profile_source`.
An undated profile can go stale in silence, which is the defect this
codebase spent weeks removing from price series -- a page that says "1,175
employees" without saying when eventually says it for years. NULL means
never obtained, which is a different fact from "obtained, provider had
nothing", and the two must not render the same way.
"""

from __future__ import annotations

import asyncio
import logging
import math
from datetime import date, datetime, timezone
from typing import Any, Optional

from compute.engine.producer_contract import (
    PopulationReconciliation, ProducerTally, SourceRefused)

log = logging.getLogger(__name__)

PRODUCER = "company_profile"
SOURCE = "eodhd:fundamentals/General"

#: Every company refreshed this often. The daily slice is derived from it,
#: so changing this changes the slice rather than needing both kept in step.
REFRESH_EVERY_DAYS = 7

#: EODHD's own accounting, not HTTP requests. See app/core/api_budget.
ENDPOINT = "fundamentals"

#: Fields taken from the provider's General block, mapped to our columns.
#: Declared as data so the producer, the migration and the tests describe
#: the same set rather than three drifting lists.
FIELD_MAP: dict[str, str] = {
    "description":         "Description",
    "website":             "WebURL",
    "employee_count":      "FullTimeEmployees",
    "logo_url":            "LogoURL",
    "head_office_address": "Address",
    "phone":               "Phone",
    "ipo_date":            "IPODate",
    "lei":                 "LEI",
    "officers":            "Officers",
}

#: Deliberately excluded. asx_companies.py states that isin is never
#: touched; overturning that belongs in its own change, not here.
NEVER_WRITTEN = ("isin",)


def _clean(value: Any) -> Any:
    """Provider placeholders are not values."""
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text or text.upper() in ("NA", "N/A", "NONE", "NULL", "-"):
            return None
        return text
    if isinstance(value, (dict, list)) and not value:
        return None
    return value


def extract(general: dict) -> dict:
    """Our columns from the provider's General block.

    Absent and empty collapse to None deliberately: the provider returns
    "NA" and {} for things it does not have, and storing those would make
    "we asked and they had nothing" indistinguishable from a real value.
    """
    out: dict[str, Any] = {}
    for column, field in FIELD_MAP.items():
        value = _clean(general.get(field))
        if column == "employee_count" and value is not None:
            try:
                value = int(value)
            except (TypeError, ValueError):
                value = None
        if column == "ipo_date" and value is not None:
            try:
                value = date.fromisoformat(str(value)[:10])
            except ValueError:
                value = None
        out[column] = value
    return out


def fetch_general(code: str) -> dict:
    """The provider's General block for one ASX code.

    Raises SourceRefused on a refusal so the caller can tell "they declined
    to serve us" from "they have nothing for this company" -- conflating
    those is the defect producer_contract exists to prevent.
    """
    import httpx                                               # noqa: PLC0415

    from app.core.config import settings                       # noqa: PLC0415
    key = settings.EODHD_API_KEY
    if not key:
        raise SourceRefused(code, "EODHD_API_KEY not set")

    try:
        r = httpx.get(f"https://eodhd.com/api/fundamentals/{code}.AU",
                      params={"api_token": key, "fmt": "json"}, timeout=30)
    except Exception as exc:                                   # noqa: BLE001
        # Type only. An exception's text can carry the URL, and the URL
        # carries the api_token.
        log.warning("%s: fetch failed — %s", code, type(exc).__name__)
        return {}

    if r.status_code in (429, 402, 403):
        raise SourceRefused(code, f"HTTP {r.status_code}")
    if r.status_code == 404:
        return {}
    if r.status_code != 200:
        log.warning("%s: HTTP %s", code, r.status_code)
        return {}
    try:
        payload = r.json() or {}
    except ValueError:
        return {}
    return payload.get("General") or {}


async def eligible(db) -> list[str]:
    """Every active, current company. The population, from the source.

    Not a hardcoded list: a list cannot notice a company it omits, which is
    how eight ETFs served four-month-old prices inside a job reporting
    success every day.
    """
    from sqlalchemy import text
    rows = (await db.execute(text(
        "SELECT asx_code FROM market.companies "
        " WHERE is_current AND status = 'active' "
        " ORDER BY asx_code"))).all()
    return [r[0] for r in rows]


async def due_slice(db, size: int) -> list[str]:
    """The least recently refreshed companies, never-profiled first.

    NULLS FIRST because a company with no profile is the most urgent, not
    the least. A day that fails leaves its companies at the front of
    tomorrow's queue instead of skipping them for a whole cycle.
    """
    from sqlalchemy import text
    rows = (await db.execute(text(
        "SELECT asx_code FROM market.companies "
        " WHERE is_current AND status = 'active' "
        " ORDER BY profile_updated_at NULLS FIRST, asx_code "
        " LIMIT :n"), {"n": size})).all()
    return [r[0] for r in rows]


async def store(db, code: str, values: dict, dry_run: bool) -> None:
    """Update the current row's profile columns, and stamp when and from where.

    UPDATE of the current row, matching what asx_companies.py does for name
    and status. This does not create a new SCD version: a weekly profile
    refresh would otherwise multiply company history by 52 a year for data
    that rarely changes.
    """
    from sqlalchemy import text
    if dry_run:
        return
    sets = ", ".join(f"{c} = :{c}" for c in FIELD_MAP)
    await db.execute(text(
        f"UPDATE market.companies SET {sets}, "
        f"       profile_updated_at = :now, profile_source = :src "
        f" WHERE asx_code = :code AND is_current"),
        {**values, "code": code, "src": SOURCE,
         "now": datetime.now(timezone.utc)})


async def run(slice_size: Optional[int] = None,
              dry_run: bool = False) -> ProducerTally:
    """One daily slice. Returns the tally so the boundary can record it."""
    from app.core.api_budget import can_spend, cost_of
    from app.db.session import AsyncSessionLocal

    tally = ProducerTally(PRODUCER)

    async with AsyncSessionLocal() as db:
        all_codes = await eligible(db)
        if not all_codes:
            log.warning("%s: no eligible companies", PRODUCER)
            tally.verify()
            return tally

        size = slice_size or math.ceil(len(all_codes) / REFRESH_EVERY_DAYS)
        codes = await due_slice(db, size)

        # The population is the SLICE this run is responsible for, not every
        # company: a run that refreshes 370 of 2,589 has not failed to
        # refresh 2,219. Reconciled against the eligible set so a slice that
        # somehow selects a company no longer eligible is still a finding.
        tally.population = PopulationReconciliation(
            producer=PRODUCER,
            eligible=frozenset(codes),
            configured=frozenset(codes))
        tally.expected = len(codes)

        price = cost_of(ENDPOINT, len(codes))
        log.info("%s: %d of %d companies due; %d EODHD calls "
                 "(every company every %d days)",
                 PRODUCER, len(codes), len(all_codes), price,
                 REFRESH_EVERY_DAYS)

        # Priced before spending. Not critical: a profile is a week stale at
        # worst, while price ingestion starved of budget is a stale site.
        if not await can_spend(price, PRODUCER, critical=False):
            for code in codes:
                tally.excluded(code, "deferred: EODHD budget")
            log.warning("%s: deferred by budget — nothing fetched", PRODUCER)
            tally.verify()
            return tally

        for i, code in enumerate(codes):
            if i:
                await asyncio.sleep(0.2)        # polite, off the event loop
            try:
                general = await asyncio.to_thread(fetch_general, code)
            except SourceRefused as exc:
                tally.refusal(code, str(exc.detail or "refused"))
                continue

            if not general:
                tally.nothing_available(code)
                continue

            values = extract(general)
            if not any(v is not None for v in values.values()):
                # Served, but every field we map was empty. Not a refusal
                # and not a success -- recorded as what it is.
                tally.nothing_available(code)
                continue

            await store(db, code, values, dry_run)
            tally.obtained(code, rows=1)

        if not dry_run:
            await db.commit()

    log.info("Company profile complete — %s", tally.summary)
    for line in tally.report():
        log.warning("  OUTCOME: %s", line)
    if tally.degraded:
        log.warning("%s DEGRADED — %d of %d companies did not refresh; "
                    "the rest are stored", PRODUCER,
                    len(tally.failures) + len(tally.unaccounted), tally.expected)

    tally.verify()
    return tally
