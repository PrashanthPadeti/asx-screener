"""
ASX Screener — Build Screener Universe (Final Nightly Job)
==========================================================
Reads from all compute tables and source financial tables,
then writes ONE denormalized row per active stock into
market.screener_universe.

This is the table all screener queries hit — no JOINs at query time.

Run order (after all compute jobs complete):
    Seq 2  compute_yearly.py
    Seq 3  compute_halfyearly.py
    Seq 4  compute_quarterly.py
    Seq 5  compute_monthly.py
    Seq 6  compute_weekly.py
    Seq 7  compute_daily.py
    Seq 8  build_screener_universe.py  ← this script

Usage:
    python jobs/build_screener_universe.py
    python jobs/build_screener_universe.py --codes BHP CBA
    python jobs/build_screener_universe.py --full-refresh  # truncate + rebuild
"""

import os
import time
import logging
import argparse
from datetime import date, datetime, timedelta
from typing import Optional

import psycopg2
from psycopg2.extras import execute_values, RealDictCursor
from dotenv import load_dotenv

load_dotenv()

DB_URL     = os.getenv("DATABASE_URL_SYNC",
               "postgresql://asx_user:asx_secure_2024@localhost:5432/asx_screener")
BUILD_VER  = "universe_v1.0"
BATCH_SIZE = 200
SLEEP_SEC  = 0.005

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
#  Data loaders — one function per source table/group
# ─────────────────────────────────────────────────────────────

def load_company(cur, asx_code: str) -> dict:
    cur.execute("""
        SELECT asx_code, company_name,
               gics_sector       AS sector,
               gics_industry     AS industry,
               gics_sub_industry AS sub_industry,
               asx_sector,
               listing_date, status,
               description, website, employee_count,
               is_asx300 AS asx_300, is_asx200 AS asx_200,
               is_asx100 AS asx_100, is_asx50  AS asx_50,
               is_asx20  AS asx_20,
               company_type
        FROM market.companies
        WHERE asx_code = %s
    """, (asx_code,))
    return cur.fetchone() or {}


def load_latest_daily(cur, asx_code: str) -> dict:
    cur.execute("""
        SELECT *
        FROM market.daily_metrics
        WHERE asx_code = %s
        ORDER BY date DESC LIMIT 1
    """, (asx_code,))
    return cur.fetchone() or {}


def load_prev_daily(cur, asx_code: str) -> dict:
    """Second-latest row — used for prev-day signal context."""
    cur.execute("""
        SELECT date, close, volume, sma_20, sma_50, sma_200,
               macd_line, macd_signal, rsi_14
        FROM market.daily_metrics
        WHERE asx_code = %s
        ORDER BY date DESC LIMIT 1 OFFSET 1
    """, (asx_code,))
    return cur.fetchone() or {}


def load_latest_price(cur, asx_code: str) -> dict:
    """Fallback: raw price from daily_prices if daily_metrics not computed yet."""
    cur.execute("""
        SELECT time::date AS last_price_date,
               adjusted_close AS close,
               volume,
               market_cap
        FROM market.daily_prices
        WHERE asx_code = %s AND adjusted_close IS NOT NULL
        ORDER BY time DESC LIMIT 1
    """, (asx_code,))
    return cur.fetchone() or {}


def load_yearly(cur, asx_code: str) -> tuple[dict, dict, dict]:
    """Returns (fy0, fy1, fy2) dicts — current, prior, two-prior fiscal year rows."""
    cur.execute("""
        SELECT *
        FROM market.yearly_metrics
        WHERE asx_code = %s
        ORDER BY fiscal_year DESC LIMIT 3
    """, (asx_code,))
    rows = cur.fetchall()
    fy0 = rows[0] if len(rows) > 0 else {}
    fy1 = rows[1] if len(rows) > 1 else {}
    fy2 = rows[2] if len(rows) > 2 else {}
    return fy0, fy1, fy2


def load_annual_pnl_multi(cur, asx_code: str) -> dict:
    """Raw annual P&L rows keyed by fiscal_year — for N-year actual values."""
    cur.execute("""
        SELECT fiscal_year, revenue, gross_profit, ebit, ebitda,
               net_profit AS net_income, eps, dps, dps_franking_pct,
               depreciation, interest_expense, tax,
               material_cost, employee_cost, other_income, extraordinary_items
        FROM financials.annual_pnl
        WHERE asx_code = %s
        ORDER BY fiscal_year DESC LIMIT 12
    """, (asx_code,))
    return {r["fiscal_year"]: r for r in cur.fetchall()}


def load_annual_bs_multi(cur, asx_code: str) -> dict:
    cur.execute("""
        SELECT fiscal_year,
               total_assets, total_liabilities, total_equity,
               current_assets, current_liabilities, cash_and_equivalents,
               total_debt, long_term_debt, short_term_debt,
               inventory, receivables, payables,
               goodwill, intangibles, fixed_assets,
               gross_block, net_block, accumulated_depreciation, capital_wip,
               lease_liabilities, equity_capital, preference_capital, reserves,
               trade_payables, advance_from_customers, contingent_liabilities,
               face_value, investments, shares_outstanding
        FROM financials.annual_balance_sheet
        WHERE asx_code = %s
        ORDER BY fiscal_year DESC LIMIT 12
    """, (asx_code,))
    return {r["fiscal_year"]: r for r in cur.fetchall()}


def load_annual_cf_multi(cur, asx_code: str) -> dict:
    cur.execute("""
        SELECT fiscal_year, cfo, cfi, cff, fcf, closing_cash,
               capex
        FROM financials.annual_cashflow
        WHERE asx_code = %s
        ORDER BY fiscal_year DESC LIMIT 12
    """, (asx_code,))
    return {r["fiscal_year"]: r for r in cur.fetchall()}


def load_halfyearly(cur, asx_code: str) -> tuple[dict, dict, dict, dict]:
    cur.execute("""
        SELECT *
        FROM market.halfyearly_metrics
        WHERE asx_code = %s
        ORDER BY period_end_date DESC LIMIT 4
    """, (asx_code,))
    rows = cur.fetchall()
    return tuple(rows[i] if i < len(rows) else {} for i in range(4))


def load_quarterly(cur, asx_code: str) -> list[dict]:
    """Latest 5 quarters (4 for embedding + 1 prior year same quarter)."""
    cur.execute("""
        SELECT *
        FROM market.quarterly_metrics
        WHERE asx_code = %s
        ORDER BY fiscal_year DESC, quarter DESC LIMIT 5
    """, (asx_code,))
    return cur.fetchall()


def load_monthly(cur, asx_code: str) -> dict:
    cur.execute("""
        SELECT *
        FROM market.monthly_metrics
        WHERE asx_code = %s
        ORDER BY month_date DESC LIMIT 1
    """, (asx_code,))
    return cur.fetchone() or {}


def load_weekly(cur, asx_code: str) -> dict:
    cur.execute("""
        SELECT *
        FROM market.weekly_metrics
        WHERE asx_code = %s
        ORDER BY week_date DESC LIMIT 1
    """, (asx_code,))
    return cur.fetchone() or {}


def load_short_interest(cur, asx_code: str) -> dict:
    try:
        cur.execute("""
            SELECT short_position, short_pct_of_float,
                   short_pct_change_1w, short_pct_change_4w
            FROM market.short_interest
            WHERE asx_code = %s
            ORDER BY report_date DESC LIMIT 1
        """, (asx_code,))
        return cur.fetchone() or {}
    except Exception:
        return {}


def load_mining(cur, asx_code: str) -> dict:
    try:
        cur.execute("""
            SELECT * FROM financials.mining_data
            WHERE asx_code = %s LIMIT 1
        """, (asx_code,))
        return cur.fetchone() or {}
    except Exception:
        return {}


def load_reit(cur, asx_code: str) -> dict:
    try:
        cur.execute("""
            SELECT * FROM financials.reit_data
            WHERE asx_code = %s LIMIT 1
        """, (asx_code,))
        return cur.fetchone() or {}
    except Exception:
        return {}


# ─────────────────────────────────────────────────────────────
#  Helper utilities
# ─────────────────────────────────────────────────────────────

def g(d: dict, key, default=None):
    """Safe dict get — returns default if key missing or value is None."""
    v = d.get(key) if d else None
    return v if v is not None else default


def fy_val(by_fy: dict, latest_fy: Optional[int], years_back: int, key: str):
    """Get key from fiscal year N years back from latest."""
    if latest_fy is None:
        return None
    target_fy = latest_fy - years_back
    row = by_fy.get(target_fy, {})
    return row.get(key) if row else None


def safe_div(num, denom):
    if num is None or denom is None or denom == 0:
        return None
    return num / denom


def safe_pct(num, denom):
    v = safe_div(num, denom)
    return round(v * 100, 4) if v is not None else None


# ─────────────────────────────────────────────────────────────
#  Build one row
# ─────────────────────────────────────────────────────────────

def build_row(asx_code: str, cur) -> dict:
    co    = load_company(cur, asx_code)
    dm    = load_latest_daily(cur, asx_code)
    dm_p  = load_prev_daily(cur, asx_code)
    dp    = load_latest_price(cur, asx_code)    # fallback price

    fy0, fy1, fy2   = load_yearly(cur, asx_code)
    pnl_by_fy       = load_annual_pnl_multi(cur, asx_code)
    bs_by_fy        = load_annual_bs_multi(cur, asx_code)
    cf_by_fy        = load_annual_cf_multi(cur, asx_code)

    hh0, hh1, hh2, hh3 = load_halfyearly(cur, asx_code)
    qq               = load_quarterly(cur, asx_code)
    mo               = load_monthly(cur, asx_code)
    wk               = load_weekly(cur, asx_code)
    si               = load_short_interest(cur, asx_code)
    mi               = load_mining(cur, asx_code)
    ri               = load_reit(cur, asx_code)

    # Current price — prefer daily_metrics, fall back to daily_prices
    close = g(dm, "close") or g(dp, "close")

    # Latest fiscal year
    latest_fy = g(fy0, "fiscal_year")

    # Quarterly embedding helpers
    def q_get(idx, key):
        if idx < len(qq):
            return qq[idx].get(key)
        return None

    # Find same-quarter prior year
    q_latest = qq[0] if qq else {}
    q_same_py = {}
    if q_latest:
        fy_q  = q_latest.get("fiscal_year", 0)
        q_num = q_latest.get("quarter", 0)
        for qr in qq[1:]:
            if qr.get("fiscal_year") == fy_q - 1 and qr.get("quarter") == q_num:
                q_same_py = qr
                break

    row = {
        # ── Identity ─────────────────────────────────────────
        "asx_code":             asx_code,
        "company_name":         g(co, "company_name"),
        "sector":               g(co, "sector"),
        "industry":             g(co, "industry"),
        "sub_industry":         g(co, "sub_industry"),
        "gics_code":            g(co, "asx_sector"),
        "listing_date":         g(co, "listing_date"),
        "is_active":            g(co, "status") == "active",
        "is_foreign":           g(co, "company_type") == "foreign",
        "description":          g(co, "description"),
        "website":              g(co, "website"),
        "employee_count":       g(co, "employee_count"),
        "asx_300":              g(co, "asx_300", False),
        "asx_200":              g(co, "asx_200", False),
        "asx_100":              g(co, "asx_100", False),
        "asx_50":               g(co, "asx_50",  False),
        "asx_20":               g(co, "asx_20",  False),
        "market_cap_group":     None,

        # ── Price & volume (today) ────────────────────────────
        "last_price":           close,
        "last_price_date":      g(dm, "date") or g(dp, "last_price_date"),
        "open":                 g(dm, "open"),
        "high":                 g(dm, "high"),
        "low":                  g(dm, "low"),
        "volume":               g(dm, "volume"),
        "volume_avg_20d":       g(dm, "volume_avg_20d"),
        "volume_avg_52w":       g(dm, "volume_avg_52w"),
        "relative_volume":      g(dm, "relative_volume"),

        # ── Market cap & valuation ────────────────────────────
        "market_cap":           g(fy0, "market_cap"),
        "enterprise_value":     g(fy0, "enterprise_value"),
        "shares_outstanding":   g(fy0, "shares_outstanding"),
        "free_float":           g(fy0, "free_float"),
        "pe_ratio":             g(fy0, "pe_ratio"),
        "pe_ratio_forward":     g(fy0, "pe_ratio_forward"),
        "pb_ratio":             g(fy0, "pb_ratio"),
        "ps_ratio":             g(fy0, "ps_ratio"),
        "ev_ebitda":            g(fy0, "ev_ebitda"),
        "ev_ebit":              g(fy0, "ev_ebit"),
        "ev_revenue":           g(fy0, "ev_revenue"),
        "ev_fcf":               g(fy0, "ev_fcf"),
        "peg_ratio":            g(fy0, "peg_ratio"),
        "price_to_fcf":         g(fy0, "price_to_fcf"),
        "price_to_book":        g(fy0, "pb_ratio"),
        "price_to_tangible_book": g(fy0, "price_to_tangible_book"),
        "dividend_yield":       g(fy0, "dividend_yield"),
        "franking_pct":         g(fy0, "franking_pct"),
        "grossed_up_yield":     g(fy0, "grossed_up_yield"),
        "payout_ratio":         g(fy0, "payout_ratio"),
        "earnings_yield":       g(fy0, "earnings_yield"),
        "fcf_yield":            g(fy0, "fcf_yield"),

        # ── Income Statement (FY0) ────────────────────────────
        "revenue":              g(fy0, "revenue"),
        "gross_profit":         g(fy0, "gross_profit"),
        "ebitda":               g(fy0, "ebitda"),
        "ebit":                 g(fy0, "ebit"),
        "net_income":           g(fy0, "net_income"),
        "eps":                  g(fy0, "eps"),
        "eps_diluted":          g(fy0, "eps_diluted"),
        "dps":                  g(fy0, "dps"),
        "dps_franking_pct":     g(fy0, "dps_franking_pct"),
        "depreciation":         g(fy0, "depreciation"),
        "interest_expense":     g(fy0, "interest_expense"),
        "tax_expense":          g(fy0, "tax_expense"),
        "other_income":         g(fy0, "other_income"),
        "extraordinary_items":  g(fy0, "extraordinary_items"),
        "material_cost":        g(fy0, "material_cost"),
        "employee_cost":        g(fy0, "employee_cost"),

        # ── Income Statement (FY-1 actuals) ───────────────────
        "revenue_fy1":          g(fy1, "revenue"),
        "gross_profit_fy1":     g(fy1, "gross_profit"),
        "ebitda_fy1":           g(fy1, "ebitda"),
        "ebit_fy1":             g(fy1, "ebit"),
        "net_income_fy1":       g(fy1, "net_income"),
        "eps_fy1":              g(fy1, "eps"),
        "dps_fy1":              g(fy1, "dps"),

        # ── Income Statement (FY-2 actuals) ───────────────────
        "revenue_fy2":          g(fy2, "revenue"),
        "ebit_fy2":             g(fy2, "ebit"),
        "net_income_fy2":       g(fy2, "net_income"),
        "eps_fy2":              g(fy2, "eps"),

        # ── N-Year Actual Values (absolute historical) ────────
        "revenue_3y":           fy_val(pnl_by_fy, latest_fy, 3, "revenue"),
        "revenue_5y":           fy_val(pnl_by_fy, latest_fy, 5, "revenue"),
        "revenue_7y":           fy_val(pnl_by_fy, latest_fy, 7, "revenue"),
        "revenue_10y":          fy_val(pnl_by_fy, latest_fy, 10, "revenue"),
        "net_income_3y":        fy_val(pnl_by_fy, latest_fy, 3, "net_profit"),
        "net_income_5y":        fy_val(pnl_by_fy, latest_fy, 5, "net_profit"),
        "net_income_7y":        fy_val(pnl_by_fy, latest_fy, 7, "net_profit"),
        "net_income_10y":       fy_val(pnl_by_fy, latest_fy, 10, "net_profit"),
        "eps_3y":               fy_val(pnl_by_fy, latest_fy, 3, "eps"),
        "eps_5y":               fy_val(pnl_by_fy, latest_fy, 5, "eps"),
        "eps_7y":               fy_val(pnl_by_fy, latest_fy, 7, "eps"),
        "eps_10y":              fy_val(pnl_by_fy, latest_fy, 10, "eps"),

        # ── Margins (FY0) ─────────────────────────────────────
        "gross_margin":         g(fy0, "gross_margin"),
        "ebitda_margin":        g(fy0, "ebitda_margin"),
        "ebit_margin":          g(fy0, "ebit_margin"),
        "net_margin":           g(fy0, "net_margin"),
        "tax_rate":             g(fy0, "tax_rate"),

        # ── Margins (FY-1) ────────────────────────────────────
        "gross_margin_fy1":     g(fy1, "gross_margin"),
        "ebit_margin_fy1":      g(fy1, "ebit_margin"),
        "net_margin_fy1":       g(fy1, "net_margin"),

        # ── Margins (FY-2) ────────────────────────────────────
        "ebit_margin_fy2":      g(fy2, "ebit_margin"),
        "net_margin_fy2":       g(fy2, "net_margin"),

        # ── Multi-year Average Margins ────────────────────────
        "gross_margin_avg_3y":  g(fy0, "gross_margin_avg_3y"),
        "gross_margin_avg_5y":  g(fy0, "gross_margin_avg_5y"),
        "opm_avg_3y":           g(fy0, "opm_avg_3y"),
        "opm_avg_5y":           g(fy0, "opm_avg_5y"),
        "opm_avg_7y":           g(fy0, "opm_avg_7y"),
        "opm_avg_10y":          g(fy0, "opm_avg_10y"),
        "npm_avg_3y":           g(fy0, "npm_avg_3y"),
        "npm_avg_5y":           g(fy0, "npm_avg_5y"),

        # ── Balance Sheet ─────────────────────────────────────
        "total_assets":         g(fy0, "total_assets"),
        "total_liabilities":    g(fy0, "total_liabilities"),
        "total_equity":         g(fy0, "total_equity"),
        "current_assets":       g(fy0, "current_assets"),
        "current_liabilities":  g(fy0, "current_liabilities"),
        "cash":                 g(fy0, "cash"),
        "total_debt":           g(fy0, "total_debt"),
        "long_term_debt":       g(fy0, "long_term_debt"),
        "short_term_debt":      g(fy0, "short_term_debt"),
        "net_debt":             g(fy0, "net_debt"),
        "working_capital":      g(fy0, "working_capital"),
        "inventory":            g(fy0, "inventory"),
        "receivables":          g(fy0, "receivables"),
        "payables":             g(fy0, "payables"),
        "goodwill":             g(fy0, "goodwill"),
        "intangibles":          g(fy0, "intangibles"),
        "fixed_assets":         g(fy0, "fixed_assets"),
        "gross_block":          g(fy0, "gross_block"),
        "net_block":            g(fy0, "net_block"),
        "accumulated_depreciation": g(fy0, "accumulated_depreciation"),
        "capital_wip":          g(fy0, "capital_wip"),
        "lease_liabilities":    g(fy0, "lease_liabilities"),
        "equity_capital":       g(fy0, "equity_capital"),
        "preference_capital":   g(fy0, "preference_capital"),
        "reserves":             g(fy0, "reserves"),
        "trade_payables":       g(fy0, "trade_payables"),
        "advance_from_customers": g(fy0, "advance_from_customers"),
        "contingent_liabilities": g(fy0, "contingent_liabilities"),
        "face_value":           g(fy0, "face_value"),
        "investments":          g(fy0, "investments"),
        "book_value_per_share": g(fy0, "book_value_per_share"),
        "tangible_book_value":  g(fy0, "tangible_book_value"),
        "tangible_bvps":        g(fy0, "tangible_bvps"),

        # ── Historical Balance Sheet (N-year actuals) ─────────
        "total_debt_3y":        fy_val(bs_by_fy, latest_fy, 3, "total_debt"),
        "total_debt_5y":        fy_val(bs_by_fy, latest_fy, 5, "total_debt"),
        "total_debt_7y":        fy_val(bs_by_fy, latest_fy, 7, "total_debt"),
        "total_debt_10y":       fy_val(bs_by_fy, latest_fy, 10, "total_debt"),
        "working_capital_3y":   fy_val(bs_by_fy, latest_fy, 3, "working_capital") if fy_val(bs_by_fy, latest_fy, 3, "current_assets") else None,
        "working_capital_5y":   None,  # computed below
        "working_capital_7y":   None,
        "net_block_3y":         fy_val(bs_by_fy, latest_fy, 3, "net_block"),
        "net_block_5y":         fy_val(bs_by_fy, latest_fy, 5, "net_block"),
        "net_block_7y":         fy_val(bs_by_fy, latest_fy, 7, "net_block"),

        # ── Cash Flow ─────────────────────────────────────────
        "cfo":                  g(fy0, "cfo"),
        "cfi":                  g(fy0, "cfi"),
        "cff":                  g(fy0, "cff"),
        "fcf":                  g(fy0, "fcf"),
        "capex":                g(fy0, "capex"),
        "closing_cash":         g(fy0, "closing_cash"),

        # ── Historical Cash Flow (N-year actuals) ─────────────
        "fcf_3y":               fy_val(cf_by_fy, latest_fy, 3, "fcf"),
        "fcf_5y":               fy_val(cf_by_fy, latest_fy, 5, "fcf"),
        "fcf_7y":               fy_val(cf_by_fy, latest_fy, 7, "fcf"),
        "fcf_10y":              fy_val(cf_by_fy, latest_fy, 10, "fcf"),
        "ocf_3y":               fy_val(cf_by_fy, latest_fy, 3, "cfo"),
        "ocf_5y":               fy_val(cf_by_fy, latest_fy, 5, "cfo"),
        "ocf_7y":               fy_val(cf_by_fy, latest_fy, 7, "cfo"),
        "ocf_10y":              fy_val(cf_by_fy, latest_fy, 10, "cfo"),
        "cash_3y":              fy_val(bs_by_fy, latest_fy, 3, "cash_and_equivalents"),
        "cash_5y":              fy_val(bs_by_fy, latest_fy, 5, "cash_and_equivalents"),
        "cash_7y":              fy_val(bs_by_fy, latest_fy, 7, "cash_and_equivalents"),

        # ── Efficiency ratios ─────────────────────────────────
        "asset_turnover":       g(fy0, "asset_turnover"),
        "inventory_turnover":   g(fy0, "inventory_turnover"),
        "receivables_turnover": g(fy0, "receivables_turnover"),
        "days_sales_outstanding": g(fy0, "days_sales_outstanding"),
        "days_inventory_outstanding": g(fy0, "days_inventory_outstanding"),
        "cash_conversion_cycle": g(fy0, "cash_conversion_cycle"),
        "capex_to_sales":       g(fy0, "capex_to_sales"),
        "capex_to_cfo":         g(fy0, "capex_to_cfo"),
        "fcf_to_net_income":    g(fy0, "fcf_to_net_income"),

        # ── Leverage ratios ───────────────────────────────────
        "debt_to_equity":       g(fy0, "debt_to_equity"),
        "debt_to_assets":       g(fy0, "debt_to_assets"),
        "debt_to_ebitda":       g(fy0, "debt_to_ebitda"),
        "net_debt_to_ebitda":   g(fy0, "net_debt_to_ebitda"),
        "interest_coverage":    g(fy0, "interest_coverage"),
        "current_ratio":        g(fy0, "current_ratio"),
        "quick_ratio":          g(fy0, "quick_ratio"),
        "cash_ratio":           g(fy0, "cash_ratio"),

        # ── Profitability / Returns ───────────────────────────
        "roe":                  g(fy0, "roe"),
        "roa":                  g(fy0, "roa"),
        "roic":                 g(fy0, "roic"),
        "roce":                 g(fy0, "roce"),
        "roe_avg_3y":           g(fy0, "roe_avg_3y"),
        "roe_avg_5y":           g(fy0, "roe_avg_5y"),
        "roe_avg_7y":           g(fy0, "roe_avg_7y"),
        "roe_avg_10y":          g(fy0, "roe_avg_10y"),
        "roa_avg_3y":           g(fy0, "roa_avg_3y"),
        "roa_avg_5y":           g(fy0, "roa_avg_5y"),
        "roic_avg_3y":          g(fy0, "roic_avg_3y"),
        "roic_avg_5y":          g(fy0, "roic_avg_5y"),
        "roce_avg_3y":          g(fy0, "roce_avg_3y"),
        "roce_avg_5y":          g(fy0, "roce_avg_5y"),
        "roce_avg_7y":          g(fy0, "roce_avg_7y"),
        "roce_avg_10y":         g(fy0, "roce_avg_10y"),

        # ── Growth rates (YoY, 1 year) ────────────────────────
        "revenue_growth_1y":    g(fy0, "revenue_growth_1y"),
        "net_income_growth_1y": g(fy0, "net_income_growth_1y"),
        "ebit_growth_1y":       g(fy0, "ebit_growth_1y"),
        "eps_growth_1y":        g(fy0, "eps_growth_1y"),
        "ebitda_growth_1y":     g(fy0, "ebitda_growth_1y"),
        "fcf_growth_1y":        g(fy0, "fcf_growth_1y"),
        "dps_growth_1y":        g(fy0, "dps_growth_1y"),

        # ── CAGR (multi-year) ─────────────────────────────────
        "revenue_cagr_3y":      g(fy0, "revenue_cagr_3y"),
        "revenue_cagr_5y":      g(fy0, "revenue_cagr_5y"),
        "revenue_cagr_7y":      g(fy0, "revenue_cagr_7y"),
        "revenue_cagr_10y":     g(fy0, "revenue_cagr_10y"),
        "net_income_cagr_3y":   g(fy0, "net_income_cagr_3y"),
        "net_income_cagr_5y":   g(fy0, "net_income_cagr_5y"),
        "net_income_cagr_7y":   g(fy0, "net_income_cagr_7y"),
        "net_income_cagr_10y":  g(fy0, "net_income_cagr_10y"),
        "eps_cagr_3y":          g(fy0, "eps_cagr_3y"),
        "eps_cagr_5y":          g(fy0, "eps_cagr_5y"),
        "eps_cagr_7y":          g(fy0, "eps_cagr_7y"),
        "eps_cagr_10y":         g(fy0, "eps_cagr_10y"),
        "ebitda_cagr_3y":       g(fy0, "ebitda_cagr_3y"),
        "ebitda_cagr_5y":       g(fy0, "ebitda_cagr_5y"),
        "fcf_cagr_3y":          g(fy0, "fcf_cagr_3y"),
        "fcf_cagr_5y":          g(fy0, "fcf_cagr_5y"),
        "gross_profit_cagr_3y": g(fy0, "gross_profit_cagr_3y"),
        "gross_profit_cagr_5y": g(fy0, "gross_profit_cagr_5y"),
        "bvps_cagr_3y":         g(fy0, "bvps_cagr_3y"),
        "bvps_cagr_5y":         g(fy0, "bvps_cagr_5y"),
        "dividend_cagr_3y":     g(fy0, "dividend_cagr_3y"),
        "dividend_cagr_5y":     g(fy0, "dividend_cagr_5y"),
        "price_cagr_1y":        g(fy0, "price_cagr_1y"),
        "price_cagr_3y":        g(fy0, "price_cagr_3y"),
        "price_cagr_5y":        g(fy0, "price_cagr_5y"),

        # ── EPS growth multi-year averages ────────────────────
        "eps_growth_avg_3y":    g(fy0, "eps_growth_avg_3y"),
        "eps_growth_avg_5y":    g(fy0, "eps_growth_avg_5y"),
        "eps_growth_avg_7y":    g(fy0, "eps_growth_avg_7y"),
        "eps_growth_avg_10y":   g(fy0, "eps_growth_avg_10y"),

        # ── Quality scores ────────────────────────────────────
        "piotroski_score":      g(fy0, "piotroski_score"),
        "altman_z_score":       g(fy0, "altman_z_score"),
        "beneish_m_score":      g(fy0, "beneish_m_score"),
        "accruals_ratio":       g(fy0, "accruals_ratio"),

        # ── Risk metrics ──────────────────────────────────────
        "beta":                 g(fy0, "beta"),
        "alpha_1y":             g(fy0, "alpha_1y"),
        "volatility_1y":        g(fy0, "volatility_1y"),
        "volatility_3y":        g(fy0, "volatility_3y"),
        "sharpe_1y":            g(fy0, "sharpe_1y"),
        "sharpe_3y":            g(fy0, "sharpe_3y"),
        "sortino_1y":           g(fy0, "sortino_1y"),
        "max_drawdown_1y":      g(fy0, "max_drawdown_1y"),
        "max_drawdown_3y":      g(fy0, "max_drawdown_3y"),
        "max_drawdown_5y":      g(fy0, "max_drawdown_5y"),
        "calmar_ratio":         g(fy0, "calmar_ratio"),

        # ── Price performance ─────────────────────────────────
        "return_1d":            g(dm, "return_1d"),
        "return_5d":            g(dm, "return_5d"),
        "return_1m":            g(mo, "monthly_return"),
        "return_3m":            g(mo, "return_3m"),
        "return_6m":            g(mo, "return_6m"),
        "return_1y":            g(mo, "return_12m"),
        "return_ytd":           g(mo, "return_ytd"),
        "return_3y":            g(fy0, "price_cagr_3y"),
        "return_5y":            g(fy0, "price_cagr_5y"),

        # ── 52w / ATH levels ─────────────────────────────────
        "high_52w":             g(dm, "high_52w"),
        "low_52w":              g(dm, "low_52w"),
        "pct_from_52w_high":    g(dm, "pct_from_52w_high"),
        "pct_from_52w_low":     g(dm, "pct_from_52w_low"),
        "all_time_high":        g(dm, "ath_price"),
        "all_time_low":         g(dm, "atl_price"),
        "pct_from_ath":         g(dm, "pct_from_ath"),
        "pct_from_atl":         g(dm, "pct_from_atl"),

        # ── Daily Technicals ──────────────────────────────────
        "sma_5":                g(dm, "sma_5"),
        "sma_10":               g(dm, "sma_10"),
        "sma_20":               g(dm, "sma_20"),
        "sma_50":               g(dm, "sma_50"),
        "sma_100":              g(dm, "sma_100"),
        "sma_200":              g(dm, "sma_200"),
        "ema_9":                g(dm, "ema_9"),
        "ema_20":               g(dm, "ema_20"),
        "ema_50":               g(dm, "ema_50"),
        "ema_200":              g(dm, "ema_200"),
        "sma_50_prev":          g(dm, "sma_50_prev"),
        "sma_200_prev":         g(dm, "sma_200_prev"),
        "dma_50_ratio":         g(dm, "dma50_ratio"),
        "dma_200_ratio":        g(dm, "dma200_ratio"),
        "price_to_sma20":       g(dm, "dma20_ratio"),
        "macd_line":            g(dm, "macd_line"),
        "macd_signal":          g(dm, "macd_signal"),
        "macd_hist":            g(dm, "macd_hist"),
        "macd_line_prev":       g(dm, "macd_line_prev"),
        "macd_signal_prev":     g(dm, "macd_signal_prev"),
        "rsi_7":                g(dm, "rsi_7"),
        "rsi_14":               g(dm, "rsi_14"),
        "rsi_21":               g(dm, "rsi_21"),
        "stoch_k":              g(dm, "stoch_k"),
        "stoch_d":              g(dm, "stoch_d"),
        "bb_upper":             g(dm, "bb_upper"),
        "bb_mid":               g(dm, "bb_mid"),
        "bb_lower":             g(dm, "bb_lower"),
        "bb_pct":               g(dm, "bb_pct"),
        "bb_width":             g(dm, "bb_width"),
        "adx":                  g(dm, "adx_14"),
        "di_plus":              g(dm, "plus_di"),
        "di_minus":             g(dm, "minus_di"),
        "cci":                  g(dm, "cci_20"),
        "williams_r":           g(dm, "williams_r"),
        "roc_10":               g(dm, "roc_10"),
        "roc_20":               g(dm, "roc_20"),
        "atr_14":               g(dm, "atr_14"),
        "obv":                  g(dm, "obv"),
        "vwap_20d":             g(dm, "vwap"),
        "cmf_20":               g(dm, "cmf_20"),
        "mfi_14":               g(dm, "mfi_14"),
        "aroon_up":             g(dm, "aroon_up"),
        "aroon_down":           g(dm, "aroon_down"),

        # ── Daily signals ─────────────────────────────────────
        "golden_cross":         g(dm, "golden_cross", False),
        "death_cross":          g(dm, "death_cross",  False),
        "above_sma20":          g(dm, "above_sma20"),
        "above_sma50":          g(dm, "above_sma50"),
        "above_sma200":         g(dm, "above_sma200"),
        "rsi_overbought":       g(dm, "rsi_overbought", False),
        "rsi_oversold":         g(dm, "rsi_oversold",   False),
        "macd_bullish_cross":   g(dm, "macd_bullish_cross", False),
        "macd_bearish_cross":   g(dm, "macd_bearish_cross", False),

        # ── Weekly technicals ─────────────────────────────────
        "rsi_14_weekly":        g(wk, "rsi_14"),
        "macd_line_weekly":     g(wk, "macd_line"),
        "macd_signal_weekly":   g(wk, "macd_signal"),
        "adx_weekly":           g(wk, "adx"),
        "stoch_k_weekly":       g(wk, "stoch_k"),
        "bb_pct_weekly":        g(wk, "bb_pct"),
        "aroon_up_weekly":      g(wk, "aroon_up"),
        "aroon_down_weekly":    g(wk, "aroon_down"),
        "weekly_return":        g(wk, "weekly_return"),
        "return_4w":            g(wk, "return_4w"),
        "return_13w":           g(wk, "return_13w"),
        "return_52w":           g(wk, "return_52w"),

        # ── Monthly technicals ────────────────────────────────
        "rsi_14_monthly":       g(mo, "rsi_14"),
        "bb_pct_monthly":       g(mo, "bb_pct"),
        "volatility_1m":        g(mo, "volatility_1m"),
        "volatility_3m":        g(mo, "volatility_3m"),
        "volatility_12m":       g(mo, "volatility_12m"),

        # ── Half-yearly (latest 2H) ───────────────────────────
        "revenue_h1":           g(hh0, "revenue"),
        "ebit_h1":              g(hh0, "ebit"),
        "net_income_h1":        g(hh0, "net_income"),
        "eps_h1":               g(hh0, "eps"),
        "dps_h1":               g(hh0, "dps"),
        "gross_margin_h1":      g(hh0, "gross_margin"),
        "ebit_margin_h1":       g(hh0, "ebit_margin"),
        "net_margin_h1":        g(hh0, "net_margin"),
        "revenue_growth_hoh":   g(hh0, "revenue_growth_hoh"),
        "revenue_growth_yoy_h": g(hh0, "revenue_growth_yoy"),
        "net_income_growth_hoh": g(hh0, "net_income_growth_hoh"),
        "net_income_growth_yoy_h": g(hh0, "net_income_growth_yoy"),
        "eps_growth_hoh":       g(hh0, "eps_growth_hoh"),
        "eps_growth_yoy_h":     g(hh0, "eps_growth_yoy"),

        # ── Quarterly embedding (latest Q) ────────────────────
        "revenue_latest_q":     q_get(0, "revenue"),
        "ebit_latest_q":        q_get(0, "ebit"),
        "net_income_latest_q":  q_get(0, "net_income"),
        "eps_latest_q":         q_get(0, "eps"),
        "gross_margin_latest_q": q_get(0, "gross_margin"),
        "ebit_margin_latest_q": q_get(0, "ebit_margin"),
        "net_margin_latest_q":  q_get(0, "net_margin"),
        "revenue_growth_qoq":   q_get(0, "revenue_growth_qoq"),
        "revenue_growth_yoy_q": q_get(0, "revenue_growth_yoy"),
        "net_income_growth_qoq": q_get(0, "net_income_growth_qoq"),
        "net_income_growth_yoy_q": q_get(0, "net_income_growth_yoy"),
        "eps_growth_yoy_q":     q_get(0, "eps_growth_yoy"),

        # ── Quarterly (previous Q) ────────────────────────────
        "revenue_prev_q":       q_get(1, "revenue"),
        "net_income_prev_q":    q_get(1, "net_income"),
        "ebit_margin_prev_q":   q_get(1, "ebit_margin"),

        # ── Quarterly (Q-2) ───────────────────────────────────
        "revenue_q2":           q_get(2, "revenue"),
        "net_income_q2":        q_get(2, "net_income"),

        # ── Quarterly (same Q prior year) ─────────────────────
        "revenue_same_q_prior_yr":    q_same_py.get("revenue"),
        "net_income_same_q_prior_yr": q_same_py.get("net_income"),
        "eps_same_q_prior_yr":        q_same_py.get("eps"),

        # ── Short interest ────────────────────────────────────
        "short_position":       g(si, "short_position"),
        "short_pct_of_float":   g(si, "short_pct_of_float"),
        "short_pct_change_1w":  g(si, "short_pct_change_1w"),
        "short_pct_change_4w":  g(si, "short_pct_change_4w"),

        # ── Mining / Resources ────────────────────────────────
        "ore_reserve_mt":       g(mi, "ore_reserve_mt"),
        "mineral_resource_mt":  g(mi, "mineral_resource_mt"),
        "aisc_per_oz":          g(mi, "aisc_per_oz"),
        "production_oz":        g(mi, "production_oz"),
        "reserve_life_years":   g(mi, "reserve_life_years"),
        "commodity_primary":    g(mi, "commodity_primary"),
        "development_stage":    g(mi, "development_stage"),

        # ── REIT ──────────────────────────────────────────────
        "nta_per_unit":         g(ri, "nta_per_unit"),
        "distribution_yield":   g(ri, "distribution_yield"),
        "distribution_per_unit": g(ri, "distribution_per_unit"),
        "funds_from_operations": g(ri, "funds_from_operations"),
        "gearing_ratio":        g(ri, "gearing_ratio"),
        "wale_years":           g(ri, "wale_years"),
        "occupancy_rate":       g(ri, "occupancy_rate"),
        "property_sector":      g(ri, "property_sector"),

        # ── Metadata ─────────────────────────────────────────
        "last_updated":         datetime.utcnow(),
        "build_version":        BUILD_VER,
    }

    # Fix working_capital historical (current_assets - current_liabilities)
    for n_back in [5, 7]:
        ca = fy_val(bs_by_fy, latest_fy, n_back, "current_assets")
        cl = fy_val(bs_by_fy, latest_fy, n_back, "current_liabilities")
        if ca is not None and cl is not None:
            row[f"working_capital_{n_back}y"] = ca - cl

    return row


# ─────────────────────────────────────────────────────────────
#  Upsert
# ─────────────────────────────────────────────────────────────

def upsert_universe(cur, rows: list[dict]) -> int:
    if not rows:
        return 0
    cols = list(rows[0].keys())
    vals = [[r.get(c) for c in cols] for r in rows]
    upd  = ", ".join([f"{c} = EXCLUDED.{c}" for c in cols if c != "asx_code"])
    sql  = f"""
        INSERT INTO market.screener_universe ({', '.join(cols)})
        VALUES %s
        ON CONFLICT (asx_code) DO UPDATE SET {upd}
    """
    execute_values(cur, sql, vals, page_size=BATCH_SIZE)
    return len(rows)


# ─────────────────────────────────────────────────────────────
#  Main
# ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--codes",         nargs="+")
    parser.add_argument("--full-refresh",  action="store_true",
                        help="Truncate screener_universe before rebuilding")
    args = parser.parse_args()

    conn = psycopg2.connect(DB_URL)
    conn.autocommit = False
    cur  = conn.cursor(cursor_factory=RealDictCursor)

    if args.full_refresh and not args.codes:
        log.info("Full refresh — truncating market.screener_universe")
        cur.execute("TRUNCATE market.screener_universe")
        conn.commit()

    if args.codes:
        codes = [c.upper() for c in args.codes]
    else:
        cur.execute("""
            SELECT asx_code FROM market.companies
            WHERE status = 'active' ORDER BY asx_code
        """)
        codes = [r["asx_code"] for r in cur.fetchall()]

    total = len(codes)
    log.info(f"build_screener_universe.py — {total} stocks")

    done = failed = 0
    batch: list[dict] = []

    for i, asx_code in enumerate(codes, 1):
        try:
            row = build_row(asx_code, cur)
            batch.append(row)

            if len(batch) >= BATCH_SIZE:
                upsert_universe(cur, batch)
                done += len(batch)
                conn.commit()
                batch = []
                log.info(f"  [{i:4d}/{total}] {done} done")

        except Exception as e:
            conn.rollback()
            batch = []
            failed += 1
            log.warning(f"  {asx_code}: {e}")
            continue

        time.sleep(SLEEP_SEC)

    if batch:
        upsert_universe(cur, batch)
        done += len(batch)
        conn.commit()

    cur.close()
    conn.close()
    log.info(f"DONE — {done} stocks upserted into screener_universe. Failed: {failed}")


if __name__ == "__main__":
    main()
