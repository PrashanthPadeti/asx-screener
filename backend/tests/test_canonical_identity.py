"""
Canonical metric identity governs semantics; spelling is only storage
=====================================================================
The class fix for the ev_to_ebitda defect, rather than the fix for
ev_to_ebitda.

``screener.universe`` spells it ``ev_to_ebitda``. The governed set and the
applicability rules spell it ``ev_ebitda``. ``apply_applicability`` compared
raw column names, so it skipped the column entirely — a bank's EV/EBITDA
stayed in the frame, in its own factor score, and in every peer statistic.
The registry that exists to prevent exactly this was sitting one import away
and was not being used by the consumer.

    No governed consumer compares storage or API column names directly.
    Source names are canonicalised first; policy operates only on canonical
    metric identity.

These tests read the engines' actual column lists out of the source rather
than importing them, because those modules pull psycopg2 at scope. That
follows the convention test_multibagger_contract.py already established.

Run under pytest, or standalone:
    cd /opt/asx-screener/backend && ../asx-venv/bin/python tests/test_canonical_identity.py
"""

import ast
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from compute.engine.applicability import DOMAIN_RULES, Domain  # noqa: E402
from compute.engine.dividends import DividendSource, FeedHealth  # noqa: E402
from compute.engine.factor_applicability import apply_applicability  # noqa: E402
from compute.engine.metric_registry import (  # noqa: E402
    ALIASES,
    SENSITIVE,
    normalise,
)
from compute.engine.metric_states import (  # noqa: E402
    GOVERNED_METRICS,
    LATEST_MODEL_VERSION,
)

ENGINE = Path(__file__).resolve().parents[1] / "compute" / "engine"
GOVERNED = GOVERNED_METRICS[LATEST_MODEL_VERSION]

from datetime import date  # noqa: E402

GOOD_FEED = DividendSource(FeedHealth(latest_ex_date=date(2026, 9, 5),
                                      as_of=date(2026, 9, 10)))


def _literal(path: Path, name: str):
    """Pull a module-level literal out of source without importing it."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        # FACTOR_SIGNALS is an annotated assignment, which is AnnAssign rather
        # than Assign — checking only the latter silently found nothing.
        targets = ([node.target] if isinstance(node, ast.AnnAssign)
                   else node.targets if isinstance(node, ast.Assign) else [])
        for target in targets:
            if isinstance(target, ast.Name) and target.id == name:
                return ast.literal_eval(node.value)
    raise AssertionError(f"{name} not found in {path.name}")


# ── Aliases round-trip ────────────────────────────────────────────────────────

def test_every_alias_resolves_to_a_canonical_name():
    for alias, target in ALIASES.items():
        assert normalise(alias) == normalise(target), alias
        assert normalise(target) == target, \
            f"{target} is an alias target and must itself be canonical"


def test_no_governed_metric_is_itself_an_alias():
    """A governed name that is really an alias would be checked under one
    spelling and stored under another."""
    aliased = sorted(m for m in GOVERNED if m in ALIASES)
    assert not aliased, f"governed but aliased: {aliased}"


def test_every_alias_of_a_governed_metric_is_still_governed_when_resolved():
    for alias, target in ALIASES.items():
        if normalise(target) in GOVERNED:
            assert normalise(alias) in GOVERNED, \
                f"{alias} resolves outside the governed set"


def test_sensitive_metrics_are_canonical():
    for metric in SENSITIVE:
        assert normalise(metric) == metric, f"{metric} is not canonical"


def test_domain_rules_are_keyed_canonically():
    for metric in DOMAIN_RULES:
        assert normalise(metric) == metric, f"{metric} is not canonical"


# ── The physical schema the engines actually read ─────────────────────────────

def universe_columns() -> set[str]:
    """Every screener.universe column the two factor engines select."""
    signals = _literal(ENGINE / "composite_score.py", "FACTOR_SIGNALS")
    extra = _literal(ENGINE / "composite_score.py", "MB_EXTRA_COLS")
    sector = _literal(ENGINE / "sector_benchmarks.py", "COLS")
    cols = {c for sigs in signals.values() for c, _ in sigs}
    return cols | set(extra) | set(sector)


def test_the_engines_really_do_use_a_non_canonical_spelling():
    """Guards the guard: if this ever stops being true the alias tests below
    are vacuous and should be re-examined rather than quietly passing."""
    cols = universe_columns()
    mismatched = {c for c in cols if normalise(c) != c}
    assert "ev_to_ebitda" in mismatched, \
        "the known mismatch is gone — verify the alias tests still bite"


def test_every_storage_column_that_maps_into_the_governed_set_is_reachable():
    """The generalised ev_to_ebitda check.

    For each column the engines select, if its canonical form is governed then
    a frame carrying that column must actually be assessed under it. Comparing
    raw names would silently skip any column whose spelling differs.
    """
    cols = sorted(universe_columns())
    relevant = [c for c in cols if normalise(c) in GOVERNED]
    assert relevant, "no governed columns found — the extraction is wrong"

    base = {"asx_code": "CBA", "sector": "Financials", "industry": "Banks",
            "is_reit": False, "is_miner": False, "revenue_ttm": 2.7e10}
    row = dict(base, **{c: 1.0 for c in relevant})
    masked = apply_applicability(pd.DataFrame([row]), GOOD_FEED)

    assessed = set(masked.assessments["CBA"])
    for col in relevant:
        assert normalise(col) in assessed, (
            f"column {col!r} maps to governed metric {normalise(col)!r} but "
            f"was never assessed — policy compared spelling, not identity")


def test_a_bank_ev_ebitda_is_masked_under_the_storage_spelling():
    """The specific regression, kept alongside the general rule."""
    row = {"asx_code": "CBA", "sector": "Financials", "industry": "Banks",
           "is_reit": False, "is_miner": False, "revenue_ttm": 2.7e10,
           "ev_to_ebitda": 12.0}
    masked = apply_applicability(pd.DataFrame([row]), GOOD_FEED)

    assert pd.isna(masked.frame.iloc[0]["ev_to_ebitda"])
    assert "ev_ebitda" in masked.assessments["CBA"]


def test_the_assessment_is_keyed_canonically_not_by_column():
    """Consumers look up the canonical name; the frame keeps its own."""
    row = {"asx_code": "IND", "sector": "Industrials", "industry": "Machinery",
           "is_reit": False, "is_miner": False, "revenue_ttm": 1e9,
           "ev_to_ebitda": 8.0}
    masked = apply_applicability(pd.DataFrame([row]), GOOD_FEED)

    assert "ev_ebitda" in masked.assessments["IND"]
    assert "ev_to_ebitda" not in masked.assessments["IND"]
    assert masked.frame.iloc[0]["ev_to_ebitda"] == 8.0


# ── Sector benchmarks name governed metrics canonically ───────────────────────

def test_governed_benchmark_metrics_are_canonical_and_governed():
    metrics = _literal(ENGINE / "sector_benchmarks.py",
                       "GOVERNED_BENCHMARK_METRICS")
    for metric in metrics:
        assert normalise(metric) == metric, \
            f"{metric} is a storage spelling, not a canonical identity"
        assert metric in GOVERNED, f"{metric} is benchmarked but not governed"


def test_the_benchmark_list_uses_ev_ebitda_not_the_column_spelling():
    metrics = _literal(ENGINE / "sector_benchmarks.py",
                       "GOVERNED_BENCHMARK_METRICS")
    assert "ev_ebitda" in metrics and "ev_to_ebitda" not in metrics


# ── Same-run consistency is executable, not documentary ───────────────────────

def test_artefacts_from_different_runs_cannot_be_shown_together():
    from compute.engine.metric_states import RunMismatch, assert_same_run

    assert_same_run(company=4711, sector_benchmark=4711)   # fine

    try:
        assert_same_run(company=4711, sector_benchmark=4712)
    except RunMismatch as e:
        assert "4711" in str(e) and "4712" in str(e)
    else:
        raise AssertionError("a mismatch must fail closed, never 'use newest'")


def test_an_unattributed_artefact_cannot_join_an_attributed_one():
    from compute.engine.metric_states import RunMismatch, assert_same_run

    try:
        assert_same_run(company=4711, sector_benchmark=None)
    except RunMismatch as e:
        assert "no run attribution" in str(e)
    else:
        raise AssertionError("a legacy row must not be shown beside a new one")


def test_two_unattributed_artefacts_are_left_alone():
    """Legacy beside legacy is the pre-existing state, not a new violation."""
    from compute.engine.metric_states import assert_same_run
    assert_same_run(company=None, sector_benchmark=None)


# ── The legacy sector-wide count is never a governed denominator ──────────────

def test_a_governed_benchmark_never_takes_its_count_from_stock_count():
    """market.sector_benchmarks.stock_count stays for ungoverned readers, but
    it is one number for the whole sector: a Financials row saying n=142 says
    nothing about how many could carry a debt_to_equity observation (none).
    A governed count comes from benchmark_states or it is wrong.
    """
    from compute.engine.applicability import Assessment, Applicability, assess
    from compute.engine.peer_benchmarks import benchmark

    stock_count = 142                       # plausible, and the wrong answer
    banks = [assess("debt_to_equity", 4.6, Domain.BANK) for _ in range(stock_count)]
    b = benchmark("debt_to_equity", banks)

    assert b.n_total_peers == stock_count
    assert b.n_applicable_peers == 0, "none of the 142 can carry this metric"
    assert b.n_valid_peers == 0
    assert b.coverage_pct == 0.0
    assert b.median is None


def test_a_successful_benchmark_carries_no_synthetic_ok_reason():
    """reason_code stays diagnostic rather than becoming a second state enum."""
    from compute.engine.applicability import Assessment, Applicability
    from compute.engine.peer_benchmarks import benchmark

    peers = [Assessment("roe", Applicability.APPLICABLE, 0.1 + i * 0.01, "",
                        Domain.GENERAL_CORPORATE) for i in range(8)]
    b = benchmark("roe", peers)

    assert b.ok and b.reason_code is None and b.reason == ""


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
