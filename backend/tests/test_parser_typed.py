"""
The parser emits meaning, and the legacy shape is compiled from it
=================================================================
Surgical extraction, not a rewrite. Same tokeniser, same grammar, same
precedence and grouping — only what the parse *returns* changes. So the
governing test is that the accepted language is unchanged and the two emit
paths agree:

    parse_query(text)                       -> legacy fragment  (old path)
    to_legacy_sql(parse_query_typed(text))  -> legacy fragment  (new path)

Anything the old path accepts, the new one must accept and compile
equivalently. Anything it rejects, the new one must still reject — this is a
correctness migration, not a language redesign.

The grouping tests matter most. The grammar can express (A AND B) OR C, and
flattening that into a list of criteria would turn a disjunction into a
conjunction: a wrong answer rather than a lost convenience.

Run under pytest, or standalone:
    cd /opt/asx-screener/backend && ../asx-venv/bin/python tests/test_parser_typed.py
"""

import ast
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.parsed_query import (  # noqa: E402
    AllOf,
    AnyOf,
    Criterion,
    canonicalise,
    to_legacy_sql,
    walk,
)
from app.core.query_parser import (  # noqa: E402
    QueryParseError,
    parse_query,
    parse_query_typed,
)
from app.core.screener_fields import build_registry  # noqa: E402

ROUTE = Path(__file__).resolve().parents[1] / "app/api/v1/routes/screener.py"


def _literal(name: str):
    tree = ast.parse(ROUTE.read_text(encoding="utf-8"))
    for node in tree.body:
        targets = ([node.target] if isinstance(node, ast.AnnAssign)
                   else node.targets if isinstance(node, ast.Assign) else [])
        for t in targets:
            if isinstance(t, ast.Name) and t.id == name:
                return ast.literal_eval(node.value)
    raise AssertionError(f"{name} not found")


ALLOWED_FIELDS = _literal("ALLOWED_FIELDS")
SORTABLE_COLS = _literal("SORTABLE_COLS")
REGISTRY = build_registry(ALLOWED_FIELDS, SORTABLE_COLS)

QUERIES = [
    "roe > 10",
    "roe > 10 AND roce > 10",
    "roe > 10 AND roce > 10 AND roic > 10",
    "roe > 10 OR roce > 10",
    "roe > 10 AND (roce > 10 OR roic > 10)",
    "(roe > 10 AND roce > 10) OR roic > 20",
    "sector = 'Materials'",
    "sector = 'Materials' AND market_cap > 1000",
    "is_reit = true",
    "is_reit",
    "is_reit = false AND pe_ratio < 15",
    "pe_ratio < 15 AND sector != 'Energy'",
    "roe >= 10 AND pe_ratio <= 20",
]


def typed(text: str):
    return parse_query_typed(text, ALLOWED_FIELDS)


# ── The accepted language is unchanged ───────────────────────────────────────

def test_every_query_the_old_path_accepts_the_new_one_accepts():
    for text in QUERIES:
        parse_query(text, ALLOWED_FIELDS)      # would raise on rejection
        typed(text)


def test_rejections_are_unchanged():
    for bad in ("", "   ", "not_a_field > 1", "roe >", "roe > 'text'",
                "is_reit > 5", "roe > 10 AND"):
        old_failed = new_failed = False
        try:
            parse_query(bad, ALLOWED_FIELDS)
        except QueryParseError:
            old_failed = True
        try:
            typed(bad)
        except QueryParseError:
            new_failed = True
        assert old_failed == new_failed, f"{bad!r} disagrees"
        assert old_failed, f"{bad!r} should be rejected by both"


# ── Grouping survives, because the tree does ─────────────────────────────────

def test_a_conjunction_is_an_allof():
    expr = typed("roe > 10 AND roce > 10").expression
    assert isinstance(expr, AllOf) and len(expr.operands) == 2


def test_a_disjunction_is_an_anyof():
    expr = typed("roe > 10 OR roce > 10").expression
    assert isinstance(expr, AnyOf)


def test_precedence_is_preserved_as_structure():
    """AND binds tighter than OR: A OR B AND C is A OR (B AND C)."""
    expr = typed("roe > 10 OR roce > 10 AND roic > 10").expression
    assert isinstance(expr, AnyOf)
    assert isinstance(expr.operands[1], AllOf)


def test_parentheses_override_precedence_in_the_tree():
    expr = typed("roe > 10 AND (roce > 10 OR roic > 10)").expression
    assert isinstance(expr, AllOf)
    assert isinstance(expr.operands[1], AnyOf)


def test_flattening_would_have_lost_the_distinction():
    """The reason the tree exists: two queries with identical leaves and
    opposite meaning."""
    conjunction = typed("roe > 10 AND roce > 10")
    disjunction = typed("roe > 10 OR roce > 10")

    assert [c.field for c in conjunction.criteria] == \
           [c.field for c in disjunction.criteria]
    assert type(conjunction.expression) is not type(disjunction.expression)


def test_walk_reaches_every_leaf_of_a_nested_tree():
    parsed = typed("roe > 10 AND (roce > 10 OR roic > 20)")
    assert sorted(c.field for c in walk(parsed.expression)) == \
        ["roce", "roe", "roic"]


# ── The two emit paths agree ─────────────────────────────────────────────────

def _sqlite(fragment: str) -> str:
    """Postgres-isms the fixture table does not need."""
    return fragment.replace("::int", "")


def build_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE u (asx_code TEXT, roe REAL, roce REAL, "
                 "roic REAL, pe_ratio REAL, market_cap REAL, sector TEXT, "
                 "is_reit INTEGER)")
    rows = [
        ("AAA", 0.20, 0.20, 0.25, 12.0, 5000.0, "Materials", 0),
        ("BBB", 0.05, 0.30, 0.05, 18.0, 2000.0, "Energy", 0),
        ("CCC", 0.25, 0.05, 0.30, 25.0, 800.0, "Materials", 1),
        ("DDD", 0.02, 0.02, 0.02, 9.0, 400.0, "Financials", 0),
    ]
    conn.executemany("INSERT INTO u VALUES (?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    return conn


def members(conn, fragment: str, params: dict) -> list[str]:
    sql = f"SELECT asx_code FROM u WHERE {_sqlite(fragment)} ORDER BY asx_code"
    return [r[0] for r in conn.execute(sql, params)]


def test_both_paths_produce_the_same_membership():
    conn = build_db()
    for text in QUERIES:
        old_where, old_params = parse_query(text, ALLOWED_FIELDS)
        new_where, new_params = to_legacy_sql(
            canonicalise(typed(text), REGISTRY), REGISTRY)

        assert members(conn, old_where, old_params) == \
            members(conn, new_where, new_params), text


def test_the_fixture_discriminates():
    """Guards the guard: if every query returned everyone, agreement is
    trivial and proves nothing."""
    conn = build_db()
    sizes = set()
    for text in QUERIES:
        where, params = parse_query(text, ALLOWED_FIELDS)
        sizes.add(len(members(conn, where, params)))
    assert len(sizes) > 2


def test_the_scale_factor_is_applied_exactly_once():
    """The typed node keeps the value as typed; the compiler scales it. Both
    paths must land on the same number, not one squared."""
    old_where, old_params = parse_query("roe > 10", ALLOWED_FIELDS)
    new_where, new_params = to_legacy_sql(
        canonicalise(typed("roe > 10"), REGISTRY), REGISTRY)

    assert list(old_params.values()) == list(new_params.values())
    assert list(new_params.values())[0] == 10 * REGISTRY["roe"].scale


def test_boolean_shapes_match():
    for text in ("is_reit", "is_reit = true", "is_reit = false"):
        old_where, _ = parse_query(text, ALLOWED_FIELDS)
        new_where, _ = to_legacy_sql(
            canonicalise(typed(text), REGISTRY), REGISTRY)
        assert "::int" in old_where and "::int" in new_where, text


# ── Canonicalisation is a separate pass ──────────────────────────────────────

def test_the_parser_does_not_consult_the_registry():
    """Syntax parsing stays independent of the 311-field product registry, so
    a saved query survives the registry evolving."""
    parsed = typed("roe > 10")
    assert parsed.criteria[0].canonical is None
    assert not parsed.criteria[0].governed

    resolved = canonicalise(parsed, REGISTRY)
    assert resolved.criteria[0].canonical == "roe"
    assert resolved.criteria[0].governed


def test_canonicalisation_preserves_the_tree():
    resolved = canonicalise(typed("roe > 10 AND (roce > 10 OR roic > 20)"),
                            REGISTRY)
    assert isinstance(resolved.expression, AllOf)
    assert isinstance(resolved.expression.operands[1], AnyOf)


def test_an_alias_resolves_to_its_field_key_in_the_tree():
    parsed = typed("return on equity > 10")
    assert parsed.criteria[0].field == "roe", "the key, not the alias"


def test_a_governed_and_an_ungoverned_field_in_one_query():
    resolved = canonicalise(typed("roe > 10 AND sector = 'Materials'"),
                            REGISTRY)
    assert [c.field for c in resolved.governed_criteria] == ["roe"]
    assert [c.field for c in resolved.ungoverned_criteria] == ["sector"]
    assert resolved.requires_run_scope


def test_an_entirely_ungoverned_query_needs_no_run_scope():
    resolved = canonicalise(typed("sector = 'Materials'"), REGISTRY)
    assert not resolved.requires_run_scope


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
