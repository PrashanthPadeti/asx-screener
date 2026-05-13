"""Nightly commodity prices worker — called by APScheduler."""
import logging
from datetime import date

log = logging.getLogger(__name__)


async def compute_commodities() -> None:
    try:
        from compute.engine.commodities import run
        await run(target_date=date.today(), backfill_days=3)
        # Invalidate cached commodities data so API serves fresh results immediately
        from app.core.cache import cache_delete_pattern
        deleted = await cache_delete_pattern("asx:commodities:*")
        log.info(f"Cache invalidated: {deleted} asx:commodities:* keys flushed")
    except Exception as exc:
        log.error(f"Commodities worker error: {exc}", exc_info=True)
