#!/usr/bin/env python
"""
Reading market.companies without a currency predicate multiplies rows
=====================================================================
`market.companies` is SCD Type 2. An attribute change closes the old row and
opens a new one, so the table holds history:

    id  477   valid_from 2026-04-28  valid_to 2026-04-28  is_current = f
    id 4225   valid_from 2026-04-28  valid_to (null)      is_current = t

Measured 7 Oct 2026: 4,459 rows for 2,579 codes; 1,878 codes carry at least
one superseded row. A query that joins the table on `asx_code` alone gets
about 1.7 rows per company, and nothing errors -- the extra rows are real rows
with the same key.

What that cost, measured in production
--------------------------------------
    /companies list      3,737 entries returned; 2,147 companies exist
    alert_worker           8 rows fetched for 4 active alerts
    announcement_worker  LIMIT 200 on a fanned-out join yields ~115 distinct
                         codes, so the top-200 announcement sweep silently
                         covered a little over half its intended population
    /companies/{code}    SELECT * ... .first() -- an arbitrary choice between
                         the current row and a historical one

The arbitrary-choice cases are narrow but real: 4 codes have a superseded row
that differs in a served column. DUI's superseded row says gics_sector
'Other'; its current row says 'Financials'.

Why this is a guard and not just a patch
----------------------------------------
Three of these sites were already defended individually -- two `DISTINCT ON`
wrappers and a `SELECT DISTINCT` -- which masked the duplication at those call
sites while leaving the join wrong everywhere else. One of them carries a
comment explaining that companies "have multiple rows", so the condition was
diagnosed, handled locally, and never fixed at the source. A per-site remedy
does not generalise to the next query someone writes.

The rule is: identity and classification are read from
`market.companies_current`. The base table is for writers.

Why the AST
-----------
The property is syntactic -- "a SQL string names this table" -- so it is
checked on the parsed source, looking only at string constants. A text scan
over the file would read this docstring, which names `market.companies`
repeatedly, and report the defect it documents. That has happened four times
in this codebase.

Run:  python tests/test_company_reads_are_current.py
"""

import ast
import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]

#: Enforced: the serving and compute layers, where a duplicated row becomes a
#: number a customer reads.
ROOTS = ("app", "compute")

#: Legacy ingestion scripts that build worklists from the base table. Their
#: duplicates cost repeated downloads, not wrong answers, and most are
#: superseded by scripts/eodhd/v2. Frozen as a named set so a NEW offender
#: fails even though these do not.
LEGACY_WORKLIST_OFFENDERS = {
    "scripts/load_fmp_prices.py",
    "scripts/load_prices.py",
    "scripts/update_prices.py",
    "scripts/update_prices_eodhd.py",
    "scripts/update_prices_fmp.py",
    "scripts/eodhd/download_daily_fundamentals.py",
    "scripts/eodhd/download_historical_dividends.py",
    "scripts/eodhd/download_historical_fundamentals.py",
    "scripts/eodhd/download_historical_prices.py",
    "scripts/load_asx_companies.py",
    "scripts/load_eodhd_financials.py",
    "scripts/load_eodhd_prices.py",
    "scripts/load_fmp_financials.py",
}

#: A literal is SQL against the table only if it is referenced from a clause
#: that selects rows. Without this the scan flags log messages -- three of
#: them in sync_companies_from_exchange.py, e.g. "codes not in
#: market.companies" -- which is a report about prose, not about a query.
_SQL_REF = re.compile(r"\b(from|join)\s+market\.companies\b", re.IGNORECASE)

#: Statements that legitimately address the base table. Writers maintain the
#: history -- closing a row by setting is_current = FALSE is precisely a write
#: that must NOT be confined to current rows.
WRITE_VERBS = ("insert into", "update ", "delete from", "create ", "alter ",
               "comment on", "drop ")


def _offending_literals(source: str):
    """Every string constant naming market.companies without a currency bound.

    Returns (literal, reason) pairs. Only ast.Constant strings are examined,
    so comments and docstrings are structurally out of scope -- except a
    module docstring, which IS a string constant, so docstrings are skipped
    explicitly below.
    """
    tree = ast.parse(source)

    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            body = getattr(node, "body", None)
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                docstrings.add(id(body[0].value))

    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        if id(node) in docstrings:
            continue
        text = node.value
        low = text.lower()
        if "market.companies" not in low:
            continue
        # companies_current is the correct read and must not be flagged by the
        # prefix it shares with the base table.
        stripped = low.replace("market.companies_current", "")
        if not _SQL_REF.search(stripped):
            continue
        if any(verb in low for verb in WRITE_VERBS):
            continue
        if "is_current" in low:
            continue
        out.append((text, "reads market.companies with no is_current bound"))
    return out


def _scan(roots=ROOTS):
    findings = []
    for root in roots:
        for path in (BACKEND / root).rglob("*.py"):
            if "/tests/" in path.as_posix():
                continue
            try:
                source = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            try:
                for literal, reason in _offending_literals(source):
                    findings.append((path.relative_to(BACKEND).as_posix(),
                                     reason, literal.strip()[:90]))
            except SyntaxError:
                continue
    return findings


def test_no_module_reads_the_base_table_unbounded():
    findings = _scan()
    assert not findings, (
        "company identity must be read from market.companies_current:\n" +
        "\n".join(f"  {p}: {r}\n      {lit}" for p, r, lit in findings))


def test_no_new_ingestion_script_joins_the_base_table():
    """scripts/ is held at its known set rather than enforced to zero.

    These build worklists -- `SELECT asx_code ... WHERE status = 'active'` --
    so a duplicated code costs a repeated download, not a wrong number, and
    most are superseded by scripts/eodhd/v2. Freezing the set keeps that
    judgement from quietly becoming a licence for new ones.
    """
    offenders = {path for path, _, _ in _scan(("scripts",))}
    new = offenders - LEGACY_WORKLIST_OFFENDERS
    assert not new, (
        "new ingestion code reads market.companies unbounded: " +
        ", ".join(sorted(new)))
    gone = LEGACY_WORKLIST_OFFENDERS - offenders
    assert not gone, (
        "these were fixed or removed; drop them from the frozen set so it "
        "keeps describing reality: " + ", ".join(sorted(gone)))


def test_the_scan_covers_the_modules_it_claims_to():
    """A guard that has lost its population passes for the wrong reason.

    This one is scoped by directory, so a move or a rename can silently empty
    it. Anchored on files known to contain company SQL.
    """
    seen = 0
    for root in ROOTS:
        for path in (BACKEND / root).rglob("*.py"):
            try:
                if "market.companies" in path.read_text(encoding="utf-8").lower():
                    seen += 1
            except (UnicodeDecodeError, OSError):
                continue
    assert seen >= 10, (
        f"only {seen} modules mention market.companies; the scan has lost its "
        "population and would pass over an empty set")


def test_a_writer_is_not_flagged():
    """Closing a superseded row is a write against the base table, by design."""
    src = 'q = "UPDATE market.companies SET is_current = FALSE WHERE id = %s"'
    assert not _offending_literals(src)

    src = 'q = "INSERT INTO market.companies (asx_code) VALUES (%s)"'
    assert not _offending_literals(src)


def test_the_view_is_not_flagged_by_its_shared_prefix():
    src = 'q = "SELECT asx_code FROM market.companies_current WHERE status = %s"'
    assert not _offending_literals(src), (
        "the correct read is being reported as the defect, which would make "
        "the guard unsatisfiable and force it to be deleted")


def test_an_explicit_predicate_on_the_base_table_is_accepted():
    """build_screener_universe reads two admin columns the view lacked, with
    its own predicate. That is correct and must stay legal."""
    src = ('q = "SELECT business_model_tag FROM market.companies '
           'WHERE asx_code = %s AND is_current = TRUE"')
    assert not _offending_literals(src)


def test_the_check_can_actually_fail():
    """Mutation control, against the exact text that was in alert_worker.py."""
    src = ('q = """SELECT c.company_name FROM users.alerts a '
           'LEFT JOIN market.companies c ON c.asx_code = a.asx_code"""')
    found = _offending_literals(src)
    assert found, (
        "the detector does not fire on the literal that fetched 8 rows for 4 "
        "alerts, so the guards above prove nothing")


def test_a_docstring_naming_the_table_does_not_trip_the_scan():
    """This file's own docstring is the counterexample."""
    src = '"""Reads market.companies on asx_code alone."""\nx = 1\n'
    assert not _offending_literals(src), (
        "the scan reads prose; it would report the bug its own documentation "
        "describes")


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
    total = len([n for n in globals() if n.startswith("test_")])
    print(f"\n{total - len(failures)}/{total} passed")
    sys.exit(1 if failures else 0)
