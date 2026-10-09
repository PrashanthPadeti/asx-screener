"""
The eligible fund population comes from the database, never from the fetch list
==============================================================================
`fund_prices` took `expected=len(FUNDS)` from the same hardcoded list that
decides what gets fetched. `market.funds` held 55; `FUNDS` held 47. The eight
missing ETFs served June prices for four months inside a job that reported
`success` every day, and **no assertion could have caught it**: remove an
entity from the list and `expected` falls with it.

This module provides the other side of the comparison. `eligible_codes` reads
`market.funds` and applies the lifecycle rules; `reconcile` sets that against
whatever the producer is configured to fetch. A population derived from the
thing it is meant to check cannot disagree with it.

Lifecycle
---------
`is_active` already existed but was written `TRUE` on every seed and never
updated — the seed's `ON CONFLICT` clause omits it — so nothing had ever
flipped it. The flag existed; the transition did not. Eligibility is
therefore defined positively, and a retirement has to be *recorded* rather
than implied by absence from a list:

    eligible    is_active = TRUE AND retired_at IS NULL
    retired     retired_at IS NOT NULL  (with a reason, and a successor
                                         where a corporate action created one)

A fund that is simply missing from the fetch list is **not** retired. That
conflation is the original defect.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable, Optional

from compute.engine.producer_contract import PopulationReconciliation

# sqlalchemy is imported lazily inside the query helpers, not at module
# scope. The lifecycle rules and the freshness classification are pure logic
# and must be testable without a database driver installed -- a pure rule
# that cannot be exercised without the DB layer tends not to get exercised.

#: Columns the lifecycle needs. Kept here so the migration and the reader
#: cannot drift apart silently.
LIFECYCLE_COLUMNS = ("retired_at", "retired_reason", "successor_code")

_HAS_LIFECYCLE = """
    SELECT count(*) FROM information_schema.columns
     WHERE table_schema = 'market' AND table_name = 'funds'
       AND column_name IN ('retired_at', 'retired_reason', 'successor_code')
"""

#: Eligibility with the lifecycle present. `{lifecycle}` is filled with the
#: retirement predicate, or emptied when the columns do not exist yet.
_ELIGIBLE = """
    SELECT asx_code
      FROM market.funds
     WHERE is_active = TRUE
       {lifecycle}
     ORDER BY asx_code
"""

LIFECYCLE_PREDICATE = "AND retired_at IS NULL"

#: What a caller is told when the migration has not been applied.
LIFECYCLE_UNAVAILABLE = "lifecycle metadata unavailable"

_RETIRED = """
    SELECT asx_code, retired_at, retired_reason, successor_code
      FROM market.funds
     WHERE retired_at IS NOT NULL
     ORDER BY asx_code
"""

#: Latest observed price per fund, independent of any global as-of date.
#:
#: `indices_funds.py` joins every fund to a single global MAX(price_date), so
#: a fund that stopped updating shows null rather than its own last value.
#: Freshness is a property of the entity, not of the table.
_FRESHNESS = """
    SELECT f.asx_code,
           f.is_active,
           max(p.price_date) AS last_price_date
      FROM market.funds f
      LEFT JOIN market.fund_prices p ON p.asx_code = f.asx_code
     GROUP BY f.asx_code, f.is_active
     ORDER BY max(p.price_date) NULLS FIRST, f.asx_code
"""

#: Trading days of silence before a live fund is considered stale. Three
#: covers a long weekend plus the day's run not having happened yet; the
#: eight-ETF defect ran to 120+ days, so the threshold is not a close call.
STALE_AFTER_DAYS = 5


@dataclass(frozen=True)
class FundFreshness:
    asx_code: str
    last_price_date: Optional[date]
    is_active: bool
    retired_at: Optional[date]

    @property
    def status(self) -> str:
        """current | stale | never | retired — never a bare date.

        A consumer must be able to tell "no data" from "old data" from "this
        security no longer trades". Returning only a date forces every caller
        to re-derive that, and they will not all do it the same way.
        """
        if self.retired_at is not None or not self.is_active:
            return "retired"
        if self.last_price_date is None:
            return "never"
        return "current" if self.age_days is not None \
            and self.age_days <= STALE_AFTER_DAYS else "stale"

    @property
    def age_days(self) -> Optional[int]:
        if self.last_price_date is None:
            return None
        return (date.today() - self.last_price_date).days


def _sql(statement: str):
    from sqlalchemy import text                                  # noqa: PLC0415
    return text(statement)


async def lifecycle_available(db) -> bool:
    """Whether the retirement columns exist yet.

    Reconciliation must run on the current schema. A pending migration is a
    reason to qualify the answer, never a reason to withhold it -- the eight
    omitted ETFs are visible today and were visible for four months, and
    blocking the report on a schema change nobody has applied would hide
    them for longer.
    """
    n = (await db.execute(_sql(_HAS_LIFECYCLE))).scalar() or 0
    return int(n) == len(LIFECYCLE_COLUMNS)


async def eligible_codes(db) -> frozenset[str]:
    """Funds the system undertakes to keep current. From the source.

    Without the lifecycle columns this falls back to `is_active` alone, which
    -- as established -- has never excluded anything, because the seed writes
    TRUE and its ON CONFLICT omits the column. The fallback therefore
    measures the CURRENT state honestly rather than the post-migration one,
    and callers are told which they are looking at.
    """
    lifecycle = LIFECYCLE_PREDICATE if await lifecycle_available(db) else ""
    rows = (await db.execute(
        _sql(_ELIGIBLE.format(lifecycle=lifecycle)))).scalars().all()
    return frozenset(rows)


async def retired_rows(db) -> list[dict] | None:
    """Recorded retirements, or None when the lifecycle columns are absent.

    None is not an empty list. "No retirement has been recorded" and "this
    schema cannot record one" are different facts, and collapsing them is the
    same conflation that let a missing fund look like a retired one.
    """
    if not await lifecycle_available(db):
        return None
    return [dict(r) for r in (await db.execute(_sql(_RETIRED))).mappings().all()]


async def freshness(db) -> list[FundFreshness]:
    return [
        FundFreshness(asx_code=r["asx_code"],
                      last_price_date=r["last_price_date"],
                      is_active=bool(r["is_active"]),
                      retired_at=r["retired_at"] if "retired_at" in r else None)
        for r in (await db.execute(_sql(_FRESHNESS))).mappings().all()
    ]


async def reconcile(db, configured: Iterable[str],
                    producer: str = "fund_prices") -> PopulationReconciliation:
    """Eligible-from-source against the configured fetch set.

    Both directions are findings and they are different findings: eligible
    but unconfigured is an omission that will never refresh; configured but
    not eligible is a request spent every day on a security that no longer
    trades.
    """
    return PopulationReconciliation(
        producer=producer,
        eligible=await eligible_codes(db),
        configured=frozenset(configured),
    )
