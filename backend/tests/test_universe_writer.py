"""
The persistence writer — seven gates
====================================
The last dangerous boundary: not computing the right state in memory, but
proving the database can store and return it without losing meaning.

  1. one run exists before any governed state is written
  2. numerics + metric_states + compute_run_id move in ONE statement
  3. UNSPECIFIED never survives past the in-memory boundary
  4. suppressed/unavailable persist as NULL + explicit state and cause
  5. exact-run read-back reproduces the participating population
  6. contradictions, run mismatch, unversioned and unsupported fail closed
  7. V1 is frozen before the first production promise

Plus the implementation check that matters most here: the writer consumes
canonical identity and translates to physical column names at one point only.
The ev_to_ebitda defect was a consumer comparing spellings; a writer that
accepted physical names would reintroduce it lower down, where it is harder
to see.

A FakeCursor stands in for psycopg2 so the whole path is exercised without a
driver. It is a substitute for the database, not for the database test — the
real run still has to happen on the server.

Run under pytest, or standalone:
    cd /opt/asx-screener/backend && ../asx-venv/bin/python tests/test_universe_writer.py
"""

import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from compute.engine.applicability import (  # noqa: E402
    Applicability,
    Cause,
    Domain,
    Observation,
    assess,
    unhealthy,
)
from compute.engine.metric_registry import normalise  # noqa: E402
from compute.engine.metric_states import (  # noqa: E402
    GOVERNED_METRICS,
    LATEST_MODEL_VERSION,
    SourceHealth,
    UnsupportedModelVersion,
    load_states,
)
from compute.engine.peer_benchmarks import valid_population  # noqa: E402
from compute.engine.universe_writer import (  # noqa: E402
    STORAGE_COLUMN,
    ComputeRun,
    WriteRefused,
    build_update,
    canonical_for,
    column_for,
    read_back,
    write_all,
    write_row,
)

RUN = ComputeRun(4711, "composite_score", LATEST_MODEL_VERSION)
GOVERNED = GOVERNED_METRICS[LATEST_MODEL_VERSION]


def cba() -> dict:
    """A bank on a broken dividend feed: three causes in one row."""
    obs = Observation(equity=8e10, earnings=1e10)
    out = {
        "debt_to_equity": assess("debt_to_equity", 4.6, Domain.BANK),
        "net_margin": assess("net_margin", 0.31, Domain.BANK),
        "roe": assess("roe", 0.1284, Domain.BANK, obs),
        "pe_ratio": assess("pe_ratio", 19.2, Domain.BANK, obs),
        "grossed_up_yield": unhealthy("grossed_up_yield", "feed incomplete",
                                      Domain.BANK),
        # roce rather than revenue_cagr_5y: the CAGR metrics are not in the
        # V1 governed set, so writing one would be refused — correctly. See
        # test_ungoverned_growth_metrics_carry_no_state for the gap that
        # leaves.
        "roce": assess("roce", 0.09, Domain.BANK,
                       Observation(invested_capital=5e10,
                                   periods_available=2, periods_required=5)),
    }

    # A canonical row is complete by definition, so the fixture is too.
    #
    # These six carry the meaning; the rest are assessed as absent. Padding
    # them is not ceremony: the writer now refuses a row that leaves any
    # governed metric unassessed, because writing it would set those columns
    # to NULL with no sidecar entry — an unexplained null in the database,
    # created by the very statement meant to prevent one. Before this the
    # fixture was a partial row, and every assertion below was made against a
    # shape the canonical path will never produce.
    from compute.engine.universe_writer import persisted_governed

    for metric in persisted_governed(LATEST_MODEL_VERSION):
        out.setdefault(metric, assess(metric, None, Domain.BANK))
    return out


class FakeCursor:
    """Enough of psycopg2 to prove the statement shape and the round trip."""

    def __init__(self):
        self.rows: dict[str, dict] = {}
        self.statements: list[tuple[str, dict]] = []
        self._result = None

    def execute(self, sql, params=None):
        self.statements.append((sql, params))
        if sql.strip().startswith("UPDATE screener.universe"):
            code = params["asx_code"]
            row = self.rows.setdefault(code, {})
            for key, value in params.items():
                if key.startswith("m_"):
                    row[column_for(key[2:])] = value
            row["metric_states"] = params["metric_states"]
            row["compute_run_id"] = params["compute_run_id"]
        elif sql.strip().startswith("SELECT"):
            code = params[0]
            cols = re.search(r"SELECT (.+?) FROM", sql, re.S).group(1)
            names = [c.strip() for c in cols.split(",")]
            row = self.rows.get(code)
            self._result = (tuple(row.get(n) for n in names)
                            if row is not None else None)

    def fetchone(self):
        return self._result


# ── Gate 1 · a run exists first, and it is interpretable ─────────────────────

def test_a_run_must_name_a_contract_this_build_knows():
    try:
        ComputeRun(1, "e", "FACTOR_MODEL_V99")
    except UnsupportedModelVersion:
        pass
    else:
        raise AssertionError("an uninterpretable run must not be constructible")


def test_a_run_with_no_version_is_refused():
    try:
        ComputeRun(1, "e", None)
    except UnsupportedModelVersion:
        pass
    else:
        raise AssertionError("unversioned is not a contract")


# ── Gate 2 · one statement carries everything ────────────────────────────────

def test_numerics_states_and_run_move_in_one_statement():
    sql, params = build_update("CBA", cba(), RUN)

    assert sql.count("UPDATE") == 1 and ";" not in sql
    assert "metric_states = %(metric_states)s::jsonb" in sql
    assert "compute_run_id = %(compute_run_id)s" in sql
    assert params["compute_run_id"] == 4711

    numeric_sets = [s for s in sql.split("SET", 1)[1].split(",")
                    if "metric_states" not in s and "compute_run_id" not in s]
    assert numeric_sets, "the numeric columns are in the same statement"


def test_the_writer_never_emits_a_second_statement_for_the_sidecar():
    cur = FakeCursor()
    write_row(cur, "CBA", cba(), RUN)
    assert len(cur.statements) == 1


# ── The translation boundary ──────────────────────────────────────────────────

def test_canonical_identity_translates_to_storage_at_one_point():
    assert column_for("ev_ebitda") == "ev_to_ebitda"
    assert column_for("ev_to_ebitda") == "ev_to_ebitda", "alias in, column out"
    assert column_for("roe") == "roe"
    assert canonical_for("ev_to_ebitda") == "ev_ebitda"


def test_the_canonical_to_storage_mapping_is_injective():
    """Two canonical metrics must never share a physical column.

    The alias tests guard the missing-mapping direction: a metric the writer
    fails to translate. This guards the opposite one — a collision, where two
    governed metrics write to the same column and the second silently
    overwrites the first, with both sidecar entries claiming to describe it.
    """
    columns: dict[str, str] = {}
    for metric in sorted(GOVERNED):
        column = column_for(metric)
        assert column not in columns, (
            f"{metric} and {columns[column]} both store in {column!r}; "
            f"one would silently overwrite the other")
        columns[column] = metric


def test_every_storage_column_round_trips_to_its_canonical_name():
    for canonical, column in STORAGE_COLUMN.items():
        assert normalise(canonical) == canonical, f"{canonical} is not canonical"
        assert canonical_for(column) == canonical, \
            f"{column} does not resolve back to {canonical}"


def test_the_statement_uses_physical_columns_and_canonical_parameters():
    # Built on the complete fixture: the canonical writer only ever emits a
    # complete row, so asserting the column mapping against a one-metric dict
    # would be asserting it against a statement that cannot occur.
    assessments = cba()
    assessments["ev_ebitda"] = assess("ev_ebitda", 9.0,
                                      Domain.GENERAL_CORPORATE,
                                      Observation(ebitda=1e9))
    sql, params = build_update("CBA", assessments, RUN)

    assert "ev_to_ebitda = %(m_ev_ebitda)s" in sql, \
        "physical column, canonical parameter — a mapping slip shows up as a " \
        "mismatch rather than overwriting the wrong column"
    assert params["m_ev_ebitda"] == 9.0


def test_an_ungoverned_metric_cannot_be_written():
    try:
        build_update("CBA", {"some_new_metric": assess(
            "some_new_metric", 1.0, Domain.GENERAL_CORPORATE)}, RUN)
    except WriteRefused as e:
        assert "not governed" in str(e)
    else:
        raise AssertionError("a metric the contract does not cover must refuse")


# ── Gate 4 · suppressed persists as NULL + cause ─────────────────────────────

def test_suppressed_metrics_are_null_in_the_column_with_a_stated_cause():
    _, params = build_update("CBA", cba(), RUN)
    states = json.loads(params["metric_states"])

    assert params["m_debt_to_equity"] is None
    assert params["m_net_margin"] is None
    assert states["debt_to_equity"]["cause"] == "domain"
    assert states["net_margin"]["cause"] == "domain"
    assert states["grossed_up_yield"]["cause"] == "source_unhealthy"
    assert states["roce"]["cause"] == "insufficient_history"


def test_the_observed_value_never_reaches_the_public_column():
    _, params = build_update("CBA", cba(), RUN)
    states = json.loads(params["metric_states"])

    assert params["m_debt_to_equity"] is None
    assert states["debt_to_equity"]["observed"] == 4.6, \
        "forensics live in the sidecar, where only a contract-aware reader looks"


def test_a_suppressed_metric_is_never_written_as_zero():
    _, params = build_update("CBA", cba(), RUN)
    for key in ("m_debt_to_equity", "m_net_margin", "m_grossed_up_yield"):
        assert params[key] is None and params[key] != 0


def test_applicable_metrics_keep_their_numbers_and_stay_out_of_the_sidecar():
    _, params = build_update("CBA", cba(), RUN)
    states = json.loads(params["metric_states"])

    assert params["m_roe"] == 0.1284 and params["m_pe_ratio"] == 19.2
    assert "roe" not in states and "pe_ratio" not in states


# ── Gate 5 · exact-run read-back reproduces the population ───────────────────

def test_read_back_reproduces_the_participating_population():
    cur = FakeCursor()
    before = cba()
    write_row(cur, "CBA", before, RUN)
    after = read_back(cur, "CBA", RUN, metrics=list(before))

    assert valid_population(before.values()) == valid_population(after.values())
    assert valid_population(after.values()) == ["pe_ratio", "roe"]


def test_read_back_reproduces_every_cause():
    cur = FakeCursor()
    before = cba()
    write_row(cur, "CBA", before, RUN)
    after = read_back(cur, "CBA", RUN, metrics=list(before))

    assert {m: a.cause for m, a in after.items()} == \
           {m: a.cause for m, a in before.items()}


def test_read_back_reproduces_the_states_not_merely_the_nulls():
    cur = FakeCursor()
    write_row(cur, "CBA", cba(), RUN)
    after = read_back(cur, "CBA", RUN, metrics=list(cba()))

    assert after["debt_to_equity"].state is Applicability.NOT_MEANINGFUL
    assert after["grossed_up_yield"].state is Applicability.UNAVAILABLE
    assert after["roce"].state is Applicability.INSUFFICIENT_DATA


def test_ungoverned_growth_metrics_carry_no_state():
    """A gap worth naming rather than discovering later.

    revenue_cagr_5y, eps_growth_3y_cagr and the other CAGRs have a genuine
    INSUFFICIENT_DATA dimension — a five-year figure computed from three years
    of history is not the same claim as one computed from five. None of them
    is in the V1 governed set, so none carries a state, and the writer
    correctly refuses to persist one under this contract. Closing that is a
    V2 decision, not something to slip into V1 after the freeze.
    """
    for metric in ("revenue_cagr_5y", "eps_growth_3y_cagr",
                   "revenue_growth_3y_cagr"):
        assert metric not in GOVERNED, f"{metric} joined V1 unnoticed"

        try:
            build_update("X", {metric: assess(metric, 0.3,
                                              Domain.GENERAL_CORPORATE)}, RUN)
        except WriteRefused:
            pass
        else:
            raise AssertionError(f"{metric} is ungoverned and must be refused")


def test_read_back_is_scoped_to_the_run_that_wrote_the_row():
    """Reading the current row and hoping it came from our write is the
    timestamp-matching fallacy in another costume."""
    cur = FakeCursor()
    write_row(cur, "CBA", cba(), RUN)

    later = ComputeRun(4712, "composite_score", LATEST_MODEL_VERSION)
    write_row(cur, "CBA", cba(), later)

    try:
        read_back(cur, "CBA", RUN, metrics=["roe"])
    except WriteRefused as e:
        assert "4712" in str(e) and "not verification" in str(e)
    else:
        raise AssertionError("a row overwritten by a later run is not proof")


def test_a_missing_row_is_refused_rather_than_reported_empty():
    cur = FakeCursor()
    try:
        read_back(cur, "NOPE", RUN, metrics=["roe"])
    except WriteRefused as e:
        assert "disappeared" in str(e)
    else:
        raise AssertionError("a vanished row is not an empty assessment")


# ── Gate 6 · contradictions fail closed ──────────────────────────────────────

def test_a_contradictory_pair_cannot_be_built():
    """persist_row makes this unreachable through the normal path, so the
    guard is asserted directly: assert_complete runs inside build_update."""
    from compute.engine.metric_states import assert_complete

    try:
        assert_complete({"roe": 0.18}, {"roe": {"state": "not_meaningful"}})
    except ValueError as e:
        assert "contradictory_state" in str(e)
    else:
        raise AssertionError("the writer must refuse a stale sidecar entry")


def test_write_all_writes_every_company_under_one_run():
    cur = FakeCursor()
    n = write_all(cur, {"CBA": cba(), "NAB": cba()}, RUN)

    assert n == 2 and len(cur.statements) == 2
    assert {r["compute_run_id"] for r in cur.rows.values()} == {4711}


# ── Standalone runner ─────────────────────────────────────────────────────────

# ── The canonical SET list is derived, and complete ──────────────────────────

def test_the_set_list_comes_from_the_registry_not_a_hand_written_list():
    """A hand-maintained list of 72 columns is a second declaration of what is
    governed, and the two diverge on the first metric added to a version --
    silently, because a column missing from an UPDATE does not fail."""
    from compute.engine.universe_writer import persisted_governed
    from compute.engine.metric_states import GOVERNED_METRICS
    from compute.engine.universe_writer import NOT_PERSISTED

    mapping = persisted_governed("FACTOR_MODEL_V2")
    expected = GOVERNED_METRICS["FACTOR_MODEL_V2"] - set(NOT_PERSISTED)

    assert set(mapping) == set(expected)


def test_no_two_metrics_may_claim_one_column():
    from compute.engine.universe_writer import persisted_governed
    mapping = persisted_governed("FACTOR_MODEL_V2")
    assert len(set(mapping.values())) == len(mapping)


def test_every_governed_column_is_assigned_even_when_the_value_is_absent():
    """The stale-survival rule, at the writer.

        "No value this run" must overwrite the previous run's value with NULL
        and the current state. Omitting the column is forbidden.

    2,954 yearly_metrics rows outlived the run that produced them because a
    producer simply did not touch them. A column left out of an UPDATE does
    not fail -- it keeps yesterday's number, which then sits beside today's
    sidecar and reads as current.
    """
    from compute.engine.applicability import Domain, assess
    from compute.engine.universe_writer import (
        ComputeRun, build_update, persisted_governed)

    mapping = persisted_governed("FACTOR_MODEL_V2")
    # Every governed metric assessed, all of them absent from the source.
    assessments = {m: assess(m, None, Domain.GENERAL_CORPORATE)
                   for m in mapping}
    run = ComputeRun(7, "test", "FACTOR_MODEL_V2")

    sql, params = build_update("TST", assessments, run)

    for column in mapping.values():
        assert f"{column} = %(" in sql, f"{column} not assigned"
    assert all(params[f"m_{m}"] is None for m in mapping)


def test_a_governed_metric_the_run_never_assessed_refuses_the_write():
    """It must abort, not arrive as SOURCE_MISSING. Reporting our own gap as
    the company having no value is the conflation this contract removes."""
    from compute.engine.applicability import Domain, assess
    from compute.engine.universe_writer import (
        ComputeRun, WriteRefused, build_update, persisted_governed)

    mapping = persisted_governed("FACTOR_MODEL_V2")
    partial = dict(sorted(mapping.items())[:-1])
    assessments = {m: assess(m, None, Domain.GENERAL_CORPORATE) for m in partial}
    run = ComputeRun(7, "test", "FACTOR_MODEL_V2")

    try:
        build_update("TST", assessments, run)
    except WriteRefused as e:
        assert "not assessed" in str(e)
    else:
        raise AssertionError("an unassessed governed metric must refuse the write")


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
