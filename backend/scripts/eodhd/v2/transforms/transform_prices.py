"""
Transform: staging_au.eod_prices → market.daily_prices
=====================================================
Converts staging DATE rows to TIMESTAMPTZ (ASX market close = 16:00 AEST = 06:00 UTC)
and upserts into the TimescaleDB hypertable.

Full run (no filters): truncates market.daily_prices first for a clean reload.
Partial run (--codes / --from-date / --to-date): upsert only.

Usage:
    python scripts/eodhd/v2/transforms/transform_prices.py
    python scripts/eodhd/v2/transforms/transform_prices.py --codes BHP CBA
    python scripts/eodhd/v2/transforms/transform_prices.py --from-date 2024-01-01 --to-date 2024-12-31
"""

import logging
import os
import sys
import argparse
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

# The database credential lives in the environment, never in source.
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from app.core.db import get_database_url_sync  # noqa: E402


load_dotenv()

DB_URL = get_database_url_sync()

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

BATCH_COMMIT = 100
# ASX close = 16:00 AEST = UTC+10 → 06:00 UTC
CLOSE_TIME = "16:00:00+10"

#: A full rebuild that lands below this fraction of the table it replaces is
#: refused. Same threshold as market.dividends, for the same reason: a source
#: that has stopped answering can still technically produce rows, and a
#: legitimate contraction of more than half has never happened to a price
#: history that only ever grows. Delisted codes keep their history.
SHRINK_FLOOR = 0.50


INSERT_SQL = """
    INSERT INTO market.daily_prices
        (time, asx_code, open, high, low, close, adjusted_close, volume, data_source)
    VALUES %s
    ON CONFLICT (time, asx_code) DO UPDATE SET
        open           = EXCLUDED.open,
        high           = EXCLUDED.high,
        low            = EXCLUDED.low,
        close          = EXCLUDED.close,
        adjusted_close = EXCLUDED.adjusted_close,
        volume         = EXCLUDED.volume,
        data_source    = EXCLUDED.data_source
"""


#: The exact inverse of the write.
#:
#: A row is stored at `date 16:00:00+10`, so converting back at a fixed +10
#: offset returns precisely the staging date it came from. 'Australia/Sydney'
#: would be the tempting spelling and is wrong in principle: it shifts to +11
#: under daylight saving, and the write does not. The two would still agree
#: today, because 06:00 UTC falls on the same calendar day at both offsets --
#: an agreement by luck, which is the kind that stops holding quietly.
STAGING_DATE = "(time AT TIME ZONE INTERVAL '+10:00')::date"

#: A per-code fingerprint of the complete set of dates held for that code.
#:
#: Set equality over (asx_code, digest) is set equality over (asx_code, date):
#: the digest covers every date the code has, in a canonical order, so two
#: sides agreeing on it agree member by member. That is what makes this a
#: proof rather than a sample -- and it is why counts are not the instrument.
#: Equal row counts over different days is a real failure mode here, and
#: min/max dates alone would miss a hole in the middle of the history.
#:
#: Done in SQL because the honest grain is roughly 6.7 million (code, date)
#: pairs. Materialising those in Python to compare them would cost more memory
#: than the transform itself, so the comparison is pushed to where the data is
#: and only ~1,900 digests come back.
def _digest_sql(table: str, date_expr: str, where: str) -> str:
    return f"""
        SELECT asx_code,
               COUNT(*)                                        AS n,
               md5(string_agg({date_expr}::text, ',' ORDER BY {date_expr})) AS digest
          FROM {table}
          {where}
         GROUP BY asx_code
    """


def transform_prices_for_code(cur, code: str, from_date: str | None, to_date: str | None) -> int:
    """Fetch, transform and insert rows for a single ASX code. Returns row count."""
    filters = ["asx_code = %s"]
    params  = [code]
    if from_date:
        filters.append("date >= %s"); params.append(from_date)
    if to_date:
        filters.append("date <= %s"); params.append(to_date)

    where = "WHERE " + " AND ".join(filters)
    cur.execute(f"""
        SELECT asx_code, date, open, high, low, close, adjusted_close, volume
        FROM staging_au.eod_prices
        {where}
        ORDER BY date
    """, params)

    rows = cur.fetchall()
    if not rows:
        return 0

    transformed = [
        (
            f"{r[1]} {CLOSE_TIME}",  # time
            r[0],                    # asx_code
            r[2], r[3], r[4],        # open, high, low
            r[5],                    # close
            r[6],                    # adjusted_close
            r[7],                    # volume
            "eodhd",                 # data_source
        )
        for r in rows
    ]

    execute_values(cur, INSERT_SQL, transformed, page_size=2000)
    return len(transformed)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--codes",     nargs="+")
    parser.add_argument("--from-date", help="YYYY-MM-DD inclusive")
    parser.add_argument("--to-date",   help="YYYY-MM-DD inclusive")
    parser.add_argument("--run-id",    type=int, default=None,
                        help="Record stage evidence against this compute run")
    parser.add_argument("--allow-shrink", action="store_true",
                        help="Permit a full rebuild that would leave "
                             "market.daily_prices below %d%% of its current "
                             "rows or codes. Intended contraction only."
                             % int(SHRINK_FLOOR * 100))
    args = parser.parse_args()

    # --allow-shrink narrows nothing, so it must not be mistaken for a filter.
    # Reading it as one would silently turn a full rebuild into a partial run
    # and skip the very guards it was passed to override.
    is_full_run = not args.codes and not args.from_date and not args.to_date

    conn = psycopg2.connect(DB_URL)
    # Prove where this process ACTUALLY connected, before any mutation.
    # An inherited environment is intent; a live connection is fact. Outside
    # a discovery run this only logs, so the nightly pipeline is unaffected.
    from compute.engine.runtime_envelope import prove as _prove_envelope
    _prove_envelope("transform_prices", conn)
    cur  = conn.cursor()

    prior_rows = prior_codes = 0
    if is_full_run:
        # The destructive step needs a precondition. A full run replaces the
        # entire price history from staging; if staging is empty -- a failed
        # load upstream, a wrong database -- the reload writes nothing, and
        # every downstream producer then computes correctly over no data.
        cur.execute("SELECT COUNT(*) FROM staging_au.eod_prices")
        staged = cur.fetchone()[0]
        if staged == 0:
            log.error("REFUSING full run: staging_au.eod_prices is empty. "
                      "Replacing market.daily_prices from an empty source "
                      "would destroy the price history and report success.")
            return 1

        # What is about to be replaced, measured before it is destroyed.
        cur.execute("SELECT count(*), count(DISTINCT asx_code) "
                    "FROM market.daily_prices")
        prior_rows, prior_codes = cur.fetchone()

        # NOT committed. TRUNCATE is transactional in PostgreSQL, so it belongs
        # in the same transaction as the inserts that replace what it removed.
        #
        # Committing it on its own -- which is what this did -- opened a window
        # in which market.daily_prices was empty and DURABLY so, for the entire
        # length of a 6.7M-row rebuild. A crash, a bad row, a killed session or
        # a failing code inside that window left the price history destroyed
        # with nothing to roll back to, and almost every producer downstream
        # reads this table.
        #
        # A population proof can report that a rebuild was incomplete. It
        # cannot undo a committed partial replacement. So the proof below now
        # runs BEFORE the commit and the commit is conditional on it: the table
        # goes from one complete state to another complete state, or it does
        # not move.
        #
        # The cost is an ACCESS EXCLUSIVE lock held for the length of the
        # rebuild, so readers block rather than see an empty table. That is a
        # strictly better failure: blocking is recoverable and being wrong is
        # not. Full runs are manual -- the daily pipeline always passes
        # --from-date -- so this is not a nightly cost.
        log.info("Full run — replacing market.daily_prices in one transaction "
                 "(staging holds %s rows; current table %s rows / %s codes) …",
                 f"{staged:,}", f"{prior_rows:,}", f"{prior_codes:,}")
        cur.execute("TRUNCATE TABLE market.daily_prices")

    # Get list of codes to process.
    #
    # From eod_prices, which is the actual source of the rows, NOT from
    # staging_au.company_profile. The profile table was used for speed -- 1,878
    # rows against a DISTINCT over 6.7M -- and it is a different population. A
    # code present in the price feed but absent from the profile was never
    # transformed, and because a full run TRUNCATES first, its entire price
    # history was destroyed and not rebuilt, while `done` counted a clean run
    # and every downstream producer read the gap as an absence of trading.
    #
    # The DISTINCT is paid once per run. The proof below would have failed on
    # this, and the selection is fixed here rather than left for the proof to
    # report every night.
    if args.codes:
        all_codes = [c.upper() for c in args.codes]
    else:
        cur.execute("SELECT DISTINCT asx_code FROM staging_au.eod_prices "
                    "ORDER BY asx_code")
        all_codes = [r[0] for r in cur.fetchall()]

    total_codes = len(all_codes)
    log.info(f"Transforming {total_codes:,} codes from staging_au.eod_prices → market.daily_prices …")

    total_rows = done = failed = 0
    for i, code in enumerate(all_codes, 1):
        try:
            n = transform_prices_for_code(cur, code, args.from_date, args.to_date)
            total_rows += n
            done += 1
        except Exception as e:
            conn.rollback()
            if is_full_run:
                # Skip-and-continue is how a partial replacement gets
                # committed. The rollback above has already restored the whole
                # table to its previous complete state, including the TRUNCATE;
                # carrying on would rebuild the remaining codes into a table
                # that was never emptied and commit the mixture.
                log.error("ABORTING full run at %s: %s", code, e)
                log.error("market.daily_prices is unchanged — the transaction "
                          "that would have replaced it has been rolled back, "
                          "TRUNCATE included.")
                cur.close()
                conn.close()
                return 1
            failed += 1
            log.warning(f"  {code}: {e}")
            continue

        # A full run is one transaction from TRUNCATE to COMMIT, so it has no
        # intermediate commit points by construction. Partial runs are additive
        # and idempotent, so batching is safe there.
        if not is_full_run and i % BATCH_COMMIT == 0:
            conn.commit()
            log.info(f"  [{i:4d}/{total_codes}]  ok={done}  err={failed}  rows={total_rows:,}")
        elif is_full_run and i % BATCH_COMMIT == 0:
            log.info(f"  [{i:4d}/{total_codes}]  ok={done}  rows={total_rows:,} (uncommitted)")

    log.info(f"Transformed {done} codes  |  {total_rows:,} rows  |  {failed} errors")

    # ── The commit precondition ──────────────────────────────────────────────
    # For a full run everything so far is still uncommitted, so these checks
    # decide whether the replacement happens at all rather than describing one
    # that already did.
    #
    # The population proof runs BEFORE the guards, so that every refusal below
    # carries the same fully computed evidence. It costs two GROUP BY passes on
    # a rebuild that is about to be rejected -- which is exactly the run whose
    # evidence is worth the most.
    details = {"codes_failed": failed, "full_run": is_full_run}
    result = build_population_result(cur, args, details)
    ok = prove_population(cur, args, result)

    if is_full_run:
        cur.execute("SELECT count(*), count(DISTINCT asx_code) "
                    "FROM market.daily_prices")
        new_rows, new_codes = cur.fetchone()
        details.update(prior_rows=prior_rows, prior_codes=prior_codes,
                       new_rows=new_rows, new_codes=new_codes)

        # The shrink guard, on the same reasoning as market.dividends: a source
        # that has stopped answering can still technically produce rows, and it
        # must not be allowed to overwrite a good dataset just because it did.
        shrunk = (prior_rows and new_rows < prior_rows * SHRINK_FLOOR) or \
                 (prior_codes and new_codes < prior_codes * SHRINK_FLOOR)
        if shrunk and args.allow_shrink:
            log.warning("Rebuild shrinks the table and --allow-shrink was "
                        "given: %s → %s rows.",
                        f"{prior_rows:,}", f"{new_rows:,}")
            shrunk = False

        failure = None
        if new_rows == 0:
            failure = ("empty_rebuild",
                       "the rebuild produced no rows")
        elif shrunk:
            failure = ("shrink_refused",
                       f"rebuild would shrink market.daily_prices from "
                       f"{prior_rows:,} rows / {prior_codes:,} codes to "
                       f"{new_rows:,} rows / {new_codes:,} codes")
        elif not ok:
            failure = ("population_not_covered",
                       "the rebuilt population does not match staging")

        if failure:
            return refuse(conn, cur, result, prior_rows, args.run_id, *failure)

    conn.commit()
    log.info("Committed.")
    cur.close()
    conn.close()
    return 0 if ok else 1


def refuse(conn, cur, result, prior_rows, run_id, failure_class, message) -> int:
    """Roll back to the previous complete state, then record why.

    The order is the whole point. The rollback comes first, so the evidence
    describes a replacement that definitively did not happen; only then does a
    second, independent connection persist the FAILED row the rollback
    destroyed. Recording beforehand would put the evidence inside the
    transaction that is about to discard it.

    A failure to record evidence never masks the refusal it was describing:
    the exit code is 1 either way, and publication stays blocked because there
    is still no success row.
    """
    from compute.engine.run_stages import record_failed_stage_after_rollback

    conn.rollback()
    log.error("REFUSING to commit: %s. market.daily_prices is unchanged "
              "(%s rows).", message, f"{prior_rows:,}")
    cur.close()
    conn.close()

    if result is not None:
        record_failed_stage_after_rollback(
            DB_URL, run_id, result, log,
            failure_class=failure_class, failure_message=message)
    return 1


def prove_population(cur, args, result) -> bool:
    """Print the proof and record it. `result` is None for a scoped run."""
    from compute.engine.run_stages import report_population

    return report_population(
        cur, args.run_id, result, log,
        scoped_reason=("a scoped run's expected population is not the source "
                       "domain" if result is None else ""))


def build_population_result(cur, args, details: dict):
    """Does market.daily_prices now hold exactly what staging holds?

    Asked of the TARGET AFTER the write, both directions, over the same window
    on both sides -- never as "does the target contain each expected code".
    market.daily_prices is a historical table: a containment query is satisfied
    by rows loaded months ago, so a run that transformed nothing at all would
    pass it for every company. That is the failure this is built to catch, and
    it is the one a containment check is structurally blind to.

    Comparing digests over a bounded window also makes a partial run provable
    on the same mechanism: if today's rows were missed, the target's digest for
    the window lacks today's date and the member differs, however much correct
    history sits beside it.
    """
    from compute.engine.run_stages import StageResult

    if args.codes:
        return None

    # The same date window applied to both sides. Applying it to one side only
    # would report every row outside the window as a difference.
    src_where, tgt_where, params = [], [], []
    if args.from_date:
        src_where.append("date >= %s")
        tgt_where.append(f"{STAGING_DATE} >= %s")
        params.append(args.from_date)
    if args.to_date:
        src_where.append("date <= %s")
        tgt_where.append(f"{STAGING_DATE} <= %s")
        params.append(args.to_date)
    src_w = ("WHERE " + " AND ".join(src_where)) if src_where else ""
    tgt_w = ("WHERE " + " AND ".join(tgt_where)) if tgt_where else ""

    cur.execute(_digest_sql("staging_au.eod_prices", "date", src_w), params)
    expected = {(r[0], r[1], r[2]) for r in cur.fetchall()}

    cur.execute(_digest_sql("market.daily_prices", STAGING_DATE, tgt_w), params)
    written = {(r[0], r[1], r[2]) for r in cur.fetchall()}

    return StageResult(
        "transform_prices",
        frozenset(expected), frozenset(written), details,
        grain="asx_code+row_count+date_set_digest")


if __name__ == "__main__":
    # sys.exit, not a bare call: a price table that does not match its source
    # must stop the pipeline, not annotate it.
    sys.exit(main())
