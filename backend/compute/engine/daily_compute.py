"""
ASX Screener — Daily Compute Engine
=====================================
Computes all daily metrics for each stock and inserts into
market.computed_metrics (TimescaleDB hypertable).

Metrics computed:
  - Market cap, Enterprise Value
  - P/E, P/B, P/S, EV/EBITDA ratios
  - Dividend yield, Grossed-up yield (franking credits)
  - ROE, ROA, ROCE
  - Debt/Equity, Current ratio, Interest coverage
  - Revenue/Profit growth (1Y, 3Y, 5Y)
  - Piotroski F-Score (9 criteria)
  - FCF yield, OCF margin

Run after market close:
    python compute/engine/daily_compute.py
    python compute/engine/daily_compute.py --codes BHP CBA  # specific stocks
    python compute/engine/daily_compute.py --limit 100      # first N stocks
"""

import os
import sys
import logging
import argparse
from datetime import datetime, timezone
from typing import Optional

import psycopg2
import psycopg2.extensions
from psycopg2.extras import execute_values
import pandas as pd
import numpy as np
from dotenv import load_dotenv
from pathlib import Path

# The database credential lives in the environment, never in source.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.core.db import get_database_url_sync  # noqa: E402
from compute.engine.dividends import DividendSource, FeedHealth  # noqa: E402


# Auto-cast PostgreSQL NUMERIC/DECIMAL → Python float on read.
# Prevents "unsupported operand type(s) for +: decimal.Decimal and float" errors
# throughout all metric calculations.
_DEC2FLOAT = psycopg2.extensions.new_type(
    psycopg2.extensions.DECIMAL.values,
    "DEC2FLOAT",
    lambda value, curs: float(value) if value is not None else None,
)
psycopg2.extensions.register_type(_DEC2FLOAT)

load_dotenv()

DB_URL = get_database_url_sync()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

COMPUTE_VERSION = "1.0.0"


# ── Data Fetchers ─────────────────────────────────────────────

def fetch_latest_price(cur, asx_code: str) -> Optional[dict]:
    cur.execute("""
        SELECT close, volume, time::date as price_date
        FROM market.daily_prices
        WHERE asx_code = %s
        ORDER BY time DESC LIMIT 1
    """, (asx_code,))
    row = cur.fetchone()
    if not row:
        return None
    return {"close": row[0], "volume": row[1], "price_date": row[2]}


def fetch_financials(cur, asx_code: str) -> dict:
    """Fetch latest annual P&L, Balance Sheet, Cash Flow."""
    # Annual P&L — last 5 years
    cur.execute("""
        SELECT fiscal_year, revenue, gross_profit, ebitda, ebit,
               net_profit, pat, eps, dps, dps_franking_pct,
               interest_expense, tax, depreciation
        FROM financials.annual_pnl
        WHERE asx_code = %s
        ORDER BY fiscal_year DESC
        LIMIT 5
    """, (asx_code,))
    pnl_rows = cur.fetchall()
    pnl_cols = ["fiscal_year","revenue","gross_profit","ebitda","ebit",
                "net_profit","pat","eps","dps","dps_franking_pct",
                "interest_expense","tax","depreciation"]
    pnl = [dict(zip(pnl_cols, r)) for r in pnl_rows]

    # Balance Sheet — latest
    cur.execute("""
        SELECT total_assets, total_liabilities, total_equity,
               total_debt, net_debt, cash_equivalents,
               total_current_assets, total_current_liab,
               shares_outstanding, book_value_per_share,
               goodwill, intangibles, inventory, trade_receivables
        FROM financials.annual_balance_sheet
        WHERE asx_code = %s
        ORDER BY fiscal_year DESC LIMIT 1
    """, (asx_code,))
    bs_row = cur.fetchone()
    bs_cols = ["total_assets","total_liabilities","total_equity",
               "total_debt","net_debt","cash_equivalents",
               "total_current_assets","total_current_liab",
               "shares_outstanding","book_value_per_share",
               "goodwill","intangibles","inventory","trade_receivables"]
    bs = dict(zip(bs_cols, bs_row)) if bs_row else {}

    # Cash Flow — latest
    cur.execute("""
        SELECT cfo, cfi, cff, capex, fcf, dividends_paid
        FROM financials.annual_cashflow
        WHERE asx_code = %s
        ORDER BY fiscal_year DESC LIMIT 1
    """, (asx_code,))
    cf_row = cur.fetchone()
    cf_cols = ["cfo","cfi","cff","capex","fcf","dividends_paid"]
    cf = dict(zip(cf_cols, cf_row)) if cf_row else {}

    return {"pnl": pnl, "bs": bs, "cf": cf}


def fetch_company(cur, asx_code: str) -> dict:
    cur.execute("""
        SELECT shares_outstanding, is_reit, is_miner
        FROM market.companies WHERE asx_code = %s
    """, (asx_code,))
    row = cur.fetchone()
    if not row:
        return {}
    return {"shares_outstanding": row[0], "is_reit": row[1], "is_miner": row[2]}


def fetch_feed_health(cur, as_of=None) -> FeedHealth:
    """The dividend feed's watermark, read once per run.

    Exchange-wide rather than per company: one issuer's gap is
    indistinguishable from a skipped dividend, but a feed that has recorded
    nothing for weeks is unambiguous. Measured on production in September
    2026 this returned 2026-08-03 with zero rows in the preceding 30 days,
    which is what a trailing-twelve-month window cannot honestly be computed
    over.
    """
    cur.execute("""
        SELECT MAX(ex_date),
               COUNT(*) FILTER (WHERE ex_date > NOW() - INTERVAL '30 days'),
               COUNT(DISTINCT asx_code)
                   FILTER (WHERE ex_date > NOW() - INTERVAL '30 days')
        FROM market.dividends
    """)
    latest, recent_rows, recent_issuers = cur.fetchone()
    return FeedHealth(latest_ex_date=latest,
                      as_of=as_of or datetime.now(timezone.utc).date(),
                      recent_rows=recent_rows,
                      recent_issuers=recent_issuers)


def fetch_dividends(cur, asx_code: str) -> list:
    """Fetch last 3 years of dividends."""
    cur.execute("""
        SELECT ex_date, amount_per_share, franking_pct, grossed_up_amount
        FROM market.dividends
        WHERE asx_code = %s AND ex_date >= NOW() - INTERVAL '3 years'
        ORDER BY ex_date DESC
    """, (asx_code,))
    rows = cur.fetchall()
    return [{"ex_date": r[0], "amount": r[1], "franking_pct": r[2], "grossed_up": r[3]} for r in rows]


# ── Metric Calculations ───────────────────────────────────────

def safe_div(a, b, default=None):
    """Safe division — returns default if b is None/0."""
    try:
        if a is None or b is None or b == 0:
            return default
        return float(a) / float(b)
    except Exception:
        return default


def _observed(row: dict, field: str) -> Optional[float]:
    """One observation, distinguishing an economic zero from missing data.

    Truthiness is what made this necessary. The previous code filtered with
    ``if p.get("revenue")``, which discards 0.0 as readily as None — so a
    year of zero revenue vanished from the series entirely rather than being
    recorded as a year in which revenue was zero.
    """
    value = row.get(field)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def growth_over(pnl: list, field: str, n: int) -> Optional[float]:
    """CAGR over exactly n fiscal years, anchored to the latest reported year.

    FACTOR_MODEL_V2. The previous form took values[n] from a list built as
    ``[p[field] for p in pnl if p.get(field)]`` — n POSITIONS back, in a
    series that had already dropped every year whose value was null or zero.

    Both halves did damage, and the second was worse. Dropping zero years
    removed the *latest* observation too, so values[0] was not the current
    year: for a company whose revenue had fallen to zero, this compared two
    historical non-zero years and served the result as current growth.
    Measured on production, EXR reported +450.7% where the exact Y-3
    comparison gives -100%, and seven other companies showed the same
    signature.

    The contract now:

        required fiscal year absent   -> None (unavailable, no observation)
        base observation is 0         -> None (undefined, not "no history")
        latest observation is 0       -> -1.0, i.e. -100%

    Zero is an observation. A value that fell to nothing did not go missing,
    and reporting -100% is the honest answer; only the absence of the period
    itself makes the metric unavailable. That distinction is what the
    truthiness check destroyed.
    """
    by_year = {int(p["fiscal_year"]): p for p in pnl
               if p.get("fiscal_year") is not None}
    if not by_year:
        return None

    latest_year = max(by_year)
    prior = by_year.get(latest_year - n)
    if prior is None:
        return None

    latest = _observed(by_year[latest_year], field)
    base = _observed(prior, field)
    if latest is None or base is None:
        return None
    # A zero or negative base leaves the ratio undefined, which is a property
    # of the arithmetic and not of the history. It must not be reported as an
    # absent period.
    if base <= 0 or latest < 0:
        return None
    if latest == 0:
        return -1.0
    try:
        return (latest / base) ** (1 / n) - 1
    except Exception:
        return None


def calc_piotroski(pnl: list, bs: dict, cf: dict) -> Optional[int]:
    """
    Piotroski F-Score (0-9). Higher = better financial quality.
    Each criterion scores 0 or 1.
    """
    if not pnl or not bs or not cf:
        return None

    p = pnl[0]       # Latest year
    p1 = pnl[1] if len(pnl) > 1 else {}  # Prior year
    score = 0

    # Profitability (4 signals)
    # F1: ROA > 0
    roa = safe_div(p.get("net_profit"), bs.get("total_assets"))
    if roa and roa > 0: score += 1

    # F2: CFO > 0
    if cf.get("cfo") and cf["cfo"] > 0: score += 1

    # F3: ROA improved YoY
    if p1:
        roa_prev = safe_div(p1.get("net_profit"), bs.get("total_assets"))
        if roa and roa_prev and roa > roa_prev: score += 1

    # F4: CFO > Net Income (accruals)
    net = p.get("net_profit") or 0
    cfo = cf.get("cfo") or 0
    if cfo > net: score += 1

    # Leverage (3 signals)
    # F5: Lower long-term debt ratio YoY (skip — need 2 BS years)
    score += 1  # Give benefit of doubt for now

    # F6: Higher current ratio YoY (skip — need 2 BS years)
    cr = safe_div(bs.get("total_current_assets"), bs.get("total_current_liab"))
    if cr and cr > 1: score += 1

    # F7: No new shares issued (skip — need share count history)
    score += 1  # Neutral for now

    # Operating efficiency (2 signals)
    # F8: Higher gross margin YoY
    if p1 and p.get("revenue") and p.get("gross_profit"):
        gm_cur  = safe_div(p.get("gross_profit"), p.get("revenue"))
        gm_prev = safe_div(p1.get("gross_profit"), p1.get("revenue"))
        if gm_cur and gm_prev and gm_cur > gm_prev: score += 1

    # F9: Higher asset turnover YoY
    if p1 and p.get("revenue") and bs.get("total_assets"):
        at_cur  = safe_div(p.get("revenue"), bs.get("total_assets"))
        at_prev = safe_div(p1.get("revenue"), bs.get("total_assets"))
        if at_cur and at_prev and at_cur > at_prev: score += 1

    return min(score, 9)


def compute_metrics(asx_code: str, price: dict, fin: dict, company: dict,
                    divs: list, dividend_source: DividendSource) -> dict:
    """Compute all metrics for a stock. Returns dict matching computed_metrics columns."""

    m = {}  # metrics dict
    now = datetime.now(tz=timezone.utc)

    pnl = fin.get("pnl", [])
    bs  = fin.get("bs", {})
    cf  = fin.get("cf", {})

    close  = price.get("close")
    p0     = pnl[0] if pnl else {}
    shares = bs.get("shares_outstanding") or company.get("shares_outstanding")

    # Market Cap (AUD millions)
    if close and shares:
        m["market_cap"] = round(close * shares / 1_000_000, 2)

    # Enterprise Value = Market Cap + Net Debt
    net_debt = bs.get("net_debt")
    if m.get("market_cap") and net_debt is not None:
        m["enterprise_value"] = round(m["market_cap"] + float(net_debt), 2)

    # ── Valuation Ratios ──────────────────────────────────────

    # P/E
    eps = p0.get("eps")
    if close and eps and eps > 0:
        m["pe_ratio"] = round(close / float(eps), 2)

    # P/B
    bvps = bs.get("book_value_per_share")
    if close and bvps and float(bvps) > 0:
        m["pb_ratio"] = round(close / float(bvps), 2)

    # P/S
    rev = p0.get("revenue")
    if m.get("market_cap") and rev and float(rev) > 0:
        m["ps_ratio"] = round(m["market_cap"] / float(rev), 2)

    # EV/EBITDA
    ebitda = p0.get("ebitda")
    if m.get("enterprise_value") and ebitda and float(ebitda) > 0:
        m["ev_ebitda"] = round(m["enterprise_value"] / float(ebitda), 2)

    # EV/EBIT
    ebit = p0.get("ebit")
    if m.get("enterprise_value") and ebit and float(ebit) > 0:
        m["ev_ebit"] = round(m["enterprise_value"] / float(ebit), 2)

    # ── Dividend Yield ────────────────────────────────────────

    # The five dividend fields come from the canonical module, which selects a
    # period-based trailing-twelve-month window rather than a fixed four
    # payments, grosses up per payment from market.dividends.grossed_up_amount
    # rather than averaging franking across an aggregate, and declines to
    # report anything at all when the feed has not observed the end of the
    # window. All five keys are always present: upsert_metrics builds its
    # UPDATE clause from the keys in this dict, so an omitted field keeps
    # whatever the last run wrote — which is how OEL carried a 480%
    # grossed-up yield against a zero dividend.
    m.update(dividend_source.metrics(divs, close, as_of=price["price_date"]))

    ttm_dps = m["dividend_per_share"]

    # Payout ratio rides on the same TTM figure, so a refused dividend cannot
    # leave a payout ratio behind that implies one.
    net_profit = p0.get("net_profit")
    if ttm_dps and shares and net_profit and float(net_profit) > 0:
        total_div = float(ttm_dps) * float(shares) / 1_000_000
        m["dividend_payout_ratio"] = round(safe_div(total_div, float(net_profit)) or 0, 4)
    else:
        m["dividend_payout_ratio"] = None

    # ── Profitability ─────────────────────────────────────────

    equity   = bs.get("total_equity")
    assets   = bs.get("total_assets")
    net_prof = p0.get("net_profit")

    if net_prof and equity and float(equity) > 0:
        m["roe"] = round(float(net_prof) / float(equity), 6)

    if net_prof and assets and float(assets) > 0:
        m["roa"] = round(float(net_prof) / float(assets), 6)

    if ebit and equity and assets:
        capital_employed = float(assets) - (bs.get("total_current_liab") or 0)
        if capital_employed > 0:
            m["roce"] = round(float(ebit) / capital_employed, 6)

    if rev:
        rev_f = float(rev)
        if p0.get("gross_profit") and rev_f > 0:
            m["gpm"] = round(float(p0["gross_profit"]) / rev_f, 6)
        if ebit and rev_f > 0:
            m["opm"] = round(float(ebit) / rev_f, 6)
        if net_prof and rev_f > 0:
            m["npm"] = round(float(net_prof) / rev_f, 6)
        if ebitda and rev_f > 0:
            m["ebitda_margin"] = round(float(ebitda) / rev_f, 6)

    # ── Financial Health ──────────────────────────────────────

    total_debt = bs.get("total_debt")
    if total_debt is not None and equity and float(equity) > 0:
        m["debt_to_equity"] = round(float(total_debt) / float(equity), 4)

    cur_assets = bs.get("total_current_assets")
    cur_liab   = bs.get("total_current_liab")
    if cur_assets and cur_liab and float(cur_liab) > 0:
        m["current_ratio"] = round(float(cur_assets) / float(cur_liab), 4)

    cash = bs.get("cash_equivalents")
    if cash and cur_liab and float(cur_liab) > 0:
        m["cash_ratio"] = round(float(cash) / float(cur_liab), 4)

    int_exp = p0.get("interest_expense")
    if ebit and int_exp and float(int_exp) > 0:
        m["interest_coverage"] = round(float(ebit) / abs(float(int_exp)), 4)

    if net_debt is not None and ebitda and float(ebitda) > 0:
        m["net_debt_to_ebitda"] = round(float(net_debt) / float(ebitda), 4)

    # ── Cash Flow ─────────────────────────────────────────────

    cfo = cf.get("cfo")
    fcf = cf.get("fcf")

    if fcf and m.get("market_cap") and m["market_cap"] > 0:
        m["fcf_yield"] = round(float(fcf) / m["market_cap"], 6)

    if cfo and net_prof and float(net_prof) != 0:
        m["ocf_to_net_income"] = round(float(cfo) / abs(float(net_prof)), 4)

    if cfo and rev and float(rev) > 0:
        m["ocf_margin"] = round(float(cfo) / float(rev), 6)

    # ── Growth ───────────────────────────────────────────────

    # Year-anchored, not positional. growth_over locates the required fiscal
    # year itself, so the length guards that used to stand in for history
    # ("at least 4 rows exist, therefore a 3-year window exists") are gone —
    # they were counting rows in a list that had already been compacted.
    m["revenue_growth_1y"] = growth_over(pnl, "revenue", 1)
    m["revenue_growth_3y"] = growth_over(pnl, "revenue", 3)
    m["profit_growth_1y"]  = growth_over(pnl, "net_profit", 1)
    m["profit_growth_3y"]  = growth_over(pnl, "net_profit", 3)

    # ── Quality Scores ────────────────────────────────────────

    m["piotroski_score"] = calc_piotroski(pnl, bs, cf)

    # ── TTM Reference Values ──────────────────────────────────

    if rev:        m["revenue_ttm"]    = float(rev)
    if ebitda:     m["ebitda_ttm"]     = float(ebitda)
    if ebit:       m["ebit_ttm"]       = float(ebit)
    if net_prof:   m["net_profit_ttm"] = float(net_prof)
    if eps:        m["eps_ttm"]        = float(eps)

    # ── Per Share ─────────────────────────────────────────────

    if eps:   m["eps_ttm_ref"] = float(eps)
    if bvps:  m["book_value_per_share"] = float(bvps)

    # Metadata
    m["compute_version"] = COMPUTE_VERSION
    m["computed_at"]     = now

    return m


# ── Database Write ────────────────────────────────────────────

def upsert_metrics(cur, asx_code: str, price_date, metrics: dict):
    """Insert one row into market.computed_metrics."""
    # Build dynamic INSERT for only the non-None columns
    time_val = datetime.combine(price_date, datetime.min.time()).replace(tzinfo=timezone.utc)

    cols   = ["time", "asx_code"] + list(metrics.keys())
    vals   = [time_val, asx_code] + list(metrics.values())
    placeholders = ", ".join(["%s"] * len(cols))
    col_str      = ", ".join(cols)
    update_str   = ", ".join([f"{c} = EXCLUDED.{c}" for c in metrics.keys()])

    sql = f"""
        INSERT INTO market.computed_metrics ({col_str})
        VALUES ({placeholders})
        ON CONFLICT (time, asx_code) DO UPDATE SET {update_str}
    """
    cur.execute(sql, vals)


# ── Main ──────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="ASX Compute Engine — daily metrics")
    parser.add_argument("--codes", nargs="+", help="Specific ASX codes")
    parser.add_argument("--limit", type=int, help="Max stocks to process")
    args = parser.parse_args()

    conn = psycopg2.connect(DB_URL)
    cur  = conn.cursor()

    # Get codes to process
    if args.codes:
        codes = [c.upper() for c in args.codes]
    else:
        sql = """
            SELECT DISTINCT p.asx_code
            FROM market.daily_prices p
            JOIN market.companies c ON c.asx_code = p.asx_code
            JOIN financials.annual_pnl f ON f.asx_code = p.asx_code
            WHERE c.status = 'active'
            ORDER BY p.asx_code
        """
        if args.limit:
            sql += f" LIMIT {args.limit}"
        cur.execute(sql)
        codes = [r[0] for r in cur.fetchall()]

    # One watermark for the whole run, obtained once and shared, so no
    # per-company path reimplements feed health and eventually forgets to.
    feed_health = fetch_feed_health(cur)
    dividend_source = DividendSource(feed_health)
    if not feed_health.healthy:
        log.warning("Dividend feed unhealthy: %s. Dividend metrics will be "
                    "written as unavailable rather than computed over a "
                    "window the feed has not observed.", feed_health.reason)

    log.info(f"Computing metrics for {len(codes)} stocks...")
    log.info("─" * 60)

    processed = 0
    skipped   = 0
    errors    = 0

    for i, asx_code in enumerate(codes, 1):
        try:
            price   = fetch_latest_price(cur, asx_code)
            if not price:
                skipped += 1
                continue

            fin     = fetch_financials(cur, asx_code)
            company = fetch_company(cur, asx_code)
            divs    = fetch_dividends(cur, asx_code)

            metrics = compute_metrics(asx_code, price, fin, company, divs,
                                      dividend_source)
            upsert_metrics(cur, asx_code, price["price_date"], metrics)
            processed += 1

            if i % 50 == 0:
                conn.commit()
                log.info(f"  [{i:4d}/{len(codes)}] {processed} computed, {skipped} skipped, {errors} errors")

        except Exception as e:
            errors += 1
            log.warning(f"  {asx_code}: {e}")

    conn.commit()
    cur.close()
    conn.close()

    log.info("─" * 60)
    log.info(f"Done! {processed} computed | {skipped} skipped (no price) | {errors} errors")


if __name__ == "__main__":
    main()
