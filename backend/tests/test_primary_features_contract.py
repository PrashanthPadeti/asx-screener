#!/usr/bin/env python
"""
P0 — the three features the product exists to provide
=====================================================
asxscreener.com.au has three primary surfaces. Everything else is an
add-on, and a release that breaks one of these should never ship:

    1. Stock screening, in three independent modes
         /screener            Filter Screen
         /screener/query      SQL-like Query Mode
         /ai/nl-screener      AI Natural Language Query
    2. Market overview        /market/*
    3. Company pages          /companies/{code} and its tabs

Why this file exists
--------------------
Before it, HTTP-level coverage across 98 test files was ONE admin
endpoint. The gate was strong at units and blind at surfaces, and every
defect found on 24 Oct 2026 shared a shape: correct in isolation, wrong in
COMPOSITION.

  - Query Mode was dark from v11.2.29 to v11.2.36 -- six releases, each
    gated green -- because the compiler stopped forwarding the SQL symbols
    the parser emits. Both components had passing tests. Nothing issued a
    query.
  - The premium gate raised NameError for 16 days: the refusal path was
    tested, the admitting path was not.
  - nl-screener 500'd on 3 of 5 genuine attempts.

A unit test cannot catch a disagreement between two correct components.
Only a request can.

What this proves, and what it does not
--------------------------------------
Against the gate's SCHEMA-ONLY clone these assert that a request compiles,
executes and serialises -- not that the data is right or present. That is
the correct division and it is sufficient for the class that hurt us:
v11.2.29 produced a 422, not an empty result. Data assertions belong in
the post-deploy smoke, where there are rows.

A 500 from any endpoint here is a release blocker. A 200 with no rows is
expected.

Run:  python tests/test_primary_features_contract.py
      (requires fastapi, pydantic and a reachable database)
"""

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

for _k, _v in (("DATABASE_URL", "postgresql+asyncpg://unused/unused"),
               ("DATABASE_URL_SYNC", "postgresql://unused/unused"),
               ("JWT_SECRET", "test-only-not-a-secret")):
    os.environ.setdefault(_k, _v)

#: A code that will not exist in a schema-only clone. Used where the test is
#: about the HANDLER surviving, not about the data.
ABSENT_CODE = "ZZZZ"

#: Correct answers from a database with no rows. 500 is never among them.
OK_OR_EMPTY = (200, 404)

_CLIENT = None


def _client():
    """ONE client for the whole module, and therefore one event loop.

    The first version built a fresh TestClient per test. Each runs its own
    event loop, while the app's async engine pools connections bound to the
    loop that opened them -- so the second test inherited a connection from
    a closed loop and failed with

        RuntimeError: Event loop is closed
        Future ... attached to a different loop

    Nine tests reported nine broken primary features; the fault was one
    shared engine and nothing to do with the product.

    Lifespan is deliberately NOT run (no `with`): startup registers the 18
    scheduler jobs, and a suite must not start the production scheduler to
    ask whether a screen compiles.

    Auth is overridden to a Premium subscriber because the point is to
    exercise the ENTITLED path. Testing only that a free user is refused is
    how the premium NameError survived 16 days -- the refusal returned
    early and never reached the broken code.
    """
    global _CLIENT
    if _CLIENT is not None:
        return _CLIENT

    from fastapi.testclient import TestClient
    from sqlalchemy.ext.asyncio import (AsyncSession, async_sessionmaker,
                                        create_async_engine)
    from sqlalchemy.pool import NullPool
    from app.main import app
    from app.db.session import get_db
    from app.core.deps import (get_current_user, get_optional_user,
                               require_query_access)

    # A NullPool engine, because TestClient opens a NEW event loop for every
    # request when it is not used as a context manager. The application
    # engine pools connections (pool_size=5), and a pooled connection created
    # on one loop and reused on the next fails with
    #
    #     RuntimeError: Event loop is closed
    #     Future ... attached to a different loop
    #
    # which presented as nine broken primary features and was the pool.
    # NullPool opens and closes a connection per checkout, so nothing
    # survives a loop. Sharing one TestClient does NOT fix this on its own --
    # the portal, and the loop, are still per-request.
    #
    # Using `with TestClient(app)` would pin one loop, but it also runs
    # lifespan: that registers the 18 scheduler jobs, and a test must not
    # start the production scheduler to ask whether a screen compiles.
    test_engine = create_async_engine(os.environ["DATABASE_URL"],
                                      poolclass=NullPool)
    test_sessions = async_sessionmaker(test_engine, class_=AsyncSession,
                                       expire_on_commit=False)

    async def _db():
        async with test_sessions() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _db

    premium = {"id": "00000000-0000-0000-0000-000000000001",
               "email": "contract-test@example.invalid",
               "plan": "premium", "status": "active", "is_admin": False}
    app.dependency_overrides[get_current_user] = lambda: premium
    app.dependency_overrides[get_optional_user] = lambda: premium
    app.dependency_overrides[require_query_access] = lambda: premium

    _CLIENT = TestClient(app)
    return _CLIENT


def _assert_not_500(resp, what: str):
    assert resp.status_code != 500, (
        f"{what} returned 500 — a primary feature is broken. Body: "
        f"{resp.text[:400]}")
    assert resp.status_code in OK_OR_EMPTY or resp.status_code in (422, 403), (
        f"{what} returned {resp.status_code}, not a documented outcome. "
        f"Body: {resp.text[:400]}")


def _stub_model(payload: dict):
    """An Anthropic client that returns `payload` without a network call.

    The suite must not spend money or depend on a third party being up.
    What it exercises is everything AFTER the model replies, which is where
    both known nl-screener defects lived.
    """
    reply = MagicMock()
    reply.content = [MagicMock(text=json.dumps(payload))]
    fake = MagicMock()
    fake.messages.create.return_value = reply
    return fake


# ── 1a. Stock screening — Filter Screen ─────────────────────────────────────

def test_filter_screen_runs():
    r = _client().post("/api/v1/screener", json={
        "filters": [{"field": "market_cap", "operator": "gte", "value": 0}],
        "sort_by": "market_cap", "sort_dir": "desc",
        "page": 1, "page_size": 10})
    assert r.status_code == 200, (
        f"the Filter Screen is broken: {r.status_code} {r.text[:400]}")
    body = r.json()
    for key in ("results", "total"):
        assert key in body, f"response is missing {key!r}: {list(body)}"


def test_filter_screen_accepts_a_boolean_filter():
    """is_reit/is_miner binding has broken twice: v11.2.29 bound the string
    "true" to a boolean column, and v11.2.38 made them Optional."""
    r = _client().post("/api/v1/screener", json={
        "filters": [{"field": "is_reit", "operator": "eq", "value": True}],
        "page": 1, "page_size": 5})
    assert r.status_code == 200, (
        f"a boolean filter is broken: {r.status_code} {r.text[:400]}")


# ── 1b. Stock screening — Query Mode ────────────────────────────────────────

def test_query_mode_runs_the_documented_syntax():
    """THE regression that went six releases unnoticed.

    SQL symbols, multi-line, AND-joined -- the shape the UI's hint bar, its
    error messages and its Field Reference panel all advertise. It returned
    "'>' is not a permitted operator" from v11.2.29 until v11.2.36.
    """
    r = _client().post("/api/v1/screener/query", json={
        "query": "return_1y > 0 AND\nmarket_cap > 0 AND\nis_reit = false",
        "page": 1, "page_size": 10})
    assert r.status_code == 200, (
        f"Query Mode cannot run the syntax it documents: {r.status_code} "
        f"{r.text[:400]}")
    assert "results" in r.json()


def test_query_mode_handles_every_documented_operator():
    """Per-operator, so one broken symbol is named rather than hidden
    behind whichever appears first in a compound query."""
    for expr in ("market_cap > 0", "market_cap >= 0", "market_cap < 1e12",
                 "market_cap <= 1e12", "sector = 'Materials'",
                 "sector != 'Materials'", "is_reit = true",
                 "is_reit = false"):
        r = _client().post("/api/v1/screener/query",
                           json={"query": expr, "page": 1, "page_size": 5})
        assert r.status_code == 200, (
            f"Query Mode rejects {expr!r}: {r.status_code} {r.text[:300]}")


def test_query_mode_refuses_a_bad_query_without_a_500():
    """A malformed query is usually a typo and must come back as a 422
    naming the problem — never a 500 carrying our SQL."""
    r = _client().post("/api/v1/screener/query",
                       json={"query": "is_reit > 5", "page": 1})
    assert r.status_code == 422, (
        f"a malformed query returned {r.status_code}, not 422: {r.text[:300]}")
    assert "detail" in r.json()


# ── 1c. Stock screening — AI Natural Language Query ─────────────────────────

def test_ai_query_runs_without_calling_the_model():
    """The parse -> validate -> compile -> execute path."""
    fake = _stub_model({"mandatory": [{"field": "market_cap",
                                       "operator": "gte", "value": 0}],
                        "exclusions": [], "preferred": [], "ranking": []})
    with patch("anthropic.Anthropic", return_value=fake):
        r = _client().post("/api/v1/ai/nl-screener",
                           json={"query": "large companies"})
    _assert_not_500(r, "AI Query")


def test_ai_query_survives_a_field_name_as_a_value():
    """The v11.2.35 defect, through the real endpoint.

    Asked for "stocks near their 52-week low", the model answered with a
    filter whose VALUE was a field name. Bound to a numeric column,
    asyncpg's objection became a 500 on 3 of 5 genuine attempts.
    """
    fake = _stub_model({"mandatory": [{"field": "price", "operator": "lte",
                                       "value": "low_52w"}],
                        "exclusions": [], "preferred": [], "ranking": []})
    with patch("anthropic.Anthropic", return_value=fake):
        r = _client().post("/api/v1/ai/nl-screener",
                           json={"query": "stocks near their 52 week low"})
    assert r.status_code != 500, (
        f"a field name used as a filter value still 500s: {r.text[:300]}")


# ── 2. Market overview ──────────────────────────────────────────────────────

def test_market_surfaces_respond():
    """Each panel separately, so one broken section is named rather than
    collapsing the whole page into a single failure."""
    for path in ("/api/v1/market/summary", "/api/v1/market/dashboard",
                 "/api/v1/market/movers", "/api/v1/market/sectors"):
        _assert_not_500(_client().get(path), f"Market overview {path}")


# ── 3. Company pages ────────────────────────────────────────────────────────

def test_company_surfaces_respond_for_an_absent_code():
    """With no rows, 404 is correct and 500 is not.

    This is about the HANDLER reaching a clean not-found rather than
    raising on the way: /companies/{code} 500'd for 805 companies in
    v11.2.27 because a NULL met a non-optional bool.
    """
    for suffix in ("", "/overview", "/financials", "/prices", "/dividends",
                   "/peers"):
        path = f"/api/v1/companies/{ABSENT_CODE}{suffix}"
        _assert_not_500(_client().get(path), f"Company page {path}")


def test_company_search_survives_unknown_flags():
    """The most frequent error on the site: 136 failures of
    /companies/search, and nobody reported it."""
    r = _client().get("/api/v1/companies/search", params={"q": "A"})
    assert r.status_code == 200, (
        f"company search is broken: {r.status_code} {r.text[:300]}")
    assert isinstance(r.json(), list)


# ── The premise ─────────────────────────────────────────────────────────────

def test_the_entitled_path_is_what_is_being_exercised():
    """Guards the override itself.

    If it stops applying, every test above exercises an unauthenticated
    refusal and passes while proving nothing -- precisely how the premium
    NameError survived 16 days.
    """
    r = _client().post("/api/v1/screener/query",
                       json={"query": "market_cap > 0", "page": 1})
    assert r.status_code != 401, (
        "the auth override is not applying; these tests are exercising the "
        "refusal path, not the entitled one, and prove nothing")
    assert r.status_code != 403, (
        "the override user is not entitled to Query Mode; fix the fixture "
        "or these tests prove nothing")


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
