"""
ASIC Short Positions Worker
============================
Daily scheduler job — downloads latest ASIC short position report and
syncs short_pct into screener.universe.
Runs after market close (ASIC publishes reports ~6pm AEST).
"""
import logging

from sqlalchemy import text

from app.db.session import AsyncSessionLocal

log = logging.getLogger(__name__)


async def run_short_positions() -> None:
    try:
        from compute.engine.short_positions import run
        await run()
        log.info("ASIC short positions ingested")
    except Exception as exc:
        log.error("Short positions worker error: %s", exc, exc_info=True)
    finally:
        # Always record execution time so Pipeline Monitor shows true last-run
        try:
            async with AsyncSessionLocal() as db:
                await db.execute(text("""
                    INSERT INTO meta.job_heartbeat (job_id, last_run_at, run_count)
                    VALUES ('short_positions', NOW(), 1)
                    ON CONFLICT (job_id) DO UPDATE SET
                        last_run_at = NOW(),
                        run_count   = meta.job_heartbeat.run_count + 1
                """))
                await db.commit()
        except Exception as hb_err:
            log.debug(f"Heartbeat write failed: {hb_err}")
