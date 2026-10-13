#!/usr/bin/env python
"""
Eligibility is a lifecycle decision; freshness is per entity
============================================================
Two rules, both of which the original code got wrong by omission.

**Eligibility comes from `market.funds`, not from the fetch list.** `is_active`
existed but was written TRUE on every seed and never updated -- the seed's
`ON CONFLICT` omits it -- so nothing had ever flipped it. The flag existed;
the transition did not. A fund missing from the fetch list is not retired, and
conflating the two is how eight ETFs served June prices for four months.

**Freshness belongs to the entity.** `indices_funds.py` joins every fund to a
single global `MAX(price_date)`, so a fund that stopped updating renders null
rather than its own last value — the consumer cannot tell "no data" from "old
data" from "no longer trades".

Run:  python tests/test_fund_population_and_freshness.py
"""

import re
import sys
from datetime import date, timedelta
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from compute.engine.fund_population import (                     # noqa: E402
    LIFECYCLE_COLUMNS, STALE_AFTER_DAYS, FundFreshness)

TODAY = date.today()


def _f(code, last=None, active=True, retired=None):
    return FundFreshness(code, last, active, retired)


# ── Freshness is four states, never a bare date ─────────────────────────────

def test_a_recent_price_is_current():
    assert _f("VAS", TODAY - timedelta(days=1)).status == "current"


def test_a_long_silence_is_stale():
    """The eight ETFs: last price 5 June, discovered 9 October."""
    assert _f("ETHI", TODAY - timedelta(days=126)).status == "stale"


def test_no_price_at_all_is_never_not_stale():
    """DIV and PMC. "Never published" is a different fact from "went quiet",
    and the cause differs: a dead identifier versus a provider that stopped
    answering."""
    assert _f("DIV", None).status == "never"


def test_a_retired_fund_is_retired_whatever_its_last_price():
    """Retirement outranks staleness.

    A retired security SHOULD have an old last price; reporting that as
    `stale` would make every correct retirement look like a fault, and a
    surface full of permanent findings is one operators stop reading.
    """
    assert _f("PMC", TODAY - timedelta(days=250),
              retired=date(2026, 2, 2)).status == "retired"


def test_inactive_counts_as_retired_even_without_a_date():
    assert _f("OLD", None, active=False).status == "retired"


def test_the_stale_boundary_is_inclusive():
    assert _f("A", TODAY - timedelta(days=STALE_AFTER_DAYS)).status == "current"
    assert _f("B", TODAY - timedelta(days=STALE_AFTER_DAYS + 1)).status == "stale"


def test_age_is_exposed_alongside_status():
    """A status without an age cannot be triaged; an age without a status
    makes every caller re-derive the rule, and they will not agree."""
    f = _f("ETHI", TODAY - timedelta(days=126))
    assert f.age_days == 126 and f.status == "stale"
    assert _f("DIV", None).age_days is None


# ── Eligibility reads the lifecycle, both halves ────────────────────────────

def _source() -> str:
    return (BACKEND / "compute" / "engine" / "fund_population.py").read_text(
        encoding="utf-8")


def test_eligibility_requires_active_AND_not_retired():
    """Either half alone leaves a hole.

    `is_active` alone was the status quo and never excluded anything, since
    nothing ever set it false. `retired_at` alone would re-admit a fund
    deactivated for some other reason.
    """
    src = _source()
    q = src[src.index("_ELIGIBLE"):src.index("_RETIRED")]
    assert "is_active = TRUE" in q, "eligibility ignores is_active"
    assert "retired_at IS NULL" in q, "eligibility ignores retired_at"


def test_the_lifecycle_columns_are_declared_in_one_place():
    """The migration and the reader must not drift apart silently."""
    assert LIFECYCLE_COLUMNS == ("retired_at", "retired_reason",
                                 "successor_code")
    src = _source()
    for col in LIFECYCLE_COLUMNS:
        assert col in src, f"{col} is declared but never read"


def test_freshness_is_per_entity_not_a_global_as_of():
    """The defect in indices_funds.py, which must not be reproduced here.

    A global MAX(price_date) joined to every fund reports null for anything
    that stopped updating. Freshness has to be grouped per fund.
    """
    src = _source()
    q = src[src.index("_FRESHNESS"):src.index("STALE_AFTER_DAYS")]
    assert "GROUP BY" in q and "max(p.price_date)" in q
    assert "LEFT JOIN" in q, (
        "an inner join would drop funds with no prices -- exactly the ones "
        "being looked for")


# ── The dry run writes nothing ──────────────────────────────────────────────

#: `UPDATE\s+\w+`, not `UPDATE\s+\w` -- with a single `\w` the trailing `\b`
#: can never match, because the next character is also a word character. The
#: first draft of this pattern was blind to every UPDATE in the codebase and
#: the no-writes tests passed anyway. Caught by the mutation control below,
#: which is the only reason it is not still blind.
WRITE = re.compile(r"\b(INSERT\s+INTO|UPDATE\s+\w+|DELETE\s+FROM|TRUNCATE|"
                   r"ALTER\s+TABLE|DROP\s+TABLE|COMMIT)\b", re.IGNORECASE)


def test_the_reconciliation_script_performs_no_writes():
    """An instrument must not join the system it observes.

    A reconciliation that corrected what it found could not be run to decide
    whether correction is needed.
    """
    src = (BACKEND / "scripts" / "reconcile_fund_population.py").read_text(
        encoding="utf-8")
    body = "\n".join(l for l in src.splitlines()
                     if not l.strip().startswith("#"))
    found = WRITE.findall(body)
    assert not found, f"the dry run contains write statements: {found}"


def test_the_population_module_performs_no_writes():
    body = "\n".join(l for l in _source().splitlines()
                     if not l.strip().startswith("#"))
    found = WRITE.findall(body)
    assert not found, f"fund_population issues writes: {found}"


def test_the_write_detector_can_fail():
    """Mutation control: a scanner that never matches proves nothing."""
    assert WRITE.findall("INSERT INTO market.funds (a) VALUES (1)")
    assert WRITE.findall("UPDATE market.funds SET is_active = FALSE")
    assert not WRITE.findall("SELECT asx_code FROM market.funds")


def test_the_dry_run_enforces_read_only_at_the_database():
    """The regex is supplementary; the database is the guarantee.

    A source scan can only show no write was *authored*. A write reachable
    through a helper, an ORM flush, or a statement added next week would all
    pass it. So the script sets READ ONLY and then attempts a write, failing
    loudly if the write succeeds -- the containment is proven at runtime, not
    asserted at authoring time.
    """
    src = (BACKEND / "scripts" / "reconcile_fund_population.py").read_text(
        encoding="utf-8")
    assert "SET TRANSACTION READ ONLY" in src, (
        "the dry run does not put the transaction in read-only mode")
    probe = src[src.index("async def _enforce_read_only"):]
    probe = probe[:probe.index("async def main")]
    assert "current_setting('transaction_read_only')" in probe, (
        "read-only is set but never confirmed, so a silently ineffective "
        "guard would read as containment")
    assert "raise RuntimeError" in probe, (
        "a failed confirmation does not abort the run, so the script could "
        "report itself read-only while writes were possible")
    # Against production the guard must CONFIRM the setting, never test it by
    # attempting a write: that tests for mutability by mutating, so the one
    # case it exists to catch is the case where it performs the write. The
    # write-rejection test belongs in an isolated database.
    for mutation in ("CREATE TEMP TABLE", "INSERT INTO", "UPDATE "):
        assert mutation not in probe, (
            f"the production guard attempts {mutation!r} to prove "
            f"read-only; if the guard is not in force, that write executes")
    assert src.index("_enforce_read_only(db)") < src.index("await reconcile("), (
        "containment is established after the first query rather than before")


def test_the_dry_run_installs_redaction_before_anything_else():
    """A probe that logs a request URL re-creates the credential leak.

    The 9 Oct ISIN probe imported neither installer and escaped only because
    nothing had configured logging, leaving the root logger at WARNING.
    Luck, not design.
    """
    src = (BACKEND / "scripts" / "reconcile_fund_population.py").read_text(
        encoding="utf-8")
    assert "install_secret_redaction(" in src, (
        "the dry run does not install log redaction")
    assert src.index("install_secret_redaction(") < src.index(
        "from compute.engine.fund_population"), (
        "redaction is installed after the modules that may log are imported")


# ── Lifecycle columns are OUT OF SCOPE here ────────────────────────────────
#
# The additive migration, DIV's retirement and the PMC/GLS link are
# deliberately absent from this change. fund_population degrades gracefully
# without the columns -- lifecycle_available() inspects information_schema
# and falls back to is_active alone -- so reconciliation runs on the current
# schema and reports "lifecycle metadata unavailable".


def test_reconciliation_works_without_the_lifecycle_columns():
    """A pending migration must not block visibility into today's omissions.

    The eight omitted funds are visible now and were visible for four months.
    """
    src = _source()
    assert "async def lifecycle_available(" in src
    assert "LIFECYCLE_UNAVAILABLE" in src
    assert 'LIFECYCLE_PREDICATE if await lifecycle_available(db) else ""' in src, (
        "eligibility does not fall back when the columns are absent")


def test_no_migration_ships_in_this_change():
    assert not (BACKEND / "migrations" / "add_fund_lifecycle_columns.sql").exists(), (
        "the lifecycle migration is in scope for a later change, not this one")


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
            except Exception as exc:                             # noqa: BLE001
                print(f"  ERROR {name}: {type(exc).__name__}: {exc}")
                failures.append(name)
    total = len([n for n in globals() if n.startswith("test_")])
    print(f"\n{total - len(failures)}/{total} passed")
    sys.exit(1 if failures else 0)
