"""
Market Snapshot Worker
======================
Daily scheduler job — runs at 7:50pm AEST (safety-net run after daily pipeline).
Delegates to compute.engine.market_snapshot.run().

Dependency gate: skips execution if the daily pipeline did not complete
successfully today (prevents writing a snapshot from stale/incomplete data).
"""
import logging
from datetime import date

from sqlalchemy import text
from app.db.session import AsyncSessionLocal
from app.workers.pipeline_tracker import track_scheduler_job

log = logging.getLogger(__name__)


async def run_market_snapshot() -> None:
    async with track_scheduler_job(
        "market_snapshot",
        "Market Snapshot",
        skip_if_pipeline_failed=False,   # gate: skip if pipeline failed today
    ) as job:
        if job.skipped:
            return   # pipeline gate fired — heartbeat still written below

        from compute.engine.market_snapshot import run
        await run(snapshot_date=date.today())
        log.info("Market snapshot complete for %s", date.today())

        # Invalidate market-related caches so homepage stats update immediately
        from app.core.cache import cache_delete_pattern
        deleted = await cache_delete_pattern("asx:market:*")
        log.info(f"Cache invalidated: {deleted} asx:market:* keys flushed")

    # ── Heartbeat (always written regardless of skip/success/failure) ─────────
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("""
                INSERT INTO meta.job_heartbeat (job_id, last_run_at, run_count)
                VALUES ('market_snapshot', NOW(), 1)
                ON CONFLICT (job_id) DO UPDATE SET
                    last_run_at = NOW(),
                    run_count   = meta.job_heartbeat.run_count + 1
            """))
            await db.commit()
    except Exception as hb_err:
        log.debug(f"Heartbeat write failed: {hb_err}")
