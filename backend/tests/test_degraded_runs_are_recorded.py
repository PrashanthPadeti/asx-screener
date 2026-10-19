#!/usr/bin/env python
"""
Partial success must name what failed, and the record must say so
=================================================================
Measured on production, 14 October 2026, 06:37 UTC:

    fund_prices: 53/55 obtained, 0 refused, 2 empty, 157 rows
    Job "compute_fund_prices" executed successfully

Two eligible funds published nothing. The run said how many and never said
which. `ProducerTally` had computed the answer -- `failures`, `unaccounted`,
`degraded` and `report()` all existed and were correct -- and `run()` logged
`summary` and discarded the rest. `ops.job_executions` recorded `success`,
because at the job level that is true: 157 rows were written for 53 funds.

The same morning, index_prices logged `9/9 obtained`. SOURCES holds nine
entries; a tenth published index, AXJO, is deliberately not fetched and was
recorded nowhere, so a perfect score was reported over a population that had
silently excluded its missing member.

Why the existing tests did not catch either
-------------------------------------------
`test_population_and_entity_outcomes.py` asserts `t.degraded` and
`t.report()` extensively -- against tallies it constructs itself. Every one
of those assertions is true of the class and none of them was true of the
running producer. `test_fund_restoration_is_scoped.py` asserted that
`recon.findings()` appears in `run()`, which is the population half, and
stopped there.

So these tests drive the real `run()` through the real `instrumented`
wrapper and assert on what reaches the log and the record. A test that builds
its own ProducerTally cannot fail when nothing calls the producer's.

What is real here and what is not
---------------------------------
REAL: compute.engine.fund_prices.run and index_prices.run, the whole
      ProducerTally contract, both workers, and
      app.core.job_instrumentation.instrumented including _degradation_of.

STUBBED: the providers (yfinance and EODHD's httpx, made to serve, refuse
      and return nothing -- those conditions ARE the test), the database
      session, the source-of-truth population lookup, and _open_run/_close_run
      so the record can be read instead of written. Stubbing the recorder is
      what makes the assertion possible; stubbing the subject would prove
      nothing.

      The 2-second politeness delay between funds is also neutralised. 55
      funds would spend 110 seconds sleeping, and the delay is not the
      property under test.

Requires the real pandas and sqlalchemy.

Run:  python tests/test_degraded_runs_are_recorded.py
"""

import asyncio
import logging
import sys
import types
from contextlib import asynccontextmanager
from datetime import date, timedelta
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

TELEMETRY: list[dict] = []
LOGS: list[logging.LogRecord] = []


# ── Harness ─────────────────────────────────────────────────────────────────

def _frame(days: int = 30):
    """A plausible OHLCV frame in the shape yfinance returns."""
    import pandas as pd
    idx = pd.date_range(end=date.today(), periods=days, freq="D", tz="UTC")
    close = [100.0 + i * 0.5 for i in range(days)]
    return pd.DataFrame(
        {"Open": close, "High": [c + 1 for c in close],
         "Low": [c - 1 for c in close], "Close": close,
         "Volume": [1000] * days},
        index=idx)


class _CaptureHandler(logging.Handler):
    def emit(self, record):
        LOGS.append(record)


def _logged() -> str:
    out = []
    for r in LOGS:
        try:
            out.append(r.getMessage())
        except Exception:                                      # noqa: BLE001
            out.append(str(r.msg))
    return "\n".join(out)


def _install_stubs(*, refuse: set[str], empty: set[str]):
    """Providers serve, refuse or return nothing, per symbol."""
    TELEMETRY.clear()
    LOGS.clear()

    class _Ticker:
        def __init__(self, sym):
            self.sym = sym

        def history(self, **kw):
            import pandas as pd
            base = self.sym.replace(".AX", "").replace("^", "")
            if base in refuse:
                raise Exception("429 Client Error: Too Many Requests for url ...")
            if base in empty:
                return pd.DataFrame()
            return _frame()

    yf = types.ModuleType("yfinance")
    yf.Ticker = _Ticker
    yf.__version__ = "stub"
    sys.modules["yfinance"] = yf

    # EODHD serves six of the nine indices. Its fetcher imports httpx inside
    # the function, so stubbing the module here reaches it. Without this the
    # request is REAL: live network, production key, and a test whose result
    # depends on the provider being up.
    class _Resp:
        status_code = 200

        def json(self):
            start = date.today() - timedelta(days=29)
            return [{"date": (start + timedelta(days=i)).isoformat(),
                     "open": 100.0 + i, "high": 101.0 + i, "low": 99.0 + i,
                     "close": 100.0 + i, "volume": 1000}
                    for i in range(30)]

        def raise_for_status(self):
            return None

    class _Client:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get(self, *a, **k): return _Resp()

    httpx = types.ModuleType("httpx")
    httpx.Client = _Client
    httpx.get = lambda *a, **k: _Resp()
    httpx.HTTPError = Exception
    httpx.TimeoutException = Exception
    sys.modules["httpx"] = httpx

    class _Result:
        def fetchone(self): return None
        def fetchall(self): return []
        def scalar(self): return None
        def mappings(self): return self
        def all(self): return []

    class _DB:
        async def execute(self, *a, **k): return _Result()
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

    cfg = sys.modules.get("app.core.config")
    if cfg is None:
        cfg = types.ModuleType("app.core.config")
        cfg.settings = types.SimpleNamespace(EODHD_API_KEY="stub-key")
        sys.modules["app.core.config"] = cfg

    import app.core.job_instrumentation as ji

    async def _open(job_id):
        TELEMETRY.append({"job_id": job_id, "status": "running"})
        return len(TELEMETRY) - 1

    async def _close(run_id, *, status, duration_ms=None, failure=None,
                     degraded=False, findings=None):
        TELEMETRY[run_id].update({
            "status": status, "degraded": degraded, "findings": findings})
        if failure is not None:
            TELEMETRY[run_id]["failure_class"] = type(failure).__name__
            TELEMETRY[run_id]["failure_message"] = str(failure)

    ji._open_run = _open
    ji._close_run = _close

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    handler = _CaptureHandler()
    root.addHandler(handler)
    return ji, handler


def _reset_modules():
    for m in list(sys.modules):
        if m.startswith(("compute.engine.fund_prices",
                         "compute.engine.index_prices",
                         "compute.engine.fund_population",
                         "app.workers.fund_prices_worker",
                         "app.workers.index_prices_worker")):
            del sys.modules[m]


def _run_funds(*, refuse: set[str], empty: set[str], drop_return: bool = False,
               eligible_extra: set[str] = frozenset()):
    """Drive the registered fund job exactly as APScheduler would."""
    _reset_modules()
    ji, handler = _install_stubs(refuse=refuse, empty=empty)
    try:
        import compute.engine.fund_prices as fp
        from compute.engine.producer_contract import PopulationReconciliation

        # The politeness delay is not under test; 55 x 2s is.
        fp.asyncio = types.SimpleNamespace(
            sleep=lambda *_a, **_k: asyncio.sleep(0),
            to_thread=asyncio.to_thread)

        # The eligible population comes from market.funds. The database is
        # stubbed, so the lookup is supplied directly -- controlled, and
        # still NOT derived from the fetch list, which is the property the
        # producer must preserve.
        configured = {f["asx_code"] for f in fp.FUNDS}

        async def _recon(db, conf):
            return PopulationReconciliation(
                producer="fund_prices",
                eligible=frozenset(configured | set(eligible_extra)),
                configured=frozenset(conf))
        fp.reconcile = _recon

        from app.workers.fund_prices_worker import compute_fund_prices
        worker = compute_fund_prices
        if drop_return:
            # Mutation: the pre-fix worker, which discarded the tally.
            async def dropping():
                await compute_fund_prices()
                return None
            worker = dropping

        job = ji.instrumented("fund_prices", worker)
        try:
            asyncio.run(job())
        except BaseException:
            pass
        return TELEMETRY[0] if TELEMETRY else {}
    finally:
        logging.getLogger().removeHandler(handler)


def _run_indices(*, refuse: set[str] = frozenset(),
                 empty: set[str] = frozenset()):
    _reset_modules()
    ji, handler = _install_stubs(refuse=refuse, empty=empty)
    try:
        from app.workers.index_prices_worker import compute_index_prices
        job = ji.instrumented("index_prices", compute_index_prices)
        try:
            asyncio.run(job())
        except BaseException:
            pass
        return TELEMETRY[0] if TELEMETRY else {}
    finally:
        logging.getLogger().removeHandler(handler)


# ── The property: a partial run names what failed ───────────────────────────

def test_the_failing_funds_are_named_in_the_log():
    """The 14 Oct run's actual shape: most obtained, two not.

    `53/55` is the number. This asserts the names, which is what an operator
    needs and what the run did not provide.
    """
    _run_funds(refuse={"DIV"}, empty={"PMC"})
    text = _logged()
    assert "DIV" in text, "the refused fund is not named anywhere in the run"
    assert "PMC" in text, "the empty fund is not named anywhere in the run"
    assert "OUTCOME" in text, (
        "per-entity outcomes were never emitted; only the aggregate was")


def test_the_reason_is_logged_not_just_the_name():
    """A name without a cause sends the reader back to guessing."""
    _run_funds(refuse={"DIV"}, empty={"PMC"})
    text = _logged()
    assert "provider refused" in text, "the refusal's cause is not recorded"
    assert "provider returned no data" in text, (
        "the empty result's cause is not recorded")


def test_a_partial_fund_run_is_recorded_as_degraded():
    rec = _run_funds(refuse={"DIV"}, empty={"PMC"})
    assert rec.get("status") == "success", (
        f"53 of 55 obtained should remain a success, got {rec.get('status')!r}")
    assert rec.get("degraded") is True, (
        "two eligible funds published nothing and the record says the run was "
        "unqualifiedly successful -- the 14 Oct defect, unchanged")


def test_the_record_carries_the_findings():
    """A degraded flag with no evidence sends an operator to the logs with
    nothing to search for. The schema refuses it; so does this."""
    rec = _run_funds(refuse={"DIV"}, empty={"PMC"})
    findings = rec.get("findings") or []
    assert findings, "degraded was recorded without any findings"
    joined = " ".join(findings)
    assert "DIV" in joined and "PMC" in joined, (
        f"the findings do not name the funds that failed: {findings}")


def test_a_clean_run_is_not_degraded():
    """Mutation control on the verdict.

    If everything is degraded, nothing is.
    """
    rec = _run_funds(refuse=set(), empty=set())
    assert rec.get("status") == "success"
    assert rec.get("degraded") is False, (
        "a run in which every eligible fund published was marked degraded")
    assert not rec.get("findings"), (
        f"a clean run carried findings: {rec.get('findings')}")


def test_an_omitted_fund_degrades_the_run():
    """The population half, through the same path.

    An entity eligible in `market.funds` but absent from the fetch set is the
    original defect: eight ETFs, four months, success every day.
    """
    rec = _run_funds(refuse=set(), empty=set(), eligible_extra={"NEWETF"})
    assert rec.get("degraded") is True, (
        "a fund eligible in the source but never fetched left the run clean")
    assert any("NEWETF" in f for f in rec.get("findings") or []), (
        f"the omitted fund is not named: {rec.get('findings')}")


# ── The chain: dropping the return value hides the verdict ──────────────────

def test_dropping_the_workers_return_value_hides_degradation():
    """Mutation control on the link this candidate adds.

    Both workers discarded `run()`'s return value, so the producer's verdict
    could not reach the boundary that records it. If this ever stops reading
    False, the mutation no longer reproduces the defect and the tests above
    prove nothing about the wiring.
    """
    rec = _run_funds(refuse={"DIV"}, empty={"PMC"}, drop_return=True)
    assert rec.get("status") == "success"
    assert rec.get("degraded") is False, (
        "the pre-fix worker no longer hides the degradation, so the "
        "counterexample is not reproducing the defect")


def test_the_instrument_cannot_fail_the_job_it_watches():
    """A result whose `degraded` raises must not become a failed run.

    The observer does not get a vote on what it observes.
    """
    import app.core.job_instrumentation as ji

    class _Hostile:
        @property
        def degraded(self):
            raise RuntimeError("telemetry must not propagate this")

    degraded, findings = ji._degradation_of("x", _Hostile())
    assert degraded is False and findings is None


def test_a_degraded_verdict_without_findings_still_says_so():
    """The flag and its evidence are one fact, and the schema enforces that.

    Recording neither would drop a true verdict; inventing evidence would be
    worse. It says the evidence is missing.
    """
    import app.core.job_instrumentation as ji

    class _NoReport:
        degraded = True

    degraded, findings = ji._degradation_of("x", _NoReport())
    assert degraded is True
    assert findings and "no findings" in findings[0]


def test_an_ordinary_job_returning_none_is_unaffected():
    """Most scheduled jobs return None and must keep recording plain success."""
    import app.core.job_instrumentation as ji
    assert ji._degradation_of("x", None) == (False, None)


# ── Indices: the excluded member is accounted for ───────────────────────────

def test_the_excluded_index_is_recorded_every_run():
    """AXJO is correctly withheld and was reported nowhere.

    `9/9 obtained` was a perfect score over a population that had quietly
    dropped its tenth member.
    """
    _run_indices()
    text = _logged()
    assert "AXJO" in text, (
        "a published index is deliberately not fetched and no run says so")
    assert "excluded" in text.lower()
    assert "provenance" in text.lower(), (
        "the exclusion is recorded without its reason")


def test_the_index_population_counts_what_is_not_fetched():
    """`expected` must not be defined by the fetch list.

    This is the defect v11.2.22 fixed in fund_prices; index_prices still had
    it, with `expected=len(SOURCES)`.
    """
    _reset_modules()
    _install_stubs(refuse=set(), empty=set())
    from compute.engine.index_prices import EXCLUDED_SOURCES, SOURCES
    assert "AXJO" not in SOURCES
    assert "AXJO" in EXCLUDED_SOURCES
    assert EXCLUDED_SOURCES["AXJO"].strip(), (
        "an exclusion without a reason is indistinguishable from an omission")

    _run_indices()
    text = _logged()
    expected = len(SOURCES) + len(EXCLUDED_SOURCES)
    assert f"/{expected} obtained" in text, (
        f"the run reports a population that excludes what it chose not to "
        f"fetch; expected {expected} accounted for. Log said:\n{text[-400:]}")


def test_a_refused_index_degrades_the_index_run():
    """One entity fails, the rest publish, the run says so.

    The refusal target is DERIVED from SOURCES, not named. This test used to
    refuse AXHJ; AXHJ then moved to EODHD, so the yfinance stub stopped
    reaching it, the httpx stub served it successfully, and the test went on
    asserting that a clean run was degraded. It failed loudly, which was
    luck -- a hardcoded symbol in a test is a premise that expires the
    moment someone changes a mapping, and it expires silently as often as
    not.
    """
    _reset_modules()
    from compute.engine.index_prices import SOURCES
    yahoo = sorted((c, s.symbol) for c, s in SOURCES.items()
                   if s.provider == "yahoo")
    assert yahoo, (
        "every index is on EODHD, so the yfinance stub can no longer refuse "
        "anything and this test proves nothing — refuse through httpx "
        "instead")
    code, symbol = yahoo[0]

    rec = _run_indices(refuse={symbol.lstrip("^")})
    assert rec.get("status") == "success", (
        "one refusal among many should not discard the entities that "
        "published")
    assert rec.get("degraded") is True
    assert any(code in f for f in rec.get("findings") or []), (
        f"the refused index {code} is not named: {rec.get('findings')}")


def test_an_exclusion_alone_does_not_degrade_a_run():
    """A deliberate, reasoned exclusion is an accounted outcome, not a fault.

    If it degraded every run, the signal would mean nothing within a day.
    """
    rec = _run_indices()
    assert rec.get("degraded") is False, (
        f"a clean run was marked degraded by its own exclusion: "
        f"{rec.get('findings')}")


# ── The migration the record depends on ─────────────────────────────────────

def test_the_migration_declares_what_the_writer_writes():
    """_close_run names two columns; an un-migrated table loses the whole row.

    Structural on purpose: the ordering requirement is a deployment fact, and
    this is the cheapest place to notice the two drifting apart.
    """
    sql = (BACKEND / "migrations" / "add_job_execution_degraded.sql").read_text(
        encoding="utf-8")
    for col in ("degraded", "findings"):
        assert col in sql, f"{col} is written but never added by a migration"
    assert "job_executions_degraded_has_findings" in sql, (
        "nothing stops a degraded row from omitting its evidence")

    writer = (BACKEND / "app" / "core" / "job_instrumentation.py").read_text(
        encoding="utf-8")
    assert "degraded        = :degraded" in writer
    assert "findings        = :findings" in writer


def test_the_status_domain_is_unchanged():
    """`degraded` rides alongside status; it does not join its domain.

    Adding a fourth literal would make a degraded run match none of the
    filters written against the existing three -- the terminal index, the
    Pipeline Monitor, last_success -- and the run would become invisible
    rather than merely green.
    """
    sql = (BACKEND / "migrations" / "add_job_execution_degraded.sql").read_text(
        encoding="utf-8")
    assert "status IN ('running', 'success', 'failed', 'degraded')" not in sql
    from compute.engine.job_telemetry import TERMINAL
    assert set(TERMINAL) == {"success", "failed"}, (
        "the terminal domain changed; every filter enumerating it must be "
        "revisited before this is safe")


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
