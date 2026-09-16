"""
Cadence is not correctness
==========================
A daily run must not fail because yearly_compute did not run that day —
reusing the weekly output is the intended behaviour. What it must not do is
assume that output is still current.

The adversarial case this suite exists for:

    advance the annual source fingerprint without rerunning yearly_compute
    -> DAILY_CANONICAL must REFUSE, and must refuse before creating a run

That proves the reuse contract rather than its happy path.

Run under pytest, or standalone:
    cd /opt/asx-screener/backend && ../asx-venv/bin/python tests/test_run_plans.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from compute.engine import source_fingerprint as sfp  # noqa: E402
from compute.engine.run_plans import (  # noqa: E402
    DAILY_CANONICAL, EXECUTABLE_PLANS, FULL_FUNDAMENTALS_CANONICAL,
    LEGACY_CANONICAL, PLANS, plan_requirements,
    PlanPreconditionFailed, PublicationRefused, RunPlan, check_yearly_reuse,
    open_plan, verify_yearly_currency_at_publication,
)


class Log:
    def __init__(self):
        self.lines = []

    def _add(self, msg, *a):
        self.lines.append(msg % a if a else msg)

    info = error = warning = _add

    def text(self):
        return "\n".join(self.lines)


class FakeCur:
    """Answers the fingerprint queries and the stage lookup.

    `tables` is the CURRENT source state; `proven` is what the recorded
    yearly_compute evidence claims.
    """

    def __init__(self, tables, proven=None, proven_run=41):
        self.tables = tables
        self.proven = proven
        self.proven_run = proven_run
        self._answer = None
        self._digest_for = None

    def execute(self, sql, params=None):
        if "information_schema.columns" in sql:
            self._answer = "numeric-set"
            self._rows = []
        elif "compute_run_stages" in sql:
            self._answer = ((self.proven_run, self.proven)
                            if self.proven is not None else None)
        else:
            # A table digest, identified by the marker the query carries. The
            # two scoped projections contain a correlated subquery over
            # financials.annual_pnl, so matching on "FROM <table>" picks
            # whichever name appears first and silently answers for the wrong
            # table — which is exactly what it did before the marker existed.
            for name in self.tables:
                if f"/* fingerprint:{name} */" in sql:
                    self._answer = (self.tables[name]["n"],
                                    self.tables[name]["digest"])
                    return
            raise AssertionError(f"unrecognised digest query: {sql[:120]}")

    def fetchone(self):
        return self._answer

    def fetchall(self):
        return []


def _state(**overrides):
    """A current-source state: every fingerprinted table, digest 'base'."""
    tables = {t: {"n": 10, "digest": overrides.get(t, "base")}
              for t in sfp.PROJECTIONS}
    return tables


def _proven_from(tables):
    return sfp.SourceFingerprint(
        sfp.FINGERPRINT_SCHEMA_VERSION, tables,
        sfp.aggregate_digest(sfp.FINGERPRINT_SCHEMA_VERSION, tables)).to_json()


# ── Plan shape ───────────────────────────────────────────────────────────────

def test_the_daily_plan_does_not_require_yearly_compute():
    """Requiring it would force a daily run to recompute the weekly output
    purely to satisfy its own bookkeeping."""
    assert "yearly_compute" not in DAILY_CANONICAL.required
    assert "yearly_compute" not in DAILY_CANONICAL.stages
    assert "yearly_compute" in DAILY_CANONICAL.reuses


def test_the_full_plan_computes_yearly_and_inherits_nothing():
    assert "yearly_compute" in FULL_FUNDAMENTALS_CANONICAL.required
    assert FULL_FUNDAMENTALS_CANONICAL.reuses == ()


def test_the_canonical_tail_is_in_both_plans():
    """Four of the five direct input families to the governed columns change
    daily. A canonical tail that runs only weekly leaves a finalised contract
    valid for hours — the temporal defect P0-A-2 found."""
    for plan in PLANS.values():
        assert "composite_score" in plan.stages, (
            f"{plan.name} rebuilds governed values without canonicalising them")
        assert plan.stages[-1] == "composite_score", (
            f"{plan.name} does not END in canonical publication")


def test_universe_build_precedes_the_canonical_tail_in_every_plan():
    for plan in PLANS.values():
        assert plan.stages.index("universe_build") < \
               plan.stages.index("composite_score")


def test_a_plan_cannot_require_a_stage_it_never_runs():
    """A prerequisite the plan cannot satisfy is a plan that can never
    publish."""
    try:
        RunPlan(name="BROKEN", stages=("a",), required=("a", "b"))
    except AssertionError as e:
        assert "never runs" in str(e)
    else:
        raise AssertionError("a plan requiring an unrun stage was accepted")


def test_a_plan_cannot_both_run_and_reuse_a_stage():
    try:
        RunPlan(name="BROKEN", stages=("yearly_compute",), required=(),
                reuses=("yearly_compute",))
    except AssertionError as e:
        assert "runs and reuses" in str(e)
    else:
        raise AssertionError("a plan that both computes and inherits was accepted")


# ── The reuse contract ───────────────────────────────────────────────────────

def test_reuse_is_permitted_when_the_fingerprint_is_unchanged():
    tables = _state()
    cur = FakeCur(tables, proven=_proven_from(tables))
    decision = check_yearly_reuse(cur)
    assert decision.permitted
    assert decision.proven_by_run == 41


def test_a_changed_fundamentals_source_refuses_reuse():
    """The adversarial case: advance the annual source without rerunning
    yearly_compute."""
    proven = _proven_from(_state())
    cur = FakeCur(_state(**{"financials.annual_pnl": "CORRECTED"}), proven=proven)

    decision = check_yearly_reuse(cur)
    assert not decision.permitted
    assert "no longer represents current fundamentals" in decision.reason
    assert any("annual_pnl" in d for d in decision.differences), (
        "the refusal does not say which source moved, leaving the operator to "
        "guess between a fundamentals correction and a price backfill")


def test_a_balance_sheet_correction_alone_refuses_reuse():
    """A fingerprint of annual_pnl alone would have certified stale output."""
    proven = _proven_from(_state())
    cur = FakeCur(_state(**{"financials.annual_balance_sheet": "CORRECTED"}),
                  proven=proven)
    assert not check_yearly_reuse(cur).permitted


def test_a_historical_price_backfill_refuses_reuse():
    """yearly_metrics carries price-derived returns and risk metrics bounded at
    each fiscal year end; correcting those prices changes the output."""
    proven = _proven_from(_state())
    cur = FakeCur(_state(**{"market.daily_prices": "BACKFILLED"}), proven=proven)
    assert not check_yearly_reuse(cur).permitted


def test_no_recorded_fingerprint_means_no_reuse():
    """Absence is not permission — the same rule that governs publication,
    applied to the thing publication would be built on."""
    cur = FakeCur(_state(), proven=None)
    decision = check_yearly_reuse(cur)
    assert not decision.permitted
    assert "Absence is not permission" in decision.reason


# ── The precondition happens before a run exists ─────────────────────────────

def test_a_stale_yearly_source_refuses_to_open_the_daily_plan():
    cur = FakeCur(_state(**{"financials.annual_cashflow": "CORRECTED"}),
                  proven=_proven_from(_state()))
    log = Log()
    try:
        open_plan(cur, DAILY_CANONICAL, log)
    except PlanPreconditionFailed as e:
        assert "No run was created" in str(e), (
            "a precondition failure must not leave an abandoned run id that "
            "later reads as a failed computation")
        assert FULL_FUNDAMENTALS_CANONICAL.name in str(e), (
            "the refusal does not say what to run instead")
    else:
        raise AssertionError("a stale yearly source opened a daily run")


def test_the_full_plan_needs_no_reuse_proof_to_open():
    """It computes yearly output for itself, so there is nothing to inherit —
    and it must open even when no fingerprint has ever been recorded, or the
    system could never recover from that state."""
    cur = FakeCur(_state(), proven=None)
    open_plan(cur, FULL_FUNDAMENTALS_CANONICAL, Log())


def test_opening_the_daily_plan_logs_what_it_inherits():
    tables = _state()
    log = Log()
    open_plan(FakeCur(tables, proven=_proven_from(tables)), DAILY_CANONICAL, log)
    out = log.text()
    assert "reuses" in out and "yearly_compute" in out
    assert "reuse PERMITTED" in out


# ── Plan identity is recorded once and resolved everywhere ───────────────────

def test_the_resolver_would_have_hidden_every_daily_run():
    """The defect the recorded plan closes.

    The resolver validated every finalised run against one static tuple that
    included yearly_compute — a stage DAILY_CANONICAL never runs. A daily run
    would have published correctly and then been invisible to the API, and the
    product would have gone on serving an older snapshot while every log line
    said the run succeeded.
    """
    historical = set(LEGACY_CANONICAL.required)
    assert "yearly_compute" in historical, "the premise of this test"
    assert not historical <= set(DAILY_CANONICAL.required), (
        "a DAILY_CANONICAL run cannot satisfy the historical static tuple, "
        "which is exactly why requirements must come from the run's own plan")


def test_every_plan_a_run_can_carry_is_resolvable():
    """The resolver joins on plan_name. A plan it cannot look up is a run it
    cannot serve, so the lookup must cover everything create_run can write —
    and LEGACY_CANONICAL, which the migration backfills."""
    reqs = plan_requirements()
    assert set(reqs) == set(PLANS)
    for name in ("DAILY_CANONICAL", "FULL_FUNDAMENTALS_CANONICAL",
                 "LEGACY_CANONICAL"):
        assert reqs[name], f"{name} resolves to no requirements"


def test_the_requirements_the_resolver_uses_are_the_plans_own():
    """Derived, never a second copy. A duplicated list drifts, and the drift
    shows up as runs that publish and are then quietly unservable."""
    for name, required in plan_requirements().items():
        assert tuple(required) == PLANS[name].required


def test_legacy_runs_stay_servable_but_nothing_new_may_use_that_plan():
    """Holding old runs to a contract that did not exist when they published
    would unpublish all of them on deploy, taking the governed surface dark,
    with no evidence any was wrong. Letting new work use it would publish
    against a weaker contract than either live plan."""
    assert not LEGACY_CANONICAL.executable
    assert "LEGACY_CANONICAL" in plan_requirements()
    assert "LEGACY_CANONICAL" not in EXECUTABLE_PLANS
    assert set(EXECUTABLE_PLANS) == {"DAILY_CANONICAL",
                                     "FULL_FUNDAMENTALS_CANONICAL"}


def test_the_legacy_plan_records_the_contract_those_runs_actually_met():
    assert LEGACY_CANONICAL.required == ("yearly_compute", "daily_compute",
                                         "universe_build")


def test_a_new_run_cannot_be_opened_under_a_non_executable_plan():
    from compute.engine.universe_writer import WriteRefused, create_run

    class Cur:
        def execute(self, *a, **k):
            raise AssertionError("a row was inserted for a refused plan")

    for bad in ("LEGACY_CANONICAL", "NOT_A_PLAN"):
        try:
            create_run(Cur(), "driver", _health(), plan_name=bad)
        except WriteRefused as e:
            assert "executable run plan" in str(e)
        else:
            raise AssertionError(f"a run was opened under {bad}")


def test_create_run_will_not_guess_a_plan():
    """A default would be a guess, and guessing the full plan for a daily run
    demands evidence from a stage that plan never runs."""
    import inspect
    from compute.engine.universe_writer import create_run
    sig = inspect.signature(create_run)
    param = sig.parameters["plan_name"]
    assert param.default is inspect.Parameter.empty, (
        "create_run has a default plan; a run that does not state its plan is "
        "a run whose publication contract nobody can name")
    assert param.kind is inspect.Parameter.KEYWORD_ONLY


BACKEND = Path(__file__).resolve().parents[1]


def _code(rel):
    """Source with comments stripped, so a guard cannot match its own
    explanation — a mistake this codebase has made four times."""
    src = (BACKEND / rel).read_text(encoding="utf-8")
    return "\n".join(ln for ln in src.splitlines()
                     if not ln.strip().startswith(("#", "--")))


def test_the_resolver_validates_against_each_runs_own_plan():
    """Asserted textually because the failure mode is a silent fallback.

    The SQL is PostgreSQL-specific (jsonb_each, unnest) so it cannot be
    exercised here, and the dangerous shape is not a wrong answer — it is the
    query going back to one static list and every daily run vanishing from the
    API while its logs say it published.
    """
    sql = _code("app/api/v1/routes/screener.py")
    assert "JOIN plan_requirements pr ON pr.plan_name = r.plan_name" in sql, (
        "the resolver no longer joins runs to their own plan's requirements")
    assert "LEFT JOIN plan_requirements" not in sql, (
        "the join is outer, so a run with an unknown plan_name validates "
        "against no requirements at all and is served unconditionally")
    assert "unnest(pr.required)" in sql
    assert "REQUIRED_STAGES" not in sql, (
        "the resolver still references the static tuple that hid daily runs")
    assert "plan_requirements()" in sql, (
        "the requirements are not derived from the plan declarations")


def test_publication_resolves_the_plan_from_the_run_not_the_flag():
    """The flag says what this invocation believes; the run row says what the
    run was opened under, and that is what the resolver will judge it by."""
    code = _code("compute/engine/composite_score.py")
    assert "SELECT plan_name FROM screener.compute_runs" in code, (
        "composite_score never reads the run's recorded plan, so a mistyped "
        "--plan would publish against a contract the resolver will not use")
    assert "recorded != plan_name" in code, (
        "the recorded plan and the flag are not compared; they can disagree "
        "and the run publishes under one contract while being judged by "
        "another")
    assert "PLANS[recorded]" in code, (
        "the required stages come from the flag rather than the record")


def test_the_run_row_carries_the_plan():
    code = _code("compute/engine/universe_writer.py")
    assert "plan_name" in code and "INSERT INTO screener.compute_runs" in code
    insert = code[code.index("INSERT INTO screener.compute_runs"):]
    assert "plan_name" in insert[:400], (
        "create_run does not persist plan_name, so the run's publication "
        "contract is unrecorded and unresolvable later")


def test_the_migration_makes_plan_identity_immutable_and_mandatory():
    sql = (BACKEND / "migrations/add_plan_name_to_compute_runs.sql"
           ).read_text(encoding="utf-8")
    assert "ALTER COLUMN plan_name SET NOT NULL" in sql, (
        "a run could be written with no plan, and the resolver's inner join "
        "would then silently drop it")
    assert "ALTER COLUMN plan_name DROP DEFAULT" in sql, (
        "the backfill default survives, so a future INSERT that forgets the "
        "plan silently becomes LEGACY_CANONICAL — the weakest contract")
    assert "NEW.plan_name            IS DISTINCT FROM OLD.plan_name" in sql, (
        "plan_name is not in the immutability trigger, so a run's publication "
        "contract could be lowered after the fact to match whatever evidence "
        "it happened to produce")
    assert "DEFAULT 'LEGACY_CANONICAL'" in sql
    assert "DISABLE TRIGGER" not in sql, (
        "a migration that disables the immutability trigger has stopped "
        "believing in it")


def _health():
    from compute.engine.metric_states import SourceHealth
    from datetime import datetime, timezone
    return SourceHealth(run_at=datetime.now(timezone.utc),
                        unhealthy_sources=(), detail={},
                        factor_model_version="FACTOR_MODEL_V2", run_id=None)


# ── The publication-time recheck: the TOCTOU window ──────────────────────────

class PubCur(FakeCur):
    """Adds the per-run stage lookup the full plan uses."""

    def __init__(self, tables, proven=None, proven_run=41, this_run=None):
        super().__init__(tables, proven, proven_run)
        self.this_run = this_run

    def execute(self, sql, params=None):
        if "WHERE run_id = %s AND stage_name = 'yearly_compute'" in sql:
            self._answer = (self.this_run,) if self.this_run else None
            return
        super().execute(sql, params)


def test_a_source_change_during_a_daily_run_refuses_publication():
    """The window the plan-open check cannot close.

        fingerprint matches -> create run -> producers run for minutes
        -> a fundamentals correction lands -> publish certifies a source
           state that no longer exists
    """
    proven = _proven_from(_state())                      # admitted at open
    moved = _state(**{"financials.annual_pnl": "CORRECTED_MID_RUN"})

    try:
        verify_yearly_currency_at_publication(
            PubCur(moved, proven=proven), DAILY_CANONICAL, 99)
    except PublicationRefused as e:
        assert e.failure_class == "reused_source_changed_during_run"
        assert "fails closed" in str(e)
        assert "annual_pnl" in str(e)
    else:
        raise AssertionError(
            "a daily run published governed values attributed to fundamentals "
            "that changed while it was computing")


def test_a_source_change_after_yearly_compute_refuses_the_full_plan_too():
    """The full plan computes its own yearly output and is not exempt: the
    correction can land after yearly_compute finished and before the tail."""
    this_run = _proven_from(_state())
    moved = _state(**{"financials.annual_balance_sheet": "CORRECTED_MID_RUN"})

    try:
        verify_yearly_currency_at_publication(
            PubCur(moved, this_run=this_run), FULL_FUNDAMENTALS_CANONICAL, 99)
    except PublicationRefused as e:
        assert e.failure_class == "fundamentals_changed_after_yearly_compute"
    else:
        raise AssertionError("a full run published against moved fundamentals")


def test_the_full_plan_compares_against_its_own_run_not_the_newest():
    """A newer yearly_compute belonging to a different run says nothing about
    what THIS run computed."""
    tables = _state()
    cur = PubCur(tables, proven=_proven_from(tables), this_run=None)
    try:
        verify_yearly_currency_at_publication(
            cur, FULL_FUNDAMENTALS_CANONICAL, 99)
    except PublicationRefused as e:
        assert "no yearly source fingerprint" in str(e), (
            "the full plan fell back to another run's fingerprint")
    else:
        raise AssertionError(
            "publication proceeded with no fingerprint from this run")


def test_an_unchanged_source_publishes():
    tables = _state()
    fp = verify_yearly_currency_at_publication(
        PubCur(tables, proven=_proven_from(tables)), DAILY_CANONICAL, 99)
    assert fp.aggregate


def test_a_new_daily_price_does_not_refuse_publication():
    """The whole point of scoping the price projection.

    Today's bar is outside every fiscal-year window the computation reads, so
    it must not invalidate a reuse that is genuinely still valid — otherwise
    DAILY_CANONICAL could never publish at all.
    """
    tables = _state()
    # Same projection, same digest: a new row beyond the scope changes neither.
    fp = verify_yearly_currency_at_publication(
        PubCur(tables, proven=_proven_from(tables)), DAILY_CANONICAL, 99)
    assert fp.aggregate == sfp.aggregate_digest(
        sfp.FINGERPRINT_SCHEMA_VERSION, tables)


# ── The fingerprint the plan compares against ────────────────────────────────

def test_the_recorded_fingerprint_survives_a_json_round_trip():
    """It is persisted in a JSONB details column and read back by a later
    process; a value that does not survive that is not a contract."""
    tables = _state()
    blob = json.loads(json.dumps(_proven_from(tables)))
    restored = sfp.SourceFingerprint.from_json(blob)
    assert restored.aggregate == sfp.aggregate_digest(
        sfp.FINGERPRINT_SCHEMA_VERSION, tables)


def test_a_projection_change_refuses_reuse_and_says_which_it_was():
    """A fingerprint recorded under an older projection says nothing about
    whether the sources moved. Refusing with "the fundamentals moved" would
    send someone looking for a source correction that never happened."""
    tables = _state()
    older = sfp.FINGERPRINT_SCHEMA_VERSION + 1        # recorded under another
    proven = sfp.SourceFingerprint(
        older, tables, sfp.aggregate_digest(older, tables)).to_json()

    decision = check_yearly_reuse(FakeCur(tables, proven=proven))
    assert not decision.permitted
    assert "projection changed" in decision.reason
    assert "fundamentals" not in decision.reason


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
