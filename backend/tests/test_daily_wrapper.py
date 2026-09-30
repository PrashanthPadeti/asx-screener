"""
The daily pipeline is a wrapper, not a second compute path
==========================================================
Rules 3 and 6 of `docs/canonical_orchestration.md`, as they apply to
`daily_pipeline`:

    INGESTION PREFIX -> barrier/lease -> CANONICAL DRIVER -> finalisation
    -> POST-PUBLICATION SUFFIX (inside the lease, only if published)

The property that matters most is negative: the canonical stages must no
longer appear in the wrapper at all. Running them there AND in the driver
would compute everything twice; running them only there is what revoked the
published contract every morning with nothing to re-establish it, and is why
the cron was disabled on 23 Sep 2026.

Static, and honest about it. Whether the sequence actually publishes is a
rehearsal question and belongs on scratch with data.

Run under pytest, or standalone:
    cd /opt/asx-screener/backend && ../asx-venv/bin/python tests/test_daily_wrapper.py
"""

import ast
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from compute.engine import canonical_boundary as cb  # noqa: E402
from compute.engine.run_plans import PLANS  # noqa: E402

WRAPPER = BACKEND / "scripts/eodhd/v2/jobs/daily_pipeline.py"


def _source() -> str:
    return cb._executable_source(WRAPPER)


# ── The canonical stages have left the wrapper ───────────────────────────────

def test_no_plan_stage_is_invoked_by_the_wrapper():
    """The negative property, and the whole point of the refactor.

    Derived from the plan rather than from a list of filenames, so adding a
    stage to DAILY_CANONICAL cannot quietly reintroduce a duplicate here.
    """
    invoked = {s.key for s in cb.pipeline_steps("daily_pipeline.py")}
    plan_keys = {p.relative_to(cb.BACKEND).as_posix()
                 for p in cb.plan_scripts().values()}
    duplicated = sorted(invoked & plan_keys)
    assert not duplicated, (
        f"the wrapper still runs canonical stages directly: {duplicated}. "
        f"They would execute twice, or -- worse -- only here, which revokes "
        f"the contract with nothing to re-establish it.")


def test_the_wrapper_invokes_the_canonical_driver():
    source = _source()
    assert "p0a_canonical_run.py" in source
    assert '"--plan", "DAILY_CANONICAL"' in source
    assert '"--execute"' in source


def test_every_wrapper_step_is_prefix_or_suffix():
    """Nothing in between. A step that is neither is one the barrier does not
    describe."""
    allowed = {cb.PRE_INGESTION, cb.POST_PUBLICATION,
               cb.POST_PUBLICATION_WRITER, None}
    for step in cb.pipeline_steps("daily_pipeline.py"):
        kind = cb.classification(step)
        assert kind in allowed, f"{step.key} is {kind}"
        if kind is None:
            assert not cb.touches_canonical_tables(step.script) \
                if hasattr(cb, "touches_canonical_tables") else True


def test_the_plan_still_covers_what_the_wrapper_stopped_doing():
    """The six steps removed from the wrapper must be exactly the plan's
    stages, or the refactor dropped work rather than moving it."""
    plan = PLANS["DAILY_CANONICAL"]
    for stage in ("transform_prices", "daily_compute", "technical_compute",
                  "halfyearly_compute", "period_metrics_compute",
                  "universe_build"):
        assert stage in plan.stages, stage
    assert plan.stages[-1] == "composite_score"


# ── Ordering: ingestion before admission ─────────────────────────────────────

def test_ingestion_completes_before_the_canonical_block():
    """Plan admission must occur before the first canonical-affecting derived
    mutation. If an ingestion step ran after the driver, it could move an
    admitted source underneath a run already computing from it.

    Anchored on the `with canonical_execution(` statement rather than on the
    comment that labels the barrier. The first draft looked for the comment
    and failed, because _executable_source strips comments before matching —
    correctly, since prose about a boundary is not a boundary. A test that
    depends on a comment tests the comment.
    """
    source = _source()
    barrier = source.index("with canonical_execution(")
    # backfill_yfinance_prices was here until 30 Sep 2026, when the job was
    # deleted rather than relocated: its eight instruments carried prices
    # 35-49 days stale, and absence is the honest state for an instrument
    # with no current source.
    for ingestion in ("download_eod_prices.py", "load_to_staging_prices.py",
                      "transform_short.py"):
        assert source.index(ingestion) < barrier, (
            f"{ingestion} runs at or after the canonical block")


def test_the_suffix_runs_after_the_driver_and_only_on_publication():
    source = _source()
    driver = source.index("p0a_canonical_run.py")
    suffix = source.index("heatmap_compute.py")
    assert driver < suffix, "the suffix runs before the canonical driver"

    block = source[source.index("with canonical_execution(tracker)"):]
    assert "if published:" in block, (
        "the suffix is not gated on a publication having happened")


def test_the_suffix_is_inside_the_lease():
    """It reads screener.universe. Releasing at finalisation would let a later
    run's provisional rebuild revoke attribution while it was still reading."""
    tree = ast.parse(WRAPPER.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not (isinstance(node, ast.With)
                and "canonical_execution" in (ast.get_source_segment(
                    WRAPPER.read_text(encoding="utf-8"), node) or "")):
            continue
        body = ast.get_source_segment(WRAPPER.read_text(encoding="utf-8"), node)
        assert "heatmap_compute.py" in body, (
            "the suffix is outside the canonical_execution block, so it runs "
            "without the lease")
        return
    raise AssertionError("no canonical_execution block found")


# ── The lease ────────────────────────────────────────────────────────────────

def test_the_wrapper_owns_the_lease_not_the_driver():
    """The driver exits at finalisation; the suffix reads after it. A
    driver-scoped lease would drop between the two."""
    source = _source()
    assert "canonical_lease(" in source
    assert 'why="daily_pipeline"' in source


def test_scheduled_runs_wait_and_manual_runs_do_not():
    from compute.engine import canonical_lease as cl
    assert cl.SCHEDULED_WAIT_SECONDS == 90 * 60
    assert cl.MANUAL_WAIT_SECONDS == 0


def test_the_lease_key_is_a_fixed_constant():
    """Two callers deriving it differently would each hold 'the' lease and
    neither would be wrong about it."""
    from compute.engine import canonical_lease as cl
    source = (BACKEND / "compute/engine/canonical_lease.py").read_text(
        encoding="utf-8")
    assert isinstance(cl.CANONICAL_LEASE_KEY, int)
    assert f"CANONICAL_LEASE_KEY = {cl.CANONICAL_LEASE_KEY:_}" in source, (
        "the key is computed rather than fixed")


def test_the_lease_is_session_scoped_and_released():
    """Session-scoped so a crashed holder releases automatically — an
    abandoned lock would be worse than the race it prevents."""
    source = (BACKEND / "compute/engine/canonical_lease.py").read_text(
        encoding="utf-8")
    assert "pg_try_advisory_lock" in source
    assert "pg_advisory_unlock" in source
    assert "finally:" in source, "the lease is not released on every path"
    assert "pg_advisory_xact_lock" not in source, (
        "a transaction-scoped lock would drop at the first commit, which the "
        "driver performs many times")


def test_lease_unavailable_is_a_refusal_not_a_crash():
    """The previously finalised output keeps serving; the cycle simply does
    not publish. A traceback here would look like a broken pipeline rather
    than a deliberate refusal."""
    source = _source()
    assert "except LeaseUnavailable" in source
    block = source[source.index("except LeaseUnavailable"):]
    assert "yield False" in block[:600], (
        "a lease timeout does not fall through to 'no publication'")


# ── Item 4: the auxiliary writers are coordinated ────────────────────────────

AUXILIARY = ("compute/engine/asx_indices.py",
             "compute/engine/short_positions.py",
             "compute/engine/pros_cons.py")


def test_every_auxiliary_universe_writer_takes_the_lease():
    """They write non-governed columns of screener.universe on their own
    schedules. They may keep those schedules; they may not keep uncoordinated
    write authority over the live canonical table.

    short_positions fires at 20:05 AEST = 10:05 UTC, inside the window a
    daily canonical run starting at 08:30 UTC is still computing. This is a
    live overlap, not a theoretical one.
    """
    for module in AUXILIARY:
        source = cb._executable_source(cb.BACKEND / module)
        assert "auxiliary_lease" in source, f"{module} writes unleased"


def test_an_auxiliary_writer_defers_rather_than_writing_anyway():
    """Taking the lease is not enough — the caller has to honour a refusal."""
    for module in AUXILIARY:
        source = cb._executable_source(cb.BACKEND / module)
        assert "if not permitted" in source, (
            f"{module} acquires the lease but writes regardless of the answer")


def test_contention_defers_an_auxiliary_writer_and_never_raises():
    """A crash on contention turns a deferral into a failed job, and the next
    person to see that alert learns to ignore it.

    Checked as an AST statement, not as the substring "raise". The first
    draft matched the word "raises" in the function's own docstring — which
    says it never does — and reported that it does. Prose about a behaviour
    is not that behaviour, which is the same rule the table extractor
    enforces and which I had just applied elsewhere.
    """
    import ast as _ast
    source = (cb.BACKEND / "compute/engine/canonical_lease.py").read_text(
        encoding="utf-8")
    for node in _ast.walk(_ast.parse(source)):
        if not (isinstance(node, _ast.FunctionDef)
                and node.name == "auxiliary_lease"):
            continue
        raises = [n for n in _ast.walk(node) if isinstance(n, _ast.Raise)]
        assert not raises, (
            f"auxiliary_lease raises at line {raises[0].lineno}; contention "
            f"must defer, not fail")
        segment = _ast.get_source_segment(source, node) or ""
        assert "yield acquired" in segment
        return
    raise AssertionError("auxiliary_lease not found")


def test_auxiliary_writers_wait_briefly_and_the_canonical_run_waits_long():
    """An auxiliary writer must never block the canonical run behind it."""
    from compute.engine import canonical_lease as cl
    assert cl.AUXILIARY_WAIT_SECONDS < cl.SCHEDULED_WAIT_SECONDS
    assert cl.AUXILIARY_WAIT_SECONDS == 5 * 60


def test_the_lease_is_held_on_its_own_connection():
    """These writers commit through their own session, and a session's
    connection can return to the pool on commit — dropping a session-scoped
    lock partway through, or handing a locked connection to someone else."""
    source = (cb.BACKEND / "compute/engine/canonical_lease.py").read_text(
        encoding="utf-8")
    body = source[source.index("def auxiliary_lease("):
                  source.index("def canonical_lease(")]
    assert "psycopg2.connect(dsn)" in body
    assert "conn.close()" in body


# ── The weekly wrapper, same shape against the FULL plan ─────────────────────

WEEKLY = BACKEND / "scripts/eodhd/v2/jobs/weekly_pipeline.py"


def test_the_weekly_wrapper_runs_no_plan_stage_directly():
    """Steps 4, 5, 8 and 9a were yearly_compute, halfyearly_compute,
    build_screener_universe and composite_score run as separate commands.

    composite_score ran with NO run id, so the weekly pipeline rebuilt the
    universe and then wrote factor scores that no finalisation vouched for.
    The resolver could not serve it and nothing said so.
    """
    invoked = {s.key for s in cb.pipeline_steps("weekly_pipeline.py")}
    plan_keys = {p.relative_to(cb.BACKEND).as_posix()
                 for p in cb.plan_scripts().values()}
    assert not sorted(invoked & plan_keys), sorted(invoked & plan_keys)


def test_the_weekly_wrapper_uses_the_full_plan():
    source = cb._executable_source(WEEKLY)
    assert '"FULL_FUNDAMENTALS_CANONICAL"' in source
    assert "p0a_canonical_run.py" in source


def test_the_weekly_input_writers_run_before_the_barrier():
    """weekly_compute and monthly_compute write canonical INPUTS. An input
    written after admission moves the source out from under a contract
    already being computed against it."""
    source = cb._executable_source(WEEKLY)
    barrier = source.index("with canonical_execution(")
    for step in ("weekly_compute.py", "monthly_compute.py"):
        assert source.index(step) < barrier, f"{step} runs after the barrier"


def test_the_weekly_suffix_is_gated_and_leased():
    source = cb._executable_source(WEEKLY)
    block = source[source.index("with canonical_execution("):]
    assert "if published:" in block
    for step in ("pros_cons.py", "sector_benchmarks.py"):
        assert step in block, f"{step} is outside the leased block"


def test_a_suffix_step_inherits_the_lease_instead_of_deadlocking():
    """pros_cons takes an auxiliary lease of its own AND runs inside the
    weekly wrapper's lease. Advisory locks are per-session, so without an
    inheritance marker it would block on its own parent's lock, wait out the
    timeout and defer — every week, quietly, while every log line said the
    pipeline succeeded."""
    from compute.engine import canonical_lease as cl

    lease_source = (BACKEND / "compute/engine/canonical_lease.py").read_text(
        encoding="utf-8")
    assert cl.LEASE_HELD_ENV in lease_source
    body = lease_source[lease_source.index("def auxiliary_lease("):
                        lease_source.index("def canonical_lease(")]
    assert f"os.getenv({cl.LEASE_HELD_ENV}" in body or "LEASE_HELD_ENV" in body

    for wrapper in (WRAPPER, WEEKLY):
        source = cb._executable_source(wrapper)
        assert "LEASE_HELD_ENV" in source, (
            f"{wrapper.name} does not tell its suffix that the lease is held")


def test_the_inheritance_marker_is_honoured():
    """Behavioural, not structural: with the marker set, an auxiliary lease
    yields True without touching a database."""
    import os

    from compute.engine.canonical_lease import LEASE_HELD_ENV, auxiliary_lease

    os.environ[LEASE_HELD_ENV] = "test"
    try:
        with auxiliary_lease("postgresql://unused/unused", why="probe") as ok:
            assert ok is True
    finally:
        os.environ.pop(LEASE_HELD_ENV, None)


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
        except Exception as e:                                 # noqa: BLE001
            failures.append(name)
            print(f"  ERROR {name}  - {type(e).__name__}: {e}")
    print(f"\n{len(tests) - len(failures)}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
