"""
Mining & REIT Metrics Sync Worker
Syncs mining and REIT sector metrics weekly on Sunday at 7:00am AEST.
"""
import logging
import asyncio

log = logging.getLogger(__name__)


async def sync_mining_reit_metrics() -> None:
    try:
        from compute.engine.mining_metrics import run as run_mining
        from compute.engine.reit_metrics import run as run_reit
        log.info("Mining metrics sync starting...")
        await run_mining(dry_run=False)
        log.info("Mining metrics sync complete. Starting REIT metrics sync...")
        await run_reit(dry_run=False)
        log.info("REIT metrics sync complete.")
    except Exception as exc:
        log.error("mining_reit_worker failed: %s", exc, exc_info=True)
