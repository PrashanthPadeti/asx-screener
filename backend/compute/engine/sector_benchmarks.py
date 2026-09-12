"""
ASX Screener — Sector Benchmarks Engine
=========================================
Computes median + P25/P75 benchmark statistics per GICS sector
from screener.universe and writes to market.sector_benchmarks.

Run weekly after build_screener_universe.py + composite_score.py.
The Peers tab uses this table to show "vs sector" context.

Usage:
    python compute/engine/sector_benchmarks.py
    python compute/engine/sector_benchmarks.py --dry-run
"""

import argparse
import json
import logging
import os
from datetime import datetime, timezone

import psycopg2
import psycopg2.extensions
from psycopg2.extras import execute_values
import pandas as pd
import numpy as np
from dotenv import load_dotenv
import sys
from pathlib import Path

# The database credential lives in the environment, never in source.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.core.db import get_database_url_sync  # noqa: E402


load_dotenv()

DB_URL = get_database_url_sync()

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

#: Benchmarks that go through the applicability contract. Every one of these
#: is either domain-sensitive or observation-sensitive, so aggregating them
#: raw is what produced a "Financials sector median debt_to_equity" with no
#: valid observation anywhere behind it. Names are canonical — ev_ebitda, not
#: the ev_to_ebitda spelling the universe column uses.
GOVERNED_BENCHMARK_METRICS = [
    "pe_ratio", "price_to_book", "ev_ebitda",
    "dividend_yield", "grossed_up_yield", "franking_pct",
    "roe", "net_margin", "gross_margin",
    "debt_to_equity", "current_ratio",
]

# net_margin is governed as of V1: NOT_MEANINGFUL for BANK, applicable
# everywhere else including other financials. Being governed is what lets the
# peer engine drop banks from the applicable population and still publish a
# Financials net-margin benchmark from the insurers, asset managers and
# exchanges that remain valid — rather than the two alternatives it had
# before, which were a mixed benchmark or none at all.

#: Deliberately left on the legacy path until migrated on purpose: EBITDA
#: margin, the growth rates, the return series and market cap. They are not
#: in the governed set, so nothing about them changes in this commit.
COLS = [
    "sector",
    "pe_ratio", "price_to_book", "ev_to_ebitda",
    "dividend_yield", "grossed_up_yield", "franking_pct",
    "roe", "net_margin", "gross_margin", "ebitda_margin",
    "revenue_growth_1y", "earnings_growth_1y",
    "debt_to_equity", "current_ratio",
    "return_1y", "return_ytd",
    "market_cap",
]


def _med(s: pd.Series) -> float | None:
    """Legacy aggregation, for UNGOVERNED metrics only.

    Every governed metric goes through peer_benchmarks.by_sector instead.
    Leaving two authorities computing the same statistic is how they end up
    disagreeing, so the split is by metric and enforced in _benchmark_columns:
    a governed metric that reached here would be a bug, not a fallback.
    """
    v = s.dropna()
    return float(np.median(v)) if len(v) >= 3 else None


def _pct(s: pd.Series, q: float) -> float | None:
    """Legacy aggregation, for UNGOVERNED metrics only. See _med."""
    v = s.dropna()
    return float(np.percentile(v, q * 100)) if len(v) >= 3 else None


def _governed_stat(bm, which: str) -> float | None:
    """One number out of a Benchmark, or None when it was withheld.

    The None is not the whole story and is never meant to be — the reason and
    the four population counts go into benchmark_states alongside it. This is
    only the numeric column, kept so existing readers are undisturbed.
    """
    if bm is None or not bm.ok:
        return None
    return getattr(bm, which)


def _benchmark_payload(results: dict) -> dict:
    """The sidecar: per-metric state, reason and denominators.

    Applicable benchmarks carry counts too, unlike the company sidecar. The
    counts are not an exception report; they are what lets a surface say
    "4.8%, 118 of 142 valid observations" rather than a bare percentage.
    """
    return {
        metric: {
            "state": bm.state.value,
            "reason_code": bm.reason_code.value if bm.reason_code else None,
            "reason": bm.reason,
            "n_total_peers": bm.n_total_peers,
            "n_applicable_peers": bm.n_applicable_peers,
            "n_valid_peers": bm.n_valid_peers,
            "coverage_pct": round(bm.coverage_pct, 1),
        }
        for metric, bm in results.items()
    }


def run(conn, dry_run: bool = False) -> int:
    from compute.engine.daily_compute import fetch_feed_health
    from compute.engine.dividends import DividendSource
    from compute.engine.factor_applicability import (
        DOMAIN_COLS, OBSERVATION_COLS, apply_applicability,
    )
    from compute.engine.peer_benchmarks import by_sector

    cur = conn.cursor()
    # asx_code keys the assessments; DOMAIN_COLS let the resolver decide each
    # company's economic model rather than inferring it from the sector label.
    select_cols = ["asx_code"] + COLS + [
        c for c in DOMAIN_COLS if c not in COLS and c != "asx_code"]
    # And OBSERVATION_COLS, without which gate 2 cannot run here at all.
    # apply_applicability builds its Observation from whatever columns the
    # frame happens to have, and this frame had none of them — so every
    # assessment in the peer path came from the domain gate, and QAN's
    # negative-equity ROE of 206% was still entering its sector's median.
    # That is the identical unwiring the factor path was carrying, surviving
    # in the one place whose output is a comparison baseline for everyone
    # else. The module docstring above describes the rule; this makes the
    # inputs available to enforce it.
    select_cols += [c for c in OBSERVATION_COLS.values()
                    if c not in select_cols]
    col_list = ", ".join(select_cols)
    cur.execute(f"""
        SELECT {col_list}
        FROM screener.universe
        WHERE status = 'active'
          AND price IS NOT NULL
          AND sector IS NOT NULL
    """)
    rows = cur.fetchall()

    feed_health = fetch_feed_health(cur)
    dividend_source = DividendSource(feed_health)
    cur.close()

    df = pd.DataFrame(rows, columns=select_cols)
    log.info(f"Loaded {len(df):,} stocks across {df['sector'].nunique()} sectors")

    numeric_cols = [c for c in select_cols
                    if c not in ("asx_code", "sector", "industry")]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # ── Assess before aggregating ─────────────────────────────────────────────
    # A peer statistic is a cross-sectional statistic, so the same rule holds:
    # suppression happens before the aggregate, not after. The assessments are
    # consumed directly rather than the masked frame, because a null in the
    # frame cannot say whether a peer left the applicable population or stayed
    # in it unmeasured — and that difference is the coverage denominator.
    if not feed_health.healthy:
        log.warning("Dividend feed unhealthy: %s. Income benchmarks will be "
                    "withheld with a stated cause.", feed_health.reason)

    masked = apply_applicability(df, dividend_source)
    sector_by_code = dict(zip(df["asx_code"], df["sector"]))
    governed_results = by_sector(masked.assessments, sector_by_code,
                                 GOVERNED_BENCHMARK_METRICS)

    now = datetime.now(tz=timezone.utc)
    upsert_rows = []

    for sector, grp in df.groupby("sector"):
        n = len(grp)
        if n < 2:
            continue

        gb = governed_results.get(sector, {})

        def g(metric: str, which: str):
            """A governed statistic, or None with its reason in the sidecar."""
            return _governed_stat(gb.get(metric), which)

        row = (
            sector,
            n,
            # ── Governed: assessed first, aggregated over valid peers only ──
            g("pe_ratio", "p25"), g("pe_ratio", "median"), g("pe_ratio", "p75"),
            g("price_to_book", "p25"), g("price_to_book", "median"),
            g("price_to_book", "p75"),
            g("ev_ebitda", "p25"), g("ev_ebitda", "median"),
            g("ev_ebitda", "p75"),
            g("dividend_yield", "median"), g("grossed_up_yield", "median"),
            g("franking_pct", "median"),
            g("roe", "p25"), g("roe", "median"), g("roe", "p75"),
            g("net_margin", "p25"), g("net_margin", "median"),
            g("net_margin", "p75"),
            g("gross_margin", "median"),
            # ── Ungoverned: legacy aggregation, deliberately untouched ──────
            _med(grp["ebitda_margin"]),
            _med(grp["revenue_growth_1y"]),
            _med(grp["earnings_growth_1y"]),
            # ── Governed again ───────────────────────────────────────────────
            g("debt_to_equity", "median"), g("current_ratio", "median"),
            # ── Ungoverned ───────────────────────────────────────────────────
            _med(grp["return_1y"]),
            _med(grp["return_ytd"]),
            _med(grp["market_cap"]),
            # updated_at
            now,
            # ── The sidecar: why a governed benchmark is missing, and the
            #    denominator behind every one that is not.
            json.dumps(_benchmark_payload(gb), separators=(",", ":"),
                       sort_keys=True),
        )
        upsert_rows.append(row)

        withheld = [m for m, bm in gb.items() if not bm.ok]
        log.info("  %-40s n=%4d  governed %d/%d published%s",
                 sector, n, len(gb) - len(withheld), len(gb),
                 f"  withheld: {', '.join(sorted(withheld))}" if withheld else "")

    if dry_run:
        log.info(f"Dry-run — would write {len(upsert_rows)} sector rows.")
        return len(upsert_rows)

    UPSERT_SQL = """
        INSERT INTO market.sector_benchmarks (
            gics_sector, stock_count,
            pe_ratio_p25, pe_ratio_median, pe_ratio_p75,
            price_to_book_p25, price_to_book_median, price_to_book_p75,
            ev_to_ebitda_p25, ev_to_ebitda_median, ev_to_ebitda_p75,
            dividend_yield_median, grossed_up_yield_median, franking_pct_median,
            roe_p25, roe_median, roe_p75,
            net_margin_p25, net_margin_median, net_margin_p75,
            gross_margin_median, ebitda_margin_median,
            revenue_growth_1y_median, earnings_growth_1y_median,
            debt_to_equity_median, current_ratio_median,
            return_1y_median, return_ytd_median,
            market_cap_median,
            updated_at,
            benchmark_states
        ) VALUES %s
        ON CONFLICT (gics_sector) DO UPDATE SET
            stock_count              = EXCLUDED.stock_count,
            pe_ratio_p25             = EXCLUDED.pe_ratio_p25,
            pe_ratio_median          = EXCLUDED.pe_ratio_median,
            pe_ratio_p75             = EXCLUDED.pe_ratio_p75,
            price_to_book_p25        = EXCLUDED.price_to_book_p25,
            price_to_book_median     = EXCLUDED.price_to_book_median,
            price_to_book_p75        = EXCLUDED.price_to_book_p75,
            ev_to_ebitda_p25         = EXCLUDED.ev_to_ebitda_p25,
            ev_to_ebitda_median      = EXCLUDED.ev_to_ebitda_median,
            ev_to_ebitda_p75         = EXCLUDED.ev_to_ebitda_p75,
            dividend_yield_median    = EXCLUDED.dividend_yield_median,
            grossed_up_yield_median  = EXCLUDED.grossed_up_yield_median,
            franking_pct_median      = EXCLUDED.franking_pct_median,
            roe_p25                  = EXCLUDED.roe_p25,
            roe_median               = EXCLUDED.roe_median,
            roe_p75                  = EXCLUDED.roe_p75,
            net_margin_p25           = EXCLUDED.net_margin_p25,
            net_margin_median        = EXCLUDED.net_margin_median,
            net_margin_p75           = EXCLUDED.net_margin_p75,
            gross_margin_median      = EXCLUDED.gross_margin_median,
            ebitda_margin_median     = EXCLUDED.ebitda_margin_median,
            revenue_growth_1y_median = EXCLUDED.revenue_growth_1y_median,
            earnings_growth_1y_median= EXCLUDED.earnings_growth_1y_median,
            debt_to_equity_median    = EXCLUDED.debt_to_equity_median,
            current_ratio_median     = EXCLUDED.current_ratio_median,
            return_1y_median         = EXCLUDED.return_1y_median,
            return_ytd_median        = EXCLUDED.return_ytd_median,
            market_cap_median        = EXCLUDED.market_cap_median,
            updated_at               = NOW()
    """

    cur = conn.cursor()
    execute_values(cur, UPSERT_SQL, upsert_rows, page_size=50)
    conn.commit()
    cur.close()

    log.info(f"  ✓ {len(upsert_rows)} sector benchmarks written to market.sector_benchmarks")
    return len(upsert_rows)


def main():
    parser = argparse.ArgumentParser(description="Compute sector benchmark statistics")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    conn = psycopg2.connect(DB_URL)
    try:
        n = run(conn, dry_run=args.dry_run)
    finally:
        conn.close()

    log.info(f"Sector benchmarks complete — {n} sectors processed.")


if __name__ == "__main__":
    main()
