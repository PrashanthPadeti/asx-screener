"""
ASX Index Constituent Worker
=============================
Daily scheduler job — updates is_asx200/is_asx300 flags in screener.universe
AND market.companies (so universe rebuilds preserve the flags).
Runs after the universe build so market caps are fresh.
"""
import logging

from sqlalchemy import text

from app.db.session import AsyncSessionLocal

log = logging.getLogger(__name__)


async def run_asx_indices() -> None:
    try:
        from compute.engine.asx_indices import run
        await run()
        log.info("ASX index constituent flags updated")
    except Exception as exc:
        log.error("ASX indices worker error: %s", exc, exc_info=True)
    finally:
        # Always record execution time so Pipeline Monitor shows true last-run
        try:
            async with AsyncSessionLocal() as db:
                await db.execute(text("""
                    INSERT INTO meta.job_heartbeat (job_id, last_run_at, run_count)
                    VALUES ('asx_index_flags', NOW(), 1)
                    ON CONFLICT (job_id) DO UPDATE SET
                        last_run_at = NOW(),
                        run_count   = meta.job_heartbeat.run_count + 1
                """))
                await db.commit()
        except Exception as hb_err:
            log.debug(f"Heartbeat write failed: {hb_err}")
