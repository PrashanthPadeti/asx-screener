#!/usr/bin/env python3
"""
The worker: scheduled jobs, in their own process
================================================
Layer 4 of the independence work. Until now one uvicorn process both served
customers and ran eighteen background jobs. That couples them in both
directions, and both directions have bitten:

  - a job that blocks the event loop stops the API answering. short_positions
    waiting five minutes on the canonical lease was a five-minute outage on an
    ordinary weekday, by design, with nothing anomalous happening.
  - a deploy restarts the API, which restarts the scheduler, which drops
    whatever was mid-flight.
  - an API that cannot start -- an undeclared .env key, say -- also stops
    every scheduled job, so the data goes stale while the site is down.

Stock screening, the market overview and the company pages are the product.
They should not be able to fail because a mining-metrics job did something
unusual, and the jobs should not stop because the API was restarted.

Same jobs, same declaration
---------------------------
This registers from app/scheduler_registry.py -- the same function the API
calls. Not a copy: a second list would drift, and drift reads as a job
running twice or not at all.

Exactly one owner
-----------------
Both processes CAN register every job, so the system must guarantee that
only one DOES. That guarantee is a PostgreSQL advisory lock, not a
configuration flag: see app/core/scheduler_ownership.py for why a flag is
not enough. This process exits non-zero if it cannot acquire ownership,
which is the honest outcome -- a worker that silently runs nothing looks
identical to a healthy one.

Usage:
    cd /opt/asx-screener/backend && ../asx-venv/bin/python worker.py
"""

import asyncio
import logging
import signal
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("worker")

#: How long a stopping worker waits for in-flight jobs before abandoning
#: them. Must stay comfortably under the unit's TimeoutStopSec (300s), or
#: systemd SIGKILLs the process mid-drain and the bound is meaningless.
DRAIN_SECONDS = 120


async def main() -> int:
    # Settings first, and in this fresh process. If configuration cannot
    # build, that is the whole story and nothing below is worth attempting.
    from app.core.config import settings
    from app.core.instrument import instrument_mode
    from app.core.scheduler_ownership import SchedulerOwner

    if instrument_mode():
        # The same protection the API has. Importing machinery under a
        # diagnostic has twice started real jobs on the production host.
        logger.error(
            "INSTRUMENT MODE is set — refusing to start. This process is a "
            "production execution authority; a diagnostic must not become "
            "one by accident.")
        return 2

    if not settings.SCHEDULERS_ENABLED:
        # The freeze applies to whoever would run the jobs. A worker that
        # ignored it would make the maintenance window meaningless the
        # moment the jobs moved out of the API.
        logger.warning(
            "SCHEDULERS_ENABLED is off — the rollout freeze is in effect. "
            "Registering nothing and exiting cleanly; nothing is computing.")
        return 0

    owner = SchedulerOwner(settings.DATABASE_URL_SYNC, role="worker")
    if not owner.try_acquire():
        logger.error(
            "not starting: another process owns the schedulers. Running the "
            "jobs anyway would double every scheduled effect — two alert "
            "emails per customer, two writes racing into the universe.")
        return 1

    logger.info("scheduler ownership acquired")

    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from app.scheduler_registry import register_jobs

    # Identical job_defaults to the API's. These are not incidental:
    # coalesce with misfire_grace_time is what makes a restart fire the work
    # it missed exactly once instead of not at all or in a catch-up storm.
    scheduler = AsyncIOScheduler(job_defaults={
        "misfire_grace_time": 3600,
        "coalesce": True,
        "max_instances": 1,
    })
    register_jobs(scheduler, settings, logger)
    scheduler.start()

    # What the scheduler HOLDS, not what was asked for. A registration that
    # silently failed cannot report success through this line.
    live = sorted(j.id for j in scheduler.get_jobs())
    logger.info("worker running — %d jobs: %s", len(live), ", ".join(live))

    stopping = asyncio.Event()

    def _stop(signum, _frame):
        logger.info("signal %s — shutting down", signal.Signals(signum).name)
        stopping.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, _stop)

    try:
        await stopping.wait()
    finally:
        # shutdown(wait=False), then drain in-flight jobs ourselves.
        #
        # wait=True DEADLOCKS here, and did: AsyncIOScheduler runs jobs as
        # coroutines on THIS event loop, and shutdown(wait=True) blocks the
        # loop waiting for them to finish -- so the jobs it is waiting for
        # cannot run. Measured on 25 Oct 2026: SIGTERM at 21:12:33, process
        # still alive at 21:27:09, released only when the scheduler's next
        # wakeup timer happened to fire 15 minutes later. Under systemd that
        # is a five-minute hang on every worker restart followed by SIGKILL
        # in the middle of whatever was running.
        #
        # wait=False stops new runs being scheduled immediately and returns.
        # The in-flight coroutines are ordinary tasks on this loop, so they
        # are drained by awaiting them -- which lets the loop keep turning,
        # which is the whole difference.
        scheduler.shutdown(wait=False)

        pending = [t for t in asyncio.all_tasks()
                   if t is not asyncio.current_task() and not t.done()]
        if pending:
            logger.info("draining %d in-flight job(s), up to %ds",
                        len(pending), DRAIN_SECONDS)
            done, still_running = await asyncio.wait(
                pending, timeout=DRAIN_SECONDS)
            if still_running:
                # Named, not silently abandoned. A job cut off mid-write is
                # something the next person needs to know happened.
                logger.warning(
                    "%d job(s) did not finish within %ds and are being "
                    "abandoned: %s", len(still_running), DRAIN_SECONDS,
                    ", ".join(sorted(t.get_name() for t in still_running)))

        owner.release()
        logger.info("worker stopped, ownership released")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
