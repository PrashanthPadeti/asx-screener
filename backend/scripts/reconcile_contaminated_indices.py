#!/usr/bin/env python
"""
Row-level reconciliation for ASX20, AXFJ and AXMJ
=================================================
READ-ONLY. No writes, no DDL, read-only transaction, api_token never
printed.

The defect
----------
Measured 19 Oct 2026: these three stored series hold the wrong data from
2025-05-01 to 2026-05-31 and are correct on both sides of that window.
ASX20 held the All Ordinaries; AXFJ and AXMJ held values roughly 1/320 and
1/1,440 of index level. ~265 sessions each, ~19.6% of their history.
See docs/finding_2026-10-19_three_indices_wrong_for_13_months.md

What this establishes, before any repair is designed
----------------------------------------------------
1. WHICH ROWS differ, by column, at row level -- not a monthly median.
2. WHETHER derived values are wrong only inside the window.

The second is the question that decides the repair's scope, and it is NOT
obvious. `compute_rows` derives returns from the FETCHED frame, never from
stored rows, so each row's derived values reflect what the provider served
on the day that row was written:

    written during the window  -> derived from contaminated frames
    written after June 2026    -> derived from corrected frames, possibly fine

If the second holds, repairing closes inside the window plus their own
derived values is sufficient. If it does not -- if rows after the window
also carry derived values computed across contaminated history -- the
repair reaches forward by up to a year, because return_1y and the 52-week
extremes look back that far.

Guessing which, and repairing on the guess, would either leave contaminated
metrics behind or rewrite correct ones. Both are worse than measuring.

How "should be" is computed
---------------------------
By calling the PRODUCER's own `fetch_eodhd_index` and `compute_rows`. Not a
reimplementation: a reimplementation would test itself. The same code that
writes rows in production decides what each row ought to contain.

What it cannot establish
------------------------
Which side is correct in an absolute sense. EODHD's current history is the
reference because it agrees exactly with our own data on both sides of the
window across four years -- that makes it the same series, not an
authority. The index's published level is neither available here nor
needed to identify rows that disagree.

Usage:
    PYTHONPATH=/opt/asx-screener/backend \\
      /opt/asx-screener/asx-venv/bin/python \\
      backend/scripts/reconcile_contaminated_indices.py
    ... --code ASX20     one index
    ... --sample 10      rows to print per section
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date
from pathlib import Path

_HERE = Path(__file__).resolve().parents[1]
BACKEND = _HERE if (_HERE / "app" / "core" / "config.py").exists() else Path.cwd()
if not (BACKEND / "app" / "core" / "config.py").exists():
    sys.exit(f"run this from the backend directory (looked in {BACKEND})")
sys.path.insert(0, str(BACKEND))

#: The contaminated codes and the EODHD symbol that matches them outside the
#: window. Not switched in v11.2.24 precisely because of this defect.
TARGETS = {"ASX20": "ATLI.INDX", "AXFJ": "AXFJ.INDX", "AXMJ": "AXMJ.INDX"}

WINDOW_FROM = date(2025, 5, 1)
WINDOW_TO = date(2026, 5, 31)

#: Every value the producer stores per row. Reconciled column by column: a
#: repair that fixes close_price and leaves return_1y is the "coverage is
#: not semantics" defect in a new place.
COLUMNS = ("close_price", "open_price", "high_price", "low_price",
           "return_1d", "return_1w", "return_1m", "return_3m", "return_6m",
           "return_1y", "return_ytd", "high_52w", "low_52w")

#: Below this two values are the same number differently rounded.
TOL_PCT = 0.01


def _differs(ours, theirs) -> bool:
    if ours is None and theirs is None:
        return False
    if ours is None or theirs is None:
        return True
    ours, theirs = float(ours), float(theirs)
    if ours == theirs:
        return False
    denom = max(abs(ours), abs(theirs))
    return (abs(ours - theirs) / denom * 100) > TOL_PCT if denom else False


async def stored_rows(code: str) -> dict:
    from sqlalchemy import text
    from app.db.session import AsyncSessionLocal
    cols = ", ".join(COLUMNS)
    async with AsyncSessionLocal() as db:
        await db.execute(text("SET TRANSACTION READ ONLY"))
        rows = (await db.execute(text(
            f"SELECT price_date, {cols} FROM market.index_prices "
            f"WHERE index_code = :c ORDER BY price_date"), {"c": code}
        )).mappings().all()
    return {r["price_date"]: dict(r) for r in rows}


def expected_rows(symbol: str, first: date, last: date) -> dict:
    """What the producer would write today, via the producer's own code."""
    from compute.engine.index_prices import compute_rows, fetch_eodhd_index
    df = fetch_eodhd_index(symbol, first, last)
    if df is None or df.empty:
        return {}
    return {r["price_date"]: r for r in compute_rows(df)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--code", default=None)
    ap.add_argument("--sample", type=int, default=6)
    args = ap.parse_args()

    targets = ({args.code.upper(): TARGETS[args.code.upper()]}
               if args.code else dict(TARGETS))

    for code, symbol in targets.items():
        print("=" * 78)
        print(f"{code}  vs  {symbol}")
        print("=" * 78)

        mine = asyncio.run(stored_rows(code))
        if not mine:
            print("  no stored rows\n")
            continue
        first, last = min(mine), max(mine)
        theirs = expected_rows(symbol, first, last)
        if not theirs:
            print("  provider returned nothing — CANNOT RECONCILE\n")
            continue

        # Rows we hold that the provider does not cover cannot be checked,
        # and must be reported rather than counted as agreeing.
        unreconcilable = sorted(set(mine) - set(theirs))
        shared = sorted(set(mine) & set(theirs))
        print(f"  stored {len(mine)} rows [{first} .. {last}]")
        print(f"  provider covers {len(theirs)}; shared {len(shared)}; "
              f"unreconcilable {len(unreconcilable)}")
        if unreconcilable:
            print(f"    earliest unreconcilable: {unreconcilable[0]}  "
                  f"latest: {unreconcilable[-1]}")

        inside, outside = [], []
        per_col_in, per_col_out = {c: 0 for c in COLUMNS}, {c: 0 for c in COLUMNS}
        for d in shared:
            bad = [c for c in COLUMNS if _differs(mine[d][c], theirs[d].get(c))]
            if not bad:
                continue
            in_window = WINDOW_FROM <= d <= WINDOW_TO
            (inside if in_window else outside).append((d, bad))
            tgt = per_col_in if in_window else per_col_out
            for c in bad:
                tgt[c] += 1

        in_total = sum(1 for d in shared if WINDOW_FROM <= d <= WINDOW_TO)
        out_total = len(shared) - in_total
        print(f"\n  INSIDE  {WINDOW_FROM} .. {WINDOW_TO}: "
              f"{len(inside)}/{in_total} rows differ")
        print(f"  OUTSIDE the window:              "
              f"{len(outside)}/{out_total} rows differ")

        print("\n  by column (inside / outside):")
        for c in COLUMNS:
            if per_col_in[c] or per_col_out[c]:
                print(f"    {c:14} {per_col_in[c]:5} / {per_col_out[c]:5}")

        # The question the repair's scope turns on.
        print("\n  SCOPE:")
        if outside:
            dates = [d for d, _ in outside]
            print(f"    Derived values are NOT contained by the window. "
                  f"{len(outside)} rows outside it differ, "
                  f"{min(dates)} .. {max(dates)}.")
            print(f"    A repair limited to the window would leave these "
                  f"behind.")
            for d, bad in outside[:args.sample]:
                print(f"      {d}  {', '.join(bad)}")
        else:
            print(f"    Every difference falls inside the window. Repairing "
                  f"those {len(inside)} rows and their derived values is "
                  f"sufficient.")

        if inside:
            print(f"\n  sample inside the window:")
            for d, bad in inside[:args.sample]:
                o, t = mine[d], theirs[d]
                print(f"    {d}  close ours={o['close_price']} "
                      f"theirs={t.get('close_price')}   "
                      f"({len(bad)} cols differ)")
        print()

    print("=" * 78)
    print("EODHD is the reference because it agrees exactly with our own data")
    print("on BOTH sides of the window across four years — that makes it the")
    print("same series, not an authority. Nothing here was written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
