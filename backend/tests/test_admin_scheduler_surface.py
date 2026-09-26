"""
The admin scheduler surface reports identities, and changes nothing
===================================================================
`/health` has always published a scheduler job COUNT. A count cannot be
reconciled against static intent: twenty declared jobs and twenty live jobs
agree numerically while naming entirely different work. This surface reports
WHICH jobs are registered, so the two can be compared.

Everything here is about the surface itself — auth, read-only, and the shape
of what it returns. Deliberately self-contained: it imports no classifier, so
it can ship and be verified on its own.

The enabled path is NOT exercised in-process. Starting this app with
schedulers enabled would register and start nineteen real jobs on whatever
host the test runs on, which for a diagnostic is precisely the wrong trade —
the same lesson as a release gate that started nineteen APScheduler jobs
while claiming to be read-only. The frozen path is proved here; the enabled
path is proved against the deployed service.

Run under pytest, or standalone:
    cd /opt/asx-screener/backend && ../asx-venv/bin/python tests/test_admin_scheduler_surface.py
"""

import ast
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

ADMIN = BACKEND / "app" / "api" / "v1" / "routes" / "admin.py"
MAIN = BACKEND / "app" / "main.py"


class Skipped(Exception):
    """Reported as SKIPPED. A skipped test that prints PASS is the failure
    mode this codebase keeps meeting."""


def _function(path: Path, name: str) -> str:
    source = path.read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(source)):
        if (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == name):
            return ast.get_source_segment(source, node) or ""
    raise AssertionError(f"{name} not found in {path.name}")


# ── Auth is mandatory ────────────────────────────────────────────────────────

def test_system_health_requires_admin():
    """Job identities name internal work. This endpoint must never become
    reachable without admin auth."""
    assert "Depends(require_admin)" in _function(ADMIN, "system_health")


# ── Read-only ────────────────────────────────────────────────────────────────

def test_the_scheduler_section_mutates_nothing():
    """Asserted, not claimed. It calls get_jobs() and nothing else: no job
    added, removed, paused, resumed or rescheduled, and no row written. A
    diagnostic that can modify what it reports on is not a diagnostic."""
    body = _function(ADMIN, "_scheduler_state")
    for forbidden in ("add_job", "remove_job", "modify_job", "reschedule_job",
                      "remove_all_jobs", "pause", "resume", "shutdown",
                      "INSERT", "UPDATE", "DELETE", "commit", "execute"):
        assert forbidden not in body, f"_scheduler_state contains {forbidden!r}"
    assert "get_jobs()" in body, "it does not actually read the scheduler"


def test_exposing_the_scheduler_does_not_change_registration():
    """The whole point of a bounded change: startup behaviour is untouched.

    app.state.scheduler is published AFTER start(), and the lifespan gains no
    new add/remove call. If this file ever starts registering or removing
    jobs as a side effect of being observable, that is a different change
    than the one that was authorised.
    """
    source = MAIN.read_text(encoding="utf-8")
    assert "app.state.scheduler = scheduler" in source

    lifespan = _function(MAIN, "lifespan")
    assert lifespan.count("remove_all_jobs()") == 1, (
        "the freeze's single remove_all_jobs is no longer single")
    start = lifespan.index("scheduler.start()")
    publish = lifespan.index("app.state.scheduler = scheduler")
    assert start < publish, (
        "the scheduler is published before it starts; an observer could then "
        "see a state the application itself has not reached")


# ── The shape of what it returns ─────────────────────────────────────────────

def test_job_count_is_derived_from_the_identities():
    """So the older count-only instrument on /health cannot disagree with this
    one silently."""
    body = _function(ADMIN, "_scheduler_state")
    assert '"job_count": len(jobs)' in body, (
        "job_count is counted separately from the list it describes")


def test_the_trigger_is_structured_not_a_repr():
    """A repr can change without any semantic change and would then read as
    drift. Cadence is reported as fields on both sides of the comparison."""
    body = _function(ADMIN, "_trigger_shape")
    assert "str(trigger)" not in body and "repr(" not in body
    assert '"interval"' in body and '"cron"' in body
    assert "total_seconds()" in body, "interval cadence is not quantified"


def test_an_absent_scheduler_is_reported_not_guessed():
    """Before the app publishes it — or in any process that never starts the
    lifespan — the honest answer is that it is unavailable, not 'enabled with
    zero jobs', which would read as a healthy frozen scheduler."""
    body = _function(ADMIN, "_scheduler_state")
    assert '"enabled": None' in body, (
        "an unavailable scheduler is reported as a definite state")


# ── Behaviour, frozen only ───────────────────────────────────────────────────

def test_the_frozen_surface_reports_zero_identities():
    """Proved in-process because frozen is safe to run: the lifespan removes
    every job before starting, so nothing registers and nothing fires.

    The freeze is forced by setting `settings.SCHEDULERS_ENABLED` directly,
    NOT by assigning os.environ. The first draft did the latter and passed
    standalone while failing under pytest — because another test imports
    app.main first, Settings reads the environment once at import time, and
    the assignment then arrives too late. `frozen` was False, and this test
    registered and started nineteen real APScheduler jobs on the host it ran
    on. The assertion caught it, but a diagnostic that starts production jobs
    to check whether production jobs are running is the exact trade this
    surface exists to avoid, and import order must not decide it.
    """
    try:
        from fastapi.testclient import TestClient
        from app.core.config import settings
        from app.core.deps import require_admin
        from app.main import app
    except Exception as exc:                                   # noqa: BLE001
        raise Skipped(f"needs the API stack: {type(exc).__name__}")

    try:
        previous = settings.SCHEDULERS_ENABLED
        settings.SCHEDULERS_ENABLED = False
    except Exception as exc:                                   # noqa: BLE001
        raise Skipped(f"cannot force the freeze safely: {type(exc).__name__}")

    assert settings.SCHEDULERS_ENABLED is False, (
        "the freeze did not take; refusing to start the app, because "
        "unfrozen it would register and start every scheduled job here")

    app.dependency_overrides[require_admin] = lambda: {"id": 1, "is_admin": True}
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/admin/system-health")
        assert response.status_code == 200, response.status_code
        state = response.json()["scheduler"]
    finally:
        app.dependency_overrides.pop(require_admin, None)
        settings.SCHEDULERS_ENABLED = previous

    assert state["enabled"] is False, state
    assert state["jobs"] == [], state["jobs"]
    assert state["job_count"] == 0, state


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failures, skipped = [], []
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except Skipped as e:
            skipped.append(name)
            print(f"  SKIP  {name}  - {e}")
        except AssertionError as e:
            failures.append(name)
            print(f"  FAIL  {name}  - {e}")
        except Exception as e:                                 # noqa: BLE001
            failures.append(name)
            print(f"  ERROR {name}  - {type(e).__name__}: {e}")
    print(f"\n{len(tests) - len(failures) - len(skipped)}/{len(tests)} passed"
          + (f", {len(skipped)} skipped" if skipped else ""))
    sys.exit(1 if failures else 0)
