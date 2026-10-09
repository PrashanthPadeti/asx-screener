#!/usr/bin/env python
"""
Dry-run reconciliation of the fund population. Writes nothing.
==============================================================
Reports, without changing anything:

  * the source-derived eligible population against the configured fetch set,
    with the differing codes NAMED in both directions
  * per-fund latest price date and freshness status
  * recorded retirements

Read-only by construction: it issues SELECTs only, and never opens a
transaction that writes. An instrument must not join the system it observes —
a reconciliation that corrected what it found could not be run to find out
whether correction is needed.

    python scripts/reconcile_fund_population.py
"""

import asyncio
import logging
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

# Redaction before anything can construct an HTTP client or log a URL.
# Importing compute.engine installs it; this is explicit so the dependency is
# visible rather than incidental.
from app.core.log_redaction import install_secret_redaction      # noqa: E402

install_secret_redaction(level=logging.INFO,
                         format="%(asctime)s %(levelname)s %(message)s",
                         stream=sys.stdout)

from compute.engine.fund_population import (                     # noqa: E402
    STALE_AFTER_DAYS, freshness, reconcile, retired_rows)
from compute.engine.fund_prices import FUNDS                     # noqa: E402


def _rule(title: str) -> None:
    print(f"\n{title}\n{'─' * len(title)}")


async def _enforce_read_only(db) -> None:
    """Put the transaction in READ ONLY mode and PROVE a write is refused.

    A regex over the source can show no write statement was authored. It
    cannot show that none executes — a write reachable through a helper, an
    ORM flush, or a statement added later would all pass the scan. The
    database is the only thing that can actually refuse one, so this asks it
    to, and then checks that it does.

    The probe targets a scratch temp table, so if the guard is NOT in force
    the attempted write still touches nothing real.
    """
    from sqlalchemy import text                                  # noqa: PLC0415

    await db.execute(text("SET TRANSACTION READ ONLY"))
    try:
        await db.execute(text("CREATE TEMP TABLE _dry_run_write_probe (x int)"))
    except Exception:                                            # noqa: BLE001
        await db.rollback()
        await db.execute(text("SET TRANSACTION READ ONLY"))
        return
    raise RuntimeError(
        "the database accepted a write inside the dry run: READ ONLY is not "
        "in force and this script cannot claim to be read-only")


async def main() -> int:
    from app.db.session import AsyncSessionLocal                 # noqa: PLC0415

    configured = {f["asx_code"] for f in FUNDS}

    async with AsyncSessionLocal() as db:
        await _enforce_read_only(db)
        print("  containment: READ ONLY in force, a write was refused")
        recon = await reconcile(db, configured)
        rows = await freshness(db)
        retired = await retired_rows(db)

    _rule("Population")
    print(f"  eligible (market.funds, active, not retired) : {len(recon.eligible)}")
    print(f"  configured (FUNDS in fund_prices.py)         : {len(recon.configured)}")
    print(f"  omitted      (eligible, never fetched)       : {len(recon.omitted)}")
    print(f"  stale config (fetched, not eligible)         : {len(recon.stale_configured)}")

    if recon.omitted:
        print(f"\n  OMITTED — eligible but absent from the fetch set:")
        for code in sorted(recon.omitted):
            print(f"    {code}")
    if recon.stale_configured:
        print(f"\n  STALE CONFIG — fetched every run, not eligible:")
        for code in sorted(recon.stale_configured):
            print(f"    {code}")
    if recon.reconciled:
        print("\n  reconciled: the eligible population and the fetch set agree")

    _rule(f"Freshness (stale after {STALE_AFTER_DAYS} days)")
    by_status: dict[str, list] = {}
    for r in rows:
        by_status.setdefault(r.status, []).append(r)
    for status in ("never", "retired", "stale", "current"):
        group = by_status.get(status, [])
        print(f"  {status:<9} {len(group)}")
    for status in ("never", "retired", "stale"):
        for r in by_status.get(status, []):
            age = "—" if r.age_days is None else f"{r.age_days}d"
            print(f"    {r.asx_code:<8} {str(r.last_price_date or 'never'):<12} "
                  f"{status:<8} {age}")

    _rule("Recorded retirements")
    if not retired:
        print("  none — no lifecycle transition has been recorded yet")
    for r in retired:
        succ = r["successor_code"] or "—"
        print(f"  {r['asx_code']:<8} {r['retired_at']}  {r['retired_reason']}  "
              f"successor={succ}")

    _rule("Verdict")
    problems = recon.findings()
    unfresh = [r for r in rows if r.status in ("stale", "never")]
    if unfresh:
        problems.append(f"{len(unfresh)} eligible funds are stale or have "
                        f"never published")
    for p in problems:
        print(f"  FINDING  {p}")
    if not problems:
        print("  clean")
    print("\n  (dry run — no rows were written)")
    return 1 if problems else 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except Exception as exc:                                     # noqa: BLE001
        # Type only. An exception message here could carry a connection
        # string or a request URL.
        print(f"reconciliation failed: {type(exc).__name__}", file=sys.stderr)
        sys.exit(2)
