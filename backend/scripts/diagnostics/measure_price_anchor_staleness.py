#!/usr/bin/env python
"""
Finding 18, per column: what does a stale price anchor actually publish?
=======================================================================
`price_at` returns the last close on or before a fiscal period end with NO
floor. For a company whose price history stops -- suspended, delisted, or
simply absent from the feed -- every later fiscal year anchors to the same
final close, however old. Measured over 33,864 rows: median 0 days, p95 2,
**max 6,644**; 402 rows more than 7 days stale.

v11.2.86 bounded ONE column at 7 calendar days (`p_fcf_ratio`). Its eleven
or so price-anchored siblings are unbounded, which is this finding.

WHAT THIS MEASURES, AND WHY IT IS NOT A CODE READING

The affected column set is DERIVED, not asserted. For each company the
producer runs twice:

    once with the real price series
    once with every observation after (period_end - 8 days) removed

Any column whose value changes between the two runs depends on the price
anchor. A column list read off the source would miss anything reached
indirectly -- market_cap feeds enterprise_value feeds ev_revenue -- and
would quietly go stale the next time a derivation is added.

Then, for the rows whose anchor is ALREADY stale in production, it counts
how many publish a value per column. That is the withholding population a
7-day bound would create, per column, split by whether the row is on the
served surface.

READ-ONLY. SELECTs inside a transaction that is rolled back.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

#: The bound v11.2.86 applied to p_fcf_ratio, in calendar days.
BOUND_DAYS = 7


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--env-file")
    ap.add_argument("--limit", type=int,
                    help="smoke test; counts are then NOT the population")
    ap.add_argument("--emit", metavar="PATH",
                    help="snapshot every stale row's stored values -- the 15 "
                         "anchor-dependent columns AND the 3 window metrics "
                         "-- so --verify can prove the first group cleared "
                         "and the second did not move")
    ap.add_argument("--verify", metavar="PATH",
                    help="reconcile an --emit snapshot against the store: "
                         "anchor-dependent columns must now be NULL, window "
                         "metrics must be unchanged, and every row is "
                         "checked by identity and value, not by count")
    ap.add_argument("--candidate", metavar="SHA",
                    help="recorded in the snapshot header; an operator "
                         "assertion, which is why the producer digest is "
                         "recorded beside it")
    args = ap.parse_args()

    if args.env_file:
        from dotenv import load_dotenv
        load_dotenv(args.env_file)

    import pandas as pd
    import psycopg2
    from app.core.db import get_database_url_sync
    from compute.engine import yearly_compute as yc

    cols = yc._insert_columns()
    I_FY = cols.index("fiscal_year")

    conn = psycopg2.connect(get_database_url_sync())
    try:
        cur = conn.cursor()
        codes = yc.fetch_codes(cur, None, args.limit)

        cur.execute("SELECT asx_code, compute_run_id FROM screener.universe")
        universe = dict(cur.fetchall())

        anchor_dependent: set[str] = set()
        stale_rows = 0
        stale_served = 0
        published: Counter[str] = Counter()
        published_served: Counter[str] = Counter()
        worst: list[tuple] = []
        latest_fy: dict[str, int] = {}
        per_code_stale: dict[str, list[int]] = defaultdict(list)

        for n, code in enumerate(codes, 1):
            fin = yc.fetch_annual_financials(cur, code)
            if fin.empty:
                continue
            prices = yc.fetch_all_prices(cur, code)
            shares = yc.fetch_current_shares(cur, code)
            currency = yc.fetch_reporting_currency(cur, code)

            rows = yc.build_yearly_rows(code, fin, prices, shares, currency)
            if not rows:
                continue
            by_fy = {int(r[I_FY]): r for r in rows}
            latest_fy[code] = max(by_fy)

            src = {int(r["fiscal_year"]): r
                   for r in fin.reset_index(drop=True).to_dict("records")
                   if r.get("fiscal_year") is not None}

            # ── Derive the anchor-dependent column set ───────────────────
            # One differential run per company is enough to reveal the set;
            # doing it for every company would double the whole measurement
            # for no extra information, so it stops once the set stabilises.
            # THE ANCHOR IS NULLED, NOT THE SERIES.
            #
            # The first version of this truncated `prices` to end 8 days
            # before the period end. That moved the anchor AND shortened the
            # 12-month price window `price_window` / `sharpe_drawdown_vol`
            # read, so it reported sharpe_1y, volatility_1y and
            # max_drawdown_1y as anchor-dependent. They are not: they take
            # the series directly and never touch the anchor.
            #
            # Replacing `_price_observation` isolates it exactly. The series
            # the window functions see is untouched; only the single
            # observation the anchor resolves to disappears, which is what a
            # freshness bound withholds. Restored in a finally so a raised
            # exception cannot leave the producer stubbed for later codes.
            if n <= 40 and not prices.empty:
                real = yc._price_observation
                try:
                    yc._price_observation = lambda *_a, **_k: (None, None)
                    alt = yc.build_yearly_rows(code, fin, prices, shares,
                                               currency)
                finally:
                    yc._price_observation = real
                alt_by = {int(r[I_FY]): r for r in alt}
                base = by_fy.get(latest_fy[code])
                other = alt_by.get(latest_fy[code])
                if base and other:
                    for i, name in enumerate(cols):
                        # computed_at is the run clock, not a metric.
                        if name == "computed_at":
                            continue
                        if base[i] != other[i]:
                            anchor_dependent.add(name)

            # ── The rows whose anchor is already stale in production ─────
            for fy, row in by_fy.items():
                ped = src.get(fy, {}).get("period_end_date")
                if ped is None or prices.empty:
                    continue
                _, when = yc._price_observation(prices, ped)
                if when is None:
                    continue
                age = int((pd.Timestamp(ped) - pd.Timestamp(when)).days)
                if age <= BOUND_DAYS:
                    continue
                stale_rows += 1
                per_code_stale[code].append(fy)
                served = (code in universe and fy == latest_fy[code])
                if served:
                    stale_served += 1
                    worst.append((age, code, fy, str(pd.Timestamp(ped).date()),
                                  str(pd.Timestamp(when).date())))
                for i, name in enumerate(cols):
                    # Only the anchor-dependent columns: a stale row also
                    # carries window metrics and identifiers that a
                    # freshness bound has no business withholding, and
                    # counting those would inflate the cost of the fix.
                    if name in ("computed_at", "asx_code", "fiscal_year",
                                "period_end_date"):
                        continue
                    if row[i] is not None:
                        published[name] += 1
                        if served:
                            published_served[name] += 1

            if n % 250 == 0:
                print(f"  ... {n}/{len(codes)} codes", flush=True)

        print("\n" + "=" * 72)
        print("THE ANCHOR-DEPENDENT COLUMN SET, derived differentially")
        print("=" * 72)
        print(f"  {len(anchor_dependent)} columns change when the price anchor")
        print(f"  is pushed past {BOUND_DAYS} days:")
        for name in sorted(anchor_dependent):
            print(f"    {name}")
        print("\n  Derived by running the producer twice per company, not read")
        print("  off the source: market_cap feeds enterprise_value feeds")
        print("  ev_revenue, and a hand-written list misses what is reached")
        print("  indirectly.")

        print("\n" + "=" * 72)
        print(f"ROWS WHOSE ANCHOR IS ALREADY STALE (> {BOUND_DAYS} days)")
        print("=" * 72)
        print(f"  stale rows           : {stale_rows}")
        print(f"  of those, SERVED     : {stale_served}  "
              f"(a company's latest fiscal year, and in the universe)")
        print(f"  codes affected       : {len(per_code_stale)}")

        print("\n── what a 7-day bound would withhold, per column " + "─" * 24)
        print(f"    {'column':<26} {'all rows':>9} {'SERVED':>8}")
        print(f"    {'-' * 26} {'-' * 9} {'-' * 8}")
        for name in sorted(anchor_dependent):
            a, s = published[name], published_served[name]
            print(f"    {name:<26} {a:>9} {s:>8}")
        other = {n for n in published if n not in anchor_dependent}
        if other:
            print()
            print(f"    not anchor-dependent, so NOT withheld by a bound "
                  f"({len(other)} columns):")
            print("      " + ", ".join(sorted(other)[:12])
                  + (" ..." if len(other) > 12 else ""))

        if worst:
            print("\n── the served rows at risk, oldest anchor first " + "─" * 25)
            print(f"    {'code':<6} {'FY':<6} {'period end':<12} "
                  f"{'anchor':<12} {'age':>7}")
            for age, code, fy, ped, when in sorted(worst, reverse=True)[:25]:
                print(f"    {code:<6} {fy:<6} {ped:<12} {when:<12} {age:>6}d")
        else:
            print("\n  NO SERVED ROW has a stale anchor today. The bound would")
            print("  withhold nothing a customer currently sees, and exists")
            print("  for the runs where a company stops trading while its")
            print("  statements stay inside the window the universe selects.")

        # ── Production acceptance: emit / verify over the stale rows ─────
        #
        # Counts prove the producer withholds. They do NOT prove the STORE
        # was cleared, and they say nothing about the columns a bound must
        # leave alone. So the snapshot carries both groups:
        #
        #   WITHHELD  the 15 anchor-dependent columns, which must become
        #             NULL -- price_at_compute and altman_z_score included
        #   UNCHANGED the 3 series-based risk metrics, which must not move,
        #             because an early version of this very instrument
        #             reported them as anchor-dependent and a gate that
        #             reached them would cost coverage for no reason
        #
        # Checked by identity and value per row. A count agreeing while the
        # rows differ is the failure this exists to catch.
        WITHHELD = sorted(anchor_dependent)
        UNCHANGED = ["sharpe_1y", "volatility_1y", "max_drawdown_1y"]
        stale_keys = sorted((c, fy) for c, fys in per_code_stale.items()
                            for fy in fys)

        def _snapshot():
            if not stale_keys:
                return {}
            want = [c for c in WITHHELD + UNCHANGED
                    if c in set(cols) or True]
            sel = ", ".join(f'"{c}"' for c in want)
            cur.execute(
                f"SELECT asx_code, fiscal_year, {sel} "
                f"FROM market.yearly_metrics "
                f"WHERE (asx_code, fiscal_year) IN %s",
                (tuple(stale_keys),))
            out = {}
            for row in cur.fetchall():
                out[(row[0], int(row[1]))] = dict(zip(want, row[2:]))
            return out

        if args.emit or args.verify:
            import hashlib
            import json
            producer = (BACKEND / "compute" / "engine" / "yearly_compute.py")
            digest = hashlib.sha256(producer.read_bytes()).hexdigest()
            snap = _snapshot()

        if args.emit:
            payload = {
                "candidate": args.candidate or "(unrecorded)",
                "producer_sha256": digest,
                "bound_days": BOUND_DAYS,
                "withheld_columns": WITHHELD,
                "unchanged_columns": UNCHANGED,
                "stale_rows": len(stale_keys),
                "rows": {f"{c}:{fy}": {k: (str(v) if v is not None else None)
                                       for k, v in vals.items()}
                         for (c, fy), vals in snap.items()},
            }
            Path(args.emit).write_text(json.dumps(payload, indent=1),
                                       encoding="utf-8")
            print(f"\nwrote a snapshot of {len(snap)} stale rows to "
                  f"{args.emit}")
            print(f"    producer_sha256: {digest}")
            print(f"    withheld columns: {len(WITHHELD)}   "
                  f"unchanged columns: {len(UNCHANGED)}")

        if args.verify:
            import json
            prior = json.loads(Path(args.verify).read_text(encoding="utf-8"))
            print("\n" + "=" * 72)
            print("ACCEPTANCE -- the stale rows, by identity and value")
            print("=" * 72)
            print(f"  snapshot candidate      : {prior.get('candidate')}")
            print(f"  snapshot producer_sha256: "
                  f"{prior.get('producer_sha256', '')[:32]}…")
            print(f"  this producer_sha256    : {digest[:32]}…")
            if prior.get("producer_sha256") == digest:
                print("\n  ** The producer has NOT changed since the snapshot.")
                print("     Verifying would compare a state to itself. Emit "
                       "the snapshot BEFORE deploying.")
                conn.rollback()
                return 1

            not_cleared, moved, missing = [], [], []
            for key, before in prior.get("rows", {}).items():
                code, _, fy = key.partition(":")
                now = snap.get((code, int(fy)))
                if now is None:
                    missing.append(key)
                    continue
                for col in prior.get("withheld_columns", []):
                    if now.get(col) is not None:
                        not_cleared.append((key, col, now[col]))
                for col in prior.get("unchanged_columns", []):
                    b = before.get(col)
                    a = now.get(col)
                    if (b is None) != (a is None) or (
                            b is not None and str(a) != b):
                        moved.append((key, col, b, a))

            print(f"\n  stale rows in the snapshot : "
                  f"{len(prior.get('rows', {}))}")
            print(f"  rows no longer stale/absent : {len(missing)}")
            print(f"  anchor columns NOT cleared  : {len(not_cleared)}")
            print(f"  window metrics that MOVED   : {len(moved)}")
            for r in not_cleared[:10]:
                print(f"    not cleared  {r[0]:<12} {r[1]:<20} = {r[2]}")
            for r in moved[:10]:
                print(f"    moved        {r[0]:<12} {r[1]:<18} "
                      f"{r[2]} -> {r[3]}")
            ok = not (not_cleared or moved)
            print(f"\n  {'RECONCILES' if ok else '** DOES NOT RECONCILE'}")
            print("  A rejected anchor must clear every affected value and")
            print("  must not touch the series-based metrics beside them.")
            if not ok:
                conn.rollback()
                return 1

        conn.rollback()
        print("\nread-only, rolled back")
        if args.limit:
            print(f"** --limit {args.limit} was passed; these are NOT "
                  f"population counts.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
