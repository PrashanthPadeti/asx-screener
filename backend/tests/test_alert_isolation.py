"""
Outbound anomaly alerts stay closed unless someone opens them
=============================================================
The freeze script's header said the anomaly alert worker was "excluded from
`thaw` deliberately". Its ``thaw()`` restored every scheduler and printed a
reminder asking a human to stop the job before the next 20:35 run.

A comment is not an exclusion. A reminder is not a control. And neither helps
anyone who restarts the service by any other route — a deploy, a reboot, a
``systemctl restart`` during an unrelated incident at 20:34.

This matters because the active anomaly set is known to contain
defect-derived flags until the detector's applicability repair and
re-detection sequence complete: doubled grossed-up yields, off-domain
Piotroski scores. Roughly 222 of them, against users watching flagged stocks.
Until today the only thing stopping those emails was that the worker happened
to crash in its users query. A crash is not a control either.

So the exclusion is executable and checked at two boundaries, because what is
being prevented is an email arriving in a customer's inbox and there is no
undo for that:

    registration   app/main.py does not add the job unless the flag is on
    send           send_anomaly_alerts refuses even if called directly

These guards are textual because the assertion is about configuration that
cannot be imported here — pydantic_settings is a server dependency. The
runtime proof is /health reporting ``anomaly_alerts: false``; this is what
stops the source drifting away from that between deploys.

Run under pytest, or standalone:
    cd /opt/asx-screener/backend && ../asx-venv/bin/python tests/test_alert_isolation.py
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

BACKEND = Path(__file__).resolve().parents[1]
CONFIG = BACKEND / "app" / "core" / "config.py"
MAIN = BACKEND / "app" / "main.py"
WORKER = BACKEND / "app" / "workers" / "anomaly_alert_worker.py"
FREEZE = BACKEND / "scripts" / "p0a_freeze.sh"

FLAG = "ANOMALY_ALERTS_ENABLED"


def _code(path: Path) -> str:
    """Source with comment lines removed — the comments discuss the defect by
    name, and a guard that matches its own explanation is a mistake this repo
    has made more than once."""
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith("--"):
            continue
        out.append(line)
    return "\n".join(out)


def test_the_flag_exists_and_defaults_to_off():
    """Default off is the whole control. A flag that defaults on protects
    nobody who has not already thought about it."""
    src = _code(CONFIG)

    assert re.search(rf"{FLAG}\s*:\s*bool\s*=\s*False", src), (
        f"{FLAG} must be declared in Settings with a default of False")
    assert not re.search(rf"{FLAG}\s*:\s*bool\s*=\s*True", src)


def test_the_job_is_not_registered_unless_the_flag_is_on():
    """The registration boundary. Without this the job comes back with every
    other scheduler on any restart."""
    src = _code(MAIN)

    m = re.search(r"scheduler\.add_job\(\s*send_anomaly_alerts", src)
    assert m, "send_anomaly_alerts registration not found in app/main.py"

    # The guard must be the nearest preceding `if`, not merely somewhere in
    # the file: a flag checked in an unrelated branch would pass a naive
    # substring test while registering the job unconditionally.
    before = src[:m.start()]
    last_if = before.rfind("\n    if ")
    assert last_if != -1, "registration is not inside any guard"
    guard = before[last_if:last_if + 200]
    assert FLAG in guard, (
        f"the nearest enclosing guard does not test {FLAG}; the job would be "
        f"registered on any restart")


def test_the_worker_refuses_when_the_flag_is_off():
    """The send boundary, which does not care how it was invoked — a manual
    run, a REPL, a future scheduler, a test harness pointed at production."""
    src = _code(WORKER)
    body = src.split("async def send_anomaly_alerts")[1].split("\nasync def ")[0]

    assert FLAG in body, (
        "send_anomaly_alerts does not check the flag; a direct call would send")
    assert "return" in body, "the check must return without sending"
    # And the refusal must come before the work, not after it.
    assert body.index(FLAG) < body.index("_run(db)"), (
        "the flag is checked after the send path has already been entered")


def test_the_freeze_script_no_longer_claims_an_exclusion_it_does_not_implement():
    """The original defect was documentation, and documentation that lies
    about a safety control is worse than none: it stops people looking."""
    src = FREEZE.read_text(encoding="utf-8")

    assert "excluded from `thaw` deliberately" not in src, (
        "the header still claims thaw excludes the alert worker; thaw()"
        " restores every scheduler")
    assert FLAG in src, (
        "the freeze script should name the flag that actually governs alerts")


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failures = []
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as e:
            failures.append(name)
            print(f"  FAIL  {name}  - {e}")
        except Exception as e:
            failures.append(name)
            print(f"  ERROR {name}  - {type(e).__name__}: {e}")

    print(f"\n{len(tests) - len(failures)}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
