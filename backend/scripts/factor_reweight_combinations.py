"""
Which models survive reweighting, and for whom
==============================================
Domain reweighting is legitimate: a bank has no meaningful leverage ratio, and
scoring it against one was the original defect. But unlimited reweighting
creates a new failure of the same kind one level down —

    a factor may keep its name after most of its declared economic dimensions
    have disappeared.

A five-signal Value model evaluated from two signals is not necessarily wrong,
but it is no longer obviously that model.

The aggregate count says 494 companies score Value on two of five. That number
alone cannot support a floor. What matters is whether those 494 are one
coherent economic class — in which case the surviving pair may be exactly the
right description of them — or dozens of accidental combinations, in which case
the factor has quietly become many different models sharing a column name.

So this reports combinations rather than counts: the surviving constituent set,
the retained nominal weight, and the domain, grouped and counted.

    cd /opt/asx-screener/backend && ../asx-venv/bin/python scripts/factor_reweight_combinations.py

Read-only.

Companies with any UNAVAILABLE constituent are excluded from this report
entirely. Those factors are already refused and no floor applies to them —
mixing them in would inflate the low-coverage rows with companies whose
problem is missing evidence rather than narrowed applicability.
"""

import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402
import psycopg2  # noqa: E402

from compute.engine.applicability import Applicability  # noqa: E402
from compute.engine.composite_score import ALL_COLS  # noqa: E402
from compute.engine.domain_resolver import resolve_domain  # noqa: E402
from compute.engine.factor_applicability import (  # noqa: E402
    DOMAIN_COLS,
    OBSERVATION_COLS,
    apply_applicability,
)
from compute.engine.factor_model import model_for  # noqa: E402

VERSION = "FACTOR_MODEL_V2"
#: Rows per factor in the combination table. Enough to see whether the tail is
#: a handful of classes or a long list of accidents.
TOP_N = 12


def load(conn):
    from compute.engine.daily_compute import fetch_feed_health
    from compute.engine.dividends import DividendSource

    select = ALL_COLS + [c for c in DOMAIN_COLS if c not in ALL_COLS]
    select += [c for c in OBSERVATION_COLS.values() if c not in select]
    cur = conn.cursor()
    cur.execute(f"""
        SELECT {', '.join(select)}
          FROM screener.universe
         WHERE status = 'active' AND price IS NOT NULL
    """)
    frame = pd.DataFrame(cur.fetchall(), columns=select)
    for col in frame.columns:
        if col not in ("asx_code", "sector", "industry"):
            frame[col] = pd.to_numeric(frame[col], errors="coerce")
    health = fetch_feed_health(cur)
    cur.close()
    return frame, DividendSource(health)


def main() -> int:
    url = os.environ.get("DATABASE_URL_SYNC") or os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL is not set — source backend/.env first")
    conn = psycopg2.connect(url.replace("postgresql+asyncpg://", "postgresql://"))
    frame, dividend_source = load(conn)
    conn.close()

    masked = apply_applicability(frame, dividend_source)
    model = model_for(VERSION)

    domains = {row["asx_code"]: resolve_domain(row).domain.value
               for _, row in frame.iterrows()}

    for factor, spec in model.items():
        nominal = {c.metric: c.weight for c in spec.constituents}
        combos: dict[tuple, Counter] = defaultdict(Counter)
        refused = 0
        weight_bands = Counter()

        for code in frame["asx_code"]:
            per_metric = masked.assessments.get(code, {})
            states = {c.metric: getattr(per_metric.get(c.metric), "state", None)
                      for c in spec.constituents}

            if any(s in (Applicability.UNAVAILABLE,
                         Applicability.INSUFFICIENT_DATA)
                   for s in states.values()):
                refused += 1
                continue

            kept = tuple(sorted(
                m for m, s in states.items()
                if s is not Applicability.NOT_MEANINGFUL))
            retained = sum(nominal[m] for m in kept)
            combos[kept][domains.get(code, "?")] += 1
            weight_bands[round(retained, 3)] += 1

        total = sum(sum(d.values()) for d in combos.values())
        print(f"\n=== {factor} — {len(spec.constituents)} declared, "
              f"{total} reweight-eligible, {refused} already refused ===")

        if not combos:
            print("  (every company has an unavailable constituent)")
            continue

        print(f"  {'retained':>8}  {'weight':>7}  {'n':>5}  "
              f"{'domains':<34}  surviving constituents")
        print("  " + "-" * 104)

        ranked = sorted(combos.items(),
                        key=lambda kv: -sum(kv[1].values()))
        for kept, by_domain in ranked[:TOP_N]:
            retained = sum(nominal[m] for m in kept)
            n = sum(by_domain.values())
            domain_text = ", ".join(f"{d}:{c}"
                                    for d, c in by_domain.most_common(3))
            print(f"  {len(kept):>3}/{len(spec.constituents):<4}  "
                  f"{retained:>7.2f}  {n:>5}  {domain_text:<34}  "
                  f"{', '.join(kept) if kept else '(none)'}")
        if len(ranked) > TOP_N:
            tail = sum(sum(d.values()) for _, d in ranked[TOP_N:])
            print(f"  ... {len(ranked) - TOP_N} further combinations, "
                  f"{tail} companies")

        # What a floor would cost, at each candidate threshold. Stated as
        # retained nominal weight rather than count, because counts only
        # coincide with weight while every constituent is equally weighted.
        print(f"\n  floor          companies scored   companies withheld")
        for floor in (0.0, 0.4, 0.5, 0.6, 0.8):
            scored = sum(n for w, n in weight_bands.items() if w > floor)
            print(f"  > {floor:<11.2f}  {scored:>16}  {total - scored:>18}")

    print("\nA floor rejects companies whose declared model has mostly "
          "disappeared. It is NOT_MEANINGFUL, not UNAVAILABLE: nothing is "
          "missing, the factor simply has too few applicable dimensions left "
          "to be the model it names.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
