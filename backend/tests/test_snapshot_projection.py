"""
One request, one snapshot, two failure policies
===============================================
The bypass this closes: the screener learned to *filter* through the
applicability contract and still *returned* the raw stored number, so a query
could correctly refuse to rank CBA on current_ratio and hand back CBA's
current_ratio in the row.

Filtering and projection need different failure policies over the same
resolution:

    ungoverned + contract      execute normally   decode under that contract
    ungoverned + no contract   execute normally   governed -> null + cause
    governed   + contract      contract-aware     same contract
    governed   + no contract   503                no rows at all
    scope changes mid-request  irrelevant         keeps the resolved snapshot

Two resolver calls — one for planning, one for projection — would satisfy
every row of that table and still be wrong, because a compute finishing
between them gives one response a filtered set from one snapshot and decoded
values from another. So the structural half of this suite asserts each handler
resolves exactly once.

Requires the app's dependencies; run under the server venv:
    cd /opt/asx-screener/backend && ../asx-venv/bin/python tests/test_snapshot_projection.py
"""

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROUTE = Path(__file__).resolve().parents[1] / "app/api/v1/routes/screener.py"

from app.api.v1.routes.screener import Snapshot  # noqa: E402
from app.core.parsed_query import (  # noqa: E402
    AllOf, Criterion, Ordering, ParsedQuery, canonicalise,
)
from app.core.row_projection import expected_outputs  # noqa: E402
from app.core.screener_fields import build_registry  # noqa: E402
from compute.engine.applicability import Domain, Observation, assess  # noqa: E402
from compute.engine.metric_states import (  # noqa: E402
    LATEST_MODEL_VERSION, persist_row,
)
from compute.engine.screen_predicates import CriterionType  # noqa: E402
from app.schemas.screener import ScreenerRow  # noqa: E402
from compute.engine.screen_sql import RunScope, ValidatedRun  # noqa: E402
from compute.engine.universe_writer import column_for  # noqa: E402
from fastapi import HTTPException  # noqa: E402


def _literal(name):
    tree = ast.parse(ROUTE.read_text(encoding="utf-8"))
    for node in tree.body:
        targets = ([node.target] if isinstance(node, ast.AnnAssign)
                   else node.targets if isinstance(node, ast.Assign) else [])
        for t in targets:
            if isinstance(t, ast.Name) and t.id == name:
                return ast.literal_eval(node.value)
    raise AssertionError(f"{name} not found")


REGISTRY = build_registry(_literal("ALLOWED_FIELDS"), _literal("SORTABLE_COLS"))
RUN = 4711
SCOPE = RunScope.from_validated_runs(
    [ValidatedRun(RUN, "FACTOR_MODEL_V1", (), validated=True)])

WITH_CONTRACT = Snapshot(SCOPE)
NO_CONTRACT = Snapshot(None, "the canonical recompute has not run.")


def ungoverned():
    return canonicalise(ParsedQuery(
        expression=AllOf((Criterion("sector", CriterionType.REQUIRED,
                                    "eq", "Materials"),)),
        ordering=Ordering("market_cap")), REGISTRY)


def governed():
    return canonicalise(ParsedQuery(
        ordering=Ordering("grossed_up_yield")), REGISTRY)


#: Every governed column ScreenerRow advertises. A fixture carrying fewer
#: would not be a realistic SQL row: inside a contract the projector requires
#: each promised field to have been fetched, and a thin fixture would fail for
#: that reason rather than for the behaviour under test.
PROMISED = expected_outputs(LATEST_MODEL_VERSION, ScreenerRow.model_fields)


def base_row(**plain):
    """A fetched row: every promised governed column present, unset."""
    row = {column: None for column in PROMISED.values()}
    row.update(plain)
    return row


def cba_row(run_id=RUN):
    """A bank: leverage and liquidity are not meaningful, ROE is."""
    values, states = persist_row({
        "debt_to_equity": assess("debt_to_equity", 4.6, Domain.BANK),
        "current_ratio": assess("current_ratio", 1.1, Domain.BANK),
        "roe": assess("roe", 0.1284, Domain.BANK,
                      Observation(equity=8e10, earnings=1e10)),
    })
    row = base_row(asx_code="CBA", company_name="Commonwealth Bank",
                   sector="Financials", price=100.0, market_cap=9000.0,
                   metric_states=states, compute_run_id=run_id)
    row.update({column_for(m): v for m, v in values.items()})
    return row


# ── The policy table ─────────────────────────────────────────────────────────

def test_ungoverned_with_a_contract_does_not_constrain_membership():
    """Passing the scope would add a compute_run_id predicate to an ordinary
    sector screen, so a newly listed company not yet in the current compute
    run would vanish from results it belongs in."""
    assert WITH_CONTRACT.for_filtering(ungoverned()) is None


def test_ungoverned_with_a_contract_still_decodes_the_rows():
    served = WITH_CONTRACT.project([cba_row()])[0]

    assert served.current_ratio is None and served.debt_to_equity is None
    assert served.roe == 0.1284, "an applicable metric survives projection"
    assert served.metric_states["current_ratio"]["cause"] == "domain"


def test_ungoverned_without_a_contract_still_executes():
    assert NO_CONTRACT.for_filtering(ungoverned()) is None


def test_ungoverned_without_a_contract_withholds_every_governed_field():
    """The behaviour proved at the last gate — a sector screen works before
    migration — must not become a licence to leak."""
    served = NO_CONTRACT.project([cba_row()])[0]

    assert served.price == 100.0 and served.market_cap == 9000.0
    assert served.sector == "Financials"
    assert served.roe is None and served.current_ratio is None
    assert served.metric_states["roe"]["cause"] == "source_missing"


def test_governed_with_a_contract_uses_that_same_scope():
    assert WITH_CONTRACT.for_filtering(governed()) is SCOPE


def test_governed_without_a_contract_refuses():
    try:
        NO_CONTRACT.for_filtering(governed())
    except HTTPException as exc:
        assert exc.status_code == 503
        assert "recompute has not run" in exc.detail, \
            "the reason must survive; two ways to have no contract are two " \
            "different operational states"
    else:
        raise AssertionError("a governed question without a contract is "
                             "unanswerable and must not be answered")


def test_a_row_outside_the_snapshot_keeps_its_identity_and_loses_its_metrics():
    """Dropping it would read to a user as a delisting."""
    served = WITH_CONTRACT.project([cba_row(run_id=99)])[0]

    assert served.asx_code == "CBA" and served.price == 100.0
    assert served.roe is None
    assert "outside the validated snapshot" in served.metric_states["roe"]["reason"]


def newly_listed():
    """A company that satisfies an ordinary filter and has never been through
    a factor-model run: no governed values, no sidecar, no attribution."""
    return base_row(asx_code="NEW", company_name="Newly Listed Ltd",
                    sector="Financials", price=2.50, market_cap=120.0,
                    metric_states={}, compute_run_id=None)


def test_a_new_listing_stays_in_an_ungoverned_screen():
    """Discovery completeness. A company must not disappear from
    `sector = Financials ORDER BY market_cap` merely because it has not yet
    participated in the latest factor-model run. Membership is an ordinary
    universe question; the snapshot governs interpretation, not existence.

    This is the test that protects the judgement — putting a compute_run_id
    predicate on an ungoverned screen would delete this row, and no comment
    prevents someone adding one later.
    """
    assert WITH_CONTRACT.for_filtering(ungoverned()) is None, \
        "no compute_run predicate may constrain ungoverned membership"

    served = WITH_CONTRACT.project([cba_row(), newly_listed()])
    codes = [r.asx_code for r in served]
    assert codes == ["CBA", "NEW"], "the new listing is a member"


def test_one_response_may_mix_compatible_and_incompatible_rows():
    """The row-by-row rule: compatibility is a property of the row against
    the snapshot, not of the request. Both companies are returned; only the
    attributable one exposes governed values."""
    cba, new = WITH_CONTRACT.project([cba_row(), newly_listed()])

    # Attributable to the snapshot: governed values decode normally.
    assert cba.roe == 0.1284
    assert cba.current_ratio is None, "still suppressed on its own merits"
    assert cba.metric_states["current_ratio"]["cause"] == "domain"

    # Not attributable: ordinary fields stay, governed fields fail closed.
    assert new.price == 2.50 and new.market_cap == 120.0
    assert new.sector == "Financials"
    assert new.roe is None
    assert new.metric_states["roe"]["cause"] == "source_missing"
    assert new.metric_states["roe"]["reason"] != \
        cba.metric_states["current_ratio"]["reason"], \
        "a run mismatch and a domain judgement are different facts"


# ── What must never leave ────────────────────────────────────────────────────

def test_the_forensic_observed_value_never_reaches_the_client():
    for snapshot in (WITH_CONTRACT, NO_CONTRACT):
        served = snapshot.project([cba_row()])[0]
        for metric, entry in served.metric_states.items():
            assert "observed" not in entry, f"{metric} leaked its observation"


def test_the_csv_projection_matches_the_json_projection():
    """An export is a response. A number withheld from the page must not
    arrive in a file the user keeps."""
    row = cba_row()
    served = WITH_CONTRACT.project([row])[0]
    values = WITH_CONTRACT.projected_values(row, ScreenerRow.model_fields)

    assert values["current_ratio"] is None and served.current_ratio is None
    assert values["debt_to_equity"] is None and served.debt_to_equity is None
    assert values["roe"] == served.roe == 0.1284


# ── One resolution per request ───────────────────────────────────────────────

def _handlers():
    tree = ast.parse(ROUTE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            decorated = any(
                isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
                and d.func.attr in ("post", "get")
                for d in node.decorator_list)
            if decorated:
                yield node


def test_no_handler_resolves_the_snapshot_twice():
    """Two resolutions recreate the mid-request race ScreenPlan removed."""
    for fn in _handlers():
        calls = [n for n in ast.walk(fn)
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                 and n.func.id == "resolve_snapshot"]
        assert len(calls) <= 1, \
            f"{fn.name} resolves the snapshot {len(calls)} times"


def test_every_handler_that_serves_governed_columns_resolves_one():
    """Scoped to handlers that actually emit governed data: those returning
    ScreenerRow, and the CSV exports. An endpoint reading the universe for
    some other purpose is not in scope and must not be forced to resolve."""
    source = ROUTE.read_text(encoding="utf-8")
    checked = []
    for fn in _handlers():
        body = ast.get_source_segment(source, fn) or ""
        serves = ("ScreenerRow" in body or "build_screener_sql" in body
                  or "_EXPORT_COLS" in body)
        if not serves:
            continue
        checked.append(fn.name)
        assert "resolve_snapshot" in body, \
            f"{fn.name} serves governed columns without a snapshot"

    assert len(checked) >= 5, \
        f"expected batch, screener, query and both exports; saw {checked}"


def test_no_raw_row_is_constructed_anywhere():
    """ScreenerRow(**dict(r)) is the bypass in its original form."""
    source = ROUTE.read_text(encoding="utf-8")
    assert "ScreenerRow(**dict(" not in source, \
        "a row built straight from the database skips the contract"


def test_the_cache_key_is_snapshot_scoped():
    """A cached body was projected under the snapshot current when it was
    stored; serving it after a recompute reintroduces the inconsistency by a
    slower route."""
    source = ROUTE.read_text(encoding="utf-8")
    start = source.find("cache_key = make_key(")
    assert start != -1, "the cache key must still be built here"
    assert "snapshot.identifier" in source[start:start + 200], \
        "the snapshot must be part of the key, not only of the response"


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
