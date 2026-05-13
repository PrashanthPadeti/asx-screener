"""
Fund Prices Worker
==================
Daily scheduler job — runs after ASX market close (5:35 pm AEST).
Delegates to compute.engine.fund_prices.run().
"""
import logging
from datetime import date

log = logging.getLogger(__name__)


async def compute_fund_prices() -> None:
    try:
        from compute.engine.fund_prices import run
        await run(target_date=date.today(), backfill_days=3)
        # Invalidate cached fund/ETF data so API serves fresh results immediately
        from app.core.cache import cache_delete_pattern
        deleted = await cache_delete_pattern("asx:funds:*")
        log.info(f"Cache invalidated: {deleted} asx:funds:* keys flushed")
    except Exception as exc:
        log.error(f"Fund prices worker error: {exc}", exc_info=True)
