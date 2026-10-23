"""
Company Profile Worker
======================
Daily scheduler job. Refreshes a seventh of the company list each day, so
every company's profile is at most seven days old.

Deliberately NOT a weekly job: fundamentals costs EODHD 10 calls per
request, so one full pass is ~25,890 calls against an ASX share of ~30,000
a day. A weekly burst would take 86% of a day's budget and starve price
ingestion on whichever day it landed.

Scheduled away from the 17:30–17:45 price window for the same reason — a
profile that is a week stale is a cosmetic problem; prices that did not
ingest because the budget was spent are not.
"""
import logging

log = logging.getLogger(__name__)


async def compute_company_profiles():
    """Returns the producer's tally so `instrumented` can record a degraded run.

    A slice that refreshes 365 of 370 due companies is neither a failure nor
    an unqualified success, and dropping the return value here is what left
    that distinction unrecorded for fund_prices until v11.2.23.
    """
    try:
        from compute.engine.company_profile import run
        tally = await run()
        from app.core.cache import cache_delete_pattern
        deleted = await cache_delete_pattern("asx:company:*")
        log.info(f"Cache invalidated: {deleted} asx:company:* keys flushed")
        return tally
    except Exception as exc:
        log.error(f"Company profile worker error: {exc}", exc_info=True)
        raise          # telemetry must observe the failure
