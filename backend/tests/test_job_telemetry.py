"""
Execution telemetry for scheduled jobs
======================================
APScheduler records intent — a trigger and a next-fire time. It records nothing
about execution. On 2 Oct 2026 the site was unavailable for ~40 minutes while an
in-process job made hundreds of serial outbound calls, and the only reason that
job's ~55-minute runtime is known is that it happened to log every HTTP request
during an outage someone was already investigating. Sixteen other jobs have no
measured runtime at all.

The load-bearing test here is registration coverage. Without it this becomes
"some jobs happen to emit timings"; with it, every live scheduler identity is
either instrumented or explicitly classified unobservable, and silence is not
evidence of health.

Run under pytest, or standalone:
    cd backend && ../asx-venv/bin/python tests/test_job_telemetry.py
"""

import ast
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from compute.engine.job_telemetry import (                       # noqa: E402
    DEFAULT_CEILING_SECONDS, Execution, FAILED, MAX_FAILURE_CHARS, RUNNING,
    MISSED_GRACE_SECONDS, SUCCESS, UNOBSERVABLE, bound_failure, ceiling_for,
    classify, first_run_state, health_view,
)

MAIN = BACKEND / "app/main.py"
NOW = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)


def _ago(**kw) -> datetime:
    return NOW - timedelta(**kw)


def _exec(job_id="alert_checker", **kw) -> Execution:
    base = dict(run_id=1, job_id=job_id, started_at=_ago(seconds=5))
    base.update(kw)
    return Execution(**base)


# ── Registration coverage: the operational contract ──────────────────────────

def _registrations() -> dict[str, ast.expr]:
    """job_id -> the first positional argument of its add_job call.

    Read from the AST, not by name matching: a function called
    `instrumented_fetch` must not satisfy a check for instrumentation.
    """
    tree = ast.parse(MAIN.read_text(encoding="utf-8"))
    out: dict[str, ast.expr] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if not (isinstance(fn, ast.Attribute) and fn.attr == "add_job"):
            continue
        job_id = next((kw.value.value for kw in node.keywords
                       if kw.arg == "id" and isinstance(kw.value, ast.Constant)),
                      None)
        if job_id and node.args:
            out[job_id] = node.args[0]
    return out


def test_every_registration_is_instrumented_or_declared_unobservable():
    """The contract. An identity that is neither is UNKNOWN, and unknown is a
    failing state — the whole point is that a job nobody measured must not look
    the same as a job that succeeded."""
    regs = _registrations()
    assert regs, "no add_job registrations found; the parser or the file moved"

    uncovered = []
    for job_id, first_arg in regs.items():
        if job_id in UNOBSERVABLE:
            continue
        wrapped = (isinstance(first_arg, ast.Call)
                   and isinstance(first_arg.func, ast.Name)
                   and first_arg.func.id == "instrumented")
        if not wrapped:
            uncovered.append(job_id)
    assert not uncovered, (
        f"these scheduler identities have no execution telemetry and are not "
        f"declared UNOBSERVABLE: {uncovered}")


def test_the_wrapper_is_given_the_same_id_the_scheduler_registers():
    """A wrapper labelled with the wrong id records real executions against a
    job that never ran, which is worse than no telemetry."""
    mismatched = []
    for job_id, first_arg in _registrations().items():
        if not (isinstance(first_arg, ast.Call)
                and getattr(first_arg.func, "id", None) == "instrumented"):
            continue
        label = first_arg.args[0]
        if not (isinstance(label, ast.Constant) and label.value == job_id):
            mismatched.append((job_id, getattr(label, "value", "<non-literal>")))
    assert not mismatched, f"wrapper label != registered id: {mismatched}"


def test_unobservable_entries_carry_a_reason():
    for job_id, reason in UNOBSERVABLE.items():
        assert reason and len(reason) > 10, (
            f"{job_id} is declared unobservable without a reason")


def test_coverage_detects_a_missing_wrapper():
    """Mutation control. A coverage test that cannot fail proves nothing."""
    tree = ast.parse(
        "scheduler.add_job(check_alerts, trigger='interval', id='alert_checker')\n"
        "scheduler.add_job(instrumented('x', f), trigger='interval', id='x')\n")
    found = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "add_job":
            jid = next(kw.value.value for kw in node.keywords if kw.arg == "id")
            found[jid] = node.args[0]
    assert not isinstance(found["alert_checker"], ast.Call), (
        "the bare registration would have been accepted as instrumented")
    assert isinstance(found["x"], ast.Call)


# ── Classification ───────────────────────────────────────────────────────────

def test_a_terminal_status_is_reported_as_itself():
    assert classify(_exec(status=SUCCESS, finished_at=NOW), NOW) == SUCCESS
    assert classify(_exec(status=FAILED, finished_at=NOW), NOW) == FAILED


def test_a_recent_running_row_is_simply_running():
    assert classify(_exec(status=RUNNING, started_at=_ago(seconds=30)), NOW) == RUNNING


def test_a_running_row_past_its_ceiling_is_stale_not_healthy():
    """A process killed mid-run writes no terminal row. The surviving RUNNING
    row must become visible rather than looking healthy forever."""
    old = _exec(status=RUNNING, started_at=_ago(seconds=DEFAULT_CEILING_SECONDS + 60))
    assert classify(old, NOW) == "stale_running"


def test_a_job_with_a_known_long_runtime_has_its_own_ceiling():
    """announcement_fetcher ran 09:10 -> 10:05 UTC on 2 Oct 2026. That is
    measured, not assumed, and it must not trip the default ceiling while it is
    still legitimately running."""
    assert ceiling_for("announcement_fetcher") > DEFAULT_CEILING_SECONDS
    long_run = _exec(job_id="announcement_fetcher", status=RUNNING,
                     started_at=_ago(minutes=50))
    assert classify(long_run, NOW) == RUNNING
    assert ceiling_for("some_other_job") == DEFAULT_CEILING_SECONDS


# ── The health view ──────────────────────────────────────────────────────────

def test_it_answers_both_operator_questions():
    running = [_exec(run_id=9, job_id="announcement_fetcher", status=RUNNING,
                     started_at=_ago(minutes=12))]
    latest = {"alert_checker": _exec(run_id=8, job_id="alert_checker",
                                     status=SUCCESS, finished_at=_ago(minutes=3),
                                     duration_ms=1200)}
    v = health_view(registered={"alert_checker": NOW + timedelta(minutes=5),
                                "announcement_fetcher": NOW + timedelta(hours=8)},
                    running=running, latest_terminal=latest, now=NOW)
    assert v["running"][0]["job_id"] == "announcement_fetcher"
    assert v["running"][0]["running_for_seconds"] == 720
    alert = next(j for j in v["jobs"] if j["job_id"] == "alert_checker")
    assert alert["last_terminal"]["duration_ms"] == 1200


def test_a_weekly_job_awaiting_its_first_run_is_healthy_not_unknown():
    """Three of the twenty jobs are weekly or monthly. A monthly job deployed
    today legitimately has no terminal execution for weeks; calling that
    `unknown` would keep the surface red for a healthy system, which is exactly
    how an operator learns to ignore it."""
    v = health_view(registered={"mining_reit_metrics": NOW + timedelta(days=5)},
                    running=[], latest_terminal={}, now=NOW)
    assert v["pending_first_run"] == ["mining_reit_metrics"]
    assert v["unknown"] == [] and v["missed"] == []
    assert v["verdict"] == "ok", "a not-yet-due job must not fail the view"
    assert v["jobs"][0]["next_expected_at"], "the expected time is not published"


def test_a_job_whose_fire_time_passed_with_no_evidence_is_missed():
    """Past the grace, absence stops being a timing artefact and becomes a
    finding: either the scheduler did not run it, or it ran untelemetered."""
    overdue = NOW - timedelta(seconds=MISSED_GRACE_SECONDS + 60)
    v = health_view(registered={"alert_checker": overdue},
                    running=[], latest_terminal={}, now=NOW)
    assert v["missed"] == ["alert_checker"]
    assert v["verdict"] == "missed"
    assert "no execution recorded" in v["jobs"][0]["detail"]


def test_within_the_grace_it_is_still_pending():
    """A job firing right now must not be reported missed because the view was
    read a second after its trigger."""
    v = health_view(registered={"alert_checker": NOW - timedelta(seconds=30)},
                    running=[], latest_terminal={}, now=NOW)
    assert v["pending_first_run"] == ["alert_checker"]
    assert v["verdict"] == "ok"


def test_unknown_is_reserved_for_the_genuinely_unresolvable():
    """Registered, but APScheduler reports no intent for it at all."""
    v = health_view(registered={"ghost": None}, running=[],
                    latest_terminal={}, now=NOW)
    assert v["unknown"] == ["ghost"]
    assert v["verdict"] == "unresolved"


def test_an_execution_with_no_matching_registration_is_unresolved():
    """Runtime fact with no matching intent — a renamed job still writing under
    its old id, or a second process. Not merely unobserved."""
    stray = _exec(run_id=77, job_id="job_that_no_longer_exists", status=RUNNING,
                  started_at=_ago(seconds=10))
    v = health_view(registered={"alert_checker": NOW + timedelta(minutes=5)},
                    running=[stray], latest_terminal={}, now=NOW)
    assert v["unexpected_job_ids"] == ["job_that_no_longer_exists"]
    assert v["verdict"] == "unresolved"


def test_a_bare_id_list_is_ignorance_not_health():
    """Passing ids without fire times means nothing is known about intent, and
    that must classify as unknown rather than quietly passing."""
    v = health_view(registered=["x"], running=[], latest_terminal={}, now=NOW)
    assert v["unknown"] == ["x"] and v["verdict"] == "unresolved"


def test_a_stale_running_job_makes_the_view_suspect():
    stale = _exec(run_id=3, status=RUNNING,
                  started_at=_ago(seconds=DEFAULT_CEILING_SECONDS + 600))
    v = health_view(registered={"alert_checker": NOW + timedelta(minutes=5)}, running=[stale],
                    latest_terminal={"alert_checker": _exec(
                        status=SUCCESS, finished_at=_ago(hours=2), duration_ms=5)},
                    now=NOW)
    assert v["verdict"] == "suspect"
    assert v["stale_running"] == ["alert_checker"]


def test_a_disabled_scheduler_running_nothing_is_not_a_failure():
    """Zero running jobs is the normal state most of the time, and a frozen
    scheduler is a legitimate operating mode. Neither may read as broken."""
    latest = {"alert_checker": _exec(status=SUCCESS, finished_at=_ago(hours=1),
                                     duration_ms=10)}
    v = health_view(registered={"alert_checker": NOW + timedelta(minutes=5)}, running=[],
                    latest_terminal=latest, now=NOW, scheduler_enabled=False)
    assert v["verdict"] == "ok"
    assert v["scheduler_enabled"] is False


def test_a_failed_terminal_run_is_reported_as_failing():
    latest = {"alert_checker": _exec(status=FAILED, finished_at=_ago(minutes=1),
                                     duration_ms=50, failure_class="TypeError",
                                     failure_message="Object of type Decimal is not JSON serializable")}
    v = health_view(registered={"alert_checker": NOW + timedelta(minutes=5)}, running=[],
                    latest_terminal=latest, now=NOW)
    assert v["verdict"] == "failing"
    assert v["failing"] == ["alert_checker"]


def test_an_unobservable_job_is_neither_unknown_nor_failing():
    UNOBSERVABLE["probe_only"] = "a diagnostic shim with no execution boundary"
    try:
        v = health_view(registered={"probe_only": NOW + timedelta(minutes=5)}, running=[],
                        latest_terminal={}, now=NOW)
        assert v["unknown"] == []
        assert v["verdict"] == "ok"
        entry = v["jobs"][0]
        assert entry["coverage"] == "unobservable" and entry["reason"]
    finally:
        UNOBSERVABLE.pop("probe_only")


# ── Failure text is bounded ──────────────────────────────────────────────────

def test_failure_text_cannot_become_an_exfiltration_channel():
    """An exception payload can carry a connection string, a token, or a
    megabyte of SQL. The admin response is not the place to find out."""
    assert bound_failure(None) is None
    assert bound_failure("short") == "short"
    long = "x" * (MAX_FAILURE_CHARS * 5)
    assert len(bound_failure(long)) <= MAX_FAILURE_CHARS
    assert bound_failure("a\n\n  b\tc") == "a b c", "whitespace not collapsed"


def test_the_view_bounds_failure_text_too():
    latest = {"j": _exec(job_id="j", status=FAILED, finished_at=NOW,
                         duration_ms=1, failure_class="E",
                         failure_message="y" * 5000)}
    v = health_view(registered={"j": NOW + timedelta(minutes=5)}, running=[], latest_terminal=latest, now=NOW)
    assert len(v["jobs"][0]["last_terminal"]["failure_message"]) <= MAX_FAILURE_CHARS


# ── The wrapper must not change what it observes ─────────────────────────────

def test_telemetry_failure_cannot_change_a_job_outcome():
    """The rule app/core/instrument.py froze after three incidents, applied to
    a different boundary: the observer does not get a vote. Checked
    structurally because exercising it needs a database."""
    src = (BACKEND / "app/core/job_instrumentation.py").read_text(encoding="utf-8")
    for fn in ("_open_run", "_close_run"):
        body = src[src.index(f"async def {fn}"):]
        body = body[:body.index("\n\n\n")] if "\n\n\n" in body else body
        assert "except Exception" in body, f"{fn} can raise into the caller"
    # Comments stripped first. The comment above the close call says
    # "then re-raise unchanged", and matching that instead of the statement
    # made this assertion fail against correct code — the same prose-as-code
    # mistake this repo has now made in several matchers.
    run = re.sub(r"#[^\n]*", "", src[src.index("async def _run("):])
    bare_raise = re.search(r"\n\s+raise\s*\n", run)
    assert bare_raise, "the wrapper swallows the job's exception"
    assert run.index("status=FAILED") < bare_raise.start(), (
        "the failure is recorded after re-raising, so it is never recorded")


def test_a_crash_is_not_recorded_as_success():
    """SUCCESS is written only after the job returns. A process killed between
    the boundaries writes neither, leaving the RUNNING row that stale detection
    exists to surface."""
    src = (BACKEND / "app/core/job_instrumentation.py").read_text(encoding="utf-8")
    run = src[src.index("async def _run("):]
    success_at = run.index("status=SUCCESS")
    await_at = run.index("await func(")
    assert await_at < success_at, "success is recorded before the job runs"


def test_the_close_only_closes_a_running_row():
    """Guards against a second terminal write overwriting the first, and
    against closing a row that some other process already closed."""
    src = (BACKEND / "app/core/job_instrumentation.py").read_text(encoding="utf-8")
    assert "AND status = 'running'" in src, (
        "the terminal update does not require the row to still be running")


# ── Storage shape ────────────────────────────────────────────────────────────

def test_executions_are_immutable_rows_not_one_row_per_job():
    """One row per job id cannot represent a job overlapping itself, and
    overlap is the pathology worth seeing."""
    sql = (BACKEND / "migrations/add_job_executions.sql").read_text(encoding="utf-8")
    assert "run_id" in sql and "PRIMARY KEY" in sql
    assert not re.search(r"UNIQUE\s*\(\s*job_id\s*\)", sql), (
        "a unique constraint on job_id would forbid overlapping executions")


def test_a_terminal_row_must_carry_its_terminal_facts():
    sql = (BACKEND / "migrations/add_job_executions.sql").read_text(encoding="utf-8")
    assert "job_executions_terminal_is_complete" in sql
    assert "job_executions_status_known" in sql


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
        except Exception as e:                                     # noqa: BLE001
            failures.append(name)
            print(f"  ERROR {name}  - {type(e).__name__}: {e}")
    print(f"\n{len(tests) - len(failures)}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
