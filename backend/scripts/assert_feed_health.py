#!/usr/bin/env python
"""
Assert the dividend feed is healthy, or fail the job
====================================================
A scheduled producer's transaction committing is not successful output. The
weekly pipeline can load every raw file and transform every staging row
without error and still leave a feed nobody should compute over -- that is
precisely what happened between May and September 2026, except that nothing
was running at all.

This is the step that turns "the transform exited 0" into "the feed is
usable", and it fails the job when those differ.

It calls ``fetch_feed_health`` -- the same implementation the factor engine
uses to decide whether to withhold the Income factor. The 35-day threshold and
the 20-row / 20-issuer floor are deliberately NOT reproduced here. An
operational definition of "healthy" that lives beside the financial one drifts
from it, and the drift is silent: the scheduler would report success while the
engine withheld every dividend metric, and neither would be wrong by its own
lights.

Structured evidence is printed whether it passes or fails, so the next feed
decay is diagnosable from the job log rather than from a forensic session.

Usage:
    python scripts/assert_feed_health.py
    python scripts/assert_feed_health.py --warn-only
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import psycopg2  # noqa: E402

from app.core.db import get_database_url_sync  # noqa: E402
# Imported from dividends, not daily_compute. Same function either way -- the
# latter re-exports it -- but importing it from the module that owns the
# concept means this script needs none of the compute engine, and works
# unchanged on a branch where that engine differs.
from compute.engine.dividends import (  # noqa: E402
    FEED_STALENESS_DAYS, MIN_RECENT_ISSUERS, MIN_RECENT_ROWS,
    fetch_feed_health,
)

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s  %(levelname)-8s %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("feed-health")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--warn-only", action="store_true",
                        help="Report and exit 0 even when unhealthy. For "
                             "inspection; a scheduled job must not use it.")
    args = parser.parse_args()

    conn = psycopg2.connect(get_database_url_sync())
    cur = conn.cursor()

    cur.execute("SELECT current_database()")
    database = cur.fetchone()[0]

    health = fetch_feed_health(cur)

    # The table's own shape, beside the classifier's verdict. Two numbers the
    # classifier does not use -- total rows and total issuers -- because a feed
    # can be current at the margin while the history behind it has been
    # replaced by something smaller, and the trailing window cannot see that.
    cur.execute("""
        SELECT count(*), count(DISTINCT asx_code),
               count(*) FILTER (WHERE ex_date > CURRENT_DATE)
          FROM market.dividends;""")
    total_rows, total_issuers, future = cur.fetchone()

    log.info("database            : %s", database)
    log.info("thresholds          : %s days, %s rows, %s issuers",
             FEED_STALENESS_DAYS, MIN_RECENT_ROWS, MIN_RECENT_ISSUERS)
    log.info("latest occurred ex  : %s (lag %s days)",
             health.latest_ex_date, health.lag_days)
    log.info("recent rows         : %s", health.recent_rows)
    log.info("recent issuers      : %s", health.recent_issuers)
    log.info("future announced    : %s", future)
    log.info("table total         : %s rows / %s issuers",
             f"{total_rows:,}", f"{total_issuers:,}")

    cur.close()
    conn.close()

    if health.healthy:
        log.info("FEED HEALTHY")
        return 0

    log.error("FEED UNHEALTHY: %s", health.failure)
    log.error("%s", health.reason)
    if args.warn_only:
        log.warning("--warn-only: exiting 0 despite the failure above.")
        return 0

    # Deliberately no rollback. A newly loaded table can be materially better
    # than what it replaced even when this assertion fails -- the September
    # 2026 repair grew the table 56% while the classifier of the day would
    # have called the result healthy for the wrong reason. Restoring
    # automatically would discard a genuine improvement on the word of a
    # validator that might itself be the defect. Fail loudly, keep the
    # evidence, and let an operator decide after looking.
    log.error("The loaded data is retained. Rollback is an operator decision "
              "after inspection, not an automatic response to this check.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
