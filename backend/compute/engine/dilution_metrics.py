"""
Dilution metrics
================
Derives share-issuance measures from market.shares_history and writes them to
screener.universe.

Separates magnitude from persistence. A company issuing 20 percent once to fund
an acquisition and one issuing 7 percent every year produce a similar 3Y CAGR,
but for a compounding score the second is much the worse signal, so the count
of dilutive years is kept alongside the annualised rate.

Trust rules, from validating the raw history:
  * Share counts of 400, 1,800 and 2,500 appear for listed companies, and jumps
    of six orders of magnitude occur. These are consolidations that
    market.splits does not record - it covers 861 of roughly 2,100 stocks.
  * A consolidation read as a 99 percent buyback would score 100 on dilution,
    the worst error available here. So an implausible step voids the window
    entirely rather than being clamped into something that merely looks
    reasonable. NULL is the honest answer; the composite handles it.

Usage:
    python backend/compute/engine/dilution_metrics.py
    python backend/compute/engine/dilution_metrics.py --dry-run
"""
import argparse
import logging
import os
import sys

import psycopg2
import psycopg2.extensions
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv("DATABASE_URL_SYNC",
                   "postgresql://asx_user:asx_secure_2024@localhost:5432/asx_screener")

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s  %(levelname)-8s %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

_DEC2FLOAT = psycopg2.extensions.new_type(
    psycopg2.extensions.DECIMAL.values, "DEC2FLOAT",
    lambda v, c: float(v) if v is not None else None)
psycopg2.extensions.register_type(_DEC2FLOAT)

# A year-on-year ratio outside these bounds is treated as a corporate action,
# not issuance. Tripling or losing two thirds of the register in one year does
# happen in genuine raises, but not often enough to justify trusting it here.
STEP_MAX = 3.0
STEP_MIN = 0.34
# Growth beyond this in a year counts as a materially dilutive year.
MATERIAL_DILUTION = 0.02
WINDOW_YEARS = 5          # look back this far to find up to 4 observations
MIN_OBS = 3               # fewer than this and no CAGR is published

COMPUTE_SQL = f"""
WITH ranked AS (
    SELECT asx_code, fiscal_date, shares,
           ROW_NUMBER() OVER (PARTITION BY asx_code ORDER BY fiscal_date DESC) AS rn
    FROM market.shares_history
    WHERE shares > 0
      AND fiscal_date >= (CURRENT_DATE - INTERVAL '{WINDOW_YEARS} years')
      AND fiscal_date <= CURRENT_DATE
),
win AS (           -- most recent observations per stock, oldest first
    SELECT asx_code, fiscal_date, shares
    FROM ranked WHERE rn <= 4
),
stepped AS (
    SELECT asx_code, fiscal_date, shares,
           LAG(shares)      OVER (PARTITION BY asx_code ORDER BY fiscal_date) AS prev,
           LAG(fiscal_date) OVER (PARTITION BY asx_code ORDER BY fiscal_date) AS prev_date
    FROM win
),
steps AS (
    SELECT asx_code,
           shares::numeric / NULLIF(prev, 0) AS ratio,
           (shares::numeric / NULLIF(prev, 0)) - 1 AS change,
           fiscal_date
    FROM stepped WHERE prev IS NOT NULL AND prev > 0
),
agg AS (
    SELECT s.asx_code,
           COUNT(*)                                                   AS n_steps,
           BOOL_OR(s.ratio > {STEP_MAX} OR s.ratio < {STEP_MIN})      AS has_break,
           COUNT(*) FILTER (WHERE s.change > {MATERIAL_DILUTION})     AS dilutive_years,
           MAX(s.change)                                              AS max_change,
           (ARRAY_AGG(s.change ORDER BY s.fiscal_date DESC))[1]       AS latest_change
    FROM steps s GROUP BY s.asx_code
),
bounds AS (
    SELECT asx_code,
           COUNT(*)                                                        AS n_obs,
           MIN(fiscal_date)                                                AS first_date,
           MAX(fiscal_date)                                                AS last_date,
           (ARRAY_AGG(shares ORDER BY fiscal_date))[1]                     AS first_shares,
           (ARRAY_AGG(shares ORDER BY fiscal_date DESC))[1]                AS last_shares
    FROM win GROUP BY asx_code
)
SELECT b.asx_code,
       CASE WHEN a.has_break OR b.n_obs < {MIN_OBS}
                 OR b.first_shares IS NULL OR b.first_shares <= 0
                 OR EXTRACT(YEAR FROM AGE(b.last_date, b.first_date)) < 1
            THEN NULL
            ELSE ROUND(
              (POWER(b.last_shares::numeric / b.first_shares,
                     1.0 / GREATEST(EXTRACT(YEAR FROM AGE(b.last_date, b.first_date)), 1))
               - 1)::numeric, 4)
       END                                            AS cagr,
       CASE WHEN a.has_break THEN NULL
            ELSE ROUND(a.latest_change::numeric, 4) END AS change_1y,
       CASE WHEN a.has_break THEN NULL
            ELSE a.dilutive_years END                 AS dilutive_years,
       CASE WHEN a.has_break THEN NULL
            ELSE ROUND(a.max_change::numeric, 4) END  AS max_dilution,
       b.n_obs                                        AS n_obs
FROM bounds b JOIN agg a USING (asx_code)
"""

UPDATE_SQL = """
UPDATE screener.universe u SET
    shares_outstanding_cagr_3y = d.cagr,
    shares_change_1y           = d.change_1y,
    dilution_years_3y          = d.dilutive_years,
    max_annual_dilution_3y     = d.max_dilution,
    shares_history_years       = d.n_obs,
    -- The simple public field stays, now derived from the richer observations
    -- rather than the always-NULL yearly_metrics column.
    shares_dilution_3y         = d.cagr
FROM (VALUES %s) AS d(asx_code, cagr, change_1y, dilutive_years, max_dilution, n_obs)
WHERE u.asx_code = d.asx_code
"""


def main() -> None:
    ap = argparse.ArgumentParser(description="Derive dilution metrics")
    ap.add_argument("--dry-run", action="store_true", help="Compute without writing")
    args = ap.parse_args()

    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute(COMPUTE_SQL)
    rows = cur.fetchall()
    log.info(f"Computed dilution metrics for {len(rows):,} stocks")

    usable = [r for r in rows if r[1] is not None]
    voided = len(rows) - len(usable)
    log.info(f"  {len(usable):,} with a trustworthy window, "
             f"{voided:,} voided by an implausible step or too little history")

    if usable:
        vals = sorted(r[1] for r in usable)
        mid = vals[len(vals) // 2]
        log.info(f"  annualised change: min {vals[0]:+.1%}  median {mid:+.1%}  max {vals[-1]:+.1%}")
        serial = [r for r in usable if r[3] is not None and r[3] >= 3]
        log.info(f"  {len(serial):,} diluted in 3 or more of the last years")

    if args.dry_run:
        log.info("Dry run — nothing written. Sample of the most diluted:")
        for r in sorted(usable, key=lambda x: -x[1])[:10]:
            log.info(f"    {r[0]:6s} cagr {r[1]:+.1%}  1y {r[2]:+.1%}  "
                     f"dilutive_years {r[3]}  max {r[4]:+.1%}  obs {r[5]}")
        conn.close()
        return

    from psycopg2.extras import execute_values
    execute_values(cur, UPDATE_SQL, rows, page_size=1000,
                   template="(%s, %s::NUMERIC, %s::NUMERIC, %s::SMALLINT, %s::NUMERIC, %s::SMALLINT)")
    conn.commit()
    cur.close()
    conn.close()
    log.info(f"  ✓ {len(rows):,} rows updated in screener.universe")


if __name__ == "__main__":
    main()
