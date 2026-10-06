#!/usr/bin/env python
"""
An alert reports a crossing, not a state
========================================
One user received 52 identical emails on 1 Oct 2026 and 29 more on 2 Oct, each
saying CBA had fallen below $150. The price had fallen once. The alert worker
asked "is CBA below $150?" every fifteen minutes and sent an email every time
the answer was yes, for fourteen hours.

    CBA  price_below  150.0000  every_time  trigger_count 81
    1 Oct   52 fires   09:43:50 -> 23:57:44
    2 Oct   29 fires   00:12:44 -> 07:28:05

Nothing was broken. `repeat_mode = 'every_time'` was explicitly exempted from
the 23-hour throttle, so it fired on every evaluation. The code did what it
said; what it said was wrong. "Tell me when CBA falls below $150" is a question
about a transition, and the answer is one email.

`decide` is pure so this is a behavioural test of the state machine rather
than an inspection of the code that implements it.

Run:  python tests/test_alerts_fire_on_crossing.py
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

# Imported directly: the module pulls in SQLAlchemy and the notification
# service at import time, neither of which this test needs.
import importlib.util                                           # noqa: E402
import types                                                    # noqa: E402

for name in ("sqlalchemy", "sqlalchemy.ext", "sqlalchemy.ext.asyncio",
             "app.db", "app.db.session", "app.services",
             "app.services.notification_service"):
    if name not in sys.modules:
        module = types.ModuleType(name)
        sys.modules[name] = module
sys.modules["sqlalchemy"].text = lambda q: q
sys.modules["sqlalchemy.ext.asyncio"].AsyncSession = object
sys.modules["app.db.session"].AsyncSessionLocal = object
sys.modules["app.services.notification_service"].send_alert_notification = None

_spec = importlib.util.spec_from_file_location(
    "_alert_worker", BACKEND / "app" / "workers" / "alert_worker.py")
AW = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(AW)

NOW = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)
LONG_AGO = NOW - timedelta(days=9)
RECENT = NOW - timedelta(hours=2)


def test_a_crossing_fires_once():
    assert AW.decide(met=True, was_met=False,
                     last_triggered_at=None, now=NOW) == "FIRE"


def test_the_same_state_does_not_fire_again():
    """The defect, as a test.

    Fifteen minutes later the price has not moved. The condition is still met.
    That is not a new event, and it must not produce a second email -- 52 of
    which is what the old behaviour produced in a single day.
    """
    assert AW.decide(met=True, was_met=True,
                     last_triggered_at=RECENT, now=NOW) == "SUPPRESS_EDGE"


def test_it_rearms_when_the_condition_goes_false():
    assert AW.decide(met=False, was_met=True,
                     last_triggered_at=RECENT, now=NOW) == "REARM"


def test_a_second_crossing_after_the_cap_fires():
    """Recovered, then fell again, a week later. That is a real new event."""
    assert AW.decide(met=True, was_met=False,
                     last_triggered_at=LONG_AGO, now=NOW) == "FIRE"


def test_a_second_crossing_within_the_cap_is_held():
    """Genuinely crossed again today, but one was already delivered.

    Distinct from SUPPRESS_EDGE: this IS a new crossing, and the caller still
    records it. Only the delivery is withheld.
    """
    assert AW.decide(met=True, was_met=False,
                     last_triggered_at=RECENT, now=NOW) == "SUPPRESS_CAP"


def test_quiet_alerts_stay_quiet():
    assert AW.decide(met=False, was_met=False,
                     last_triggered_at=None, now=NOW) == "IDLE"


def test_the_cap_boundary_is_not_off_by_one():
    just_inside = NOW - timedelta(hours=22, minutes=59)
    just_outside = NOW - timedelta(hours=23, minutes=1)
    assert AW.decide(True, False, just_inside, NOW) == "SUPPRESS_CAP"
    assert AW.decide(True, False, just_outside, NOW) == "FIRE"


def test_the_old_behaviour_would_fail_this_suite():
    """Mutation control.

    The previous rule was: fire whenever the condition is met. If `decide`
    ever returns FIRE for an already-met condition, the 52-emails-a-day defect
    is back.
    """
    level_triggered = lambda met, was_met, last, now: "FIRE" if met else "IDLE"
    assert level_triggered(True, True, RECENT, NOW) == "FIRE", (
        "the counterexample no longer reproduces the old behaviour")
    assert AW.decide(True, True, RECENT, NOW) != "FIRE"


def test_the_state_is_durable_before_the_email_is_sent():
    """An email cannot be un-sent, so what suppresses the next one must commit
    first.

    The old worker sent every notification inside one transaction and
    committed after the loop. A single failing send rolled back the throttle
    for every alert already processed -- whose emails had gone out. The next
    cycle sent them all again.

    Checked on the source because the ordering is the property, and it is not
    observable from `decide`.
    """
    source = (BACKEND / "app" / "workers" / "alert_worker.py").read_text(
        encoding="utf-8")
    fire_path = source[source.index("INSERT INTO users.alert_triggers"):]
    commit_at = fire_path.index("await db.commit()")
    send_at = fire_path.index("await send_alert_notification")
    assert commit_at < send_at, (
        "the notification is sent before the suppression state is committed; "
        "a later failure re-sends every email in the cycle")


def test_the_query_sees_every_active_alert():
    """Edge-triggering needs to observe alerts that are NOT firing.

    The old query filtered out anything triggered in the last 23 hours. Under
    edge-triggering that would be fatal: an alert whose condition has gone
    false would never be seen, so it would never re-arm, and the next genuine
    crossing would be silent.
    """
    source = (BACKEND / "app" / "workers" / "alert_worker.py").read_text(
        encoding="utf-8")
    where = source[source.index("WHERE a.is_active = TRUE"):
                   source.index("alerts = result.fetchall()")]
    assert "last_triggered_at <" not in where, (
        "the selection still excludes recently-triggered alerts, so they can "
        "never re-arm")
    assert "repeat_mode = 'every_time'" not in where, (
        "the every_time exemption is still in the query -- that exemption is "
        "what sent 52 emails in a day")


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
    total = len([n for n in globals() if n.startswith("test_")])
    print(f"\n{total - len(failures)}/{total} passed")
    sys.exit(1 if failures else 0)
