#!/usr/bin/env python
"""
P0 — the three features the product exists to provide
=====================================================
asxscreener.com.au has three primary surfaces. Everything else is an
add-on, and a release that breaks one of these is a release that should
never have shipped:

    1. Stock screening, in three independent modes
         /screener            Filter Screen
         /screener  (query)   SQL-like Query Mode
         /ai/nl-screener      AI Natural Language Query
    2. Market overview        /market/*
    3. Company pages          /companies/{code} and its tabs

Why this file exists
--------------------
Before it, HTTP-level coverage across 98 test files was **one admin
endpoint**. The gate was strong at units and blind at surfaces, and every
defect found on 24 Oct 2026 shared one shape: the code was correct in
isolation and wrong in COMPOSITION.

  - Query Mode was dark from v11.2.29 to v11.2.36 -- six releases, each
    gated green -- because removing a fallback in the compiler stopped
    forwarding the SQL symbols the parser emits. Both components had
    passing tests. Nothing issued a query.
  - The premium gate raised NameError for 16 days: the refusal path was
    tested, the admitting path was not.
  - nl-screener 500'd on 3 of 5 genuine attempts.

A unit test cannot catch a disagreement between two correct components.
Only a request can.

What this file proves, and what it does not
-------------------------------------------
The gate's database is a SCHEMA-ONLY clone: real tables, no rows. So these
tests assert that a request **compiles, executes and serialises** -- they
do not assert that the data is right or even present. That is the correct
division, and it is sufficient for the regression class that hurt us:
v11.2.29 produced a 422 Parse Error, not an empty result set.

Data assertions -- non-empty results, sane values -- belong in the
post-deploy smoke against production, where there are rows.

A 500 from any endpoint here is a release blocker. A 200 with no rows is
expected and fine.

Run:  python tests/test_primary_features_contract.py
      (requires fastapi, pydantic and a database; runs in the gate)
"""

import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

for _k, _v in (("DATABASE_URL", "postgresql+asyncpg://unused/unused"),
               ("DATABASE_URL_SYNC", "postgresql://unused/unused"),
               ("JWT_SECRET", "test-only-not-a-secret")):
    os.environ.setdefault(_k, _v)

#: A code that will not exist in a schema-only clone. Used where the test
#: is about the HANDLER surviving, not about the data.
ABSENT_CODE = "ZZZZ"

#: Every status that is a correct answer from a database with no rows.
#: 500 is never in this set -- that is the whole point of the file.
OK_OR_EMPTY = (200, 404)


def _client():
    """A TestClient with auth overridden to a Premium subscriber.

    The point is to exercise the ENTITLED path. Testing only that a free
    user is refused is how the premium NameError survived 16 days: the
    refusal returned early and never reached the code that was broken.
    """
    from fastapi.testclient import TestClient
    from app.main import app
    from app.core.deps import (get_current_user, get_optional_user,
                               require_query_access)

    premium = {"id": "00000000-0000-0000-0000-000000000001",
               "email": "contract-test@example.invalid",
               "plan": "premium", "status": "active", "is_admin": False}

    app.dependency_overrides[get_current_user] = lambda: premium
    app.dependency_overrides[get_optional_user] = lambda: premium
    app.dependency_overrides[require_query_access] = lambda: premium
    return TestClient(app), app


def _assert_not_500(resp, what: str):
    assert resp.status_code != 500, (
        f"{what} returned 500 — a primary feature is broken. Body: "
        f"{resp.text[:400]}")
    assert resp.status_code in OK_OR_EMPTY or resp.status_code in (422, 403), (
        f"{what} returned {resp.status_code}, which is not a documented "
        f"outcome for this request. Body: {resp.text[:400]}")


# ── 1a. Stock screening — Filter Screen ─────────────────────────────────────

def test_filter_screen_runs():
    """The default mode. Unauthenticated users reach it too."""
    client, app = _client()
    try:
        r = client.post("/api/v1/screener", json={
            "filters": [{"field": "market_cap", "operator": "gte",
                         "value": 0}],
            "sort_by": "market_cap", "sort_dir": "desc",
            "page": 1, "page_size": 10})
        assert r.status_code == 200, (
            f"the Filter Screen is broken: {r.status_code} {r.text[:400]}")
        body = r.json()
        for key in ("results", "total"):
            assert key in body, f"response is missing {key!r}: {list(body)}"
    finally:
        app.dependency_overrides.clear()


def test_filter_screen_accepts_a_boolean_filter():
    """is_reit/is_miner are booleans whose binding has broken twice:
    v11.2.29 bound the string "true" to a boolean column, and v11.2.38
    changed their type to Optional."""
    client, app = _client()
    try:
        r = client.post("/api/v1/screener", json={
            "filters": [{"field": "is_reit", "operator": "eq",
                         "value": True}],
            "page": 1, "page_size": 5})
        assert r.status_code == 200, (
            f"a boolean filter is broken: {r.status_code} {r.text[:400]}")
    finally:
        app.dependency_overrides.clear()


# ── 1b. Stock screening — Query Mode ────────────────────────────────────────

def test_query_mode_runs_the_documented_syntax():
    """THE regression that went six releases unnoticed.

    This exact shape -- SQL symbols, multi-line, AND-joined -- is what the
    UI's hint bar, its error messages and its Field Reference panel all
    advertise, and it returned "'>' is not a permitted operator" from
    v11.2.29 until v11.2.36.
    """
    client, app = _client()
    try:
        r = client.post("/api/v1/screener/query", json={
            "query": "return_1y > 0 AND\nmarket_cap > 0 AND\nis_reit = false",
            "page": 1, "page_size": 10})
        assert r.status_code == 200, (
            f"Query Mode cannot run the syntax it documents: "
            f"{r.status_code} {r.text[:400]}")
        assert "results" in r.json()
    finally:
        app.dependency_overrides.clear()


def test_query_mode_handles_every_documented_operator():
    """A per-operator sweep, so one broken symbol is named rather than
    hidden behind whichever appears first in a compound query."""
    client, app = _client()
    try:
        for expr in ("market_cap > 0", "market_cap >= 0", "market_cap < 1e12",
                     "market_cap <= 1e12", "sector = 'Materials'",
                     "sector != 'Materials'", "is_reit = true",
                     "is_reit = false"):
            r = client.post("/api/v1/screener/query",
                            json={"query": expr, "page": 1, "page_size": 5})
            assert r.status_code == 200, (
                f"Query Mode rejects {expr!r}: {r.status_code} "
                f"{r.text[:300]}")
    finally:
        app.dependency_overrides.clear()


def test_query_mode_refuses_a_bad_query_without_a_500():
    """A malformed query is the customer's typo and must come back as a
    422 naming the problem — never a 500 carrying our SQL."""
    client, app = _client()
    try:
        r = client.post("/api/v1/screener/query",
                        json={"query": "is_reit > 5", "page": 1})
        assert r.status_code == 422, (
            f"a malformed query returned {r.status_code}, not 422: "
            f"{r.text[:300]}")
        assert "detail" in r.json()
    finally:
        app.dependency_overrides.clear()


# ── 1c. Stock screening — AI Natural Language Query ─────────────────────────

def test_ai_query_runs_without_calling_the_model():
    """The parse -> validate -> compile -> execute path.

    The model is stubbed: this test must not spend money or depend on a
    third party being up. What it exercises is everything AFTER the model
    replies, which is where both known nl-screener defects lived -- the
    503 and the `could not convert string to float: 'low_52w'` 500.
    """
    import json as _json
    from unittest.mock import patch, MagicMock

    client, app = _client()

    reply = MagicMock()
    reply.content = [MagicMock(text=_json.dumps({
        "mandatory": [{"field": "market_cap", "operator": "gte",
                       "value": 0}],
        "exclusions": [], "preferred": [], "ranking": []}))]
    fake = MagicMock()
    fake.messages.create.return_value = reply

    try:
        with patch("anthropic.Anthropic", return_value=fake):
            r = client.post("/api/v1/ai/nl-screener",
                            json={"query": "large companies"})
        _assert_not_500(r, "AI Query")
    finally:
        app.dependency_overrides.clear()


def test_ai_query_survives_a_field_name_as_a_value():
    """The v11.2.35 defect, reproduced through the real endpoint.

    Asked for "stocks near their 52-week low", the model answered with a
    filter whose VALUE was a field name. It was bound to a numeric column
    and asyncpg's objection became a 500 on 3 of 5 genuine attempts.
    """
    import json as _json
    from unittest.mock import patch, MagicMock

    client, app = _client()

    reply = MagicMock()
    reply.content = [MagicMock(text=_json.dumps({
        "mandatory": [{"field": "price", "operator": "lte",
                       "value": "low_52w"}],
        "exclusions": [], "preferred": [], "ranking": []}))]
    fake = MagicMock()
    fake.messages.create.return_value = reply

    try:
        with patch("anthropic.Anthropic", return_value=fake):
            r = client.post("/api/v1/ai/nl-screener",
                            json={"query": "stocks near their 52 week low"})
        assert r.status_code != 500, (
            f"a field name used as a filter value still 500s: {r.text[:300]}")
    finally:
        app.dependency_overrides.clear()


# ── 2. Market overview ──────────────────────────────────────────────────────

def test_market_surfaces_respond():
    """Each panel separately, so one broken section is named rather than
    collapsing the whole page into a single failure."""
    client, app = _client()
    try:
        for path in ("/api/v1/market/summary", "/api/v1/market/dashboard",
                     "/api/v1/market/movers", "/api/v1/market/sectors"):
            r = client.get(path)
            _assert_not_500(r, f"Market overview {path}")
    finally:
        app.dependency_overrides.clear()


# ── 3. Company pages ────────────────────────────────────────────────────────

def test_company_surfaces_respond_for_an_absent_code():
    """With no rows, 404 is the correct answer and 500 is not.

    This is about the HANDLER surviving: that it reaches a clean
    not-found rather than raising on the way. /companies/{code} 500'd for
    805 companies in v11.2.27 because a NULL met a non-optional bool, and
    the shape of that failure was a handler raising, not a missing row.
    """
    client, app = _client()
    try:
        for suffix in ("", "/overview", "/financials", "/prices",
                       "/dividends", "/peers"):
            path = f"/api/v1/companies/{ABSENT_CODE}{suffix}"
            r = client.get(path)
            _assert_not_500(r, f"Company page {path}")
    finally:
        app.dependency_overrides.clear()


def test_company_search_survives_unknown_flags():
    """The most frequent error on the site: 136 failures of
    /companies/search, nobody reported it."""
    client, app = _client()
    try:
        r = client.get("/api/v1/companies/search", params={"q": "A"})
        assert r.status_code == 200, (
            f"company search is broken: {r.status_code} {r.text[:300]}")
        assert isinstance(r.json(), list)
    finally:
        app.dependency_overrides.clear()


# ── The premise ─────────────────────────────────────────────────────────────

def test_the_entitled_path_is_what_is_being_exercised():
    """Guards the override itself.

    If the overrides stop applying, every test above would exercise an
    unauthenticated refusal and pass while proving nothing -- which is
    precisely how the premium NameError survived 16 days.
    """
    client, app = _client()
    try:
        r = client.post("/api/v1/screener/query",
                        json={"query": "market_cap > 0", "page": 1})
        assert r.status_code != 401, (
            "the auth override is not applying; these tests are exercising "
            "the refusal path, not the entitled one, and prove nothing")
        assert r.status_code != 403, (
            "the override user is not entitled to Query Mode; fix the "
            "fixture or these tests prove nothing")
    finally:
        app.dependency_overrides.clear()


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
