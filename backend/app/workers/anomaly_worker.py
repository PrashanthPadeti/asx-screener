"""
Anomaly Detection Worker
Wraps compute.engine.anomaly_detect for APScheduler.
"""
import logging
from compute.engine.anomaly_detect import run as _run_anomaly
import asyncio

log = logging.getLogger(__name__)


async def run_anomaly_detect() -> None:
    log.info("Anomaly detection starting...")
    try:
        await _run_anomaly(dry_run=False)
        log.info("Anomaly detection complete")
    except Exception as e:
        log.error("Anomaly detection failed: %s", e, exc_info=True)
