"""
A served row is a decoded row, not a selected one
=================================================
The defect this closes: filtering and ranking learned the applicability
contract, and projection did not. A screen would correctly refuse to rank a
bank on EV/EBITDA and then return that same bank's EV/EBITDA in the row, and
``/batch`` did it with no filtering in front of it at all.

Four situations produce a null and they carry different meanings. These tests
assert the meanings survive, because a null whose reason is lost is exactly
the collapse the whole contract exists to prevent.

Run under pytest, or standalone:
    cd /opt/asx-screener/backend && ../asx-venv/bin/python tests/test_row_projection.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.row_projection import (  # noqa: E402
    NO_CONTRACT,
    OUTSIDE_SNAPSHOT,
    MissingProjectedColumn,
    expected_outputs,
    governed_columns,
    project_row,
)
from compute.engine.applicability import Domain, Observation, assess, unhealthy  # noqa: E402
from compute.engine.metric_states import persist_row  # noqa: E402
from compute.engine.universe_writer import column_for  # noqa: E402

V1 = "FACTOR_MODEL_V1"
RUN = 4711


def promised(*metrics) -> dict:
    """The governed outputs a fixture's notional response advertises."""
    return {m: column_for(m) for m in metrics}


THREE = promised("debt_to_equity", "ev_ebitda", "roe")


def project(row, run_ids, expected=THREE):
    return project_row(row, model_version=V1, run_ids=run_ids,
                       expected=expected)


def stored_row(assessments, *, run_id=RUN, **plain):
    """A row as the database holds it: numeric columns, sidecar, run id."""
    values, states = persist_row(assessments)
    row = {column_for(m): v for m, v in values.items()}
    row.update(plain)
    row["metric_states"] = states
    row["compute_run_id"] = run_id
    return row


def a_bank():
    return {
        "debt_to_equity": assess("debt_to_equity", 4.6, Domain.BANK),
        "ev_ebitda": assess("ev_ebitda", 11.0, Domain.BANK),
        "roe": assess("roe", 0.1284, Domain.BANK,
                      Observation(equity=8e10, earnings=1e10)),
    }


def an_industrial():
    obs = Observation(equity=8e10, earnings=1e10)
    return {
        "debt_to_equity": assess("debt_to_equity", 0.4,
                                 Domain.GENERAL_CORPORATE),
        "ev_ebitda": assess("ev_ebitda", 8.2, Domain.GENERAL_CORPORATE),
        "roe": assess("roe", 0.22, Domain.GENERAL_CORPORATE, obs),
    }


# ── The value stands only when the contract says applicable ──────────────────

def test_an_applicable_metric_keeps_its_value():
    row = stored_row(an_industrial(), asx_code="IND", price=10.0)
    values, states = project(row, [RUN])

    assert values["roe"] == 0.22
    assert values[column_for("ev_ebitda")] == 8.2
    assert states == {}, "applicable metrics carry no entry"


def test_a_suppressed_metric_is_nulled_and_explained():
    row = stored_row(a_bank(), asx_code="CBA", price=100.0)
    values, states = project(row, [RUN])

    assert values["debt_to_equity"] is None
    assert states["debt_to_equity"]["state"] == "not_meaningful"
    assert states["debt_to_equity"]["cause"] == "domain"
    assert states["debt_to_equity"]["reason"], "a bare state is not an answer"


def test_a_source_unhealthy_metric_is_not_reported_as_not_applicable():
    """FEED_INCOMPLETE is not NOT_APPLICABLE — a broken dividend feed must not
    render as 'this company pays no dividend'."""
    row = stored_row({"grossed_up_yield": unhealthy("grossed_up_yield",
                                                    "feed incomplete")},
                     asx_code="FEED")
    _, states = project(row, [RUN], promised("grossed_up_yield"))

    assert states["grossed_up_yield"]["state"] == "unavailable"
    assert states["grossed_up_yield"]["cause"] == "source_unhealthy"


# ── The row's standing against the contract ──────────────────────────────────

def test_without_a_contract_every_governed_metric_is_withheld():
    """Pre-migration, no governed value on the database is interpretable —
    but the watchlist must still show a price."""
    row = stored_row(an_industrial(), asx_code="IND", price=10.0,
                     market_cap=5000.0)
    values, states = project(row, None)

    assert values["roe"] is None and values["debt_to_equity"] is None
    assert values["price"] == 10.0 and values["market_cap"] == 5000.0
    assert states["roe"] == {"state": "unavailable",
                             "cause": "source_missing",
                             "reason": NO_CONTRACT}


def test_a_row_outside_the_snapshot_is_withheld_for_a_different_reason():
    """Its sidecar was written under semantics this response is not speaking,
    so reading it would mix two contracts in one payload."""
    row = stored_row(an_industrial(), asx_code="OLD", price=10.0, run_id=99)
    values, states = project(row, [RUN])

    assert values["roe"] is None
    assert states["roe"]["reason"] == OUTSIDE_SNAPSHOT
    assert states["roe"]["reason"] != NO_CONTRACT, \
        "an absent contract and a stale row are different facts"


def test_a_row_with_no_run_id_is_not_treated_as_in_scope():
    row = stored_row(an_industrial(), asx_code="LEGACY", run_id=None)
    values, _ = project(row, [RUN])
    assert values["roe"] is None, "a legacy row predates the contract"


# ── What must never cross the boundary ───────────────────────────────────────

def test_the_forensic_observed_value_never_reaches_the_client():
    """The sidecar keeps the suppressed number so an operator can audit the
    decision. Serving it hands the frontend back exactly what was suppressed,
    and a frontend that finds a number will display it."""
    row = stored_row(a_bank(), asx_code="CBA")
    assert any("observed" in e for e in row["metric_states"].values()), \
        "the fixture must actually carry a forensic value"

    values, states = project(row, [RUN])

    for metric, entry in states.items():
        assert "observed" not in entry, f"{metric} leaked its observed value"
    assert 4.6 not in [v for v in values.values() if isinstance(v, float)]


def test_the_machinery_columns_are_not_served_as_fields():
    row = stored_row(a_bank(), asx_code="CBA")
    values, _ = project(row, [RUN])

    assert "metric_states" not in values, \
        "the raw sidecar would re-expose the observed values just stripped"
    assert "compute_run_id" not in values


def test_ungoverned_columns_are_never_touched():
    plain = dict(asx_code="IND", company_name="Industrial Ltd",
                 sector="Materials", price=10.0, rsi_14=55.0, sma_50=9.4)
    for run_ids in ([RUN], [99], None):
        row = stored_row(an_industrial(), **plain)
        values, _ = project(row, run_ids)
        for key, expected in plain.items():
            assert values[key] == expected, f"{key} changed for {run_ids}"


# ── Identity, not spelling ───────────────────────────────────────────────────

def test_a_metric_stored_under_another_spelling_is_still_projected():
    """The sidecar is keyed canonically and the row by column. Comparing them
    directly is how ev_to_ebitda escaped assessment once already."""
    assert column_for("ev_ebitda") != "ev_ebitda", \
        "the fixture must exercise a differing spelling"

    row = stored_row(a_bank(), asx_code="CBA")
    values, states = project(row, [RUN])

    assert values[column_for("ev_ebitda")] is None
    assert "ev_ebitda" in states


def test_governed_columns_covers_the_pinned_version():
    """42 canonical metrics are governed in V1. The field registry reports 37
    governed *fields*, which is a different denominator — five governed
    metrics are computed and stored without being exposed as an API field."""
    from compute.engine.metric_states import GOVERNED_METRICS

    columns = governed_columns(V1)
    assert set(columns) == set(GOVERNED_METRICS[V1])
    assert columns["ev_ebitda"] == column_for("ev_ebitda")


def test_no_two_governed_metrics_share_a_column():
    """Projection nulls by column. Two canonical metrics mapped to one column
    would make suppressing either one suppress both, and the state map would
    claim only one of them."""
    columns = governed_columns(V1)
    collisions = {c for c in columns.values()
                  if list(columns.values()).count(c) > 1}
    assert not collisions, f"column reused by several metrics: {collisions}"


# ── Fail closed ──────────────────────────────────────────────────────────────

def test_a_contradictory_row_withholds_rather_than_serves():
    """A value beside an entry is the state violations() exists to catch. On
    the read path the safe reading of a contradiction is the one that
    withholds — serving the number would defeat the sidecar entirely."""
    row = stored_row(a_bank(), asx_code="CBA")
    row["debt_to_equity"] = 4.6              # as a torn write would leave it

    values, states = project(row, [RUN])
    assert values["debt_to_equity"] is None
    assert states["debt_to_equity"]["state"] == "not_meaningful"


def test_a_sidecar_returned_as_text_is_decoded():
    """Not every driver hands back JSONB as a dict."""
    row = stored_row(a_bank(), asx_code="CBA")
    row["metric_states"] = json.dumps(row["metric_states"])

    values, states = project(row, [RUN])
    assert values["debt_to_equity"] is None and "debt_to_equity" in states


def test_an_entry_for_an_ungoverned_metric_is_ignored_not_applied():
    row = stored_row(an_industrial(), asx_code="IND", sma_50=9.4)
    row["metric_states"] = dict(row["metric_states"])
    row["metric_states"]["sma_50"] = {"state": "unavailable"}

    values, states = project(row, [RUN])
    assert values["sma_50"] == 9.4, "an ungoverned column must not be nulled"
    assert "sma_50" not in states


# ── SQL omission is not a financial state ────────────────────────────────────
# Gate A found governed fields arriving as null with no cause because the
# query never selected them. A column absent from the SQL row means the
# application failed to fetch something its own contract promises. It is not
# SOURCE_MISSING, not UNAVAILABLE and not NOT_MEANINGFUL, and letting it
# become one would make a deleted SELECT column indistinguishable from correct
# fail-closed behaviour.

PROMISED = {"roe": "roe", "ev_ebitda": column_for("ev_ebitda"),
            "interest_coverage": "interest_coverage"}


def test_an_advertised_field_absent_from_the_row_is_an_error_not_a_state():
    """Inside a contract the promise is binding."""
    row = stored_row(an_industrial(), asx_code="IND")   # no interest_coverage
    try:
        project_row(row, model_version=V1, run_ids=[RUN], expected=PROMISED)
    except MissingProjectedColumn as e:
        assert "interest_coverage" in str(e)
    else:
        raise AssertionError(
            "a field the response promises and the query never fetched must "
            "fail loudly, not tell the customer their data is unavailable")


def test_without_a_contract_an_unfetched_field_is_synthesised_not_demanded():
    """Nothing governed is interpretable, so the legacy column need not be
    fetched at all — containment does not require widening every SELECT."""
    row = stored_row(an_industrial(), asx_code="IND")   # no interest_coverage
    values, states = project_row(row, model_version=V1, run_ids=None,
                                 expected=PROMISED)

    assert values["interest_coverage"] is None
    assert states["interest_coverage"]["cause"] == "source_missing"
    assert states["interest_coverage"]["reason"] == NO_CONTRACT


def test_every_promised_field_is_explained_when_there_is_no_contract():
    """Both halves together, which is what Gate A actually asserts."""
    row = stored_row(an_industrial(), asx_code="IND", price=10.0)
    values, states = project_row(row, model_version=V1, run_ids=None,
                                 expected=PROMISED)

    for metric, column in PROMISED.items():
        assert values[column] is None, f"{column} leaked"
        assert metric in states, f"{column} blank without a cause"
    assert values["price"] == 10.0


def test_a_row_outside_the_snapshot_explains_unfetched_fields_too():
    row = stored_row(an_industrial(), asx_code="OLD", run_id=99)
    _, states = project_row(row, model_version=V1, run_ids=[RUN],
                            expected=PROMISED)
    assert states["interest_coverage"]["reason"] == OUTSIDE_SNAPSHOT


def test_expected_outputs_is_an_intersection_not_the_whole_governed_set():
    """Being governed means 'if consumed, these semantics apply'. It does not
    oblige every endpoint to expose every governed metric."""
    promised = expected_outputs(V1, {"roe", "price", "sector"})

    assert promised == {"roe": "roe"}
    assert "price" not in promised.values(), "ungoverned fields are not owned"
    assert len(promised) < len(governed_columns(V1))


def test_an_unadvertised_governed_metric_is_neither_demanded_nor_explained():
    """A governed metric a surface does not expose is a design choice, so it
    must not appear in that surface's state map either."""
    row = stored_row(a_bank(), asx_code="CBA")
    _, states = project_row(row, model_version=V1, run_ids=[RUN],
                            expected={"roe": "roe"})

    assert "debt_to_equity" not in states, \
        "explaining a field the response does not carry is noise"


# ── Standalone runner ─────────────────────────────────────────────────────────

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
