"""
Exactly one process may hold the schedulers
===========================================
The API and the worker both call `register_jobs`. They have to: two lists
would drift, and the drift reads as a job running twice or not at all. But
that means both processes are *capable* of running every job, and if both
ever do, every scheduled effect happens twice -- two alert emails to the same
customer, two writes racing into screener.universe, two announcement fetches
inserting the same filings.

A configuration flag is not enough to prevent that. SCHEDULERS_ENABLED=false
on the API is a DECLARATION; it is true only while the file says so and
somebody remembers to restart. A restored .env, a fresh host, a rollback, an
ordering mistake during cutover -- each one silently gives you two owners,
and the symptom (duplicate emails) surfaces far from the cause.

So ownership is ENFORCED, by the database, at the moment of acquisition:

    pg_try_advisory_lock(SCHEDULER_OWNER_KEY)

Session-scoped, so it is held exactly as long as the connection is open and
released automatically if the process dies -- no stale lock to clear by hand
after a crash, which is the failure mode of a lease stored in a table.

The same mechanism as compute/engine/canonical_lease.py, deliberately: that
one serialises canonical EXECUTIONS, this one arbitrates scheduler
OWNERSHIP. Different keys, same protocol, so there is one thing to understand
rather than two.

Whoever acquires it runs the jobs. Whoever does not, does not -- and says so,
naming the holder, because "I am not the owner" is only useful if you can
find out who is.
"""

import logging
import os
import socket

import psycopg2

logger = logging.getLogger(__name__)

#: Distinct from CANONICAL_LEASE_KEY (8_090_141_026). A shared key would make
#: a canonical run and a scheduler start contend for the same lock, and the
#: scheduler would silently fail to own itself for the duration of a pipeline.
SCHEDULER_OWNER_KEY = 8_090_251_045


class SchedulerOwner:
    """Holds scheduler ownership for the lifetime of this process.

    The connection is deliberately NOT taken from the application's pool. A
    pooled connection can be recycled, returned, or closed underneath you,
    and a session-scoped advisory lock dies with its session -- ownership
    would be dropped at a moment nothing is watching, leaving the jobs
    registered and the lock free for a second process to take.
    """

    def __init__(self, dsn: str, role: str):
        self._dsn = dsn
        self._role = role
        self._conn = None
        self.acquired = False

    def try_acquire(self) -> bool:
        """True if this process now owns the schedulers.

        A failure to CONNECT is not reported as "someone else owns it".
        Those are different facts: one means another process is running the
        jobs, the other means we cannot tell. The caller must not register
        jobs in either case, but the log has to distinguish them or the next
        person debugging a silent scheduler looks in the wrong place.
        """
        try:
            self._conn = psycopg2.connect(
                self._dsn,
                application_name=f"asx-scheduler-owner/{self._role}"
                                 f"@{socket.gethostname()}:{os.getpid()}",
            )
            self._conn.autocommit = True
        except Exception as exc:                               # noqa: BLE001
            logger.error(
                "scheduler ownership UNDETERMINED — could not reach the "
                "database to arbitrate it (%s: %s). No jobs will be "
                "registered by this process, because running them without "
                "establishing ownership risks every scheduled effect "
                "happening twice.",
                type(exc).__name__, exc)
            self._conn = None
            self.acquired = False
            return False

        with self._conn.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_lock(%s)",
                        (SCHEDULER_OWNER_KEY,))
            self.acquired = bool(cur.fetchone()[0])

        if not self.acquired:
            held_by = self.holder() or "an unidentified session"
            logger.warning(
                "scheduler ownership DECLINED — held by %s. This process "
                "will serve normally and register no background jobs.",
                held_by)
            self._close()
        return self.acquired

    def holder(self) -> str | None:
        """Who holds the lock, for the log. Never raises: this runs on the
        path where something has already gone sideways, and an exception
        here would replace a useful diagnostic with a stack trace."""
        try:
            with self._conn.cursor() as cur:
                cur.execute(
                    "SELECT a.application_name, a.pid, a.backend_start "
                    "FROM pg_locks l JOIN pg_stat_activity a USING (pid) "
                    "WHERE l.locktype = 'advisory' AND l.objid = %s "
                    "AND l.granted LIMIT 1",
                    (SCHEDULER_OWNER_KEY,))
                row = cur.fetchone()
            if not row:
                return None
            return f"{row[0]} (pid {row[1]}, since {row[2]:%Y-%m-%d %H:%M:%S})"
        except Exception:                                      # noqa: BLE001
            return None

    def release(self) -> None:
        """Explicit release on a clean shutdown.

        Not strictly required -- closing the session drops the lock -- but a
        handover that waits on TCP teardown makes a restart look like a
        contended start, and the next process logs DECLINED for no reason.
        """
        if self._conn is not None and self.acquired:
            try:
                with self._conn.cursor() as cur:
                    cur.execute("SELECT pg_advisory_unlock(%s)",
                                (SCHEDULER_OWNER_KEY,))
            except Exception:                                  # noqa: BLE001
                pass
        self.acquired = False
        self._close()

    def _close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            finally:
                self._conn = None
