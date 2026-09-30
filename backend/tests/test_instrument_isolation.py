"""
The protections are exercised, not asserted into existence
==========================================================
Rule 6 of `docs/canonical_orchestration.md`: an instrument is side-effect-free
by default. These tests deliberately attempt the three mutations the rule
names — scheduler startup, a cache write, and outbound mail — and require each
to be stopped.

Two stop differently, and the difference was learned by getting it wrong.
A deliberate irreversible action (mail) is REFUSED and raises. A mutation the
application performs on its own initiative (its response cache) is SUPPRESSED:
declined, recorded, logged, and never raised — because raising inside a
request breaks the surface the instrument is measuring, which is exactly how
Gate B died the first time this shipped.

That direction matters. Asserting "no scheduler started" in a suite that never
tries to start one proves nothing, and it is exactly the shape of the inert
guards this codebase keeps producing: a check that examines nothing and
reports success. Every test here makes the attempt.

Run under pytest (conftest sets instrument mode before any import), or
standalone:
    cd /opt/asx-screener/backend && ../asx-venv/bin/python tests/test_instrument_isolation.py
"""

import asyncio
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

# Standalone runs get no conftest, so declare it here too. setdefault, so the
# pytest-set value wins and this never silently disagrees with it.
os.environ.setdefault("ASX_INSTRUMENT_MODE", "1")

from app.core import instrument  # noqa: E402


class Skipped(Exception):
    pass


# ── The mode itself ──────────────────────────────────────────────────────────

def test_the_suite_runs_as_an_instrument():
    """If this is False every other test here passes vacuously."""
    assert instrument.instrument_mode() is True


def test_the_mode_is_read_at_call_time_not_import_time():
    """The whole reason incident three happened.

    Settings resolved SCHEDULERS_ENABLED once at import, so a flag set later
    had no effect and a test believed it had frozen a scheduler it had in
    fact started. A protection whose correctness depends on import order is
    not a protection.
    """
    saved = os.environ.get(instrument.INSTRUMENT_ENV)
    try:
        os.environ[instrument.INSTRUMENT_ENV] = "0"
        assert instrument.instrument_mode() is False, (
            "the mode was cached; changing the environment had no effect")
        os.environ[instrument.INSTRUMENT_ENV] = "1"
        assert instrument.instrument_mode() is True
    finally:
        if saved is None:
            os.environ.pop(instrument.INSTRUMENT_ENV, None)
        else:
            os.environ[instrument.INSTRUMENT_ENV] = saved


def test_the_suite_carries_no_write_attestation():
    """A default attestation would make every refusal below unreachable."""
    assert instrument.allow_writes() is None


def test_a_contentless_attestation_is_not_an_attestation():
    """'1' says nothing. An attestation must name what is being attested, or
    it is the absence of one written confidently."""
    saved = os.environ.get(instrument.WRITE_ATTESTATION_ENV)
    try:
        for value in ("1", "true", "yes", "on", ""):
            os.environ[instrument.WRITE_ATTESTATION_ENV] = value
            assert instrument.allow_writes() is None, value
        os.environ[instrument.WRITE_ATTESTATION_ENV] = "scratch:asx_screener_scratch"
        assert instrument.allow_writes() == "scratch:asx_screener_scratch"
    finally:
        if saved is None:
            os.environ.pop(instrument.WRITE_ATTESTATION_ENV, None)
        else:
            os.environ[instrument.WRITE_ATTESTATION_ENV] = saved


# ── Mutation 1: the scheduler ────────────────────────────────────────────────

def test_importing_the_app_starts_no_scheduler():
    """The attempt, not the assumption: this starts the real lifespan.

    Without the protection it registers and starts nineteen jobs — which is
    what happened, twice, on the production host.
    """
    try:
        from fastapi.testclient import TestClient
        from app.main import app
    except Exception as exc:                                   # noqa: BLE001
        raise Skipped(f"needs the API stack: {type(exc).__name__}")

    with TestClient(app):
        scheduler = getattr(app.state, "scheduler", None)
        assert scheduler is not None, "the app published no scheduler"
        assert isinstance(scheduler, instrument.NullScheduler), (
            f"a REAL scheduler was created in instrument mode: "
            f"{type(scheduler).__name__}")
        assert scheduler.get_jobs() == []
        assert getattr(app.state, "schedulers_frozen") is True
        assert getattr(app.state, "scheduler_jobs") == 0


def test_the_null_scheduler_records_what_it_refused():
    """Silently dropping twenty registrations would leave nothing to notice.
    The declarations are kept so the suppression is visible."""
    null = instrument.NullScheduler()
    null.add_job(lambda: None, id="alert_checker")
    null.add_job(lambda: None, id="short_positions")
    null.start()
    assert null.get_jobs() == []
    assert null.refused == ["alert_checker", "short_positions"]


# ── Mutation 2: the serving cache ────────────────────────────────────────────

def test_a_cache_write_is_suppressed_and_recorded():
    """Attempted, not assumed — and suppressed rather than raised.

    The first version raised, and Gate B died: the gate asks the screener for
    a page, the route writes its response cache on the way out, and the
    exception broke the surface being measured. A response cache is something
    the application does on its own initiative; the requirement is that the
    write must not LAND, not that the request must fail. So it is declined,
    recorded and logged — and the suppression is asserted here, because a
    silent decline would be indistinguishable from a protection that has
    stopped working.
    """
    try:
        from app.core.cache import cache_set
    except Exception as exc:                                   # noqa: BLE001
        raise Skipped(f"needs the app stack: {type(exc).__name__}")

    before = len(instrument.SUPPRESSED)
    result = asyncio.run(cache_set("asx:instrument:probe", {"x": 1}))
    assert result is False, "the cache write reported success"
    assert len(instrument.SUPPRESSED) == before + 1, (
        "the write was declined without being recorded")
    assert "asx:instrument:probe" in instrument.SUPPRESSED[-1]


def test_a_cache_read_returns_a_miss_rather_than_serving_state():
    """Disabled, not merely read-only. A cached body was projected under
    whatever contract was current when it was stored, so a diagnostic reading
    it can assert against a response it did not cause — which is how Gate B
    could have passed on what an earlier run left behind."""
    try:
        from app.core.cache import cache_get
    except Exception as exc:                                   # noqa: BLE001
        raise Skipped(f"needs the app stack: {type(exc).__name__}")
    assert asyncio.run(cache_get("asx:anything")) is None


# ── Mutation 3: outbound mail ────────────────────────────────────────────────

def test_sending_mail_is_refused():
    """The one side effect that cannot be undone. A cache key expires and a
    scheduler can be stopped; a delivered message has reached a person."""
    try:
        from app.services import email
    except Exception as exc:                                   # noqa: BLE001
        raise Skipped(f"needs the app stack: {type(exc).__name__}")

    try:
        email._client()
    except instrument.InstrumentRefused as exc:
        assert "email" in str(exc)
        return
    raise AssertionError("instrument mode was allowed to build a mail client")


# ── The attestation actually opens the door ──────────────────────────────────

def test_an_attested_write_is_permitted():
    """Otherwise the mode is not a mode, it is a wall — and the next person
    who needs a legitimate scratch write will disable the protection
    wholesale rather than attest to one mutation."""
    saved = os.environ.get(instrument.WRITE_ATTESTATION_ENV)
    os.environ[instrument.WRITE_ATTESTATION_ENV] = "scratch:asx_screener_scratch"
    try:
        instrument.refuse("a probe write")          # must not raise
    finally:
        if saved is None:
            os.environ.pop(instrument.WRITE_ATTESTATION_ENV, None)
        else:
            os.environ[instrument.WRITE_ATTESTATION_ENV] = saved


def test_outside_instrument_mode_nothing_is_refused():
    """The application itself must be unaffected. If this fails, the
    protection has escaped its scope and production cannot send mail."""
    saved = os.environ.get(instrument.INSTRUMENT_ENV)
    os.environ[instrument.INSTRUMENT_ENV] = "0"
    try:
        instrument.refuse("outbound email")         # must not raise
    finally:
        if saved is None:
            os.environ.pop(instrument.INSTRUMENT_ENV, None)
        else:
            os.environ[instrument.INSTRUMENT_ENV] = saved


# ── The protection is early enough ───────────────────────────────────────────

def test_conftest_sets_the_mode_before_any_application_import():
    """Structural. The flag must be set in conftest, which pytest imports
    before collection — not in a test body, which is what failed."""
    conftest = (BACKEND / "tests" / "conftest.py").read_text(encoding="utf-8")
    assert "ASX_INSTRUMENT_MODE" in conftest
    flag = conftest.index("ASX_INSTRUMENT_MODE")
    for late in ("from app", "import app"):
        if late in conftest:
            assert flag < conftest.index(late), (
                f"conftest imports the application ({late!r}) before setting "
                f"the instrument flag")


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
