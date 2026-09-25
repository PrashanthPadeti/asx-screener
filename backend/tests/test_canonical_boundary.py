"""
The boundary is derived, and the derivation actually looks at something
=======================================================================
`canonical_boundary` answers one question for every pipeline step — can this
mutate a table whose state can reach a governed value? — by reading the SQL
the stages contain rather than a list somebody maintained.

That makes the module itself the thing most worth attacking. A boundary
checker that quietly finds no tables would report a perfectly classified
pipeline and prove nothing, which is the exact shape of the inert guards this
codebase has produced repeatedly: an ordering guard that scanned for
statements that were not there, a fault-injection guard that matched its own
module docstring. So roughly half the tests below are about the extractor
rather than the boundary.

Run under pytest, or standalone:
    cd /opt/asx-screener/backend && ../asx-venv/bin/python tests/test_canonical_boundary.py
"""

import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from compute.engine import canonical_boundary as cb  # noqa: E402
from compute.engine.run_plans import PLANS  # noqa: E402


class Skipped(Exception):
    """Reported as SKIPPED. A skipped test that prints PASS is the failure
    mode this whole effort keeps running into."""


def _written(text: str) -> dict:
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False,
                                     encoding="utf-8") as handle:
        handle.write(text)
        path = Path(handle.name)
    try:
        return cb.tables_touched(path)
    finally:
        path.unlink(missing_ok=True)


# ── The extractor is not inert ───────────────────────────────────────────────

def test_the_extractor_finds_tables_in_a_real_stage():
    """If this returns nothing, every classification below is vacuous."""
    touched = cb.tables_touched(cb.TAIL_SCRIPT)
    assert touched, "composite_score.py appears to touch no tables at all"
    assert "screener.universe" in touched, sorted(touched)


def test_every_plan_stage_resolves_to_a_file_that_exists():
    for stage, path in cb.plan_scripts().items():
        assert path.exists(), f"{stage} -> {path} does not exist"


def test_a_table_named_only_in_prose_is_not_a_reference():
    """Docstrings describe tables constantly. A guard that reads them would
    classify a step by its own documentation."""
    touched = _written('"""We used to write INSERT INTO market.daily_prices here."""\n'
                       'x = 1\n')
    assert touched == {}, touched


def test_a_table_named_only_in_a_comment_is_not_a_reference():
    """Both comment syntaxes. These files carry SQL in triple-quoted strings,
    so a commented-out `-- UPDATE` inside one is not a write."""
    touched = _written('# INSERT INTO market.daily_prices\n'
                       'q = """\n'
                       '    SELECT 1\n'
                       '    -- UPDATE screener.universe\n'
                       '"""\n')
    assert touched == {}, touched


def test_comments_are_stripped_even_when_the_file_will_not_parse():
    """Comment removal must not depend on a successful ast.parse. The first
    draft returned raw source on SyntaxError, so an unparseable file kept
    every commented-out statement and reported tables it never touches."""
    touched = _written('# INSERT INTO market.daily_prices\n'
                       'this is not python(((\n')
    assert touched == {}, touched


def test_delete_from_is_a_write_not_a_read():
    """`DELETE FROM x` contains `FROM x`. Matched in the wrong order, a
    deletion records as a read and the step looks harmless."""
    touched = _written('q = "DELETE FROM screener.universe WHERE 1=0"\n')
    assert touched == {"screener.universe": {"w"}}, touched


def test_insert_into_is_a_write_not_a_read():
    touched = _written('q = "INSERT INTO market.daily_prices SELECT 1"\n')
    assert touched["market.daily_prices"] == {"w"}, touched


def test_reads_and_writes_are_distinguished_on_one_table():
    touched = _written('a = "UPDATE screener.universe SET x=1"\n'
                       'b = "SELECT 1 FROM screener.universe"\n')
    assert touched["screener.universe"] == {"r", "w"}, touched


def test_tables_are_found_inside_f_strings():
    """Every producer in this codebase builds SQL with f-strings."""
    touched = _written('t = "x"\nq = f"SELECT 1 FROM market.yearly_metrics WHERE a={t}"\n')
    assert "market.yearly_metrics" in touched, touched


# ── The derived sets ─────────────────────────────────────────────────────────

def test_outputs_and_inputs_are_disjoint_and_both_populated():
    inputs, outputs = cb.canonical_tables()
    assert outputs, "no canonical outputs derived; the driver owns nothing"
    assert inputs, "no canonical inputs derived"
    assert not (inputs & outputs), sorted(inputs & outputs)


def test_the_universe_is_a_canonical_output():
    """The table the whole contract is about. If it ever leaves this set, the
    boundary has stopped describing the system."""
    _inputs, outputs = cb.canonical_tables()
    assert "screener.universe" in outputs


def test_the_fingerprinted_sources_are_canonical_inputs():
    """The six tables yearly_compute consumes decide whether DAILY_CANONICAL
    may reuse yearly output. Every one must be inside the boundary, or an
    ingestion step could move them without being classified."""
    from compute.engine.source_fingerprint import PROJECTIONS

    deps = cb.dependency_tables()
    missing = sorted(t for t in PROJECTIONS if t not in deps)
    assert not missing, (
        f"fingerprinted sources outside the derived boundary: {missing}")


def test_the_parsed_stage_commands_match_the_driver_itself():
    """The AST parse exists so this module needs no database driver. It must
    not become a second source of truth.

    Needs psycopg2, so it SKIPS where the compute stack is absent rather than
    passing."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("p0a_driver", cb.DRIVER)
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:                                  # noqa: BLE001
        raise Skipped(f"needs the compute stack: {type(exc).__name__}")

    parsed = {k: v.relative_to(cb.BACKEND).as_posix()
              for k, v in cb.stage_scripts().items()}
    real = {stage: builder(1)[1]
            for stage, builder in module.STAGE_COMMANDS.items()}
    assert parsed == real, f"parsed {parsed}\nreal {real}"


# ── The boundary itself ──────────────────────────────────────────────────────

def test_every_step_touching_a_dependency_table_is_classified():
    unclassified = [v for v in cb.violations() if v.startswith("UNCLASSIFIED")]
    assert not unclassified, "\n".join(unclassified)


def test_no_new_boundary_violations():
    assert not cb.violations(), "\n".join(cb.violations())


def test_a_plan_stage_is_never_hand_classified():
    """It is CANONICAL_DRIVER by derivation. A declaration would be a second
    answer that can disagree with the first."""
    stages = {p.relative_to(cb.BACKEND).as_posix()
              for p in cb.plan_scripts().values()}
    overlap = stages & set(cb.CLASSIFICATIONS)
    assert not overlap, (
        f"these are plan stages and must not be declared: {sorted(overlap)}")


def test_accepted_entries_are_real_violations():
    """An exemption for something that does not violate is a comment nobody
    will ever delete."""
    violating = {cb._key_of(v) for v in cb.violations(include_accepted=True)}
    visible = set(cb.all_units())
    stale = sorted((set(cb.ACCEPTED) & visible) - violating)
    assert not stale, f"ACCEPTED lists non-violations: {stale}"


def test_every_accepted_entry_states_why():
    for key, reason in cb.ACCEPTED.items():
        assert len(reason) > 120, (
            f"{key}'s exemption is too short to be a justification; an "
            f"allowlist without reasons becomes permanent")


# ── The suffix writer, and its non-governed claim ────────────────────────────

def test_the_column_extractor_finds_pros_and_cons():
    """Non-inert check. columns_written reports nothing for a SQL shape it
    cannot read, so an extractor that silently found nothing would clear every
    writer it does not understand — including the one it exists to police."""
    found = cb.columns_written(
        cb.BACKEND / "compute/engine/pros_cons.py", "screener.universe")
    assert found == {"pros", "cons"}, found


def test_an_aliased_update_is_seen():
    """`UPDATE screener.universe u SET ...` is the shape short_positions uses.

    A pattern demanding SET immediately after the table reported no columns
    for it, which silently cleared an aliased writer of the governed-column
    check. Found because the scheduler trace said that job writes
    screener.universe while the column extractor said it writes nothing — two
    derivations disagreeing is how this surfaced at all.
    """
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False,
                                     encoding="utf-8") as handle:
        handle.write('q = """\n'
                     '    UPDATE screener.universe u\n'
                     '    SET short_pct = sp.a, short_interest_chg_1w = sp.b\n'
                     '    FROM market.short_positions sp\n'
                     '"""\n')
        path = Path(handle.name)
    try:
        found = cb.columns_written(path, "screener.universe")
        assert found == {"short_pct", "short_interest_chg_1w"}, found
    finally:
        path.unlink(missing_ok=True)


def test_the_alias_is_not_mistaken_for_a_column():
    """The alias must not swallow SET, or the first assignment is lost."""
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False,
                                     encoding="utf-8") as handle:
        handle.write('q = "UPDATE screener.universe SET pros = 1 WHERE x"\n')
        path = Path(handle.name)
    try:
        assert cb.columns_written(path, "screener.universe") == {"pros"}
    finally:
        path.unlink(missing_ok=True)


def test_governed_columns_is_populated():
    governed = cb.governed_columns()
    assert len(governed) >= 60, f"only {len(governed)} governed columns"


def test_no_canonical_stage_reads_what_the_suffix_writer_writes():
    """The one thing that would overturn the decision to put pros_cons after
    publication: if a plan stage consumed its columns, it would have to run
    before. Established mechanically rather than by reading."""
    import re as _re
    written = cb.columns_written(
        cb.BACKEND / "compute/engine/pros_cons.py", "screener.universe")
    assert written, "fixture is empty; the assertion below would be vacuous"
    for stage, path in cb.plan_scripts().items():
        source = cb._executable_source(path)
        for column in written:
            assert not _re.search(rf"\b{column}\b", source), (
                f"{stage} references '{column}', which a POST_PUBLICATION "
                f"writer produces — it cannot run after publication")


def test_every_suffix_writer_states_why():
    for step in cb.all_steps():
        if cb.classification(step) == cb.POST_PUBLICATION_WRITER:
            reason = cb.SUFFIX_WRITE_REASONS.get(step.key, "")
            assert len(reason) > 120, (
                f"{step.key} writes a shared canonical table without a "
                f"stated reason")


def test_a_suffix_writer_touching_a_governed_column_is_detected():
    """The mutation for the non-governed claim. Pretend one of pros_cons's
    columns is governed and require the boundary to object."""
    real = cb.governed_columns
    cb.governed_columns = lambda: real() | {"pros"}
    try:
        found = cb.violations()
        assert any("GOVERNED columns" in v and "pros_cons" in v for v in found), (
            f"a suffix writer touching a governed column was not reported: {found}")
    finally:
        cb.governed_columns = real


def test_a_suffix_writer_without_a_reason_is_detected():
    saved = cb.SUFFIX_WRITE_REASONS.pop("compute/engine/pros_cons.py")
    try:
        found = cb.violations()
        assert any("no stated reason" in v for v in found), found
    finally:
        cb.SUFFIX_WRITE_REASONS["compute/engine/pros_cons.py"] = saved


def test_a_decided_case_is_not_left_as_an_exemption():
    """ACCEPTED is for UNDECIDED cases. Leaving a resolved one there makes the
    exceptional state permanent, which is the opposite of deciding.

    This asserted `ACCEPTED == {}` while pros_cons was the only entry, which
    was really a test that one decision had been taken, written as though it
    were a rule about the list. A legitimate new entry then failed it."""
    decided = {"compute/engine/pros_cons.py"}
    left = decided & set(cb.ACCEPTED)
    assert not left, (
        f"these were decided and should be classified, not exempted: "
        f"{sorted(left)}")


# ── The guard fails when the boundary is broken ──────────────────────────────

def test_removing_a_classification_is_detected():
    """The mutation. Without it, everything above could be reporting on an
    empty step list."""
    victim = "compute/engine/heatmap_compute.py"
    assert victim in cb.CLASSIFICATIONS, "fixture moved; pick another step"
    saved = cb.CLASSIFICATIONS.pop(victim)
    try:
        found = cb.violations()
        assert any(v.startswith("UNCLASSIFIED") and victim in v for v in found), (
            f"an unclassified dependency-touching step was not reported: {found}")
    finally:
        cb.CLASSIFICATIONS[victim] = saved


def test_a_pre_ingestion_step_writing_a_canonical_output_is_detected():
    victim = "scripts/eodhd/v2/load_to_staging_prices.py"
    saved = cb.CLASSIFICATIONS[victim]
    cb.CLASSIFICATIONS[victim] = cb.POST_PUBLICATION
    try:
        found = cb.violations()
        assert any(victim in v and cb.POST_PUBLICATION in v for v in found), (
            f"a post-publication step writing a dependency table was not "
            f"reported: {found}")
    finally:
        cb.CLASSIFICATIONS[victim] = saved


def test_a_stale_exemption_is_detected():
    """The fixture must be a unit this environment can SEE and that does not
    violate. An invisible key is not stale — it is unjudgeable — and the first
    draft of this test used one, so it was asserting the wrong thing."""
    victim = "scripts/eodhd/v2/load_to_staging_prices.py"
    assert victim in cb.all_units(), "fixture is not visible here"
    cb.ACCEPTED[victim] = "x" * 130
    try:
        assert any("STALE EXEMPTION" in v and victim in v
                   for v in cb.violations()), cb.violations()
    finally:
        cb.ACCEPTED.pop(victim)


def test_an_invisible_exemption_is_not_called_stale():
    """backfill_yfinance_prices lives in the runtime crontab and not in the
    checked-in generator, so off-server it is invisible. Reporting it as a
    resolved violation would delete the record of an open question."""
    cb.ACCEPTED["scripts/does/not/exist_here.py"] = "y" * 130
    try:
        assert not any("STALE EXEMPTION" in v and "exist_here" in v
                       for v in cb.violations()), cb.violations()
    finally:
        cb.ACCEPTED.pop("scripts/does/not/exist_here.py")


def test_all_three_pipelines_yield_steps():
    """If a pipeline's call shape changes, pipeline_steps returns [] and the
    whole boundary silently covers less than it claims."""
    for pipeline in cb.PIPELINES:
        steps = cb.pipeline_steps(pipeline)
        assert len(steps) >= 2, f"{pipeline} yielded {len(steps)} steps"


def test_the_universe_build_is_seen_in_every_pipeline_that_runs_it():
    """The step that revokes attribution. If the extractor stopped finding it,
    the boundary would be describing a system where nothing invalidates."""
    for pipeline in cb.PIPELINES:
        keys = {s.key for s in cb.pipeline_steps(pipeline)}
        assert "scripts/eodhd/v2/build_screener_universe.py" in keys, pipeline


def test_the_plans_cover_more_than_one_stage():
    """A guard against PLANS collapsing and taking the derived set with it."""
    assert all(len(p.stages) >= 2 for p in PLANS.values())


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
        except Exception as e:                                # noqa: BLE001
            failures.append(name)
            print(f"  ERROR {name}  - {type(e).__name__}: {e}")
    print(f"\n{len(tests) - len(failures) - len(skipped)}/{len(tests)} passed"
          + (f", {len(skipped)} skipped" if skipped else ""))
    sys.exit(1 if failures else 0)
