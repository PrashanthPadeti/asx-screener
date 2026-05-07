"""Nightly commodity prices worker — called by APScheduler."""
import logging
from datetime import date

log = logging.getLogger(__name__)


async def compute_commodities() -> None:
    try:
        from compute.engine.commodities import run
        await run(target_date=date.today(), backfill_days=3)
    except Exception as exc:
        log.error(f"Commodities worker error: {exc}", exc_info=True)
