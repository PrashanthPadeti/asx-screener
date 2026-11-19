#!/usr/bin/env python
"""
V4 activation: capture the expectation, then reconcile production to it.
========================================================================
`--emit` runs the REAL scoring path from the candidate tree, under
FACTOR_MODEL_V4, against production inputs, and records per row what V4 will
publish: the five factor scores, the composite, the composite rank, and
`fcf_yield` as masked (suppressed -> NULL). Read-only.

`--verify` reconciles the served universe against that expectation after the
V4 canonical run, by identity and value, and additionally proves what a
per-row value check cannot see:

  * deployment identity: the deployed producer IS the intended candidate
  * the publication is attributed to FACTOR_MODEL_V4, by exactly one run
  * the artifact, the publishing run's recorded input fingerprint and the
    live inputs all agree -- or the comparison is VOID, not failed
  * population equality in BOTH directions
  * suppressed `fcf_yield` rows carry a sidecar entry with a unit-mismatch
    cause, so a null has a recorded reason
  * the finalised V1-V3 run records are byte-identical, because activation
    must not rewrite what published runs claimed

Exit contract: 0 pass, 1 mismatch, 2 void.

A MISMATCH IS A DISAGREEMENT TO INVESTIGATE, not a located fault. v11.2.86
reported two of 471 rows differing and the comparator was wrong, not the
producer.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

PRODUCER_MODULES = ("yearly_compute.py", "periods.py", "applicability.py",
                    "metric_states.py", "factor_model.py",
                    "factor_applicability.py", "composite_score.py")

FACTORS = ["value_score", "quality_score", "growth_score",
           "momentum_score", "income_score"]


def _digest_of(root: Path):
    """sha256 over the declared producer set in a tree, or None.

    Wider than the price-anchor set deliberately: activation's behaviour is
    decided by the model registry, the governed registry, the applicability
    gates and the scorer, so all of them are in the identity.
    """
    h = hashlib.sha256()
    for name in PRODUCER_MODULES:
        f = root / "compute" / "engine" / name
        if not f.is_file():
            return None
        h.update(name.encode())
        h.update(f.read_bytes())
    return h.hexdigest()


def _capture(cs, conn):
    """Run the real scoring path once; return the scored frame."""
    grabbed = {}
    real = cs.compute_composite

    def wrapper(df_scores, *a, **kw):
        out = real(df_scores, *a, **kw)
        cols = ["asx_code"] + [c for c in FACTORS if c in df_scores.columns]
        if "fcf_yield" in df_scores.columns:
            cols.append("fcf_yield")
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
            "compute_composite was never called, so nothing was captured. "
            "The scoring path changed shape and this instrument is measuring "
            "nothing -- the failure mode it must not have.")
    return grabbed["frame"]


def _runs_digest(cur, max_id=None):
    """A digest of the finalised run records, so activation cannot rewrite
    what published runs claimed.

    SCOPED TO THE IDS THAT EXISTED AT CAPTURE, which the first version was
    not: it hashed every row, so the activation run's own record -- the whole
    point of the release -- necessarily changed the digest and the comparison
    reported a defect in correct behaviour. The error message said the right
    thing ("new runs are expected, a CHANGED digest over the SAME ids is
    not") while the code hashed all of them, which is a comment describing an
    intention the implementation did not have.
    """
    if max_id is None:
        cur.execute("""
            SELECT id, run_at, factor_model_version, rows_written, plan_name
            FROM screener.compute_runs ORDER BY id
        """)
    else:
        cur.execute("""
            SELECT id, run_at, factor_model_version, rows_written, plan_name
            FROM screener.compute_runs WHERE id <= %s ORDER BY id
        """, (max_id,))
    rows = cur.fetchall()
    h = hashlib.sha256()
    for r in rows:
        h.update("|".join("" if v is None else str(v) for v in r).encode())
    return h.hexdigest(), len(rows), [r[0] for r in rows]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--env-file")
    ap.add_argument("--emit", metavar="PATH")
    ap.add_argument("--verify", metavar="PATH")
    ap.add_argument("--candidate", metavar="SHA")
    ap.add_argument("--deployed-root", default="/opt/asx-screener/backend")
    ap.add_argument("--frozen-max-id", type=int,
                    help="the highest run id that existed when the "
                         "expectation was captured. Needed only for an "
                         "expectation emitted BEFORE the snapshot started "
                         "recording frozen_runs_max_id -- the value comes "
                         "from that emit run's own log, not from a guess. "
                         "Newer snapshots carry it and this flag is unused.")
    args = ap.parse_args()
    if not (args.emit or args.verify):
        print("nothing to do: pass --emit or --verify")
        return 2
    if args.env_file:
        from dotenv import load_dotenv
        load_dotenv(args.env_file)

    import pandas as pd
    import psycopg2
    from app.core.db import get_database_url_sync
    from compute.engine import composite_score as cs
    from compute.engine import source_fingerprint as sfp
    from compute.engine.metric_states import LATEST_MODEL_VERSION

    conn = psycopg2.connect(get_database_url_sync())
    try:
        cur = conn.cursor()
        candidate_digest = _digest_of(BACKEND)
        deployed_digest = _digest_of(Path(args.deployed_root))
        live_fp = sfp.compute(cur)
        runs_hash, runs_n, runs_ids = _runs_digest(cur)

        print(f"model version in this tree : {LATEST_MODEL_VERSION}")
        print(f"candidate digest           : {(candidate_digest or '')[:32]}")
        print(f"deployed digest            : {(deployed_digest or '')[:32]}")
        print(f"live input aggregate       : {live_fp.aggregate[:32]}")
        print(f"finalised runs             : {runs_n} (through "
              f"{runs_ids[-1] if runs_ids else 'none'})")

        if args.emit:
            if LATEST_MODEL_VERSION != "FACTOR_MODEL_V4":
                print(f"\n** --emit must run from the ACTIVATION candidate. "
                      f"This tree is {LATEST_MODEL_VERSION}, so the "
                      f"expectation would describe V3's output.")
                conn.rollback()
                return 2
            frame = _capture(cs, conn)
            comp = pd.to_numeric(frame["composite_score"], errors="coerce")
            frame = frame.assign(
                composite_rank=comp.rank(ascending=False, method="min"))
            rows = {}
            for _, r in frame.iterrows():
                rows[r["asx_code"]] = {
                    c: (None if pd.isna(r.get(c)) else str(r.get(c)))
                    for c in FACTORS + ["fcf_yield", "composite_score",
                                        "composite_rank"]
                }
            payload = {
                "candidate": args.candidate or "(unrecorded)",
                "model_version": LATEST_MODEL_VERSION,
                "intended_candidate_digest": candidate_digest,
                "baseline_deployed_digest": deployed_digest,
                "capture_fingerprint_schema": live_fp.schema_version,
                "capture_fingerprint_aggregate": live_fp.aggregate,
                "frozen_runs_digest": runs_hash,
                "frozen_runs_count": runs_n,
                # The high-water mark, so a verify can re-digest the SAME ids
                # rather than all of them and call a new run a defect.
                "frozen_runs_max_id": (runs_ids[-1] if runs_ids else None),
                "producer_modules": list(PRODUCER_MODULES),
                "rows": rows,
            }
            Path(args.emit).write_text(json.dumps(payload), encoding="utf-8")
            suppressed = sum(1 for v in rows.values()
                             if v.get("fcf_yield") is None)
            print(f"\nwrote {len(rows)} expected rows to {args.emit}")
            print(f"    fcf_yield suppressed or absent in: {suppressed}")
            conn.rollback()
            return 0

        prior = json.loads(Path(args.verify).read_text(encoding="utf-8"))
        problems: list[str] = []
        voids: list[str] = []

        print("\n" + "=" * 72)
        print("ACCEPTANCE -- V4 activation")
        print("=" * 72)
        intended = prior.get("intended_candidate_digest")
        print(f"  snapshot model version : {prior.get('model_version')}")
        print(f"  intended digest        : {(intended or '')[:32]}")
        print(f"  deployed NOW           : {(deployed_digest or '')[:32]}")
        if intended is None or deployed_digest is None:
            problems.append("a digest is missing; deployment identity cannot "
                            "be established")
        elif deployed_digest != intended:
            problems.append(
                f"the deployed producer is not the intended candidate "
                f"(deployed {deployed_digest[:16]}, intended "
                f"{intended[:16]})")
        else:
            print("  deployment identity holds.")

        # The publishing run, and its attribution.
        cur.execute("""
            WITH a AS (SELECT DISTINCT compute_run_id AS run_id
                       FROM screener.universe
                       WHERE compute_run_id IS NOT NULL)
            SELECT (SELECT count(*) FROM a),
                   (SELECT max(run_id) FROM a),
                   (SELECT r.factor_model_version FROM screener.compute_runs r
                     JOIN a ON a.run_id = r.id),
                   (SELECT s.details->'yearly_source_fingerprint'
                             ->>'aggregate'
                    FROM screener.compute_run_stages s JOIN a
                      ON a.run_id = s.run_id
                    WHERE s.stage_name='yearly_compute'
                      AND s.status='success')
        """)
        n_runs, run_id, run_version, run_agg = cur.fetchone()
        print(f"\n  publishing run         : {run_id}  "
              f"({n_runs} distinct non-NULL)")
        print(f"  its model version      : {run_version}")
        print(f"  its input aggregate    : {(run_agg or '(none)')[:32]}")
        if n_runs != 1:
            problems.append(f"{n_runs} run ids attribute the universe")
        if run_version != "FACTOR_MODEL_V4":
            problems.append(
                f"the publication is attributed to {run_version}, not "
                f"FACTOR_MODEL_V4 -- activation did not take effect for the "
                f"run that published these rows")
        cap_agg = prior.get("capture_fingerprint_aggregate")
        if cap_agg != live_fp.aggregate:
            voids.append(
                f"the inputs moved (capture {(cap_agg or '')[:16]}, live "
                f"{live_fp.aggregate[:16]}). Recapture and repeat.")
        elif run_agg is not None and run_agg != cap_agg:
            voids.append(
                f"the publishing run read different inputs than the capture "
                f"({run_agg[:16]} vs {(cap_agg or '')[:16]})")

        # V1-V3 finalised records must be untouched.
        frozen_max = prior.get("frozen_runs_max_id") or args.frozen_max_id
        if frozen_max is not None:
            runs_hash, runs_n, _ = _runs_digest(cur, frozen_max)
            print(f"  re-digested runs <= {frozen_max}: {runs_n} rows")
        if prior.get("frozen_runs_digest") != runs_hash:
            problems.append(
                f"the finalised run records changed: "
                f"{prior.get('frozen_runs_count')} runs digested at capture, "
                f"{runs_n} now. New runs are expected -- a CHANGED digest "
                f"over the SAME ids is not, and that is what this catches.")
        else:
            print("  finalised run records unchanged.")

        # Per-row reconciliation.
        # THE SAME POPULATION THE EXPECTATION DESCRIBES.
        #
        # --emit captures the SCORED frame -- the rows composite_score
        # actually scores, 2,120 of them. The first version of this query read
        # every universe row, 2,578, and reported the 458 unattributed ones as
        # "added by the run". Two different populations compared as one, which
        # is the defect the population check exists to catch, committed by the
        # check itself.
        #
        # compute_run_id IS NOT NULL is that population: it is exactly what
        # the publishing run attributed, and the run reported the same count.
        cur.execute("""
            SELECT asx_code, value_score, quality_score, growth_score,
                   momentum_score, income_score, composite_score, fcf_yield,
                   metric_states
            FROM screener.universe
            WHERE compute_run_id IS NOT NULL
        """)
        served = {}
        sidecars = {}
        for r in cur.fetchall():
            served[r[0]] = dict(zip(FACTORS + ["composite_score",
                                               "fcf_yield"], r[1:9]))
            sidecars[r[0]] = r[8]

        want = prior.get("rows", {})
        extra = sorted(set(served) - set(want))
        missing = sorted(set(want) - set(served))
        print(f"\n  rows expected / served : {len(want)} / {len(served)}")
        print(f"  ADDED / REMOVED        : {len(extra)} / {len(missing)}")
        if extra or missing:
            problems.append(
                f"population differs: {len(extra)} added, {len(missing)} "
                f"removed. A value comparison over matching keys alone would "
                f"have reported this as clean.")

        differing = []
        no_reason = []
        for code in sorted(set(want) & set(served)):
            exp, got = want[code], served[code]
            for col in FACTORS + ["composite_score", "fcf_yield"]:
                e, g = exp.get(col), got.get(col)
                if (e is None) != (g is None):
                    differing.append((code, col, e, g))
                elif e is not None and abs(float(e) - float(g)) > 0.005:
                    differing.append((code, col, e, g))
            # A suppressed fcf_yield must carry a reason.
            if exp.get("fcf_yield") is None and got.get("fcf_yield") is None:
                sc = sidecars.get(code) or {}
                entry = sc.get("fcf_yield") if isinstance(sc, dict) else None
                if not entry:
                    no_reason.append(code)

        print(f"  rows differing         : {len(differing)}")
        print(f"  suppressed with NO sidecar reason : {len(no_reason)}")
        for d in differing[:10]:
            print(f"    {d[0]:<6} {d[1]:<16} expected {d[2]} served {d[3]}")
        for c in no_reason[:10]:
            print(f"    no reason  {c}")
        if differing:
            problems.append(f"{len(differing)} value disagreements")
        if no_reason:
            problems.append(
                f"{len(no_reason)} rows have a NULL fcf_yield with no sidecar "
                f"entry -- the unexplained null this release exists to avoid")

        print()
        if voids:
            print("  ** VOID -- verification remains OPEN, not failed")
            for v in voids:
                print("     - " + v)
            if problems:
                print("     (also: " + "; ".join(problems) + ")")
            conn.rollback()
            return 2
        if problems:
            print("  ** DOES NOT RECONCILE -- a mismatch to investigate; it "
                  "does not by itself locate the fault")
            for p_ in problems:
                print("     - " + p_)
            conn.rollback()
            return 1
        print("  RECONCILES: V4 is deployed and attributed, inputs agree, the "
              "population is")
        print("  identical, every row matches, every suppression carries a "
              "reason, and the")
        print("  finalised V1-V3 records are untouched.")
        conn.rollback()
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
