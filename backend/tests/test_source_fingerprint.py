"""
What "current yearly output" actually means
===========================================
Two fixtures define it:

    change one financially consumed source value, leaving every timestamp and
    watermark untouched  ->  the fingerprint MUST change

    change a field yearly_compute does not consume  ->  the fingerprint MUST
    NOT change

Both are asserted here as properties of the projection, so they hold without a
database and cannot be satisfied by a lucky run. The first becomes "every
column yearly_compute selects is in the projection"; the second becomes "no
ingestion metadata is". Together they stop the design drifting back to a
timestamp-based freshness proxy later, which is precisely how this sort of
contract decays.

The runtime counterparts belong in the rehearsal, where real rows exist.

Run under pytest, or standalone:
    cd /opt/asx-screener/backend && ../asx-venv/bin/python tests/test_source_fingerprint.py
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from compute.engine.source_fingerprint import (  # noqa: E402
    FINGERPRINT_SCHEMA_VERSION, NULL_TOKEN, PROJECTIONS, SourceFingerprint,
    _table_digest_sql, _text, aggregate_digest,
)

BACKEND = Path(__file__).resolve().parents[1]
YEARLY = (BACKEND / "compute/engine/yearly_compute.py").read_text(encoding="utf-8")

#: Columns yearly_compute selects under an alias, mapped to the table the
#: alias refers to in fetch_financials' FROM/JOIN clauses.
ALIAS_TABLE = {
    "p": "financials.annual_pnl",
    "b": "financials.annual_balance_sheet",
    "cf": "financials.annual_cashflow",
}


def _consumed_columns(alias: str) -> set:
    """Every `alias.column` yearly_compute's financial query selects."""
    query = YEARLY[YEARLY.index("FROM financials.annual_pnl") - 3000:
                   YEARLY.index("ORDER BY p.fiscal_year ASC")]
    found = set(re.findall(rf"\b{alias}\.([a-z_]+)", query))
    # Join keys are structural, not values the computation reads.
    return found - {"asx_code", "fiscal_year"}


# ── Fixture 1: a consumed value must move the fingerprint ────────────────────

def test_every_consumed_financial_column_is_in_the_projection():
    """A column the computation reads but the fingerprint ignores is a value
    that can change while yearly_metrics is still certified current."""
    missing = {}
    for alias, table in ALIAS_TABLE.items():
        projected = set(PROJECTIONS[table][0])
        consumed = _consumed_columns(alias)
        assert consumed, f"no columns found for alias {alias!r}; this guard is inert"
        gap = consumed - projected
        if gap:
            missing[table] = sorted(gap)

    assert not missing, (
        f"these columns are consumed by yearly_compute but absent from the "
        f"fingerprint, so changing one would leave the yearly output "
        f"certified current: {missing}")


def test_every_table_yearly_compute_reads_is_fingerprinted():
    """P&L alone would certify stale output after a balance-sheet correction."""
    reads = set(re.findall(r"(?:FROM|JOIN)\s+((?:financials|staging_au|market)\.\w+)",
                           YEARLY))
    # yearly_metrics is this producer's OUTPUT, not one of its inputs.
    reads.discard("market.yearly_metrics")

    assert reads, "no input tables found; this guard is inert"
    assert reads <= set(PROJECTIONS), (
        f"yearly_compute reads {sorted(reads - set(PROJECTIONS))} but the "
        f"fingerprint does not cover it")


def test_the_two_daily_growing_tables_are_scoped_not_ignored():
    """market.daily_prices gains rows every day.

    Unscoped, the fingerprint changes nightly and DAILY_CANONICAL promotes
    itself to the full plan every time — reuse would never be valid. Absent,
    a historical price correction would pass unnoticed. Both are wrong; the
    projection must be bounded by the fiscal year end instead.
    """
    for table in ("market.daily_prices", "market.dividends"):
        where = PROJECTIONS[table][1]
        assert "max(p2.period_end_date)" in where, (
            f"{table} is fingerprinted unscoped; today's rows would change it "
            f"daily even though the computation never reads them")
        assert "<=" in where


# ── Fixture 2: irrelevant metadata must not move it ──────────────────────────

def test_ingestion_metadata_is_not_fingerprinted():
    """data_as_of was rejected on evidence and must not creep back in.

    Three of the four writers of financials.annual_* never set it, so a real
    change leaves it unchanged; the fourth sets NOW() on every load, so an
    unchanged source reads as changed. Including it would invalidate reuse
    when nothing financially meaningful had happened.
    """
    forbidden = {"data_as_of", "created_at", "updated_at", "loaded_at",
                 "ingested_at", "compute_version", "computed_at", "id"}
    for table, (columns, _where) in PROJECTIONS.items():
        leaked = forbidden & set(columns)
        assert not leaked, (
            f"{table} fingerprints {sorted(leaked)}, which yearly_compute "
            f"never reads; reuse would be refused for a metadata touch")


def test_no_projection_smuggles_a_timestamp_through_the_where_clause():
    for table, (_columns, where) in PROJECTIONS.items():
        assert "data_as_of" not in where, (
            f"{table}'s scope depends on data_as_of, which is not maintained "
            f"by every writer")


# ── Determinism ──────────────────────────────────────────────────────────────

def test_nulls_are_encoded_distinguishably():
    """"Cannot exist" and "happens to be absent" are different financial
    states, so NULL must not render as the empty string."""
    rendered = _text("revenue", is_numeric=True)
    assert NULL_TOKEN in rendered and NULL_TOKEN != ""
    assert "trim_scale" in rendered


def test_only_numeric_columns_are_scale_trimmed():
    """float8 rendered through numeric would lose precision — a fingerprint
    change that is not a source change."""
    assert "trim_scale" not in _text("ex_date", is_numeric=False)
    assert "trim_scale" in _text("revenue", is_numeric=True)


def test_the_digest_does_not_depend_on_row_order():
    sql = _table_digest_sql("financials.annual_pnl", ["asx_code", "revenue"])
    assert "ORDER BY h" in sql, (
        "rows are combined in whatever order PostgreSQL returned them, so the "
        "same data can fingerprint two different ways")


def test_an_empty_table_has_a_digest_rather_than_null():
    """string_agg over no rows returns NULL, and NULL != NULL — two empty
    sources would never compare equal, so reuse could never be granted."""
    assert "'empty'" in _table_digest_sql("staging_au.shares_stats",
                                          ["asx_code"])


def test_the_aggregate_is_order_independent_and_version_tagged():
    a = {"t1": {"n": 2, "digest": "x"}, "t2": {"n": 3, "digest": "y"}}
    b = {"t2": {"n": 3, "digest": "y"}, "t1": {"n": 2, "digest": "x"}}
    assert aggregate_digest(1, a) == aggregate_digest(1, b)
    assert aggregate_digest(1, a) != aggregate_digest(2, a), (
        "a projection change must not be able to masquerade as unchanged data")


def test_any_table_moving_moves_the_aggregate():
    base = {t: {"n": 1, "digest": "d"} for t in PROJECTIONS}
    for table in PROJECTIONS:
        moved = dict(base)
        moved[table] = {"n": 1, "digest": "CHANGED"}
        assert aggregate_digest(1, moved) != aggregate_digest(1, base), (
            f"a change in {table} does not reach the aggregate")


def test_row_count_alone_moves_the_aggregate():
    """A deletion and an insertion that hash the same way still changed the
    source."""
    a = {"t": {"n": 1, "digest": "d"}}
    b = {"t": {"n": 2, "digest": "d"}}
    assert aggregate_digest(1, a) != aggregate_digest(1, b)


# ── Comparison and reporting ─────────────────────────────────────────────────

def _fp(**digests):
    tables = {t: {"n": 1, "digest": digests.get(t, "same")} for t in PROJECTIONS}
    return SourceFingerprint(FINGERPRINT_SCHEMA_VERSION, tables,
                             aggregate_digest(FINGERPRINT_SCHEMA_VERSION, tables))


def test_differences_name_the_table_that_moved():
    """"The fingerprint changed" leaves the operator guessing whether a
    balance-sheet correction landed or a price backfill ran."""
    diffs = _fp(**{"financials.annual_balance_sheet": "moved"}).differences(_fp())
    assert len(diffs) == 1
    assert "annual_balance_sheet" in diffs[0]


def test_an_incomparable_schema_version_says_so_rather_than_differing_quietly():
    old = SourceFingerprint(0, {}, "x")
    diffs = _fp().differences(old)
    assert any("not comparable" in d for d in diffs)


def test_a_round_trip_through_json_preserves_the_aggregate():
    fp = _fp()
    assert SourceFingerprint.from_json(fp.to_json()).aggregate == fp.aggregate
    assert SourceFingerprint.from_json(None) is None


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
