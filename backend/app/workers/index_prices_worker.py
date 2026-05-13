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
        # Invalidate cached index data so API serves fresh results immediately
        from app.core.cache import cache_delete_pattern
        deleted = await cache_delete_pattern("asx:indices:*")
        log.info(f"Cache invalidated: {deleted} asx:indices:* keys flushed")
    except Exception as exc:
        log.error(f"Index prices worker error: {exc}", exc_info=True)
