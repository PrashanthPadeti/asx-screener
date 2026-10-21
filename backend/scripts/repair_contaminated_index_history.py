#!/usr/bin/env python
"""
Repair the 13-month contaminated window in ASX20, AXFJ and AXMJ
===============================================================
DRY RUN BY DEFAULT. Writes nothing unless `--apply` is passed, and even
then only inside the measured window and only for the three affected codes.

What is being repaired
----------------------
Between 2025-05 and 2026-05 these three stored series hold the wrong data.
ASX20 carried the All Ordinaries; AXFJ and AXMJ carried values roughly
1/320 and 1/1,440 of index level. Measured 20 Oct 2026 by
`reconcile_contaminated_indices.py`: ~265 rows per index, all 13 stored
columns, with closes agreeing exactly on both sides of the window across
four years.

    docs/finding_2026-10-19_three_indices_wrong_for_13_months.md

Why this is allowed to overwrite history
----------------------------------------
Forward-only exists so one provider cannot silently restate another's rows
in ignorance. Here nothing is silent and nothing is ignorant: the rows are
measured wrong, the replacement source agrees with our own data on both
sides of the window across 1,078 rows, the scope was established row by
row, and the change is declared. A rule that forbade repairing rows KNOWN
to be wrong would preserve the defect it was written to prevent.

Why recomputing derived values is sound
---------------------------------------
`compute_rows` is the producer's own calculation, and
`tests/test_derived_values_have_no_lookahead.py` establishes behaviourally
that no derived value depends on observations after its row's date -- each
row computed on a frame truncated at that row equals the same row computed
on the full frame. So recomputing a 2025 row on history reaching to 2026
cannot import information that was unavailable on the day.

One property it does NOT have: `_pct_return` offsets POSITIONALLY (252
rows, not a calendar year), so a repaired row's long-horizon returns are
computed against a different prior row than its unrepaired neighbours
were. The repaired values are correct against the provider on the
producer's own basis. They do not tie exactly to the neighbours' basis, and
that is a property of the metric definition rather than of this repair.

What it will NOT touch
----------------------
  * Any row outside 2025-05-01 .. 2026-05-31
  * Any index other than the three
  * The 252 rows at the series start whose derived values differ because
    of the positional lookback, and the 8 scattered sessions where stored
    closes differ slightly from the provider's current values. Both are
    real, both are separate, and a repair that "fixed" them would have
    overreached its evidence.

Usage:
    PYTHONPATH=/opt/asx-screener/backend \\
      /opt/asx-screener/asx-venv/bin/python \\
      backend/scripts/repair_contaminated_index_history.py
    ... --code ASX20        one index
    ... --sample 12         rows to print
    ... --apply             WRITE. Requires --i-have-reviewed-the-dry-run
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

TARGETS = {"ASX20": "ATLI.INDX", "AXFJ": "AXFJ.INDX", "AXMJ": "AXMJ.INDX"}

#: The measured window. Repair is bounded by these dates in the SQL itself,
#: not merely by the rows this script happens to stage -- a bug in the
#: staging logic must not be able to reach a row outside it.
WINDOW_FROM = date(2025, 5, 1)
WINDOW_TO = date(2026, 5, 31)

COLUMNS = ("close_price", "open_price", "high_price", "low_price",
           "return_1d", "return_1w", "return_1m", "return_3m", "return_6m",
           "return_1y", "return_ytd", "high_52w", "low_52w")

#: Every repaired row must change its close by more than this. The window's
#: contamination is 46% to 138,000%; anything under a few percent is not
#: the defect being repaired and its presence means the scope is wrong.
MIN_CLOSE_CHANGE_PCT = 5.0


def _differs(ours, theirs) -> bool:
    """Would the producer, writing today, store this same value?

    Quantised to the scale the stored Decimal already carries, not a
    relative tolerance -- stored returns are NUMERIC with a fixed scale, so
    comparing a rounded 0.0123 against a computed 0.012345 relatively says
    0.36% and flags every row in the table.
    """
    from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
    if ours is None or theirs is None:
        return (ours is None) != (theirs is None)
    try:
        d_ours = Decimal(str(ours))
        d_theirs = Decimal(str(float(theirs)))
        exponent = d_ours.as_tuple().exponent
        if isinstance(exponent, int) and exponent < 0:
            d_theirs = d_theirs.quantize(Decimal(1).scaleb(exponent),
                                         rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        return True
    return d_ours != d_theirs


async def load_stored(codes):
    from sqlalchemy import text
    from app.db.session import AsyncSessionLocal
    cols = ", ".join(COLUMNS)
    out = {}
    async with AsyncSessionLocal() as db:
        await db.execute(text("SET TRANSACTION READ ONLY"))
        for code in codes:
            rows = (await db.execute(text(
                f"SELECT price_date, {cols} FROM market.index_prices "
                f"WHERE index_code = :c AND price_date BETWEEN :a AND :b "
                f"ORDER BY price_date"),
                {"c": code, "a": WINDOW_FROM, "b": WINDOW_TO}
            )).mappings().all()
            out[code] = {r["price_date"]: dict(r) for r in rows}
    return out


def expected(symbol: str):
    """What the producer would write today, from the producer's own code."""
    from compute.engine.index_prices import compute_rows, fetch_eodhd_index
    # Reach well before the window: the 252-session lookback for the window's
    # first rows needs about a year of prior history, and those prior closes
    # are correct.
    df = fetch_eodhd_index(symbol, date(2023, 1, 1), date.today())
    if df is None or df.empty:
        return {}
    return {r["price_date"]: r for r in compute_rows(df)}


async def apply_repair(code: str, staged: dict) -> int:
    """UPDATE only. Never INSERT: a date absent from the window is not a row
    this repair is entitled to create.

    Bounded in the SQL by the window AND the code, so a staging bug cannot
    reach a row outside the measured scope. Counts are checked before the
    transaction commits.
    """
    from sqlalchemy import text
    from app.db.session import AsyncSessionLocal

    sets = ", ".join(f"{c} = :{c}" for c in COLUMNS)
    stmt = text(
        f"UPDATE market.index_prices SET {sets} "
        f"WHERE index_code = :code AND price_date = :price_date "
        f"  AND price_date BETWEEN :win_a AND :win_b")

    touched = 0
    async with AsyncSessionLocal() as db:
        for d, row in staged.items():
            params = {c: row.get(c) for c in COLUMNS}
            params.update({"code": code, "price_date": d,
                           "win_a": WINDOW_FROM, "win_b": WINDOW_TO})
            result = await db.execute(stmt, params)
            touched += result.rowcount or 0
        if touched != len(staged):
            await db.rollback()
            raise SystemExit(
                f"{code}: staged {len(staged)} rows but {touched} were "
                f"updated — rolled back, nothing written")
        await db.commit()
    return touched


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--code", default=None)
    ap.add_argument("--sample", type=int, default=8)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--i-have-reviewed-the-dry-run", action="store_true",
                    dest="reviewed")
    args = ap.parse_args()

    if args.apply and not args.reviewed:
        sys.exit("--apply also requires --i-have-reviewed-the-dry-run. "
                 "This overwrites production history; it should not be one "
                 "flag away from a dry run.")

    targets = ({args.code.upper(): TARGETS[args.code.upper()]}
               if args.code else dict(TARGETS))
    stored = asyncio.run(load_stored(list(targets)))

    mode = "APPLY — WILL WRITE" if args.apply else "DRY RUN — writes nothing"
    print(f"{mode}")
    print(f"window {WINDOW_FROM} .. {WINDOW_TO}; "
          f"codes {', '.join(targets)}\n")

    all_staged = {}
    for code, symbol in targets.items():
        print("=" * 78)
        print(f"{code}  <-  {symbol}")
        print("=" * 78)
        mine = stored.get(code, {})
        theirs = expected(symbol)
        if not mine:
            print("  no stored rows in the window\n")
            continue
        if not theirs:
            print("  provider returned nothing — REFUSING to repair\n")
            continue

        staged, unchanged, missing = {}, 0, []
        for d in sorted(mine):
            want = theirs.get(d)
            if want is None:
                missing.append(d)
                continue
            if any(_differs(mine[d][c], want.get(c)) for c in COLUMNS):
                staged[d] = want
            else:
                unchanged += 1

        print(f"  rows in window: {len(mine)}")
        print(f"  to repair:      {len(staged)}")
        print(f"  already correct:{unchanged}")
        if missing:
            print(f"  NOT COVERED by the provider: {len(missing)} "
                  f"({missing[0]} .. {missing[-1]}) — left untouched")

        # Every repaired row must show the contamination. A row whose close
        # barely moves is not this defect and its presence means the scope
        # is wrong, not that the row needs a smaller fix.
        small = []
        for d, want in staged.items():
            old = float(mine[d]["close_price"] or 0)
            new = float(want["close_price"])
            if old and abs(new - old) / old * 100 < MIN_CLOSE_CHANGE_PCT:
                small.append((d, old, new))
        if small:
            print(f"\n  {len(small)} staged row(s) change close by less than "
                  f"{MIN_CLOSE_CHANGE_PCT}% — NOT the contamination this "
                  f"repair is scoped to:")
            for d, old, new in small[:args.sample]:
                print(f"    {d}  {old} -> {new}")
            print("  REFUSING to apply. Narrow the scope or explain these.")
            if args.apply:
                return 2

        print(f"\n  sample:")
        for d in list(staged)[:args.sample]:
            o, n = mine[d], staged[d]
            print(f"    {d}  close {o['close_price']} -> "
                  f"{n['close_price']:.4f}   "
                  f"return_1y {o['return_1y']} -> {n.get('return_1y')}")
        all_staged[code] = staged
        print()

    total = sum(len(s) for s in all_staged.values())
    print("=" * 78)
    if not args.apply:
        print(f"DRY RUN complete. {total} rows would be repaired across "
              f"{len(all_staged)} indices.")
        print("Nothing was written. Re-run with --apply "
              "--i-have-reviewed-the-dry-run to write.")
        return 0

    print(f"APPLYING to {total} rows …")
    for code, staged in all_staged.items():
        n = asyncio.run(apply_repair(code, staged))
        print(f"  {code}: {n} rows updated")
    print("\nNow re-run reconcile_contaminated_indices.py. Inside the window "
          "must be 0; the 252 leading rows and the scattered sessions must "
          "be UNCHANGED — a repair that moved those overreached.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
