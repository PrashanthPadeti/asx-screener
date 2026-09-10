"""
One field definition, and a typed query representation
======================================================
Two maps became one, and the parser's canonical output stopped being SQL.

The registry is derived from the route's existing ALLOWED_FIELDS and
SORTABLE_COLS rather than retyped, so there is no opportunity to mistype a
column while tidying — and these tests assert the derivation is faithful to
both sources rather than merely plausible.

Run under pytest, or standalone:
    cd /opt/asx-screener/backend && ../asx-venv/bin/python tests/test_screener_fields.py
"""

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.parsed_query import (  # noqa: E402
    AllOf,
    Criterion,
    Direction,
    Ordering,
    ParsedQuery,
    canonicalise,
    to_legacy_sql,
)
from app.core.screener_fields import (  # noqa: E402
    FieldDef,
    UnknownField,
    build_registry,
    governed_fields,
    resolve,
)
from compute.engine.metric_registry import normalise  # noqa: E402
from compute.engine.screen_predicates import CriterionType  # noqa: E402

ROUTE = Path(__file__).resolve().parents[1] / "app/api/v1/routes/screener.py"


def _literal(name: str):
    tree = ast.parse(ROUTE.read_text(encoding="utf-8"))
    for node in tree.body:
        targets = ([node.target] if isinstance(node, ast.AnnAssign)
                   else node.targets if isinstance(node, ast.Assign) else [])
        for target in targets:
            if isinstance(target, ast.Name) and target.id == name:
                return ast.literal_eval(node.value)
    raise AssertionError(f"{name} not found in the route")


ALLOWED_FIELDS = _literal("ALLOWED_FIELDS")
SORTABLE_COLS = _literal("SORTABLE_COLS")
REGISTRY = build_registry(ALLOWED_FIELDS, SORTABLE_COLS)


# ── The derivation is faithful to both sources ───────────────────────────────

def test_every_filterable_field_survives():
    for key in ALLOWED_FIELDS:
        assert key in REGISTRY and REGISTRY[key].filterable


def test_every_sortable_field_survives():
    for key in SORTABLE_COLS:
        assert key in REGISTRY and REGISTRY[key].sortable


def test_no_column_is_changed_by_the_merge():
    """The mechanical part: tidying must not retype a column."""
    for key, info in ALLOWED_FIELDS.items():
        assert REGISTRY[key].column == info["col"], key
    for key, column in SORTABLE_COLS.items():
        assert REGISTRY[key].column == column, key


def test_the_two_maps_agreed_and_the_merge_keeps_it_that_way():
    both = set(ALLOWED_FIELDS) & set(SORTABLE_COLS)
    assert both, "the fixture must exercise the overlap"
    for key in both:
        assert ALLOWED_FIELDS[key]["col"] == SORTABLE_COLS[key] == \
            REGISTRY[key].column


def test_filter_only_and_sort_only_fields_are_both_represented():
    filter_only = [k for k, f in REGISTRY.items() if f.filterable and not f.sortable]
    sort_only = [k for k, f in REGISTRY.items() if f.sortable and not f.filterable]

    assert len(filter_only) > 100, "most fields are filter-only"
    assert set(sort_only) == {"asx_code", "company_name"}


# ── Governance is resolved once, here ────────────────────────────────────────

def test_a_governed_field_carries_its_canonical_identity():
    field = REGISTRY["debt_to_equity"]
    assert field.governed and field.canonical == "debt_to_equity"


def test_a_storage_spelling_resolves_to_the_governed_metric():
    """The key is an API name and may be a storage spelling; the canonical
    identity is what the contract knows."""
    field = REGISTRY.get("ev_to_ebitda")
    assert field is not None
    assert field.canonical == "ev_ebitda", "not the key"
    assert field.governed


def test_an_ungoverned_field_is_marked_as_such():
    """P0-A does not apply to all 309 fields, and the registry is where a
    caller learns which it is holding."""
    field = REGISTRY["sector"]
    assert not field.governed and field.canonical is None


def test_the_governed_subset_is_a_minority():
    governed = governed_fields(REGISTRY)
    assert 0 < len(governed) < len(REGISTRY) / 2


# ── Unknown fields refuse, and never default ─────────────────────────────────

def test_an_unknown_filter_field_raises():
    try:
        resolve(REGISTRY, "not_a_field")
    except UnknownField as e:
        assert "not_a_field" in str(e)
    else:
        raise AssertionError("an unknown field must not resolve")


def test_an_unknown_sort_field_raises_rather_than_becoming_market_cap():
    """The live gate violation this replaces: the route resolved an unknown
    sort_by to market_cap, silently re-sorting the page by something the
    caller never asked for."""
    try:
        resolve(REGISTRY, "not_a_field", for_sort=True)
    except UnknownField:
        pass
    else:
        raise AssertionError("a wrong answer must not be presented as ordinary")


def test_a_filterable_but_unsortable_field_refuses_to_sort():
    unsortable = next(k for k, f in REGISTRY.items()
                      if f.filterable and not f.sortable)
    resolve(REGISTRY, unsortable)                       # fine as a filter
    try:
        resolve(REGISTRY, unsortable, for_sort=True)
    except UnknownField as e:
        assert "not sortable" in str(e)
    else:
        raise AssertionError("sortability is a capability, not a suggestion")


def test_lookup_is_case_and_whitespace_insensitive():
    assert resolve(REGISTRY, "  Debt_To_Equity ").key == "debt_to_equity"


# ── The typed query ──────────────────────────────────────────────────────────

def test_canonicalisation_attaches_identity_and_governance():
    parsed = ParsedQuery(
        expression=AllOf((
            Criterion("ev_to_ebitda", CriterionType.REQUIRED, "lt", 12),
            Criterion("sector", CriterionType.REQUIRED, "eq", "Materials"))),
        ordering=Ordering("grossed_up_yield", Direction.DESC))
    out = canonicalise(parsed, REGISTRY)

    assert out.criteria[0].canonical == "ev_ebitda" and out.criteria[0].governed
    assert out.criteria[1].canonical is None and not out.criteria[1].governed
    assert out.ordering.governed and out.ordering.canonical == "grossed_up_yield"


def test_governed_and_ungoverned_criteria_are_separable():
    parsed = canonicalise(ParsedQuery(expression=AllOf((
        Criterion("roe", CriterionType.REQUIRED, "gt", 0.1),
        Criterion("sector", CriterionType.REQUIRED, "eq", "Materials")))),
        REGISTRY)

    assert [c.field for c in parsed.governed_criteria] == ["roe"]
    assert [c.field for c in parsed.ungoverned_criteria] == ["sector"]


def test_a_query_touching_nothing_governed_needs_no_run_scope():
    parsed = canonicalise(ParsedQuery(expression=AllOf((
        Criterion("sector", CriterionType.REQUIRED, "eq", "Materials"),))),
        REGISTRY)
    assert not parsed.requires_run_scope


def test_a_governed_ordering_alone_requires_a_run_scope():
    parsed = canonicalise(
        ParsedQuery(ordering=Ordering("grossed_up_yield")), REGISTRY)
    assert parsed.requires_run_scope, \
        "ranking on a governed metric needs the contract even with no filters"


def test_canonicalisation_rejects_an_unknown_field_before_the_database():
    try:
        canonicalise(ParsedQuery(expression=AllOf((
            Criterion("nope", CriterionType.REQUIRED, "gt", 1),))), REGISTRY)
    except UnknownField:
        pass
    else:
        raise AssertionError("resolution failures belong here, not at the DB")


# ── The adapter compiles one way only ────────────────────────────────────────

def test_the_adapter_produces_the_legacy_shape():
    parsed = canonicalise(ParsedQuery(expression=AllOf((
        Criterion("roe", CriterionType.REQUIRED, "gt", 10),))), REGISTRY)
    where, params = to_legacy_sql(parsed, REGISTRY)

    assert "(u.roe) >" in where and list(params.values())[0] == 10 * \
        REGISTRY["roe"].scale


def test_the_adapter_applies_the_field_scale():
    field = next(f for f in REGISTRY.values()
                 if f.type == "number" and f.scale != 1.0)
    parsed = canonicalise(ParsedQuery(expression=AllOf((
        Criterion(field.key, CriterionType.REQUIRED, "gt", 2),))), REGISTRY)
    _, params = to_legacy_sql(parsed, REGISTRY)

    assert list(params.values())[0] == 2 * field.scale


def test_an_excluded_criterion_negates_in_the_legacy_shape():
    parsed = canonicalise(ParsedQuery(expression=AllOf((
        Criterion("roe", CriterionType.EXCLUDED, "lt", 5),))), REGISTRY)
    where, _ = to_legacy_sql(parsed, REGISTRY)
    # The AllOf wrapper parenthesises each operand, so the negation is nested
    # rather than leading. The semantic property is that it is negated at all.
    assert "NOT (" in where and "(u.roe) <" in where


def test_there_is_no_inverse_adapter():
    """Recovering typed semantics from SQL is the loss this module prevents,
    so no function offers to do it."""
    import app.core.parsed_query as module

    reverse = [n for n in dir(module)
               if "from_sql" in n or "from_legacy" in n or "parse_sql" in n]
    assert not reverse, f"one-way only, found: {reverse}"


def test_an_empty_query_compiles_to_a_true_clause():
    where, params = to_legacy_sql(ParsedQuery(), REGISTRY)
    assert where == "TRUE" and params == {}


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
    print(f"\nregistry: {len(REGISTRY)} fields, "
          f"{len(governed_fields(REGISTRY))} governed")
    sys.exit(1 if failures else 0)
