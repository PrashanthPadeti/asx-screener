"""
Capital Raise Scanner Worker
Scans recent ASX announcements for capital raise keywords daily at 7:30am AEST.
"""
import logging

log = logging.getLogger(__name__)


async def scan_capital_raises() -> None:
    try:
        from compute.engine.capital_raise_tracker import run
        await run(dry_run=False, days=3)
    except Exception as exc:
        log.error("capital_raise_worker failed: %s", exc, exc_info=True)
