"""
Top 5 Strategy Worker
=====================
Monthly scheduler job — runs on the 2nd of each month at 8pm AEST,
after the universe build and composite scores are up to date.
Delegates to compute.engine.top5_strategy.run().
"""
import logging
from datetime import date

log = logging.getLogger(__name__)


async def run_top5_strategy() -> None:
    try:
        from compute.engine.top5_strategy import run
        pick_month = date.today().replace(day=1)
        await run(pick_month=pick_month, force=False, dry_run=False)
        log.info("Top 5 strategy picks computed for %s", pick_month)
    except Exception as exc:
        log.error("Top 5 strategy worker error: %s", exc, exc_info=True)
