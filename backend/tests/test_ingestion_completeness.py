"""
The upstream proof hole, and the three things that close it
===========================================================
Found by the 30 Sep 2026 scratch rehearsal (`docs/canonical_rehearsal_record.md`).

Every canonical stage proved it covered its own source population, truthfully,
and a FULL run finalised with zero violations -- while one company's weekly
refresh had been silently discarded upstream. The chain:

    files → staging loses rows (the loader rolled back a whole 50-file batch
    on one bad file, and still counted those files as loaded)
        → downstream stages derive `expected` from that shrunken staging
            → every set-equality proof passes
                → publication finalises on an incomplete refresh

Containment held -- the unattributed row was never served -- but a failed
refresh had disappeared from the proof chain, which is the one thing the
population-proof architecture exists to prevent.

These tests exist to make the new failures BITE. A guard that cannot be made
to fail has not been shown to work, so each one here induces the exact
condition it claims to catch.

Run under pytest, or standalone:
    cd backend && ../asx-venv/bin/python tests/test_ingestion_completeness.py
"""

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from compute.engine.run_stages import StageResult  # noqa: E402


# ── B3: zero coverage must justify itself ────────────────────────────────────

def test_two_empty_sets_are_not_a_proof():
    """The exact record run 3 produced: expected 0, written 0, hashes equal.

    Set equality holds because both sides hash the empty string. Before this
    rule that was `success`.
    """
    r = StageResult("transform_prices", frozenset(), frozenset())
    assert r.vacuous
    assert r.ok is False
    assert r.status == "failed"


def test_the_vacuous_failure_says_what_is_wrong():
    """`0 missing; 0 extra` would read as a clean run to an operator, which is
    how this survived unnoticed."""
    r = StageResult("transform_prices", frozenset(), frozenset())
    assert "NO_WORK_EXPECTED" in r.summary()


def test_zero_coverage_passes_when_the_emptiness_is_proved():
    """The escape is a reason, not a flag -- and it must be independently
    established by the caller, not derived from the stage's own output."""
    r = StageResult("transform_prices", frozenset(), frozenset(),
                    no_work_expected="staging_au.eod_prices is empty outright")
    assert r.vacuous is False
    assert r.ok is True
    assert r.payload()["no_work_expected"]


def test_the_new_rule_does_not_fail_ordinary_stages():
    """The mutation control. Without this, a rule that failed everything would
    pass every test above."""
    keys = frozenset({"BHP", "CBA", "CSL"})
    assert StageResult("yearly_compute", keys, keys).ok is True


def test_a_real_shortfall_still_fails_for_its_own_reason():
    r = StageResult("yearly_compute", frozenset({"BHP", "CBA"}),
                    frozenset({"BHP"}))
    assert r.ok is False
    assert r.missing == frozenset({"CBA"})
    assert "expected but not written" in r.summary()


def test_no_work_expected_cannot_excuse_a_real_shortfall():
    """A reason for emptiness must not become a reason for incompleteness."""
    r = StageResult("yearly_compute", frozenset({"BHP", "CBA"}),
                    frozenset({"BHP"}),
                    no_work_expected="nothing to do")
    assert r.ok is False


# ── B1: a foreign-currency file is an explained absence, not a failure ───────

def test_an_unstorable_figure_is_refused_before_anything_is_written():
    """ATM (Aneka Tambang) states revenue of 88,851,053,565,000.00 IDR, beyond
    NUMERIC(20,4). Ten of its snapshots failed on 30 Sep 2026.

    A foreign currency is NOT the disqualifier -- that is recorded and
    labelled, because refusing it would have excluded BHP. What is refused is
    a magnitude with no representation to label, keyed on the magnitude
    itself rather than on a currency list that would rot.

    The ordering is the property: the refusal must come BEFORE the first
    write, or a rejected file still leaves a partial row behind. Proven from
    the source rather than by importing, because the module needs a database
    driver to import and this property does not need a database to be true.
    """
    import ast
    src = (BACKEND / "scripts/eodhd/v2/load_to_staging_fundamentals.py").read_text(
        encoding="utf-8")
    tree = ast.parse(src)
    load_file = next(n for n in ast.walk(tree)
                     if isinstance(n, ast.FunctionDef) and n.name == "load_file")

    raise_line = next(
        n.lineno for n in ast.walk(load_file)
        if isinstance(n, ast.Raise)
        and getattr(getattr(n.exc, "func", None), "id", "") == "Unrepresentable")
    first_write = min(
        n.lineno for n in ast.walk(load_file)
        if isinstance(n, ast.Call)
        and getattr(n.func, "id", "").startswith("upsert_"))

    assert raise_line < first_write, (
        f"Unrepresentable raised at line {raise_line}, after the first write "
        f"at line {first_write}: a rejected file would leave a partial row")


def test_the_currency_guard_reads_the_statements_not_the_listing():
    """ATM.AU states two currencies and only one is about the numbers:

        General.CurrencyCode             AUD   the LISTING currency
        Income_Statement currency_symbol IDR   the STATEMENTS

    The first version of this guard checked only General, so ATM passed
    straight through and overflowed on write. Measured 30 Sep 2026.
    """
    src = (BACKEND / "scripts/eodhd/v2/load_to_staging_fundamentals.py").read_text(
        encoding="utf-8")
    assert "currency_symbol" in src, (
        "the guard must read the per-statement currency, not only "
        "General.CurrencyCode")
    for section in ("Income_Statement", "Balance_Sheet", "Cash_Flow"):
        assert section in src, f"{section}'s stated currency is unchecked"


def test_the_loader_no_longer_rolls_back_the_whole_connection():
    """The amplifier, not the trigger.

    `conn.rollback()` is per-connection: one bad file discarded every row
    staged since the last commit -- up to 49 other companies -- and those
    files had already incremented the `done` counter. ATH and ATHDA were
    alphabetically adjacent to ATM, shared its batches, and lost everything.

    Asserted against the file-processing loop specifically, because
    `conn.rollback()` remains legitimate elsewhere.
    """
    import ast
    src = (BACKEND / "scripts/eodhd/v2/load_to_staging_fundamentals.py").read_text(
        encoding="utf-8")
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "load_files")
    loop = next(n for n in ast.walk(fn) if isinstance(n, ast.For))
    calls = [n for n in ast.walk(loop)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
             and n.func.attr == "rollback"]
    assert not calls, "per-connection rollback is back inside the per-file loop"
    assert "SAVEPOINT one_file" in ast.dump(loop)


# ── B2: files → staging proves its own population ───────────────────────────

def test_the_expected_population_does_not_come_from_staging():
    """The whole point. An expected set drawn from the loader's own output
    proves only that the loop agrees with itself -- which is exactly how a
    shrunken staging propagated into every downstream stage's `expected`.
    """
    import ast
    src = (BACKEND / "scripts/eodhd/v2/load_to_staging_fundamentals.py").read_text(
        encoding="utf-8")
    fn = next(n for n in ast.walk(ast.parse(src))
              if isinstance(n, ast.FunctionDef) and n.name == "load_files")
    loop = next(n for n in ast.walk(fn) if isinstance(n, ast.For))

    # `expected` is fed from the iterated path and from the file's own stated
    # periods -- never from a query against staging.
    adds = [n for n in ast.walk(loop)
            if isinstance(n, ast.Call)
            and getattr(n.func, "attr", "") == "add"
            and getattr(getattr(n.func, "value", None), "id", "") == "expected"]
    assert adds, "expected must be populated from the manifest inside the loop"
    assert "staging" not in ast.dump(loop).lower()


def test_the_proof_is_keyed_finer_than_the_file():
    """A fundamentals file holds many periods, and the loader drops any period
    whose record is not a dict or whose date will not parse.

    A file-grain proof passes while periods vanish inside the file, so the
    expected set must carry the source-stated period keys too.
    """
    import ast
    src = (BACKEND / "scripts/eodhd/v2/load_to_staging_fundamentals.py").read_text(
        encoding="utf-8")
    tree = ast.parse(src)
    load_file = next(n for n in ast.walk(tree)
                     if isinstance(n, ast.FunctionDef) and n.name == "load_file")
    account = next(n for n in ast.walk(load_file)
                   if isinstance(n, ast.FunctionDef) and n.name == "account")
    body = ast.dump(account)
    assert "expected" in body and "written" in body
    # Both sides of the within-file comparison must come from one predicate,
    # or the proof can drift away from the admission it claims to measure.
    assert "period_key" in body

    admissions = [n for n in ast.walk(load_file)
                  if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "period_key"]
    assert admissions, "account() must use the same predicate the upserts use"


def test_an_incomplete_load_exits_non_zero():
    """A shrunken staging must stop the pipeline rather than quietly hand a
    smaller domain to stages that will then prove themselves against it.

    Step 1 is dispatched with `run()` rather than `run_optional()`, so a
    non-zero exit fails the weekly pipeline.
    """
    import ast
    src = (BACKEND / "scripts/eodhd/v2/load_to_staging_fundamentals.py").read_text(
        encoding="utf-8")
    main = next(n for n in ast.walk(ast.parse(src))
                if isinstance(n, ast.FunctionDef) and n.name == "main")
    exits = [n for n in ast.walk(main)
             if isinstance(n, ast.Call)
             and getattr(n.func, "attr", "") == "exit"
             and n.args and getattr(n.args[0], "value", None) == 1]
    assert exits, "an incomplete load must exit non-zero"

    weekly = (BACKEND / "scripts/eodhd/v2/jobs/weekly_pipeline.py").read_text(
        encoding="utf-8")
    step1 = next(line for line in weekly.splitlines()
                 if "Step 1: Load staging fundamentals" in line)
    assert "run_optional" not in step1


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
        except Exception as e:                                     # noqa: BLE001
            failures.append(name)
            print(f"  ERROR {name}  - {type(e).__name__}: {e}")
    print(f"\n{len(tests) - len(failures)}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
