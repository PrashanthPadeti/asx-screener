"""
AlphaFive Strategy Worker
==========================
Weekly scheduler job — runs every Monday at 8am AEST,
after the weekly pipeline (fundamentals + universe rebuild) completes.
Delegates to compute.engine.top5_strategy.run().
"""
import logging
from datetime import date, timedelta

log = logging.getLogger(__name__)


def _monday_of_week(d: date) -> date:
    """Return the Monday of the week containing d."""
    return d - timedelta(days=d.weekday())


async def run_top5_strategy() -> None:
    try:
        from compute.engine.top5_strategy import run
        pick_week = _monday_of_week(date.today())
        await run(pick_month=pick_week, force=False, dry_run=False)
        log.info("AlphaFive picks computed for week of %s", pick_week)
    except Exception as exc:
        log.error("AlphaFive strategy worker error: %s", exc, exc_info=True)
