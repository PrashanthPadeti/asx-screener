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
import asyncio
from contextlib import asynccontextmanager, contextmanager

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


#: An auxiliary writer waits briefly, then defers to the next cycle.
#:
#: These are not the canonical run and must never block it. asx_indices,
#: short_positions and pros_cons write non-governed columns of
#: screener.universe on their own schedules; if a canonical execution holds
#: the table, the correct behaviour is to skip this cycle and say so, not to
#: queue for ninety minutes or to write alongside it.
AUXILIARY_WAIT_SECONDS = 5 * 60

#: Set by a wrapper on the environment of the suffix steps it launches while
#: holding the lease. Those steps must NOT take a second one: advisory locks
#: are per-session, so a child would block on its own parent's lock.
LEASE_HELD_ENV = "ASX_CANONICAL_LEASE_HELD"


def lease_is_held(conn) -> bool:
    """Is the canonical lease actually held by SOME session right now?

    Asked of pg_locks, which is cluster-wide, so a caller can verify a lease
    another process holds without being able to take it.

    This exists because inheritance was claim-based. A child that found
    ASX_CANONICAL_LEASE_HELD set skipped the lock entirely and trusted the
    variable -- so anyone who exported it, deliberately or by inheriting a
    stale shell, walked straight past the only thing serializing canonical
    mutation. An environment variable is an assertion; this is the evidence
    for it.

    Note what it deliberately does NOT claim: that the lock is held by our
    parent, or by anyone in particular. Advisory locks carry no ownership we
    can attribute across sessions. It establishes that a canonical execution
    is genuinely in flight, which is the thing an inheriting child needs to be
    true, and it fails closed when the claim has nothing behind it.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*) > 0
              FROM pg_locks
             WHERE locktype = 'advisory'
               AND ((classid::bigint << 32) | objid::bigint) = %s
               AND granted
            """,
            (CANONICAL_LEASE_KEY,),
        )
        return bool(cur.fetchone()[0])


@contextmanager
def auxiliary_lease(dsn: str, *, why: str, wait_seconds: int = AUXILIARY_WAIT_SECONDS):
    """Hold the lease on a connection of its own, for an auxiliary writer.

    Yields True when the lease was taken and the caller may write; False when
    a canonical execution holds it and the caller must SKIP.

    A separate connection, deliberately. These writers do their work through
    an AsyncSession, and a session's connection can return to the pool on
    commit — which would either drop a session-scoped advisory lock partway
    through, or hand a still-locked connection to an unrelated caller. The
    lock's lifetime has to be something we control, so it gets its own
    connection and nothing else uses it.

    Never raises on contention. An auxiliary writer that crashes because the
    canonical run is busy converts a deferral into a failed job, and the next
    person to see that alert learns to ignore it.
    """
    import os

    # Already inside a wrapper's lease? Then do not take a second one.
    #
    # pros_cons is a POST_PUBLICATION_WRITER in the weekly suffix, which the
    # wrapper runs while holding the lease on its own connection. Advisory
    # locks are per-session, so this subprocess would block on a lock its own
    # parent holds, wait out the timeout, and defer — every single week,
    # quietly, while every log line said the pipeline succeeded.
    #
    # The wrapper sets this for the suffix it launches. It is an inheritance
    # marker, not a bypass: the lease IS held, by the process that started
    # this one.
    if os.getenv(LEASE_HELD_ENV, "").strip():
        log.info("%s: running inside the caller's canonical lease", why)
        yield True
        return

    import psycopg2

    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    acquired = False
    try:
        deadline = time.monotonic() + max(0, wait_seconds)
        while True:
            acquired = try_acquire(conn)
            if acquired or time.monotonic() >= deadline:
                break
            time.sleep(_POLL_SECONDS)

        if not acquired:
            log.warning(
                "%s: canonical execution holds the lease (%s) — skipping this "
                "cycle rather than writing alongside it. screener.universe "
                "keeps whatever the canonical run publishes; this job's own "
                "columns are simply not refreshed until next time.",
                why, holder(conn) or "unidentified holder")
        yield acquired
    finally:
        if acquired:
            release(conn)
        conn.close()



@asynccontextmanager
async def auxiliary_lease_async(dsn: str, *, why: str,
                                wait_seconds: int = AUXILIARY_WAIT_SECONDS):
    """auxiliary_lease, for a caller running on an event loop.

    The synchronous version polls with time.sleep for up to
    AUXILIARY_WAIT_SECONDS -- five minutes -- while waiting for a canonical
    execution to finish. Three scheduled jobs entered it from `async def run`:
    asx_indices, short_positions and top5_strategy. AsyncIOScheduler runs
    coroutines ON the event loop, so each of those could stop the API
    answering anything for the whole wait.

    short_positions fires at 20:05 AEDT = 09:05 UTC, inside the window the
    08:30 UTC canonical run holds the lease. That is a five-minute outage on
    an ordinary weekday, by design, with nothing anomalous happening.

    Identical semantics, deliberately: this wraps the existing context manager
    rather than reimplementing the protocol. Acquisition and release -- the
    only blocking parts -- happen on a worker thread; everything about
    locking, contention, logging and the skip-rather-than-fail behaviour is
    the same code as before.
    """
    manager = auxiliary_lease(dsn, why=why, wait_seconds=wait_seconds)
    permitted = await asyncio.to_thread(manager.__enter__)
    try:
        yield permitted
    finally:
        await asyncio.to_thread(manager.__exit__, None, None, None)

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
