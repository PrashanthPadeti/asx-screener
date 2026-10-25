"""
One declaration, one owner
==========================
The worker (v11.2.45) and the API both register the same jobs from the same
function. That is deliberate -- two lists would drift, and drift reads as a
job running twice or not at all -- but it means both processes are CAPABLE
of running every scheduled job.

If both ever do, every scheduled effect happens twice: two alert emails to
the same customer, two announcement fetches inserting the same filings, two
writes racing into screener.universe. The symptom appears far from the
cause, and the first report comes from a customer.

SCHEDULERS_ENABLED=false on the API DECLARES the cutover. What makes it true
is a PostgreSQL advisory lock, and the difference between those two is the
whole subject of this file: an entitlement is real only when the path
enforces it.

The behavioural test at the end is the one that matters. The structural ones
establish that the machinery is wired; only the behavioural one establishes
that a second owner is actually refused.
"""

import ast
import logging
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.core.scheduler_ownership import (                      # noqa: E402
    SCHEDULER_OWNER_KEY, SchedulerOwner,
)
from compute.engine.canonical_lease import CANONICAL_LEASE_KEY  # noqa: E402

WORKER = BACKEND / "worker.py"
MAIN = BACKEND / "app" / "main.py"
REGISTRY = BACKEND / "app" / "scheduler_registry.py"


def _tree(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), str(path))


def _calls(tree: ast.AST, attr: str) -> list:
    return [n for n in ast.walk(tree)
            if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == attr]


# ── One declaration ─────────────────────────────────────────────────────────

def test_the_worker_registers_from_the_shared_declaration():
    """Not a second copy of the job list.

    A worker with its own add_job calls would drift from the API's, and the
    drift is invisible until a job runs twice or stops running.
    """
    src = WORKER.read_text(encoding="utf-8")
    assert "from app.scheduler_registry import register_jobs" in src, (
        "the worker must register from app/scheduler_registry.py")
    assert not _calls(_tree(WORKER), "add_job"), (
        "worker.py declares jobs of its own; there must be exactly one "
        "declaration site and it is app/scheduler_registry.py")


def test_both_processes_call_the_same_registration_function():
    for path in (WORKER, MAIN):
        names = [n.func.id for n in ast.walk(_tree(path))
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
        assert "register_jobs" in names, f"{path.name} does not register jobs"


def test_the_registry_is_the_only_declaration_site():
    """Guards the property the discovery in launch_authority relies on."""
    from compute.engine import launch_authority as la
    assert la.scheduler_sources() == [REGISTRY], (
        f"expected exactly one declaration site, found "
        f"{[str(p) for p in la.scheduler_sources()]}")


# ── One owner: structure ────────────────────────────────────────────────────

def test_the_two_locks_do_not_collide():
    """Scheduler ownership and canonical execution are different questions.

    A shared key would make a canonical pipeline run and a scheduler start
    contend for the same lock: the scheduler would fail to own itself for
    the duration of a pipeline, register nothing, and look like a dead
    worker.
    """
    assert SCHEDULER_OWNER_KEY != CANONICAL_LEASE_KEY


def test_the_api_freezes_itself_when_it_does_not_own_the_schedulers():
    """The flag is not what makes the cutover true.

    main.py must set frozen=True on a failed acquisition, so a stale or
    restored .env cannot produce a second owner.
    """
    src = MAIN.read_text(encoding="utf-8")
    assert "SchedulerOwner" in src, "the API does not arbitrate ownership"
    acquire = src.index("try_acquire()")
    following = src[acquire:acquire + 400]
    assert "frozen = True" in following, (
        "the API does not freeze itself when it fails to acquire ownership; "
        "a wrong .env would then give two processes running every job")


def test_a_frozen_api_does_not_take_the_lock():
    """A process running nothing must not hold ownership.

    If it did, the worker would be permanently locked out by an API that is
    deliberately idle -- and nothing would run the jobs at all, which is the
    one state the lock cannot distinguish from health on its own.
    """
    src = MAIN.read_text(encoding="utf-8")
    assert "if not frozen:" in src.split("owner = None")[1][:200], (
        "ownership is attempted unconditionally; a frozen API would hold "
        "the lock while running nothing")


def test_the_worker_refuses_to_run_without_ownership():
    src = WORKER.read_text(encoding="utf-8")
    assert "try_acquire()" in src
    assert "return 1" in src.split("try_acquire()")[1][:400], (
        "the worker continues without ownership; it must exit non-zero, "
        "because a worker silently running nothing looks healthy")


def test_the_worker_honours_the_rollout_freeze_and_instrument_mode():
    """Both protections moved with the jobs.

    A freeze that only applied to the API would be meaningless once the jobs
    live elsewhere, and instrument mode exists because importing this
    machinery has twice started real jobs on the production host.
    """
    src = WORKER.read_text(encoding="utf-8")
    assert "SCHEDULERS_ENABLED" in src, "the worker ignores the rollout freeze"
    assert "instrument_mode" in src, "the worker ignores instrument mode"


def test_the_worker_does_not_block_its_own_shutdown():
    """shutdown(wait=True) deadlocks an AsyncIOScheduler.

    Jobs run as coroutines on the worker's event loop. wait=True blocks that
    loop waiting for them to finish, so the jobs it waits for cannot run.
    Measured 25 Oct 2026: SIGTERM at 21:12:33, process alive until 21:27:09,
    released only when the scheduler's next wakeup timer fired.

    Under systemd that is a five-minute hang on every worker restart, ending
    in SIGKILL mid-job. The drain must therefore be awaited, not blocked on.
    """
    src = WORKER.read_text(encoding="utf-8")
    tree = _tree(WORKER)

    for call in _calls(tree, "shutdown"):
        waits = [k for k in call.keywords if k.arg == "wait"]
        assert waits, "scheduler.shutdown() must state wait= explicitly"
        for keyword in waits:
            assert isinstance(keyword.value, ast.Constant)
            assert keyword.value.value is False, (
                "worker.py calls scheduler.shutdown(wait=True), which "
                "deadlocks the event loop the jobs run on")

    assert "asyncio.wait(" in src, (
        "the worker does not await its in-flight jobs; without a drain, a "
        "restart tears a job off mid-write")
    assert "DRAIN_SECONDS" in src, "the drain must be bounded"


def test_the_drain_fits_inside_the_unit_s_stop_timeout():
    """A bound longer than TimeoutStopSec is not a bound.

    systemd would SIGKILL the process mid-drain, and the careful handling
    above would never complete.
    """
    import re
    from app import __file__ as _app  # noqa: F401

    unit = (BACKEND / "scripts" / "systemd" / "asx-worker.service"
            ).read_text(encoding="utf-8")
    stop_timeout = int(re.search(r"TimeoutStopSec=(\d+)", unit).group(1))
    drain = int(re.search(r"DRAIN_SECONDS = (\d+)",
                          WORKER.read_text(encoding="utf-8")).group(1))
    assert drain < stop_timeout, (
        f"DRAIN_SECONDS={drain} is not less than TimeoutStopSec="
        f"{stop_timeout}; systemd would kill the worker mid-drain")


def test_the_deploy_restarts_the_worker():
    deploy = (BACKEND.parent / "deploy.sh").read_text(encoding="utf-8")
    assert "restart_worker" in deploy
    assert deploy.count("restart_worker") >= 3, (
        "restart_worker must be defined and called on both deploy paths")


# ── One owner: behaviour ────────────────────────────────────────────────────

def test_a_second_owner_is_refused():
    """The property, not the machinery.

    Everything above establishes that the code is wired to ask the question.
    This establishes that the answer is no. Six green structural guards once
    sat over a live composition defect in this codebase; the behavioural
    test is the one that would have caught it.
    """
    from app.core.config import settings

    first = SchedulerOwner(settings.DATABASE_URL_SYNC, role="test-first")
    try:
        assert first.try_acquire(), (
            "could not acquire scheduler ownership on an idle database; "
            "this test cannot say anything about exclusion")

        second = SchedulerOwner(settings.DATABASE_URL_SYNC, role="test-second")
        try:
            assert not second.try_acquire(), (
                "TWO processes acquired scheduler ownership simultaneously. "
                "Every scheduled job would run twice: duplicate alert "
                "emails, duplicate writes.")
        finally:
            second.release()
    finally:
        first.release()


def test_ownership_is_released_and_can_be_retaken():
    """A restart must not lock the next process out.

    An advisory lock is session-scoped, so this also covers the crash case:
    if release were the only thing freeing it, a killed worker would block
    its own replacement until a DBA intervened.
    """
    from app.core.config import settings

    first = SchedulerOwner(settings.DATABASE_URL_SYNC, role="test-cycle-1")
    assert first.try_acquire()
    first.release()
    assert not first.acquired

    second = SchedulerOwner(settings.DATABASE_URL_SYNC, role="test-cycle-2")
    try:
        assert second.try_acquire(), (
            "ownership was not released — the next worker start would be "
            "locked out by its own predecessor")
    finally:
        second.release()


def test_the_key_is_large_enough_to_exercise_the_split():
    """A 64-bit advisory key is stored across TWO 32-bit columns.

    classid holds the high half, objid the low half. The first version of
    holder() matched on objid alone, which compares against the low half and
    finds nothing. With a key below 2**32 the high half is zero and the bug
    is invisible, so this pins the condition that makes the test below mean
    something.
    """
    assert SCHEDULER_OWNER_KEY > 2 ** 32, (
        "the key no longer spans both lock columns, so the test below would "
        "pass even with a predicate that ignores classid")


class _Capture(logging.Handler):
    """Collects records from the ownership logger.

    Not pytest's caplog: the gate executes these files as standalone
    scripts, where fixtures do not exist. A test that only works under
    pytest is a test the gate silently skips -- which is the defect this
    whole release is about.
    """

    def __init__(self):
        super().__init__()
        self.messages = []

    def emit(self, record):
        self.messages.append(record.getMessage())

    def __enter__(self):
        self._logger = logging.getLogger("app.core.scheduler_ownership")
        self._previous = self._logger.level
        self._logger.setLevel(logging.WARNING)
        self._logger.addHandler(self)
        return self

    def __exit__(self, *_exc):
        self._logger.removeHandler(self)
        self._logger.setLevel(self._previous)
        return False

    @property
    def text(self) -> str:
        return " ".join(self.messages)


def test_a_refused_owner_names_the_holder():
    """'I am not the owner' is only useful if you can find out who is.

    Asked from the REFUSED process, which is what production does. The
    previous version asked the holder's own connection, and so passed on
    25 Oct 2026 while the live worker printed "an unidentified session" --
    a guard whose conditions differed from the path it claimed to cover.
    """
    from app.core.config import settings

    first = SchedulerOwner(settings.DATABASE_URL_SYNC, role="test-holder")
    try:
        assert first.try_acquire()

        probe = SchedulerOwner(settings.DATABASE_URL_SYNC, role="test-probe")
        with _Capture() as captured:
            assert not probe.try_acquire()
        logged = captured.text

        assert "asx-scheduler-owner/test-holder" in logged, (
            f"the refused process could not identify the holder: {logged!r}")
        assert "no session holds it" not in logged, (
            "the lock is held, but the query reported nobody holds it — the "
            "predicate does not match the key as stored")
        assert "could not be determined" not in logged, (
            f"the holder query itself failed: {logged!r}")
    finally:
        first.release()


def test_the_three_outcomes_stay_distinguishable():
    """Held, nobody, and could-not-look are different facts.

    Collapsing them is what sent 25 Oct 2026's investigation toward
    permissions when the cause was a wrong predicate.
    """
    from app.core.config import settings

    free = SchedulerOwner(settings.DATABASE_URL_SYNC, role="test-unheld")
    assert free.try_acquire()
    held = free.holder()
    free.release()
    assert "asx-scheduler-owner" in held, held

    broken = SchedulerOwner(settings.DATABASE_URL_SYNC, role="test-broken")
    # No connection was ever opened, so the query must fail -- and must SAY
    # it failed rather than reporting an empty result.
    assert "could not be determined" in broken.holder()


if __name__ == "__main__":
    # The gate runs suites as standalone scripts and reads this summary. A
    # file without this block defines its functions, runs nothing, exits 0,
    # and is counted as passing -- which is exactly what happened to this
    # suite from v11.2.45 until v11.2.47, while it was being cited as
    # behavioural proof that two owners cannot coexist.
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
        except Exception as e:                                # noqa: BLE001
            failures.append(name)
            print(f"  ERROR {name}  - {type(e).__name__}: {e}")
    print(f"\n{len(tests) - len(failures)}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
