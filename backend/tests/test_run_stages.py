"""
Coverage proved, not asserted
=============================
The invariant these tests hold:

    A full producer must define an expected population independently of its
    own loop, and prove that the population it successfully wrote is equal to
    it, before its stage can be marked complete.

The incident that motivated it is worth keeping in front of whoever changes
this. yearly_compute reported ``1626 stocks | 0 skipped | 0 errors`` and had
left 2,954 rows with a live source untouched. Every counter it kept was
accurate. They described the loop, and the loop had never been shown the 224
delisted codes that build_screener_universe reads. A counter cannot report
work it was not given.

So the check is set equality against an independently derived expectation, in
both directions -- and the tests below are mostly about the ways "it looked
fine" can still be false.

Pure: no database. The SQL-touching helpers are exercised against a fake
cursor, because what matters here is the decision, not the driver.

Run under pytest, or standalone:
    cd /opt/asx-screener/backend && ../asx-venv/bin/python tests/test_run_stages.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from compute.engine.run_stages import (  # noqa: E402
    SAMPLE_LIMIT,
    StageIncomplete,
    StageResult,
    finalise,
    record_stage,
    require_stages,
    set_hash,
    stages_passed,
)


class Skipped(Exception):
    """This check could not run here. Reported as SKIP, never as PASS."""


def result(expected, written, **details) -> StageResult:
    return StageResult("yearly_compute", frozenset(expected), frozenset(written),
                       details or None)


class FakeCursor:
    """Records statements and answers the one SELECT the helpers make."""

    def __init__(self, passed_stages=()):
        self.passed = set(passed_stages)
        self.statements = []
        self._rows = []

    def execute(self, sql, params=None):
        self.statements.append((" ".join(sql.split()), params))
        if "FROM screener.compute_run_stages" in sql:
            wanted = params[1]
            self._rows = [(s,) for s in wanted if s in self.passed]
        else:
            self._rows = []

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


# ── The equality itself ──────────────────────────────────────────────────────

def test_equal_populations_pass():
    assert result("ABC DEF GHI".split(), "ABC DEF GHI".split()).ok


def test_a_missed_source_fails_the_stage():
    """The 224-delisted-codes case: expected includes them, written does not."""
    r = result("ABC DEF GHI".split(), "ABC DEF".split())

    assert not r.ok
    assert r.missing == frozenset({"GHI"})
    assert r.status == "failed"


def test_an_unexpected_write_also_fails():
    """Written-but-not-expected is not harmless. The producer wrote something
    its own definition of scope does not account for, so one of the two is
    wrong and nothing here can say which."""
    r = result("ABC DEF".split(), "ABC DEF GHI".split())

    assert not r.ok
    assert r.extra == frozenset({"GHI"})


def test_matching_counts_are_not_matching_sets():
    """The failure a count-based check cannot see. Three expected, three
    written, and one of each differs -- so missing_count and extra_count are
    both 1 while the totals agree perfectly."""
    r = result("ABC DEF GHI".split(), "ABC DEF XYZ".split())

    assert len(r.expected) == len(r.written)
    assert not r.ok
    assert r.missing == frozenset({"GHI"}) and r.extra == frozenset({"XYZ"})


# ── The hash is a fingerprint, not a count ───────────────────────────────────

def test_the_hash_ignores_processing_order():
    assert set_hash(["CBA", "BHP", "ANZ"]) == set_hash(["ANZ", "BHP", "CBA"])


def test_the_hash_separates_different_populations_of_the_same_size():
    assert set_hash(["ABC", "DEF"]) != set_hash(["ABC", "XYZ"])


def test_equal_hashes_mean_equal_sets():
    r = result("ABC DEF".split(), "DEF ABC".split())
    assert r.ok
    assert set_hash(r.expected) == set_hash(r.written)


# ── What gets persisted ──────────────────────────────────────────────────────

def test_a_failed_stage_is_recorded_rather_than_left_silent():
    """A stage that failed and wrote nothing is indistinguishable from one the
    run never reached, and those need different responses."""
    cur = FakeCursor()
    ok = record_stage(cur, 7, result("ABC DEF".split(), ["ABC"]))

    assert ok is False
    sql, params = cur.statements[0]
    assert "INSERT INTO screener.compute_run_stages" in sql
    assert params[2] == "failed"
    assert params[5] == 1, "missing_count"


def test_the_sample_is_bounded_and_says_so_when_truncated():
    """A successful run must not persist thousands of codes to say nothing
    happened, and a failing one must not either."""
    expected = [f"C{i:04d}" for i in range(SAMPLE_LIMIT * 4)]
    payload = result(expected, []).payload()

    assert len(payload["missing_sample"]) == SAMPLE_LIMIT
    assert payload["missing_truncated"] is True


def test_a_clean_stage_carries_no_sample_at_all():
    payload = result(["ABC"], ["ABC"]).payload()

    assert "missing_sample" not in payload and "extra_sample" not in payload


def test_stage_details_survive_onto_the_record():
    payload = result(["ABC"], ["ABC"], pruned_orphans=55).payload()
    assert payload["pruned_orphans"] == 55


# ── The gate the writer has to pass ──────────────────────────────────────────

def test_a_missing_stage_record_is_not_permission():
    """A stage that never ran has no failed row either. Treating absence as
    consent would make the whole mechanism optional by omission."""
    cur = FakeCursor(passed_stages=())

    assert stages_passed(cur, 7, ["yearly_compute"]) == ["yearly_compute"]
    try:
        require_stages(cur, 7, ["yearly_compute"])
    except StageIncomplete as e:
        assert "yearly_compute" in str(e)
    else:
        raise AssertionError("an unproven stage must block the writer")


def test_only_a_success_row_counts():
    cur = FakeCursor(passed_stages={"yearly_compute"})
    assert stages_passed(cur, 7, ["yearly_compute"]) == []
    require_stages(cur, 7, ["yearly_compute"])


def test_finalisation_refuses_an_incomplete_run():
    cur = FakeCursor(passed_stages=())
    try:
        finalise(cur, 7, rows_written=2117, persistence_violations=0,
                 required_stages=["yearly_compute"])
    except StageIncomplete:
        pass
    else:
        raise AssertionError("publication must require the prerequisite stage")
    assert not any("compute_run_finalizations" in s for s, _ in cur.statements)


def test_finalisation_refuses_a_run_that_wrote_violating_rows():
    """Complete coverage is not sufficient. A run can cover its whole
    population and still write rows whose values and states disagree."""
    cur = FakeCursor(passed_stages={"yearly_compute"})
    try:
        finalise(cur, 7, rows_written=2117, persistence_violations=3,
                 required_stages=["yearly_compute"])
    except StageIncomplete as e:
        assert "persistence contract" in str(e) or "violate" in str(e)
    else:
        raise AssertionError("a dirty run must not publish")


def test_a_complete_clean_run_publishes():
    cur = FakeCursor(passed_stages={"yearly_compute"})
    finalise(cur, 7, rows_written=2117, persistence_violations=0,
             required_stages=["yearly_compute"], snapshot_id="snap-1")

    assert any("compute_run_finalizations" in s for s, _ in cur.statements)


# ── The 224-row incident, as an assertion ────────────────────────────────────

def test_a_clean_looking_run_that_missed_rows_cannot_publish():
    """The incident this whole mechanism exists for, end to end.

    yearly_compute reported "1626 stocks | 0 skipped | 0 errors" and had left
    2,954 sourced rows untouched. Every counter it kept was accurate; none of
    them was evidence. Expected {A,B,C}, written {A,B}, no exception raised
    anywhere -- the stage must record failed, and finalisation must be
    impossible.
    """
    cur = FakeCursor(passed_stages=())

    r = result("ABC DEF GHI".split(), "ABC DEF".split(), skipped=0, errors=0)
    assert record_stage(cur, 9, r) is False

    _, params = cur.statements[0]
    assert params[2] == "failed"

    # And nothing can be published on top of it.
    try:
        finalise(cur, 9, rows_written=2, persistence_violations=0,
                 required_stages=["yearly_compute"])
    except StageIncomplete:
        pass
    else:
        raise AssertionError("a run that missed rows must not become servable")


def test_zero_errors_is_not_a_coverage_claim():
    """Explicitly: the absence of exceptions says nothing about whether the
    intended population was processed."""
    r = result("ABC DEF GHI".split(), "ABC".split(), errors=0, skipped=0)

    assert not r.ok, "no exception was raised and two thirds went unprocessed"


# ── Neither half may masquerade as publication ───────────────────────────────
#
# These assert the resolver's SQL rather than calling it: _validated_scope
# needs an async SQLAlchemy session, and what matters here is that the query
# demands both conditions conjunctively. A resolver that required only one of
# them would still pass every test that exercised a fully-correct run.

def _resolver_sql() -> str:
    from pathlib import Path as _P
    src = (_P(__file__).resolve().parents[1]
           / "app" / "api" / "v1" / "routes" / "screener.py").read_text(encoding="utf-8")
    import re as _re
    m = _re.search(r"VALIDATED_RUNS_SQL_TEXT = \"\"\"(.*?)\"\"\"", src, _re.S)
    assert m, "could not locate VALIDATED_RUNS_SQL_TEXT"
    return " ".join(m.group(1).split())


def test_stage_successes_without_finalisation_are_not_publication():
    """compute_run exists, all stages SUCCESS, rows carry compute_run_id, and
    no finalisation row. The run must be refused: stage evidence says the
    inputs were complete, not that the canonical write validated."""
    sql = _resolver_sql()

    assert "compute_run_finalizations" in sql, (
        "the resolver must require a finalisation record; stage successes "
        "alone describe the inputs, not the published row")
    assert "JOIN screener.compute_run_finalizations" in sql, (
        "an INNER join, so a run without finalisation cannot appear at all")


def test_finalisation_without_every_required_stage_is_not_publication():
    """The converse. A finalisation row exists and a required stage is missing
    or failed — the run must still be refused."""
    sql = _resolver_sql()

    assert "compute_run_stages" in sql and "status" in sql
    assert "NOT EXISTS" in sql, (
        "written as 'no required stage lacks a success row'. Counting success "
        "rows instead would accept two successes for one stage and none for "
        "the other")
    assert "persistence_violations = 0" in sql


def test_the_resolver_requires_the_same_stages_the_writer_proves():
    """Two copies of the required set would eventually disagree about what
    published means, and the disagreement would be silent in both directions.

    Needs fastapi, so it reports SKIPPED where the API stack is not installed
    rather than passing. A skipped test that prints PASS is the failure mode
    this whole effort keeps running into."""
    try:
        from app.api.v1.routes import screener as route
    except ModuleNotFoundError as e:
        raise Skipped(f"needs the API stack: {e}")

    assert route.REQUIRED_STAGES is REQUIRED_STAGES


def test_rows_written_is_no_longer_accepted_as_publication():
    """It used to be. The run sets it while still executing, so a run that
    wrote every row and then failed validation looked identical to one that
    succeeded."""
    sql = _resolver_sql()

    assert "rows_written IS NOT NULL" not in sql


# ── The driver's preconditions ───────────────────────────────────────────────

def _driver():
    import importlib.util, os
    from pathlib import Path as _P
    os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://unused/unused")
    path = _P(__file__).resolve().parents[1] / "scripts" / "p0a_canonical_run.py"
    spec = importlib.util.spec_from_file_location("p0a_canonical_run", path)
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except ModuleNotFoundError as e:
        raise Skipped(f"needs the compute stack: {e}")
    return module


def _health(*unhealthy, **detail):
    from datetime import datetime, timezone
    from compute.engine.metric_states import SourceHealth
    return SourceHealth(run_at=datetime.now(timezone.utc),
                        unhealthy_sources=tuple(unhealthy), detail=detail)


def test_an_unhealthy_source_never_opens_a_run():
    """Fail-closed, and before create_run rather than after.

    A run under an unhealthy source withholds Income and the composite
    universe-wide -- correctly -- but can never produce the contract the
    driver exists to publish. Giving it a run identity would record an attempt
    that was structurally incapable of succeeding.
    """
    drv = _driver()
    try:
        drv.require_publishable(_health("dividends", dividends="41 days behind"))
    except drv.PreconditionFailed as e:
        assert "dividends" in str(e)
    else:
        raise AssertionError("an unhealthy source must not open a run")


def test_a_healthy_source_is_admitted():
    drv = _driver()
    drv.require_publishable(_health())


def test_there_is_no_override_for_unhealthy_sources():
    """If an unhealthy-source experiment is ever needed it belongs in a mode
    structurally forbidden from finalising, not in a flag that relaxes this
    precondition. A flag would be reached for under pressure."""
    drv = _driver()
    import inspect

    source = inspect.getsource(drv)
    for flag in ("allow-unhealthy", "allow_unhealthy", "ignore-health",
                 "skip_health"):
        assert flag not in source, f"{flag} weakens the health precondition"


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failures = []
    skipped = []
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
        except Exception as e:
            failures.append(name)
            print(f"  ERROR {name}  - {type(e).__name__}: {e}")

    # Skipped checks are excluded from the denominator rather than counted as
    # passes. "22/22 passed" over a check that never ran is the same lie this
    # suite exists to catch, told about itself.
    ran = len(tests) - len(skipped)
    print(f"\n{ran - len(failures)}/{ran} passed"
          + (f", {len(skipped)} SKIPPED" if skipped else ""))
    sys.exit(1 if failures else 0)
