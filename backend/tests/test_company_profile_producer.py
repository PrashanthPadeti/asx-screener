#!/usr/bin/env python
"""
The company profile producer
============================
Measured 23 Oct 2026: employee_count, listing_date, logo_url, state and abn
are populated for 0 of 2,589 current companies; description and website for
about 70%. The columns exist and nothing fills them, which is why every
company page reads "EMPLOYEES —".

This producer fills them from a provider that has the data, on a schedule,
with a date attached. These tests cover the properties that decide whether
it can be trusted to do that.

Run:  python tests/test_company_profile_producer.py
"""

import ast
import re
import sys
from datetime import date
from pathlib import Path

_HERE = Path(__file__).resolve().parents[1]
BACKEND = _HERE if (_HERE / "compute" / "engine").is_dir() else Path.cwd()
sys.path.insert(0, str(BACKEND))

SRC_PATH = BACKEND / "compute" / "engine" / "company_profile.py"
SRC = SRC_PATH.read_text(encoding="utf-8")
MIGRATION = (BACKEND / "migrations"
             / "add_company_profile_fields.sql").read_text(encoding="utf-8")


def _module():
    """The pure parts, without importing httpx, the DB or app settings."""
    tree = ast.parse(SRC)
    keep = []
    for n in tree.body:
        if isinstance(n, ast.FunctionDef) and n.name in ("_clean", "extract"):
            keep.append(n)
        elif isinstance(n, (ast.Assign, ast.AnnAssign)):
            t = ast.unparse(n)
            if t.startswith(("FIELD_MAP", "NEVER_WRITTEN", "REFRESH_EVERY_DAYS",
                             "PRODUCER", "SOURCE", "ENDPOINT")):
                keep.append(n)
    ns = {}
    exec("from datetime import date\nfrom typing import Any\n", ns)
    exec(compile(ast.Module(body=keep, type_ignores=[]), "<m>", "exec"), ns)
    return ns


NS = _module()
extract = NS["extract"]
FIELD_MAP = NS["FIELD_MAP"]


# ── "They had nothing" must not be stored as a value ─────────────────────────

def test_provider_placeholders_become_absent():
    """EODHD returns "NA" and {} for things it does not have.

    Storing those would make "we asked and they had nothing" look identical
    to a real value, which is the distinction this whole codebase keeps
    having to re-establish.
    """
    got = extract({"Description": "NA", "WebURL": "", "Phone": "  ",
                   "Officers": {}, "LEI": "N/A", "Address": "-"})
    for column in ("description", "website", "phone", "officers", "lei",
                   "head_office_address"):
        assert got[column] is None, f"{column} stored a placeholder: {got[column]!r}"


def test_real_values_survive_intact():
    """The control. If everything becomes None the test above proves nothing."""
    got = extract({"Description": "Lithium miner.", "WebURL": "https://x.au",
                   "FullTimeEmployees": 1175, "Address": "146 Colin Street",
                   "Officers": {"0": {"Name": "A"}}})
    assert got["description"] == "Lithium miner."
    assert got["website"] == "https://x.au"
    assert got["employee_count"] == 1175
    assert got["head_office_address"] == "146 Colin Street"
    assert got["officers"] == {"0": {"Name": "A"}}


def test_employee_count_is_an_integer_or_absent():
    """A count that arrives as text must not be stored as text, and a count
    that cannot be read must not be stored as zero."""
    assert extract({"FullTimeEmployees": "1175"})["employee_count"] == 1175
    assert extract({"FullTimeEmployees": "about 40"})["employee_count"] is None
    assert extract({"FullTimeEmployees": None})["employee_count"] is None


def test_an_unparseable_ipo_date_is_absent_not_guessed():
    assert extract({"IPODate": "2007-09-19"})["ipo_date"] == date(2007, 9, 19)
    assert extract({"IPODate": "not a date"})["ipo_date"] is None
    assert extract({"IPODate": "0000-00-00"})["ipo_date"] is None


def test_every_mapped_column_is_present_even_when_absent():
    """A column missing from the dict and a column set to None write
    differently. Every mapped column must appear, so the UPDATE clears a
    field the provider no longer has rather than leaving a stale value."""
    got = extract({})
    assert set(got) == set(FIELD_MAP), (
        f"extract returned {sorted(got)}, FIELD_MAP declares "
        f"{sorted(FIELD_MAP)}")
    assert all(v is None for v in got.values())


# ── One declaration, not three that drift ────────────────────────────────────

def test_the_migration_adds_every_column_the_producer_writes():
    """Producer, migration and database must describe the same set.

    A column written but never added fails at runtime on the first slice; a
    column added but never written is dead. Derived from FIELD_MAP rather
    than listed again here, so this cannot drift either.
    """
    existing = {"description", "website", "employee_count", "logo_url"}
    missing = [c for c in FIELD_MAP
               if c not in existing and f"IF NOT EXISTS {c}" not in MIGRATION]
    assert not missing, (
        f"the producer writes {missing} and the migration does not add them")


def test_the_producer_never_writes_what_it_says_it_will_not():
    """asx_companies.py instructs that isin is never touched.

    Overturning that belongs in its own change. Checked against the UPDATE
    the producer actually issues, not against the comment saying so.
    """
    for column in NS["NEVER_WRITTEN"]:
        assert column not in FIELD_MAP, f"{column} is in FIELD_MAP"
        store = SRC[SRC.index("async def store("):SRC.index("async def run(")]
        assert f"{column} =" not in store, f"store() writes {column}"


def test_a_dated_profile_must_say_where_it_came_from():
    """'As of 23 October' means different things depending on who said so."""
    assert "companies_profile_dated_has_source" in MIGRATION
    assert "profile_updated_at IS NULL OR profile_source IS NOT NULL" in MIGRATION
    store = SRC[SRC.index("async def store("):SRC.index("async def run(")]
    assert "profile_updated_at = :now" in store and "profile_source = :src" in store, (
        "a refresh stores values without dating them, so the profile can go "
        "stale in silence")


# ── Budget: priced before spending ───────────────────────────────────────────

def test_the_slice_is_priced_before_anything_is_fetched():
    """Fundamentals costs 10 calls. 2,589 companies is 25,890 — 86% of the
    ASX daily share in one burst. The job must ask before spending."""
    body = SRC[SRC.index("async def run("):]
    assert "cost_of(ENDPOINT, len(codes))" in body, "the slice is not priced"
    assert "can_spend(price" in body, "the budget is never consulted"
    # Order matters: asking after fetching is not asking.
    assert body.index("can_spend(price") < body.index("fetch_general"), (
        "the budget is consulted after the fetch loop begins")


def test_a_deferred_run_records_why_rather_than_vanishing():
    body = SRC[SRC.index("async def run("):]
    assert 'tally.excluded(code, "deferred: EODHD budget")' in body, (
        "a budget deferral leaves no per-company record, so a week of "
        "deferrals is indistinguishable from a week of success")


def test_the_slice_size_follows_the_refresh_interval():
    """One number governs both, so they cannot drift apart."""
    assert NS["REFRESH_EVERY_DAYS"] == 7
    body = SRC[SRC.index("async def run("):]
    assert "math.ceil(len(all_codes) / REFRESH_EVERY_DAYS)" in body, (
        "the slice size is a literal; changing the interval would not "
        "change how many companies are refreshed")


# ── Population and outcomes ──────────────────────────────────────────────────

def test_the_population_comes_from_the_database_not_a_list():
    """A hardcoded list cannot notice a company it omits -- eight ETFs
    served four-month-old prices inside a job reporting success daily."""
    assert "FROM market.companies" in SRC
    assert "is_current AND status = 'active'" in SRC
    tree = ast.parse(SRC)
    literals = [n for n in ast.walk(tree)
                if isinstance(n, (ast.List, ast.Tuple))
                and len(n.elts) > 20
                and all(isinstance(e, ast.Constant) and isinstance(e.value, str)
                        for e in n.elts)]
    assert not literals, "a large hardcoded code list appeared in the producer"


def test_the_oldest_profiles_are_refreshed_first():
    """NULLS FIRST: a company never profiled is the most urgent, not the
    least. It also makes a failed day self-correcting."""
    assert "ORDER BY profile_updated_at NULLS FIRST" in SRC, (
        "the slice is not ordered by staleness, so a company can be skipped "
        "for cycles while others refresh repeatedly")


def test_per_entity_outcomes_are_emitted():
    """ProducerTally computing report() and the producer discarding it is
    the v11.2.23 defect; it does not get to recur in a new producer."""
    body = SRC[SRC.index("async def run("):]
    assert "tally.report()" in body, "per-entity outcomes are never logged"
    assert "tally.degraded" in body, "the degraded state is never reported"
    assert "return tally" in body, (
        "the tally never reaches the execution boundary, so a degraded run "
        "cannot be recorded")


def test_refusal_and_emptiness_are_different_outcomes():
    """"They declined to serve us" and "they have nothing for this company"
    both yield no data and are not the same finding."""
    body = SRC[SRC.index("async def run("):]
    assert "tally.refusal(" in body and "tally.nothing_available(" in body
    assert "except SourceRefused" in body, (
        "a refusal is not distinguished from an empty response")


def test_a_served_but_entirely_empty_payload_is_not_a_success():
    """The provider answering with every mapped field empty is not data."""
    body = SRC[SRC.index("async def run("):]
    assert "if not any(v is not None for v in values.values())" in body, (
        "a payload with no usable field would be counted as obtained")


def test_the_url_is_never_logged():
    """It carries the api_token. v11.2.17 shipped because it was logged."""
    assert "type(exc).__name__" in SRC
    assert not re.search(r'log\.\w+\([^)]*\{r\.url', SRC), "a log prints the URL"
    assert not re.search(r'log\.\w+\([^)]*api_token', SRC)


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
