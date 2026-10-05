#!/usr/bin/env python
"""
Behavioural proof: a stale derived row must not serve
=====================================================
Runs against the SCRATCH database only. Refuses production.

`screener.universe` draws its technical columns from `market.daily_metrics`
through a LATERAL join that used to take the latest row EVER WRITTEN for the
code, unrelated to the prices it claimed to describe. ALPH served
dma200_ratio = 1.0175 from 19 Jun 2026 until 3 Oct against prices running to
1 Oct.

That matters beyond the ungoverned technical columns, because governed
`momentum_score` is built from five of them:

    momentum = return_1m, return_3m, return_6m, rsi_14, adx_14

so a governed metric could publish an ordinary valid state from evidence
three months stale. That is why P0-A was reopened.

The source guards in tests/test_universe_metric_as_of.py prove the predicate
is present in the SQL. They do NOT prove PostgreSQL and the real build path
enforce it. This does.

Three cases in ONE build, so a single pass exercises all of them:

    STALE    metric row dated well before the code's latest price
             -> technical columns must be NULL
             -> governed momentum_score must be ABSENT WITH A CAUSE,
                never zero and never an ordinary score
    FRESH    metric row dated AT the latest price   -> serves normally
    NOPRICE  no price rows at all                   -> nothing serves

Usage (from a worktree, against scratch):
    python tests/fixtures/prove_stale_metric_rejection.py --setup
    python tests/fixtures/prove_stale_metric_rejection.py --assert
"""

import argparse
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

import psycopg2                                                    # noqa: E402

from app.core.db import get_database_url_sync                      # noqa: E402

STALE_CODE   = "BHP"      # plenty of history; we age its metric row
FRESH_CODE   = "CSL"      # left alone: the control
NOPRICE_CODE = "WBC"      # prices removed in scratch

STALE_DATE = "2026-06-19"

#: The five governed-momentum inputs, plus two ungoverned technical columns
#: that make the stale/fresh contrast visible on their own.
WATCHED = ("return_1m", "return_3m", "return_6m", "rsi_14", "adx_14",
           "dma200_ratio", "sma_200")


def _connect():
    """Scratch only. A fixture that mutates production is not a fixture."""
    url = get_database_url_sync()
    if "scratch" not in url:
        raise SystemExit(
            f"REFUSING: this fixture mutates data and the target is not a "
            f"scratch database.\n  target: ...{url[-40:]}\n"
            f"Point DATABASE_URL_SYNC at asx_screener_scratch.")
    conn = psycopg2.connect(url)
    conn.autocommit = False
    return conn


def setup(conn) -> None:
    cur = conn.cursor()

    # STALE: collapse the code's metric history to one row, dated long before
    # its latest price. Built by COPYING a real row rather than inventing
    # values, so every column stays internally consistent -- the only thing
    # wrong with it is its as-of date, which is exactly the property on trial.
    cur.execute("SELECT max(date) FROM market.daily_metrics WHERE asx_code=%s",
                (STALE_CODE,))
    newest = cur.fetchone()[0]
    if newest is None:
        raise SystemExit(f"{STALE_CODE} has no daily_metrics rows in scratch")

    # market.daily_metrics is a TimescaleDB hypertable partitioned on `date`,
    # so UPDATE ... SET date moves the row out of its chunk's range and the
    # chunk's own CHECK constraint rejects it. The row is COPIED to the stale
    # date instead, which lands it in the correct chunk, and the originals are
    # then removed.
    cur.execute("""
        SELECT string_agg(quote_ident(column_name), ', ' ORDER BY ordinal_position)
        FROM information_schema.columns
        WHERE table_schema='market' AND table_name='daily_metrics'
    """)
    cols = cur.fetchone()[0]
    projected = ", ".join(
        f"DATE %s" if c.strip() == "date" else c.strip()
        for c in cols.split(","))

    cur.execute(f"""
        INSERT INTO market.daily_metrics ({cols})
        SELECT {projected} FROM market.daily_metrics
         WHERE asx_code = %s AND date = %s
        ON CONFLICT (asx_code, date) DO NOTHING
    """, (STALE_DATE, STALE_CODE, newest))
    cur.execute("DELETE FROM market.daily_metrics "
                "WHERE asx_code = %s AND date <> %s", (STALE_CODE, STALE_DATE))

    # The five momentum inputs must be NON-NULL on the stale row, or the test
    # would pass for the wrong reason: absent inputs prove nothing about a
    # predicate that rejects present ones.
    cur.execute(f"""
        UPDATE market.daily_metrics
           SET return_1m = COALESCE(return_1m, 0.05),
               return_3m = COALESCE(return_3m, 0.10),
               return_6m = COALESCE(return_6m, 0.15),
               rsi_14    = COALESCE(rsi_14,   70.80),
               adx_14    = COALESCE(adx_14,   25.00),
               dma200_ratio = COALESCE(dma200_ratio, 1.0175),
               sma_200   = COALESCE(sma_200, 11.0564)
         WHERE asx_code = %s AND date = %s
    """, (STALE_CODE, STALE_DATE))

    # Sentinels in the weekly and monthly sources.
    #
    # The first version of this patch bounded only the daily lateral, and the
    # fixture still failed -- because the served columns COALESCEd across three
    # cadences, so rejecting the stale daily row PROMOTED the weekly one. The
    # universe served sma_200 = 54.6245 from market.weekly_metrics while the
    # daily row said 11.0564.
    #
    # Distinctive values make that leak impossible to miss: if 91.23 or 123.45
    # ever appears in a daily-semantic column, a coarser cadence has occupied a
    # daily metric's identity.
    for code in (STALE_CODE, NOPRICE_CODE):
        cur.execute("UPDATE market.monthly_metrics SET rsi_14 = 91.23 "
                    "WHERE asx_code = %s", (code,))
        cur.execute("UPDATE market.weekly_metrics SET sma_20w = 123.45, "
                    "sma_40w = 123.45 WHERE asx_code = %s", (code,))

    # NOPRICE: remove the price history entirely, keep a metric row.
    cur.execute("DELETE FROM market.daily_prices WHERE asx_code = %s",
                (NOPRICE_CODE,))

    conn.commit()

    cur.execute("""
        SELECT d.asx_code, max(d.date) AS metric_date,
               (SELECT max((p.time AT TIME ZONE INTERVAL '+10:00')::date)
                  FROM market.daily_prices p WHERE p.asx_code = d.asx_code)
        FROM market.daily_metrics d WHERE d.asx_code = ANY(%s)
        GROUP BY d.asx_code ORDER BY 1
    """, ([STALE_CODE, FRESH_CODE, NOPRICE_CODE],))
    print("  code    metric_date   latest_price")
    for code, mdate, pdate in cur.fetchall():
        print(f"  {code:7s} {str(mdate):13s} {pdate}")
    print("\nNow rebuild the universe and score it, then run --assert.")


def check(conn, serving_only: bool = False) -> int:
    cur = conn.cursor()
    failures = []

    def report(name: str, ok: bool, detail: str = "") -> None:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}" +
              (f"\n        {detail}" if not ok and detail else ""))
        if not ok:
            failures.append(name)

    cols = ", ".join(WATCHED)
    cur.execute(f"SELECT {cols} FROM screener.universe WHERE asx_code=%s",
                (STALE_CODE,))
    stale = cur.fetchone()
    report("a stale metric row serves no technical value",
           stale is not None and all(v is None for v in stale),
           f"expected every one of {WATCHED} to be NULL, got {stale}")

    cur.execute(f"SELECT {cols} FROM screener.universe WHERE asx_code=%s",
                (FRESH_CODE,))
    fresh = cur.fetchone()
    report("a matching-as-of row still serves normally",
           fresh is not None and any(v is not None for v in fresh),
           "the control serves nothing either -- the predicate is too strict, "
           "or the control's own metric row is not at its latest price date")

    cur.execute(f"SELECT {cols} FROM screener.universe WHERE asx_code=%s",
                (NOPRICE_CODE,))
    noprice = cur.fetchone()
    report("no price means no technical value",
           noprice is None or all(v is None for v in noprice),
           f"a code with no prices served {noprice}")

    # No coarser cadence may occupy a daily metric's identity, whatever the
    # daily source happens to hold. Checked by value rather than by NULLness,
    # because the first patch produced the right shape from the wrong source.
    cur.execute(f"""
        SELECT asx_code, {cols} FROM screener.universe
         WHERE asx_code = ANY(%s)
    """, ([STALE_CODE, NOPRICE_CODE],))
    leaked = []
    for row in cur.fetchall():
        for name, value in zip(("asx_code",) + WATCHED, row)   :
            if name != "asx_code" and value is not None and \
                    str(value) in ("91.23", "123.45", "91.2300", "123.4500"):
                leaked.append(f"{row[0]}.{name} = {value}")
    report("no weekly or monthly sentinel reaches a daily-semantic column",
           not leaked,
           "a coarser cadence occupied a daily metric's name: " +
           ", ".join(leaked))

    if serving_only:
        # The governed half is proven elsewhere, and deliberately so.
        #
        # Reaching it here would need composite_score to publish under a real
        # run, which means the canonical driver -- and the driver runs
        # technical_compute, which writes a row for EVERY code with prices.
        # That would hand the stale code a matching-as-of row and erase the
        # condition under test before universe_build ever saw it. The stale
        # state only exists when a technical run SKIPS a code, which is
        # exactly what the driver will not do.
        #
        # So the governed propagation is proven as a property instead:
        #   tests/test_momentum_fails_closed.py  — effective_weights is pure
        # and on production data, run 6, 4 Oct 2026: of 2,121 served rows, 21
        # had all five momentum inputs absent, 0 scored anyway, and all 21
        # carried {"cause": "source_missing", "state": "unavailable"}.
        #
        # Bending the canonical lifecycle to keep one synthetic row alive
        # would prove less and cost more.
        print(f"\n{len(failures)} failure(s)" if failures
              else "\nserving properties hold "
                   "(governed half: tests/test_momentum_fails_closed.py)")
        return 1 if failures else 0

    # ── The governed half ────────────────────────────────────────────────────
    # Absence alone is not the contract. A governed metric that merely vanishes
    # is an unexplained blank; the contract is that it carries a cause.
    cur.execute("SELECT momentum_score, metric_states->'momentum_score' "
                "FROM screener.universe WHERE asx_code=%s", (STALE_CODE,))
    row = cur.fetchone()
    score, state = (row if row else (None, None))
    report("governed momentum_score is not computed from stale evidence",
           score is None,
           f"momentum_score = {score!r} from a metric row dated {STALE_DATE} "
           f"against a far later price")
    report("governed momentum_score is not silently zero",
           score != 0,
           "zero is a score, not an absence -- a stale input became a verdict")
    report("the governed absence carries a cause",
           state is not None,
           "momentum_score is absent with no metric_states entry: the stale "
           "value was removed and replaced by an unexplained blank. That is a "
           "SECOND P0-A defect, not a passing test")
    if state is not None:
        print(f"        state recorded: {state}")

    cur.execute("SELECT momentum_score FROM screener.universe WHERE asx_code=%s",
                (FRESH_CODE,))
    fresh_score = cur.fetchone()
    report("governed momentum_score still computes from current evidence",
           fresh_score is not None and fresh_score[0] is not None,
           "the control lost its score too -- the predicate suppresses valid "
           "evidence")

    print(f"\n{len(failures)} failure(s)" if failures else "\nall properties hold")
    return 1 if failures else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--setup", action="store_true")
    ap.add_argument("--assert", dest="do_assert", action="store_true")
    ap.add_argument("--serving-only", action="store_true",
                    help="skip the governed half; it is proven by "
                         "tests/test_momentum_fails_closed.py")
    a = ap.parse_args()
    if not (a.setup or a.do_assert):
        ap.error("pass --setup or --assert")
    c = _connect()
    try:
        sys.exit(setup(c) or 0 if a.setup else check(c, a.serving_only))
    finally:
        c.close()
