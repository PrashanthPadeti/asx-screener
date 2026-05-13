"""
Global Markets Worker
=====================
Daily scheduler job — runs after market close (5:40pm AEST).
Fetches global index prices and AUD FX rates via compute.engine.global_markets.
"""
import logging
from datetime import date

log = logging.getLogger(__name__)


async def compute_global_markets() -> None:
    try:
        from compute.engine.global_markets import run
        await run(target_date=date.today(), backfill_days=3)
        # Invalidate cached global markets data so API serves fresh results immediately
        from app.core.cache import cache_delete_pattern
        deleted = await cache_delete_pattern("asx:global_markets:*")
        log.info(f"Cache invalidated: {deleted} asx:global_markets:* keys flushed")
    except Exception as exc:
        log.error(f"Global markets worker error: {exc}", exc_info=True)
