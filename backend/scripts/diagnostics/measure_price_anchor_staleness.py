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
    ap.add_argument("--deployed-root",
                    default="/opt/asx-screener/backend",
                    help="the DEPLOYED tree, read to establish "
                         "deployment identity. Digest inequality "
                         "proves only that code changed; the check "
                         "is identity against the intended "
                         "candidate.")
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

        # ── Production acceptance ────────────────────────────────────────
        #
        # Three groups, because they have three different expectations and
        # one of them is "nothing may change":
        #
        #   WITHHELD   the anchor-dependent columns ON STALE ROWS. Must
        #              become NULL -- price_at_compute and altman_z_score
        #              included.
        #   RETAINED   the SAME columns on ELIGIBLE rows. Must not move. The
        #              Price/FCF reconciliation could never establish this:
        #              it compares one column. A bound that wrongly withheld
        #              an eligible row would pass every check written so far.
        #   UNCHANGED  the series-based risk metrics, on every row. Must not
        #              move. An early version of this instrument reported
        #              them as anchor-dependent, so "did not move" is an
        #              assertion here, not an assumption.
        #
        # Stale rows carry VALUES, because change there is expected and must
        # be readable. Eligible rows carry a per-row DIGEST of the same
        # columns -- 33,000 rows of values would be unwieldy, and a digest
        # still names the row that moved, after which the values can be
        # re-read. Scoped, not sampled: every yearly row is covered.
        WITHHELD = sorted(anchor_dependent)
        UNCHANGED = [c for c in ("sharpe_1y", "volatility_1y",
                                 "max_drawdown_1y") if c in cols]
        stale_keys = sorted((c, fy) for c, fys in per_code_stale.items()
                            for fy in fys)

        def _acceptance_state():
            """(stale values, per-row digests) over every yearly row."""
            import hashlib as _h
            want = WITHHELD + UNCHANGED
            sel = ", ".join('"' + c + '"' for c in want)
            cur.execute("SELECT asx_code, fiscal_year, " + sel +
                        " FROM market.yearly_metrics")
            stale_vals, digests = {}, {}
            stale_set = set(stale_keys)
            for row in cur.fetchall():
                key = (row[0], int(row[1]))
                vals = dict(zip(want, row[2:]))
                flat = "|".join("" if vals[c] is None else str(vals[c])
                                for c in want)
                digests[key[0] + ":" + str(key[1])] = _h.sha256(
                    flat.encode()).hexdigest()[:16]
                if key in stale_set:
                    stale_vals[key[0] + ":" + str(key[1])] = {
                        c: (None if vals[c] is None else str(vals[c]))
                        for c in want}
            return stale_vals, digests

        def _digest_of(root):
            """sha256 over the producer set in a given tree, or None."""
            import hashlib as _h
            h = _h.sha256()
            for name in ("yearly_compute.py", "periods.py",
                         "applicability.py"):
                f = root / "compute" / "engine" / name
                if not f.is_file():
                    return None
                h.update(name.encode())
                h.update(f.read_bytes())
            return h.hexdigest()

        if args.emit or args.verify:
            import json
            from compute.engine import source_fingerprint as sfp
            candidate_digest = _digest_of(BACKEND)
            deployed_digest = _digest_of(Path(args.deployed_root))
            # The INPUTS at capture time. Retention claims -- "eligible rows
            # kept their values", "risk metrics did not move" -- are only
            # meaningful if the recomputation read the same inputs. An
            # ingestion between capture and run makes a changed value correct
            # and the comparison void, so the fingerprint is recorded and
            # compared rather than hoped for.
            live_fp = sfp.compute(cur)

        if args.emit:
            stale_vals, digests = _acceptance_state()
            payload = {
                "candidate": args.candidate or "(unrecorded)",
                # The tree this instrument is RUNNING from: the code whose
                # behaviour these expectations describe.
                "intended_candidate_digest": candidate_digest,
                # The tree DEPLOYED when the before-values were captured, so
                # the baseline is identified rather than assumed and a verify
                # can tell "not deployed yet" from "deployed something else".
                "baseline_deployed_digest": deployed_digest,
                # The inputs these before-values were captured against.
                "capture_fingerprint_schema": live_fp.schema_version,
                "capture_fingerprint_aggregate": live_fp.aggregate,
                "bound_days": BOUND_DAYS,
                "withheld_columns": WITHHELD,
                "unchanged_columns": UNCHANGED,
                "stale_rows": len(stale_keys),
                "stale_values": stale_vals,
                "row_digests": digests,
            }
            Path(args.emit).write_text(json.dumps(payload), encoding="utf-8")
            print("\nwrote an acceptance snapshot to " + args.emit)
            print("    intended candidate digest : "
                  + (candidate_digest or "(none)")[:32])
            print("    baseline deployed digest  : "
                  + (deployed_digest or "(none)")[:32])
            print("    stale rows with values    : " + str(len(stale_vals)))
            print("    rows with a digest        : " + str(len(digests)))

        if args.verify:
            import json
            prior = json.loads(Path(args.verify).read_text(encoding="utf-8"))
            stale_vals, digests = _acceptance_state()

            print("\n" + "=" * 72)
            print("ACCEPTANCE -- deployment identity, then rows")
            print("=" * 72)
            intended = prior.get("intended_candidate_digest")
            baseline = prior.get("baseline_deployed_digest")
            print("  intended candidate (snapshot) : "
                  + (intended or "(none)")[:32])
            print("  baseline deployed (snapshot)  : "
                  + (baseline or "(none)")[:32])
            print("  deployed NOW                  : "
                  + (deployed_digest or "(none)")[:32])

            # Digest INEQUALITY proves nothing -- it says some code changed,
            # not that the right code is running. And equality is correct and
            # expected when the snapshot was emitted from the candidate
            # BEFORE deploying it, which is how v11.2.86 was accepted. So the
            # check is identity against the INTENDED candidate.
            # VOID is not FAILED, and the two must not share a verdict line.
            # A failed comparison says the gate is wrong. A void one says
            # this comparison cannot answer the question -- the inputs moved
            # under it -- and leaves the verification OPEN. Both are
            # non-success; conflating them would let "recapture and repeat"
            # read as "the release is broken", or worse, the reverse.
            problems: list[str] = []
            voids: list[str] = []
            if intended is None or deployed_digest is None:
                problems.append("a digest is missing, so deployment identity "
                                "cannot be established at all")
            elif deployed_digest != intended:
                problems.append(
                    "the deployed producer is not the intended candidate: "
                    "deployed " + deployed_digest[:16] + ", intended "
                    + intended[:16])
            else:
                print("\n  deployment identity holds: the running producer IS "
                      "the intended candidate.")

            cur.execute("""
                WITH a AS (SELECT DISTINCT compute_run_id AS run_id
                           FROM screener.universe
                           WHERE compute_run_id IS NOT NULL)
                SELECT (SELECT count(*) FROM a),
                       (SELECT max(run_id) FROM a),
                       (SELECT s.details->'yearly_source_fingerprint'
                                 ->>'schema_version'
                        FROM screener.compute_run_stages s JOIN a
                          ON a.run_id = s.run_id
                        WHERE s.stage_name='yearly_compute'
                          AND s.status='success'),
                       (SELECT left(s.details->'yearly_source_fingerprint'
                                 ->>'aggregate', 32)
                        FROM screener.compute_run_stages s JOIN a
                          ON a.run_id = s.run_id
                        WHERE s.stage_name='yearly_compute'
                          AND s.status='success')
            """)
            n_runs, run_id, fp_schema, fp_agg = cur.fetchone()
            print("\n  publishing run id            : " + str(run_id)
                  + "  (" + str(n_runs) + " distinct non-NULL)")
            print("  its recorded yearly schema   : " + str(fp_schema))
            print("  its recorded input aggregate : " + str(fp_agg))
            if n_runs != 1:
                problems.append(
                    str(n_runs) + " distinct run ids attribute the universe; "
                    "there is no single publication to tie this to")
            if fp_agg is None:
                problems.append(
                    "the publishing run recorded no yearly fingerprint -- it "
                    "reused yearly output, so this cannot be tied to the run "
                    "that produced these values (finding 24)")

            # INPUT STABILITY. Retention is only a claim about the gate if
            # the recomputation read the inputs the snapshot was captured
            # against. If an ingestion intervened, a moved value is correct
            # and the comparison is void -- which must invalidate the
            # verification rather than be reported as a defect.
            cap_schema = prior.get("capture_fingerprint_schema")
            cap_agg = prior.get("capture_fingerprint_aggregate")
            print("  capture input aggregate      : "
                  + (cap_agg or "(none recorded)")[:32])
            print("  live input aggregate         : "
                  + live_fp.aggregate[:32])
            if cap_agg is None:
                voids.append(
                    "the snapshot recorded no input fingerprint, so the "
                    "retention claims cannot be qualified -- recapture")
            elif cap_agg != live_fp.aggregate:
                voids.append(
                    "THE INPUTS MOVED between capture and now (capture "
                    + cap_agg[:16] + ", live " + live_fp.aggregate[:16]
                    + "). A changed eligible value may be correct. Recapture "
                    "and repeat against consistent inputs.")
            elif str(cap_schema) != str(live_fp.schema_version):
                voids.append(
                    "the fingerprint projection changed (capture schema "
                    + str(cap_schema) + ", live " + str(live_fp.schema_version)
                    + "), so the two aggregates are not comparable")

            not_cleared, retained_moved, window_moved, missing = [], [], [], []
            for key, before in prior.get("stale_values", {}).items():
                now = stale_vals.get(key)
                if now is None:
                    missing.append(key)
                    continue
                for col in prior.get("withheld_columns", []):
                    if now.get(col) is not None:
                        not_cleared.append((key, col, now[col]))
                for col in prior.get("unchanged_columns", []):
                    if before.get(col) != now.get(col):
                        window_moved.append((key, col, before.get(col),
                                             now.get(col)))

            stale_set = set(prior.get("stale_values", {}))
            for key, d in prior.get("row_digests", {}).items():
                if key in stale_set:
                    continue
                now = digests.get(key)
                if now is None:
                    missing.append(key)
                elif now != d:
                    retained_moved.append((key, d, now))

            # POPULATION EQUALITY, both directions. The loops above walk the
            # SNAPSHOT's keys, so they can only ever find rows that vanished.
            # A row the recomputation ADDED is invisible to them -- and a
            # deleted row would be, too, if the snapshot were ever the newer
            # side. Compare the key sets themselves.
            prior_keys = set(prior.get("row_digests", {}))
            now_keys = set(digests)
            extra = sorted(now_keys - prior_keys)
            vanished = sorted(prior_keys - now_keys)
            print("  rows in snapshot / now       : "
                  + str(len(prior_keys)) + " / " + str(len(now_keys)))
            print("  rows ADDED by the run        : " + str(len(extra)))
            print("  rows REMOVED by the run      : " + str(len(vanished)))
            for k in extra[:8]:
                print("    added    " + k)
            for k in vanished[:8]:
                print("    removed  " + k)
            if extra or vanished:
                problems.append(
                    "the yearly-row population changed (" + str(len(extra))
                    + " added, " + str(len(vanished)) + " removed). A "
                    "value comparison over matching keys alone would have "
                    "reported this as clean.")

            print("\n  stale rows in the snapshot   : "
                  + str(len(prior.get("stale_values", {}))))
            print("  eligible rows digested       : "
                  + str(len(prior.get("row_digests", {})) - len(stale_set)))
            print("  rows now absent              : " + str(len(missing)))
            print("  STALE: columns not cleared   : " + str(len(not_cleared)))
            print("  ELIGIBLE: rows that moved    : "
                  + str(len(retained_moved)))
            print("  window metrics that moved    : " + str(len(window_moved)))
            for r in not_cleared[:8]:
                print("    not cleared  " + r[0] + "  " + r[1] + " = "
                      + str(r[2]))
            for r in retained_moved[:8]:
                print("    moved        " + r[0] + "  " + r[1] + " -> " + r[2])
            for r in window_moved[:8]:
                print("    window       " + r[0] + "  " + r[1] + "  "
                      + str(r[2]) + " -> " + str(r[3]))

            if not_cleared or retained_moved or window_moved or missing:
                problems.append("rows did not reconcile")
            print()
            if voids:
                # Exit 2, distinct from a failure, and the row results above
                # are retained as evidence rather than suppressed -- they are
                # just not a verdict.
                print("  ** VOID -- verification remains OPEN, not failed")
                for v in voids:
                    print("     - " + v)
                if problems:
                    print("     (also, independent of the void: "
                          + "; ".join(problems) + ")")
                conn.rollback()
                return 2
            if problems:
                print("  ** DOES NOT RECONCILE")
                for pr in problems:
                    print("     - " + pr)
                conn.rollback()
                return 1
            print("  RECONCILES: the intended candidate is deployed, a single")
            print("  run published, every stale row cleared, every eligible")
            print("  row unmoved, and the risk metrics untouched.")

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
