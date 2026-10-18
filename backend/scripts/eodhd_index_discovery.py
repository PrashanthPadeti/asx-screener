#!/usr/bin/env python
"""
Which EODHD symbol IS each index? Let the data answer.
======================================================
READ-ONLY. Writes nothing to the database and nothing to disk. Every query
runs in a read-only transaction.

Why this exists
---------------
v11.2.21 moved ASX100 to EODHD and proved the switch MECHANISM works:
forward-only writes, an explicit effective date, no historical overwrite.
It did not prove that any other mapping is correct, and a symbol that
returns data is not a symbol that returns the intended index.

That distinction has already cost us once. `AXJO` was mapped to Yahoo's
`^AXJO` under a comment calling it the accumulation series. `^AXJO` is the
price-only series, so a surface advertised as total-return was served price
data for months. The symbol worked. It was the wrong series.

So this script does not test mappings I chose. It inverts the problem:

  1. Ask EODHD for every index it lists, and keep the Australian ones.
  2. Fetch recent daily closes for each candidate -- once.
  3. For each of our index codes, compare every candidate against the
     closes ALREADY STORED for that code on the dates they share.
  4. Rank by agreement.

A candidate that is the same series agrees to ~0.00% on every shared date.
A candidate that is a different index does not. The stored history is the
reference because it is what the site has been publishing, so a symbol that
matches it continues the same series rather than silently substituting
another one.

What this CANNOT establish
--------------------------
That the stored series was ever the right index to begin with. If a code has
been publishing the wrong series all along, a perfect match here reproduces
that error faithfully. It answers "does this symbol continue what we have",
not "is what we have correct". AXJO is the known instance and stays
excluded; for the rest, agreement with a long stored history plus a name
that matches is the available evidence, and it is worth saying plainly that
it is evidence and not proof.

Usage (on the server, where the key and the database are):
    /opt/asx-screener/asx-venv/bin/python backend/scripts/eodhd_index_discovery.py
    ... --days 120        how much recent history to compare
    ... --symbol FOO.INDX test one specific symbol against every code
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from datetime import date, timedelta
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

#: The eight still on Yahoo, plus ASX100 as a CONTROL -- it is already on
#: EODHD via ATOI.INDX, so its known-correct mapping must come out on top. If
#: the control does not rank first for ASX100, the method is not working and
#: nothing else it reports should be believed.
TARGETS = ("ASX20", "ASX50", "ASX100", "ASX200", "ASX300",
           "AXFJ", "AXMJ", "AXEJ", "AXHJ")

#: Excluded deliberately: provenance unverified. See
#: docs/finding_2026-10-09_axjo_accumulation_is_price_series.md
EXCLUDED = ("AXJO",)

AUSTRALIAN = re.compile(
    r"\b(asx|australia|australian|s&p/asx|all ordinaries)\b", re.I)


def _key() -> str:
    from app.core.config import settings
    key = settings.EODHD_API_KEY
    if not key:
        sys.exit("EODHD_API_KEY is not set")
    return key


def list_candidates(key: str) -> list[dict]:
    """Every index EODHD lists, filtered to the Australian ones."""
    import httpx
    r = httpx.get("https://eodhd.com/api/exchange-symbol-list/INDX",
                  params={"api_token": key, "fmt": "json"}, timeout=60)
    if r.status_code != 200:
        # Status only. An exception's text can carry the URL, and the URL
        # carries the api_token.
        sys.exit(f"EODHD symbol list: HTTP {r.status_code}")
    rows = r.json() or []
    out = [x for x in rows
           if AUSTRALIAN.search(f"{x.get('Name','')} {x.get('Code','')}")]
    print(f"EODHD lists {len(rows)} indices; {len(out)} look Australian\n")
    return out


def fetch_closes(key: str, symbol: str, days: int) -> dict[date, float]:
    """{price_date: close} for one symbol. Empty dict on any refusal."""
    import httpx
    start = date.today() - timedelta(days=days)
    try:
        r = httpx.get(f"https://eodhd.com/api/eod/{symbol}",
                      params={"api_token": key, "fmt": "json", "order": "a",
                              "from": start.isoformat(),
                              "to": date.today().isoformat()},
                      timeout=30)
    except Exception as exc:                                   # noqa: BLE001
        print(f"    {symbol}: fetch failed ({type(exc).__name__})")
        return {}
    if r.status_code != 200:
        print(f"    {symbol}: HTTP {r.status_code}")
        return {}
    out = {}
    for row in (r.json() or []):
        try:
            out[date.fromisoformat(row["date"])] = float(row["close"])
        except (KeyError, TypeError, ValueError):
            continue
    return out


async def stored_closes(days: int) -> dict[str, dict[date, float]]:
    """What we have been publishing, per index code. Read-only."""
    from sqlalchemy import text
    from app.db.session import AsyncSessionLocal

    start = date.today() - timedelta(days=days)
    out: dict[str, dict[date, float]] = {}
    async with AsyncSessionLocal() as db:
        await db.execute(text("SET TRANSACTION READ ONLY"))
        rows = (await db.execute(text("""
            SELECT index_code, price_date, close_price
              FROM market.index_prices
             WHERE price_date >= :start AND close_price IS NOT NULL
        """), {"start": start})).mappings().all()
    for r in rows:
        out.setdefault(r["index_code"], {})[r["price_date"]] = float(
            r["close_price"])
    return out


def agreement(ours: dict[date, float],
              theirs: dict[date, float]) -> tuple[int, float, float]:
    """(shared dates, mean abs % diff, max abs % diff)."""
    shared = sorted(set(ours) & set(theirs))
    if not shared:
        return 0, float("inf"), float("inf")
    diffs = [abs(theirs[d] - ours[d]) / ours[d] * 100
             for d in shared if ours[d]]
    if not diffs:
        return len(shared), float("inf"), float("inf")
    return len(shared), sum(diffs) / len(diffs), max(diffs)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=120)
    ap.add_argument("--symbol", default=None,
                    help="test one symbol against every code")
    args = ap.parse_args()

    key = _key()
    ours = asyncio.run(stored_closes(args.days))

    print(f"Stored series ({args.days}d window):")
    for code in TARGETS + EXCLUDED:
        s = ours.get(code, {})
        last = max(s) if s else None
        print(f"  {code:8} {len(s):4} rows   last={last}")
    print()

    if args.symbol:
        candidates = [{"Code": args.symbol.replace(".INDX", ""),
                       "Name": "(explicit)"}]
    else:
        candidates = list_candidates(key)
        for c in candidates:
            print(f"  {c.get('Code',''):16} {c.get('Name','')}")
        print()

    print("Fetching candidates …")
    fetched: dict[str, dict[date, float]] = {}
    names: dict[str, str] = {}
    for c in candidates:
        sym = f"{c['Code']}.INDX"
        names[sym] = c.get("Name", "")
        closes = fetch_closes(key, sym, args.days)
        if closes:
            fetched[sym] = closes
            print(f"    {sym:18} {len(closes):4} rows   last={max(closes)}")
    print()

    print("═" * 78)
    print("AGREEMENT WITH WHAT WE ALREADY PUBLISH (lower is better)")
    print("═" * 78)
    for code in TARGETS:
        mine = ours.get(code, {})
        if not mine:
            print(f"\n{code}: no stored history in window — cannot verify")
            continue
        ranked = []
        for sym, theirs in fetched.items():
            n, mean, mx = agreement(mine, theirs)
            if n >= 5:
                ranked.append((mean, mx, n, sym))
        ranked.sort()
        print(f"\n{code}  ({len(mine)} stored rows, last {max(mine)})")
        if not ranked:
            print("    no candidate shared enough dates to compare")
        for mean, mx, n, sym in ranked[:3]:
            verdict = "MATCH" if mean < 0.05 else ("close" if mean < 1 else "")
            print(f"    {sym:18} shared={n:3}  mean={mean:8.4f}%  "
                  f"max={mx:8.4f}%  {verdict}   {names.get(sym,'')[:34]}")

    print("\n" + "═" * 78)
    print("ASX100 is the control: ATOI.INDX must rank first with mean ~0.00%.")
    print("If it does not, the method is unsound and no result above counts.")
    print("AXJO is excluded and is not a target.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
