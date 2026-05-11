"""
Worker wrapper for the ASX companies list sync.
Runs daily at 06:00 AEST — after overnight data but before the universe build.
"""
import logging

log = logging.getLogger(__name__)


async def sync_asx_companies() -> None:
    try:
        from compute.engine.asx_companies import run
        await run(dry_run=False, source="auto")
    except Exception as exc:
        log.error("asx_companies_worker failed: %s", exc, exc_info=True)
