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
from compute.engine.daily_compute import fetch_feed_health  # noqa: E402
from compute.engine.dividends import FEED_STALENESS_DAYS  # noqa: E402
from compute.engine.metric_states import GOVERNED_METRICS  # noqa: E402
from compute.engine.serving_population import (  # noqa: E402
    SERVING_POPULATION, serving_predicate,
)
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

    # One idiom for every query below: f-string interpolation of predicates
    # bound here, before the first use. Mixing f-strings with .format() in one
    # expression evaluates the braces at definition time, which is how
    # {serving} raised NameError before .format could supply it.
    serving = serving_predicate()
    serving_u = serving_predicate("u")

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
    # Reported first and unprompted, because a source outage looks exactly
    # like a methodology regression in the factor table and must not share a
    # column with one.
    #
    # This block used to assert the outage rather than measure it. It printed
    # "Income is withheld universe-wide as UNAVAILABLE/SOURCE_UNHEALTHY"
    # unconditionally -- prose left over from the period when that was true --
    # while its own withdrawal table, thirty lines below, showed that cause
    # occurring zero times. And it derived staleness from an unbounded
    # max(ex_date), which counts announced future ex-dates: after the
    # September 2026 reload that produced "2026-12-16 (-93 days stale)", a
    # negative staleness that should have been unprintable.
    #
    # Both faults are the same fault. The engine already decides this, once,
    # in fetch_feed_health -- bounded above by CURRENT_DATE, with future
    # announcements counted separately because an announcement is not an
    # observation. A second copy of the judgement in the instrument that
    # audits it is worse than no copy: it can disagree with the run it is
    # describing and still sound authoritative.
    heading("STATED CONDITIONS")
    health = fetch_feed_health(cur)
    cur.execute("SELECT count(*) AS rows FROM market.dividends;")
    total_rows = cur.fetchone()["rows"]

    print(f"  dividend feed              : "
          f"{'HEALTHY' if health.healthy else 'UNHEALTHY'}")
    print(f"  latest occurred ex-date    : {health.latest_ex_date} "
          f"({health.lag_days} days behind, {total_rows:,} rows on file)")
    print(f"  breadth in last {FEED_STALENESS_DAYS} days     : "
          f"{health.recent_rows:,} rows / {health.recent_issuers:,} issuers")
    if health.future_announced:
        print(f"  announced, not yet occurred: {health.future_announced:,} "
              f"(counted separately; not freshness evidence)")
    if health.healthy:
        print("  => Income is computed. A non-payer over a fully observed "
              "window scores")
        print("     on a zero yield; it is not withheld. Any Income shortfall "
              "below is")
        print("     a finding, not a stated condition.")
    else:
        print(f"  => {health.reason}")
        print("  => Income is withheld universe-wide as "
              "UNAVAILABLE/SOURCE_UNHEALTHY.")
        print("     A correctly-reported source outage, not a V2 effect.")

    cur.execute(f"""
        SELECT count(*) AS universe,
               count(*) FILTER (WHERE status='active') AS active,
               count(*) FILTER (WHERE {serving}) AS servable,
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

    sidecars = row["with_sidecar"]
    runs_attributed = row["with_run"]
    if sidecars == 0:
        print("\n  *** NO SIDECAR WAS PERSISTED BY THIS RUN ***")
        print("  Every 'unexplained' count in the coverage table below is")
        print("  therefore 'no sidecar exists at all', NOT 'this metric lost")
        print("  its state'. The assessments were computed -- the domain tally")
        print("  is in the run log -- and then discarded at the writer.")
        print("  Read the coverage table with that in mind: it is measuring")
        print("  one defect, once, repeated per metric.")

    # ── Reporting history, the new observation ───────────────────────────────
    heading("REPORTING HISTORY (annual_periods)")
    print("  How many consecutive annual periods each company has reported.")
    print("  This is what separates INSUFFICIENT_HISTORY from SOURCE_MISSING,")
    print("  so its distribution decides how much of the avg_* withdrawal is")
    print("  the companies' record and how much is our feed.\n")
    cur.execute(f"""
        SELECT CASE WHEN annual_periods IS NULL THEN 'unknown (no FY0)'
                    WHEN annual_periods < 3 THEN '0-2  (no 3y average)'
                    WHEN annual_periods < 5 THEN '3-4  (3y only)'
                    WHEN annual_periods < 10 THEN '5-9  (3y and 5y)'
                    ELSE '10+' END AS band,
               count(*) AS companies
          FROM screener.universe WHERE {serving}
         GROUP BY 1 ORDER BY 1;""")
    for r in cur.fetchall():
        print(f"  {r['band']:24} {r['companies']:>6,}")

    # ── Coverage, V1 set vs V2 set ───────────────────────────────────────────
    heading("COVERAGE BY GOVERNED METRIC")
    print("  populated = the column holds a value. withheld = it does not and")
    print("  the sidecar says why. A metric with neither is the condition")
    print("  Gate A exists to catch: an unexplained blank.\n")
    print(f"  {'metric':32} {'ver':4} {'populated':>9} {'withheld':>9} {'unexplained':>11}")

    # A governed metric whose column does not exist on screener.universe is
    # its own finding, not a crash. It means the contract governs something
    # the storage layer never provides, so no row can ever carry a value or a
    # state for it — and the coverage table below would be answering a
    # question about a column that isn't there.
    cur.execute("""
        SELECT column_name FROM information_schema.columns
         WHERE table_schema='screener' AND table_name='universe';""")
    universe_cols = {r[0] for r in cur.fetchall()}

    both = sorted(GOVERNED_METRICS[V2])
    no_column = sorted(m for m in both if column_for(m) not in universe_cols)
    if no_column:
        print(f"\n  GOVERNED WITH NO COLUMN ON screener.universe ({len(no_column)}):")
        for metric in no_column:
            print(f"    {metric:32} (expected column: {column_for(metric)})")
        print("    These cannot hold a value or a state. Excluded from the")
        print("    coverage table below, and counted as findings.\n")

    unexplained_total = 0
    for metric in both:
        col = column_for(metric)
        if col not in universe_cols:
            continue
        cur.execute(f"""
            SELECT count(*) FILTER (WHERE u.{col} IS NOT NULL) AS populated,
                   count(*) FILTER (WHERE u.{col} IS NULL
                                     AND u.metric_states ? %s) AS withheld,
                   count(*) FILTER (WHERE u.{col} IS NULL
                                     AND NOT (coalesce(u.metric_states,'{{}}'::jsonb) ? %s)
                                   ) AS unexplained
              FROM screener.universe u
             WHERE {serving_u};""", (metric, metric))
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
    cur.execute(f"""
        SELECT s.key AS metric, s.value->>'state' AS state,
               coalesce(s.value->>'cause','(none)') AS cause, count(*) AS n
          FROM screener.universe u,
               LATERAL jsonb_each(u.metric_states) s
         WHERE {serving_u}
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
    heading("SEMANTIC ANOMALIES")
    print("  Two dimensions, reported separately, because collapsing them into")
    print("  one boolean turns a single diagnosis into several defects.\n")
    print("    stored       the raw stored value meets the anomalous condition")
    print("    servable     ...and the metric's own state permits serving it\n")
    print("  The architecture stores the observation and governs at projection,")
    print("  so a stored anomaly is not by itself a customer-surface defect —")
    print("  it is forensic evidence, and stays useful even once the contract")
    print("  withholds the value. What must be zero is the servable column.\n")
    print("  'servable' here evaluates the metric state ONLY. Real servability")
    print("  also requires a supported model version, a finalised compute run,")
    print("  and the row attributed to it. None of those exist in this run, so")
    print("  the name is servable_by_metric_state and claims nothing more.\n")

    # (label, canonical metric, stored-anomaly predicate[, severity])
    #
    # DEFECT   a servable row breaches a rule the contract declares. Counts
    #          toward the run's failure, because the contract is supposed to
    #          have withheld it and did not.
    # SOURCING an observation worth reporting that no declared rule covers.
    #          Reported in its own right and never counted, because failing a
    #          run for it would train everyone to ignore the failure.
    DEFECT, SOURCING = "defect", "sourcing"
    checks = [
        ("banks carrying ev_to_ebitda", "ev_ebitda",
         "sector='Financials' AND ev_to_ebitda IS NOT NULL"),
        ("ev_to_ebitda stored as exactly zero", "ev_ebitda",
         "ev_to_ebitda = 0"),
        ("negative equity beside a positive ROE", "roe",
         "total_equity < 0 AND roe > 0"),
        ("piotroski_f_score written at all", "piotroski_f_score",
         "piotroski_f_score IS NOT NULL"),
        ("avg_roe_3y with fewer than 3 periods", "avg_roe_3y",
         "avg_roe_3y IS NOT NULL AND annual_periods < 3"),
        ("avg_roe_5y with fewer than 5 periods", "avg_roe_5y",
         "avg_roe_5y IS NOT NULL AND annual_periods < 5"),
        # Demoted to a sourcing observation, deliberately.
        #
        # A 3-year revenue CAGR above 1000% is not a contract breach. It is
        # arithmetically correct for a company going from near-zero revenue to
        # a real number -- an explorer's first shipment, a biotech's first
        # product -- and the applicability contract has no rule it violates,
        # so no state can withhold it and calling it a CUSTOMER-SURFACE DEFECT
        # made the run fail for something the contract never claimed to catch.
        #
        # A magnitude threshold is the wrong instrument for the real question,
        # which is whether the denominator year was a true observation or a
        # sourcing artifact. That needs the prior-year revenue, not a ceiling
        # on the ratio. Until such a check exists this is reported and not
        # counted.
        ("revenue CAGR beyond +1000%", "revenue_cagr_3y",
         "revenue_growth_3y_cagr > 10", SOURCING),
        ("composite scored while a factor's source failed", "composite_score",
         "composite_score IS NOT NULL AND income_score IS NULL"),
    ]

    print(f"  {'anomaly':46} {'stored':>7} {'servable':>9}  diagnosis")
    flagged = 0
    contract_absent_total = 0
    sourcing_notes = []
    for check in checks:
        label, metric, predicate = check[0], check[1], check[2]
        severity = check[3] if len(check) > 3 else DEFECT
        # A row is servable on this metric when its sidecar exists and carries
        # no entry for it: absent-from-the-sidecar means APPLICABLE. A NULL
        # sidecar is not the same as an empty one — it means no run ever
        # assessed the row, which the projector treats as withhold-everything.
        cur.execute(f"""
            SELECT count(*) AS stored,
                   count(*) FILTER (
                       WHERE metric_states IS NOT NULL
                         AND NOT (metric_states ? %s)) AS servable,
                   count(*) FILTER (WHERE metric_states IS NULL) AS no_contract
              FROM screener.universe
             WHERE {serving} AND ({predicate});""", (metric,))
        r = cur.fetchone()
        stored, servable, no_contract = r["stored"], r["servable"], r["no_contract"]

        if stored == 0:
            diagnosis = "clean"
        elif severity == SOURCING:
            # Reported, never counted. See the note on the check itself.
            diagnosis = "sourcing observation (not a contract breach)"
            if servable:
                sourcing_notes.append((label, servable))
        elif servable:
            diagnosis = "CUSTOMER-SURFACE DEFECT"
            flagged += 1
        elif no_contract == stored:
            diagnosis = "blocked: no applicability state on the row"
            contract_absent_total += 1
        else:
            diagnosis = "withheld by its own state (forensic only)"
        print(f"  {label:46} {stored:>7,} {servable:>9,}  {diagnosis}")

    if sourcing_notes:
        print("\n  Sourcing observations — reported, not counted as defects:")
        for label, n in sourcing_notes:
            print(f"    {n:,} rows: {label}")
        print("  No declared rule covers these, so no applicability state can")
        print("  withhold them. Failing the run for a rule we never wrote would")
        print("  teach everyone to ignore the failure.")

    if contract_absent_total:
        print(f"\n  {contract_absent_total} anomal{'y' if contract_absent_total == 1 else 'ies'} "
              f"read as blocked only because no row carries an applicability")
        print("  state. That is ONE defect — the sidecar is not persisted — not")
        print("  one per anomaly. Until it is fixed these rows are neither")
        print("  provably safe nor provably unsafe: the projector withholds them")
        print("  for want of a contract, not because anything assessed them.")

    # ── Factor coverage ──────────────────────────────────────────────────────
    heading("FACTOR COVERAGE")
    cur.execute(f"""
        SELECT count(*) FILTER (WHERE value_score IS NOT NULL)     AS value,
               count(*) FILTER (WHERE quality_score IS NOT NULL)   AS quality,
               count(*) FILTER (WHERE growth_score IS NOT NULL)    AS growth,
               count(*) FILTER (WHERE momentum_score IS NOT NULL)  AS momentum,
               count(*) FILTER (WHERE income_score IS NOT NULL)    AS income,
               count(*) FILTER (WHERE composite_score IS NOT NULL) AS composite
          FROM screener.universe WHERE {serving};""")
    r = cur.fetchone()
    print("  Compare against the V1 production figures recorded before the")
    print("  freeze. A fall is only a finding once its cause table above")
    print("  fails to account for it.\n")
    for name in ("value", "quality", "growth", "momentum", "income", "composite"):
        print(f"  {name:12} {r[name]:>6,}")

    heading("SUMMARY")
    print(f"  sidecars persisted:                     {sidecars:,}")
    print(f"  rows attributed to a compute run:       {runs_attributed:,}")
    print(f"  governed metrics with no column:        {len(no_column)}")
    print(f"  unexplained blanks on governed metrics: {unexplained_total:,}")
    print(f"  customer-surface defects (servable):    {flagged}")
    print(f"  anomalies blocked only by a missing state: {contract_absent_total}")
    print("  Publication remains disabled: this database is named by no")
    print("  application connection string.")
    print()
    if unexplained_total or flagged or contract_absent_total:
        print("  Non-zero. Findings to classify -- expected withdrawal or new")
        print("  defect -- before any production recompute. Note that anomalies")
        print("  blocked only by a missing state collapse into a single")
        print("  diagnosis, not one finding each.")
    else:
        print("  Clean. Coverage changes are all accounted for by a declared")
        print("  cause, and no red flag fired.")

    cur.close()
    conn.close()
    return 1 if (unexplained_total or flagged or no_column or not sidecars) else 0


if __name__ == "__main__":
    sys.exit(main())
