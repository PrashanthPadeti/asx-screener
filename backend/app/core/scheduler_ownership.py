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
            held_by = self.holder()
            logger.warning(
                "scheduler ownership DECLINED — held by %s. This process "
                "will serve normally and register no background jobs.",
                held_by)
            self._close()
        return self.acquired

    def holder(self) -> str:
        """Who holds the lock, for the log.

        Always returns a sentence. Three outcomes, and they are DIFFERENT
        facts that must not collapse into one:

            "<name> (pid N, since ...)"   someone holds it
            "no session holds it"         nobody does
            "could not be determined: X"  the query failed

        The first version returned None for all three and the caller printed
        "an unidentified session" over every one. On 25 Oct 2026 that is
        exactly what happened, and it read as a permissions problem when the
        real cause was a wrong predicate. A diagnostic that cannot
        distinguish "nobody" from "I could not look" sends the next person
        to the wrong place -- the same cannot-exist versus failed-to-obtain
        distinction this codebase keeps having to relearn.

        A 64-bit advisory key is stored SPLIT across two 32-bit columns:
        classid holds the high half, objid the low half, and objsubid is 1
        for the bigint form (2 for the two-int form, which is a different
        lock space entirely). Matching on objid alone compares against the
        low half and silently finds nothing:

            8090251045  ->  classid 1, objid 3795283749
        """
        try:
            with self._conn.cursor() as cur:
                cur.execute(
                    "SELECT a.application_name, a.pid, a.backend_start "
                    "FROM pg_locks l JOIN pg_stat_activity a USING (pid) "
                    "WHERE l.locktype = 'advisory' "
                    # pg_locks is CLUSTER-wide; advisory locks are acquired
                    # per DATABASE. Without this the query matches the same
                    # key held in another database and LIMIT 1 returns a
                    # session that has nothing to do with this one.
                    #
                    # Caught on 25 Oct 2026 the first time this suite
                    # actually ran: a test holding the lock in an isolated
                    # probe database was told the holder was the production
                    # API. In production it had been right by luck, because
                    # only one database held the key.
                    "  AND l.database = (SELECT oid FROM pg_database "
                    "                    WHERE datname = current_database()) "
                    "  AND l.objsubid = 1 "
                    "  AND l.classid::bigint * 4294967296 "
                    "      + l.objid::bigint = %s "
                    "  AND l.granted "
                    "LIMIT 1",
                    (SCHEDULER_OWNER_KEY,))
                row = cur.fetchone()
        except Exception as exc:                               # noqa: BLE001
            return f"could not be determined: {type(exc).__name__}: {exc}"

        if not row:
            return "no session holds it"

        name = row[0] or "<no application_name>"
        since = f"{row[2]:%Y-%m-%d %H:%M:%S}" if row[2] else "unknown"
        return f"{name} (pid {row[1]}, since {since})"

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
