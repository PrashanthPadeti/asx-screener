"""
Anomaly Detection Worker
========================
Daily scheduler job — runs at 8:20pm AEST (after market snapshot at 7:50pm).
Wraps compute.engine.anomaly_detect for APScheduler.

Dependency gate: skips execution if the daily pipeline did not complete
successfully today (anomaly detection reads mover_snapshots and screener.universe
which are only valid after a successful pipeline run).
"""
import logging

from app.workers.pipeline_tracker import track_scheduler_job

log = logging.getLogger(__name__)


async def run_anomaly_detect() -> None:
    async with track_scheduler_job(
        "anomaly_detect",
        "Anomaly Detection",
        skip_if_pipeline_failed=False,   # gate: needs valid snapshot + universe
    ) as job:
        if job.skipped:
            return   # pipeline gate fired — nothing to do

        log.info("Anomaly detection starting...")
        from compute.engine.anomaly_detect import run as _run_anomaly
        await _run_anomaly(dry_run=False)
        log.info("Anomaly detection complete")
