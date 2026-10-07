#!/usr/bin/env python
"""
Integration proof for v11.2.11 — the whole chain, with real objects
===================================================================
Two changes ship together because their value is the composition, not either
half:

    source refuses
      -> fetch_index_data raises SourceRefused          (producer_contract)
      -> run() counts it and verify() raises ProducerFailure
      -> compute_index_prices logs, runs its finally, RE-RAISES
      -> instrumented() records FAILED with class and message

Each link is unit-tested elsewhere. This asserts they connect. Before
v11.2.11, link 3 consumed the exception and the run was recorded `success`
with zero rows written -- which is how index_prices and fund_prices reported
four consecutive successful days while publishing nothing.

What is real here and what is not
---------------------------------
REAL: compute.engine.index_prices.fetch_index_data and run, the
      ProducerTally contract, app.workers.index_prices_worker, and
      app.core.job_instrumentation.instrumented.

STUBBED: yfinance (made to refuse, which is the condition under test) and the
      database session plus _open_run/_close_run (so telemetry is captured
      rather than written). Stubbing the recorder is what lets the assertion
      read the record; stubbing the subject would prove nothing.

Requires the real pandas and sqlalchemy, so it runs on the server or any
environment with backend requirements installed.

Run:  python tests/test_refusal_reaches_telemetry_end_to_end.py
"""

import asyncio
import sys
import types
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

TELEMETRY: list[dict] = []
CLEANUP: list[str] = []


def _install_stubs(*, refuse: bool):
    """yfinance refuses (or serves nothing); the DB is captured, not written."""
    TELEMETRY.clear()
    CLEANUP.clear()

    class _Ticker:
        def __init__(self, sym): self.sym = sym

        def history(self, **kw):
            if refuse:
                raise Exception("429 Client Error: Too Many Requests for url ...")
            import pandas as pd
            return pd.DataFrame()           # served, but empty

    yf = types.ModuleType("yfinance")
    yf.Ticker = _Ticker
    yf.__version__ = "stub"
    sys.modules["yfinance"] = yf

    class _Result:
        def fetchone(self): return None
        def fetchall(self): return []
        def scalar(self): return None

    class _DB:
        async def execute(self, *a, **k):
            CLEANUP.append("db.execute")        # heartbeat write lands here
            return _Result()
        async def commit(self): return None
        async def rollback(self): return None

    @asynccontextmanager
    async def _session():
        yield _DB()

    class _Factory:
        def __call__(self): return _session()

    sess = types.ModuleType("app.db.session")
    sess.AsyncSessionLocal = _Factory()
    sess.engine = None
    sys.modules["app.db.session"] = sess

    cache = types.ModuleType("app.core.cache")
    async def _cache_delete_pattern(p): return 0
    cache.cache_delete_pattern = _cache_delete_pattern
    sys.modules["app.core.cache"] = cache

    # Capture telemetry instead of writing it. instrumented() itself is real.
    import app.core.job_instrumentation as ji
    async def _open(job_id):
        TELEMETRY.append({"job_id": job_id, "status": "running"})
        return len(TELEMETRY) - 1
    async def _close(run_id, *, status, duration_ms=None, failure=None):
        TELEMETRY[run_id]["status"] = status
        if failure is not None:
            TELEMETRY[run_id]["failure_class"] = type(failure).__name__
            TELEMETRY[run_id]["failure_message"] = str(failure)
    ji._open_run = _open
    ji._close_run = _close
    return ji


def _run_registered_job(*, refuse: bool, reraise: bool = True):
    """Invoke exactly what APScheduler invokes: instrumented(id, worker)."""
    for m in list(sys.modules):
        if m.startswith(("compute.engine.index_prices",
                         "app.workers.index_prices_worker")):
            del sys.modules[m]

    ji = _install_stubs(refuse=refuse)
    from app.workers.index_prices_worker import compute_index_prices

    worker = compute_index_prices
    if not reraise:
        # Mutation: restore the pre-v11.2.11 swallowing wrapper.
        async def swallowing():
            try:
                from compute.engine.index_prices import run
                await run(target_date=date.today(), backfill_days=3)
            except Exception:
                pass
        worker = swallowing

    job = ji.instrumented("index_prices", worker)
    try:
        asyncio.run(job())
    except BaseException:
        pass                                   # instrumented re-raises; fine
    return TELEMETRY[0] if TELEMETRY else {}


# ── The property ────────────────────────────────────────────────────────────

def test_total_refusal_is_recorded_as_failed():
    rec = _run_registered_job(refuse=True)
    assert rec.get("status") == "failed", (
        f"every ticker was refused and telemetry recorded {rec.get('status')!r}"
        " -- this is the defect that hid four days of empty publication")


def test_the_cause_reaches_the_record():
    rec = _run_registered_job(refuse=True)
    assert rec.get("failure_class") == "ProducerFailure", rec
    assert "source_refused" in rec.get("failure_message", ""), (
        "the record says a job failed without saying the source refused us")
    assert "0 usable" in rec.get("failure_message", "")


def test_cleanup_still_runs_on_the_failure_path():
    """The heartbeat write lives in the worker's `finally`."""
    _run_registered_job(refuse=True)
    assert CLEANUP, (
        "the finally did not execute, so the re-raise was hoisted above the "
        "cleanup it must not skip")


def test_an_empty_but_willing_source_also_fails():
    """Refusal and absence are different causes, both still failures here.

    Every ticker returning an empty frame is `no_observations`, not
    `source_refused` -- the distinction the old `return None` destroyed.
    """
    rec = _run_registered_job(refuse=False)
    assert rec.get("status") == "failed", rec
    assert "no_observations" in rec.get("failure_message", ""), rec


def test_removing_the_wrapper_reraise_breaks_the_chain():
    """Mutation control on link 3.

    With the pre-v11.2.11 swallowing wrapper, the identical producer failure
    is recorded as success. If this ever asserts 'failed', the mutation no
    longer reproduces the old behaviour and the tests above prove nothing.
    """
    rec = _run_registered_job(refuse=True, reraise=False)
    assert rec.get("status") == "success", (
        "the swallowing wrapper no longer hides the failure, so the "
        "counterexample is not reproducing the defect")


def test_removing_the_producer_raise_breaks_the_chain():
    """Mutation control on link 2.

    A tally that never verifies returns normally no matter what it obtained,
    so the wrapper has nothing to re-raise.
    """
    from compute.engine.producer_contract import ProducerTally
    t = ProducerTally("index_prices", expected=10)
    for i in range(10):
        t.refusal(f"^SYM{i}")
    raised = False
    try:
        t.verify()
    except Exception:
        raised = True
    assert raised, "verify() does not raise on total refusal"

    class _NoVerify(ProducerTally):
        def verify(self): return None
    t2 = _NoVerify("index_prices", expected=10)
    for i in range(10):
        t2.refusal(f"^SYM{i}")
    t2.verify()          # must not raise -- that is the mutation


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
            except Exception as exc:                       # noqa: BLE001
                print(f"  ERROR {name}: {type(exc).__name__}: {exc}")
                failures.append(name)
    total = len([n for n in globals() if n.startswith("test_")])
    print(f"\n{total - len(failures)}/{total} passed")
    sys.exit(1 if failures else 0)
