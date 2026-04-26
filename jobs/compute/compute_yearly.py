"""
ASX Screener — Compute Yearly Metrics (Seq 2)
==============================================
Reads raw annual financials from financials.annual_* tables and computes:
  - Valuation ratios (PE, PB, PS, EV/EBITDA, etc.)
  - Return on capital (ROE, ROA, ROIC, ROCE)
  - Margin ratios (gross, EBITDA, EBIT, net, FCF)
  - Efficiency ratios (asset turnover, DSO, DIO, DPO, CCC)
  - Leverage & liquidity (D/E, net debt/EBITDA, current ratio, etc.)
  - Quality scores (Piotroski F-Score, Altman Z-Score)
  - Multi-year growth CAGRs (3Y/5Y/7Y/10Y revenue, profit, EPS)
  - Multi-year averages (avg ROE 3Y/5Y/7Y/10Y, avg ROCE, avg margins)
  - Price CAGRs (1Y/3Y/5Y/7Y/10Y)
  - Risk metrics (beta, volatility, Sharpe)

Execution sequence: AFTER financial data is loaded, BEFORE all other computes.

Usage:
    python jobs/compute/compute_yearly.py              # All active stocks
    python jobs/compute/compute_yearly.py --codes BHP CBA
    python jobs/compute/compute_yearly.py --mode historical  # All past FYs
    python jobs/compute/compute_yearly.py --fy 2024    # Specific fiscal year
    python jobs/compute/compute_yearly.py --from-code WBC  # Resume from code
"""

import os
import sys
import math
import time
import logging
import argparse
import statistics
from datetime import date, datetime
from typing import Optional

import psycopg2
from psycopg2.extras import execute_values, RealDictCursor
from dotenv import load_dotenv

load_dotenv()

DB_URL          = os.getenv("DATABASE_URL_SYNC",
                    "postgresql://asx_user:asx_secure_2024@localhost:5432/asx_screener")
COMPUTE_VERSION = "yearly_v1.0"
SLEEP_SEC       = 0.05
RFR             = 0.043   # RBA cash rate (risk-free rate) — update quarterly

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
#  Safe math helpers
# ─────────────────────────────────────────────────────────────

def floatify(d: dict) -> dict:
    """Convert Decimal values to float so standard arithmetic works."""
    from decimal import Decimal
    return {k: float(v) if isinstance(v, Decimal) else v
            for k, v in (d or {}).items()}

def safe_div(num, denom, scale=1):
    """Return num/denom*scale, None if denom is zero or either is None."""
    if num is None or denom is None or denom == 0:
        return None
    result = (num / denom) * scale
    return round(result, 6) if abs(result) < 1e12 else None


def safe_ratio(num, denom):
    """Return num/denom rounded to 4dp, clamped for display."""
    if num is None or denom is None or denom == 0:
        return None
    r = num / denom
    return round(r, 4) if abs(r) < 99999 else None


def safe_pct(num, denom):
    """Return (num/denom)*100 as percentage, None on bad inputs."""
    v = safe_div(num, denom, 100)
    return round(v, 4) if v is not None else None


def cagr(end_val, start_val, years):
    """Compound Annual Growth Rate. Returns None if inputs invalid."""
    if not end_val or not start_val or years <= 0:
        return None
    if start_val < 0 and end_val < 0:
        return None          # both negative — CAGR meaningless
    if start_val <= 0:
        return None          # can't compute from zero/negative base
    try:
        rate = (end_val / start_val) ** (1 / years) - 1
        return round(rate * 100, 4)   # return as %
    except (ZeroDivisionError, ValueError):
        return None


def median_growth(values: list) -> Optional[float]:
    """Median of YoY growth rates from a list of (year, value) tuples."""
    if len(values) < 2:
        return None
    rates = []
    sorted_vals = sorted(values, key=lambda x: x[0])   # sort by year
    for i in range(1, len(sorted_vals)):
        prev = sorted_vals[i - 1][1]
        curr = sorted_vals[i][1]
        if prev and prev > 0 and curr is not None:
            rates.append((curr - prev) / prev * 100)
    return round(statistics.median(rates), 4) if len(rates) >= 2 else None


def piotroski_score(pnl0, pnl1, bs0, bs1, cf0) -> Optional[int]:
    """
    Piotroski F-Score (0–9). Each criterion = 1 point.
    Profitability (4): ROA > 0, OCF > 0, ROA increasing, OCF > Net Income
    Leverage (3): Debt/Assets decreasing, Current ratio increasing, Shares not diluted
    Efficiency (2): Gross margin increasing, Asset turnover increasing
    """
    score = 0
    try:
        # ── Profitability ──────────────────────────────────
        # F1: ROA > 0
        if bs0.get("total_assets") and pnl0.get("net_profit"):
            roa0 = pnl0["net_profit"] / bs0["total_assets"]
            if roa0 > 0:
                score += 1

        # F2: OCF > 0
        if cf0.get("cfo") and cf0["cfo"] > 0:
            score += 1

        # F3: ROA increasing (ROA0 > ROA1)
        if (bs0.get("total_assets") and bs1.get("total_assets") and
                pnl0.get("net_profit") and pnl1.get("net_profit")):
            roa0 = pnl0["net_profit"] / bs0["total_assets"]
            roa1 = pnl1["net_profit"] / bs1["total_assets"]
            if roa0 > roa1:
                score += 1

        # F4: OCF > Net Income (earnings quality)
        if cf0.get("cfo") and pnl0.get("net_profit"):
            if cf0["cfo"] > pnl0["net_profit"]:
                score += 1

        # ── Leverage ───────────────────────────────────────
        # F5: Long-term debt ratio decreasing
        if (bs0.get("total_assets") and bs1.get("total_assets") and
                bs0.get("long_term_debt") is not None and bs1.get("long_term_debt") is not None):
            dr0 = (bs0["long_term_debt"] or 0) / bs0["total_assets"]
            dr1 = (bs1["long_term_debt"] or 0) / bs1["total_assets"]
            if dr0 < dr1:
                score += 1

        # F6: Current ratio increasing
        if (bs0.get("total_current_assets") and bs0.get("total_current_liab") and
                bs1.get("total_current_assets") and bs1.get("total_current_liab")):
            cr0 = bs0["total_current_assets"] / bs0["total_current_liab"]
            cr1 = bs1["total_current_assets"] / bs1["total_current_liab"]
            if cr0 > cr1:
                score += 1

        # F7: No new shares issued
        shares0 = bs0.get("shares_outstanding")
        shares1 = bs1.get("shares_outstanding")
        if shares0 and shares1 and shares0 <= shares1 * 1.01:   # allow 1% tolerance
            score += 1

        # ── Efficiency ─────────────────────────────────────
        # F8: Gross margin increasing
        if (pnl0.get("gross_profit") and pnl0.get("revenue") and
                pnl1.get("gross_profit") and pnl1.get("revenue")):
            gm0 = pnl0["gross_profit"] / pnl0["revenue"]
            gm1 = pnl1["gross_profit"] / pnl1["revenue"]
            if gm0 > gm1:
                score += 1

        # F9: Asset turnover increasing
        if (pnl0.get("revenue") and bs0.get("total_assets") and
                pnl1.get("revenue") and bs1.get("total_assets")):
            at0 = pnl0["revenue"] / bs0["total_assets"]
            at1 = pnl1["revenue"] / bs1["total_assets"]
            if at0 > at1:
                score += 1

    except Exception:
        pass

    return score


def altman_z(pnl, bs, market_cap) -> Optional[float]:
    """
    Altman Z-Score for non-financial companies.
    Z = 1.2*X1 + 1.4*X2 + 3.3*X3 + 0.6*X4 + 1.0*X5
    """
    try:
        ta = bs.get("total_assets")
        if not ta or ta == 0:
            return None

        wc   = (bs.get("total_current_assets") or 0) - (bs.get("total_current_liab") or 0)
        re   = bs.get("retained_earnings") or 0
        ebit_v = pnl.get("ebit") or 0
        tl   = bs.get("total_liabilities") or 0
        rev  = pnl.get("revenue") or 0

        x1 = wc   / ta
        x2 = re   / ta
        x3 = ebit_v / ta
        x4 = (market_cap or 0) / tl if tl else 0
        x5 = rev  / ta

        z = 1.2*x1 + 1.4*x2 + 3.3*x3 + 0.6*x4 + 1.0*x5
        return round(z, 4)
    except Exception:
        return None


def beneish_m(pnls: list) -> Optional[float]:
    """
    Beneish M-Score (simplified 5-variable version).
    Requires at least 2 years of P&L + Balance Sheet data.
    M < -2.22 → unlikely manipulator. M > -2.22 → possible manipulator.
    """
    if len(pnls) < 2:
        return None
    try:
        p0, p1 = pnls[0], pnls[1]   # current, prior year
        # DSRI: Days Sales Receivable Index
        rec0 = p0["pnl"].get("revenue") or 1
        rec1 = p1["pnl"].get("revenue") or 1
        ar0  = p0["bs"].get("trade_receivables") or 0
        ar1  = p1["bs"].get("trade_receivables") or 0
        dsri = (ar0 / rec0) / (ar1 / rec1) if rec1 else None

        # GMI: Gross Margin Index
        gm0 = safe_pct(p0["pnl"].get("gross_profit"), p0["pnl"].get("revenue"))
        gm1 = safe_pct(p1["pnl"].get("gross_profit"), p1["pnl"].get("revenue"))
        gmi = gm1 / gm0 if gm0 and gm0 != 0 else None

        # AQI: Asset Quality Index
        ta0 = p0["bs"].get("total_assets") or 1
        ta1 = p1["bs"].get("total_assets") or 1
        ca0 = p0["bs"].get("total_current_assets") or 0
        ca1 = p1["bs"].get("total_current_assets") or 0
        ppe0 = p0["bs"].get("net_block") or 0
        ppe1 = p1["bs"].get("net_block") or 0
        aqi = ((1 - (ca0 + ppe0) / ta0) /
               (1 - (ca1 + ppe1) / ta1)) if ta1 else None

        # SGI: Sales Growth Index
        sgi = rec0 / rec1 if rec1 else None

        # DEPI: Depreciation Index
        dep0 = p0["pnl"].get("depreciation") or 0
        dep1 = p1["pnl"].get("depreciation") or 0
        nb0  = p0["bs"].get("net_block") or 1
        nb1  = p1["bs"].get("net_block") or 1
        dep_rate0 = dep0 / (dep0 + nb0) if (dep0 + nb0) else None
        dep_rate1 = dep1 / (dep1 + nb1) if (dep1 + nb1) else None
        depi = dep_rate1 / dep_rate0 if dep_rate0 and dep_rate0 != 0 else None

        vals = [dsri, gmi, aqi, sgi, depi]
        if any(v is None for v in vals):
            return None

        m = (-4.84 + 0.92*dsri + 0.528*gmi + 0.404*aqi +
              0.892*sgi + 0.115*depi)
        return round(m, 4)
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────
#  Data fetching
# ─────────────────────────────────────────────────────────────

def fetch_all_pnl(cur, asx_code: str) -> list[dict]:
    cur.execute("""
        SELECT * FROM financials.annual_pnl
        WHERE asx_code = %s ORDER BY fiscal_year DESC
    """, (asx_code,))
    return [floatify(r) for r in cur.fetchall()]


def fetch_all_bs(cur, asx_code: str) -> list[dict]:
    cur.execute("""
        SELECT * FROM financials.annual_balance_sheet
        WHERE asx_code = %s ORDER BY fiscal_year DESC
    """, (asx_code,))
    return [floatify(r) for r in cur.fetchall()]


def fetch_all_cf(cur, asx_code: str) -> list[dict]:
    cur.execute("""
        SELECT * FROM financials.annual_cashflow
        WHERE asx_code = %s ORDER BY fiscal_year DESC
    """, (asx_code,))
    return [floatify(r) for r in cur.fetchall()]


def fetch_price_at_fy(cur, asx_code: str, fy_end_date: date) -> Optional[float]:
    """Get closing price on or just before FY end date."""
    cur.execute("""
        SELECT close FROM market.daily_prices
        WHERE asx_code = %s AND time::date <= %s
        ORDER BY time DESC LIMIT 1
    """, (asx_code, fy_end_date))
    row = cur.fetchone()
    return float(row["close"]) if row and row["close"] else None


def fetch_price_history(cur, asx_code: str) -> list[tuple]:
    """Returns [(date, adj_close)] sorted ascending for CAGR/returns calc."""
    cur.execute("""
        SELECT time::date AS dt, adjusted_close
        FROM market.daily_prices
        WHERE asx_code = %s AND adjusted_close IS NOT NULL
        ORDER BY time ASC
    """, (asx_code,))
    return [(r["dt"], float(r["adjusted_close"])) for r in cur.fetchall()]


def get_price_on_or_before(history: list[tuple], target_date: date) -> Optional[float]:
    """Binary search for the closest price on or before target_date."""
    lo, hi = 0, len(history) - 1
    result = None
    while lo <= hi:
        mid = (lo + hi) // 2
        if history[mid][0] <= target_date:
            result = history[mid][1]
            lo = mid + 1
        else:
            hi = mid - 1
    return result


def annualised_vol(history: list[tuple], years: int) -> Optional[float]:
    """Annualised historical volatility using daily log returns over N years."""
    if not history:
        return None
    cutoff = date(date.today().year - years, date.today().month, date.today().day)
    window = [p for d, p in history if d >= cutoff]
    if len(window) < 20:
        return None
    log_rets = [math.log(window[i] / window[i-1])
                for i in range(1, len(window))
                if window[i-1] > 0]
    if len(log_rets) < 10:
        return None
    std = statistics.stdev(log_rets)
    return round(std * math.sqrt(252) * 100, 4)   # annualised %


def compute_beta(cur, asx_code: str, xjo_history: list[tuple], years: int) -> Optional[float]:
    """Beta of stock vs XJO (ASX 200) using N years of daily returns."""
    cur.execute("""
        SELECT time::date AS dt, adjusted_close
        FROM market.daily_prices
        WHERE asx_code = %s AND adjusted_close IS NOT NULL
        ORDER BY time ASC
    """, (asx_code,))
    stock_prices = {r["dt"]: float(r["adjusted_close"]) for r in cur.fetchall()}

    cutoff = date(date.today().year - years, date.today().month, date.today().day)
    xjo_dict = {d: p for d, p in xjo_history if d >= cutoff}
    common_dates = sorted(set(stock_prices) & set(xjo_dict))

    if len(common_dates) < 60:
        return None

    s_rets = [math.log(stock_prices[common_dates[i]] / stock_prices[common_dates[i-1]])
              for i in range(1, len(common_dates))
              if stock_prices.get(common_dates[i-1], 0) > 0]
    m_rets = [math.log(xjo_dict[common_dates[i]] / xjo_dict[common_dates[i-1]])
              for i in range(1, len(common_dates))
              if xjo_dict.get(common_dates[i-1], 0) > 0]

    if len(s_rets) < 50 or len(m_rets) < 50:
        return None

    n = min(len(s_rets), len(m_rets))
    s_rets, m_rets = s_rets[:n], m_rets[:n]

    cov = sum((s - statistics.mean(s_rets)) * (m - statistics.mean(m_rets))
              for s, m in zip(s_rets, m_rets)) / (n - 1)
    var = statistics.variance(m_rets)
    return round(cov / var, 4) if var else None


# ─────────────────────────────────────────────────────────────
#  Core compute function for one stock / one fiscal year
# ─────────────────────────────────────────────────────────────

def compute_for_fy(asx_code: str, fiscal_year: int,
                   pnl_rows: list, bs_rows: list, cf_rows: list,
                   price_history: list, xjo_history: list,
                   cur) -> Optional[dict]:
    """
    Compute all yearly metrics for one (asx_code, fiscal_year).
    Returns a dict of column → value ready for upsert, or None if insufficient data.
    """
    # Index rows by fiscal_year for O(1) lookup
    pnl_by_fy = {r["fiscal_year"]: r for r in pnl_rows}
    bs_by_fy  = {r["fiscal_year"]: r for r in bs_rows}
    cf_by_fy  = {r["fiscal_year"]: r for r in cf_rows}

    pnl0 = pnl_by_fy.get(fiscal_year)
    bs0  = bs_by_fy.get(fiscal_year)
    cf0  = cf_by_fy.get(fiscal_year)

    if not pnl0 or not bs0:
        return None

    period_end = pnl0["period_end_date"]
    price = fetch_price_at_fy(cur, asx_code, period_end) if price_history else None

    # Prior year rows for growth / Piotroski
    pnl1 = pnl_by_fy.get(fiscal_year - 1)
    bs1  = bs_by_fy.get(fiscal_year - 1)

    # Shares outstanding
    shares = bs0.get("shares_outstanding")

    # Market cap and EV
    market_cap = (price * shares / 1_000_000) if price and shares else None
    net_debt   = bs0.get("net_debt")
    ev         = (market_cap + net_debt) if market_cap is not None and net_debt is not None else None

    # Core financials (AUD millions)
    rev      = pnl0.get("revenue")
    gp       = pnl0.get("gross_profit")
    ebitda_v = pnl0.get("ebitda")
    ebit_v   = pnl0.get("ebit")
    pat      = pnl0.get("net_profit")
    dep      = pnl0.get("depreciation")
    int_exp  = pnl0.get("interest_expense")
    tax      = pnl0.get("tax")
    pbt      = pnl0.get("pbt")
    eps      = pnl0.get("eps")
    dps      = pnl0.get("dps")
    frank    = pnl0.get("dps_franking_pct") or 0

    ta       = bs0.get("total_assets")
    te       = bs0.get("total_equity")
    td       = bs0.get("total_debt")
    ca       = bs0.get("total_current_assets")
    cl       = bs0.get("total_current_liab")
    inv      = bs0.get("inventory")
    rec      = bs0.get("trade_receivables")
    pay      = bs0.get("trade_payables")
    ltd      = bs0.get("long_term_debt")
    cash_v   = bs0.get("cash_equivalents")
    bvps_v   = bs0.get("book_value_per_share")

    ocf      = cf0.get("cfo")  if cf0 else None
    fcf      = cf0.get("fcf")  if cf0 else None
    capex    = cf0.get("capex") if cf0 else None

    # ── Valuation ratios ──────────────────────────────────────
    pe       = safe_ratio(price, eps) if price and eps and eps > 0 else None
    pb       = safe_ratio(price, bvps_v) if price and bvps_v and bvps_v > 0 else None
    ps       = safe_ratio(market_cap, rev) if market_cap and rev else None
    pcf      = safe_ratio(price, (ocf / shares * 1_000_000) if ocf and shares else None)
    pfcf     = safe_ratio(price, (fcf / shares * 1_000_000) if fcf and shares else None)
    ev_ebitda= safe_ratio(ev, ebitda_v) if ev and ebitda_v else None
    ev_ebit  = safe_ratio(ev, ebit_v)   if ev and ebit_v   else None
    ev_rev   = safe_ratio(ev, rev)       if ev and rev       else None
    ev_fcf   = safe_ratio(ev, fcf)       if ev and fcf       else None

    earn_yld = safe_pct(eps, price) if eps and price else None
    fcf_yld  = safe_pct(fcf / shares * 1_000_000, price) if fcf and shares and price else None
    div_yld  = safe_pct(dps, price) if dps and price else None
    gross_up = dps * (1 + frank / 100 * 0.43 / 0.57) if dps and frank else dps
    frnk_yld = safe_pct(gross_up, price) if gross_up and price else None
    payout   = safe_pct(dps, eps) if dps and eps and eps > 0 else None

    graham   = None
    if eps and bvps_v and eps > 0 and bvps_v > 0:
        graham = round(math.sqrt(22.5 * float(eps) * float(bvps_v)), 4)

    # ── Per share ─────────────────────────────────────────────
    tbvps_v  = None
    if ta and bs0.get("goodwill") is not None and bs0.get("intangibles") is not None and te:
        tang_assets = ta - (bs0["goodwill"] or 0) - (bs0["intangibles"] or 0)
        tbvps_v = round(tang_assets * 1_000_000 / shares, 4) if shares else None

    fcf_ps   = round(fcf * 1_000_000 / shares, 4) if fcf and shares else None
    ocf_ps   = round(ocf * 1_000_000 / shares, 4) if ocf and shares else None
    rev_ps   = round(rev * 1_000_000 / shares, 4) if rev and shares else None
    nd_ps    = round(net_debt * 1_000_000 / shares, 4) if net_debt is not None and shares else None

    # ── Return on capital ─────────────────────────────────────
    # Average equity / assets for more accurate ratios
    te1 = bs_by_fy.get(fiscal_year - 1, {}).get("total_equity")
    ta1 = bs_by_fy.get(fiscal_year - 1, {}).get("total_assets")
    avg_te = (te + te1) / 2 if te and te1 else te
    avg_ta = (ta + ta1) / 2 if ta and ta1 else ta

    roe_v  = safe_pct(pat, avg_te)
    roa_v  = safe_pct(pat, avg_ta)
    roae_v = safe_pct(pat, avg_te)
    roaa_v = safe_pct(pat, avg_ta)

    # ROIC = EBIT*(1-t) / (equity + net_debt)
    tax_rate = safe_div(tax, pbt) if tax and pbt and pbt != 0 else 0.30
    nopat    = ebit_v * (1 - (tax_rate or 0.30)) if ebit_v else None
    inv_cap  = te + net_debt if te is not None and net_debt is not None else None
    roic_v   = safe_pct(nopat, inv_cap) if nopat and inv_cap and inv_cap != 0 else None

    # ROCE = EBIT / capital_employed (total_assets - current_liabilities)
    cap_emp  = (ta - cl) if ta and cl else None
    roce_v   = safe_pct(ebit_v, cap_emp) if ebit_v and cap_emp and cap_emp != 0 else None

    # Cash ROIC
    croic_v  = safe_pct(fcf, inv_cap) if fcf and inv_cap and inv_cap != 0 else None

    # ── Margins ───────────────────────────────────────────────
    gm     = safe_pct(gp,       rev)
    ebitda_m = safe_pct(ebitda_v, rev)
    ebit_m = safe_pct(ebit_v,   rev)
    ptm    = safe_pct(pbt,      rev)
    npm    = safe_pct(pat,      rev)
    ocf_m  = safe_pct(ocf,      rev)
    fcf_m  = safe_pct(fcf,      rev)
    eff_tax = safe_pct(tax, pbt) if tax and pbt and pbt != 0 else None

    # ── Efficiency ────────────────────────────────────────────
    at     = safe_ratio(rev, avg_ta)
    inv_t  = safe_ratio(rev, inv) if inv and inv > 0 else None    # using revenue as proxy for COGS
    rec_t  = safe_ratio(rev, rec) if rec and rec > 0 else None
    dso    = round(rec / rev * 365, 2) if rec and rev and rev > 0 else None
    dio    = round(inv / rev * 365, 2) if inv and rev and rev > 0 else None
    dpo    = round(pay / rev * 365, 2) if pay and rev and rev > 0 else None
    ccc    = round(dso + dio - dpo, 2) if dso and dio and dpo else None
    capex_i = safe_pct(capex, rev) if capex and rev else None

    # ── Leverage & Liquidity ──────────────────────────────────
    cr     = safe_ratio(ca,  cl)  if ca  and cl  and cl  > 0 else None
    qr     = safe_ratio((ca - (inv or 0)), cl) if ca and cl and cl > 0 else None
    cashr  = safe_ratio(cash_v, cl) if cash_v and cl and cl > 0 else None
    dte    = safe_ratio(td,  te)  if td  and te  and te  != 0 else None
    dta    = safe_ratio(td,  ta)  if td  and ta  else None
    dt_ebitda = safe_ratio(td, ebitda_v) if td and ebitda_v and ebitda_v > 0 else None
    nd_ebitda = safe_ratio(net_debt, ebitda_v) if net_debt is not None and ebitda_v and ebitda_v > 0 else None
    nd_te     = safe_ratio(net_debt, te) if net_debt is not None and te and te != 0 else None
    icr    = safe_ratio(ebit_v, int_exp) if ebit_v and int_exp and int_exp > 0 else None
    eq_mul = safe_ratio(ta, te)  if ta  and te  and te  != 0 else None
    ltd_cap = safe_ratio(ltd, (ltd + te)) if ltd and te and (ltd + te) != 0 else None

    # ── Quality scores ────────────────────────────────────────
    pnl1_row = pnl_by_fy.get(fiscal_year - 1) or {}
    bs1_row  = bs_by_fy.get(fiscal_year - 1) or {}
    cf1_row  = cf_by_fy.get(fiscal_year - 1) or {}
    f_score  = piotroski_score(pnl0, pnl1_row, bs0, bs1_row, cf0 or {})
    z_score  = altman_z(pnl0, bs0, market_cap)
    m_score  = beneish_m([
        {"pnl": pnl0, "bs": bs0},
        {"pnl": pnl1_row, "bs": bs1_row}
    ])

    # ── 1-Year YoY Growth ─────────────────────────────────────
    def yoy(curr, prev):
        if curr is None or prev is None or prev == 0:
            return None
        return round((curr - prev) / abs(prev) * 100, 4)

    rev_g1   = yoy(rev,      pnl1.get("revenue")     if pnl1 else None)
    gp_g1    = yoy(gp,       pnl1.get("gross_profit") if pnl1 else None)
    ebitda_g1= yoy(ebitda_v, pnl1.get("ebitda")      if pnl1 else None)
    ebit_g1  = yoy(ebit_v,   pnl1.get("ebit")        if pnl1 else None)
    pat_g1   = yoy(pat,      pnl1.get("net_profit")   if pnl1 else None)
    eps_g1   = yoy(eps,      pnl1.get("eps")          if pnl1 else None)
    ocf_g1   = yoy(ocf,      cf_by_fy.get(fiscal_year - 1, {}).get("cfo"))
    fcf_g1   = yoy(fcf,      cf_by_fy.get(fiscal_year - 1, {}).get("fcf"))
    bvps_g1  = yoy(bvps_v,   bs1.get("book_value_per_share") if bs1 else None)

    # ── Multi-year growth CAGRs ───────────────────────────────
    def rev_n(fy): return pnl_by_fy.get(fy, {}).get("revenue")
    def pat_n(fy): return pnl_by_fy.get(fy, {}).get("net_profit")
    def eps_n(fy): return pnl_by_fy.get(fy, {}).get("eps")
    def ebd_n(fy): return pnl_by_fy.get(fy, {}).get("ebitda")
    def fcf_n(fy): return cf_by_fy.get(fy, {}).get("fcf")
    def gp_n(fy):  return pnl_by_fy.get(fy, {}).get("gross_profit")
    def bv_n(fy):  return bs_by_fy.get(fy, {}).get("book_value_per_share")
    def dps_n(fy): return pnl_by_fy.get(fy, {}).get("dps")

    fy = fiscal_year

    # Revenue CAGRs
    rev_c3  = cagr(rev_n(fy), rev_n(fy-3),  3)
    rev_c5  = cagr(rev_n(fy), rev_n(fy-5),  5)
    rev_c7  = cagr(rev_n(fy), rev_n(fy-7),  7)
    rev_c10 = cagr(rev_n(fy), rev_n(fy-10), 10)

    # Median revenue growth
    rev_years = [(fy-i, rev_n(fy-i)) for i in range(6) if rev_n(fy-i)]
    rev_med5  = median_growth([(y, v) for y, v in rev_years if y >= fy-5])
    rev_years10 = [(fy-i, rev_n(fy-i)) for i in range(11) if rev_n(fy-i)]
    rev_med10 = median_growth(rev_years10)

    # Net income CAGRs
    pat_c3  = cagr(pat_n(fy), pat_n(fy-3),  3)
    pat_c5  = cagr(pat_n(fy), pat_n(fy-5),  5)
    pat_c7  = cagr(pat_n(fy), pat_n(fy-7),  7)
    pat_c10 = cagr(pat_n(fy), pat_n(fy-10), 10)

    # EPS CAGRs
    eps_c3  = cagr(eps_n(fy), eps_n(fy-3),  3)
    eps_c5  = cagr(eps_n(fy), eps_n(fy-5),  5)
    eps_c7  = cagr(eps_n(fy), eps_n(fy-7),  7)
    eps_c10 = cagr(eps_n(fy), eps_n(fy-10), 10)

    # EBITDA CAGRs
    ebd_c3  = cagr(ebd_n(fy), ebd_n(fy-3),  3)
    ebd_c5  = cagr(ebd_n(fy), ebd_n(fy-5),  5)
    ebd_c7  = cagr(ebd_n(fy), ebd_n(fy-7),  7)
    ebd_c10 = cagr(ebd_n(fy), ebd_n(fy-10), 10)

    # FCF CAGRs
    fcf_c3  = cagr(fcf_n(fy), fcf_n(fy-3), 3)
    fcf_c5  = cagr(fcf_n(fy), fcf_n(fy-5), 5)

    # Gross profit CAGRs
    gp_c3   = cagr(gp_n(fy),  gp_n(fy-3),  3)
    gp_c5   = cagr(gp_n(fy),  gp_n(fy-5),  5)

    # BVPS CAGRs
    bv_c3   = cagr(bv_n(fy),  bv_n(fy-3),  3)
    bv_c5   = cagr(bv_n(fy),  bv_n(fy-5),  5)

    # Dividend CAGRs
    dps_c3  = cagr(dps_n(fy), dps_n(fy-3), 3)
    dps_c5  = cagr(dps_n(fy), dps_n(fy-5), 5)

    # Price CAGRs — use historical price at each FY end
    def price_at(n_years_ago):
        target_fy = fy - n_years_ago
        row = pnl_by_fy.get(target_fy)
        if not row:
            return None
        return get_price_on_or_before(price_history, row["period_end_date"])

    curr_price = price
    p_c1  = cagr(curr_price, price_at(1),  1)
    p_c3  = cagr(curr_price, price_at(3),  3)
    p_c5  = cagr(curr_price, price_at(5),  5)
    p_c7  = cagr(curr_price, price_at(7),  7)
    p_c10 = cagr(curr_price, price_at(10), 10)

    # ── Multi-year averages ────────────────────────────────────
    def avg_metric(fn, n_years):
        vals = [fn(fy-i) for i in range(n_years) if fn(fy-i) is not None]
        return round(statistics.mean(vals), 4) if vals else None

    def roe_for_fy(y):
        p = pnl_by_fy.get(y, {}).get("net_profit")
        e = bs_by_fy.get(y, {}).get("total_equity")
        return safe_pct(p, e)

    def roa_for_fy(y):
        p = pnl_by_fy.get(y, {}).get("net_profit")
        a = bs_by_fy.get(y, {}).get("total_assets")
        return safe_pct(p, a)

    def roic_for_fy(y):
        e_v = pnl_by_fy.get(y, {}).get("ebit")
        te_v = bs_by_fy.get(y, {}).get("total_equity")
        nd_v = bs_by_fy.get(y, {}).get("net_debt")
        ic = te_v + nd_v if te_v is not None and nd_v is not None else None
        return safe_pct(e_v, ic) if ic and ic != 0 else None

    def roce_for_fy(y):
        e_v = pnl_by_fy.get(y, {}).get("ebit")
        ta_v = bs_by_fy.get(y, {}).get("total_assets")
        cl_v = bs_by_fy.get(y, {}).get("total_current_liab")
        ce = (ta_v - cl_v) if ta_v and cl_v else None
        return safe_pct(e_v, ce) if ce and ce != 0 else None

    def margin_for_fy(y, field):
        num = pnl_by_fy.get(y, {}).get(field)
        den = pnl_by_fy.get(y, {}).get("revenue")
        return safe_pct(num, den)

    def eps_growth_for_fy(y):
        e0 = pnl_by_fy.get(y, {}).get("eps")
        e1 = pnl_by_fy.get(y-1, {}).get("eps")
        return yoy(e0, e1)

    avg_roe3  = avg_metric(roe_for_fy,  3)
    avg_roe5  = avg_metric(roe_for_fy,  5)
    avg_roe7  = avg_metric(roe_for_fy,  7)
    avg_roe10 = avg_metric(roe_for_fy, 10)
    avg_roa3  = avg_metric(roa_for_fy,  3)
    avg_roa5  = avg_metric(roa_for_fy,  5)
    avg_roic3 = avg_metric(roic_for_fy, 3)
    avg_roic5 = avg_metric(roic_for_fy, 5)
    avg_roce3 = avg_metric(roce_for_fy, 3)
    avg_roce5 = avg_metric(roce_for_fy, 5)
    avg_roce7 = avg_metric(roce_for_fy, 7)
    avg_roce10= avg_metric(roce_for_fy, 10)

    avg_gm3   = avg_metric(lambda y: margin_for_fy(y, "gross_profit"),   3)
    avg_gm5   = avg_metric(lambda y: margin_for_fy(y, "gross_profit"),   5)
    avg_ebd_m3= avg_metric(lambda y: margin_for_fy(y, "ebitda"),         3)
    avg_ebd_m5= avg_metric(lambda y: margin_for_fy(y, "ebitda"),         5)
    avg_opm3  = avg_metric(lambda y: margin_for_fy(y, "ebit"),           3)
    avg_opm5  = avg_metric(lambda y: margin_for_fy(y, "ebit"),           5)
    avg_opm10 = avg_metric(lambda y: margin_for_fy(y, "ebit"),          10)
    avg_npm3  = avg_metric(lambda y: margin_for_fy(y, "net_profit"),     3)
    avg_npm5  = avg_metric(lambda y: margin_for_fy(y, "net_profit"),     5)
    avg_npm10 = avg_metric(lambda y: margin_for_fy(y, "net_profit"),    10)

    def fcf_margin_for_fy(y):
        f = cf_by_fy.get(y, {}).get("fcf")
        r = pnl_by_fy.get(y, {}).get("revenue")
        return safe_pct(f, r)

    avg_fcfm3 = avg_metric(fcf_margin_for_fy, 3)
    avg_fcfm5 = avg_metric(fcf_margin_for_fy, 5)

    avg_epsg3 = avg_metric(eps_growth_for_fy, 3)
    avg_epsg5 = avg_metric(eps_growth_for_fy, 5)
    avg_epsg10= avg_metric(eps_growth_for_fy, 10)
    avg_cr3   = avg_metric(lambda y: safe_ratio(
        bs_by_fy.get(y, {}).get("total_current_assets"),
        bs_by_fy.get(y, {}).get("total_current_liab") or None), 3)

    # Average EBIT value (AUD millions)
    avg_ebit5_val  = avg_metric(lambda y: pnl_by_fy.get(y, {}).get("ebit"),  5)
    avg_ebit10_val = avg_metric(lambda y: pnl_by_fy.get(y, {}).get("ebit"), 10)

    # ── Risk metrics ──────────────────────────────────────────
    vol_1y = annualised_vol(price_history, 1)
    vol_3y = annualised_vol(price_history, 3)
    beta1y = compute_beta(cur, asx_code, xjo_history, 1)
    beta3y = compute_beta(cur, asx_code, xjo_history, 3)
    beta5y = compute_beta(cur, asx_code, xjo_history, 5)

    # Sharpe: (annual return - RFR) / volatility
    ann_ret_1y = p_c1 / 100 if p_c1 else None
    sharpe_1y_v = round((ann_ret_1y - RFR) / (vol_1y / 100), 4) \
        if ann_ret_1y is not None and vol_1y else None

    ann_ret_3y = ((p_c3 / 100 + 1) ** (1/3) - 1) if p_c3 else None
    sharpe_3y_v = round((ann_ret_3y - RFR) / (vol_3y / 100), 4) \
        if ann_ret_3y is not None and vol_3y else None

    # ── PEG ratio ─────────────────────────────────────────────
    peg_v = safe_ratio(pe, eps_g1) if pe and eps_g1 and eps_g1 > 0 else None

    # ── Dividend consecutive years ─────────────────────────────
    consec_div = 0
    for y in range(fy, fy - 25, -1):
        d = pnl_by_fy.get(y, {}).get("dps")
        if d and d > 0:
            consec_div += 1
        else:
            break

    # ─────────────────────────────────────────────────────────
    #  Assemble result dict
    # ─────────────────────────────────────────────────────────
    return {
        "asx_code":             asx_code,
        "fiscal_year":          fiscal_year,
        "period_end_date":      period_end,
        "price_at_compute":     price,

        # Market
        "market_cap":           market_cap,
        "enterprise_value":     ev,
        "shares_outstanding":   shares,

        # Valuation
        "pe_ratio":             pe,
        "pb_ratio":             pb,
        "ps_ratio":             ps,
        "pcf_ratio":            pcf,
        "p_fcf_ratio":          pfcf,
        "ev_ebitda":            ev_ebitda,
        "ev_ebit":              ev_ebit,
        "ev_revenue":           ev_rev,
        "ev_fcf":               ev_fcf,
        "peg_ratio":            peg_v,
        "earnings_yield":       earn_yld,
        "fcf_yield":            fcf_yld,
        "graham_number":        graham,

        # Per share
        "eps":                  eps,
        "eps_diluted":          pnl0.get("eps_diluted"),
        "bvps":                 bvps_v,
        "tbvps":                tbvps_v,
        "dps":                  dps,
        "dps_grossed_up":       round(gross_up, 4) if gross_up else None,
        "franking_pct":         frank,
        "fcf_per_share":        fcf_ps,
        "ocf_per_share":        ocf_ps,
        "revenue_per_share":    rev_ps,
        "net_debt_per_share":   nd_ps,

        # Dividends
        "dividend_yield":       div_yld,
        "franked_yield":        frnk_yld,
        "payout_ratio":         payout,
        "dividend_cagr_3y":     dps_c3,
        "dividend_cagr_5y":     dps_c5,
        "dividend_consecutive_yrs": consec_div,

        # Return on capital
        "roe":                  roe_v,
        "roa":                  roa_v,
        "roic":                 roic_v,
        "roce":                 roce_v,
        "roae":                 roae_v,
        "roaa":                 roaa_v,
        "croic":                croic_v,

        # Margins
        "gross_margin":         gm,
        "ebitda_margin":        ebitda_m,
        "ebit_margin":          ebit_m,
        "pretax_margin":        ptm,
        "net_margin":           npm,
        "ocf_margin":           ocf_m,
        "fcf_margin":           fcf_m,
        "tax_rate_effective":   eff_tax,

        # Efficiency
        "asset_turnover":       at,
        "inventory_turnover":   inv_t,
        "receivables_turnover": rec_t,
        "receivables_days":     dso,
        "inventory_days":       dio,
        "payables_days":        dpo,
        "cash_conversion_cycle": ccc,
        "capex_intensity":      capex_i,

        # Leverage
        "current_ratio":        cr,
        "quick_ratio":          qr,
        "cash_ratio":           cashr,
        "debt_to_equity":       dte,
        "debt_to_assets":       dta,
        "debt_to_ebitda":       dt_ebitda,
        "net_debt_to_ebitda":   nd_ebitda,
        "net_debt_to_equity":   nd_te,
        "interest_coverage":    icr,
        "equity_multiplier":    eq_mul,
        "lt_debt_to_capital":   ltd_cap,

        # Quality
        "piotroski_f_score":    f_score,
        "altman_z_score":       z_score,
        "beneish_m_score":      m_score,

        # 1Y growth
        "revenue_growth_1y":    rev_g1,
        "gross_profit_growth_1y": gp_g1,
        "ebitda_growth_1y":     ebitda_g1,
        "ebit_growth_1y":       ebit_g1,
        "net_income_growth_1y": pat_g1,
        "eps_growth_1y":        eps_g1,
        "ocf_growth_1y":        ocf_g1,
        "fcf_growth_1y":        fcf_g1,
        "bvps_growth_1y":       bvps_g1,

        # Multi-year growth CAGRs
        "revenue_cagr_3y":      rev_c3,
        "revenue_cagr_5y":      rev_c5,
        "revenue_cagr_7y":      rev_c7,
        "revenue_cagr_10y":     rev_c10,
        "revenue_growth_median_5y":  rev_med5,
        "revenue_growth_median_10y": rev_med10,
        "net_income_cagr_3y":   pat_c3,
        "net_income_cagr_5y":   pat_c5,
        "net_income_cagr_7y":   pat_c7,
        "net_income_cagr_10y":  pat_c10,
        "eps_cagr_3y":          eps_c3,
        "eps_cagr_5y":          eps_c5,
        "eps_cagr_7y":          eps_c7,
        "eps_cagr_10y":         eps_c10,
        "ebitda_cagr_3y":       ebd_c3,
        "ebitda_cagr_5y":       ebd_c5,
        "ebitda_cagr_7y":       ebd_c7,
        "ebitda_cagr_10y":      ebd_c10,
        "fcf_cagr_3y":          fcf_c3,
        "fcf_cagr_5y":          fcf_c5,
        "gross_profit_cagr_3y": gp_c3,
        "gross_profit_cagr_5y": gp_c5,
        "bvps_cagr_3y":         bv_c3,
        "bvps_cagr_5y":         bv_c5,

        # Price CAGRs
        "price_cagr_1y":        p_c1,
        "price_cagr_3y":        p_c3,
        "price_cagr_5y":        p_c5,
        "price_cagr_7y":        p_c7,
        "price_cagr_10y":       p_c10,

        # Multi-year averages
        "avg_roe_3y":           avg_roe3,
        "avg_roe_5y":           avg_roe5,
        "avg_roe_7y":           avg_roe7,
        "avg_roe_10y":          avg_roe10,
        "avg_roa_3y":           avg_roa3,
        "avg_roa_5y":           avg_roa5,
        "avg_roic_3y":          avg_roic3,
        "avg_roic_5y":          avg_roic5,
        "avg_roce_3y":          avg_roce3,
        "avg_roce_5y":          avg_roce5,
        "avg_roce_7y":          avg_roce7,
        "avg_roce_10y":         avg_roce10,
        "avg_gross_margin_3y":  avg_gm3,
        "avg_gross_margin_5y":  avg_gm5,
        "avg_ebitda_margin_3y": avg_ebd_m3,
        "avg_ebitda_margin_5y": avg_ebd_m5,
        "avg_operating_margin_3y": avg_opm3,
        "avg_operating_margin_5y": avg_opm5,
        "avg_operating_margin_10y": avg_opm10,
        "avg_net_margin_3y":    avg_npm3,
        "avg_net_margin_5y":    avg_npm5,
        "avg_net_margin_10y":   avg_npm10,
        "avg_fcf_margin_3y":    avg_fcfm3,
        "avg_fcf_margin_5y":    avg_fcfm5,
        "avg_eps_growth_3y":    avg_epsg3,
        "avg_eps_growth_5y":    avg_epsg5,
        "avg_eps_growth_10y":   avg_epsg10,
        "avg_current_ratio_3y": avg_cr3,
        "avg_ebit_5y":          avg_ebit5_val,
        "avg_ebit_10y":         avg_ebit10_val,

        # Risk
        "beta_1y":              beta1y,
        "beta_3y":              beta3y,
        "beta_5y":              beta5y,
        "volatility_1y":        vol_1y,
        "volatility_3y":        vol_3y,
        "sharpe_1y":            sharpe_1y_v,
        "sharpe_3y":            sharpe_3y_v,

        # Metadata
        "compute_version":      COMPUTE_VERSION,
        "computed_at":          datetime.utcnow(),
    }


# ─────────────────────────────────────────────────────────────
#  Upsert
# ─────────────────────────────────────────────────────────────

UPSERT_SQL = """
INSERT INTO market.yearly_metrics ({cols})
VALUES ({placeholders})
ON CONFLICT (asx_code, fiscal_year) DO UPDATE SET
    {updates},
    computed_at = EXCLUDED.computed_at
"""


def upsert_yearly(cur, rows: list[dict]) -> int:
    if not rows:
        return 0
    cols   = list(rows[0].keys())
    values = [[r.get(c) for c in cols] for r in rows]
    ph     = ", ".join(["%s"] * len(cols))
    upd    = ", ".join([f"{c} = EXCLUDED.{c}" for c in cols
                        if c not in ("asx_code", "fiscal_year")])
    sql    = f"""
        INSERT INTO market.yearly_metrics ({', '.join(cols)})
        VALUES %s
        ON CONFLICT (asx_code, fiscal_year) DO UPDATE SET {upd}
    """
    execute_values(cur, sql, values, page_size=200)
    return len(rows)


# ─────────────────────────────────────────────────────────────
#  XJO benchmark history (ASX 200 index proxy via ^AXJO)
# ─────────────────────────────────────────────────────────────

def fetch_xjo_history(cur) -> list[tuple]:
    """Fetch ASX 200 index history — stored as asx_code='XJO' in daily_prices."""
    cur.execute("""
        SELECT time::date AS dt, adjusted_close
        FROM market.daily_prices
        WHERE asx_code = 'XJO' AND adjusted_close IS NOT NULL
        ORDER BY time ASC
    """)
    rows = cur.fetchall()
    if not rows:
        log.warning("XJO benchmark data not found — beta/alpha will be NULL")
    return [(r["dt"], float(r["adjusted_close"])) for r in rows]


# ─────────────────────────────────────────────────────────────
#  Main
# ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--codes",     nargs="+", help="Specific ASX codes")
    parser.add_argument("--fy",        type=int,  help="Specific fiscal year")
    parser.add_argument("--from-code", help="Resume from this ASX code")
    parser.add_argument("--mode",      choices=["latest", "historical"],
                        default="latest",
                        help="latest=current FY only, historical=all FYs")
    args = parser.parse_args()

    conn = psycopg2.connect(DB_URL)
    conn.autocommit = False
    cur  = conn.cursor(cursor_factory=RealDictCursor)

    # Load XJO benchmark for beta calculation
    xjo_history = fetch_xjo_history(cur)

    # Get stock list
    if args.codes:
        codes = [c.upper() for c in args.codes]
    else:
        cur.execute("""
            SELECT DISTINCT asx_code FROM financials.annual_pnl
            ORDER BY asx_code
        """)
        codes = [r["asx_code"] for r in cur.fetchall()]

    if args.from_code:
        codes = [c for c in codes if c >= args.from_code.upper()]

    total = len(codes)
    log.info(f"compute_yearly.py — {total} stocks, mode={args.mode}")

    done = failed = rows_written = 0

    for i, asx_code in enumerate(codes, 1):
        try:
            pnl_rows = fetch_all_pnl(cur, asx_code)
            bs_rows  = fetch_all_bs(cur, asx_code)
            cf_rows  = fetch_all_cf(cur, asx_code)
            price_h  = fetch_price_history(cur, asx_code)

            if not pnl_rows:
                failed += 1
                continue

            # Determine fiscal years to compute
            all_fys = sorted({r["fiscal_year"] for r in pnl_rows}, reverse=True)
            if args.fy:
                fys_to_compute = [args.fy]
            elif args.mode == "historical":
                fys_to_compute = all_fys
            else:
                fys_to_compute = [all_fys[0]] if all_fys else []

            batch = []
            for fy in fys_to_compute:
                row = compute_for_fy(
                    asx_code, fy,
                    pnl_rows, bs_rows, cf_rows,
                    price_h, xjo_history, cur
                )
                if row:
                    batch.append(row)

            if batch:
                upsert_yearly(cur, batch)
                rows_written += len(batch)
                done += 1
            else:
                failed += 1

        except Exception as e:
            conn.rollback()
            failed += 1
            log.warning(f"  {asx_code}: {e}")
            continue

        if i % 100 == 0:
            conn.commit()
            log.info(f"  [{i:4d}/{total}] {done} done, {failed} failed | "
                     f"{rows_written:,} rows written")

        time.sleep(SLEEP_SEC)

    conn.commit()
    cur.close()
    conn.close()
    log.info(f"DONE — {done} stocks, {rows_written:,} rows. Failed: {failed}")


if __name__ == "__main__":
    main()
