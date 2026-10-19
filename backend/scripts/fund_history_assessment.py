#!/usr/bin/env python
"""
Does stored fund history still say what the provider says?
==========================================================
READ-ONLY. No writes, no DDL, every query in a read-only transaction, and
the api_token is never printed.

Why this is NOT the index script pointed at funds
-------------------------------------------------
`eodhd_index_discovery.py` targets index codes, draws candidates from
EODHD's INDX exchange, and compares against `market.index_prices`. Funds are
ASX-listed securities on the AU exchange with a different symbol format and
a different table. It produced no evidence about funds and cannot.

The harder difference: for indices, any disagreement with the provider is a
defect. For funds it is not.

    `market.fund_prices.close_price` is neither raw nor adjusted. It is
    ADJUSTED AS OF WHATEVER DATE EACH ROW WAS FETCHED, because yfinance's
    auto_adjust restates history retroactively every time a distribution is
    paid, while append-only persistence freezes each row at its fetch-time
    basis.

So a one-year-old row for a 4%-yielding ETF is expected to sit a few percent
away from today's adjusted value, with no defect anywhere. Reusing the index
rule here would flag all 55 funds and mean nothing.

Two causes, two signatures
--------------------------
    ADJUSTMENT DRIFT   smooth, monotonic, grows with age, dividend-sized.
                       The ratio stored/current declines steadily going back
                       in time. Expected, documented, not a defect.

    WRONG SERIES       a STEP. Agreement either side of a boundary and a
                       large constant ratio inside it, or magnitudes that no
                       distribution could explain. This is what was found in
                       three indices: a bounded window holding another
                       security entirely.

This script reports both and classifies neither automatically. A monotone
drift of 0.3%/year is one story; a 46% step is another; and something in
between is a question for a person, not a threshold invented here.

What it establishes
-------------------
1. COVERAGE  — does EODHD serve each configured fund at all, with how much
   history and how recent. That is the open question blocking any fund
   source migration, and it is answered per fund, never in aggregate.
2. SHAPE     — per fund, monthly median agreement between stored closes and
   EODHD's current values, so drift and steps are distinguishable by eye.

What it does NOT establish
--------------------------
Which side is correct. Both are derived series; neither is the index's
published level. It compares two accounts of the same thing and shows where
they stop agreeing.

Usage (on the server, where the key and the database are):
    PYTHONPATH=/opt/asx-screener/backend \\
      /opt/asx-screener/asx-venv/bin/python backend/scripts/fund_history_assessment.py
    ... --days 2000      how much history to compare
    ... --codes VAS,STW  limit to specific funds (fewer provider calls)
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

_HERE = Path(__file__).resolve().parents[1]
BACKEND = _HERE if (_HERE / "app" / "core" / "config.py").exists() else Path.cwd()
if not (BACKEND / "app" / "core" / "config.py").exists():
    sys.exit(f"run this from the backend directory (looked in {BACKEND})")
sys.path.insert(0, str(BACKEND))

REQUESTS = [0]

#: A session where the two disagree by more than this is not a rounding
#: difference. Distributions move a price by a few percent at most, so this
#: is generous to the drift explanation on purpose.
STEP_PCT = 5.0


def _key() -> str:
    from app.core.config import settings
    key = settings.EODHD_API_KEY
    if not key:
        sys.exit("EODHD_API_KEY is not set")
    return key


def fetch_closes(key: str, symbol: str, days: int) -> tuple[dict, str]:
    """({date: close}, status). Status only — a URL carries the token."""
    import httpx
    REQUESTS[0] += 1
    start = date.today() - timedelta(days=days)
    try:
        r = httpx.get(f"https://eodhd.com/api/eod/{symbol}",
                      params={"api_token": key, "fmt": "json", "order": "a",
                              "from": start.isoformat(),
                              "to": date.today().isoformat()},
                      timeout=30)
    except Exception as exc:                                   # noqa: BLE001
        return {}, f"fetch failed ({type(exc).__name__})"
    if r.status_code in (429, 402, 403):
        return {}, f"REFUSED HTTP {r.status_code}"
    if r.status_code == 404:
        return {}, "NOT COVERED (404)"
    if r.status_code != 200:
        return {}, f"HTTP {r.status_code}"
    out = {}
    for row in (r.json() or []):
        try:
            out[date.fromisoformat(row["date"])] = float(row["close"])
        except (KeyError, TypeError, ValueError):
            continue
    return (out, "ok") if out else ({}, "EMPTY RESPONSE")


async def stored(days: int, codes: list[str] | None):
    """What we publish, per fund. Read-only."""
    from sqlalchemy import text
    from app.db.session import AsyncSessionLocal

    start = date.today() - timedelta(days=days)
    sql = """SELECT asx_code, price_date, close_price
               FROM market.fund_prices
              WHERE price_date >= :start AND close_price IS NOT NULL"""
    params = {"start": start}
    if codes:
        sql += " AND asx_code = ANY(:codes)"
        params["codes"] = codes

    out: dict[str, dict] = {}
    async with AsyncSessionLocal() as db:
        await db.execute(text("SET TRANSACTION READ ONLY"))
        for r in (await db.execute(text(sql), params)).mappings().all():
            out.setdefault(r["asx_code"], {})[r["price_date"]] = float(
                r["close_price"])
    return out


def _median(xs):
    if not xs:
        return float("inf")
    s = sorted(xs)
    m = len(s) // 2
    return s[m] if len(s) % 2 else (s[m - 1] + s[m]) / 2


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=2000)
    ap.add_argument("--codes", default=None)
    args = ap.parse_args()

    codes = [c.strip().upper() for c in args.codes.split(",")] if args.codes else None
    key = _key()

    from compute.engine.fund_prices import FUNDS
    configured = [f["asx_code"] for f in FUNDS]
    if codes:
        configured = [c for c in configured if c in codes]

    ours = asyncio.run(stored(args.days, configured))

    print(f"{len(configured)} funds configured; comparing {args.days} days\n")
    print("=" * 78)
    print("COVERAGE — does EODHD serve this fund at all?")
    print("=" * 78)

    theirs: dict[str, dict] = {}
    not_covered = []
    for code in configured:
        symbol = f"{code}.AU"
        closes, status = fetch_closes(key, symbol, args.days)
        mine = ours.get(code, {})
        if closes:
            theirs[code] = closes
            print(f"  {code:8} {symbol:12} {len(closes):5} rows  "
                  f"last={max(closes)}   stored={len(mine):5} rows "
                  f"last={max(mine) if mine else None}")
        else:
            not_covered.append((code, status))
            print(f"  {code:8} {symbol:12} {status}   "
                  f"stored={len(mine)} rows")

    print(f"\n  EODHD requests: {REQUESTS[0]}")
    print(f"  served: {len(theirs)}/{len(configured)}")
    if not_covered:
        print("  NOT SERVED — a fund migration cannot include these:")
        for code, status in not_covered:
            print(f"    {code:8} {status}")

    print("\n" + "=" * 78)
    print("SHAPE — drift or step?")
    print("=" * 78)
    print("  Drift: smooth, grows with age, dividend-sized. EXPECTED —")
    print("    stored closes are adjusted as of their fetch date.")
    print(f"  Step: agreement either side of a boundary, >{STEP_PCT}% inside.")
    print("    That is the pattern found in three indices.\n")

    for code in configured:
        mine, their = ours.get(code, {}), theirs.get(code, {})
        shared = sorted(set(mine) & set(their))
        if len(shared) < 20:
            print(f"{code:8} too few shared sessions ({len(shared)}) — "
                  f"CANNOT ASSESS")
            continue
        buckets = defaultdict(list)
        for d in shared:
            if mine[d]:
                buckets[d.strftime("%Y-%m")].append(
                    (their[d] - mine[d]) / mine[d] * 100)   # SIGNED
        months = sorted(buckets)
        meds = [_median(buckets[m]) for m in months]
        steps = sum(1 for v in meds if abs(v) > STEP_PCT)
        overall = _median([abs(v) for v in meds])

        flag = ""
        if steps:
            flag = f"  <-- {steps} month(s) beyond {STEP_PCT}%"
        print(f"\n{code:8} shared={len(shared):5} [{shared[0]} .. {shared[-1]}]"
              f"  median|diff| across months={overall:7.3f}%{flag}")
        # Signed and oldest-first: drift reads as a trend, a step as a jump.
        for m, v in zip(months, meds):
            mark = " *" if abs(v) > STEP_PCT else ""
            print(f"    {m}  n={len(buckets[m]):3}  med={v:+9.4f}%{mark}")

    print("\n" + "=" * 78)
    print("Neither side here is the fund's published NAV. This compares two")
    print("derived accounts and shows where they stop agreeing. Classifying")
    print("a borderline case is a judgement, not a threshold.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
