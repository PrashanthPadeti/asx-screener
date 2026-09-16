"""
Every write-producing stage proves where it actually connected
==============================================================
The P0-A-2 target-isolation gate.

discovery-15 ran cleanly against the scratch database, its production sentinel
was unchanged, and it flushed **production** Redis:

    Cache invalidated: 2 asx:screener:* keys flushed

The database redirect held perfectly. The second isolation dimension had no
redirect at all. So the rehearsal boundary is the **execution context**, not
the database, and database identity alone can never again be the isolation
proof.

Two properties are asserted here:

    every canonical-path writer calls the envelope gate, immediately after
    connecting and before any mutation

    the gate refuses a discovery run whose Redis is undeclared — the exact
    d15 hole — and refuses one that reached the wrong database

The first is textual because the failure mode is omission: a producer added
later without the gate cannot be caught by testing the producers that have it.

Run under pytest, or standalone:
    cd /opt/asx-screener/backend && ../asx-venv/bin/python tests/test_runtime_envelope.py
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from compute.engine.runtime_envelope import (  # noqa: E402
    DISCOVERY_REDIS_VAR, EXPECTED_DB_VAR, EnvelopeRefused, prove,
)

BACKEND = Path(__file__).resolve().parents[1]

#: Every stage on the path that can change, or feed, the 72 governed values.
#: Derived from docs/p0a_orchestration_manifest.md. A producer added to that
#: path without the gate fails here rather than being discovered by a
#: forensic run.
CANONICAL_PATH_WRITERS = {
    "compute/engine/daily_compute.py": "daily_compute",
    "compute/engine/technical_compute.py": "technical_compute",
    "compute/engine/halfyearly_compute.py": "halfyearly_compute",
    "compute/engine/period_metrics_compute.py": "period_metrics_compute",
    "compute/engine/yearly_compute.py": "yearly_compute",
    "compute/engine/composite_score.py": "composite_score",
    "scripts/eodhd/v2/transforms/transform_prices.py": "transform_prices",
    "scripts/eodhd/v2/build_screener_universe.py": "build_screener_universe",
}


class Cur:
    """A cursor that answers with the database it was told to be."""

    def __init__(self, db):
        self.db = db

    def execute(self, q):
        assert "current_database()" in q, (
            "the envelope must ask the live connection, never read the URL")

    def fetchone(self):
        return (self.db,)

    def close(self):
        pass


def _with_env(**env):
    """Run with exactly this environment, restoring afterwards."""
    class Ctx:
        def __enter__(self):
            self.saved = dict(os.environ)
            for k in (EXPECTED_DB_VAR, DISCOVERY_REDIS_VAR, "REDIS_URL"):
                os.environ.pop(k, None)
            os.environ.update({k: v for k, v in env.items() if v is not None})
        def __exit__(self, *a):
            os.environ.clear()
            os.environ.update(self.saved)
    return Ctx()


# ── The gate's decisions ─────────────────────────────────────────────────────

def test_production_is_unaffected():
    """No discovery variables means production. Wiring this gate into a
    producer must not be able to break the nightly pipeline."""
    with _with_env():
        env = prove("daily_compute", cursor=Cur("asx_screener"))
    assert env.database == "asx_screener"
    assert not env.discovery


def test_a_discovery_run_that_reached_production_is_refused():
    with _with_env(**{EXPECTED_DB_VAR: "asx_screener_scratch",
                      "REDIS_URL": "redis://localhost:6379/15",
                      DISCOVERY_REDIS_VAR: "isolated"}):
        try:
            prove("daily_compute", cursor=Cur("asx_screener"))
        except EnvelopeRefused as e:
            assert "asx_screener_scratch" in str(e)
        else:
            raise AssertionError("a production connection was permitted")


def test_undeclared_redis_in_a_discovery_run_is_refused():
    """The d15 incident, as a regression test.

    REDIS_URL unset means every cache call falls back to
    redis://localhost:6379/0 — production — while the database sentinel stays
    perfectly clean. That combination actually happened.
    """
    with _with_env(**{EXPECTED_DB_VAR: "asx_screener_scratch"}):
        try:
            prove("build_screener_universe",
                  cursor=Cur("asx_screener_scratch"))
        except EnvelopeRefused as e:
            assert "REDIS_URL is unset" in str(e)
        else:
            raise AssertionError(
                "a discovery run with undeclared Redis was permitted; this is "
                "exactly what flushed production keys in discovery-15")


def test_redis_pointing_at_production_is_refused_even_with_the_right_database():
    with _with_env(**{EXPECTED_DB_VAR: "asx_screener_scratch",
                      "REDIS_URL": "redis://localhost:6379/0"}):
        try:
            prove("build_screener_universe",
                  cursor=Cur("asx_screener_scratch"))
        except EnvelopeRefused:
            pass
        else:
            raise AssertionError(
                "database identity alone was accepted as the isolation proof")


def test_isolated_or_disabled_redis_is_permitted():
    for mode, url in (("isolated", "redis://localhost:6379/15"),
                      ("disabled", None)):
        with _with_env(**{EXPECTED_DB_VAR: "asx_screener_scratch",
                          "REDIS_URL": url, DISCOVERY_REDIS_VAR: mode}):
            env = prove("daily_compute", cursor=Cur("asx_screener_scratch"))
            assert env.discovery


# ── Outbound side effects ────────────────────────────────────────────────────

def _alert_log(**env):
    """Call send_failure_alert and return what it logged."""
    import logging
    from scripts.utils import alert

    records = []

    class Capture(logging.Handler):
        def emit(self, r):
            records.append(r.getMessage() if not r.args else r.msg % r.args)

    h = Capture()
    alert.log.addHandler(h)
    try:
        with _with_env(**env):
            alert.send_failure_alert(pipeline="daily", step="Step 7",
                                     target_date="2026-09-16", exit_code=1)
    finally:
        alert.log.removeHandler(h)
    return " ".join(records)


def test_a_discovery_run_does_not_email_the_admins():
    """The alert fires on the failure path — the one a rehearsal reaches most
    often — and would report a PRODUCTION failure that did not happen."""
    out = _alert_log(**{EXPECTED_DB_VAR: "asx_screener_scratch",
                        "RESEND_API_KEY": "re_live_key_shaped_value",
                        "ADMIN_EMAILS": "admin@example.com"})
    assert "SUPPRESSED" in out, (
        "a scratch-confined run was willing to email the real admins from the "
        f"production sender; it logged: {out!r}")
    assert "asx_screener_scratch" in out


def test_production_alerting_still_reaches_the_send_path():
    """Suppression must not become a silent permanent disablement.

    With no key configured the function reports exactly that, which proves it
    ran past the discovery guard rather than stopping at it.
    """
    out = _alert_log(**{"RESEND_API_KEY": "", "ADMIN_EMAILS": "a@example.com"})
    assert "SUPPRESSED" not in out
    assert "RESEND_API_KEY not set" in out


# ── Fault injection: reachable only from a real rehearsal ────────────────────

FAULT = "after_provisional_rebuild"


def _isolated(**extra):
    """The full set of conditions a fault needs. Individually removable."""
    env = {EXPECTED_DB_VAR: "asx_screener_scratch",
           "P0A_PRODUCTION_DB": "asx_screener",
           "P0A_DISCOVERY_MODE": "enabled",
           DISCOVERY_REDIS_VAR: "isolated",
           "REDIS_URL": "redis://localhost:6379/15",
           "P0A_DISCOVERY_FAULT": FAULT}
    env.update(extra)
    return {k: v for k, v in env.items() if v is not None}


def test_the_fault_fires_only_in_a_fully_isolated_rehearsal():
    from compute.engine.runtime_envelope import InjectedFault, discovery_fault
    with _with_env(**_isolated()):
        env = prove("universe_build", cursor=Cur("asx_screener_scratch"))
        try:
            discovery_fault(FAULT, env)
        except InjectedFault as e:
            assert "asx_screener_scratch" in str(e)
        else:
            raise AssertionError("the requested fault did not fire")


def test_a_fault_variable_against_production_refuses_before_any_work():
    """The dangerous case is not a fault that fails to fire.

    It is a fault variable left in an environment that resolves to production,
    where the safe-looking outcome is that nothing happens and the unsafe one
    is that something does. Every writer carrying the envelope gate refuses.
    """
    with _with_env(**{"P0A_DISCOVERY_FAULT": FAULT}):
        try:
            prove("universe_build", cursor=Cur("asx_screener"))
        except EnvelopeRefused as e:
            assert "before any work" in str(e)
        else:
            raise AssertionError(
                "a production run carrying a fault variable was permitted")


def test_every_isolation_condition_is_individually_required():
    """Each condition on its own is satisfiable by an environment that is not
    actually isolated, so removing any one must refuse.

    Exercised against refuse_faults_outside_discovery rather than prove().
    enforce() carries its own database and Redis checks which fire first, so
    going through prove() would let two of these pass for the wrong reason —
    the guard would be testing the outer checks twice and reporting coverage
    it does not have.
    """
    from compute.engine.runtime_envelope import (
        Envelope, refuse_faults_outside_discovery,
    )

    def envelope():
        return Envelope(stage="universe_build",
                        database="asx_screener_scratch",
                        expected_db="asx_screener_scratch",
                        discovery=True,
                        redis_endpoint="localhost:6379",
                        redis_logical_db="15")

    removals = {
        "discovery mode off": {"P0A_DISCOVERY_MODE": None},
        "discovery mode merely truthy": {"P0A_DISCOVERY_MODE": "0"},
        "no expected db": {EXPECTED_DB_VAR: None},
        "production undeclared": {"P0A_PRODUCTION_DB": None},
        "target IS production": {"P0A_PRODUCTION_DB": "asx_screener_scratch"},
        "redis undeclared": {DISCOVERY_REDIS_VAR: None},
        "redis neither isolated nor disabled": {DISCOVERY_REDIS_VAR: "maybe"},
    }
    for label, removal in removals.items():
        env_vars = _isolated()
        for k, v in removal.items():
            env_vars.pop(k, None) if v is None else env_vars.update({k: v})

        e = envelope()
        if removal.get(EXPECTED_DB_VAR, "") is None:
            e.expected_db = None          # the envelope observes it too

        with _with_env(**env_vars):
            try:
                refuse_faults_outside_discovery(e)
            except EnvelopeRefused:
                continue
            raise AssertionError(
                f"a fault was armed with {label}: the conditions are not all "
                f"required, so 'isolated' can be claimed without being true")


def test_a_fault_is_refused_when_the_process_landed_somewhere_unexpected():
    """A third database, neither the expected one nor production.

    Every other condition here is satisfiable by an environment that merely
    says the right things; only comparing the LIVE connection catches a child
    that resolved its own URL and landed somewhere else entirely. The
    production check does not cover this case, which is exactly why it needs
    its own.
    """
    from compute.engine.runtime_envelope import (
        Envelope, refuse_faults_outside_discovery,
    )

    # Asserted against refuse_faults_outside_discovery directly, not through
    # prove(). enforce() has its own database check that fires first, so
    # calling prove() here would pass for the wrong reason and this guard
    # would be inert — it would be testing the outer check twice.
    env = Envelope(stage="universe_build",
                   database="asx_screener_someone_elses",
                   expected_db="asx_screener_scratch",
                   discovery=True,
                   redis_endpoint="localhost:6379", redis_logical_db="15")
    with _with_env(**_isolated()):
        try:
            refuse_faults_outside_discovery(env)
        except EnvelopeRefused as e:
            assert "asx_screener_someone_elses" in str(e)
        else:
            raise AssertionError(
                "a fault was armed in a process that reached an unexpected "
                "database")


def test_email_suppression_rides_on_the_variable_the_fault_gate_requires():
    """The coupling, asserted where it can actually bite.

    A fault may only fire when P0A_EXPECTED_DB is set, and alert.py suppresses
    mail on that same variable — so "production email is disabled" comes free
    with the fault conditions. Duplicating it as another runtime branch would
    be a second copy of one check rather than a second safeguard; what no
    runtime check can see is alert.py's condition being changed, so that is
    what this asserts.
    """
    alert_src = (BACKEND / "scripts/utils/alert.py").read_text(encoding="utf-8")
    code = "\n".join(ln for ln in alert_src.splitlines()
                     if not ln.strip().startswith("#"))
    assert f'os.getenv("{EXPECTED_DB_VAR}"' in code, (
        f"alert.py no longer suppresses on {EXPECTED_DB_VAR}, so a rehearsal "
        f"fault can now fire while production email is live")
    assert "SUPPRESSED" in code


def test_an_unknown_fault_name_is_refused_rather_than_ignored():
    """A typo that silently injects nothing makes the adversarial case pass by
    not happening."""
    with _with_env(**_isolated(P0A_DISCOVERY_FAULT="after_provisonal_rebuild")):
        try:
            prove("universe_build", cursor=Cur("asx_screener_scratch"))
        except EnvelopeRefused as e:
            assert "not a known fault point" in str(e)
        else:
            raise AssertionError("a misspelled fault name was ignored")


def test_a_fault_point_not_requested_is_a_no_op():
    from compute.engine.runtime_envelope import discovery_fault
    with _with_env(**_isolated(P0A_DISCOVERY_FAULT=None)):
        env = prove("universe_build", cursor=Cur("asx_screener_scratch"))
        discovery_fault(FAULT, env)          # must not raise


def test_a_call_site_cannot_invent_a_fault_point():
    """The allowlist and the call sites must not drift apart."""
    from compute.engine.runtime_envelope import discovery_fault
    with _with_env(**_isolated()):
        env = prove("universe_build", cursor=Cur("asx_screener_scratch"))
        try:
            discovery_fault("some_undeclared_point", env)
        except AssertionError as e:
            assert "not a declared fault point" in str(e)
        else:
            raise AssertionError("an undeclared fault point was accepted")


def test_production_is_still_unaffected_when_no_fault_is_requested():
    with _with_env():
        env = prove("daily_compute", cursor=Cur("asx_screener"))
        assert not env.discovery


# ── The gate is actually present ─────────────────────────────────────────────

def test_every_canonical_path_writer_proves_its_envelope():
    """Omission is the failure mode, so presence is asserted directly."""
    missing = []
    for rel, stage in CANONICAL_PATH_WRITERS.items():
        path = BACKEND / rel
        assert path.exists(), f"{rel} has moved; this guard is now inert"
        code = "\n".join(ln for ln in path.read_text(encoding="utf-8").splitlines()
                         if not ln.strip().startswith("#"))
        if f'_prove_envelope("{stage}"' not in code:
            missing.append(rel)

    assert not missing, (
        f"these stages write without proving where they connected: {missing}. "
        f"An inherited environment is intent; a live connection is fact.")


def test_the_gate_is_the_first_statement_after_connecting():
    """After connecting, and before anything else runs.

    Scanning forward for `INSERT INTO` would be nearly inert here: six of these
    eight stages hold their SQL in module-level constants declared *above* the
    connection, so there is no mutation literal after it to find. A guard that
    examines nothing passes for the wrong reason.

    The checkable property is stronger. Between the connect and the gate there
    must be nothing executable but the gate's own import — so no query can be
    issued, on any path, before the process has proved where it landed.
    """
    for rel in CANONICAL_PATH_WRITERS:
        lines = (BACKEND / rel).read_text(encoding="utf-8").splitlines()
        conn = next(i for i, l in enumerate(lines) if "psycopg2.connect(" in l)
        gate = next(i for i, l in enumerate(lines) if "_prove_envelope(" in l
                    and "import" not in l)
        assert conn < gate, f"{rel}: the gate precedes the connection it proves"

        for offset, line in enumerate(lines[conn + 1:gate], start=conn + 2):
            body = line.strip()
            if not body or body.startswith("#"):
                continue
            assert "import" in body and "runtime_envelope" in body, (
                f"{rel}:{offset}: {body!r} runs between the connection and the "
                f"proof of where that connection landed. Nothing may execute "
                f"in that window but the gate's own import.")


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
