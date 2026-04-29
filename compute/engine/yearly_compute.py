"""
ASX Screener — Yearly Compute Engine
======================================
Computes per-fiscal-year metrics for all ASX stocks.

Sources (no API calls — pure computation):
  financials.annual_pnl           → income / margins / EPS / DPS
  financials.annual_balance_sheet → assets / liabilities / equity
  financials.annual_cashflow      → CFO / capex / FCF
  market.daily_prices             → price at period_end for PE/PB,
                                    Sharpe ratio (1y), max drawdown

Output: market.yearly_metrics (one row per asx_code per fiscal_year)

Metrics computed:
  - Profitability         ROE, ROA, ROCE, ROIC, margins (gross/EBITDA/EBIT/net/OCF/FCF)
  - Efficiency            asset turnover, receivables/inventory/payable days
  - Leverage & liquidity  D/E, current ratio, net debt/EBITDA, interest coverage
  - Per share             EPS, DPS, BVPS, FCF/share, OCF/share
  - Valuation ratios      PE, PB, PS, EV/EBITDA (using price at period_end_date)
  - Dividend              yield, payout ratio, CAGR 3y, consecutive uninterrupted years
  - YoY growth            revenue, gross profit, EBITDA, net income, EPS, FCF, BVPS
  - Multi-year CAGRs      revenue/EPS/net income/EBITDA/FCF — 3y, 5y, 7y, 10y
  - Rolling averages      ROE, ROA, ROCE, margins — 3y, 5y
  - Quality scores        Piotroski F-score (0–9), Altman Z-score
  - Risk & performance    Sharpe 1y, max drawdown 1y, annualised volatility 1y
                          (beta/alpha skipped — need market index)

Usage:
    python compute/engine/yearly_compute.py               # all stocks
    python compute/engine/yearly_compute.py --codes BHP CBA
    python compute/engine/yearly_compute.py --limit 20
    python compute/engine/yearly_compute.py --min-year 2020  # only recompute recent FYs
"""

import os
import logging
import argparse
from datetime import datetime, timezone, timedelta
from typing import Optional

import psycopg2
import psycopg2.extensions
from psycopg2.extras import execute_values
import pandas as pd
import numpy as np
from dotenv import load_dotenv

# Cast PostgreSQL NUMERIC → Python float automatically
_DEC2FLOAT = psycopg2.extensions.new_type(
    psycopg2.extensions.DECIMAL.values,
    "DEC2FLOAT",
    lambda value, curs: float(value) if value is not None else None,
)
psycopg2.extensions.register_type(_DEC2FLOAT)

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

COMPUTE_VERSION  = "1.0.0"
BATCH_COMMIT     = 50
RISK_FREE_RATE   = 0.04   # 4% — approximate Australian cash rate for Sharpe calc


# ── Helpers ───────────────────────────────────────────────────────────────────

def _nan_to_none(val):
    if val is None:
        return None
    if isinstance(val, (bool, np.bool_)):
        return bool(val)
    if isinstance(val, float) and np.isnan(val):
        return None
    if isinstance(val, (np.integer,)):
        return int(val)
    if isinstance(val, (np.floating,)):
        return None if np.isnan(val) else float(val)
    return val


def _safe_div(num, den, round_dp=4):
    """Return num/den rounded, or None if denominator is zero/None."""
    try:
        if den is None or den == 0 or np.isnan(float(den)):
            return None
        result = float(num) / float(den)
        return round(result, round_dp) if not np.isnan(result) and not np.isinf(result) else None
    except Exception:
        return None


def _cagr(end_val, start_val, years: int):
    """Compound Annual Growth Rate. Returns None on invalid inputs."""
    try:
        if years <= 0 or start_val is None or end_val is None:
            return None
        s, e = float(start_val), float(end_val)
        if s == 0 or np.isnan(s) or np.isnan(e):
            return None
        if s < 0 and e < 0:
            # Both negative — flip sign convention: growth = improvement
            result = (abs(e) / abs(s)) ** (1 / years) - 1
        elif s < 0 or e < 0:
            return None   # sign change — CAGR undefined
        else:
            result = (e / s) ** (1 / years) - 1
        return round(result, 6) if not np.isinf(result) else None
    except Exception:
        return None


def _rolling_avg(series: list, n: int):
    """Mean of last n non-None values."""
    vals = [v for v in series[-n:] if v is not None]
    return round(sum(vals) / len(vals), 4) if vals else None


# ── Data Fetchers ─────────────────────────────────────────────────────────────

def fetch_codes(cur, codes=None, limit=None):
    if codes:
        return [c.upper() for c in codes]
    sql = """
        SELECT DISTINCT p.asx_code
        FROM financials.annual_pnl p
        JOIN market.companies c ON c.asx_code = p.asx_code
        WHERE c.status = 'active'
        ORDER BY p.asx_code
    """
    if limit:
        sql += f" LIMIT {limit}"
    cur.execute(sql)
    return [r[0] for r in cur.fetchall()]


def fetch_annual_financials(cur, asx_code: str) -> pd.DataFrame:
    """
    Returns one row per fiscal_year joining pnl + balance_sheet + cashflow.
    Sorted ascending by fiscal_year.
    """
    cur.execute("""
        SELECT
            p.fiscal_year,
            p.period_end_date,
            -- P&L
            p.revenue,      p.gross_profit,  p.ebitda,
            p.ebit,         p.interest_expense,
            p.net_profit,   p.eps,           p.eps_diluted,
            p.dps,          p.dps_franking_pct,
            p.gpm,          p.opm,           p.npm,   p.ebitda_margin,
            -- Balance Sheet
            b.total_assets,       b.total_equity,
            b.total_current_assets, b.total_current_liab,
            b.total_debt,         b.net_debt,
            b.cash_equivalents,   b.long_term_debt,
            b.retained_earnings,  b.working_capital,
            b.book_value_per_share, b.shares_outstanding,
            b.trade_receivables,  b.inventory,  b.trade_payables,
            -- Cash Flow
            cf.cfo,   cf.capex,  cf.fcf,
            cf.equity_raised
        FROM financials.annual_pnl p
        LEFT JOIN financials.annual_balance_sheet b
               ON b.asx_code = p.asx_code AND b.fiscal_year = p.fiscal_year
        LEFT JOIN financials.annual_cashflow cf
               ON cf.asx_code = p.asx_code AND cf.fiscal_year = p.fiscal_year
        WHERE p.asx_code = %s
        ORDER BY p.fiscal_year ASC
    """, [asx_code])

    rows = cur.fetchall()
    if not rows:
        return pd.DataFrame()

    cols = [
        "fiscal_year", "period_end_date",
        "revenue", "gross_profit", "ebitda", "ebit", "interest_expense",
        "net_profit", "eps", "eps_diluted",
        "dps", "dps_franking_pct",
        "gpm", "opm", "npm", "ebitda_margin",
        "total_assets", "total_equity",
        "total_current_assets", "total_current_liab",
        "total_debt", "net_debt", "cash_equivalents", "long_term_debt",
        "retained_earnings", "working_capital",
        "book_value_per_share", "shares_outstanding",
        "trade_receivables", "inventory", "trade_payables",
        "cfo", "capex", "fcf", "equity_raised",
    ]
    df = pd.DataFrame(rows, columns=cols)
    df["period_end_date"] = pd.to_datetime(df["period_end_date"])
    return df


def fetch_price_at_date(cur, asx_code: str, target_date) -> Optional[float]:
    """Closest closing price on or before target_date."""
    cur.execute("""
        SELECT close
        FROM market.daily_prices
        WHERE asx_code = %s
          AND DATE(time AT TIME ZONE 'Australia/Sydney') <= %s
        ORDER BY time DESC
        LIMIT 1
    """, [asx_code, target_date])
    row = cur.fetchone()
    return float(row[0]) if row and row[0] is not None else None


def fetch_daily_prices_for_year(cur, asx_code: str,
                                 period_end: pd.Timestamp) -> pd.Series:
    """Daily closes for the 12 months ending at period_end."""
    start = (period_end - pd.DateOffset(years=1)).date()
    cur.execute("""
        SELECT DATE(time AT TIME ZONE 'Australia/Sydney') AS day, close
        FROM market.daily_prices
        WHERE asx_code = %s
          AND DATE(time AT TIME ZONE 'Australia/Sydney') BETWEEN %s AND %s
        ORDER BY time ASC
    """, [asx_code, start, period_end.date()])
    rows = cur.fetchall()
    if not rows:
        return pd.Series(dtype=float)
    return pd.Series(
        [float(r[1]) for r in rows if r[1] is not None],
        index=pd.to_datetime([r[0] for r in rows if r[1] is not None]),
    )


# ── Ratio Calculations ────────────────────────────────────────────────────────

def piotroski_f_score(cur_yr: dict, prev_yr: Optional[dict]) -> Optional[int]:
    """
    Piotroski F-Score: 9 binary signals (0 or 1 each).
    Returns 0–9 or None if insufficient data.
    """
    if not cur_yr or cur_yr.get("total_assets") in (None, 0):
        return None

    score = 0
    ta   = cur_yr["total_assets"]
    prev = prev_yr or {}

    # ── Profitability ──
    roa_cur  = _safe_div(cur_yr.get("net_profit"),  ta)
    roa_prev = _safe_div(prev.get("net_profit"),    prev.get("total_assets")) if prev else None
    cfo_cur  = cur_yr.get("cfo")

    if roa_cur  is not None and roa_cur > 0:   score += 1   # F1 ROA > 0
    if cfo_cur  is not None and cfo_cur > 0:   score += 1   # F2 CFO > 0
    if roa_cur  is not None and roa_prev is not None and roa_cur > roa_prev:
        score += 1                                           # F3 ΔROa > 0
    # F4 Accruals: CFO/Assets > ROA
    cfo_assets = _safe_div(cfo_cur, ta)
    if cfo_assets is not None and roa_cur is not None and cfo_assets > roa_cur:
        score += 1

    # ── Leverage / Liquidity ──
    ltd_ratio_cur  = _safe_div(cur_yr.get("long_term_debt"),  ta)
    ltd_ratio_prev = _safe_div(prev.get("long_term_debt"),    prev.get("total_assets")) if prev else None
    cr_cur  = _safe_div(cur_yr.get("total_current_assets"), cur_yr.get("total_current_liab"))
    cr_prev = _safe_div(prev.get("total_current_assets"),   prev.get("total_current_liab")) if prev else None

    if ltd_ratio_cur is not None and ltd_ratio_prev is not None and ltd_ratio_cur < ltd_ratio_prev:
        score += 1                                           # F5 Δleverage < 0
    if cr_cur is not None and cr_prev is not None and cr_cur > cr_prev:
        score += 1                                           # F6 Δcurrent ratio > 0
    # F7 No new dilution: equity_raised ≤ 0 (no net new shares issued)
    eq_raised = cur_yr.get("equity_raised")
    if eq_raised is not None and eq_raised <= 0:
        score += 1

    # ── Efficiency ──
    gm_cur  = cur_yr.get("gpm")
    gm_prev = prev.get("gpm") if prev else None
    at_cur  = _safe_div(cur_yr.get("revenue"),  ta)
    at_prev = _safe_div(prev.get("revenue"),    prev.get("total_assets")) if prev else None

    if gm_cur is not None and gm_prev is not None and gm_cur > gm_prev:
        score += 1                                           # F8 Δgross margin > 0
    if at_cur is not None and at_prev is not None and at_cur > at_prev:
        score += 1                                           # F9 Δasset turnover > 0

    return score


def altman_z_score(cur_yr: dict, market_cap: Optional[float]) -> Optional[float]:
    """
    Altman Z-Score (modified for non-manufacturers):
    Z = 1.2*X1 + 1.4*X2 + 3.3*X3 + 0.6*X4 + 1.0*X5
    """
    ta    = cur_yr.get("total_assets")
    if ta is None or ta == 0:
        return None

    wc    = cur_yr.get("working_capital")
    re    = cur_yr.get("retained_earnings")
    ebit  = cur_yr.get("ebit")
    rev   = cur_yr.get("revenue")
    tliab = cur_yr.get("total_debt")   # proxy for total liabilities

    if any(v is None for v in [wc, re, ebit, rev]):
        return None

    x1 = float(wc)   / float(ta)
    x2 = float(re)   / float(ta)
    x3 = float(ebit) / float(ta)
    x5 = float(rev)  / float(ta)

    # X4: market cap / total liabilities (use total_equity as fallback if no market cap)
    if market_cap is not None and tliab is not None and float(tliab) > 0:
        x4 = float(market_cap) / float(tliab)
    elif cur_yr.get("total_equity") is not None and tliab is not None and float(tliab) > 0:
        x4 = float(cur_yr["total_equity"]) / float(tliab)
    else:
        x4 = 0.0

    z = 1.2*x1 + 1.4*x2 + 3.3*x3 + 0.6*x4 + 1.0*x5
    return round(z, 4) if not np.isnan(z) and not np.isinf(z) else None


def sharpe_max_drawdown(prices: pd.Series):
    """
    Sharpe ratio and max drawdown from a 1-year daily close series.
    Returns (sharpe_1y, max_drawdown_1y, volatility_1y).
    """
    if len(prices) < 20:
        return None, None, None

    returns = prices.pct_change().dropna()
    if returns.empty:
        return None, None, None

    ann_vol = returns.std() * np.sqrt(252)
    ann_ret = (prices.iloc[-1] / prices.iloc[0]) - 1

    sharpe = round((ann_ret - RISK_FREE_RATE) / ann_vol, 4) if ann_vol > 0 else None

    cum_max   = prices.cummax()
    drawdowns = (prices - cum_max) / cum_max
    max_dd    = round(float(drawdowns.min()), 4)  # negative value

    return sharpe, max_dd, round(float(ann_vol), 4)


def consecutive_dividend_years(df: pd.DataFrame) -> int:
    """Count years with DPS > 0, starting from the most recent year going back."""
    years = df.sort_values("fiscal_year", ascending=False)
    count = 0
    for _, row in years.iterrows():
        if row["dps"] is not None and float(row["dps"]) > 0:
            count += 1
        else:
            break
    return count


# ── Row Builder ───────────────────────────────────────────────────────────────

def build_yearly_rows(asx_code: str, df: pd.DataFrame, cur) -> list[tuple]:
    """
    For each fiscal_year row, compute all metrics.
    Returns list of tuples ready for execute_values INSERT.
    """
    if df.empty:
        return []

    df = df.reset_index(drop=True)
    rows = []
    now  = datetime.now(tz=timezone.utc)

    # Pre-compute rolling lists (in chronological order)
    roe_list  = []
    roa_list  = []
    roce_list = []
    gm_list   = []
    em_list   = []   # EBITDA margin
    om_list   = []   # EBIT margin
    nm_list   = []   # net margin
    eps_growth_list = []

    # Build per-year dict list for multi-year lookups
    yearly = df.to_dict("records")

    for i, row in enumerate(yearly):
        fy   = row["fiscal_year"]
        ped  = row["period_end_date"]
        prev = yearly[i - 1] if i > 0 else None

        ta = row.get("total_assets")
        te = row.get("total_equity")
        rev  = row.get("revenue")
        ebit = row.get("ebit")
        ni   = row.get("net_profit")
        cfo  = row.get("cfo")
        fcf  = row.get("fcf")
        dps  = row.get("dps")
        eps  = row.get("eps")
        bvps = row.get("book_value_per_share")
        td   = row.get("total_debt")
        nd   = row.get("net_debt")
        ebitda = row.get("ebitda")
        shares = row.get("shares_outstanding")
        gpm    = row.get("gpm")
        opm    = row.get("opm")
        npm    = row.get("npm")
        ebm    = row.get("ebitda_margin")

        # ── Price at period end ────────────────────────────────────────────
        price = fetch_price_at_date(cur, asx_code, ped.date() if hasattr(ped, "date") else ped)
        market_cap = (float(price) * float(shares) / 1e6) if (price and shares) else None

        # ── Profitability ratios ───────────────────────────────────────────
        # Use stored margins if available, else recompute
        gross_margin  = float(gpm) if gpm is not None else _safe_div(row.get("gross_profit"), rev)
        ebitda_margin = float(ebm) if ebm is not None else _safe_div(ebitda, rev)
        ebit_margin   = float(opm) if opm is not None else _safe_div(ebit, rev)
        net_margin    = float(npm) if npm is not None else _safe_div(ni, rev)
        ocf_margin    = _safe_div(cfo, rev)
        fcf_margin    = _safe_div(fcf, rev)

        # Average equity/assets for ROE/ROA
        avg_equity = ((float(te) + float(prev["total_equity"])) / 2
                      if te and prev and prev.get("total_equity") else te)
        avg_assets = ((float(ta) + float(prev["total_assets"])) / 2
                      if ta and prev and prev.get("total_assets") else ta)

        roe  = _safe_div(ni, avg_equity)
        roa  = _safe_div(ni, avg_assets)
        # ROCE = EBIT / Capital Employed; Capital Employed = Total Assets - Current Liab
        cap_emp = ((float(ta) - float(row["total_current_liab"]))
                   if ta and row.get("total_current_liab") else None)
        roce = _safe_div(ebit, cap_emp)
        # ROIC = NOPAT / Invested Capital; NOPAT = EBIT*(1-t); IC ≈ Total Equity + Net Debt
        ic   = ((float(te) + float(nd)) if te and nd else None)
        roic = _safe_div(ni, ic)   # simplified: use NI as NOPAT proxy

        # ── Efficiency ────────────────────────────────────────────────────
        asset_turnover    = _safe_div(rev, avg_assets)
        rec_turnover      = _safe_div(rev, row.get("trade_receivables"))
        inv_turnover      = _safe_div(row.get("ebit"),  row.get("inventory")) if row.get("inventory") else None
        rec_days          = (round(365 / rec_turnover, 2) if rec_turnover and rec_turnover > 0 else None)
        inv_days          = _safe_div(row.get("inventory"), _safe_div(row.get("ebit"), 365)) if row.get("inventory") else None
        pay_days_val      = _safe_div(row.get("trade_payables"), _safe_div(row.get("ebit"), 365))
        capex_intensity   = _safe_div(row.get("capex"), rev) if row.get("capex") else None

        # ── Leverage & liquidity ──────────────────────────────────────────
        cr     = _safe_div(row.get("total_current_assets"), row.get("total_current_liab"))
        de     = _safe_div(td, te)
        da     = _safe_div(td, ta)
        nd_ebitda = _safe_div(nd, ebitda)
        int_cov   = _safe_div(ebit, row.get("interest_expense"))
        lt_debt_cap = _safe_div(row.get("long_term_debt"),
                                ((float(row.get("long_term_debt", 0)) + float(te)) if te else None))

        # ── Per share ─────────────────────────────────────────────────────
        fcf_ps = _safe_div(fcf, shares / 1e6 if shares else None)   # AUD per share
        ocf_ps = _safe_div(cfo, shares / 1e6 if shares else None)

        # ── Valuation ratios ──────────────────────────────────────────────
        pe_ratio  = _safe_div(price, eps)             if price and eps  else None
        pb_ratio  = _safe_div(price, bvps)            if price and bvps else None
        ps_ratio  = _safe_div(market_cap, rev)        if market_cap and rev else None
        ev        = (float(market_cap) + float(nd)) if (market_cap and nd) else None
        ev_ebitda = _safe_div(ev, ebitda)
        ev_ebit   = _safe_div(ev, ebit)
        ev_rev    = _safe_div(ev, rev)
        fcf_yield = _safe_div(fcf_ps, price)          if fcf_ps and price else None
        div_yield = _safe_div(dps, price)             if dps and price else None
        payout_r  = _safe_div(dps, eps)               if eps and eps > 0 else None
        earnings_yield = _safe_div(eps, price)        if price and eps else None

        # Graham number: √(22.5 × EPS × BVPS)
        graham = None
        if eps and bvps and float(eps) > 0 and float(bvps) > 0:
            graham = round(np.sqrt(22.5 * float(eps) * float(bvps)), 4)

        # Franked yield
        fpc = row.get("dps_franking_pct")
        franked_yield = None
        if div_yield and fpc is not None:
            gross_up = float(div_yield) * (1 + (float(fpc) / 100) * 0.4286)  # 30% corp tax grossup
            franked_yield = round(gross_up, 4)

        # ── YoY Growth ────────────────────────────────────────────────────
        rev_g1    = _cagr(rev,  prev.get("revenue"),       1) if prev else None
        gp_g1     = _cagr(row.get("gross_profit"), prev.get("gross_profit"), 1) if prev else None
        ebitda_g1 = _cagr(ebitda, prev.get("ebitda"),      1) if prev else None
        ni_g1     = _cagr(ni,   prev.get("net_profit"),    1) if prev else None
        eps_g1    = _cagr(eps,  prev.get("eps"),           1) if prev else None
        cfo_g1    = _cagr(cfo,  prev.get("cfo"),           1) if prev else None
        fcf_g1    = _cagr(fcf,  prev.get("fcf"),           1) if prev else None
        bvps_g1   = _cagr(bvps, prev.get("book_value_per_share"), 1) if prev else None

        # ── Multi-year CAGRs ─────────────────────────────────────────────
        def fy_n_ago(n):
            return yearly[i - n] if i >= n else None

        def cagr_n(field, n):
            prior = fy_n_ago(n)
            return _cagr(row.get(field), prior.get(field), n) if prior else None

        rev_cagr3  = cagr_n("revenue",    3)
        rev_cagr5  = cagr_n("revenue",    5)
        rev_cagr7  = cagr_n("revenue",    7)
        rev_cagr10 = cagr_n("revenue",   10)
        ni_cagr3   = cagr_n("net_profit", 3)
        ni_cagr5   = cagr_n("net_profit", 5)
        eps_cagr3  = cagr_n("eps",        3)
        eps_cagr5  = cagr_n("eps",        5)
        eb_cagr3   = cagr_n("ebitda",     3)
        eb_cagr5   = cagr_n("ebitda",     5)
        fcf_cagr3  = cagr_n("fcf",        3)
        fcf_cagr5  = cagr_n("fcf",        5)
        gp_cagr3   = cagr_n("gross_profit", 3)
        gp_cagr5   = cagr_n("gross_profit", 5)
        bvps_cagr3 = cagr_n("book_value_per_share", 3)
        bvps_cagr5 = cagr_n("book_value_per_share", 5)

        # ── Rolling averages ──────────────────────────────────────────────
        roe_list .append(roe);  roa_list .append(roa)
        roce_list.append(roce); gm_list  .append(gross_margin)
        em_list  .append(ebitda_margin);  om_list.append(ebit_margin)
        nm_list  .append(net_margin);     eps_growth_list.append(eps_g1)

        avg_roe3  = _rolling_avg(roe_list,  3)
        avg_roe5  = _rolling_avg(roe_list,  5)
        avg_roa3  = _rolling_avg(roa_list,  3)
        avg_roa5  = _rolling_avg(roa_list,  5)
        avg_roce3 = _rolling_avg(roce_list, 3)
        avg_roce5 = _rolling_avg(roce_list, 5)
        avg_gm3   = _rolling_avg(gm_list,   3)
        avg_gm5   = _rolling_avg(gm_list,   5)
        avg_em3   = _rolling_avg(em_list,   3)
        avg_em5   = _rolling_avg(em_list,   5)
        avg_om3   = _rolling_avg(om_list,   3)
        avg_om5   = _rolling_avg(om_list,   5)
        avg_nm3   = _rolling_avg(nm_list,   3)
        avg_nm5   = _rolling_avg(nm_list,   5)
        avg_epsg3 = _rolling_avg(eps_growth_list, 3)
        avg_epsg5 = _rolling_avg(eps_growth_list, 5)

        # ── Quality scores ────────────────────────────────────────────────
        f_score = piotroski_f_score(row, prev)
        z_score = altman_z_score(row, market_cap)

        # ── Dividend: consecutive years ───────────────────────────────────
        # Only compute for the most recent FY (expensive); for historic FYs use None
        div_consec = consecutive_dividend_years(df) if i == len(yearly) - 1 else None

        # Dividend CAGR 3y
        dps_prev3  = fy_n_ago(3)
        div_cagr3  = _cagr(dps, dps_prev3.get("dps"), 3) if dps_prev3 else None
        div_cagr5  = _cagr(dps, fy_n_ago(5).get("dps"), 5) if fy_n_ago(5) else None

        # ── Risk & performance (price-based) ─────────────────────────────
        price_series = fetch_daily_prices_for_year(cur, asx_code, ped)
        sharpe, max_dd, vol_1y = sharpe_max_drawdown(price_series)

        # ── Build tuple ───────────────────────────────────────────────────
        rows.append((
            asx_code, fy,
            ped.date() if hasattr(ped, "date") else ped,
            _nan_to_none(price),
            _nan_to_none(market_cap),
            int(shares) if shares else None,
            # Valuation
            _nan_to_none(pe_ratio), _nan_to_none(pb_ratio),
            _nan_to_none(ps_ratio),
            _nan_to_none(ev), _nan_to_none(ev_ebitda),
            _nan_to_none(ev_ebit), _nan_to_none(ev_rev),
            _nan_to_none(earnings_yield), _nan_to_none(fcf_yield),
            _nan_to_none(graham),
            # Per share
            _nan_to_none(eps), _nan_to_none(row.get("eps_diluted")),
            _nan_to_none(bvps), _nan_to_none(dps),
            _nan_to_none(row.get("dps_franking_pct")),
            # Dividend
            _nan_to_none(div_yield), _nan_to_none(franked_yield),
            _nan_to_none(payout_r),
            _nan_to_none(div_cagr3), _nan_to_none(div_cagr5),
            div_consec,
            # Returns on capital
            _nan_to_none(roe), _nan_to_none(roa),
            _nan_to_none(roce), _nan_to_none(roic),
            # Margins
            _nan_to_none(gross_margin), _nan_to_none(ebitda_margin),
            _nan_to_none(ebit_margin), _nan_to_none(net_margin),
            _nan_to_none(ocf_margin),  _nan_to_none(fcf_margin),
            # Efficiency
            _nan_to_none(asset_turnover), _nan_to_none(rec_turnover),
            _nan_to_none(rec_days), _nan_to_none(capex_intensity),
            # Leverage & liquidity
            _nan_to_none(cr), _nan_to_none(de), _nan_to_none(da),
            _nan_to_none(nd_ebitda), _nan_to_none(int_cov),
            _nan_to_none(lt_debt_cap),
            # Quality scores
            f_score, _nan_to_none(z_score),
            # YoY growth
            _nan_to_none(rev_g1), _nan_to_none(gp_g1),
            _nan_to_none(ebitda_g1), _nan_to_none(ni_g1),
            _nan_to_none(eps_g1), _nan_to_none(cfo_g1),
            _nan_to_none(fcf_g1), _nan_to_none(bvps_g1),
            # Revenue CAGR
            _nan_to_none(rev_cagr3), _nan_to_none(rev_cagr5),
            _nan_to_none(rev_cagr7), _nan_to_none(rev_cagr10),
            # Net income CAGR
            _nan_to_none(ni_cagr3), _nan_to_none(ni_cagr5),
            # EPS CAGR
            _nan_to_none(eps_cagr3), _nan_to_none(eps_cagr5),
            # EBITDA CAGR
            _nan_to_none(eb_cagr3), _nan_to_none(eb_cagr5),
            # FCF CAGR
            _nan_to_none(fcf_cagr3), _nan_to_none(fcf_cagr5),
            # Gross profit CAGR
            _nan_to_none(gp_cagr3), _nan_to_none(gp_cagr5),
            # BVPS CAGR
            _nan_to_none(bvps_cagr3), _nan_to_none(bvps_cagr5),
            # Rolling averages — ROE
            _nan_to_none(avg_roe3), _nan_to_none(avg_roe5),
            # Rolling averages — ROA
            _nan_to_none(avg_roa3), _nan_to_none(avg_roa5),
            # Rolling averages — ROCE
            _nan_to_none(avg_roce3), _nan_to_none(avg_roce5),
            # Rolling averages — Margins
            _nan_to_none(avg_gm3),  _nan_to_none(avg_gm5),
            _nan_to_none(avg_em3),  _nan_to_none(avg_em5),
            _nan_to_none(avg_om3),  _nan_to_none(avg_om5),
            _nan_to_none(avg_nm3),  _nan_to_none(avg_nm5),
            # Rolling averages — EPS growth
            _nan_to_none(avg_epsg3), _nan_to_none(avg_epsg5),
            # Risk & performance
            _nan_to_none(vol_1y), _nan_to_none(sharpe),
            _nan_to_none(max_dd),
            COMPUTE_VERSION, now,
        ))

    return rows


# ── Database Write ────────────────────────────────────────────────────────────

INSERT_SQL = """
    INSERT INTO market.yearly_metrics (
        asx_code, fiscal_year, period_end_date, price_at_compute,
        market_cap, shares_outstanding,
        -- Valuation
        pe_ratio, pb_ratio, ps_ratio,
        enterprise_value, ev_ebitda, ev_ebit, ev_revenue,
        earnings_yield, fcf_yield, graham_number,
        -- Per share
        eps, eps_diluted, bvps, dps, franking_pct,
        -- Dividend
        dividend_yield, franked_yield, payout_ratio,
        dividend_cagr_3y, dividend_cagr_5y, dividend_consecutive_yrs,
        -- Returns on capital
        roe, roa, roce, roic,
        -- Margins
        gross_margin, ebitda_margin, ebit_margin, net_margin,
        ocf_margin, fcf_margin,
        -- Efficiency
        asset_turnover, receivables_turnover, receivables_days, capex_intensity,
        -- Leverage & liquidity
        current_ratio, debt_to_equity, debt_to_assets,
        net_debt_to_ebitda, interest_coverage, lt_debt_to_capital,
        -- Quality scores
        piotroski_f_score, altman_z_score,
        -- YoY growth
        revenue_growth_1y, gross_profit_growth_1y, ebitda_growth_1y,
        net_income_growth_1y, eps_growth_1y, ocf_growth_1y,
        fcf_growth_1y, bvps_growth_1y,
        -- Revenue CAGR
        revenue_cagr_3y, revenue_cagr_5y, revenue_cagr_7y, revenue_cagr_10y,
        -- Net income CAGR
        net_income_cagr_3y, net_income_cagr_5y,
        -- EPS CAGR
        eps_cagr_3y, eps_cagr_5y,
        -- EBITDA CAGR
        ebitda_cagr_3y, ebitda_cagr_5y,
        -- FCF CAGR
        fcf_cagr_3y, fcf_cagr_5y,
        -- Gross profit CAGR
        gross_profit_cagr_3y, gross_profit_cagr_5y,
        -- BVPS CAGR
        bvps_cagr_3y, bvps_cagr_5y,
        -- Rolling averages ROE / ROA / ROCE
        avg_roe_3y, avg_roe_5y,
        avg_roa_3y, avg_roa_5y,
        avg_roce_3y, avg_roce_5y,
        -- Rolling averages margins
        avg_gross_margin_3y, avg_gross_margin_5y,
        avg_ebitda_margin_3y, avg_ebitda_margin_5y,
        avg_operating_margin_3y, avg_operating_margin_5y,
        avg_net_margin_3y, avg_net_margin_5y,
        -- Rolling averages EPS growth
        avg_eps_growth_3y, avg_eps_growth_5y,
        -- Risk & performance
        volatility_1y, sharpe_1y, max_drawdown_1y,
        compute_version, computed_at
    ) VALUES %s
    ON CONFLICT (asx_code, fiscal_year) DO UPDATE SET
        period_end_date         = EXCLUDED.period_end_date,
        price_at_compute        = EXCLUDED.price_at_compute,
        market_cap              = EXCLUDED.market_cap,
        shares_outstanding      = EXCLUDED.shares_outstanding,
        pe_ratio                = EXCLUDED.pe_ratio,
        pb_ratio                = EXCLUDED.pb_ratio,
        ps_ratio                = EXCLUDED.ps_ratio,
        enterprise_value        = EXCLUDED.enterprise_value,
        ev_ebitda               = EXCLUDED.ev_ebitda,
        ev_ebit                 = EXCLUDED.ev_ebit,
        ev_revenue              = EXCLUDED.ev_revenue,
        earnings_yield          = EXCLUDED.earnings_yield,
        fcf_yield               = EXCLUDED.fcf_yield,
        graham_number           = EXCLUDED.graham_number,
        eps                     = EXCLUDED.eps,
        eps_diluted             = EXCLUDED.eps_diluted,
        bvps                    = EXCLUDED.bvps,
        dps                     = EXCLUDED.dps,
        franking_pct            = EXCLUDED.franking_pct,
        dividend_yield          = EXCLUDED.dividend_yield,
        franked_yield           = EXCLUDED.franked_yield,
        payout_ratio            = EXCLUDED.payout_ratio,
        dividend_cagr_3y        = EXCLUDED.dividend_cagr_3y,
        dividend_cagr_5y        = EXCLUDED.dividend_cagr_5y,
        dividend_consecutive_yrs = EXCLUDED.dividend_consecutive_yrs,
        roe                     = EXCLUDED.roe,
        roa                     = EXCLUDED.roa,
        roce                    = EXCLUDED.roce,
        roic                    = EXCLUDED.roic,
        gross_margin            = EXCLUDED.gross_margin,
        ebitda_margin           = EXCLUDED.ebitda_margin,
        ebit_margin             = EXCLUDED.ebit_margin,
        net_margin              = EXCLUDED.net_margin,
        ocf_margin              = EXCLUDED.ocf_margin,
        fcf_margin              = EXCLUDED.fcf_margin,
        asset_turnover          = EXCLUDED.asset_turnover,
        receivables_turnover    = EXCLUDED.receivables_turnover,
        receivables_days        = EXCLUDED.receivables_days,
        capex_intensity         = EXCLUDED.capex_intensity,
        current_ratio           = EXCLUDED.current_ratio,
        debt_to_equity          = EXCLUDED.debt_to_equity,
        debt_to_assets          = EXCLUDED.debt_to_assets,
        net_debt_to_ebitda      = EXCLUDED.net_debt_to_ebitda,
        interest_coverage       = EXCLUDED.interest_coverage,
        lt_debt_to_capital      = EXCLUDED.lt_debt_to_capital,
        piotroski_f_score       = EXCLUDED.piotroski_f_score,
        altman_z_score          = EXCLUDED.altman_z_score,
        revenue_growth_1y       = EXCLUDED.revenue_growth_1y,
        gross_profit_growth_1y  = EXCLUDED.gross_profit_growth_1y,
        ebitda_growth_1y        = EXCLUDED.ebitda_growth_1y,
        net_income_growth_1y    = EXCLUDED.net_income_growth_1y,
        eps_growth_1y           = EXCLUDED.eps_growth_1y,
        ocf_growth_1y           = EXCLUDED.ocf_growth_1y,
        fcf_growth_1y           = EXCLUDED.fcf_growth_1y,
        bvps_growth_1y          = EXCLUDED.bvps_growth_1y,
        revenue_cagr_3y         = EXCLUDED.revenue_cagr_3y,
        revenue_cagr_5y         = EXCLUDED.revenue_cagr_5y,
        revenue_cagr_7y         = EXCLUDED.revenue_cagr_7y,
        revenue_cagr_10y        = EXCLUDED.revenue_cagr_10y,
        net_income_cagr_3y      = EXCLUDED.net_income_cagr_3y,
        net_income_cagr_5y      = EXCLUDED.net_income_cagr_5y,
        eps_cagr_3y             = EXCLUDED.eps_cagr_3y,
        eps_cagr_5y             = EXCLUDED.eps_cagr_5y,
        ebitda_cagr_3y          = EXCLUDED.ebitda_cagr_3y,
        ebitda_cagr_5y          = EXCLUDED.ebitda_cagr_5y,
        fcf_cagr_3y             = EXCLUDED.fcf_cagr_3y,
        fcf_cagr_5y             = EXCLUDED.fcf_cagr_5y,
        gross_profit_cagr_3y    = EXCLUDED.gross_profit_cagr_3y,
        gross_profit_cagr_5y    = EXCLUDED.gross_profit_cagr_5y,
        bvps_cagr_3y            = EXCLUDED.bvps_cagr_3y,
        bvps_cagr_5y            = EXCLUDED.bvps_cagr_5y,
        avg_roe_3y              = EXCLUDED.avg_roe_3y,
        avg_roe_5y              = EXCLUDED.avg_roe_5y,
        avg_roa_3y              = EXCLUDED.avg_roa_3y,
        avg_roa_5y              = EXCLUDED.avg_roa_5y,
        avg_roce_3y             = EXCLUDED.avg_roce_3y,
        avg_roce_5y             = EXCLUDED.avg_roce_5y,
        avg_gross_margin_3y     = EXCLUDED.avg_gross_margin_3y,
        avg_gross_margin_5y     = EXCLUDED.avg_gross_margin_5y,
        avg_ebitda_margin_3y    = EXCLUDED.avg_ebitda_margin_3y,
        avg_ebitda_margin_5y    = EXCLUDED.avg_ebitda_margin_5y,
        avg_operating_margin_3y = EXCLUDED.avg_operating_margin_3y,
        avg_operating_margin_5y = EXCLUDED.avg_operating_margin_5y,
        avg_net_margin_3y       = EXCLUDED.avg_net_margin_3y,
        avg_net_margin_5y       = EXCLUDED.avg_net_margin_5y,
        avg_eps_growth_3y       = EXCLUDED.avg_eps_growth_3y,
        avg_eps_growth_5y       = EXCLUDED.avg_eps_growth_5y,
        volatility_1y           = EXCLUDED.volatility_1y,
        sharpe_1y               = EXCLUDED.sharpe_1y,
        max_drawdown_1y         = EXCLUDED.max_drawdown_1y,
        compute_version         = EXCLUDED.compute_version,
        computed_at             = EXCLUDED.computed_at
"""


def upsert_rows(cur, rows: list[tuple]) -> int:
    if not rows:
        return 0
    execute_values(cur, INSERT_SQL, rows, page_size=200)
    return len(rows)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="ASX Yearly Compute Engine")
    parser.add_argument("--codes",    nargs="+", help="Specific ASX codes")
    parser.add_argument("--limit",    type=int,  help="Max stocks to process")
    parser.add_argument("--min-year", type=int,  help="Only upsert rows for fiscal_year >= N")
    args = parser.parse_args()

    conn = psycopg2.connect(DB_URL)
    cur  = conn.cursor()

    codes = fetch_codes(cur, args.codes, args.limit)
    total = len(codes)
    log.info(f"Yearly compute — {total} stocks"
             + (f" | min-year {args.min_year}" if args.min_year else " (all years)"))
    log.info("─" * 60)

    processed = skipped = errors = total_rows = 0

    for i, asx_code in enumerate(codes, 1):
        try:
            df = fetch_annual_financials(cur, asx_code)
            if df.empty:
                skipped += 1
                continue

            if args.min_year:
                # Still pass full history so CAGRs compute correctly;
                # filter output rows afterwards
                pass

            rows = build_yearly_rows(asx_code, df, cur)
            if not rows:
                skipped += 1
                continue

            if args.min_year:
                rows = [r for r in rows if r[1] >= args.min_year]
            if not rows:
                skipped += 1
                continue

            n = upsert_rows(cur, rows)
            total_rows += n
            processed  += 1

            if i % BATCH_COMMIT == 0:
                conn.commit()
                log.info(f"  [{i:4d}/{total}] {processed} done | "
                         f"{skipped} skipped | {errors} errors | "
                         f"{total_rows:,} rows so far")

        except Exception as e:
            errors += 1
            log.warning(f"  {asx_code}: {e}")
            conn.rollback()

    conn.commit()
    cur.close()
    conn.close()

    log.info("─" * 60)
    log.info(f"Done! {processed} stocks | {skipped} skipped | "
             f"{errors} errors | {total_rows:,} rows upserted")


if __name__ == "__main__":
    main()
