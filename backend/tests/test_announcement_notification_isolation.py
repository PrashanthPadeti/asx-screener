#!/usr/bin/env python
"""
One subscriber's failure must not silence the rest
==================================================
`_notify_subscribers` called `send_announcement_notification` unguarded.
The first subscriber whose notification raised aborted the whole function:
every later subscriber for that announcement, and every later announcement,
was skipped in silence.

That is not hypothetical. It is what the `:meta::jsonb` defect did for
months. The email is sent BEFORE it is logged, so the first subscriber
received their announcement, `_log_notification` then raised on the
malformed SQL, and nobody after that first person heard about the filing.
Fixing the SQL removed the trigger; it did not remove the fragility, and
the next bad address or SMTP timeout would do the same thing.

Two properties, both exercised rather than asserted about the source:

    isolation   a failing subscriber is skipped, the next one still sends
    recovery    the transaction is cleared before the next attempt

The second is the one that makes the first true. `_log_notification` does
not commit -- the caller does -- so a failed statement leaves the
transaction ABORTED and every subsequent `db.execute` in it fails with
InFailedSqlTransaction. A `try/except` that catches and continues without
rolling back would LOOK like isolation while quietly failing everyone
downstream. The fake database here models that: once a statement fails it
refuses further work until `rollback()` is called, so a fix missing the
rollback fails this test instead of passing it.

Run:  python tests/test_announcement_notification_isolation.py
      (requires the app's dependencies: /opt/asx-screener/asx-venv/bin/python)
"""

import asyncio
import os
import sys
from pathlib import Path
from types import SimpleNamespace

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

# Importing the worker constructs Settings, which requires these. This test
# never opens a connection -- the session is a fake passed in by hand -- so
# it supplies its own placeholders rather than depending on a deployed .env.
# Without this the suite errors in any checkout that is not a live install,
# including the disposable worktrees the gate and this session use, and the
# failure looks like a defect in the code under test rather than a missing
# file. Existing values are never overwritten, so a real environment wins.
for _key, _placeholder in (
        ("DATABASE_URL",      "postgresql+asyncpg://unused/unused"),
        ("DATABASE_URL_SYNC", "postgresql://unused/unused"),
        ("JWT_SECRET",        "test-only-not-a-secret")):
    os.environ.setdefault(_key, _placeholder)


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class FakeDB:
    """A session that refuses work while its transaction is aborted.

    This is the behaviour that matters: Postgres will not execute anything
    else in a transaction that has already failed.
    """

    def __init__(self, subscribers):
        self.subscribers = subscribers
        self.commits = 0
        self.rollbacks = 0
        self.aborted = False

    async def execute(self, *_a, **_k):
        if self.aborted:
            raise RuntimeError(
                "InFailedSqlTransaction: current transaction is aborted, "
                "commands ignored until end of transaction block")
        return FakeResult(self.subscribers)

    async def commit(self):
        if self.aborted:
            raise RuntimeError("cannot commit an aborted transaction")
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1
        self.aborted = False


def _subscriber(n: int):
    return SimpleNamespace(
        user_id=f"user-{n}", email=f"u{n}@example.com", name=f"User {n}",
        company_name="Example Ltd", announcements_email=True,
        announcements_sms=False, phone_number=None)


ANNOUNCEMENT = [{"asx_code": "NXT", "title": "Trading halt",
                 "doc_type": "General", "url": "https://example.com/a"}]


def _run(subscribers, failing_users):
    """Drive _notify_subscribers with a stubbed sender.

    `failing_users` are the user_ids whose send raises -- and, like the real
    defect, the failure aborts the database transaction.
    """
    from app.services import notification_service
    from app.workers import announcement_worker

    db = FakeDB(subscribers)
    calls = []

    async def fake_send(**kwargs):
        uid = kwargs["user_id"]
        calls.append(uid)
        if uid in failing_users:
            db.aborted = True          # what a real failed statement does
            raise RuntimeError(f"simulated failure for {uid}")

    original = notification_service.send_announcement_notification
    notification_service.send_announcement_notification = fake_send
    try:
        error = None
        try:
            asyncio.run(announcement_worker._notify_subscribers(
                db, ANNOUNCEMENT))
        except Exception as exc:                               # noqa: BLE001
            error = exc
        return db, calls, error
    finally:
        notification_service.send_announcement_notification = original


def test_a_failing_subscriber_does_not_stop_the_others():
    subs = [_subscriber(1), _subscriber(2), _subscriber(3)]
    db, calls, error = _run(subs, failing_users={"user-2"})

    assert error is None, f"a single failure raised out of the loop: {error!r}"
    assert calls == ["user-1", "user-2", "user-3"], (
        f"every subscriber must be attempted; attempted {calls}. Before "
        f"v11.2.31 this stopped at user-2.")
    assert db.commits >= 2, (
        f"only {db.commits} commits — the subscribers who succeeded must "
        f"have their notifications made durable independently")


def test_the_transaction_is_cleared_before_the_next_subscriber():
    """The property that makes isolation real rather than apparent."""
    subs = [_subscriber(1), _subscriber(2), _subscriber(3)]
    db, calls, error = _run(subs, failing_users={"user-1"})

    assert error is None
    assert db.rollbacks >= 1, (
        "no rollback after a failed notification; the transaction stays "
        "aborted and every later subscriber fails on a dead session — "
        "isolation in appearance only")
    assert "user-3" in calls, (
        "the last subscriber was never reached, which is what happens when "
        "the aborted transaction is not cleared")
    assert not db.aborted, "the session was left in an aborted state"


def test_total_failure_is_reported_as_a_failure():
    """Partial failure is logged; nothing delivered is systemic and must
    reach telemetry, not sit in a log line."""
    subs = [_subscriber(1), _subscriber(2)]
    db, calls, error = _run(subs, failing_users={"user-1", "user-2"})

    assert isinstance(error, RuntimeError), (
        f"every notification failed and the job reported success: {error!r}")
    assert "every announcement notification failed" in str(error)
    assert len(calls) == 2, "all subscribers must still be attempted"


def test_no_subscribers_is_not_a_failure():
    """An announcement nobody watches is a normal outcome, not an error."""
    db, calls, error = _run([], failing_users=set())
    assert error is None, f"an empty subscriber list raised: {error!r}"
    assert calls == []


if __name__ == "__main__":
    failures = []
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  PASS  {name}")
            except AssertionError as exc:
                print(f"  FAIL  {name}\n        {exc}")
                failures.append(name)
            except Exception as exc:                           # noqa: BLE001
                print(f"  ERROR {name}: {type(exc).__name__}: {exc}")
                failures.append(name)
    total = len([n for n in globals() if n.startswith("test_")])
    print(f"\n{total - len(failures)}/{total} passed")
    sys.exit(1 if failures else 0)
