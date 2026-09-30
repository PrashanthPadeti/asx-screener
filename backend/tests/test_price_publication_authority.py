"""
One publisher for market.daily_prices
=====================================
Rule 5 of `docs/canonical_orchestration.md`: a canonical output table has one
publication authority. For `market.daily_prices` that is `transform_prices`,
and nothing else.

How this was achieved is worth recording, because the first attempt was a
refactor and the right answer was a subtraction.

`backfill_yfinance_prices` wrote `market.daily_prices` directly from an
independent 09:00 UTC cron, thirty minutes into the daily pipeline's own
window. The planned fix moved it behind a staging table with a declared
merge precedence — a second source, a new table, a `DISTINCT ON`, a
migration. Then the evidence was measured:

    eodhd    6,892,731 rows   2,394 codes   latest 2026-09-23
    yahoo        1,849 rows     484 codes   latest 2026-09-04

    companies served ONLY by yahoo: 8, every one 35-49 days stale

Eight instruments — seven ETFs and a deferred-settlement line — sitting in
the serving population with prices up to seven weeks old, presented exactly
like same-day ones. Not thin coverage: wrong coverage. The selector only ever
targeted codes with `price_date IS NULL`, so once an instrument had any price
it was never refreshed again, by design.

So the job was deleted. The decision, frozen 30 Sep 2026:

    ASXScreener will not manufacture ETF coverage from a stale yfinance
    backfill. Instruments without a sufficiently current supported price
    source are excluded from the serving population. ETF pricing, if
    commercially required later, gets a proper source and freshness contract.

Absence is the honest customer state. These tests hold that line.

Run under pytest, or standalone:
    cd /opt/asx-screener/backend && ../asx-venv/bin/python tests/test_price_publication_authority.py
"""

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from compute.engine import canonical_boundary as cb  # noqa: E402

PUBLISHER = "scripts/eodhd/v2/transforms/transform_prices.py"
OUTPUT = "market.daily_prices"
PRIMARY = "staging_au.eod_prices"


# ── One publication authority ────────────────────────────────────────────────

def test_only_the_plan_stage_publishes_daily_prices():
    """The claim Rule 5 makes, and it is about the TABLE rather than the
    schedule: a script in the tree with an INSERT into a canonical output is
    one manual invocation away from being a second authority."""
    plan = {p.relative_to(cb.BACKEND).as_posix()
            for p in cb.plan_scripts().values()}
    writers = cb.output_writers()[OUTPUT]
    assert writers & plan == {PUBLISHER}, sorted(writers & plan)
    undeclared = writers - plan - set(cb.QUARANTINED_WRITERS)
    assert not undeclared, f"undeclared writers of {OUTPUT}: {sorted(undeclared)}"


def test_every_canonical_output_has_exactly_one_publisher():
    """Generalised, so a new output cannot arrive with two writers unnoticed.

    screener.universe legitimately has two: the provisional rebuild and the
    canonical commit, which are the designed pair rather than competing
    authorities.
    """
    plan = {p.relative_to(cb.BACKEND).as_posix()
            for p in cb.plan_scripts().values()}
    expected_pairs = {"screener.universe"}
    for table, writers in sorted(cb.output_writers().items()):
        authority = writers & plan
        limit = 2 if table in expected_pairs else 1
        assert 1 <= len(authority) <= limit, (
            f"{table} has publishers {sorted(authority)}")


# ── The deletion is complete ─────────────────────────────────────────────────

def test_the_yfinance_backfill_no_longer_exists():
    """Deleted, not disabled. A disabled script is one `python` away from
    being a second publication authority again."""
    assert not (BACKEND / "scripts/eodhd/v2/backfill_yfinance_prices.py").exists()


def test_no_yfinance_staging_table_remains():
    """No table, no merge, no precedence rule. The machinery went with the
    job it existed to serve."""
    assert not (BACKEND / "migrations/add_yfinance_price_staging.sql").exists()
    inputs, outputs = cb.canonical_tables()
    assert "staging_au.yfinance_prices" not in inputs | outputs


def test_the_transform_reads_one_source():
    """A single feed needs no precedence rule, and an unused one would be a
    rule nobody maintains."""
    touched = cb.tables_touched(BACKEND / PUBLISHER)
    assert "r" in touched.get(PRIMARY, set())
    assert "staging_au.yfinance_prices" not in touched


def test_nothing_is_classified_or_quarantined_for_yfinance():
    """The classifier carried an entry for the backfill while its fate was
    open. With the job gone the entry must go too, or the exceptional state
    outlives the exception."""
    for registry in (cb.CLASSIFICATIONS, cb.QUARANTINED_WRITERS,
                     cb.ACCEPTED, cb.SUFFIX_WRITE_REASONS):
        assert not any("yfinance" in key for key in registry), sorted(registry)


def test_the_daily_wrapper_does_not_acquire_yfinance_prices():
    source = cb._executable_source(
        BACKEND / "scripts/eodhd/v2/jobs/daily_pipeline.py")
    assert "yfinance" not in source


def test_the_generator_no_longer_declares_the_yfinance_cron():
    """Desired state says the job does not exist.

    Its runtime cron entry still does until an operator removes it, so
    launch-authority reconciliation will report UNDECLARED. That is the drift
    being visible, which is what the two-artifact model is for — not a bug to
    paper over.
    """
    generator = (BACKEND / "scripts/eodhd/v2/jobs/setup_cron.sh").read_text(
        encoding="utf-8")
    declarations = [line for line in generator.splitlines()
                    if line.strip().startswith(("YFINANCE", "BACKFILL"))
                    and "_CMD=" in line]
    assert not declarations, declarations


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
