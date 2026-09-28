"""
One publisher for market.daily_prices, and a declared precedence
================================================================
Rule 5 of `docs/canonical_orchestration.md`. `backfill_yfinance_prices`
acquires into `staging_au.yfinance_prices`; `transform_prices` publishes.

What these tests can and cannot establish
-----------------------------------------
Everything here is static or fixture-based, and says so. The proofs that need
a database — backfilled rows surviving until consumed, a three-day backfill
producing the same result as the old direct write, end-to-end idempotence —
are runtime proofs and belong in a scratch exercise, not here. Writing a
test that *looks* like it proves them without touching data would be worse
than not having one.

Run under pytest, or standalone:
    cd /opt/asx-screener/backend && ../asx-venv/bin/python tests/test_price_publication_authority.py
"""

import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from compute.engine import canonical_boundary as cb  # noqa: E402

TRANSFORM = BACKEND / "scripts/eodhd/v2/transforms/transform_prices.py"
BACKFILL = BACKEND / "scripts/eodhd/v2/backfill_yfinance_prices.py"
MIGRATION = BACKEND / "migrations/add_yfinance_price_staging.sql"

PRIMARY = "staging_au.eod_prices"
FALLBACK = "staging_au.yfinance_prices"
OUTPUT = "market.daily_prices"


# ── One publication authority ────────────────────────────────────────────────

def test_only_the_plan_stage_publishes_daily_prices():
    """The claim Rule 5 actually makes, and it is about the TABLE rather than
    about the schedule: a script in the tree with an INSERT into a canonical
    output is one manual invocation away from being a second authority."""
    plan = {p.relative_to(cb.BACKEND).as_posix() for p in cb.plan_scripts().values()}
    writers = cb.output_writers()[OUTPUT]
    authority = writers & plan
    assert authority == {"scripts/eodhd/v2/transforms/transform_prices.py"}, (
        f"publishers of {OUTPUT}: {sorted(authority)}")
    undeclared = writers - plan - set(cb.QUARANTINED_WRITERS)
    assert not undeclared, f"undeclared writers of {OUTPUT}: {sorted(undeclared)}"


def test_the_backfill_no_longer_writes_the_canonical_output():
    """The specific change. If this regresses, the 09:00 cron is publishing
    again — thirty minutes into the daily pipeline's own window."""
    touched = cb.tables_touched(BACKFILL)
    assert "w" not in touched.get(OUTPUT, set()), (
        f"the backfill writes {OUTPUT} again: {touched.get(OUTPUT)}")
    assert "w" in touched.get(FALLBACK, set()), (
        "the backfill does not write its staging table")


def test_the_backfill_is_now_legally_classified():
    """It fit none of the three classes while it published. Fitting one is the
    evidence the architecture changed rather than the taxonomy."""
    key = "scripts/eodhd/v2/backfill_yfinance_prices.py"
    assert cb.CLASSIFICATIONS.get(key) == cb.PRE_INGESTION
    assert not cb.check_unit(key, BACKFILL), cb.check_unit(key, BACKFILL)


def test_the_yfinance_staging_table_is_a_canonical_input():
    """Derived, not declared: it becomes an input because transform_prices
    reads it. If that read disappeared, so would this."""
    inputs, outputs = cb.canonical_tables()
    assert FALLBACK in inputs, sorted(inputs)
    assert FALLBACK not in outputs


def test_no_exemption_is_left_over():
    """The backfill's entry in ACCEPTED described an unresolved question. The
    question is resolved, so the entry must be gone — a resolved case left as
    an exemption makes the exceptional state permanent."""
    assert "scripts/eodhd/v2/backfill_yfinance_prices.py" not in cb.ACCEPTED


# ── The merge, and its precedence ────────────────────────────────────────────

def _transform_source() -> str:
    return cb._executable_source(TRANSFORM)


def test_the_transform_reads_both_feeds():
    touched = cb.tables_touched(TRANSFORM)
    assert "r" in touched.get(PRIMARY, set())
    assert "r" in touched.get(FALLBACK, set())


def _declaration(name: str):
    """A module-level literal, read by AST rather than by import.

    transform_prices needs psycopg2, and a test that SKIPS wherever the driver
    is absent would leave the precedence rule unchecked in exactly the
    environments where it is cheapest to check. The declarations are literals;
    nothing needs to be executed to read them.
    """
    import ast
    tree = ast.parse(TRANSFORM.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == name:
            return ast.literal_eval(node.value)
    raise AssertionError(f"{name} not found in transform_prices")


def test_precedence_is_declared_and_eodhd_wins():
    """A literal precedence column resolved by DISTINCT ON, so the rule is in
    the query rather than in the order rows happen to arrive."""
    sources = _declaration("SOURCES")
    assert sources[0][0] == PRIMARY and sources[0][2] == 1, sources
    assert sources[1][0] == FALLBACK and sources[1][2] == 2, sources

    sql = _declaration("MERGED_SOURCE_SQL")
    assert "DISTINCT ON (asx_code, date)" in sql
    assert "ORDER BY asx_code, date, precedence" in sql


def test_precedence_does_not_depend_on_time_or_arrival():
    """An arrival-time rule means a slow primary feed silently loses to a fast
    fallback, and which feed won would depend on the day rather than on the
    decision."""
    sql = _declaration("MERGED_SOURCE_SQL")
    ordering = sql[sql.index("ORDER BY asx_code"):]
    for forbidden in ("fetched_at", "loaded_at", "ctid", "NOW()"):
        assert forbidden not in ordering, (
            f"precedence depends on {forbidden!r}")


def test_the_winning_feed_is_recorded_per_row():
    """data_source used to be the literal 'eodhd' for every row. With two
    feeds that would be a lie on the rows yfinance supplied."""
    source = _transform_source()
    assert '"eodhd",                 # data_source' not in source, (
        "data_source is still hardcoded")
    assert "r[8]" in source, "the source column is not carried into the insert"


# ── The proof follows the writer ─────────────────────────────────────────────

def test_the_expected_population_is_the_merged_source():
    """Derived from the primary feed alone, every yfinance-only code would be
    written-but-not-expected — a correct transform reported as a failure."""
    source = _transform_source()
    digest_call = source[source.index("merged_source ="):]
    digest_call = digest_call[:digest_call.index("expected =")]
    assert "MERGED_SOURCE_SQL" in digest_call, (
        "the expected population is not derived from the merged source")


def test_the_full_run_precondition_counts_both_feeds():
    """Either feed may legitimately be empty — the yfinance table is empty
    whenever no backfill was needed — so refusing on one alone would block
    every ordinary full run."""
    source = _transform_source()
    block = source[source.index("REFUSING full run") - 600:
                   source.index("REFUSING full run")]
    assert PRIMARY in block and FALLBACK in block, block[-300:]


# ── Idempotence, as far as static evidence goes ──────────────────────────────

def test_the_backfill_upserts_on_the_natural_key():
    """A re-run of the same window must update the same rows rather than
    accumulate duplicates. That is a property of the key, so it is asserted
    against the key."""
    source = cb._executable_source(BACKFILL)
    assert "ON CONFLICT (asx_code, date) DO UPDATE" in source, source[:0] or (
        "the backfill does not upsert on (asx_code, date)")


def test_the_staging_table_has_that_key():
    ddl = MIGRATION.read_text(encoding="utf-8")
    assert "PRIMARY KEY (asx_code, date)" in ddl


def test_staging_types_match_the_primary_feed():
    """transform_prices passes these values straight through to
    market.daily_prices. A type change here is a precision change there, and
    this codebase has already lost a day to Decimal-versus-float differences
    that only surfaced in a full-population read-back."""
    ddl = MIGRATION.read_text(encoding="utf-8")
    for column in ("open", "high", "low", "close", "adjusted_close"):
        assert re.search(rf"\b{column}\s+NUMERIC\(12,4\)", ddl), column
    assert re.search(r"\bvolume\s+BIGINT", ddl)
    assert re.search(r"\basx_code\s+VARCHAR\(10\)", ddl)


def test_acquisition_failure_cannot_touch_the_published_table():
    """Structural, and the strongest form available without a database: the
    acquisition process has no statement that writes the output at all."""
    touched = cb.tables_touched(BACKFILL)
    assert "w" not in touched.get(OUTPUT, set())
    assert "w" not in touched.get(PRIMARY, set()), (
        "the backfill writes the primary feed's staging table, which its "
        "loader truncates — the rows would not survive to be consumed")


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
