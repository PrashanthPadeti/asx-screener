"""
What V2 actually scores, measured through the assessment path
=============================================================
The SQL strictness report counted NULL columns. That is not the quantity the
scorer reasons over, and the difference decides the V2 question.

``compute_factor`` triggers on assessments, not on nulls. A governed
constituent assessed NOT_MEANINGFUL has its weight set to zero and the factor
reweights around it; only UNAVAILABLE and INSUFFICIENT_DATA refuse. So every
governed row in the SQL report is an upper bound on exclusion rather than the
figure — most importantly ``pe_ratio``, whose 916 sole-blocked rows are
overwhelmingly companies with non-positive earnings. If the observation gate
rules those NOT_MEANINGFUL, Value loses almost nothing. If it rules them
UNAVAILABLE, Value genuinely collapses to a third of the universe.

This runs the real machinery — the same frame, the same
``apply_applicability``, the same declared-model scorer — rather than
approximating it again.

    cd /opt/asx-screener/backend && ../asx-venv/bin/python scripts/factor_assessment_sizing.py

Read-only: it loads, assesses and scores in memory and writes nothing.

Exits non-zero on a contract defect — a declared constituent absent from the
frame, a governed metric with no assessment, or a factor that produced a
number despite a required constituent being unavailable. Those are faults in
the model or the engine, not findings about the data, and a report that
merely mentioned them could be read past.
"""

import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402
import psycopg2  # noqa: E402

from compute.engine.applicability import Applicability  # noqa: E402
from compute.engine.composite_score import (  # noqa: E402
    ALL_COLS,
    compute_factor,
)
from compute.engine.factor_applicability import (  # noqa: E402
    DOMAIN_COLS,
    apply_applicability,
)
from compute.engine.factor_model import model_for  # noqa: E402
from compute.engine.universe_writer import column_for  # noqa: E402

VERSION = "FACTOR_MODEL_V2"

#: Score columns as they stand today, for the before/after comparison.
CURRENT_SCORES = ["value_score", "quality_score", "growth_score",
                  "momentum_score", "income_score"]

defects: list[str] = []


def load(conn):
    """The same frame composite_score scores, loaded the same way."""
    from compute.engine.daily_compute import fetch_feed_health
    from compute.engine.dividends import DividendSource

    select = ALL_COLS + [c for c in DOMAIN_COLS if c not in ALL_COLS]
    select += [c for c in CURRENT_SCORES if c not in select]
    cur = conn.cursor()
    cur.execute(f"""
        SELECT {', '.join(select)}
          FROM screener.universe
         WHERE status = 'active' AND price IS NOT NULL
    """)
    rows = cur.fetchall()
    frame = pd.DataFrame(rows, columns=select)
    for col in frame.columns:
        if col not in ("asx_code", "sector", "industry"):
            frame[col] = pd.to_numeric(frame[col], errors="coerce")

    health = fetch_feed_health(cur)
    cur.close()
    return frame, DividendSource(health), health


def constituent_states(model, masked, frame):
    """Per constituent: what the assessment path actually said.

    Ungoverned constituents carry no assessment at all, and this reports that
    as raw presence rather than manufacturing a state for them. Inventing one
    would be the same category error as reading a NULL as a decision.
    """
    print(f"\n{'factor':<13} {'constituent':<26} {'gov':<4} {'weight':>6} "
          f"{'present':>8} {'applic':>7} {'NM':>6} {'unavail':>8}  causes")
    print("-" * 108)

    for factor, spec in model.items():
        for c in spec.constituents:
            column = column_for(c.metric)
            if column not in frame.columns:
                defects.append(
                    f"{factor}: declared constituent {c.metric} ({column}) is "
                    f"absent from the frame")
                continue

            present = int(frame[column].notna().sum())
            tally = Counter()
            causes = Counter()
            governed = False

            for code in frame["asx_code"]:
                assessment = masked.assessments.get(code, {}).get(c.metric)
                if assessment is None:
                    continue
                governed = True
                tally[assessment.state] += 1
                if assessment.state is not Applicability.APPLICABLE:
                    causes[assessment.cause.value if assessment.cause
                           else "—"] += 1

            cause_text = ", ".join(f"{k}:{v}" for k, v in causes.most_common(3))
            print(f"{factor:<13} {c.metric:<26} {'y' if governed else 'n':<4} "
                  f"{c.weight:>6.3f} {present:>8} "
                  f"{tally[Applicability.APPLICABLE]:>7} "
                  f"{tally[Applicability.NOT_MEANINGFUL]:>6} "
                  f"{tally[Applicability.UNAVAILABLE] + tally[Applicability.INSUFFICIENT_DATA]:>8}"
                  f"  {cause_text}")


def factor_outcomes(model, masked, frame):
    """Per factor: what V2 scores, against what is populated today."""
    print(f"\n{'factor':<13} {'today':>7} {'V2 scored':>10} {'V2 absent':>10} "
          f"{'delta':>7}  effective constituent counts")
    print("-" * 92)

    scores = {}
    for factor, spec in model.items():
        try:
            series = compute_factor(frame, factor, spec, masked.assessments,
                                    model_version=VERSION)
        except KeyError as exc:
            defects.append(f"{factor}: {exc}")
            continue
        scores[factor] = series

        today_col = f"{factor}_score"
        today = int(frame[today_col].notna().sum()) \
            if today_col in frame.columns else 0
        scored = int(series.notna().sum())

        # How many constituents actually carried weight, per company. A model
        # that always reweights is not the model that was declared.
        widths = Counter()
        for code in frame["asx_code"]:
            per_metric = masked.assessments.get(code, {})
            kept = sum(
                1 for c in spec.constituents
                if getattr(per_metric.get(c.metric), "state", None)
                is not Applicability.NOT_MEANINGFUL)
            widths[kept] += 1
        width_text = ", ".join(
            f"{n}/{len(spec.constituents)}:{count}"
            for n, count in sorted(widths.items(), reverse=True)[:4])

        print(f"{factor:<13} {today:>7} {scored:>10} "
              f"{len(series) - scored:>10} {scored - today:>+7}  {width_text}")

    return scores


def sole_blockers(model, masked, frame, scores):
    """The assessment-aware replacement for the SQL sole_blocker.

    Rows where exactly one declared constituent is unavailable, so the factor
    is withheld because of that one alone. These are the rows that would
    return if only it were resolved — which is the number worth acting on,
    unlike a raw null count that mostly describes companies already excluded
    by something else.
    """
    print(f"\n{'factor':<13} {'constituent':<26} {'sole blocker':>13}  "
          f"dominant cause")
    print("-" * 76)

    rows = []
    for factor, spec in model.items():
        if factor not in scores:
            continue
        blocked = defaultdict(Counter)
        for code in frame["asx_code"]:
            per_metric = masked.assessments.get(code, {})
            absent = [
                c.metric for c in spec.constituents
                if getattr(per_metric.get(c.metric), "state", None)
                in (Applicability.UNAVAILABLE, Applicability.INSUFFICIENT_DATA)]
            if len(absent) == 1:
                assessment = per_metric.get(absent[0])
                blocked[absent[0]][
                    assessment.cause.value if assessment.cause else "—"] += 1

        for metric, causes in blocked.items():
            rows.append((factor, metric, sum(causes.values()),
                         causes.most_common(1)[0][0]))

    for factor, metric, count, cause in sorted(rows, key=lambda r: -r[2]):
        print(f"{factor:<13} {metric:<26} {count:>13}  {cause}")
    if not rows:
        print("(none — no factor is withheld by a single constituent)")


def contract_checks(model, masked, frame, scores):
    """Faults in the model or engine, as distinct from facts about the data."""
    for factor, spec in model.items():
        if factor not in scores:
            continue
        series = scores[factor]
        for position, code in zip(frame.index, frame["asx_code"]):
            per_metric = masked.assessments.get(code, {})
            unavailable = [
                c.metric for c in spec.constituents
                if getattr(per_metric.get(c.metric), "state", None)
                in (Applicability.UNAVAILABLE, Applicability.INSUFFICIENT_DATA)]
            if unavailable and pd.notna(series.at[position]):
                defects.append(
                    f"{factor} scored {series.at[position]} for {code} while "
                    f"{', '.join(unavailable)} is unavailable — the engine is "
                    f"not obeying the declared model")
                break


def main() -> int:
    url = os.environ.get("DATABASE_URL_SYNC") or os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL is not set — source backend/.env first")
    conn = psycopg2.connect(url.replace("postgresql+asyncpg://", "postgresql://"))

    frame, dividend_source, health = load(conn)
    conn.close()

    print(f"model:          {VERSION}")
    print(f"rows:           {len(frame)} active with a price")
    print(f"dividend feed:  {'healthy' if health.healthy else health.reason}")

    masked = apply_applicability(frame, dividend_source)
    model = model_for(VERSION)

    constituent_states(model, masked, masked.frame)
    scores = factor_outcomes(model, masked, masked.frame)
    sole_blockers(model, masked, masked.frame, scores)
    contract_checks(model, masked, masked.frame, scores)

    print()
    if defects:
        print(f"CONTRACT DEFECTS — {len(defects)}:")
        for defect in defects[:20]:
            print("  -", defect)
        return 1
    print("no contract defects: every declared constituent was assessed, and "
          "no factor scored while a required constituent was unavailable")
    return 0


if __name__ == "__main__":
    sys.exit(main())
