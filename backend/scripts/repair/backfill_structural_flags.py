#!/usr/bin/env python
"""
Backfill is_reit / is_miner for companies no producer ever classified
====================================================================
Measured on production, 24 Oct 2026:

    2,589 current companies
      884 have no gics_industry
      805 carry NULL is_reit / is_miner -- never classified by anything
    2,552 rows in screener.universe, 768 unclassified (30%)

and the API renders every one of them as "Is REIT: No", because v11.2.27
made NULL render as False to stop a 500. Of a random sample: Altitude
Minerals, Gorilla Gold Mines, Linq Minerals, Verity Resources -- all
sector Materials, all shown as "not a miner".

`transform_companies` read `company_profile.gic_industry`, which is
populated for only 36 of the 327 unclassified OPERATING companies.
`fundamentals.general_industry` has it for 200. The data was there; the
producer was reading the thinner of two sources.

Population of this repair, from the SOURCE:

    205  operating, industry recoverable  -> classified here
    111  operating, sector only           -> left unknown, deliberately
     11  operating, nothing at all        -> left unknown
    478  non-operating (ETF/note/fund)    -> not applicable, left NULL

The 111 are left alone on purpose. GICS `Materials` covers chemicals,
packaging and steel as well as mining; `Real Estate` covers non-REIT
developers. Classifying from sector would manufacture a different set of
wrong answers with more confidence than the evidence carries.

Two rules this obeys
--------------------
*The classification is not reimplemented here.* It imports the same
`classification` module the producer now uses, so the repair cannot drift
from the rule that will apply on the next scheduled run.

*No new SCD2 version is written.* is_reit and is_miner are SCD2-tracked,
so changing one normally closes the current row and opens a new version.
That is for a company that CHANGED. These rows are NULL because nobody
ever classified them -- opening a version would assert that Gorilla Gold
Mines became a miner on 24 October 2026, which is false history written to
make a repair look routine. The current row is corrected in place and the
repair is declared in docs/.

Usage:
    python backfill_structural_flags.py             # dry run, writes nothing
    python backfill_structural_flags.py --apply     # one transaction
    python backfill_structural_flags.py --limit 20  # sample the plan
"""

import argparse
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
BACKEND = HERE.parents[2]
sys.path.insert(0, str(BACKEND / "scripts" / "eodhd" / "v2" / "transforms"))

from classification import classify_miner, classify_reit    # noqa: E402

import psycopg2                                              # noqa: E402
import psycopg2.extras                                       # noqa: E402
from dotenv import load_dotenv                               # noqa: E402

# Config at the execution boundary: this script is its own entry point and
# must not rely on another module's import-time load_dotenv having run.
load_dotenv(BACKEND / ".env")

DSN = os.environ.get("DATABASE_URL_SYNC")

#: Industry is preferred from company_profile and falls back to fundamentals.
#: Both are one row per asx_code (asserted below before anything is read).
POPULATION = """
    SELECT c.asx_code,
           c.company_name,
           c.company_type,
           c.gics_sector,
           c.is_reit   AS current_is_reit,
           c.is_miner  AS current_is_miner,
           COALESCE(p.gic_industry, f.general_industry) AS industry,
           CASE WHEN p.gic_industry IS NOT NULL THEN 'company_profile'
                WHEN f.general_industry IS NOT NULL THEN 'fundamentals'
                ELSE NULL END AS industry_source
    FROM market.companies c
    LEFT JOIN staging_au.company_profile p ON p.asx_code = c.asx_code
    LEFT JOIN staging_au.fundamentals     f ON f.asx_code = c.asx_code
    WHERE c.is_current
      AND (c.is_reit IS NULL OR c.is_miner IS NULL)
    ORDER BY c.asx_code
"""

#: Rows that ALREADY carry a verdict, to be re-derived and compared.
#:
#: The backfill above only fills NULLs, so it cannot correct a row that was
#: confidently wrong. The original keyword list missed industries named for
#: the commodity -- Copper, Uranium, Aluminum -- so companies classified
#: before this release may hold FALSE where the corrected rule says TRUE.
#: Those are found here and reported; they are only written under an
#: explicit flag, because overwriting a derived value is a different act
#: from filling an absence.
DISAGREEMENT = """
    SELECT c.asx_code,
           c.company_name,
           c.company_type,
           c.is_reit   AS current_is_reit,
           c.is_miner  AS current_is_miner,
           COALESCE(p.gic_industry, f.general_industry) AS industry
    FROM market.companies c
    LEFT JOIN staging_au.company_profile p ON p.asx_code = c.asx_code
    LEFT JOIN staging_au.fundamentals     f ON f.asx_code = c.asx_code
    WHERE c.is_current
      AND c.is_reit IS NOT NULL
      AND c.is_miner IS NOT NULL
      AND COALESCE(p.gic_industry, f.general_industry) IS NOT NULL
    ORDER BY c.asx_code
"""

OVERWRITE = """
    UPDATE market.companies
       SET is_reit = %(is_reit)s, is_miner = %(is_miner)s, updated_at = NOW()
     WHERE asx_code = %(asx_code)s AND is_current
"""

DUPLICATE_CHECK = """
    SELECT 'company_profile' AS t, count(*) - count(DISTINCT asx_code) AS dupes
    FROM staging_au.company_profile
    UNION ALL
    SELECT 'fundamentals', count(*) - count(DISTINCT asx_code)
    FROM staging_au.fundamentals
"""

UPDATE = """
    UPDATE market.companies
       SET is_reit    = COALESCE(is_reit,  %(is_reit)s),
           is_miner   = COALESCE(is_miner, %(is_miner)s),
           updated_at = NOW()
     WHERE asx_code = %(asx_code)s
       AND is_current
       AND (is_reit IS NULL OR is_miner IS NULL)
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="write the repair (default is a dry run)")
    ap.add_argument("--limit", type=int, default=0,
                    help="print only the first N planned rows")
    ap.add_argument("--fix-disagreements", action="store_true",
                    help="also correct rows that already hold a verdict the "
                         "current rule disagrees with (overwrites a derived "
                         "value; reported either way)")
    args = ap.parse_args()

    if not DSN:
        print("DATABASE_URL_SYNC is not set", file=sys.stderr)
        return 2

    conn = psycopg2.connect(DSN)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # A second row per code would silently duplicate the population and make
    # every count below a lie. Refuse rather than discover it afterwards.
    cur.execute(DUPLICATE_CHECK)
    for row in cur.fetchall():
        if row["dupes"]:
            print(f"REFUSING: staging_au.{row['t']} has {row['dupes']} "
                  f"duplicate asx_code rows; the join would fan out",
                  file=sys.stderr)
            return 2

    cur.execute(POPULATION)
    rows = cur.fetchall()

    planned, unknown, not_applicable = [], [], []
    for r in rows:
        evidence = {"gic_industry": r["industry"], "type": r["company_type"]}
        reit = classify_reit(evidence)
        miner = classify_miner(evidence)

        if reit is None and miner is None:
            (not_applicable if (r["company_type"] or "").lower() in
             ("etf", "notes", "fund", "preferred_stock")
             else unknown).append(r)
            continue
        planned.append((r, reit, miner))

    print(f"population (is_reit or is_miner NULL, current): {len(rows)}")
    print(f"  classifiable from staging industry : {len(planned)}")
    print(f"  left unknown (no industry)         : {len(unknown)}")
    print(f"  not applicable (ETF/note/fund)     : {len(not_applicable)}")

    shown = planned if not args.limit else planned[:args.limit]
    print(f"\n{'code':<8} {'is_reit':<18} {'is_miner':<18} "
          f"{'source':<16} industry")
    print("-" * 100)
    for r, reit, miner in shown:
        print(f"{r['asx_code']:<8} "
              f"{str(r['current_is_reit']) + ' -> ' + str(reit):<18} "
              f"{str(r['current_is_miner']) + ' -> ' + str(miner):<18} "
              f"{str(r['industry_source']):<16} {r['industry']}")
    if args.limit and len(planned) > args.limit:
        print(f"... {len(planned) - args.limit} more")

    new_miners = sum(1 for _, _, m in planned if m is True)
    new_reits = sum(1 for _, rt, _ in planned if rt is True)
    print(f"\nwould set is_miner = TRUE for {new_miners} companies")
    print(f"would set is_reit  = TRUE for {new_reits} companies")

    # ── Rows that already hold a verdict the current rule disagrees with ──
    cur.execute(DISAGREEMENT)
    disagreements = []
    for r in cur.fetchall():
        evidence = {"gic_industry": r["industry"], "type": r["company_type"]}
        reit, miner = classify_reit(evidence), classify_miner(evidence)
        # Only a definite verdict may displace a definite verdict. None here
        # means the rule has nothing to say, which is not grounds to erase
        # what a previous run recorded.
        if reit is None or miner is None:
            continue
        if reit != r["current_is_reit"] or miner != r["current_is_miner"]:
            disagreements.append((r, reit, miner))

    print(f"\nalready classified, current rule DISAGREES: "
          f"{len(disagreements)}")
    if disagreements:
        print(f"{'code':<8} {'is_reit':<18} {'is_miner':<18} industry")
        print("-" * 100)
        for r, reit, miner in disagreements[:args.limit or 40]:
            print(f"{r['asx_code']:<8} "
                  f"{str(r['current_is_reit']) + ' -> ' + str(reit):<18} "
                  f"{str(r['current_is_miner']) + ' -> ' + str(miner):<18} "
                  f"{r['industry']}")
        if not args.fix_disagreements:
            print("  (not corrected — pass --fix-disagreements to write "
                  "these; they overwrite a derived value)")

    if not args.apply:
        print("\nDRY RUN — nothing written. Re-run with --apply.")
        conn.rollback()
        return 0

    written = 0
    for r, reit, miner in planned:
        cur.execute(UPDATE, {"asx_code": r["asx_code"],
                             "is_reit": reit, "is_miner": miner})
        written += cur.rowcount

    corrected = 0
    if args.fix_disagreements:
        for r, reit, miner in disagreements:
            cur.execute(OVERWRITE, {"asx_code": r["asx_code"],
                                    "is_reit": reit, "is_miner": miner})
            corrected += cur.rowcount

    conn.commit()
    print(f"\nAPPLIED — {written} filled, {corrected} corrected, "
          f"one transaction.")

    # Prove the population is gone, from the target, after the write.
    cur.execute("""
        SELECT count(*) AS still_null FROM market.companies
        WHERE is_current AND (is_reit IS NULL OR is_miner IS NULL)
    """)
    remaining = cur.fetchone()["still_null"]
    expected = len(unknown) + len(not_applicable)
    print(f"remaining unclassified: {remaining} (expected {expected} — "
          f"the deliberately-unknown and the not-applicable)")
    if remaining != expected:
        print("MISMATCH: the remainder is not what the plan predicted",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
