"""
ASX Screener — Pros / Cons Engine
====================================
Evaluates ~25 bullish and ~15 bearish rules against screener.universe
and writes pre-computed signal lists to screener.universe.pros / .cons.

Running after build_screener_universe.py means the rules operate on the
latest Golden Record data. Signals are plain-English strings ready for
direct display in the company UI.

All threshold constants are defined at the top so they're easy to tune.

Usage:
    python compute/engine/pros_cons.py
    python compute/engine/pros_cons.py --dry-run
    python compute/engine/pros_cons.py --codes BHP CBA ANZ
"""

import argparse
import logging
import os
from typing import Optional

import psycopg2
import psycopg2.extensions
from psycopg2.extras import execute_values
import pandas as pd
import numpy as np
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv(
    "DATABASE_URL_SYNC",
    "postgresql://asx_user:asx_secure_2024@localhost:5432/asx_screener"
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

# ── Thresholds (easy to tune) ─────────────────────────────────────────────────
T = {
    # Dividends
    "div_yield_attractive":    0.04,    # 4%
    "div_yield_exceptional":   0.07,    # 7%
    "grossed_up_high":         0.08,    # 8% grossed-up
    "consecutive_divs_good":   5,
    "consecutive_divs_great":  10,
    "div_cagr_good":           0.05,    # 5% CAGR
    "payout_sustainable":      0.80,    # 80% — below this is sustainable
    "payout_unsustainable":    1.00,    # 100%+ is unsustainable

    # Quality
    "piotroski_strong":        7,
    "piotroski_weak":          2,
    "roe_good":                0.15,    # 15%
    "roe_exceptional":         0.25,    # 25%
    "net_margin_good":         0.15,    # 15%
    "altman_safe":             2.99,
    "altman_distress":         1.81,

    # Leverage
    "d_to_e_low":              0.30,
    "d_to_e_high":             2.00,
    "current_ratio_strong":    2.00,
    "current_ratio_weak":      1.00,

    # Growth
    "revenue_growth_good":     0.10,    # 10%
    "revenue_growth_weak":    -0.05,   # -5%
    "eps_cagr_good":           0.10,

    # Valuation
    "pe_expensive":            40,
    "analyst_upside_good":     0.15,    # 15%
    "analyst_downside_bad":   -0.10,   # -10%

    # Technical
    "rsi_oversold":            35,
    "rsi_overbought":          75,

    # Short interest
    "short_low":               2.0,     # 2% — very low
    "short_high":              8.0,     # 8% — elevated
    "short_rising_1w":         1.5,     # +1.5pp WoW — rising materially

    # Returns
    "return_1y_strong":        0.25,    # +25%
    "return_1y_weak":         -0.20,   # -20%

    # Drawdown
    "drawdown_severe":        -0.50,   # -50% from ATH
}

# ── Columns to fetch ──────────────────────────────────────────────────────────
COLS = [
    "asx_code",
    "dividend_yield", "grossed_up_yield", "franking_pct",
    "dividend_consecutive_yrs", "dividend_cagr_3y", "payout_ratio",
    "piotroski_f_score", "altman_z_score",
    "roe", "roce", "net_margin",
    "debt_to_equity", "current_ratio", "net_debt",
    "revenue_growth_1y", "eps_growth_3y_cagr",
    "revenue_growth_hoh", "net_income_growth_hoh",
    "pe_ratio", "fcf_fy0",
    "analyst_upside", "analyst_target_price",
    "return_1y", "drawdown_from_ath",
    "short_pct", "short_interest_chg_1w",
    "rsi_14", "price", "sma_200",
]


def fmt_pct(v: float, decimals: int = 1) -> str:
    return f"{v * 100:.{decimals}f}%"


def eval_row(r: pd.Series) -> tuple[list[str], list[str]]:
    """Evaluate all rules for one stock. Returns (pros, cons)."""
    pros: list[str] = []
    cons: list[str] = []

    def v(col) -> Optional[float]:
        val = r.get(col)
        if val is None or (isinstance(val, float) and np.isnan(val)):
            return None
        return float(val)

    # ── BULLISH SIGNALS ───────────────────────────────────────────────────────

    # Dividends
    dy = v("dividend_yield")
    gy = v("grossed_up_yield")
    fk = v("franking_pct")
    cr = v("dividend_consecutive_yrs")
    dc = v("dividend_cagr_3y")
    pr = v("payout_ratio")

    if dy is not None and dy >= T["div_yield_exceptional"]:
        pros.append(f"Exceptional dividend yield {fmt_pct(dy)} — well above market average")
    elif dy is not None and dy >= T["div_yield_attractive"]:
        pros.append(f"Attractive dividend yield {fmt_pct(dy)} — above market average")

    if gy is not None and gy >= T["grossed_up_high"]:
        pros.append(f"High grossed-up yield {fmt_pct(gy)} — excellent after-tax income for Australian investors")

    if fk is not None and fk == 100:
        pros.append("Fully franked dividends — 100% tax credit for Australian shareholders")
    elif fk is not None and fk >= 70:
        pros.append(f"{fk:.0f}% franked dividends — substantial tax credit for Australian investors")

    if cr is not None:
        n = int(cr)
        if n >= T["consecutive_divs_great"]:
            pros.append(f"{n} consecutive years of dividends — long track record of shareholder returns")
        elif n >= T["consecutive_divs_good"]:
            pros.append(f"{n} consecutive years of dividends — consistent income history")

    if dc is not None and dc >= T["div_cagr_good"]:
        pros.append(f"Dividend growing at {fmt_pct(dc)} CAGR (3Y) — rising income stream")

    if pr is not None and pr > 0 and pr <= T["payout_sustainable"]:
        pros.append(f"Sustainable payout ratio {fmt_pct(pr)} — room to grow dividends")

    # Quality
    pf = v("piotroski_f_score")
    az = v("altman_z_score")
    roe_v = v("roe")
    roce_v = v("roce")
    nm = v("net_margin")

    if pf is not None and pf >= T["piotroski_strong"]:
        pros.append(f"Strong Piotroski F-Score {int(pf)}/9 — financially healthy company")

    if az is not None and az >= T["altman_safe"]:
        pros.append(f"Altman Z-Score {az:.1f} — low financial distress risk")

    if roe_v is not None and roe_v >= T["roe_exceptional"]:
        pros.append(f"Exceptional ROE {fmt_pct(roe_v)} — outstanding return on equity")
    elif roe_v is not None and roe_v >= T["roe_good"]:
        pros.append(f"Strong ROE {fmt_pct(roe_v)} — efficient use of shareholder equity")

    if nm is not None and nm >= T["net_margin_good"]:
        pros.append(f"High net margin {fmt_pct(nm)} — highly profitable business")

    # Balance sheet
    de = v("debt_to_equity")
    cur = v("current_ratio")
    nd = v("net_debt")

    if de is not None and 0 <= de <= T["d_to_e_low"]:
        pros.append(f"Low debt-to-equity {de:.2f}x — strong balance sheet")
    if cur is not None and cur >= T["current_ratio_strong"]:
        pros.append(f"Strong current ratio {cur:.1f}x — excellent short-term liquidity")
    if nd is not None and nd < 0:
        pros.append(f"Net cash position ${abs(nd):.0f}M — no net debt")

    # Cash flow
    fcf = v("fcf_fy0")
    if fcf is not None and fcf > 0:
        pros.append(f"Positive free cash flow ${fcf:.0f}M — self-funding business")

    # Growth
    rg1 = v("revenue_growth_1y")
    ec3 = v("eps_growth_3y_cagr")
    rgh = v("revenue_growth_hoh")

    if rg1 is not None and rg1 >= T["revenue_growth_good"]:
        pros.append(f"Revenue grew {fmt_pct(rg1)} last year — strong top-line momentum")
    if ec3 is not None and ec3 >= T["eps_cagr_good"]:
        pros.append(f"EPS CAGR {fmt_pct(ec3)} over 3 years — sustained earnings growth")
    if rgh is not None and rgh > 0:
        pros.append(f"Revenue accelerating half-over-half {fmt_pct(rgh)} ★ — positive half-yearly trend")

    # Technical
    rsi = v("rsi_14")
    price_v = v("price")
    sma200 = v("sma_200")
    r1y = v("return_1y")
    au = v("analyst_upside")
    short = v("short_pct")

    if rsi is not None and rsi <= T["rsi_oversold"]:
        pros.append(f"RSI {rsi:.0f} — potentially oversold / attractive entry point")
    if price_v is not None and sma200 is not None and price_v > sma200:
        pros.append("Trading above 200-day moving average — long-term uptrend intact")
    if r1y is not None and r1y >= T["return_1y_strong"]:
        pros.append(f"Up {fmt_pct(r1y)} in the past year — strong price momentum")

    # Analyst
    if au is not None and au >= T["analyst_upside_good"]:
        pros.append(f"Analyst consensus target {fmt_pct(au)} above current price")

    # Short interest
    if short is not None and short <= T["short_low"]:
        pros.append(f"Very low short interest {short:.1f}% — minimal bearish positioning")

    # ── BEARISH SIGNALS ───────────────────────────────────────────────────────

    # Profitability
    if nm is not None and nm < 0:
        cons.append("Currently operating at a net loss")

    # Quality
    if pf is not None and pf <= T["piotroski_weak"]:
        cons.append(f"Weak Piotroski F-Score {int(pf)}/9 — financial health concerns")
    if az is not None and az < T["altman_distress"]:
        cons.append(f"Altman Z-Score {az:.1f} — elevated financial distress risk")

    # Leverage
    if de is not None and de > T["d_to_e_high"]:
        cons.append(f"High debt-to-equity {de:.1f}x — elevated leverage")
    if cur is not None and cur < T["current_ratio_weak"]:
        cons.append(f"Current ratio {cur:.1f}x below 1 — near-term liquidity risk")

    # Dividends
    if pr is not None and pr > T["payout_unsustainable"]:
        cons.append(f"Payout ratio {fmt_pct(pr)} — dividend may be unsustainable")

    # Growth
    if rg1 is not None and rg1 < T["revenue_growth_weak"]:
        cons.append(f"Revenue declined {fmt_pct(abs(rg1))} last year")

    # Valuation
    pe_v = v("pe_ratio")
    if pe_v is not None and pe_v > T["pe_expensive"]:
        cons.append(f"High P/E {pe_v:.1f}x — premium valuation requires strong growth")

    # Technical
    if rsi is not None and rsi >= T["rsi_overbought"]:
        cons.append(f"RSI {rsi:.0f} — potentially overbought / extended")
    if r1y is not None and r1y < T["return_1y_weak"]:
        cons.append(f"Down {fmt_pct(abs(r1y))} in the past year — significant underperformance")

    # Drawdown
    dd = v("drawdown_from_ath")
    if dd is not None and dd <= T["drawdown_severe"]:
        cons.append(f"Down {fmt_pct(abs(dd))} from all-time high — deep drawdown")

    # Analyst
    if au is not None and au <= T["analyst_downside_bad"]:
        cons.append(f"Analyst consensus target {fmt_pct(au)} below current price")

    # Short interest
    if short is not None and short >= T["short_high"]:
        cons.append(f"{short:.1f}% short interest — elevated bearish positioning")

    chg_1w = v("short_interest_chg_1w")
    if chg_1w is not None and chg_1w >= T["short_rising_1w"]:
        cons.append(f"Short interest rising +{chg_1w:.1f}pp this week — increasing bearish pressure")

    return pros, cons


def run(conn, codes: Optional[list[str]] = None, dry_run: bool = False) -> int:
    """Compute pros/cons for all (or listed) stocks and write to DB."""
    log.info("Loading screener.universe for pros/cons computation…")

    cur = conn.cursor()
    col_list = ", ".join(COLS)

    if codes:
        placeholders = ",".join(["%s"] * len(codes))
        cur.execute(
            f"SELECT {col_list} FROM screener.universe WHERE asx_code IN ({placeholders})",
            [c.upper() for c in codes]
        )
    else:
        cur.execute(
            f"SELECT {col_list} FROM screener.universe WHERE status = 'active' AND price IS NOT NULL"
        )

    rows = cur.fetchall()
    cur.close()

    if not rows:
        log.warning("No rows found")
        return 0

    df = pd.DataFrame(rows, columns=COLS)
    log.info(f"  Evaluating {len(df):,} stocks…")

    # Coerce numerics
    for col in COLS[1:]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    results = []
    for _, row in df.iterrows():
        pros, cons = eval_row(row)
        results.append((row["asx_code"], pros, cons))

    # Sample log
    sample = results[:3]
    for code, pros, cons in sample:
        log.info(f"  {code}: {len(pros)} pros, {len(cons)} cons")

    if dry_run:
        log.info("Dry-run mode — skipping DB write.")
        return len(results)

    UPDATE_SQL = """
        UPDATE screener.universe
        SET pros = data.pros, cons = data.cons
        FROM (VALUES %s) AS data(asx_code, pros, cons)
        WHERE screener.universe.asx_code = data.asx_code
    """

    update_rows = [
        (code, pros, cons)
        for code, pros, cons in results
    ]

    cur = conn.cursor()
    execute_values(
        cur, UPDATE_SQL, update_rows,
        template="(%s, %s::TEXT[], %s::TEXT[])",
        page_size=500,
    )
    conn.commit()
    cur.close()

    log.info(f"  ✓ {len(update_rows):,} rows updated")
    return len(update_rows)


def main():
    parser = argparse.ArgumentParser(description="Compute pros/cons signals for all stocks")
    parser.add_argument("--codes", nargs="+", help="Only process these ASX codes")
    parser.add_argument("--dry-run", action="store_true", help="Compute without writing to DB")
    args = parser.parse_args()

    conn = psycopg2.connect(DB_URL)
    try:
        n = run(conn, codes=args.codes, dry_run=args.dry_run)
    finally:
        conn.close()

    log.info(f"Pros/cons engine complete — {n} stocks processed.")


if __name__ == "__main__":
    main()
