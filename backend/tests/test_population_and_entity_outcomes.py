#!/usr/bin/env python
"""
A producer's population comes from the source, and every entity gets a verdict
==============================================================================
`fund_prices` took its expected population from the same hardcoded list that
decides what gets fetched:

    FUNDS: list[dict] = [ ... 47 entries ... ]
    tally = ProducerTally("fund_prices", expected=len(FUNDS))

`market.funds` held 55. Eight ETFs served June prices for four months inside a
job that reported `success` every day, and **no assertion could have caught
it**: drop an entity from the list and `expected` drops with it. The contract
was sound; its population was not.

Hidden behind the same code path, because the contract is all-or-nothing
(`expected > 0 and usable == 0`):

    DIV   delisted 2020-05-21, fetched daily ever since, never a row
    PMC   became GLS, fetched daily since, never a row

45 of 47 passes. Forever.

Three different causes, one symptom
-----------------------------------
"This fund has no current price" was produced by never being requested, by a
dead identifier, and by the provider refusing the host (yfinance, 9 Oct 2026)
— all at once, all invisible, because the run reported a single verdict.

Run:  python tests/test_population_and_entity_outcomes.py
"""

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from compute.engine.producer_contract import (                # noqa: E402
    EMPTY, EXCLUDED, PROVIDER_ERROR, USABLE, PopulationReconciliation,
    ProducerFailure, ProducerTally)


def _recon(eligible, configured):
    return PopulationReconciliation("fund_prices", frozenset(eligible),
                                    frozenset(configured))


# ── Population reconciliation ───────────────────────────────────────────────

def test_the_eight_omitted_etfs_are_found():
    """The defect, at the scale it actually occurred."""
    eligible = {f"F{i}" for i in range(47)} | {
        "ETHI", "EX20", "HNDQ", "SLF", "VBND", "VESG", "DZZF", "ETPMAG"}
    configured = {f"F{i}" for i in range(47)}
    r = _recon(eligible, configured)
    assert len(r.eligible) == 55 and len(r.configured) == 47
    assert r.omitted == frozenset(
        {"ETHI", "EX20", "HNDQ", "SLF", "VBND", "VESG", "DZZF", "ETPMAG"})
    assert not r.stale_configured
    assert not r.reconciled
    assert "never refreshed" in " ".join(r.findings())


def test_stale_configuration_is_a_finding_too():
    """DIV and PMC: fetched forever for securities that no longer trade.

    The opposite direction from the ETF defect, and it must not be silent
    either -- these two burned a request a day for the producer's whole life.
    """
    r = _recon(eligible={"A", "B"}, configured={"A", "B", "DIV", "PMC"})
    assert r.stale_configured == frozenset({"DIV", "PMC"})
    assert not r.omitted
    assert not r.reconciled
    assert "fetched for nothing" in " ".join(r.findings())


def test_a_reconciled_population_reports_nothing():
    r = _recon(eligible={"A", "B"}, configured={"A", "B"})
    assert r.reconciled and r.findings() == []


def test_the_population_cannot_be_derived_from_the_configured_set():
    """Mutation control — the original defect, reconstructed.

    If `eligible` is taken from `configured`, reconciliation is vacuously
    true no matter what is missing. This asserts that such a derivation
    cannot report the eight omissions, which is precisely why `eligible` must
    come from `market.funds`.
    """
    configured = {f"F{i}" for i in range(47)}
    self_derived = _recon(eligible=configured, configured=configured)
    assert self_derived.reconciled, (
        "the control is not reproducing the defect")
    assert not self_derived.omitted, (
        "a self-derived population reported an omission, which it cannot "
        "possibly see -- the control is wrong")


# ── Per-entity outcomes ─────────────────────────────────────────────────────

def test_every_entity_gets_an_explicit_outcome():
    t = ProducerTally("fund_prices", expected=4)
    t.obtained("VAS", 5)
    t.nothing_available("DIV")
    t.refusal("ETHI", "rate limited")
    t.excluded("PMC", "retired 2026-02-02, successor GLS")
    assert [o.code for o in t.outcomes] == ["VAS", "DIV", "ETHI", "PMC"]
    assert [o.outcome for o in t.outcomes] == [
        USABLE, EMPTY, PROVIDER_ERROR, EXCLUDED]
    assert t.outcomes[0].rows == 5


def test_the_three_causes_are_distinguishable():
    """The point of the whole change.

    Never requested, dead identifier, and provider refusal all surfaced as
    "no current price". They must not share an outcome.
    """
    t = ProducerTally("fund_prices", expected=3)
    t.nothing_available("DIV")                  # dead identifier
    t.refusal("ETHI", "rate limited")           # provider refused
    t.excluded("PMC", "retired, successor GLS")  # deliberately skipped
    by_code = {o.code: o.outcome for o in t.outcomes}
    assert len({by_code["DIV"], by_code["ETHI"], by_code["PMC"]}) == 3, (
        f"causes collapsed into one outcome: {by_code}")


def test_an_exclusion_must_carry_a_reason():
    """An exclusion without a reason is an omission wearing a label."""
    t = ProducerTally("p", expected=1)
    try:
        t.excluded("PMC", "")
    except ValueError:
        return
    raise AssertionError(
        "a reasonless exclusion was accepted, so a silently dropped entity "
        "can be recorded as a deliberate decision")


# ── Degraded is a state ─────────────────────────────────────────────────────

def test_partial_failure_is_degraded_not_failed():
    """Successful data publishes; the run still says something is wrong."""
    t = ProducerTally("fund_prices", expected=3)
    t.obtained("VAS", 5)
    t.obtained("STW", 5)
    t.nothing_available("DIV")
    assert t.degraded
    t.verify()                        # must NOT raise: 2 of 3 published
    assert t.rows == 10, "successful entities were not published"


def test_a_total_failure_is_still_a_failure_not_degraded():
    """Degradation must not become a way to soften a dead run."""
    t = ProducerTally("fund_prices", expected=2)
    t.refusal("VAS", "rate limited")
    t.refusal("STW", "rate limited")
    assert not t.degraded, "a run that obtained nothing reported as degraded"
    try:
        t.verify()
    except ProducerFailure:
        return
    raise AssertionError("a total failure did not raise")


def test_an_unreconciled_population_degrades_a_clean_run():
    """The eight ETFs again — every fetched entity succeeded.

    Without this, a run where all 47 configured funds published looks
    perfect while 8 eligible ones are never requested. That is exactly the
    state the system was in for four months.
    """
    t = ProducerTally("fund_prices", expected=2)
    t.obtained("VAS", 5)
    t.obtained("STW", 5)
    assert not t.degraded, "a clean, reconciled run reported as degraded"
    t.population = _recon(eligible={"VAS", "STW", "ETHI"},
                          configured={"VAS", "STW"})
    assert t.degraded, (
        "every fetched entity succeeded and an eligible one was never "
        "requested, yet the run reported clean -- the four-month defect")
    assert any("ETHI" in line for line in t.report())


def test_a_clean_run_reports_nothing():
    t = ProducerTally("fund_prices", expected=2)
    t.obtained("VAS", 5)
    t.obtained("STW", 5)
    t.population = _recon(eligible={"VAS", "STW"}, configured={"VAS", "STW"})
    assert not t.degraded and t.report() == []


def test_excluded_entities_do_not_degrade_the_run():
    """A documented retirement is a decision, not a failure."""
    t = ProducerTally("fund_prices", expected=2)
    t.obtained("VAS", 5)
    t.excluded("DIV", "delisted 2020-05-21")
    t.population = _recon(eligible={"VAS"}, configured={"VAS"})
    assert not t.degraded, (
        "a documented exclusion degraded the run, which would make every "
        "retirement look like a fault and train operators to ignore it")


# ── The contract that already existed still holds ───────────────────────────

def test_an_empty_population_is_vacuous_not_failed():
    ProducerTally("p", expected=0).verify()


def test_the_summary_names_the_population_gap():
    t = ProducerTally("fund_prices", expected=47)
    t.obtained("VAS", 5)
    t.population = _recon(eligible={"VAS", "ETHI"}, configured={"VAS"})
    assert "omitted" in t.summary


if __name__ == "__main__":
    failures = []
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  PASS  {name}")
            except AssertionError as exc:
                print(f"  FAIL  {name}\n        {exc}")
                failures.append(name)
            except Exception as exc:                           # noqa: BLE001
                print(f"  ERROR {name}: {type(exc).__name__}: {exc}")
                failures.append(name)
    total = len([n for n in globals() if n.startswith("test_")])
    print(f"\n{total - len(failures)}/{total} passed")
    sys.exit(1 if failures else 0)
