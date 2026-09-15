#!/usr/bin/env python
"""
Does the quantiser round the way PostgreSQL rounds?
===================================================
The full-population read-back validator compares canonical intent against what
the database holds. Intent is a full-precision Python float; the column stores
it at a declared scale. So intent must be put through the same rounding the
column applies, or every row reports a mismatch and publication is blocked
forever for something that is not a defect.

A fake cursor cannot answer whether that rounding agrees. In particular:

    Python  Decimal.quantize()  defaults to ROUND_HALF_EVEN (banker's)
    Postgres NUMERIC            rounds half AWAY FROM ZERO

If that is so, 0.1234565 at scale 6 is 0.123456 in Python and 0.123457 in
PostgreSQL, and only exact ties expose it — which means the discovery run
would find it, at 25 minutes a cycle, on whichever rows happened to land on a
boundary.

This probe asks the database directly. It writes nothing: every value is cast
in a SELECT, so it is safe against any database including production, though
scratch is the right target.

    python scripts/p0a_quantise_probe.py
    python scripts/p0a_quantise_probe.py --database asx_screener_scratch

Exit 0 means the quantiser and PostgreSQL agree on every probed boundary for
every scale the contract actually persists. Exit 1 names the disagreements.
"""

from __future__ import annotations

import argparse
import sys
from decimal import Decimal, ROUND_HALF_EVEN, ROUND_HALF_UP
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import psycopg2  # noqa: E402

from app.core.db import get_database_url_sync  # noqa: E402
from compute.engine.canonical_readback import quantise  # noqa: E402
from compute.engine.metric_states import LATEST_MODEL_VERSION  # noqa: E402
from compute.engine.universe_writer import (  # noqa: E402
    column_for, governed_for,
)


def boundary_values(precision: int, scale: int) -> list[float]:
    """Values that sit exactly on, just below and just above a rounding tie.

    A tie is the only place two rounding modes can disagree, so probing
    anything else would pass under either and prove nothing.

    Bounded by the type's own capacity. NUMERIC(p,s) holds p-s integer digits,
    so NUMERIC(8,6) must stay under 100 — a fixed set of bases overflowed it
    and killed the probe before it measured anything. The persisted scales run
    from 0 to 6 and precisions from 5 to 18, so the generator has to read the
    type rather than assume a shape.
    """
    max_int_digits = precision - scale
    limit = Decimal(10) ** max_int_digits
    half = Decimal(5) * Decimal(10) ** -(scale + 1)
    eps = Decimal(10) ** -(scale + 2)

    out: list[float] = []
    for base in (Decimal(0), Decimal("0.1"), Decimal(1),
                 Decimal("12.34"), Decimal(999)):
        for sign in (1, -1):
            for delta in (half, half + eps, half - eps):
                value = sign * (base + delta)
                # Margin of one unit: the value must still fit AFTER rounding up.
                if abs(value) < limit - 1:
                    out.append(float(value))

    # A tie landing on an even last digit and one on an odd last digit, since
    # ROUND_HALF_EVEN only differs on one of them. Meaningless at scale 0.
    if scale >= 1:
        out.append(float(Decimal(f"0.{'0' * (scale - 1)}25")))
        out.append(float(Decimal(f"0.{'0' * (scale - 1)}35")))

    return sorted(set(out))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--database", help="override the database name")
    args = ap.parse_args()

    url = get_database_url_sync()
    if args.database:
        url = url.rsplit("/", 1)[0] + "/" + args.database

    conn = psycopg2.connect(url)
    cur = conn.cursor()
    cur.execute("SELECT current_database()")
    print(f"database: {cur.fetchone()[0]}\n")

    # Only the scales the contract actually persists. Probing scales nothing
    # uses would invent a requirement.
    columns = [column_for(m) for m in sorted(governed_for(LATEST_MODEL_VERSION))]
    cur.execute("""
        SELECT DISTINCT numeric_precision, numeric_scale
          FROM information_schema.columns
         WHERE table_schema = 'screener' AND table_name = 'universe'
           AND column_name = ANY(%s) AND numeric_scale IS NOT NULL
         ORDER BY numeric_precision, numeric_scale
    """, (columns,))
    types = cur.fetchall()
    print(f"persisted numeric types: "
          f"{', '.join(f'NUMERIC({p},{s})' for p, s in types)}\n")

    disagreements: list[str] = []
    skipped: list[str] = []
    probed = 0
    half_even_ok = half_up_ok = True

    for precision, scale in types:
        for value in boundary_values(precision, scale):
            # Exactly the path the writer takes: a Python float parameter,
            # adapted by psycopg2, cast by the column's type.
            try:
                cur.execute(
                    f"SELECT (%s::float8)::numeric({precision},{scale})",
                    (value,))
                pg = cur.fetchone()[0]
            except psycopg2.Error as e:
                # A value this type cannot hold is a defect in the generator,
                # not a finding about rounding. Record it and carry on: a probe
                # that dies on one input measures nothing about the rest, which
                # is how the first version of this script reported nothing at
                # all after NUMERIC(8,6) rejected 999.
                conn.rollback()
                skipped.append(
                    f"  NUMERIC({precision},{scale})  input={value!r} "
                    f"rejected: {str(e).splitlines()[0]}")
                continue

            # The validator's actual comparison, end to end: intent quantised
            # on one side, the stored value read back and quantised on the
            # other. This is what answers "does PostgreSQL return values such
            # that normalisation produces the same canonical representation as
            # intent" — psycopg2 may hand back Decimal, or float if a
            # DEC2FLOAT adapter is registered, and both must normalise alike.
            probed += 1
            ours = quantise(value, scale)
            round_tripped = quantise(pg, scale)
            if ours != round_tripped:
                disagreements.append(
                    f"  NUMERIC({precision},{scale})  input={value!r:>24}  "
                    f"intent_norm={ours}  readback_norm={round_tripped}  "
                    f"(pg returned {type(pg).__name__})")
                continue

            he = str(Decimal(str(value)).quantize(
                Decimal(1).scaleb(-scale), rounding=ROUND_HALF_EVEN))
            hu = str(Decimal(str(value)).quantize(
                Decimal(1).scaleb(-scale), rounding=ROUND_HALF_UP))

            if Decimal(he) != pg:
                half_even_ok = False
            if Decimal(hu) != pg:
                half_up_ok = False
            if Decimal(ours) != pg:
                disagreements.append(
                    f"  NUMERIC({precision},{scale})  input={value!r:>24}  "
                    f"postgres={pg}  quantise={ours}")

    print(f"values probed                      : {probed}")
    print(f"ROUND_HALF_EVEN matches PostgreSQL : {half_even_ok}")
    print(f"ROUND_HALF_UP   matches PostgreSQL : {half_up_ok}")
    print(f"current quantise() disagreements   : {len(disagreements)}")
    print(f"values the type rejected (skipped) : {len(skipped)}\n")

    for line in skipped[:10]:
        print(line)
    if skipped:
        print()

    if probed == 0:
        print("FAIL — nothing was probed. The generator produced no value any "
              "of these types would accept, so this run proves nothing.")
        cur.close()
        conn.close()
        return 1

    for line in disagreements[:40]:
        print(line)
    if len(disagreements) > 40:
        print(f"  ... {len(disagreements) - 40} more")

    cur.close()
    conn.close()

    if disagreements:
        print("\nFAIL — the quantiser does not reproduce PostgreSQL's rounding. "
              "Every intended value landing on a tie would be reported as a "
              "payload mismatch, and publication would be blocked by the "
              "validator rather than by a defect.")
        return 1
    print("PASS — quantiser and PostgreSQL agree on every probed boundary.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
