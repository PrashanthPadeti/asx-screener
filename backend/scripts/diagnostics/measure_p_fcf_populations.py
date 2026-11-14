#!/usr/bin/env python
"""
Why does each Price/FCF row decline, and how many are there?
============================================================
v11.2.86 restores ``p_fcf_ratio`` behind five guards. Before that release is
proposed for merge, each guard's population has to be a measured number.

HOW THIS AVOIDS THE MISTAKE IT IS HERE TO AVOID

The v11.2.84 forecast of ``volume_breakout`` missed by 542 rows because it was
derived from the inputs that happened to be STORED rather than the ones the
code actually reads. So this script does not model the producer. It RUNS it:
the same fetches, the same ``build_yearly_rows``, the same rows that an
upsert would carry -- and then attributes a reason to each row.

The attribution is checked, not trusted. Two reconciliations run over every
row, and either one failing voids the counts:

  R1  the reason attributed to a row must predict that row's actual
      ``p_fcf_ratio`` -- the exact value, not merely NULL vs not-NULL
  R2  the price this script reads for the staleness measurement must equal the
      ``price_at_compute`` the producer stored, which proves both picked the
      same observation

WHAT IT REPORTS

  P1  publishable, and the value distribution
  P2  an input missing (mc or fcf is None)
  P3  non-positive market capitalisation
  P4  non-positive free cash flow
  P5a a stated foreign currency -- the units do not cancel
  P5b no currency stated at all. Publishing here would assert a unit the
      source never stated; the strict rule (14 Nov 2026) withholds, and
      this count is the coverage it costs
  P6  declined by _clamp at |ratio| > 9,999
  P10 declined because the ratio rounded to 0.00 -- the underflow end of
      the same problem, found by reading P1's distribution rather than its
      count, and guarded from the same release
  P7  THE OPEN QUESTION: rows that publish ONLY because the reporting
      currency is unstated. This is the population the strict silence rule
      would additionally withhold, and the number the release decision needs.
  P8  price staleness -- days between period_end_date and the close
      ``price_at`` actually selected, since "at or before" can reach back
      arbitrarily far on a suspended or delisted stock
  P9  the extreme-end asymmetry: rows where _clamp declines the ratio while
      fcf_yield publishes a near-zero yield for the same pair

Overlaps are reconciled explicitly: the reasons are evaluated in the
producer's own short-circuit order, so each row is counted under exactly one,
and a second pass reports how many rows satisfy more than one predicate.

READ-ONLY. SELECTs only, inside a transaction that is rolled back. It writes
nothing, creates nothing, and holds one connection.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path
from typing import Optional

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

CLAMP_LIMIT = 9_999.0


def _pct(n: int, d: int) -> str:
    return f"{100.0 * n / d:5.1f}%" if d else "    --"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--env-file", help="path to a .env to load first")
    ap.add_argument("--limit", type=int,
                    help="only this many codes (smoke test; counts are then "
                         "NOT the population and the report says so)")
    args = ap.parse_args()

    if args.env_file:
        from dotenv import load_dotenv
        load_dotenv(args.env_file)

    import pandas as pd
    import psycopg2
    from app.core.db import get_database_url_sync
    from compute.engine.applicability import BASE_CURRENCY
    from compute.engine import yearly_compute as yc

    cols = yc._insert_columns()
    I_FY = cols.index("fiscal_year")
    I_PED = cols.index("period_end_date")
    I_MC = cols.index("market_cap")
    I_PX = cols.index("price_at_compute")
    I_PFCF = cols.index("p_fcf_ratio")
    I_YLD = cols.index("fcf_yield")

    conn = psycopg2.connect(get_database_url_sync())
    try:
        cur = conn.cursor()
        codes = yc.fetch_codes(cur, None, args.limit)

        reasons: Counter[str] = Counter()
        currencies: Counter[str] = Counter()
        values: list[float] = []
        silence_published: list[tuple] = []      # P7
        clamped: list[tuple] = []                # P6
        underflow: list[tuple] = []              # P10
        asymmetric: list[tuple] = []             # P9
        staleness: list[int] = []                # P8
        stale_worst: list[tuple] = []
        multi_reason = 0
        r1_failures: list[tuple] = []
        r2_failures: list[tuple] = []
        rows_total = 0

        for n, code in enumerate(codes, 1):
            fin = yc.fetch_annual_financials(cur, code)
            if fin.empty:
                continue
            prices = yc.fetch_all_prices(cur, code)
            current_shares = yc.fetch_current_shares(cur, code)
            currency = yc.fetch_reporting_currency(cur, code)
            currencies[currency or "(none stated)"] += 1

            produced = yc.build_yearly_rows(code, fin, prices, current_shares,
                                            currency)
            # Mirrors the producer exactly: it does `fin.reset_index(drop=True)`
            # then `to_dict("records")`, so the fcf this reads is the object
            # the producer's `_f(row.get("fcf"))` reads. Iterating the frame
            # instead would hand back Series objects -- a different type, with
            # different truthiness, which is how this instrument first failed.
            by_year = {int(r["fiscal_year"]): r
                       for r in fin.reset_index(drop=True).to_dict("records")
                       if r.get("fiscal_year") is not None}

            for row in produced:
                rows_total += 1
                fy = int(row[I_FY])
                mc = row[I_MC]
                actual = row[I_PFCF]
                src = by_year.get(fy)
                if src is None:
                    r1_failures.append((code, fy, "no source row for the "
                                        "fiscal year the producer emitted",
                                        None, actual))
                    continue
                fcf = yc._f(src.get("fcf"))

                coherent = (currency is None or currency == BASE_CURRENCY)

                # ── The producer's own order, so each row lands in one bucket
                if mc is None or fcf is None:
                    reason = "P2 an input missing"
                    predicted = None
                elif not mc > 0:
                    reason = "P3 market capitalisation <= 0"
                    predicted = None
                elif not fcf > 0:
                    reason = "P4 free cash flow <= 0"
                    predicted = None
                elif not coherent:
                    # Split, because the two halves are different facts and
                    # the strict silence rule (14 Nov 2026) was decided on
                    # the size of the second one. Collapsing them into one
                    # "currency" bucket would hide the only number that
                    # decision rests on.
                    reason = ("P5b currency not stated at all"
                              if currency is None
                              else "P5a currency stated and foreign")
                    predicted = None
                else:
                    predicted = yc._clamp(yc._div(mc, fcf))
                    if predicted == 0:
                        # The underflow guard: both inputs positive, the ratio
                        # below the column's 4dp precision. Mirrors _clamp.
                        predicted = None
                        reason = "P10 ratio rounds to 0.00 (underflow)"
                        underflow.append((code, fy, mc, fcf, row[I_YLD]))
                    elif predicted is None:
                        reason = "P6 declined by _clamp (> 9,999)"
                        clamped.append((code, fy, yc._div(mc, fcf),
                                        row[I_YLD]))
                        if row[I_YLD] is not None:
                            asymmetric.append((code, fy, yc._div(mc, fcf),
                                               row[I_YLD]))
                    else:
                        reason = "P1 publishable"
                        values.append(float(predicted))
                        if currency is None:
                            silence_published.append((code, fy, predicted))

                reasons[reason] += 1

                # How many predicates does this row satisfy at once?
                hits = sum([
                    mc is None or fcf is None,
                    mc is not None and not mc > 0,
                    fcf is not None and not fcf > 0,
                    not coherent,
                ])
                if hits > 1:
                    multi_reason += 1

                # R1 -- the attribution must predict the stored value exactly
                if (predicted is None) != (actual is None) or (
                        predicted is not None and actual is not None
                        and abs(float(predicted) - float(actual)) > 1e-9):
                    r1_failures.append((code, fy, reason, predicted, actual))

                # R2 + P8 -- the price observation, and how old it is
                ped = src.get("period_end_date")
                if ped is not None and not prices.empty:
                    tgt = pd.Timestamp(ped)
                    subset = prices[prices.index <= tgt]
                    if not subset.empty:
                        picked_px = float(subset.iloc[-1])
                        picked_on = subset.index[-1]
                        stored_px = row[I_PX]
                        if stored_px is not None and abs(
                                picked_px - float(stored_px)) > 1e-6:
                            r2_failures.append((code, fy, picked_px,
                                                stored_px))
                        age = int((tgt - picked_on).days)
                        staleness.append(age)
                        if age > 7:
                            stale_worst.append((code, fy, age,
                                                str(picked_on.date())))

            if n % 250 == 0:
                print(f"  ... {n}/{len(codes)} codes, {rows_total} rows",
                      flush=True)

        # ── Reconciliations first: the counts mean nothing without them ────
        print("\n" + "=" * 70)
        print("RECONCILIATION -- read this before any count below")
        print("=" * 70)
        print(f"  R1  attribution predicts the stored ratio : "
              f"{len(r1_failures)} failures of {rows_total} rows")
        print(f"  R2  price matches price_at_compute        : "
              f"{len(r2_failures)} failures")
        if r1_failures or r2_failures:
            print("\n  ** VOID. The attribution does not reproduce what the")
            print("     producer did, so every population below is a guess")
            print("     about code that behaves differently. First 10:")
            for f in (r1_failures + r2_failures)[:10]:
                print(f"       {f}")
            conn.rollback()
            return 1
        print("\n  both hold: the reasons below describe the code that ran.")

        if args.limit:
            print(f"\n  ** --limit {args.limit} was passed. These are NOT")
            print("     population counts. Re-run without it before deciding.")

        print("\n" + "=" * 70)
        print(f"POPULATIONS  ({rows_total} yearly rows, {len(codes)} codes)")
        print("=" * 70)
        for reason in sorted(reasons):
            n = reasons[reason]
            print(f"  {reason:<34} {n:>7}  {_pct(n, rows_total)}")
        print(f"  {'':<34} {'-' * 7}")
        print(f"  {'total':<34} {sum(reasons.values()):>7}")
        print(f"\n  rows satisfying more than one decline predicate: "
              f"{multi_reason}")
        print("  (counted once each, under the producer's own first match,")
        print("   so the column above sums to the row total exactly)")

        if values:
            s = pd.Series(values)
            print("\n── P1 the published distribution " + "─" * 36)
            print(f"  n {len(s)}   min {s.min():.2f}   p25 {s.quantile(.25):.2f}"
                  f"   median {s.median():.2f}   p75 {s.quantile(.75):.2f}"
                  f"   max {s.max():.2f}")

        print("\n── P7 THE OPEN QUESTION " + "─" * 45)
        print(f"  rows publishing ONLY because the currency is unstated: "
              f"{len(silence_published)}")
        print("  These are what the strict silence rule would additionally")
        print("  withhold. Roughly 8% of ASX reporters state a foreign")
        print("  currency, so that share of these is wrong by an exchange")
        print("  rate -- and the identical rows publish a P/E today, because")
        print("  unit_gate makes the same permissive choice under a frozen V3.")
        for r in silence_published[:10]:
            print(f"       {r}")

        print("\n── P6/P9 the extreme end " + "─" * 44)
        print(f"  declined by _clamp: {len(clamped)}")
        print(f"  of those, fcf_yield published anyway: {len(asymmetric)}")
        print("  (a ratio over 9,999 is a yield under 0.0001, which rounds to")
        print("   0.0000 in NUMERIC(8,4) and publishes -- the pair disagrees")
        print("   at the extreme, by column type, not by policy)")
        for r in asymmetric[:5]:
            print(f"       {r}")

        if staleness:
            s = pd.Series(staleness)
            print("\n── P8 how stale is the price price_at selected " + "─" * 22)
            print(f"  days before period_end: median {s.median():.0f}   "
                  f"p95 {s.quantile(.95):.0f}   max {s.max():.0f}")
            print(f"  rows more than 7 days stale: {len(stale_worst)} of "
                  f"{len(staleness)}")
            for r in sorted(stale_worst, key=lambda r: -r[2])[:10]:
                print(f"       {r}")

        print("\n── reporting currency, as the codes state it " + "─" * 24)
        for c, n in currencies.most_common(12):
            print(f"  {c:<16} {n:>6} codes")

        conn.rollback()
        print("\nread-only, rolled back")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
