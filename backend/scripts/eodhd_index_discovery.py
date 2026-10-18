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

# Resolved from the file's own location when it sits in the repository, but
# this script is deliberately run by reading it out of a commit into /tmp so
# the server checkout need not move -- and then `parents[1]` is `/`. Fall
# back to the working directory, which the caller sets to backend/.
_HERE = Path(__file__).resolve().parents[1]
BACKEND = _HERE if (_HERE / "app" / "core" / "config.py").exists() else Path.cwd()
if not (BACKEND / "app" / "core" / "config.py").exists():
    sys.exit(f"run this from the backend directory (looked in {BACKEND})")
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

#: The rule, fixed here in source rather than chosen once results are visible.
# REVISED after the first run's control FAILED. The revision is to the
# STATISTIC, not to the thresholds: median replaces mean because one corrupt
# stored row destroys a mean over 250 sessions, and our stored AXFJ/AXMJ
# series demonstrably contain such rows. The numeric bars are unchanged, and
# the control must now pass under the revised rule or this is abandoned.
MIN_SHARED = 20            # sessions; fewer cannot distinguish much
LEVEL_MED_MAX = 0.05       # %  — same series on the same base, typical day
RETURN_MED_MAX = 0.02      # pp — rules out an accumulation variant
MAX_OUTLIER_FRAC = 0.02    # at most 2% of sessions may disagree by >1%

#: Provider calls made, reported so the cost is visible rather than assumed.
REQUESTS = [0]


def _key() -> str:
    from app.core.config import settings
    key = settings.EODHD_API_KEY
    if not key:
        sys.exit("EODHD_API_KEY is not set")
    return key


def list_candidates(key: str) -> list[dict]:
    """Every index EODHD lists, filtered to the Australian ones."""
    import httpx
    REQUESTS[0] += 1
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
    REQUESTS[0] += 1
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


class Agreement:
    """How closely two series agree, on levels AND on daily returns.

    Both, because they fail differently and catch different impostors.

    A LEVEL comparison catches a different index. It does not catch the same
    index republished on a different base: rebase S&P/ASX 200 to 1000 and
    every close is wrong by a constant factor while every daily return is
    identical.

    A RETURN comparison catches the variant that matters most here. An
    accumulation index reinvests dividends, so it tracks the price index in
    shape but drifts upward: its daily returns exceed the price index's by
    roughly the dividend yield. That is exactly the error already found in
    AXJO, where a total-return surface was served price data, and a level
    check alone would not reliably separate them over a short window.

    Agreement on both is a much stronger claim than agreement on either.

    Why MEDIAN and not mean
    -----------------------
    The first version of this ranked on the mean, and a mean over 250
    sessions is destroyed by one bad row. Our stored AXFJ and AXMJ series
    contain values so extreme that every candidate -- the VIX, a currency
    index, a small-cap index -- reported the SAME maximum daily-return
    difference, 31,342pp and 140,348pp respectively. When every candidate
    agrees on the outlier, the outlier is ours. The correct symbol for ASX20
    matched at 0.0017% over 120 days and did not reach the top THREE over
    400, because the contaminated rows dominated its mean.

    The median answers "do these two series agree on a typical session",
    which is the question. The outliers are then reported separately rather
    than averaged away -- a series needs both: agreement on typical days AND
    an accounted-for number of exceptional ones. A median alone would let a
    series with 10% corrupt rows pass silently, which is the same mistake in
    a different direction.
    """

    __slots__ = ("n", "first", "last", "lvl_med", "lvl_max", "worst",
                 "ret_n", "ret_med", "ret_max", "outliers")

    #: A session where the two series disagree by more than this is not a
    #: rounding difference and is counted, listed and explained.
    OUTLIER_PCT = 1.0

    @staticmethod
    def _median(xs: list[float]) -> float:
        if not xs:
            return float("inf")
        s = sorted(xs)
        mid = len(s) // 2
        return s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2

    def __init__(self, ours: dict[date, float], theirs: dict[date, float]):
        shared = sorted(set(ours) & set(theirs))
        self.n = len(shared)
        self.first = shared[0] if shared else None
        self.last = shared[-1] if shared else None

        lvl: list[float] = []
        per_date: list[tuple[float, date]] = []
        for d in shared:
            if not ours[d]:
                continue
            pct = abs(theirs[d] - ours[d]) / ours[d] * 100
            lvl.append(pct)
            per_date.append((pct, d))
        self.lvl_med = self._median(lvl)
        self.lvl_max = max(lvl) if lvl else float("inf")
        self.outliers = sum(1 for p in lvl if p > self.OUTLIER_PCT)
        per_date.sort(reverse=True)
        #: The worst sessions, with both values, so a disagreement can be
        #: looked at rather than guessed about.
        self.worst = [(d, ours[d], theirs[d], p) for p, d in per_date[:4]]

        # Daily returns, only across CONSECUTIVE shared sessions. A gap in
        # either series would otherwise produce a multi-day "daily" return
        # and a difference that means nothing.
        rets = []
        for prev, cur in zip(shared, shared[1:]):
            if ours.get(prev) and theirs.get(prev):
                ours_r = ours[cur] / ours[prev] - 1
                their_r = theirs[cur] / theirs[prev] - 1
                rets.append(abs(their_r - ours_r) * 100)   # percentage points
        self.ret_n = len(rets)
        self.ret_med = self._median(rets)
        self.ret_max = max(rets) if rets else float("inf")


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

    # Stated BEFORE the results, so it cannot be fitted to them.
    print("═" * 78)
    print("MATCH RULE (fixed before results are read)")
    print("═" * 78)
    print(f"  shared sessions     >= {MIN_SHARED}")
    print(f"  level  MEDIAN |diff| <  {LEVEL_MED_MAX}%    (same series, same base)")
    print(f"  return MEDIAN |diff| <  {RETURN_MED_MAX} pp  (not an accumulation variant)")
    print(f"  outlier sessions     <= {MAX_OUTLIER_FRAC:.0%} of shared (|diff| > "
          f"{Agreement.OUTLIER_PCT}%)")
    print("  name must name the intended index — numbers alone never decide")
    print("  a target with two passing candidates is AMBIGUOUS, not matched")
    print("  MEDIAN, not mean: one corrupt stored row destroys a mean over")
    print("  250 sessions. Outliers are reported, never averaged away.\n")

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
    print(f"\n  EODHD requests made: {REQUESTS[0]}"
          f"  (1 symbol list + {len(candidates)} candidates;"
          f" each fetched once and compared against all {len(TARGETS)} targets)\n")

    print("═" * 78)
    print("AGREEMENT WITH WHAT WE ALREADY PUBLISH (lower is better)")
    print("═" * 78)
    passing: dict[str, list[str]] = {}
    for code in TARGETS:
        mine = ours.get(code, {})
        print(f"\n{code}  ({len(mine)} stored rows"
              + (f", last {max(mine)}" if mine else "") + ")")
        if not mine:
            print("    no stored history in window — CANNOT VERIFY")
            continue
        ranked = []
        for sym, theirs in fetched.items():
            a = Agreement(mine, theirs)
            if a.n >= MIN_SHARED:
                ranked.append((a.lvl_med, a, sym))
        ranked.sort(key=lambda t: t[0])
        if not ranked:
            print(f"    no candidate shared >= {MIN_SHARED} dates — CANNOT VERIFY")
            continue
        for _, a, sym in ranked[:3]:
            frac = a.outliers / a.n if a.n else 1.0
            ok = (a.lvl_med < LEVEL_MED_MAX
                  and a.ret_med < RETURN_MED_MAX
                  and frac <= MAX_OUTLIER_FRAC)
            if ok:
                passing.setdefault(code, []).append(sym)
            print(f"    {sym:18} {names.get(sym,'')[:36]}")
            print(f"        shared={a.n:3} [{a.first} .. {a.last}]")
            print(f"        level  med={a.lvl_med:9.5f}%  max={a.lvl_max:11.3f}%")
            print(f"        return med={a.ret_med:9.5f}pp max={a.ret_max:11.3f}pp"
                  f" (n={a.ret_n})")
            print(f"        outliers>{Agreement.OUTLIER_PCT}%: {a.outliers}/{a.n}"
                  f" ({frac:.1%})   {'PASS' if ok else ''}")
            if a.outliers and sym == ranked[0][2]:
                print("        worst sessions (ours vs theirs):")
                for d, mine_v, their_v, pct in a.worst:
                    print(f"          {d}  ours={mine_v:12.3f}  "
                          f"theirs={their_v:12.3f}  {pct:9.3f}%")

    print("\n" + "═" * 78)
    print("CONTROL")
    print("═" * 78)
    ctl = passing.get("ASX100", [])
    if ctl == ["ATOI.INDX"]:
        print("  PASS — ASX100 resolves to ATOI.INDX, its known-correct symbol.")
        print("  The method reproduces a mapping established independently.")
    elif not ours.get("ASX100"):
        print("  NOT RUN — no stored ASX100 history in this window.")
        print("  Re-run with a larger --days. Until the control produces a")
        print("  verdict the method is UNVALIDATED and no result above counts.")
    else:
        print(f"  FAIL — ASX100 resolved to {ctl or 'nothing'}, not ATOI.INDX.")
        print("  The method is unsound. No result above counts.")

    print("\nPASSING BOTH CHECKS:")
    for code in TARGETS:
        syms = passing.get(code, [])
        if len(syms) == 1:
            print(f"    {code:8} {syms[0]}")
        elif len(syms) > 1:
            print(f"    {code:8} AMBIGUOUS — {', '.join(syms)} "
                  f"(needs a documented reason, not a coin toss)")
        else:
            print(f"    {code:8} UNRESOLVED — stays on its current source")
    print("\nAXJO is excluded and is not a target. Note EODHD lists AXJOA")
    print("(S&P/ASX 200 Accumulated) — a lead for that provenance question,")
    print("deliberately NOT acted on here.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
