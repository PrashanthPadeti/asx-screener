"""
ASIC Short Positions Worker
============================
Daily scheduler job — runs at 8:05pm AEST (after pipeline finishes ~7:30-7:40pm).
Downloads latest ASIC short position report and syncs short_pct into screener.universe.

No pipeline dependency gate — short position data is independent of the daily
pipeline (ASIC publishes with a 2-3 day lag anyway).  Runs as a safety-net
refresh in case the pipeline's optional steps 2/4/6 were skipped or failed.
"""
import logging

from sqlalchemy import text
from app.db.session import AsyncSessionLocal
from app.workers.pipeline_tracker import track_scheduler_job

log = logging.getLogger(__name__)


async def run_short_positions() -> None:
    async with track_scheduler_job(
        "short_positions",
        "ASIC Short Positions",
        skip_if_pipeline_failed=False,  # independent of pipeline — always run
    ):
        from compute.engine.short_positions import run
        await run()
        log.info("ASIC short positions ingested")

    # ── Heartbeat ─────────────────────────────────────────────────────────────
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
