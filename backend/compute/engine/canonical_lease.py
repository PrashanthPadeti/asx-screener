"""
Only one canonical-affecting execution at a time
================================================
Rule 3 of `docs/canonical_orchestration.md`.

    Only one canonical-affecting execution may be in flight at once.

A PostgreSQL session-scoped advisory lock. It is NOT the fix for the blank
screener — that is the missing canonical tail — and it must never influence
plan selection. It does one thing: canonical producers write shared mutable
tables rather than run-private copies, so two genuinely overlapping executions
can interleave their writes before either universe is built.

The overlap is not hypothetical. `short_positions` fires at 20:05 AEST, which
is 10:05 UTC, inside the window a daily canonical run starting at 08:30 UTC is
still computing; `asx_indices` fires at 17:50 AEST. The publication-time
fingerprint recheck catches some versions of that race. Serialization is
cheaper and clearer than relying on a late detector.

Who holds it
------------
The WRAPPER, not the driver.

Releasing at finalisation leaves a race: run A finalises, the lease drops, A's
suffix starts reading `screener.universe`, run B acquires and its provisional
rebuild revokes attribution underneath — so A's suffix observes B's
provisional state rather than A's published one. The lease therefore spans
admission through every suffix consumer that reads mutable live canonical
state. Since the wrapper runs the suffix, the wrapper owns the lock.

Session-scoped, so a crashed holder releases automatically when PostgreSQL
closes the connection. Whatever state the lifecycle reached is then governed
by the ordinary fail-closed rules — an abandoned lock would be worse than the
race it prevents.
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager

log = logging.getLogger(__name__)

#: One fixed key for "a canonical-affecting execution". Arbitrary but stable:
#: chosen once, never derived from a name that someone might later reformat.
#: Two callers computing it differently would each hold "the" lease and
#: neither would be wrong about it.
CANONICAL_LEASE_KEY = 8_090_141_026

#: Scheduled runs wait; the previous finalised output keeps serving meanwhile.
#: Long enough to let the ~hour-long FULL path finish ahead of a daily run
#: (production measured 57 minutes on 23 Sep), short enough that an ordinary
#: overlap does not become a missed trading-day publication. An operational
#: parameter — change the number on measured evidence, not the semantics.
SCHEDULED_WAIT_SECONDS = 90 * 60

#: Manual runs fail fast by default, so an unnoticed hand-started backfill
#: cannot queue behind — or ahead of — the scheduled job.
MANUAL_WAIT_SECONDS = 0

_POLL_SECONDS = 5


class LeaseUnavailable(RuntimeError):
    """Another canonical-affecting execution holds the lease."""


def try_acquire(conn) -> bool:
    """One non-blocking attempt. True if this session now holds the lease."""
    with conn.cursor() as cur:
        cur.execute("SELECT pg_try_advisory_lock(%s)", (CANONICAL_LEASE_KEY,))
        return bool(cur.fetchone()[0])


def release(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT pg_advisory_unlock(%s)", (CANONICAL_LEASE_KEY,))


def holder(conn) -> dict | None:
    """Who holds it, for a refusal message worth reading.

    "The lease is taken" sends an operator hunting. "PID 12345, running
    p0a_canonical_run.py since 08:31" does not.
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT a.pid, a.application_name, a.query_start, left(a.query, 120)
              FROM pg_locks l
              JOIN pg_stat_activity a ON a.pid = l.pid
             WHERE l.locktype = 'advisory'
               AND l.objid = %s::bigint %% 2147483648
               AND l.granted
             LIMIT 1""", (CANONICAL_LEASE_KEY,))
        row = cur.fetchone()
    if not row:
        return None
    return {"pid": row[0], "application": row[1], "since": row[2],
            "query": row[3]}


@contextmanager
def canonical_lease(conn, *, wait_seconds: int, why: str):
    """Hold the canonical execution lease for the duration of the block.

    `wait_seconds=0` fails fast. Anything larger polls until the deadline,
    which is the scheduled behaviour: the previously finalised output keeps
    serving while we wait, so waiting costs freshness rather than correctness.

    IMPORTANT: every plan admission check — including the yearly fingerprint —
    must be evaluated AFTER this returns, never before the wait. A fingerprint
    proved before a ninety-minute wait proves nothing about the state the run
    will compute against.
    """
    deadline = time.monotonic() + max(0, wait_seconds)
    attempts = 0
    while True:
        if try_acquire(conn):
            break
        attempts += 1
        if time.monotonic() >= deadline:
            current = holder(conn)
            raise LeaseUnavailable(
                f"canonical execution lease held by "
                f"{current or 'an unidentified session'}; {why} waited "
                f"{wait_seconds}s and is refusing rather than running "
                f"alongside it. Nothing was created and no canonical table "
                f"was touched.")
        if attempts == 1:
            log.warning("canonical lease busy (%s); waiting up to %ds",
                        holder(conn) or "unidentified holder", wait_seconds)
        time.sleep(_POLL_SECONDS)

    log.info("canonical execution lease acquired by %s", why)
    try:
        yield
    finally:
        release(conn)
        log.info("canonical execution lease released by %s", why)
