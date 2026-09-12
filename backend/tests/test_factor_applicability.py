"""
Applying applicability to the factor frame — ordering is the substance
======================================================================
The masking itself is easy. The property worth testing is *when* it happens:

    Mask before ranking, never after.

pct_rank ranks a whole column, so an out-of-domain value left in place does
not only mislabel its own row — it moves the percentile of every other company
in the market. Suppressing after the ranking would show CBA an NM for
debt_to_equity while its 4.6x had already pushed every industrial company's
leverage percentile down. That is the original defect surviving in a form
nobody would think to look for, so it gets a test that measures the other
companies rather than the bank.

Run under pytest, or standalone:
    cd /opt/asx-screener/backend && ../asx-venv/bin/python tests/test_factor_applicability.py
"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from compute.engine.applicability import Cause, Domain  # noqa: E402
from compute.engine.dividends import DividendSource, FeedHealth  # noqa: E402
from compute.engine.factor_applicability import (  # noqa: E402
    INCOME_METRICS,
    apply_applicability,
    withhold_source_failed,
)

TODAY = date(2026, 9, 10)
BROKEN_FEED = DividendSource(FeedHealth(latest_ex_date=date(2026, 8, 3),
                                        as_of=TODAY, recent_rows=0))
GOOD_FEED = DividendSource(FeedHealth(latest_ex_date=date(2026, 9, 5),
                                      as_of=TODAY, recent_rows=180))


def universe() -> pd.DataFrame:
    """One bank and four industrials, with leverage spread across the range."""
    return pd.DataFrame([
        {"asx_code": "CBA", "sector": "Financials", "industry": "Banks",
         "is_reit": False, "is_miner": False, "revenue_ttm": 2.7e10,
         "debt_to_equity": 4.6, "altman_z_score": -0.15, "current_ratio": 0.1,
         "piotroski_f_score": 3.0, "roe": 0.1284, "grossed_up_yield": 0.0466},
        {"asx_code": "IND1", "sector": "Industrials", "industry": "Machinery",
         "is_reit": False, "is_miner": False, "revenue_ttm": 1e9,
         "debt_to_equity": 0.2, "altman_z_score": 4.0, "current_ratio": 2.0,
         "piotroski_f_score": 8.0, "roe": 0.22, "grossed_up_yield": 0.03},
        {"asx_code": "IND2", "sector": "Industrials", "industry": "Machinery",
         "is_reit": False, "is_miner": False, "revenue_ttm": 1e9,
         "debt_to_equity": 0.5, "altman_z_score": 3.0, "current_ratio": 1.5,
         "piotroski_f_score": 6.0, "roe": 0.15, "grossed_up_yield": 0.04},
        {"asx_code": "IND3", "sector": "Industrials", "industry": "Machinery",
         "is_reit": False, "is_miner": False, "revenue_ttm": 1e9,
         "debt_to_equity": 0.9, "altman_z_score": 2.0, "current_ratio": 1.2,
         "piotroski_f_score": 5.0, "roe": 0.11, "grossed_up_yield": 0.05},
        {"asx_code": "IND4", "sector": "Industrials", "industry": "Machinery",
         "is_reit": False, "is_miner": False, "revenue_ttm": 1e9,
         "debt_to_equity": 1.4, "altman_z_score": 1.5, "current_ratio": 1.0,
         "piotroski_f_score": 4.0, "roe": 0.08, "grossed_up_yield": 0.06},
    ])


def pct_rank(series: pd.Series, direction: int) -> pd.Series:
    """The real ranking function, copied so this test needs no psycopg2."""
    s = series if direction == 1 else -series
    return s.rank(method="average", pct=True, na_option="keep") * 100


# ── The ordering property ─────────────────────────────────────────────────────

def test_masking_happens_before_ranking_so_a_bank_does_not_move_the_market():
    """The test that measures the *other* companies, not the bank."""
    df = universe()

    # Wrong order: rank first, suppress after.
    ranked_first = pct_rank(df["debt_to_equity"], -1)

    # Right order: suppress first, then rank.
    masked = apply_applicability(df, GOOD_FEED)
    ranked_after_masking = pct_rank(masked.frame["debt_to_equity"], -1)

    idx = {c: i for i, c in enumerate(df["asx_code"])}
    before = {c: ranked_first[i] for c, i in idx.items()}
    after = {c: ranked_after_masking[i] for c, i in idx.items()}

    # CBA's 4.6x is the *worst* leverage in the frame, so it sits at the
    # bottom of the ranking and flatters everyone above it. Every industrial
    # reads as better-levered than it is, purely because a bank is beneath it.
    assert before["CBA"] == 20.0, "the bank is ranked, and ranked badly"
    assert pd.isna(after["CBA"]), "after masking it is not ranked at all"

    assert (before["IND2"], after["IND2"]) == (80.0, 75.0)
    assert (before["IND3"], after["IND3"]) == (60.0, 50.0)
    assert (before["IND4"], after["IND4"]) == (40.0, 25.0)

    for code in ("IND2", "IND3", "IND4"):
        assert before[code] > after[code], (
            f"{code} was inflated by the bank sitting below it; suppressing "
            f"after the ranking would have left that inflation in place")

    # IND1 is unchanged at 100 — it was already best. The distortion lives in
    # the middle of the distribution, which is exactly where it is hardest to
    # notice by eye and why this is asserted rather than assumed.
    assert before["IND1"] == after["IND1"] == 100.0


def test_the_bank_itself_is_removed_from_the_column():
    masked = apply_applicability(universe(), GOOD_FEED)
    cba = masked.frame[masked.frame["asx_code"] == "CBA"].iloc[0]

    for col in ("debt_to_equity", "altman_z_score", "current_ratio",
                "piotroski_f_score"):
        assert pd.isna(cba[col]), f"{col} still in the ranking population"


def test_a_valid_metric_for_a_bank_survives():
    masked = apply_applicability(universe(), GOOD_FEED)
    cba = masked.frame[masked.frame["asx_code"] == "CBA"].iloc[0]
    assert cba["roe"] == 0.1284, "suppression is per metric, not per company"


def test_the_frame_keeps_its_shape():
    """A company with a suppressed metric is still a company."""
    df = universe()
    assert len(apply_applicability(df, GOOD_FEED).frame) == len(df)


# ── States are collected for persistence ──────────────────────────────────────

def test_states_are_recorded_per_company_with_causes():
    masked = apply_applicability(universe(), GOOD_FEED)

    assert "CBA" in masked.states
    assert masked.states["CBA"]["debt_to_equity"]["cause"] == "domain"
    assert "roe" not in masked.states["CBA"], "applicable metrics stay out"


def test_a_clean_company_carries_only_our_own_defect():
    """There is no longer a company with an empty payload, and the reason is
    deliberate: piotroski_f_score is unavailable for everyone until it is
    computed faithfully, so an otherwise clean industrial carries exactly one
    entry — and it names a fault in our implementation, not in its data."""
    masked = apply_applicability(universe(), GOOD_FEED)
    entries = masked.states.get("IND1") or {}

    assert set(entries) == {"piotroski_f_score"}, \
        f"expected only the unsupported computation, got {sorted(entries)}"
    assert entries["piotroski_f_score"]["cause"] == "computation_unsupported"


def test_the_tally_reports_domains_and_states():
    masked = apply_applicability(universe(), GOOD_FEED)
    assert masked.tally["domain:bank"] == 1
    assert masked.tally["domain:general_corporate"] == 4
    assert masked.tally["state:not_meaningful"] > 0


# ── Source failure is not an applicability decision ───────────────────────────

def test_a_broken_feed_marks_income_as_source_unhealthy_for_everyone():
    masked = apply_applicability(universe(), BROKEN_FEED)

    assert masked.any_source_failed
    assert masked.source_failed.all(), "the feed is broken for the whole exchange"
    for code in ("CBA", "IND1"):
        assert masked.states[code]["grossed_up_yield"]["cause"] == "source_unhealthy"


def test_a_healthy_feed_leaves_income_alone():
    masked = apply_applicability(universe(), GOOD_FEED)
    assert not masked.any_source_failed
    ind1 = masked.frame[masked.frame["asx_code"] == "IND1"].iloc[0]
    assert ind1["grossed_up_yield"] == 0.03


def test_income_metrics_are_nan_when_the_feed_is_broken():
    masked = apply_applicability(universe(), BROKEN_FEED)
    present = [c for c in INCOME_METRICS if c in masked.frame.columns]
    assert present, "the fixture must carry at least one income metric"
    for col in present:
        assert masked.frame[col].isna().all()


# ── The composite refuses to reweight around a source failure ─────────────────

def scores(n=5) -> pd.DataFrame:
    return pd.DataFrame({
        "value_score": [60.0] * n, "quality_score": [70.0] * n,
        "growth_score": [55.0] * n, "momentum_score": [65.0] * n,
        "income_score": [np.nan] * n,
    })


def test_a_source_failure_withholds_the_composite_entirely():
    df = scores()
    composite = df.mean(axis=1, skipna=True)
    withheld = withhold_source_failed(composite, pd.Series([True] * 5))
    assert withheld.isna().all(), \
        "four factors under a five-factor name is a different model"


def test_an_applicability_driven_absence_still_produces_a_composite():
    df = scores()
    composite = df.mean(axis=1, skipna=True)
    kept = withhold_source_failed(composite, pd.Series([False] * 5))
    assert kept.notna().all(), "the legitimate case must keep working"


def test_withholding_is_per_row():
    df = scores()
    composite = df.mean(axis=1, skipna=True)
    out = withhold_source_failed(composite,
                                 pd.Series([True, False, True, False, False]))
    assert list(out.isna()) == [True, False, True, False, False]


def test_no_mask_means_no_change():
    composite = pd.Series([50.0, 60.0])
    assert withhold_source_failed(composite, None).equals(composite)


# ── The rule is about cross-sectional statistics, not about ranking ───────────

def test_margin_expansion_inherits_the_domain_of_the_margin():
    """The multibagger score ranks these cross-sectionally, so an unmasked
    bank would move every industrial company's capital-efficiency percentile
    exactly the way its leverage moved theirs."""
    df = universe()
    df["gross_margin_expansion"] = [0.05, 0.01, 0.02, 0.03, 0.04]
    df["operating_margin_expansion"] = [0.06, 0.01, 0.02, 0.03, 0.04]

    masked = apply_applicability(df, GOOD_FEED)
    cba = masked.frame[masked.frame["asx_code"] == "CBA"].iloc[0]

    assert pd.isna(cba["gross_margin_expansion"])
    assert pd.isna(cba["operating_margin_expansion"])
    ind1 = masked.frame[masked.frame["asx_code"] == "IND1"].iloc[0]
    assert ind1["gross_margin_expansion"] == 0.01, "industrials keep theirs"


def test_a_column_is_matched_by_canonical_name_not_by_spelling():
    """screener.universe says ev_to_ebitda; the rules say ev_ebitda.

    Comparing raw names skipped the column entirely, so a bank's EV/EBITDA
    stayed in the frame and in every peer statistic — the alias failure the
    registry exists to prevent, one layer above where it was being prevented.
    """
    df = universe()
    df["ev_to_ebitda"] = [12.0, 8.0, 9.0, 10.0, 11.0]

    masked = apply_applicability(df, GOOD_FEED)
    cba_row = masked.frame[masked.frame["asx_code"] == "CBA"].iloc[0]

    assert pd.isna(cba_row["ev_to_ebitda"]), "the frame column is masked"
    assert "ev_ebitda" in masked.assessments["CBA"], \
        "the assessment is keyed canonically, which is what consumers look up"
    assert masked.assessments["CBA"]["ev_ebitda"].cause is Cause.DOMAIN

    ind1 = masked.frame[masked.frame["asx_code"] == "IND1"].iloc[0]
    assert ind1["ev_to_ebitda"] == 8.0, "industrials keep theirs"


# ── Domains that are not resolvable stay conservative ─────────────────────────

def test_an_unresolved_domain_suppresses_domain_sensitive_metrics():
    df = pd.DataFrame([{
        "asx_code": "XYZ", "sector": "", "industry": "", "is_reit": False,
        "is_miner": False, "revenue_ttm": None,
        "debt_to_equity": 4.6, "roe": 0.12,
    }])
    masked = apply_applicability(df, GOOD_FEED)
    row = masked.frame.iloc[0]

    assert pd.isna(row["debt_to_equity"]), "no domain, no industrial default"
    assert row["roe"] == 0.12, "domain-neutral metrics survive"
    assert masked.tally["domain:unknown"] == 1


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
