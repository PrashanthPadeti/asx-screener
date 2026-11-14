#!/usr/bin/env python
"""
How many companies does the fcf_yield currency gap affect?
==========================================================
Applicability gate 1b marks eight ratios NOT_MEANINGFUL when the statements
are stated in a currency other than AUD, because an AUD market
capitalisation over a foreign-currency denominator has no unit.

`fcf_yield` has that exact shape -- free cash flow over market cap -- and is
NOT in CROSS_CURRENCY. It is served today: a registered filter, a sort
column, a CSV column, a company-detail field, and a constituent of the
factor model's Value signal.

`price_to_fcf` has the same shape. It is guarded at the producer from
v11.2.86 because it is not assessable and so gate 1b cannot reach it.

WHAT THIS MEASURES

  Q1  how many universe rows state a currency at all, and which
  Q2  of the foreign reporters, how many publish an fcf_yield today
  Q3  how many of those are inside the factor model's scored population,
      where the value does not merely display but moves a score
  Q4  the same question for the eight ALREADY-guarded ratios, as a
      control: if those come back non-zero the gate is not doing what
      this finding assumes, and the finding is wrong before it starts

Q4 is the point. A measurement of an unguarded metric means nothing
without evidence that the guard works where it is applied.

READ-ONLY. Opens one connection, runs SELECTs inside a transaction it
rolls back, and touches no hypertable.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))


CURRENCY_CENSUS = """
SELECT
    COALESCE(reporting_currency, '(none stated)') AS currency,
    COUNT(*)                                      AS universe_rows
FROM screener.universe
GROUP BY 1
ORDER BY 2 DESC
"""

#: The served exposure. A foreign reporter publishing a number whose units
#: do not cancel.
EXPOSURE = """
SELECT
    COUNT(*)                                            AS foreign_rows,
    COUNT(fcf_yield)                                    AS publishing_yield,
    COUNT(price_to_fcf)                                 AS publishing_p_fcf,
    COUNT(*) FILTER (WHERE compute_run_id IS NOT NULL)  AS attributed_rows
FROM screener.universe
WHERE reporting_currency IS NOT NULL
  AND UPPER(TRIM(reporting_currency)) <> 'AUD'
"""

#: Of the foreign reporters publishing a yield, how many carry a composite
#: score -- i.e. the value did not merely display, it moved a ranking.
SCORED = """
SELECT COUNT(*) AS scored_and_publishing
FROM screener.universe
WHERE reporting_currency IS NOT NULL
  AND UPPER(TRIM(reporting_currency)) <> 'AUD'
  AND fcf_yield IS NOT NULL
  AND composite_score IS NOT NULL
"""

#: THE CONTROL. The eight ratios gate 1b already covers must be absent on
#: these same rows. If any of them publishes, the gate is not enforcing
#: what this finding assumes it enforces, and the comparison is void.
CONTROL = """
SELECT
    COUNT(pe_ratio)       AS pe_ratio,
    COUNT(price_to_book)  AS price_to_book,
    COUNT(price_to_sales) AS price_to_sales,
    COUNT(peg_ratio)      AS peg_ratio,
    COUNT(ev_to_ebitda)   AS ev_to_ebitda,
    COUNT(ev_to_ebit)     AS ev_to_ebit,
    COUNT(altman_z_score) AS altman_z_score,
    COUNT(bvps)           AS bvps
FROM screener.universe
WHERE reporting_currency IS NOT NULL
  AND UPPER(TRIM(reporting_currency)) <> 'AUD'
  AND compute_run_id IS NOT NULL
"""


def _table(cur, sql: str) -> tuple[list[str], list[tuple]]:
    cur.execute(sql)
    return [d[0] for d in cur.description], cur.fetchall()


def _show(title: str, cols, rows) -> None:
    print(f"\n── {title} " + "─" * max(0, 62 - len(title)))
    widths = [max(len(c), *(len(str(r[i])) for r in rows)) if rows else len(c)
              for i, c in enumerate(cols)]
    print("  " + "  ".join(c.ljust(w) for c, w in zip(cols, widths)))
    print("  " + "  ".join("-" * w for w in widths))
    for r in rows:
        print("  " + "  ".join(str(v).ljust(w) for v, w in zip(r, widths)))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--env-file", help="path to a .env to load first")
    args = ap.parse_args()

    if args.env_file:
        from dotenv import load_dotenv
        load_dotenv(args.env_file)

    import psycopg2
    from app.core.db import get_database_url_sync

    conn = psycopg2.connect(get_database_url_sync())
    try:
        cur = conn.cursor()

        cols, rows = _table(cur, CURRENCY_CENSUS)
        _show("Q1  what the universe states as a reporting currency",
              cols, rows)

        cols, rows = _table(cur, EXPOSURE)
        _show("Q2  foreign reporters, and what they publish", cols, rows)
        foreign, yielding, p_fcf, attributed = rows[0]

        cols, srows = _table(cur, SCORED)
        _show("Q3  of those, how many carry a composite score", cols, srows)

        cols, crows = _table(cur, CONTROL)
        _show("Q4  CONTROL -- the eight ratios gate 1b already guards",
              cols, crows)

        leaking = [c for c, v in zip(cols, crows[0]) if v]
        print()
        if leaking:
            print("  ** CONTROL FAILED. These are guarded by gate 1b and are")
            print(f"     still published on foreign reporters: {leaking}")
            print()
            print("     WHAT THIS DOES AND DOES NOT MEAN. It means gate 1b is")
            print("     not enforcing what this script assumes -- either the")
            print("     gate is broken, or these rows do not reach it, or the")
            print("     assumption about which metrics it covers is wrong.")
            print()
            print("     It does NOT disprove the fcf_yield unit mismatch. That")
            print("     mismatch is a property of the arithmetic: an AUD market")
            print("     capitalisation over a foreign-currency cash flow has no")
            print("     unit whatever any gate does about it. A failing control")
            print("     invalidates the COMPARISON -- 'fcf_yield publishes")
            print("     where its guarded peers do not' -- not the defect.")
            print("     Finding 17 stands; what needs auditing is the gate.")
        else:
            print("  control holds: all eight guarded ratios are absent on")
            print(f"  the {attributed} attributed foreign-reporter rows, so")
            print("  gate 1b does enforce the rule where it is applied.")
            print()
            print(f"  fcf_yield publishes on {yielding} of {foreign} foreign")
            print(f"  reporters, {srows[0][0]} of them inside the scored")
            print("  population. Those are rows where an AUD market")
            print("  capitalisation sits over a foreign-currency cash flow")
            print("  and nothing says so.")
            print()
            print(f"  price_to_fcf publishes on {p_fcf}. From v11.2.86 the")
            print("  producer declines these, so after the next yearly run")
            print("  this must be 0 while fcf_yield is unchanged -- that")
            print("  difference is the finding.")

        conn.rollback()
        print("\nread-only, rolled back")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
