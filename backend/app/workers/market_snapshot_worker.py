"""
Market Snapshot Worker
======================
Daily scheduler job — runs at 6:00pm AEST after universe build and price ingestion.
Delegates to compute.engine.market_snapshot.run().
"""
import logging
from datetime import date

log = logging.getLogger(__name__)


async def run_market_snapshot() -> None:
    try:
        from compute.engine.market_snapshot import run
        await run(snapshot_date=date.today())
        log.info("Market snapshot complete for %s", date.today())
    except Exception as exc:
        log.error("Market snapshot worker error: %s", exc, exc_info=True)
