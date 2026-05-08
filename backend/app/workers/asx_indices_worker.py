"""
ASX Index Constituent Worker
=============================
Daily scheduler job — updates is_asx200/is_asx300 flags in screener.universe.
Runs after the universe build so market caps are fresh.
"""
import logging

log = logging.getLogger(__name__)


async def run_asx_indices() -> None:
    try:
        from compute.engine.asx_indices import run
        await run()
        log.info("ASX index constituent flags updated")
    except Exception as exc:
        log.error("ASX indices worker error: %s", exc, exc_info=True)
