"""
ASX Screener — Top 5 Strategy Engine
=====================================
Monthly algo-ranked top 5 (default) picks from the ASX200 universe.

Algorithm:
  - Universe  : screener.universe WHERE is_asx200 = TRUE AND status = 'active'
  - Ranking   : composite_score DESC (pre-computed by composite_score.py)
                composite_score = equal-weight average of:
                  momentum_score  (return_1m/3m/6m, RSI, ADX)
                  quality_score   (Piotroski, ROE, ROCE, Altman-Z, D/E, margin)
                  value_score     (PE, PB, EV/EBITDA, FCF yield, P/S)
                  income_score    (grossed-up yield, franking, consecutive yrs)
                  growth_score    (revenue/EPS growth 1Y, 3Y CAGR, HoH)
  - Output    : strategy.monthly_picks  (idempotent — safe to re-run same month)

Usage:
    python compute/engine/top5_strategy.py
    python compute/engine/top5_strategy.py --top-n 10
    python compute/engine/top5_strategy.py --date 2026-05-01
    python compute/engine/top5_strategy.py --dry-run
"""

import argparse
import logging
import os
from datetime import date, datetime

import psycopg2
import psycopg2.extensions
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv(
    "DATABASE_URL_SYNC",
    "postgresql://asx_user:asx_secure_2024@localhost:5432/asx_screener",
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

_DEC2FLOAT = psycopg2.extensions.new_type(
    psycopg2.extensions.DECIMAL.values, "DEC2FLOAT",
    lambda v, c: float(v) if v is not None else None,
)
psycopg2.extensions.register_type(_DEC2FLOAT)


def run(pick_month: date, top_n: int = 5, dry_run: bool = False) -> list[dict]:
    """
    Rank ASX200 by composite_score and upsert top_n picks for pick_month.
    Returns the list of picked rows.
    """
    conn = psycopg2.connect(DB_URL)
    cur  = conn.cursor()

    # ── Verify composite scores exist ─────────────────────────────────────────
    cur.execute("""
        SELECT COUNT(*) FROM screener.universe
        WHERE is_asx200 = TRUE
          AND status = 'active'
          AND composite_score IS NOT NULL
    """)
    scored = cur.fetchone()[0]
    if scored == 0:
        log.error(
            "No ASX200 stocks have composite_score set. "
            "Run compute/engine/composite_score.py first."
        )
        cur.close()
        conn.close()
        return []

    log.info(f"ASX200 stocks with composite_score: {scored}")

    # ── Rank and select top N ─────────────────────────────────────────────────
    cur.execute(f"""
        SELECT
            u.asx_code,
            u.company_name,
            u.sector,
            u.industry,
            ROUND(u.composite_score::numeric, 2)   AS composite_score,
            ROUND(u.momentum_score::numeric, 2)    AS momentum_score,
            ROUND(u.quality_score::numeric, 2)     AS quality_score,
            ROUND(u.value_score::numeric, 2)       AS value_score,
            ROUND(u.income_score::numeric, 2)      AS income_score,
            ROUND(u.growth_score::numeric, 2)      AS growth_score,
            u.price,
            u.market_cap,
            u.pe_ratio,
            ROUND(u.dividend_yield::numeric, 4)    AS dividend_yield,
            ROUND(u.grossed_up_yield::numeric, 4)  AS grossed_up_yield,
            u.franking_pct,
            ROUND(u.return_3m::numeric, 4)         AS return_3m,
            ROUND(u.return_1y::numeric, 4)         AS return_1y,
            ROUND(u.roe::numeric, 4)               AS roe,
            u.piotroski_f_score
        FROM screener.universe u
        WHERE u.is_asx200 = TRUE
          AND u.status    = 'active'
          AND u.composite_score IS NOT NULL
          AND u.price IS NOT NULL
        ORDER BY u.composite_score DESC
        LIMIT {top_n}
    """)

    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]

    log.info(f"Top {top_n} picks for {pick_month.strftime('%B %Y')}:")
    for i, r in enumerate(rows, 1):
        log.info(
            f"  #{i:2d}  {r['asx_code']:6s}  {(r['company_name'] or '')[:35]:35s}"
            f"  composite={r['composite_score'] or 0:5.1f}"
            f"  price=${r['price'] or 0:.2f}"
        )

    if dry_run:
        log.info("DRY RUN — nothing written.")
        cur.close()
        conn.close()
        return rows

    # ── Upsert into strategy.monthly_picks ───────────────────────────────────
    # Delete existing picks for this month first (clean slate each run)
    cur.execute(
        "DELETE FROM strategy.monthly_picks WHERE pick_month = %s",
        (pick_month,)
    )
    deleted = cur.rowcount
    if deleted:
        log.info(f"Replaced {deleted} existing picks for {pick_month}")

    insert_rows = [
        (
            pick_month,
            rank,
            r["asx_code"],
            r["company_name"],
            r["sector"],
            r["industry"],
            r["composite_score"],
            r["momentum_score"],
            r["quality_score"],
            r["value_score"],
            r["income_score"],
            r["growth_score"],
            r["price"],
            r["market_cap"],
            r["pe_ratio"],
            r["dividend_yield"],
            r["grossed_up_yield"],
            r["franking_pct"],
            r["return_3m"],
            r["return_1y"],
            r["roe"],
            r["piotroski_f_score"],
        )
        for rank, r in enumerate(rows, 1)
    ]

    execute_values(cur, """
        INSERT INTO strategy.monthly_picks (
            pick_month, rank, asx_code, company_name, sector, industry,
            composite_score, momentum_score, quality_score,
            value_score, income_score, growth_score,
            price, market_cap, pe_ratio,
            dividend_yield, grossed_up_yield, franking_pct,
            return_3m, return_1y, roe, piotroski_f_score
        ) VALUES %s
        ON CONFLICT (pick_month, rank) DO UPDATE SET
            asx_code         = EXCLUDED.asx_code,
            company_name     = EXCLUDED.company_name,
            sector           = EXCLUDED.sector,
            industry         = EXCLUDED.industry,
            composite_score  = EXCLUDED.composite_score,
            momentum_score   = EXCLUDED.momentum_score,
            quality_score    = EXCLUDED.quality_score,
            value_score      = EXCLUDED.value_score,
            income_score     = EXCLUDED.income_score,
            growth_score     = EXCLUDED.growth_score,
            price            = EXCLUDED.price,
            market_cap       = EXCLUDED.market_cap,
            pe_ratio         = EXCLUDED.pe_ratio,
            dividend_yield   = EXCLUDED.dividend_yield,
            grossed_up_yield = EXCLUDED.grossed_up_yield,
            franking_pct     = EXCLUDED.franking_pct,
            return_3m        = EXCLUDED.return_3m,
            return_1y        = EXCLUDED.return_1y,
            roe              = EXCLUDED.roe,
            piotroski_f_score = EXCLUDED.piotroski_f_score,
            computed_at      = NOW()
    """, insert_rows)

    conn.commit()
    log.info(f"Inserted {len(rows)} picks for {pick_month}")

    # ── Verify total history ──────────────────────────────────────────────────
    cur.execute("SELECT COUNT(DISTINCT pick_month) FROM strategy.monthly_picks")
    months = cur.fetchone()[0]
    log.info(f"Total months in strategy.monthly_picks: {months}")

    cur.close()
    conn.close()
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--date",
        help="Pick month as YYYY-MM-DD (defaults to first day of current month)",
        default=None,
    )
    parser.add_argument(
        "--top-n", type=int, default=5,
        help="Number of picks to store (default 5)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print picks without writing to DB",
    )
    args = parser.parse_args()

    if args.date:
        d = datetime.strptime(args.date, "%Y-%m-%d").date()
        pick_month = d.replace(day=1)
    else:
        today = date.today()
        pick_month = today.replace(day=1)

    log.info(f"Top-{args.top_n} Strategy — pick month: {pick_month}")
    run(pick_month=pick_month, top_n=args.top_n, dry_run=args.dry_run)
    log.info("DONE")


if __name__ == "__main__":
    main()
