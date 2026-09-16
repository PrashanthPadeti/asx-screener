"""
Two plans, named explicitly
===========================
Not a dependency scheduler. Two run shapes, each stating which stages it runs
and which stage evidence its canonical publication requires.

    FULL_FUNDAMENTALS_CANONICAL   fundamentals refresh; yearly_compute runs
    DAILY_CANONICAL               daily producers; yearly output is REUSED

The distinction that matters is not cadence, it is what the run computes for
itself versus what it inherits. A daily run must not fail because
yearly_compute did not run that day -- reusing the weekly output is the
intended behaviour. What it must not do is *assume* that output is still
current.

Cadence and correctness are separate
------------------------------------
A single growing REQUIRED_STAGES tuple would conflate them: every stage any
plan runs would become mandatory for every plan, so the daily run would have
to re-run yearly_compute purely to satisfy its own bookkeeping. Prerequisites
are therefore per-plan.

The reuse contract
------------------
`DAILY_CANONICAL` may reuse market.yearly_metrics only when the current
fingerprint of yearly_compute's entire input set equals the one a successful
yearly_compute proved. Not "a successful yearly_compute happened less than
seven days ago" -- that permits a fundamentals correction to land on Tuesday
while daily canonical runs keep publishing Monday's yearly output, which is
precisely the stale-input problem P0-A exists to end.

A fingerprint mismatch is NOT a failed daily computation. Nothing has computed
anything yet. It is a plan precondition failure -- the yearly output no longer
represents current fundamentals -- and it is evaluated BEFORE a run is created,
so the lifecycle stays:

    plan/source precondition failure   -> no run
    execution failure after creation   -> run + immutable FAILED evidence
    successful execution               -> immutable SUCCESS evidence
    valid complete run                 -> finalisation

Creating a run and only then discovering that its deliberately reused
prerequisite was stale would leave an abandoned run id behind for a condition
that was knowable in advance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


class PlanPreconditionFailed(RuntimeError):
    """The plan may not open a run. No run id has been created."""


@dataclass(frozen=True)
class RunPlan:
    name: str

    #: Stages this plan executes, in dependency order. The order comes from the
    #: dependency graph in docs/p0a_orchestration_manifest.md, not from the
    #: schedule a cron entry happens to use.
    stages: tuple[str, ...]

    #: Stage evidence that must exist, and be successful, under THIS run before
    #: its canonical publication may finalise. A subset of `stages`: a stage
    #: can be worth running without its success being a condition of publishing
    #: governed values.
    required: tuple[str, ...]

    #: Producers whose output this plan inherits rather than computes. Each
    #: needs a currentness proof, because inheriting an output is a claim about
    #: it.
    reuses: tuple[str, ...] = ()

    description: str = ""

    #: Whether a NEW run may be opened under this plan. LEGACY_CANONICAL exists
    #: only to describe runs published before plans did, so that the resolver
    #: can validate them against the contract they actually met. Choosing it
    #: for new work would publish under a weaker contract than either real
    #: plan.
    executable: bool = True

    def __post_init__(self):
        unknown = set(self.required) - set(self.stages)
        assert not unknown, (
            f"{self.name} requires {sorted(unknown)}, which it never runs. A "
            f"prerequisite the plan cannot satisfy is a plan that can never "
            f"publish.")
        overlap = set(self.reuses) & set(self.stages)
        assert not overlap, (
            f"{self.name} both runs and reuses {sorted(overlap)}. One of those "
            f"is wrong, and which one decides whether a currentness proof is "
            f"needed.")


#: The daily producers, in dependency order.
#:
#: transform_prices feeds every price-derived producer, so it comes first;
#: daily/technical/halfyearly/period all feed the universe build; the universe
#: build feeds the canonical writer. composite_score is the canonical tail --
#: the commit, read-back and finalisation -- and under the new orchestration it
#: runs DAILY, not weekly. Four of the five direct input families to the
#: governed columns change daily, so a weekly canonical tail leaves a finalised
#: contract valid for hours rather than a week.
_DAILY_PRODUCERS = (
    "transform_prices",
    "daily_compute",
    "technical_compute",
    "halfyearly_compute",
    "period_metrics_compute",
    "universe_build",
)

DAILY_CANONICAL = RunPlan(
    name="DAILY_CANONICAL",
    stages=_DAILY_PRODUCERS + ("composite_score",),
    # yearly_compute is deliberately absent. Its output is inherited, and the
    # fingerprint below is what makes that legitimate.
    required=_DAILY_PRODUCERS,
    reuses=("yearly_compute",),
    description="Daily governed rebuild ending in canonical publication, "
                "reusing proven-current yearly output.")

FULL_FUNDAMENTALS_CANONICAL = RunPlan(
    name="FULL_FUNDAMENTALS_CANONICAL",
    stages=("transform_prices", "yearly_compute", "daily_compute",
            "technical_compute", "halfyearly_compute",
            "period_metrics_compute", "universe_build", "composite_score"),
    required=("transform_prices", "yearly_compute", "daily_compute",
              "technical_compute", "halfyearly_compute",
              "period_metrics_compute", "universe_build"),
    reuses=(),
    description="Fundamentals refresh: computes yearly output for itself, so "
                "it inherits nothing and needs no reuse proof.")

#: What runs published before plans existed actually proved.
#:
#: Historical only. Its required set is the old static REQUIRED_STAGES tuple,
#: which is what those runs were validated against when they published. The two
#: live plans now require four more producer stages, and holding old runs to a
#: contract that did not exist when they ran would unpublish every one of them
#: on deploy -- taking the governed surface dark -- with no evidence that any
#: of them was wrong.
#:
#: Recording what they proved is the honest claim. Refusing to let anything new
#: use it is what stops that honesty becoming a loophole.
LEGACY_CANONICAL = RunPlan(
    name="LEGACY_CANONICAL",
    stages=("yearly_compute", "daily_compute", "universe_build",
            "composite_score"),
    required=("yearly_compute", "daily_compute", "universe_build"),
    reuses=(),
    description="Runs published before run plans existed, under the historical "
                "three-stage contract. Not executable.",
    executable=False)

PLANS = {p.name: p for p in (DAILY_CANONICAL, FULL_FUNDAMENTALS_CANONICAL,
                             LEGACY_CANONICAL)}

#: What a new run may be opened under. `PLANS` is the wider set, because the
#: resolver must be able to look up the plan of a run that already exists.
EXECUTABLE_PLANS = {n: p for n, p in PLANS.items() if p.executable}


def plan_requirements() -> dict:
    """{plan_name: [required stages]} — for the resolver's per-run validation.

    Derived from the plan declarations, never written out a second time. A
    duplicated requirement list is a list that drifts, and the drift shows up
    as runs that publish and are then quietly unservable.
    """
    return {name: list(plan.required) for name, plan in PLANS.items()}


@dataclass
class ReuseDecision:
    """Whether inherited output may be used, and on what evidence."""

    permitted: bool
    reason: str
    proven_by_run: Optional[int] = None
    differences: list = field(default_factory=list)

    def lines(self) -> list:
        head = ("reuse PERMITTED" if self.permitted else "reuse REFUSED")
        out = [f"{head}: {self.reason}"]
        if self.proven_by_run is not None:
            out.append(f"  proven by run {self.proven_by_run}")
        out.extend(f"  {d}" for d in self.differences)
        return out


def check_yearly_reuse(cur) -> ReuseDecision:
    """May a daily run inherit market.yearly_metrics as it stands?

    Read-only, and called before any run exists.
    """
    from compute.engine import source_fingerprint as sfp

    run_id, proven = sfp.proven_by_latest_yearly(cur)
    if proven is None:
        return ReuseDecision(
            False,
            "no successful yearly_compute has recorded a source fingerprint. "
            "Absence is not permission: a run that never proved its inputs "
            "cannot license reuse of its output.")

    current = sfp.compute(cur)

    # Checked before the aggregate, for the diagnosis rather than the verdict.
    # The version is already inside the aggregate, so a projection change
    # refuses reuse either way -- but it would refuse saying "the fundamentals
    # moved", sending someone to look for a source correction that never
    # happened.
    if current.schema_version != proven.schema_version:
        return ReuseDecision(
            False,
            f"fingerprint projection changed (schema "
            f"{proven.schema_version} → {current.schema_version}); the "
            f"recorded fingerprint is not comparable and says nothing about "
            f"whether the sources moved",
            run_id, current.differences(proven))

    if current.aggregate == proven.aggregate:
        return ReuseDecision(
            True, "yearly source fingerprint is unchanged", run_id)

    return ReuseDecision(
        False,
        "yearly output no longer represents current fundamentals",
        run_id, current.differences(proven))


class PublicationRefused(RuntimeError):
    """The run may not finalise. It exists, so this is execution evidence."""

    def __init__(self, message: str, failure_class: str):
        super().__init__(message)
        self.failure_class = failure_class


def verify_yearly_currency_at_publication(cur, plan: RunPlan, run_id: int):
    """Re-check, immediately before the canonical commit.

    Checking at plan-open time is necessary and not sufficient. The producers
    run for minutes, and the window is real:

        fingerprint matches -> create run -> producers run for several minutes
        -> a fundamentals correction lands -> canonical publish certifies a
           source state that no longer exists

    Publication cannot certify a source state that ceased to exist during the
    run, so the fingerprint that the yearly output represents must still equal
    the current one at the moment of commit.

    The check applies to BOTH plans, for the same reason in two shapes: a daily
    run reuses an earlier yearly output, a full run computes its own -- and in
    either case the governed values about to be attributed were derived from
    fundamentals that may have moved since.
    """
    from compute.engine import source_fingerprint as sfp

    if "yearly_compute" in plan.reuses:
        source_run, represented = sfp.proven_by_latest_yearly(cur)
        failure_class = "reused_source_changed_during_run"
        what = f"the yearly output reused from run {source_run}"
    else:
        source_run, represented = run_id, sfp.proven_by_run(cur, run_id)
        failure_class = "fundamentals_changed_after_yearly_compute"
        what = "this run's own yearly_compute output"

    if represented is None:
        raise PublicationRefused(
            f"{plan.name} run {run_id}: no yearly source fingerprint is "
            f"available to re-check at publication. Absence is not permission "
            f"-- publishing would attribute governed values to fundamentals "
            f"nobody has shown to be current.",
            failure_class)

    current = sfp.compute(cur)
    if current.aggregate == represented.aggregate:
        return current

    raise PublicationRefused(
        f"{plan.name} run {run_id}: the fundamentals moved during the run, so "
        f"{what} no longer represents them. "
        + "; ".join(current.differences(represented))
        + ". Not finalising: publication would certify a source state that "
          "ceased to exist while this run was computing. The governed rows "
          "stay provisional and un-attributed, so the product fails closed.",
        failure_class)


def open_plan(cur, plan: RunPlan, log) -> None:
    """Evaluate a plan's preconditions. Raises rather than creating a run.

    Called before create_run, deliberately. A precondition failure must leave
    no trace in the run table: the condition was knowable without computing
    anything, and an abandoned run id would later read as a failed computation.
    """
    log.info("plan %s — %s", plan.name, plan.description)
    log.info("  stages   : %s", ", ".join(plan.stages))
    log.info("  required : %s", ", ".join(plan.required))
    log.info("  reuses   : %s", ", ".join(plan.reuses) or "nothing")

    if "yearly_compute" not in plan.reuses:
        return

    decision = check_yearly_reuse(cur)
    for line in decision.lines():
        (log.info if decision.permitted else log.error)("  %s", line)

    if not decision.permitted:
        raise PlanPreconditionFailed(
            f"{plan.name} cannot open: {decision.reason}. "
            f"Run {FULL_FUNDAMENTALS_CANONICAL.name} instead, which computes "
            f"yearly output for itself. No run was created.")
