#!/usr/bin/env python
"""
Restore the eight omitted funds, and nothing else
=================================================
Eight funds sit in `market.funds` and were never in `FUNDS`, so they were
never fetched: `ETHI EX20 HNDQ SLF VBND VESG DZZF ETPMAG`. All eight were
verified currently trading on 8 Oct 2026. Their last recorded price is June,
written by a writer this repository does not identify.

This change restores them to the fetch set and wires source-derived
reconciliation into the producer. It deliberately excludes:

  * the additive lifecycle migration
  * DIV's retirement
  * the PMC -> GLS link, whose ISINs differ (AU000000PMC2 vs AU0000440166)
  * any backfill of the June-October gap

Scope matters here because three of those four rest on evidence that is still
outstanding, and the fourth is a separate decision.

Run:  python tests/test_fund_restoration_is_scoped.py
"""

import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

SRC = (BACKEND / "compute" / "engine" / "fund_prices.py").read_text(
    encoding="utf-8")

RESTORED = ("ETHI", "EX20", "HNDQ", "SLF", "VBND", "VESG", "DZZF", "ETPMAG")


def _codes() -> list[str]:
    block = SRC[SRC.index("FUNDS: list[dict] = ["):]
    block = block[:block.index("\n]")]
    return re.findall(r'dict\(asx_code="([A-Z0-9]+)"', block)


# ── The eight are restored ──────────────────────────────────────────────────

def test_all_eight_are_in_the_fetch_set():
    missing = [c for c in RESTORED if c not in _codes()]
    assert not missing, f"still omitted from FUNDS: {missing}"


def test_the_fetch_set_grew_by_exactly_eight():
    """47 -> 55. A larger jump means something else came along."""
    assert len(_codes()) == 55, (
        f"FUNDS has {len(_codes())} entries, expected 55 (47 + 8)")


def test_no_duplicates_were_introduced():
    codes = _codes()
    dupes = {c for c in codes if codes.count(c) > 1}
    assert not dupes, f"duplicated entries: {dupes}"


def test_div_and_pmc_are_still_configured():
    """They stay in the fetch set so their failures stay VISIBLE.

    Removing them would silence two dead tickers without recording that they
    are dead -- the exact conflation this work exists to end. They are
    retired by the lifecycle change, which is not in this candidate, so until
    then they keep failing per-entity and the run keeps reporting it.
    """
    codes = _codes()
    assert "DIV" in codes and "PMC" in codes, (
        "DIV/PMC were dropped from the fetch set, which hides their failure "
        "instead of recording it")


# ── Reconciliation is wired, not merely available ───────────────────────────

def test_expected_comes_from_the_source_not_the_fetch_list():
    """The original defect, in one line.

    `expected=len(FUNDS)` cannot see what FUNDS omits.
    """
    assert "expected=len(FUNDS)" not in SRC, (
        "expected is still derived from the fetch list")
    assert "tally.expected = len(recon.eligible)" in SRC


def test_the_producer_actually_calls_reconcile():
    """A module nobody calls is a comment."""
    assert "from compute.engine.fund_population import reconcile" in SRC
    body = SRC[SRC.index("async def run("):]
    assert "recon = await reconcile(db, configured)" in body
    assert "tally.population = recon" in body, (
        "the reconciliation result is computed and then discarded")


def test_findings_are_logged():
    body = SRC[SRC.index("async def run("):]
    assert "recon.findings()" in body, (
        "a divergence between population and fetch set is never reported")


# ── Out of scope ────────────────────────────────────────────────────────────

def test_no_lifecycle_migration():
    assert not (BACKEND / "migrations" / "add_fund_lifecycle_columns.sql").exists()


def test_nothing_retires_div():
    """DIV's official delisting date is still outstanding.

    Its last observed trade was 2020-05-21, which establishes the last trade
    seen -- not an official delisting date.
    """
    for path in ("compute/engine/fund_prices.py",
                 "compute/engine/fund_population.py"):
        src = (BACKEND / path).read_text(encoding="utf-8")
        body = "\n".join(l for l in src.splitlines()
                         if not l.strip().startswith("#"))
        assert "retired_reason" not in body or "retired_at IS NULL" in body, (
            f"{path} writes a retirement")
        assert "UPDATE market.funds" not in body.upper(), (
            f"{path} updates market.funds")


def test_pmc_is_not_linked_to_gls():
    """Different ISINs; continuity unproven."""
    for path in ("compute/engine/fund_prices.py",
                 "compute/engine/fund_population.py"):
        src = (BACKEND / path).read_text(encoding="utf-8")
        statements = [l for l in src.splitlines()
                      if l.strip() and not l.strip().startswith("#")]
        offenders = [l for l in statements if "GLS" in l.upper()]
        assert not offenders, f"{path} references GLS: {offenders}"


def test_this_change_restores_recent_prices_only():
    """NOT a gap backfill.

    backfill_days defaults to 3, so a scheduled run writes only the last few
    days. The June-October hole in those eight funds' history stays open and
    is a separate decision.
    """
    assert "backfill_days: int = 3" in SRC, (
        "the default backfill window changed; this candidate would now fill "
        "history rather than restore current prices")


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
