#!/usr/bin/env python
"""
What would FACTOR_MODEL_V4 move? Measured, before it is designed.
=================================================================
Findings 17 and 20 both need a new model version, because both change which
values applicability gate 1b suppresses, and suppression changes scores:

  17  `fcf_yield` is a free cash flow (reporting currency) over an AUD market
      capitalisation -- the exact shape CROSS_CURRENCY exists for -- and is
      NOT in it. Measured: 167 of 178 foreign-reporter rows publish it, 78 of
      them inside the scored population.

  20  `unit_gate` publishes when the reporting currency is UNSTATED. v11.2.86
      decided the opposite for Price/FCF at the producer, which left
      Price/FCF stricter than its own peers. Applying the strict rule in the
      gate touches the eight ratios it covers.

WHY THIS CANNOT BE REASONED ABOUT

Scoring is PERCENTILE-RANK: `pct_rank` uses `rank(pct=True,
na_option="keep")`. Removing a value from a metric's population changes that
metric's percentile for EVERY company that still has one. So the blast radius
of suppressing 167 values is not 167 rows -- it is every scored row, by a
small amount, plus the 167 whose factor reweights outright. "How many rows
are affected" has no answer short of computing it both ways.

And a small score delta is not a small customer-visible change: the screener
SORTS on these columns. A composite moving 0.3 can move a stock fifty places.
So rank movement is reported beside score movement, because that is what a
customer sees.

HOW IT MEASURES

It runs the REAL scoring path -- `composite_score.run(conn, dry_run=True)` --
three times, capturing the frame by wrapping `compute_composite`, which
receives it already carrying the five factor scores. No producer change, no
reimplementation of the model, and the only difference between runs is the
rule under test:

  S1  current rules (baseline)
  S2  S1 + fcf_yield in CROSS_CURRENCY                    (finding 17)
  S3  S2 + an unstated currency treated as a mismatch     (finding 20)

READ-ONLY: dry_run never writes, and the connection is rolled back.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))


def _capture(cs, conn):
    """Run the real scoring path once; return the scored frame."""
    import pandas as pd

    grabbed: dict[str, pd.DataFrame] = {}
    real = cs.compute_composite

    def wrapper(df_scores, *a, **kw):
        out = real(df_scores, *a, **kw)
        cols = ["asx_code"] + [c for c in (
            "value_score", "quality_score", "growth_score",
            "momentum_score", "income_score") if c in df_scores.columns]
        snap = df_scores[cols].copy()
        snap["composite_score"] = out.values
        grabbed["frame"] = snap
        return out

    cs.compute_composite = wrapper
    try:
        cs.run(conn, dry_run=True)
    finally:
        cs.compute_composite = real
    if "frame" not in grabbed:
        raise RuntimeError(
            "compute_composite was never called, so no scores were captured. "
            "The scoring path changed shape and this instrument is measuring "
            "nothing -- which is the failure mode it must not have.")
    return grabbed["frame"].set_index("asx_code")


def _diff(base, cand, label, factors):
    import pandas as pd

    common = base.index.intersection(cand.index)
    print("\n" + "=" * 72)
    print(label)
    print("=" * 72)
    print(f"  rows scored: baseline {len(base)}  candidate {len(cand)}  "
          f"common {len(common)}")
    only_b = sorted(set(base.index) - set(cand.index))
    only_c = sorted(set(cand.index) - set(base.index))
    if only_b or only_c:
        print(f"  ** population differs: {len(only_b)} only in baseline, "
              f"{len(only_c)} only in candidate")
        print(f"     {only_b[:6]} / {only_c[:6]}")

    for col in ["composite_score"] + factors:
        if col not in base.columns or col not in cand.columns:
            continue
        b = pd.to_numeric(base.loc[common, col], errors="coerce")
        c = pd.to_numeric(cand.loc[common, col], errors="coerce")
        # A value appearing or disappearing is a change, and a NaN-aware
        # subtraction would hide it as NaN rather than report it.
        gained = int((b.isna() & c.notna()).sum())
        lost = int((b.notna() & c.isna()).sum())
        d = (c - b).abs()
        moved = int((d > 0.0001).sum())
        print(f"\n  {col}")
        print(f"    changed      {moved} of {len(common)}"
              f"   gained {gained}   withheld {lost}")
        if moved:
            print(f"    |delta|      median {d.median():.2f}  "
                  f"p95 {d.quantile(.95):.2f}  max {d.max():.2f}")

    # RANK MOVEMENT on the composite: what a customer actually sees.
    b = pd.to_numeric(base.loc[common, "composite_score"], errors="coerce")
    c = pd.to_numeric(cand.loc[common, "composite_score"], errors="coerce")
    rb = b.rank(ascending=False, method="min")
    rc = c.rank(ascending=False, method="min")
    shift = (rc - rb).abs().dropna()
    if len(shift):
        print("\n  composite RANK movement (the screener sorts on this)")
        print(f"    median {shift.median():.0f}   p95 {shift.quantile(.95):.0f}"
              f"   max {shift.max():.0f} places")
        for n in (10, 50, 100, 250):
            print(f"    moved more than {n:>4} places: "
                  f"{int((shift > n).sum())}")
        worst = shift.sort_values(ascending=False).head(10)
        print("    biggest movers:")
        for code, places in worst.items():
            print(f"      {code:<6} {int(places):>5} places   "
                  f"{b.get(code)} -> {c.get(code)}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--env-file")
    args = ap.parse_args()
    if args.env_file:
        from dotenv import load_dotenv
        load_dotenv(args.env_file)

    import psycopg2
    from app.core.db import get_database_url_sync
    from compute.engine import applicability as ap_mod
    from compute.engine import composite_score as cs
    from compute.engine.metric_states import LATEST_MODEL_VERSION

    FACTORS = ["value_score", "quality_score", "growth_score",
               "momentum_score", "income_score"]

    conn = psycopg2.connect(get_database_url_sync())
    try:
        print(f"model version in force: {LATEST_MODEL_VERSION}")
        print(f"CROSS_CURRENCY covers {len(ap_mod.CROSS_CURRENCY)} metrics; "
              f"fcf_yield in it: {'fcf_yield' in ap_mod.CROSS_CURRENCY}")

        print("\n── S1  current rules ──")
        s1 = _capture(cs, conn)

        print("\n── S2  + fcf_yield in CROSS_CURRENCY (finding 17) ──")
        real_cc = dict(ap_mod.CROSS_CURRENCY)
        try:
            ap_mod.CROSS_CURRENCY["fcf_yield"] = (
                "free cash flow is stated in {currency} and the market "
                "capitalisation it is divided by is AUD")
            s2 = _capture(cs, conn)
        finally:
            ap_mod.CROSS_CURRENCY.clear()
            ap_mod.CROSS_CURRENCY.update(real_cc)

        print("\n── S3  + an unstated currency is a mismatch (finding 20) ──")
        real_gate = ap_mod.unit_gate

        def strict_gate(metric, reporting_currency):
            reason = ap_mod.CROSS_CURRENCY.get(metric)
            if reason is None:
                return None
            stated = (reporting_currency or "").strip().upper()
            if stated == ap_mod.BASE_CURRENCY:
                return None
            return (ap_mod.Applicability.NOT_MEANINGFUL,
                    reason.format(currency=stated or "an unstated currency"))

        try:
            ap_mod.CROSS_CURRENCY["fcf_yield"] = (
                "free cash flow is stated in {currency} and the market "
                "capitalisation it is divided by is AUD")
            ap_mod.unit_gate = strict_gate
            s3 = _capture(cs, conn)
        finally:
            ap_mod.unit_gate = real_gate
            ap_mod.CROSS_CURRENCY.clear()
            ap_mod.CROSS_CURRENCY.update(real_cc)

        _diff(s1, s2, "S2 vs S1 — finding 17 alone (fcf_yield gated)",
              FACTORS)
        _diff(s1, s3, "S3 vs S1 — findings 17 and 20 together", FACTORS)
        _diff(s2, s3, "S3 vs S2 — the strict silence rule's own share",
              FACTORS)

        conn.rollback()
        print("\nread-only, rolled back")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
