#!/usr/bin/env python3
"""
Post-deploy smoke — the three primary features, against real data
=================================================================
Layer 2 of four. The contract suite (layer 1) proves a request COMPILES,
EXECUTES and SERIALISES against a schema-only clone. It cannot prove the
answer contains anything, because the clone has no rows.

This proves the rest: that the screener returns stocks, that the market
page has numbers in it, and that a company page renders for a company that
actually exists. Run against the deployed process, immediately after
deploy, so a release that breaks a primary feature fails loudly instead of
succeeding quietly.

Why both layers exist
---------------------
v11.2.29 broke Query Mode with a 422 -- layer 1 catches that class. But a
release that leaves every endpoint answering 200 with an EMPTY body is
equally broken to a customer and invisible to layer 1. The market
dashboard's "snapshot not yet available" 503 is accepted in the contract
suite precisely because it is rejected here.

Coverage, stated rather than implied
------------------------------------
Query Mode and AI Query require a Pro/Premium token. Without one they
answer 401, which proves the route and the auth layer exist and proves
NOTHING about the feature. So:

  SMOKE_TOKEN set    -> all three screener modes are exercised
  SMOKE_TOKEN unset  -> they are reported SKIPPED, by name, and the exit
                        status still reflects what actually ran

A smoke that silently tested two thirds of the thing and printed a green
tick would be worse than no smoke, because it reads as full coverage. A
scoped verdict carries its scope.

Read-only: every call is a GET or a screener POST. Nothing is written.

Usage:
    python3 smoke_primary_features.py [--base http://localhost:8000]
    SMOKE_TOKEN=<jwt> python3 smoke_primary_features.py
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = "http://localhost:8000"
TIMEOUT = 30

results = []          # (ok|skip|fail, name, detail)


def record(status, name, detail=""):
    results.append((status, name, detail))
    mark = {"ok": "  ok  ", "fail": " FAIL ", "skip": " skip "}[status]
    print(f"{mark} {name}" + (f"\n        {detail}" if detail else ""))


def call(method, path, body=None, token=None):
    """(status_code, parsed_json_or_text). Never raises on an HTTP error."""
    url = f"{BASE}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            raw = r.read().decode("utf-8", "replace")
            try:
                return r.status, json.loads(raw)
            except ValueError:
                return r.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, raw
    except Exception as exc:                                   # noqa: BLE001
        return 0, f"{type(exc).__name__}: {exc}"


# ── 1. Stock screening ──────────────────────────────────────────────────────

def smoke_filter_screen():
    """Must return STOCKS, not merely a well-formed empty page."""
    code, body = call("POST", "/api/v1/screener", {
        "filters": [{"field": "market_cap", "operator": "gte", "value": 0}],
        "sort_by": "market_cap", "sort_dir": "desc",
        "page": 1, "page_size": 10})
    if code != 200:
        return record("fail", "Filter Screen", f"HTTP {code}: {str(body)[:200]}")
    rows = (body or {}).get("data") or []
    total = (body or {}).get("total") or 0
    if not rows:
        return record("fail", "Filter Screen",
                      f"200 with an EMPTY page (total={total}). The screen "
                      f"works and the product does not.")
    if not rows[0].get("asx_code"):
        return record("fail", "Filter Screen", "rows carry no asx_code")
    record("ok", "Filter Screen", f"{len(rows)} rows, total={total}")
    return rows[0]["asx_code"]


def _rejected(code: int) -> str:
    """A token the API refused, said plainly.

    A JWT expires. Reported as a bare "HTTP 401" this reads like the feature
    is broken, and the quickest way to make the deploy green again is to
    delete SMOKE_TOKEN -- which silently restores the blindness it was added
    to remove. Naming the cause is what stops that.
    """
    return (f"SMOKE_TOKEN was REJECTED (HTTP {code}). The token is expired, "
            f"revoked, or belongs to an account below Pro. The feature itself "
            f"is NOT verified either way. Re-mint the token; do not unset it.")


def smoke_query_mode(token):
    if not token:
        return record("skip", "Query Mode",
                      "no token could be minted (JWT_SECRET unreadable) and "
                      "none supplied. NOT verified by this run.")
    code, body = call("POST", "/api/v1/screener/query",
                      {"query": "market_cap > 0", "page": 1, "page_size": 10},
                      token=token)
    if code in (401, 403):
        return record("fail", "Query Mode", _rejected(code))
    if code != 200:
        return record("fail", "Query Mode", f"HTTP {code}: {str(body)[:200]}")
    rows = (body or {}).get("data") or []
    if not rows:
        return record("fail", "Query Mode", "200 with an EMPTY page")
    record("ok", "Query Mode", f"{len(rows)} rows")


def smoke_ai_query(token):
    # Opt-in, unlike Query Mode. This endpoint calls the Anthropic API, so
    # verifying it spends money on every deploy and makes the deploy depend
    # on a third party: a rate limit or key problem would fail a release for
    # a reason that has nothing to do with the code being released. An
    # instrument must not consume the resources of the system it observes.
    #
    # Skipped loudly either way -- the run names what it did not verify.
    if not _truthy(_env_value("SMOKE_AI")):
        return record("skip", "AI Query",
                      "SMOKE_AI not set — this check calls the Anthropic API "
                      "and costs money per run. NOT verified by this run.")
    if not token:
        return record("skip", "AI Query",
                      "no token could be minted or supplied. "
                      "NOT verified by this run.")
    code, body = call("POST", "/api/v1/ai/nl-screener",
                      {"query": "mining companies with a dividend yield "
                                "above 4 percent"}, token=token)
    if code in (401, 403):
        return record("fail", "AI Query", _rejected(code))
    if code != 200:
        return record("fail", "AI Query", f"HTTP {code}: {str(body)[:200]}")
    rows = (body or {}).get("data")
    if rows is None:
        return record("fail", "AI Query",
                      f"200 but no data field: {str(body)[:200]}")
    record("ok", "AI Query", f"{len(rows)} rows")


# ── 2. Market overview ──────────────────────────────────────────────────────

def smoke_market():
    """A 'snapshot not yet available' 503 is accepted by the contract suite
    and rejected here: in production the snapshot must exist."""
    for path in ("/api/v1/market/summary", "/api/v1/market/dashboard",
                 "/api/v1/market/movers", "/api/v1/market/sectors"):
        code, body = call("GET", path)
        name = f"Market {path.rsplit('/', 1)[-1]}"
        if code != 200:
            record("fail", name, f"HTTP {code}: {str(body)[:200]}")
            continue
        if not body or (isinstance(body, dict) and not any(
                v not in (None, [], {}, 0) for v in body.values())):
            record("fail", name, "200 with nothing in it")
            continue
        record("ok", name)


# ── 3. Company pages ────────────────────────────────────────────────────────

def smoke_company(code_from_screener):
    """Uses a code the screener just returned, rather than a hardcoded one.

    A hardcoded ticker eventually delists, and the smoke then fails for a
    reason that has nothing to do with the release.
    """
    if not code_from_screener:
        return record("fail", "Company page",
                      "no code available — the Filter Screen returned none")
    asx = code_from_screener
    code, body = call("GET", f"/api/v1/companies/{asx}")
    if code != 200:
        return record("fail", f"Company {asx}", f"HTTP {code}: {str(body)[:200]}")
    if not (body or {}).get("company_name"):
        return record("fail", f"Company {asx}", "200 with no company_name")
    record("ok", f"Company {asx} detail", (body or {}).get("company_name", ""))

    # The tabs that answer 200 for an ABSENT company, so status alone proves
    # nothing: they must carry content for a real one.
    for suffix in ("/overview", "/financials", "/prices", "/dividends"):
        c, b = call("GET", f"/api/v1/companies/{asx}{suffix}")
        name = f"Company {asx}{suffix}"
        if c != 200:
            record("fail", name, f"HTTP {c}: {str(b)[:160]}")
        elif not b or (isinstance(b, dict) and not any(
                v not in (None, [], {}, 0) for v in b.values())):
            record("fail", name, "200 with nothing in it")
        else:
            record("ok", name)

    code, body = call("GET", f"/api/v1/companies/search?q={asx[:2]}")
    if code != 200 or not isinstance(body, list) or not body:
        record("fail", "Company search", f"HTTP {code}: {str(body)[:160]}")
    else:
        record("ok", "Company search", f"{len(body)} matches")


#: A synthetic identity for the smoke's own token. Deliberately not a real
#: account: _resolve_user decodes the JWT and never queries the database
#: ("Does NOT hit the DB -- trusts the signed JWT payload"), so no user row is
#: needed, nothing is created, and no customer's data is touched. The email is
#: in .invalid, which RFC 2606 reserves precisely so it can never resolve.
SMOKE_SUBJECT = "00000000-0000-0000-0000-000000000001"
SMOKE_EMAIL   = "post-deploy-smoke@asxscreener.invalid"
SMOKE_PLAN    = "premium"
SMOKE_TTL_MIN = 5


def _truthy(value) -> bool:
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


def _env_value(key: str):
    """A key from the environment, else from the project's .env.

    deploy.sh runs this as a subprocess and does not export backend/.env, so
    anything placed there is invisible to os.environ. Resolved here, at the
    execution boundary, rather than depending on the caller's shell.
    """
    value = os.environ.get(key, "").strip()
    if value:
        return value
    env = Path(__file__).resolve().parents[1] / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith(f"{key}=") and not line.startswith("#"):
                return line.partition("=")[2].strip().strip("'\"") or None
    return None


def _smoke_token():
    """A Pro/Premium token for this run, minted here or supplied.

    Minted rather than stored, because access tokens live 15 minutes
    (ACCESS_TOKEN_EXPIRE_MINUTES). A token pasted into .env would be rejected
    the same afternoon and every deploy after it, and the quickest way to a
    green deploy would be to remove it -- restoring exactly the blindness this
    exists to remove.

    Nothing new is exposed: JWT_SECRET is already on this host, and anyone
    able to run this script can already read it.

    SMOKE_TOKEN still wins when set, for a host that wants to pin a specific
    identity.
    """
    supplied = _env_value("SMOKE_TOKEN")
    if supplied:
        return supplied

    secret = _env_value("JWT_SECRET")
    if not secret:
        return None
    try:
        import jwt as pyjwt
    except ImportError:
        try:
            from jose import jwt as pyjwt           # the API's own library
        except ImportError:
            return None

    now = datetime.now(timezone.utc)
    return pyjwt.encode(
        {"sub": SMOKE_SUBJECT, "email": SMOKE_EMAIL, "plan": SMOKE_PLAN,
         "status": "active", "iat": now,
         "exp": now + timedelta(minutes=SMOKE_TTL_MIN), "type": "access"},
        secret,
        algorithm=_env_value("JWT_ALGORITHM") or "HS256")


def main() -> int:
    global BASE
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=BASE)
    args = ap.parse_args()
    BASE = args.base.rstrip("/")

    token = _smoke_token()

    print(f"smoke: {BASE}")
    print(f"smoke: authenticated modes "
          f"{'ENABLED' if token else 'SKIPPED (no token)'}"
          f"{'' if _truthy(_env_value('SMOKE_AI')) else '  (AI Query opt-in: set SMOKE_AI=1)'}")
    print()

    code, health = call("GET", "/health")
    if code != 200:
        record("fail", "health", f"HTTP {code}: {str(health)[:200]}")
    else:
        record("ok", "health", f"version={(health or {}).get('version')}")

    first_code = smoke_filter_screen()
    smoke_query_mode(token)
    smoke_ai_query(token)
    smoke_market()
    smoke_company(first_code if isinstance(first_code, str) else None)

    failed = [r for r in results if r[0] == "fail"]
    skipped = [r for r in results if r[0] == "skip"]
    passed = [r for r in results if r[0] == "ok"]

    print()
    print(f"smoke: {len(passed)} ok, {len(failed)} failed, "
          f"{len(skipped)} skipped")
    if skipped:
        print("smoke: NOT VERIFIED by this run — " +
              ", ".join(r[1] for r in skipped))
    if failed:
        print("smoke: a PRIMARY FEATURE is not working in production:")
        for _, name, detail in failed:
            print(f"    {name}: {detail}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
