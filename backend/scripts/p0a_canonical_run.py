#!/usr/bin/env python
"""
The canonical run driver
========================
The only path that can create a production-shaped lifecycle. Direct stage
invocation may compute or diagnose; only this can open a run capable of
finalisation. That is deliberate: an alternate publication path is exactly the
kind of thing that grows back later, and the resolver cannot tell one lifecycle
from another once the rows exist.

    prove the runtime envelope
    verify schema capability
    verify the plan is a valid canonical plan
    evaluate source health
    require publishable source health
    plan preconditions, including the yearly reuse contract
    create_run(plan)                  -> plan identity is immutable metadata
    for each producer in plan.stages[:-1]:
        dispatch a FIXED known command with production-shaped arguments
        require its terminal SUCCESS evidence when the plan requires it
    discovery_fault("after_provisional_rebuild")   -> rehearsal only
    composite_score(run_id, plan)     -> publication-time fingerprint recheck,
                                         canonical commit, read-back, finalise

The stage list comes from the plan; the commands come from a fixed mapping in
this module. A plan names stages, never executables -- see STAGE_COMMANDS.

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
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import psycopg2  # noqa: E402

from app.core.db import get_database_url_sync  # noqa: E402
from compute.engine.metric_states import (  # noqa: E402
    LATEST_MODEL_VERSION, SourceHealth,
)
from compute.engine.run_stages import stages_passed  # noqa: E402
from compute.engine.run_plans import (  # noqa: E402
    PLANS, PlanPreconditionFailed, open_plan,
)
from compute.engine.runtime_envelope import (  # noqa: E402
    InjectedFault, discovery_fault, prove as prove_envelope,
)
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
#: The static REQUIRED_STAGES tuple is no longer what publication uses -- each
#: plan carries its own required set -- so asserting equality against it would
#: be a tripwire on something the driver has stopped consulting.
#:
#: What replaces it are the structural properties a canonical plan must have,
#: checked against the plan actually being executed. Not a second copy of the
#: stage list: a duplicated list drifts, and the drift then reads as a defect
#: in whichever copy was not edited.
def verify_plan(plan) -> None:
    wrong = []
    if not plan.stages or plan.stages[-1] != "composite_score":
        wrong.append(f"{plan.name} does not end in canonical publication")
    if "universe_build" not in plan.required:
        wrong.append(f"{plan.name} would publish without requiring the "
                     f"universe build that produced the governed values")
    if "composite_score" in plan.required:
        wrong.append(f"{plan.name} requires evidence from the stage that "
                     f"writes the finalisation, which cannot exist yet")
    for stage in plan.reuses:
        if stage in plan.required:
            wrong.append(f"{plan.name} reuses {stage} and also requires its "
                         f"evidence under this run")
    if wrong:
        raise PreconditionFailed(
            "the run plan is not a valid canonical plan: " + "; ".join(wrong))

    log.info("plan                       : %s", plan.name)
    log.info("plan stages                : %s", ", ".join(plan.stages))
    log.info("plan required evidence     : %s", ", ".join(plan.required))
    log.info("plan reuses                : %s",
             ", ".join(plan.reuses) or "nothing")


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
             "governed": len(mapping)}

    log.info("model version              : %s", facts["model"])
    log.info("persisted governed metrics : %s", facts["governed"])

    wrong = []
    if facts["model"] != EXPECTED_MODEL:
        wrong.append(f"model is {facts['model']}, expected {EXPECTED_MODEL}")
    if facts["governed"] != EXPECTED_GOVERNED:
        wrong.append(f"{facts['governed']} governed metrics, expected "
                     f"{EXPECTED_GOVERNED}")
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

# ── The stage dispatcher ─────────────────────────────────────────────────────
#
# A fixed Python mapping from stage name to argv builder. Deliberately boring:
# no executable names taken from the plan, no command strings, no shell
# adapter, shell=False throughout. A plan is a list of names this module
# already knows how to run, and an unknown name is an error before the run
# starts rather than a subprocess failure halfway through one.
#
# The arguments are PRODUCTION-SHAPED, not merely production code. The point of
# the rehearsal is whether the nightly sequence composes, so each stage is
# invoked the way its real cadence invokes it. transform_prices is the one that
# matters: the daily pipeline passes --from-date, and exercising its
# full-replacement mode here would answer a different question. That mode's
# atomicity work stands on its own; it is not what this run is testing.


def _daily_window() -> str:
    """The same incremental boundary the nightly pipeline uses."""
    return (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()


#: stage name -> argv builder. Each takes the run id and returns a full argv.
STAGE_COMMANDS = {
    "transform_prices": lambda rid: [
        PYBIN, "scripts/eodhd/v2/transforms/transform_prices.py",
        "--from-date", _daily_window(), "--run-id", str(rid)],
    "yearly_compute": lambda rid: [
        PYBIN, "compute/engine/yearly_compute.py", "--run-id", str(rid)],
    "daily_compute": lambda rid: [
        PYBIN, "compute/engine/daily_compute.py", "--run-id", str(rid)],
    "technical_compute": lambda rid: [
        PYBIN, "compute/engine/technical_compute.py", "--run-id", str(rid)],
    "halfyearly_compute": lambda rid: [
        PYBIN, "compute/engine/halfyearly_compute.py", "--run-id", str(rid)],
    "period_metrics_compute": lambda rid: [
        PYBIN, "compute/engine/period_metrics_compute.py", "--run-id", str(rid)],
    "universe_build": lambda rid: [
        PYBIN, "scripts/eodhd/v2/build_screener_universe.py",
        "--run-id", str(rid)],
}


def dispatch(stage: str, run_id: int) -> list[str]:
    """argv for one known stage. An unknown name is a defect, not a failure."""
    if stage not in STAGE_COMMANDS:
        raise PreconditionFailed(
            f"no command is defined for stage '{stage}'. The plan names a "
            f"stage this driver does not know how to run; add it to "
            f"STAGE_COMMANDS deliberately rather than letting the plan supply "
            f"an executable.")
    return STAGE_COMMANDS[stage](run_id)


def run_stage(label: str, argv: list[str]) -> None:
    log.info("── %s", label)
    # shell=False (the default) and an argv list, never a string: nothing here
    # should be able to become a shell command.
    result = subprocess.run(argv, cwd=str(BACKEND), shell=False)
    if result.returncode != 0:
        raise RuntimeError(f"{label} exited {result.returncode}")


def run_producer(conn, plan, stage: str, run_id: int) -> None:
    """Execute one producer and require its terminal SUCCESS evidence.

    Two separate conditions, because a zero exit is not completion proof --
    that is the whole reason the stage evidence exists. A producer can exit 0
    having written a subset of its population, and the evidence is what says
    whether it covered the population it owed.

    Only stages the plan REQUIRES are checked for evidence. A plan may run a
    stage whose success is not a condition of publishing.
    """
    run_stage(f"{stage} (plan {plan.name})", dispatch(stage, run_id))
    if stage in plan.required:
        require_stage(conn, run_id, stage)


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
    parser.add_argument("--plan", default="FULL_FUNDAMENTALS_CANONICAL",
                        choices=tuple(PLANS),
                        help="Which run plan to execute. The plan decides "
                             "which stages run, which stage evidence its "
                             "publication requires, and what it may reuse.")
    args = parser.parse_args()

    plan = PLANS[args.plan]

    conn = psycopg2.connect(get_database_url_sync())
    cur = conn.cursor()

    # The driver proves its own envelope like every write-producing child, and
    # keeps it: the fault seam below needs the OBSERVED envelope, not a fresh
    # reading of the environment that could disagree with it.
    #
    # This also refuses immediately if a fault variable is present while the
    # envelope resolves production — before any precondition runs, and long
    # before a run exists.
    envelope = prove_envelope("canonical_driver", conn)

    database = envelope.database
    log.info("target database: %s", database)

    if "scratch" not in database and not args.allow_production:
        log.error("REFUSING: '%s' is not a scratch database. Pass "
                  "--allow-production deliberately.", database)
        return 2

    # ── Preconditions. A failure here creates nothing. ───────────────────────
    log.info("── preconditions")
    try:
        verify_activation()
        verify_plan(plan)
        verify_schema(cur)
        # Plan preconditions, including the yearly reuse contract. Evaluated
        # here so a stale reused prerequisite prevents the run from opening at
        # all, rather than leaving an abandoned run id behind for a condition
        # that was knowable without computing anything.
        open_plan(cur, plan, log)
        health = assess_source_health(cur)
        log.info("  source health: %s",
                 "healthy" if health.healthy
                 else f"UNHEALTHY {health.unhealthy_sources} {health.detail}")
        require_publishable(health)
    except (PreconditionFailed, PlanPreconditionFailed) as exc:
        log.error("PRECONDITION FAILED — no run was created.")
        log.error("%s", exc)
        return 2

    if not args.execute:
        log.info("Preconditions pass. Re-run with --execute to open a run.")
        return 0

    # ── From here a run exists, and survives failure as evidence. ────────────
    run = create_run(cur, "canonical_driver", health, LATEST_MODEL_VERSION,
                     plan_name=plan.name)
    conn.commit()
    log.info("run %s created under %s / plan %s",
             run.run_id, LATEST_MODEL_VERSION, plan.name)

    try:
        # The plan's producers, in the plan's order, which comes from the
        # dependency graph rather than from any schedule. The last stage is
        # always the canonical tail and is run separately below, after the
        # fault seam: everything before it is a producer, and the boundary
        # between them is exactly where the temporal guarantee is vulnerable.
        for stage in plan.stages[:-1]:
            run_producer(conn, plan, stage, run.run_id)

        # ── The vulnerable boundary ──────────────────────────────────────────
        # The provisional rebuild has committed. The old canonical claim is
        # revoked — metric_states and compute_run_id are NULL across the
        # population — and the new one has not been made. The governed surface
        # is fail-closed right now, and it stays that way unless the tail below
        # completes.
        #
        # A no-op in every run except a rehearsal that explicitly asked for
        # this fault from inside a proven-isolated envelope. If the fault
        # variable were set anywhere else, the envelope gate would already have
        # refused this process before it wrote anything.
        discovery_fault("after_provisional_rebuild", envelope, log)

        # composite_score performs the canonical commit: it re-emits every
        # governed value with the sidecar and the attribution, validates, and
        # finalises — all in one transaction.
        run_stage("composite_score (canonical commit)",
                  [PYBIN, "compute/engine/composite_score.py",
                   "--run-id", str(run.run_id),
                   "--plan", plan.name])

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
        log.info("Plan: %s | required evidence: %s",
                 plan.name, ", ".join(plan.required))
        return 0

    except InjectedFault as fault:
        # Deliberate, and the point of the run. Logged apart from a real
        # failure so the rehearsal transcript cannot be misread later as an
        # unexplained outage at this boundary.
        log.error("─" * 60)
        log.error("RUN %s STOPPED BY INJECTED FAULT: %s", run.run_id, fault)
        log.error("Expected state now: the provisional rebuild is committed, "
                  "every governed row is un-attributed (compute_run_id IS "
                  "NULL, metric_states IS NULL), run %s has universe_build "
                  "SUCCESS and no finalisation, and the governed surface "
                  "fails closed. Recovery is a NEW run, not a repair of this "
                  "one.", run.run_id)
        return 1

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
