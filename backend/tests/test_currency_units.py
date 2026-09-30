"""
Gate 1b — a ratio with two currencies in it has no unit
=======================================================
Found 30 Sep 2026, while closing the ingestion blockers. EODHD states two
currencies per fundamentals file and only one of them is about the numbers:

    General.CurrencyCode              AUD    the LISTING currency
    Income_Statement currency_symbol  IDR    the STATEMENTS

Checking only ``General`` passes every foreign reporter straight through, and
that is what the loader did. Measured across the newest snapshot per code:

    NONE 1016    AUD 843    USD 89    NZD 39    CAD 16
    PGK 4   GBP 4   EUR 4   IDR 1   MYR 1   SGD 1   HKD 1

160 ASX companies report in a non-AUD currency, and BHP -- the largest company
on the exchange -- is one of them. Its earnings per share are stated in USD and
its price is quoted in AUD, so its P/E has been off by roughly the exchange
rate for as long as the column has existed. Amcor and a2 Milk likewise.

Two things this must NOT do, and both have their own test below:

  * suppress the 1,016 codes that state no currency. Not knowing a currency is
    not evidence of a mismatch, and treating it as one would blank half the
    exchange to fix 160 companies.
  * suppress currency-invariant ratios. gross_margin, roe and debt_to_equity
    divide one statement figure by another, so the units cancel and the
    numbers are correct exactly as they stand.

Run under pytest, or standalone:
    cd backend && ../asx-venv/bin/python tests/test_currency_units.py
"""

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from compute.engine.applicability import (                          # noqa: E402
    Applicability, Cause, CROSS_CURRENCY, Domain, Observation, UNIT_SENSITIVE,
    assess, unit_gate,
)

USD = Observation(reporting_currency="USD")
AUD = Observation(reporting_currency="AUD")
UNKNOWN = Observation()


# ── The defect ───────────────────────────────────────────────────────────────

def test_a_usd_reporters_pe_is_not_meaningful():
    """BHP. Price in AUD over earnings in USD is not a P/E, it is a number."""
    a = assess("pe_ratio", 18.4, Domain.MINING_PRODUCER, USD)
    assert a.state is Applicability.NOT_MEANINGFUL
    assert a.cause is Cause.UNIT_MISMATCH
    assert a.display() == "NM"


def test_the_reason_names_the_currency_that_caused_it():
    a = assess("pe_ratio", 18.4, Domain.MINING_PRODUCER, USD)
    assert "USD" in a.reason and "AUD" in a.reason


def test_every_mixed_ratio_is_covered():
    """Each of these divides an AUD market quantity by a statement quantity."""
    for metric in ("pe_ratio", "price_to_book", "price_to_sales", "peg_ratio",
                   "ev_ebitda", "ev_ebit", "altman_z_score"):
        a = assess(metric, 1.0, Domain.MINING_PRODUCER, USD)
        assert a.state is Applicability.NOT_MEANINGFUL, metric
        assert a.cause is Cause.UNIT_MISMATCH, metric


# ── The controls: what must NOT be suppressed ────────────────────────────────

def test_an_aud_reporter_is_untouched():
    """Without this, a gate that suppressed everything would pass the tests
    above. 843 of the companies that state a currency state AUD."""
    assert assess("pe_ratio", 18.4, Domain.MINING_PRODUCER, AUD).state \
        is Applicability.APPLICABLE


def test_an_unknown_currency_is_not_treated_as_a_mismatch():
    """1,016 codes state no currency at all -- they have no financial
    statements. Not knowing is not evidence of difference, and suppressing
    them would blank half the exchange to fix 160 companies."""
    assert assess("pe_ratio", 18.4, Domain.MINING_PRODUCER, UNKNOWN).state \
        is Applicability.APPLICABLE
    assert assess("pe_ratio", 18.4, Domain.MINING_PRODUCER, None).state \
        is Applicability.APPLICABLE


def test_currency_invariant_ratios_stay_applicable():
    """Both sides come from the same statements, so the units cancel. These
    numbers are correct as they stand and suppressing them would be a
    regression, not a fix."""
    for metric in ("roe", "roa", "gross_margin", "operating_margin",
                   "net_margin", "debt_to_equity"):
        assert metric not in CROSS_CURRENCY, metric
        assert assess(metric, 0.25, Domain.MINING_PRODUCER, USD).state \
            is Applicability.APPLICABLE, metric


def test_domain_still_outranks_units():
    """A metric meaningless for a bank is NM whatever currency it reports in,
    and the domain reason is the more informative of the two."""
    a = assess("ev_ebitda", 7.1, Domain.BANK, USD)
    assert a.state is Applicability.NOT_MEANINGFUL
    assert a.cause is Cause.DOMAIN


# ── The gate in isolation ────────────────────────────────────────────────────

def test_the_gate_passes_metrics_it_does_not_govern():
    assert unit_gate("roe", "USD") is None


def test_the_gate_is_case_and_whitespace_insensitive():
    assert unit_gate("pe_ratio", " aud ") is None
    assert unit_gate("pe_ratio", "usd") is not None


def test_unit_sensitive_is_derived_not_declared_twice():
    assert UNIT_SENSITIVE == frozenset(CROSS_CURRENCY)


def test_every_reason_can_name_its_currency():
    """A reason template that forgets its placeholder would render a sentence
    that never says which currency was involved."""
    for metric, template in CROSS_CURRENCY.items():
        assert "{currency}" in template, metric
        assert "NZD" in template.format(currency="NZD"), metric


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
