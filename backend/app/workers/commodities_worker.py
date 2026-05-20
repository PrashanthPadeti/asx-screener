"""Nightly commodity prices worker — called by APScheduler."""
import logging
from datetime import date

from sqlalchemy import text
from app.db.session import AsyncSessionLocal

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
    finally:
        try:
            async with AsyncSessionLocal() as db:
                await db.execute(text("""
                    INSERT INTO meta.job_heartbeat (job_id, last_run_at, run_count)
                    VALUES ('commodities', NOW(), 1)
                    ON CONFLICT (job_id) DO UPDATE SET
                        last_run_at = NOW(),
                        run_count   = meta.job_heartbeat.run_count + 1
                """))
                await db.commit()
        except Exception as hb_err:
            log.debug(f"Heartbeat write failed: {hb_err}")
