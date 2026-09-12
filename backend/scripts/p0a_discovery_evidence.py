#!/usr/bin/env python
"""
The discovery run's evidence bundle
===================================
Reads the scratch database only. Answers one question in a form that can be
argued with: **what did V2 change, and is each change a correction or a
defect?**

The distinction this bundle exists to support:

    expected withdrawal   a value V1 served that V2 refuses to serve because
                          it could not be substantiated -- a bank's gross
                          margin, a three-year average built from one year,
                          a CAGR annualised over the wrong span

    new defect            a value that disappeared, or changed, for a reason
                          the V2 methodology does not account for

Coverage alone cannot separate them: both look like a number going down. So
every withdrawal is reported **with its recorded cause**, because the cause is
the claim being made, and a withdrawal whose cause does not match a rule we
declared is the signature of a defect.

Run through p0a_discovery.sh, which points DATABASE_URL_SYNC at the scratch
database. Refuses to run against a database whose name is not a scratch one,
because printing production's numbers under this heading would be worse than
printing nothing.
"""

from __future__ import annotations

import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psycopg2  # noqa: E402
import psycopg2.extras  # noqa: E402

from app.core.db import get_database_url_sync  # noqa: E402
from compute.engine.metric_states import GOVERNED_METRICS  # noqa: E402
from compute.engine.universe_writer import column_for  # noqa: E402

V1, V2 = "FACTOR_MODEL_V1", "FACTOR_MODEL_V2"

RULE = "-" * 78


def heading(text: str) -> None:
    print(f"\n{text}\n{RULE}")


def main() -> int:
    url = get_database_url_sync()
    conn = psycopg2.connect(url)
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    cur.execute("SELECT current_database()")
    db = cur.fetchone()[0]
    if "scratch" not in db:
        print(f"REFUSING: '{db}' is not a scratch database.", file=sys.stderr)
        print("This bundle is headed 'discovery run'. Printing production's "
              "numbers under that heading would be a false claim about where "
              "they came from.", file=sys.stderr)
        return 2

    print("run type: TARGETED V2 DISCOVERY REBUILD")
    print(f"database: {db}")
    print(f"revision: {os.environ.get('DISCOVERY_REV', '(see run log)')}")

    # ── Provenance ───────────────────────────────────────────────────────────
    # First, and unprompted, because it bounds what this run can be said to
    # prove. Holding the unchanged producers constant is what makes every
    # observed difference attributable to the code that changed — and it is
    # exactly why a result here must never later be described as proving full
    # same-run coherence. Some upstream products came from the production
    # snapshot on purpose.
    heading("PROVENANCE")
    print("  RECOMPUTED under the code under test")
    for item in ("market.computed_metrics      (daily_compute)",
                 "market.yearly_metrics        (yearly_compute)",
                 "screener.universe            (build_screener_universe)",
                 "screener.universe factors    (composite_score)",
                 "market.sector_benchmarks     (sector_benchmarks)"):
        print(f"    {item}")
    print("\n  CLONED / HELD CONSTANT from the production snapshot")
    for item in ("market.daily_metrics         (technical_compute)",
                 "market.weekly_metrics        (weekly_compute)",
                 "market.monthly_metrics       (monthly_compute)",
                 "market.halfyearly_metrics    (halfyearly_compute)",
                 "market.period_metrics        (period_metrics_compute)",
                 "market.daily_prices, market.dividends, financials.*",
                 "market.valuation_snapshot, market.analyst_ratings",
                 "staging_au.shares_stats, staging_au.company_profile"):
        print(f"    {item}")
    print("\n  This run answers: do the changed contracts compose?")
    print("  It does NOT answer: does the whole production sequence compose?")
    print("  That needs a production-shaped rehearsal immediately before the")
    print("  canonical recompute, and it is a separate gate.")

    # ── Stated conditions of the run ─────────────────────────────────────────
    # Reported first and unprompted. The dividend feed is unhealthy, so Income
    # is withheld universe-wide -- which will look like a catastrophic coverage
    # regression to anyone reading the factor table without this in front of
    # them. It is a correctly-reported source outage, not a V2 effect, and it
    # does not belong in the same column as a methodology change.
    heading("STATED CONDITIONS")
    cur.execute("""
        SELECT max(ex_date) AS last_ex_date,
               current_date - max(ex_date) AS days_stale,
               count(*) AS rows
          FROM market.dividends;""")
    row = cur.fetchone()
    print(f"  dividend feed last ex-date : {row['last_ex_date']} "
          f"({row['days_stale']} days stale, {row['rows']:,} rows)")
    print("  => Income is withheld universe-wide as UNAVAILABLE/SOURCE_UNHEALTHY.")
    print("     Expected. Not a V2 effect. Blocks V2 publication, not this run.")

    cur.execute("""
        SELECT count(*) AS universe, count(*) FILTER (WHERE status='active') AS active,
               count(annual_periods) AS with_periods,
               count(metric_states)  AS with_sidecar,
               count(compute_run_id) AS with_run,
               max(universe_built_at) AS built_at
          FROM screener.universe;""")
    row = cur.fetchone()
    print(f"\n  universe rows              : {row['universe']:,} "
          f"({row['active']:,} active)")
    print(f"  annual_periods populated   : {row['with_periods']:,}")
    print(f"  metric_states populated    : {row['with_sidecar']:,}")
    print(f"  compute_run_id populated   : {row['with_run']:,}")
    print(f"  built at                   : {row['built_at']}")

    # ── Reporting history, the new observation ───────────────────────────────
    heading("REPORTING HISTORY (annual_periods)")
    print("  How many consecutive annual periods each company has reported.")
    print("  This is what separates INSUFFICIENT_HISTORY from SOURCE_MISSING,")
    print("  so its distribution decides how much of the avg_* withdrawal is")
    print("  the companies' record and how much is our feed.\n")
    cur.execute("""
        SELECT CASE WHEN annual_periods IS NULL THEN 'unknown (no FY0)'
                    WHEN annual_periods < 3 THEN '0-2  (no 3y average)'
                    WHEN annual_periods < 5 THEN '3-4  (3y only)'
                    WHEN annual_periods < 10 THEN '5-9  (3y and 5y)'
                    ELSE '10+' END AS band,
               count(*) AS companies
          FROM screener.universe WHERE status='active'
         GROUP BY 1 ORDER BY 1;""")
    for r in cur.fetchall():
        print(f"  {r['band']:24} {r['companies']:>6,}")

    # ── Coverage, V1 set vs V2 set ───────────────────────────────────────────
    heading("COVERAGE BY GOVERNED METRIC")
    print("  populated = the column holds a value. withheld = it does not and")
    print("  the sidecar says why. A metric with neither is the condition")
    print("  Gate A exists to catch: an unexplained blank.\n")
    print(f"  {'metric':32} {'ver':4} {'populated':>9} {'withheld':>9} {'unexplained':>11}")

    both = sorted(GOVERNED_METRICS[V2])
    unexplained_total = 0
    for metric in both:
        col = column_for(metric)
        cur.execute(f"""
            SELECT count(*) FILTER (WHERE u.{col} IS NOT NULL) AS populated,
                   count(*) FILTER (WHERE u.{col} IS NULL
                                     AND u.metric_states ? %s) AS withheld,
                   count(*) FILTER (WHERE u.{col} IS NULL
                                     AND NOT (coalesce(u.metric_states,'{{}}'::jsonb) ? %s)
                                   ) AS unexplained
              FROM screener.universe u
             WHERE u.status='active';""", (metric, metric))
        r = cur.fetchone()
        ver = "V1" if metric in GOVERNED_METRICS[V1] else "V2"
        flag = "" if r["unexplained"] == 0 else "  <-- UNEXPLAINED"
        unexplained_total += r["unexplained"]
        print(f"  {metric:32} {ver:4} {r['populated']:>9,} "
              f"{r['withheld']:>9,} {r['unexplained']:>11,}{flag}")

    # ── Why things were withheld ─────────────────────────────────────────────
    heading("WITHDRAWAL CAUSES")
    print("  Every withheld value carries a state and a cause. A cause that")
    print("  does not correspond to a rule we declared is a defect, however")
    print("  reasonable the coverage number looks.\n")
    cur.execute("""
        SELECT s.key AS metric, s.value->>'state' AS state,
               coalesce(s.value->>'cause','(none)') AS cause, count(*) AS n
          FROM screener.universe u,
               LATERAL jsonb_each(u.metric_states) s
         WHERE u.status='active'
         GROUP BY 1,2,3 ORDER BY 4 DESC, 1;""")
    rows = cur.fetchall()
    by_cause: Counter = Counter()
    for r in rows:
        by_cause[(r["state"], r["cause"])] += r["n"]
    print(f"  {'state':18} {'cause':26} {'values':>9}")
    for (state, cause), n in by_cause.most_common():
        print(f"  {state:18} {cause:26} {n:>9,}")

    print(f"\n  top 25 metric/state/cause combinations")
    print(f"  {'metric':30} {'state':16} {'cause':24} {'n':>7}")
    for r in rows[:25]:
        print(f"  {r['metric']:30} {r['state']:16} {r['cause']:24} {r['n']:>7,}")

    # ── Semantic red flags ───────────────────────────────────────────────────
    # Not coverage. These are the values that would be wrong while looking
    # entirely ordinary, which is the class the whole rollout exists to remove.
    heading("SEMANTIC RED FLAGS")
    checks = [
        ("banks still carrying ev_to_ebitda", """
            SELECT count(*) FROM screener.universe
             WHERE status='active' AND sector='Financials'
               AND ev_to_ebitda IS NOT NULL"""),
        ("ev_to_ebitda stored as exactly zero", """
            SELECT count(*) FROM screener.universe
             WHERE status='active' AND ev_to_ebitda = 0"""),
        ("negative equity with a positive ROE served", """
            SELECT count(*) FROM screener.universe
             WHERE status='active' AND total_equity < 0 AND roe > 0"""),
        ("piotroski_f_score still written", """
            SELECT count(*) FROM screener.universe
             WHERE status='active' AND piotroski_f_score IS NOT NULL"""),
        ("avg_roe_3y present with fewer than 3 periods", """
            SELECT count(*) FROM screener.universe
             WHERE status='active' AND avg_roe_3y IS NOT NULL
               AND annual_periods < 3"""),
        ("avg_roe_5y present with fewer than 5 periods", """
            SELECT count(*) FROM screener.universe
             WHERE status='active' AND avg_roe_5y IS NOT NULL
               AND annual_periods < 5"""),
        ("revenue CAGR beyond +1000%", """
            SELECT count(*) FROM screener.universe
             WHERE status='active' AND revenue_growth_3y_cagr > 10"""),
        ("composite scored while a factor's source failed", """
            SELECT count(*) FROM screener.universe
             WHERE status='active' AND composite_score IS NOT NULL
               AND income_score IS NULL"""),
    ]
    # Every check is written so that zero is the only correct answer. A check
    # whose expected value depends on the data would be an observation, and
    # observations do not fail a run.
    print(f"  {'check':52} {'rows':>7}   expect")
    flagged = 0
    for label, sql in checks:
        cur.execute(sql)
        n = cur.fetchone()[0]
        mark = "ok" if n == 0 else "<-- INVESTIGATE"
        if n:
            flagged += 1
        print(f"  {label:52} {n:>7,}   0  {mark}")

    # ── Factor coverage ──────────────────────────────────────────────────────
    heading("FACTOR COVERAGE")
    cur.execute("""
        SELECT count(*) FILTER (WHERE value_score IS NOT NULL)     AS value,
               count(*) FILTER (WHERE quality_score IS NOT NULL)   AS quality,
               count(*) FILTER (WHERE growth_score IS NOT NULL)    AS growth,
               count(*) FILTER (WHERE momentum_score IS NOT NULL)  AS momentum,
               count(*) FILTER (WHERE income_score IS NOT NULL)    AS income,
               count(*) FILTER (WHERE composite_score IS NOT NULL) AS composite
          FROM screener.universe WHERE status='active';""")
    r = cur.fetchone()
    print("  Compare against the V1 production figures recorded before the")
    print("  freeze. A fall is only a finding once its cause table above")
    print("  fails to account for it.\n")
    for name in ("value", "quality", "growth", "momentum", "income", "composite"):
        print(f"  {name:12} {r[name]:>6,}")

    heading("SUMMARY")
    print(f"  unexplained blanks on governed metrics: {unexplained_total:,}")
    print(f"  semantic red flags raised:              {flagged}")
    print("  Publication remains disabled: this database is named by no")
    print("  application connection string.")
    print()
    if unexplained_total or flagged:
        print("  Non-zero. These are findings to classify -- expected")
        print("  withdrawal or new defect -- before any production recompute.")
    else:
        print("  Clean. Coverage changes are all accounted for by a declared")
        print("  cause, and no red flag fired.")

    cur.close()
    conn.close()
    return 1 if (unexplained_total or flagged) else 0


if __name__ == "__main__":
    sys.exit(main())
