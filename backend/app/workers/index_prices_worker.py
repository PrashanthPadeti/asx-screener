"""
Index Prices Worker
===================
Daily scheduler job — runs after ASX market close (5:30 pm AEST).
Delegates to compute.engine.index_prices.run().
"""
import logging
from datetime import date

log = logging.getLogger(__name__)


async def compute_index_prices() -> None:
    try:
        from compute.engine.index_prices import run
        await run(target_date=date.today(), backfill_days=3)
    except Exception as exc:
        log.error(f"Index prices worker error: {exc}", exc_info=True)
