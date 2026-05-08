"""
ASIC Short Positions Worker
============================
Daily scheduler job — downloads latest ASIC short position report and
syncs short_pct into screener.universe.
Runs after market close (ASIC publishes reports ~6pm AEST).
"""
import logging

log = logging.getLogger(__name__)


async def run_short_positions() -> None:
    try:
        from compute.engine.short_positions import run
        await run()
        log.info("ASIC short positions ingested")
    except Exception as exc:
        log.error("Short positions worker error: %s", exc, exc_info=True)
