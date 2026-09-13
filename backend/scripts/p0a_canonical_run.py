#!/usr/bin/env python
"""
The canonical run driver
========================
The only path that can create a production-shaped lifecycle. Direct stage
invocation may compute or diagnose; only this can open a run capable of
finalisation. That is deliberate: an alternate publication path is exactly the
kind of thing that grows back later, and the resolver cannot tell one lifecycle
from another once the rows exist.

    verify target database
    verify schema capability
    evaluate source health
    require publishable source health
    create_run(the health that was evaluated)
    yearly_compute(run_id)      -> require stage success
    daily_compute(run_id)       -> require stage success
    universe_build(run_id)      -> require stage success
    composite_score(run_id)     -> canonical commit, validate, finalise

Three outcomes, with clean semantics:

    precondition failure   no run row. Nothing began. A missing lifecycle
                           table, an unsupported schema or an unhealthy feed
                           are not failed computations — there is nothing to
                           attribute them to.

    execution failure      the immutable run remains as forensic evidence,
                           with whatever terminal stage evidence exists and no
                           finalisation. The resolver will not select it.

    publication            finalisation exists; the resolver may select it.

Fail-closed on source health, with no override. A canonical run is opened only
when its declared prerequisites are capable of producing a publishable
contract, and "record unhealthy and proceed" would give the run identity to a
computation that cannot reach publication — which is the weaker property the
lifecycle was built to replace.

Usage:
    python scripts/p0a_canonical_run.py                 # dry preconditions
    python scripts/p0a_canonical_run.py --execute
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import psycopg2  # noqa: E402

from app.core.db import get_database_url_sync  # noqa: E402
from compute.engine.metric_states import (  # noqa: E402
    LATEST_MODEL_VERSION, SourceHealth,
)
from compute.engine.run_stages import REQUIRED_STAGES, stages_passed  # noqa: E402
from compute.engine.universe_writer import (  # noqa: E402
    create_run, persisted_governed, verify_storage,
)

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s  %(levelname)-8s %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("canonical")

PYBIN = sys.executable


class PreconditionFailed(RuntimeError):
    """Nothing began. No run identity was created."""


# ── Schema capability, not merely table existence ────────────────────────────

def verify_schema(cur) -> None:
    """A half-applied migration is not materially better than no migration.

    Checks the capability the lifecycle code depends on — tables, the keys
    that make stage evidence terminal, and the triggers that make it
    append-only. A compute_run_stages table without its primary key would
    accept two contradictory rows for one stage, and the resolver would then
    find a success beside a failure and believe the success.

    Every check runs, so one invocation reports everything that is missing
    rather than sending an operator round the loop once per object.
    """
    checks: list[tuple[str, str]] = [
        ("table screener.compute_runs",
         "SELECT to_regclass('screener.compute_runs') IS NOT NULL"),
        ("table screener.compute_run_stages",
         "SELECT to_regclass('screener.compute_run_stages') IS NOT NULL"),
        ("table screener.compute_run_finalizations",
         "SELECT to_regclass('screener.compute_run_finalizations') IS NOT NULL"),

        # Terminal evidence depends on these, not on the tables alone.
        ("primary key on (run_id, stage_name)", """
            SELECT count(*) = 1 FROM pg_constraint
             WHERE conrelid = 'screener.compute_run_stages'::regclass
               AND contype = 'p'"""),
        ("primary key on finalizations(run_id)", """
            SELECT count(*) = 1 FROM pg_constraint
             WHERE conrelid = 'screener.compute_run_finalizations'::regclass
               AND contype = 'p'"""),
        ("status CHECK on compute_run_stages", """
            SELECT count(*) >= 1 FROM pg_constraint
             WHERE conrelid = 'screener.compute_run_stages'::regclass
               AND contype = 'c'"""),

        ("append-only trigger on compute_run_stages", """
            SELECT count(*) = 1 FROM pg_trigger
             WHERE tgrelid = 'screener.compute_run_stages'::regclass
               AND NOT tgisinternal"""),
        ("append-only trigger on finalizations", """
            SELECT count(*) = 1 FROM pg_trigger
             WHERE tgrelid = 'screener.compute_run_finalizations'::regclass
               AND NOT tgisinternal"""),
        ("immutability trigger on compute_runs", """
            SELECT count(*) = 1 FROM pg_trigger
             WHERE tgrelid = 'screener.compute_runs'::regclass
               AND NOT tgisinternal"""),

        ("screener.universe.metric_states", """
            SELECT count(*) = 1 FROM information_schema.columns
             WHERE table_schema='screener' AND table_name='universe'
               AND column_name='metric_states'"""),
        ("screener.universe.compute_run_id", """
            SELECT count(*) = 1 FROM information_schema.columns
             WHERE table_schema='screener' AND table_name='universe'
               AND column_name='compute_run_id'"""),
        ("screener.universe.annual_periods", """
            SELECT count(*) = 1 FROM information_schema.columns
             WHERE table_schema='screener' AND table_name='universe'
               AND column_name='annual_periods'"""),
    ]

    missing = []
    for label, sql in checks:
        try:
            cur.execute(sql)
            ok = bool(cur.fetchone()[0])
        except Exception as exc:                      # noqa: BLE001
            cur.connection.rollback()
            ok = False
            label = f"{label} ({type(exc).__name__})"
        log.info("  %-45s %s", label, "ok" if ok else "MISSING")
        if not ok:
            missing.append(label)

    if missing:
        raise PreconditionFailed(
            "schema capability missing: " + "; ".join(missing)
            + ". Apply migrations/add_compute_run_stages.sql (and "
              "add_annual_periods_to_universe.sql) before opening a run.")

    # Every column this model version promises must exist too. A governed
    # metric with no column would abort mid-write, after the run exists.
    verify_storage(cur, LATEST_MODEL_VERSION)
    log.info("  %-45s ok", f"storage columns for {LATEST_MODEL_VERSION}")


#: What the driver must be running under. Stated here rather than derived from
#: the constant it is checking, so a change to that constant fails this rather
#: than silently redefining what "correct" means.
EXPECTED_MODEL = "FACTOR_MODEL_V2"
EXPECTED_GOVERNED = 72
EXPECTED_STAGES = ("yearly_compute", "daily_compute", "universe_build")


def verify_activation() -> dict:
    """The contract this run would execute under, printed and asserted.

    A one-line change to LATEST_MODEL_VERSION is visually small and moves
    every canonical path between a 40-metric contract and a 72-metric one.
    The run has to say which it is executing before it computes anything --
    otherwise a discovery run could exercise V1 end to end, finalise cleanly,
    and prove nothing about the contract it was built to test.
    """
    mapping = persisted_governed(LATEST_MODEL_VERSION)
    facts = {"model": LATEST_MODEL_VERSION,
             "governed": len(mapping),
             "stages": tuple(REQUIRED_STAGES)}

    log.info("model version              : %s", facts["model"])
    log.info("persisted governed metrics : %s", facts["governed"])
    log.info("required stages            : %s", ", ".join(facts["stages"]))

    wrong = []
    if facts["model"] != EXPECTED_MODEL:
        wrong.append(f"model is {facts['model']}, expected {EXPECTED_MODEL}")
    if facts["governed"] != EXPECTED_GOVERNED:
        wrong.append(f"{facts['governed']} governed metrics, expected "
                     f"{EXPECTED_GOVERNED}")
    if facts["stages"] != EXPECTED_STAGES:
        wrong.append(f"required stages are {facts['stages']}, expected "
                     f"{EXPECTED_STAGES}")
    if wrong:
        raise PreconditionFailed(
            "the activated contract is not the one this driver expects: "
            + "; ".join(wrong))
    return facts


# ── Source health, evaluated once ────────────────────────────────────────────

def assess_source_health(cur, run_id=None) -> SourceHealth:
    """The feed's state, as one object.

    Evaluated once and then both tested and recorded, rather than computed
    twice. Recomputing it at insertion would leave a gap — small, but real —
    between the state that admitted the run and the state the run declares it
    ran under, and the run declaration exists precisely to be the record of
    that decision.
    """
    from compute.engine.daily_compute import fetch_feed_health

    feed = fetch_feed_health(cur)
    return SourceHealth(
        run_at=datetime.now(timezone.utc),
        unhealthy_sources=() if feed.healthy else ("dividends",),
        detail={} if feed.healthy else {"dividends": feed.reason},
        factor_model_version=LATEST_MODEL_VERSION,
        run_id=run_id)


def require_publishable(health: SourceHealth) -> None:
    """Refuse to open a run that cannot reach publication.

    Not a judgement about whether the numbers would be interesting. A run
    under an unhealthy source withholds the Income factor and the composite
    universe-wide — correctly — but it can never produce the contract this
    driver exists to publish, so giving it a run identity would record an
    attempt that was structurally incapable of succeeding.

    There is deliberately no override. If an unhealthy-source experiment is
    ever needed it belongs in a separate mode that is structurally forbidden
    from finalising, not in a flag that relaxes this one.
    """
    if health.healthy:
        return
    detail = "; ".join(f"{k}: {v}" for k, v in (health.detail or {}).items())
    raise PreconditionFailed(
        f"source health is not publishable: {', '.join(health.unhealthy_sources)}"
        + (f" — {detail}" if detail else "")
        + ". Repair the source and prove it healthy before opening a run.")


# ── Stages ───────────────────────────────────────────────────────────────────

def run_stage(label: str, argv: list[str]) -> None:
    log.info("── %s", label)
    result = subprocess.run(argv, cwd=str(BACKEND))
    if result.returncode != 0:
        raise RuntimeError(f"{label} exited {result.returncode}")


def require_stage(conn, run_id: int, stage: str) -> None:
    cur = conn.cursor()
    try:
        outstanding = stages_passed(cur, run_id, [stage])
    finally:
        cur.close()
    if outstanding:
        raise RuntimeError(
            f"{stage} recorded no success for run {run_id}. Its evidence is in "
            f"screener.compute_run_stages; the run stays unfinalised and the "
            f"resolver will not select it.")
    log.info("   %s: stage SUCCESS recorded", stage)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true",
                        help="Run the lifecycle. Without it only the "
                             "preconditions are evaluated and no run is "
                             "created.")
    parser.add_argument("--allow-production", action="store_true",
                        help="Permit running against the database named by "
                             "DATABASE_URL when it is not a scratch one.")
    args = parser.parse_args()

    conn = psycopg2.connect(get_database_url_sync())
    cur = conn.cursor()

    cur.execute("SELECT current_database()")
    database = cur.fetchone()[0]
    log.info("target database: %s", database)

    if "scratch" not in database and not args.allow_production:
        log.error("REFUSING: '%s' is not a scratch database. Pass "
                  "--allow-production deliberately.", database)
        return 2

    # ── Preconditions. A failure here creates nothing. ───────────────────────
    log.info("── preconditions")
    try:
        verify_activation()
        verify_schema(cur)
        health = assess_source_health(cur)
        log.info("  source health: %s",
                 "healthy" if health.healthy
                 else f"UNHEALTHY {health.unhealthy_sources} {health.detail}")
        require_publishable(health)
    except PreconditionFailed as exc:
        log.error("PRECONDITION FAILED — no run was created.")
        log.error("%s", exc)
        return 2

    if not args.execute:
        log.info("Preconditions pass. Re-run with --execute to open a run.")
        return 0

    # ── From here a run exists, and survives failure as evidence. ────────────
    run = create_run(cur, "canonical_driver", health, LATEST_MODEL_VERSION)
    conn.commit()
    log.info("run %s created under %s", run.run_id, LATEST_MODEL_VERSION)

    try:
        run_stage("yearly_compute",
                  [PYBIN, "compute/engine/yearly_compute.py",
                   "--run-id", str(run.run_id)])
        require_stage(conn, run.run_id, "yearly_compute")

        # Both feed universe_build, so both precede it. Their order relative
        # to each other does not matter: neither reads the other's output.
        run_stage("daily_compute",
                  [PYBIN, "compute/engine/daily_compute.py",
                   "--run-id", str(run.run_id)])
        require_stage(conn, run.run_id, "daily_compute")

        run_stage("universe_build",
                  [PYBIN, "scripts/eodhd/v2/build_screener_universe.py",
                   "--run-id", str(run.run_id)])
        require_stage(conn, run.run_id, "universe_build")

        # composite_score performs the canonical commit: it re-emits every
        # governed value with the sidecar and the attribution, validates, and
        # finalises — all in one transaction.
        run_stage("composite_score (canonical commit)",
                  [PYBIN, "compute/engine/composite_score.py",
                   "--run-id", str(run.run_id)])

        cur.execute("""
            SELECT rows_written, persistence_violations
              FROM screener.compute_run_finalizations WHERE run_id = %s;""",
            (run.run_id,))
        final = cur.fetchone()
        if final is None:
            raise RuntimeError(
                "the canonical commit did not finalise the run. The rows were "
                "rolled back and the run stays unpublished.")

        log.info("─" * 60)
        log.info("PUBLISHED: run %s, %s rows, %s violations",
                 run.run_id, f"{final[0]:,}", final[1])
        log.info("Required stages: %s", ", ".join(REQUIRED_STAGES))
        return 0

    except Exception as exc:                          # noqa: BLE001
        log.error("─" * 60)
        log.error("RUN %s FAILED: %s", run.run_id, exc)
        log.error("The run row and its stage evidence remain. There is no "
                  "finalisation, so no resolver will select it. Start a new "
                  "run rather than repairing this one.")
        return 1
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
