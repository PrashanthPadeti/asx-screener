#!/usr/bin/env python
"""
Why does withholding GAIN a composite score? Reproducibly, per row.
===================================================================
Measuring finding 20 turned up five companies that acquire a composite score
when the strict silence rule withholds MORE of their inputs. A gain from a
withholding is counter-intuitive enough that it cannot ship as an
observation -- it needs a mechanism anyone can re-derive.

THE HYPOTHESIS THIS TESTS

The model treats the two kinds of absence oppositely, by design:

    NOT_MEANINGFUL   may be reweighted around, within a floor, as declared
                     policy -- a bank has no meaningful leverage ratio
    UNAVAILABLE      refuses, because reweighting an applicable-but-missing
                     signal publishes a different model under this one's name

The composite is five factors at 1/5 each with `domain_reweight=True` and
`min_effective_weight_fraction=0.60`, so it survives losing one factor and
just clears losing two -- but only when the loss is NOT_MEANINGFUL.

So the predicted mechanism is: the strict rule converts "absent for an
unrecorded reason" into "declared not meaningful", a factor crosses from
UNAVAILABLE to NM, and the composite may then reweight around it above the
floor where before it refused outright.

PREDICTED, NOT ASSUMED. If the gained rows do not show a factor crossing
exactly that way, the hypothesis is wrong and this prints what actually
happened instead.

WHAT IT REPORTS, per gained row
  * each factor's usability and effective weight, in both scenarios
  * which constituents dropped, and with which state
  * the composite's own surviving weight against the 0.60 floor

READ-ONLY: dry_run never writes, and the connection is rolled back.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

FACTORS = ("value", "quality", "growth", "momentum", "income")


def _capture(cs, conn):
    """Run the real scoring path once; return (scored frame, factor states).

    `compute_composite` receives the frame already carrying the five factor
    scores AND the per-factor states dict, which is where the effective
    weights live -- so one wrapper yields both without reimplementing any
    part of the model.
    """
    grabbed = {}
    real = cs.compute_composite

    def wrapper(df_scores, source_failed, factor_states, *a, **kw):
        out = real(df_scores, source_failed, factor_states, *a, **kw)
        cols = ["asx_code"] + [f"{f}_score" for f in FACTORS
                               if f"{f}_score" in df_scores.columns]
        snap = df_scores[cols].copy()
        snap["composite_score"] = out.values
        grabbed["frame"] = snap.set_index("asx_code")
        grabbed["states"] = factor_states
        return out

    cs.compute_composite = wrapper
    try:
        cs.run(conn, dry_run=True)
    finally:
        cs.compute_composite = real
    if "frame" not in grabbed:
        raise RuntimeError(
            "compute_composite was never called, so nothing was captured -- "
            "the scoring path changed shape and this explains nothing.")
    return grabbed["frame"], grabbed["states"]


def _describe(states, factor, code):
    """One factor's eligibility for one company, as the model computed it."""
    eff = (states.get(factor) or {}).get(code)
    if eff is None:
        return "no state recorded"
    usable = getattr(eff, "usable", None)
    weights = getattr(eff, "weights", None) or {}
    total = sum(weights.values()) if weights else 0.0
    return (f"usable={usable}  surviving={len(weights)}  "
            f"weight={total:.2f}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--env-file")
    args = ap.parse_args()
    if args.env_file:
        from dotenv import load_dotenv
        load_dotenv(args.env_file)

    import pandas as pd
    import psycopg2
    from app.core.db import get_database_url_sync
    from compute.engine import applicability as ap_mod
    from compute.engine import composite_score as cs
    from compute.engine.factor_model import composite_for
    from compute.engine.metric_states import LATEST_MODEL_VERSION

    spec = composite_for(LATEST_MODEL_VERSION)
    floor = getattr(spec, "min_effective_weight_fraction", None)

    conn = psycopg2.connect(get_database_url_sync())
    try:
        print(f"live model version : {LATEST_MODEL_VERSION}")
        print(f"composite floor    : {floor}  "
              f"({len(spec.constituents)} factors at "
              f"{spec.constituents[0].weight:.2f} each)")

        print("\n── A: the live rules ──")
        a_frame, a_states = _capture(cs, conn)

        print("\n── B: + an unstated currency treated as a mismatch ──")
        real_gate = ap_mod.unit_gate

        def strict_gate(metric, reporting_currency, model_version=None):
            reason = ap_mod.cross_currency_for(model_version).get(metric)
            if reason is None:
                return None
            stated = (reporting_currency or "").strip().upper()
            if stated == ap_mod.BASE_CURRENCY:
                return None
            return (ap_mod.Applicability.NOT_MEANINGFUL,
                    reason.format(currency=stated or "an unstated currency"))

        try:
            ap_mod.unit_gate = strict_gate
            b_frame, b_states = _capture(cs, conn)
        finally:
            ap_mod.unit_gate = real_gate

        common = a_frame.index.intersection(b_frame.index)
        a_comp = pd.to_numeric(a_frame.loc[common, "composite_score"],
                               errors="coerce")
        b_comp = pd.to_numeric(b_frame.loc[common, "composite_score"],
                               errors="coerce")
        gained = [c for c in common if pd.isna(a_comp[c])
                  and not pd.isna(b_comp[c])]
        lost = [c for c in common if not pd.isna(a_comp[c])
                and pd.isna(b_comp[c])]

        print("\n" + "=" * 72)
        print(f"COMPOSITES GAINED: {len(gained)}    LOST: {len(lost)}")
        print("=" * 72)
        if not gained:
            print("  No row gained a composite. The five seen earlier were "
                  "measured when V3 was live and fcf_yield was ungated; the "
                  "hypothesis cannot be tested against a population that no "
                  "longer exists, and this says so rather than inventing one.")

        for code in gained:
            print(f"\n  {code}:  composite {a_comp[code]} -> {b_comp[code]}")
            crossed = []
            for f in FACTORS:
                da = _describe(a_states, f, code)
                db = _describe(b_states, f, code)
                mark = "  <-- CHANGED" if da != db else ""
                print(f"      {f:<9} A: {da}")
                print(f"      {'':<9} B: {db}{mark}")
                if da != db:
                    crossed.append(f)
            print(f"      factors whose eligibility changed: "
                  f"{crossed or 'none'}")
            if not crossed:
                print("      ** The composite changed with NO factor "
                      "eligibility change, so the hypothesis does not "
                      "explain this row.")

        for code in lost[:5]:
            print(f"\n  LOST {code}: composite {a_comp[code]} -> withheld")
            for f in FACTORS:
                da, db = _describe(a_states, f, code), _describe(b_states, f, code)
                if da != db:
                    print(f"      {f}: {da}  ->  {db}")

        conn.rollback()
        print("\nread-only, rolled back")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
