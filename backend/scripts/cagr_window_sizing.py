"""
Exact-window CAGR sizing — how often is an n-year CAGR not n years?
===================================================================
The defect, stated narrowly because an earlier description of it was wrong:

    yearly_compute.cn(field, n) takes the prior value as yearly[i - n] —
    n ROWS back — and passes n to _cagr, which divides by n YEARS.

The series comes from financials.annual_pnl ordered by fiscal_year ASC, one
row per reported year. When a company's reported years are contiguous the two
agree. When a year is missing, n rows back is more than n years back, so the
growth is annualised over a shorter period than it actually spans and the
rate is understated.

It is NOT the case that a CAGR can be computed from fewer than n years: the
`i >= n` guard is on row count, so a short history yields None. The error is
one-directional — affected companies look like slower compounders than they
were, never faster.

This script measures, on real data, how many companies and how many stored
values that affects, and by how much. It reads only, writes nothing, and is
safe to run at any time.

    cd /opt/asx-screener/backend && ../asx-venv/bin/python scripts/cagr_window_sizing.py

The output decides V1 versus V2:

    negligible    ship V1 with the positional behaviour documented, and fix
                  the window in V2. A pinned model version is exactly the
                  mechanism for saying "this is what V1 meant".
    material      fix before the first canonical recompute, because a
                  persisted V1 would freeze the wrong semantics into a
                  contract that consumers are being told to trust.

"Material" is a judgement about the product, not a threshold this script
knows, so it reports the distribution rather than a verdict.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psycopg2  # noqa: E402
import psycopg2.extras  # noqa: E402

#: The windows yearly_compute actually asks for. Anything else is untested
#: territory and should not be inferred from this output.
WINDOWS = (3, 5, 7, 10)

#: The fields computed through cn(). Each is a separate stored column per
#: window, so the count of affected values scales with this list.
FIELDS = ("revenue", "net_profit", "eps", "ebitda", "fcf", "gross_profit",
          "book_value_per_share")

# One row per (company, end year, window) where the positional step of n rows
# does not equal n fiscal years. lag() measures the real distance between the
# two endpoints cn() would have used, which is the whole point: the compute
# trusts position, so the only way to size the error is to ask the data.
GAP_SQL = """
WITH series AS (
    SELECT asx_code,
           fiscal_year,
           lag(fiscal_year, %(n)s) OVER (PARTITION BY asx_code
                                          ORDER BY fiscal_year) AS prior_year
      FROM financials.annual_pnl
)
SELECT asx_code, fiscal_year, prior_year,
       fiscal_year - prior_year AS actual_span
  FROM series
 WHERE prior_year IS NOT NULL
   AND fiscal_year - prior_year <> %(n)s
"""

COVERAGE_SQL = """
SELECT count(DISTINCT asx_code) AS companies,
       count(*)                 AS rows,
       min(fiscal_year)         AS earliest,
       max(fiscal_year)         AS latest
  FROM financials.annual_pnl
"""

# Only companies in the active universe matter for the product decision: a
# delisted shell with a broken history affects nothing anyone sees.
ACTIVE_SQL = """
SELECT DISTINCT asx_code FROM screener.universe WHERE status = 'active'
"""


def connect():
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL is not set — source backend/.env first")
    # psycopg2 does not understand the +asyncpg driver suffix the app uses.
    return psycopg2.connect(url.replace("postgresql+asyncpg://", "postgresql://"))


def main() -> int:
    conn = connect()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    cur.execute(COVERAGE_SQL)
    cov = cur.fetchone()
    print(f"financials.annual_pnl: {cov['rows']} rows, "
          f"{cov['companies']} companies, {cov['earliest']}-{cov['latest']}")

    cur.execute(ACTIVE_SQL)
    active = {r["asx_code"] for r in cur.fetchall()}
    print(f"active universe:       {len(active)} companies")
    print()

    print(f"{'window':>7}  {'affected pairs':>14}  {'companies':>9}  "
          f"{'active':>6}  {'spans':<22}  worst")
    print("-" * 86)

    totals = {"pairs": 0, "companies": set(), "active": set()}

    for n in WINDOWS:
        cur.execute(GAP_SQL, {"n": n})
        rows = cur.fetchall()

        companies = {r["asx_code"] for r in rows}
        active_hit = companies & active
        spans: dict[int, int] = {}
        for r in rows:
            spans[r["actual_span"]] = spans.get(r["actual_span"], 0) + 1

        # The understatement factor: a rate annualised over n when the span is
        # actually s is wrong by a power of s/n, so the reported CAGR is
        # (1+r)^(n/s) - 1 instead of r. Reporting the span ratio keeps this
        # honest without pretending to know each company's true rate.
        worst = max(spans) if spans else n
        span_text = ", ".join(f"{s}y:{c}" for s, c in sorted(spans.items())[:4])

        totals["pairs"] += len(rows)
        totals["companies"] |= companies
        totals["active"] |= active_hit

        print(f"{n:>7}  {len(rows):>14}  {len(companies):>9}  "
              f"{len(active_hit):>6}  {span_text:<22}  "
              f"{worst}y for a {n}y window")

    print("-" * 86)
    print(f"{'total':>7}  {totals['pairs']:>14}  {len(totals['companies']):>9}  "
          f"{len(totals['active']):>6}")
    print()

    # A pair is one (company, end year, window). Each one feeds every field
    # computed at that window, so the count of wrong stored values is larger
    # than the pair count — though only the latest year per company reaches
    # screener.universe.
    print(f"fields computed per window: {len(FIELDS)}  "
          f"({', '.join(FIELDS)})")
    print(f"upper bound on affected stored values in market.yearly_metrics: "
          f"{totals['pairs'] * len(FIELDS)}")

    # What actually reaches the product: screener.universe carries the most
    # recent fiscal year only, so this is the number a user could see.
    latest_hit = set()
    for n in WINDOWS:
        cur.execute(f"""
            WITH series AS (
                SELECT asx_code, fiscal_year,
                       lag(fiscal_year, %(n)s) OVER (PARTITION BY asx_code
                                                      ORDER BY fiscal_year)
                           AS prior_year,
                       row_number() OVER (PARTITION BY asx_code
                                           ORDER BY fiscal_year DESC) AS recency
                  FROM financials.annual_pnl
            )
            SELECT asx_code FROM series
             WHERE recency = 1 AND prior_year IS NOT NULL
               AND fiscal_year - prior_year <> %(n)s
        """, {"n": n})
        latest_hit |= {r["asx_code"] for r in cur.fetchall()}

    visible = latest_hit & active
    print()
    print(f"active companies whose LATEST year is affected: {len(visible)}"
          f"  ({100.0 * len(visible) / max(len(active), 1):.1f}% of the "
          f"active universe)")
    if visible:
        print("  " + ", ".join(sorted(visible)[:25])
              + (" ..." if len(visible) > 25 else ""))

    cur.close()
    conn.close()

    print()
    print("This is evidence, not a verdict. The V1/V2 decision is whether the "
          "visible count above is small enough to document rather than fix "
          "before the first persisted canonical run.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
