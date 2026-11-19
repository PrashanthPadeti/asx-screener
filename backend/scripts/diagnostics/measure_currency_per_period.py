#!/usr/bin/env python
"""
Finding 19: is a per-period reporting currency obtainable at all?
=================================================================
`staging_au.fundamentals` holds ONE currency per company, read from whichever
of Income_Statement / Balance_Sheet / Cash_Flow first carries a
`currency_symbol`, in the latest snapshot. Both consumers -- applicability
gate 1b for its ratios, and the Price/FCF guard -- apply that single value to
every historical fiscal year.

So a company that restated from USD into AUD has its pre-restatement years
judged by its current currency. Published where they were USD is the unsafe
direction.

THE QUESTION THIS ANSWERS, AND WHY IT COMES FIRST

Finding 19 is only worth a release if the source can answer it. Three things
decide that, and all three are read from the raw payload rather than assumed
from EODHD's documentation:

  Q1  do the three financial sections ever DISAGREE on the currency? If they
      do, "the company's currency" is already ambiguous and the loader's
      first-non-empty rule is picking one arbitrarily.
  Q2  does any PERIOD record carry a currency of its own? If EODHD states it
      only per section, no amount of parsing produces a per-period value and
      finding 19 is permanent rather than deferred.
  Q3  how many companies would a per-period currency actually change -- that
      is, how many have statements spanning a currency change at all?

Q2 is the decisive one. Q1 and Q3 size the problem either way.

READ-ONLY: one connection, SELECTs inside a transaction that is rolled back.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

SECTIONS = ("Income_Statement", "Balance_Sheet", "Cash_Flow")

#: Keys that would carry a currency inside a single period's record. Checked
#: as a SET rather than one guess, because the whole question is whether the
#: source states it somewhere this codebase has not looked.
PERIOD_CURRENCY_KEYS = (
    "currency", "currency_symbol", "currencySymbol", "reportedCurrency",
    "reporting_currency", "currency_code", "currencyCode",
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--env-file")
    ap.add_argument("--limit", type=int,
                    help="smoke test; counts are then NOT the population")
    args = ap.parse_args()
    if args.env_file:
        from dotenv import load_dotenv
        load_dotenv(args.env_file)

    import psycopg2
    from app.core.db import get_database_url_sync

    conn = psycopg2.connect(get_database_url_sync())
    try:
        cur = conn.cursor()
        sql = """
            SELECT asx_code, raw_json
            FROM staging_au.fundamentals
            WHERE raw_json IS NOT NULL
            ORDER BY asx_code
        """
        if args.limit:
            sql += f" LIMIT {int(args.limit)}"
        cur.execute(sql)

        codes = 0
        section_values: Counter[str] = Counter()
        disagreeing: list[tuple] = []
        period_keys_found: Counter[str] = Counter()
        periods_scanned = 0
        with_any_section_currency = 0

        for code, raw in cur.fetchall():
            codes += 1
            fin = (raw or {}).get("Financials") or {}

            stated = {}
            for section in SECTIONS:
                block = fin.get(section) or {}
                if not isinstance(block, dict):
                    continue
                sym = (block.get("currency_symbol") or "").strip()
                if sym:
                    stated[section] = sym.upper()

                # Q2: look inside each PERIOD record.
                for ptype in ("yearly", "quarterly"):
                    periods = block.get(ptype) or {}
                    if not isinstance(periods, dict):
                        continue
                    for _, rec in periods.items():
                        if not isinstance(rec, dict):
                            continue
                        periods_scanned += 1
                        for key in PERIOD_CURRENCY_KEYS:
                            if key in rec:
                                period_keys_found[f"{section}.{ptype}.{key}"] += 1

            if stated:
                with_any_section_currency += 1
                for v in stated.values():
                    section_values[v] += 1
                if len(set(stated.values())) > 1:
                    disagreeing.append((code, dict(stated)))

        print("=" * 72)
        print(f"Q1  do the three sections agree?   ({codes} codes read)")
        print("=" * 72)
        print(f"  codes stating a currency in any section : "
              f"{with_any_section_currency}")
        print(f"  codes where the sections DISAGREE      : "
              f"{len(disagreeing)}")
        for code, st in disagreeing[:15]:
            print(f"    {code}: {st}")
        if not disagreeing:
            print("    none -- the loader's first-non-empty rule is picking")
            print("    between values that agree, so it is not arbitrary.")

        print("\n" + "=" * 72)
        print("Q2  does any PERIOD record carry its own currency?")
        print("=" * 72)
        print(f"  period records scanned : {periods_scanned}")
        if period_keys_found:
            print("  ** A PER-PERIOD CURRENCY EXISTS in the payload:")
            for k, n in period_keys_found.most_common(12):
                print(f"     {k}: {n} records")
            print("  So finding 19 is FIXABLE: the parser can carry a")
            print("  currency per period instead of one per company.")
        else:
            print("  NONE. No period record carries any of: "
                  + ", ".join(PERIOD_CURRENCY_KEYS))
            print("  EODHD states the currency PER SECTION only, so no")
            print("  parsing produces a per-period value. Finding 19 is then")
            print("  PERMANENT under this source, not deferred -- and the")
            print("  honest fix is to record the limitation at the point of")
            print("  use, which v11.2.86 already does, rather than to keep")
            print("  it open as though work would close it.")

        print("\n── currencies stated, by section occurrence " + "─" * 25)
        for v, n in section_values.most_common(12):
            print(f"  {v:<6} {n}")

        conn.rollback()
        print("\nread-only, rolled back")
        if args.limit:
            print(f"** --limit {args.limit}: NOT population counts.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
