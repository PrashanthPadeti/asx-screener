"""
ASX Screener — Yearly Compute Engine
======================================
Computes per-fiscal-year metrics for all ASX stocks.

Sources (no API calls — pure computation):
  financials.annual_pnl           → income / margins / EPS / DPS
  financials.annual_balance_sheet → assets / liabilities / equity
  financials.annual_cashflow      → CFO / capex / FCF
  market.daily_prices             → price at period_end for PE/PB,
                                    Sharpe 1y, max drawdown
                                    (fetched ONCE per stock, all lookups in-memory)

Output: market.yearly_metrics (one row per asx_code per fiscal_year)

Metrics computed:
  - Profitability         ROE, ROA, ROCE, ROIC, margins (gross/EBITDA/EBIT/net/OCF/FCF)
  - Efficiency            asset turnover, receivables days, capex intensity
  - Leverage & liquidity  D/E, current ratio, net debt/EBITDA, interest coverage
  - Per share             EPS, DPS, BVPS, FCF/share; valuation: PE, PB, PS, EV/EBITDA
  - Dividend              yield, payout ratio, CAGR 3y/5y, consecutive uninterrupted years
  - YoY growth            revenue, gross profit, EBITDA, net income, EPS, FCF, BVPS
  - Multi-year CAGRs      revenue/EPS/NI/EBITDA/FCF — 3y, 5y, 7y, 10y
  - Rolling averages      ROE, ROA, ROCE, margins — 3y, 5y
  - Quality scores        Piotroski F-score (0–9), Altman Z-score
  - Risk & performance    Sharpe 1y, max drawdown 1y, annualised vol 1y
                          (beta skipped — needs market index)

Usage:
    python compute/engine/yearly_compute.py
    python compute/engine/yearly_compute.py --codes BHP CBA
    python compute/engine/yearly_compute.py --limit 20
    python compute/engine/yearly_compute.py --min-year 2020
"""

import os
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

COMPUTE_VERSION = "1.0.0"
BATCH_COMMIT    = 50
RISK_FREE_RATE  = 0.04    # 4% — approximate Australian cash rate for Sharpe


# ── Safe helpers ──────────────────────────────────────────────────────────────

def _v(val):
    """Return Python float/int/None; coerce numpy scalars and NaN to None."""
    if val is None:
        return None
    if isinstance(val, (bool, np.bool_)):
        return bool(val)
    if isinstance(val, (np.integer,)):
        return int(val)
    if isinstance(val, (np.floating,)):
        return None if np.isnan(val) else float(val)
    if isinstance(val, float):
        return None if np.isnan(val) else val
    return val


def _f(val) -> Optional[float]:
    """Safe float: returns None for None/NaN, float otherwise."""
    v = _v(val)
    return float(v) if v is not None else None


def _div(num, den, dp=4) -> Optional[float]:
    """num / den, rounded. Returns None on zero/None/NaN denominator."""
    n, d = _f(num), _f(den)
    if n is None or d is None or d == 0:
        return None
    try:
        result = n / d
        return round(result, dp) if np.isfinite(result) else None
    except Exception:
        return None


def _cagr(end_val, start_val, years: int) -> Optional[float]:
    """Compound Annual Growth Rate. Returns None on invalid inputs."""
    e, s = _f(end_val), _f(start_val)
    if e is None or s is None or years <= 0 or s == 0:
        return None
    if s < 0 and e < 0:
        result = (abs(e) / abs(s)) ** (1 / years) - 1
    elif s < 0 or e < 0:
        return None
    else:
        result = (e / s) ** (1 / years) - 1
    return round(result, 6) if np.isfinite(result) else None


def _avg(values: list, n: int) -> Optional[float]:
    """Mean of last n non-None values from a list."""
    vals = [_f(v) for v in values[-n:]]
    vals = [v for v in vals if v is not None]
    return round(sum(vals) / len(vals), 4) if vals else None


# ── Data Fetchers ─────────────────────────────────────────────────────────────

def fetch_codes(cur, codes=None, limit=None) -> list:
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
    """One row per fiscal_year — pnl + balance_sheet + cashflow joined.

    Notes on data gaps (EODHD ASX feed):
      - annual_pnl.eps / dps / shares_outstanding are NULL for all stocks —
        EODHD does not provide per-share data in the income statement endpoint.
      - DPS is derived here by summing market.dividends for the 12-month
        window ending on period_end_date (ex_date basis).
      - EPS is derived later in build_yearly_rows using current_shares proxy.
    """
    cur.execute("""
        SELECT
            p.fiscal_year,
            p.period_end_date,
            p.revenue,      p.gross_profit,  p.ebitda,
            p.ebit,         p.interest_expense,
            p.net_profit,   p.eps,           p.eps_diluted,
            p.dps,          p.dps_franking_pct,
            p.gpm,          p.opm,           p.npm,   p.ebitda_margin,
            b.total_assets,       b.total_equity,
            b.total_current_assets, b.total_current_liab,
            b.total_debt,         b.net_debt,
            b.cash_equivalents,   b.long_term_debt,
            b.retained_earnings,  b.working_capital,
            b.book_value_per_share, b.shares_outstanding,
            b.trade_receivables,  b.inventory,
            cf.cfo,   cf.capex,  cf.fcf,
            cf.equity_raised, cf.cfi,
            -- Derive DPS from market.dividends (12-month window per FY)
            COALESCE(div.total_dps, p.dps)  AS derived_dps,
            div.avg_franking_pct            AS derived_franking_pct
        FROM financials.annual_pnl p
        LEFT JOIN financials.annual_balance_sheet b
               ON b.asx_code = p.asx_code AND b.fiscal_year = p.fiscal_year
        LEFT JOIN financials.annual_cashflow cf
               ON cf.asx_code = p.asx_code AND cf.fiscal_year = p.fiscal_year
        LEFT JOIN LATERAL (
            SELECT
                SUM(d.amount_per_share)           AS total_dps,
                AVG(d.franking_pct)               AS avg_franking_pct
            FROM market.dividends d
            WHERE d.asx_code = p.asx_code
              AND d.ex_date >  p.period_end_date - INTERVAL '1 year'
              AND d.ex_date <= p.period_end_date
              AND LOWER(d.dividend_type) NOT LIKE '%special%'
        ) div ON TRUE
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
        "trade_receivables", "inventory",
        "cfo", "capex", "fcf", "equity_raised", "cfi",
        "derived_dps", "derived_franking_pct",
    ]
    df = pd.DataFrame(rows, columns=cols)
    df["period_end_date"] = pd.to_datetime(df["period_end_date"])
    return df


def fetch_current_shares(cur, asx_code: str) -> Optional[float]:
    """
    Fetch current shares outstanding from staging.shares_stats.
    Used as a proxy for historical per-share calculations when
    EODHD does not provide per-share data in the income statement.
    """
    cur.execute("""
        SELECT shares_outstanding
        FROM staging.shares_stats
        WHERE asx_code = %s
        LIMIT 1
    """, [asx_code])
    row = cur.fetchone()
    return float(row[0]) if row and row[0] is not None else None


def fetch_all_prices(cur, asx_code: str) -> pd.Series:
    """
    Fetch ALL daily closing prices for a stock in a SINGLE query.
    Returns pd.Series indexed by date (pd.Timestamp).
    Used for all price lookups per fiscal year without re-querying.
    """
    cur.execute("""
        SELECT
            DATE(time AT TIME ZONE 'Australia/Sydney') AS day,
            close
        FROM market.daily_prices
        WHERE asx_code = %s
        ORDER BY time ASC
    """, [asx_code])
    rows = cur.fetchall()
    if not rows:
        return pd.Series(dtype=float)

    dates  = pd.to_datetime([r[0] for r in rows])
    closes = [float(r[1]) if r[1] is not None else np.nan for r in rows]
    return pd.Series(closes, index=dates, name="close").dropna()


def price_at(prices: pd.Series, target_date) -> Optional[float]:
    """Last close on or before target_date from pre-fetched Series."""
    if prices.empty:
        return None
    tgt = pd.Timestamp(target_date)
    subset = prices[prices.index <= tgt]
    return float(subset.iloc[-1]) if not subset.empty else None


def price_window(prices: pd.Series, period_end) -> pd.Series:
    """Daily closes for 12 months ending period_end."""
    end   = pd.Timestamp(period_end)
    start = end - pd.DateOffset(years=1)
    return prices[(prices.index >= start) & (prices.index <= end)]


def price_return(prices: pd.Series, end_date, years: int) -> Optional[float]:
    """Total price return over N years ending at end_date.
    Uses pre-fetched prices Series — no DB query."""
    p_end   = price_at(prices, end_date)
    start   = pd.Timestamp(end_date) - pd.DateOffset(years=years)
    p_start = price_at(prices, start)
    if p_end is None or p_start is None or p_start == 0:
        return None
    result = (p_end - p_start) / abs(p_start)
    return round(result, 6) if np.isfinite(result) else None


# ── Quality Scores ────────────────────────────────────────────────────────────

def piotroski_f_score(row: dict, prev: Optional[dict]) -> Optional[int]:
    ta = _f(row.get("total_assets"))
    if ta is None or ta == 0:
        return None

    score = 0
    p = prev or {}

    roa_cur  = _div(row.get("net_profit"), ta)
    roa_prev = _div(p.get("net_profit"),   p.get("total_assets"))
    cfo_cur  = _f(row.get("cfo"))

    if roa_cur  is not None and roa_cur > 0:                    score += 1  # F1
    if cfo_cur  is not None and cfo_cur > 0:                    score += 1  # F2
    if roa_cur  is not None and roa_prev is not None and roa_cur > roa_prev:
                                                                 score += 1  # F3
    cfo_assets = _div(cfo_cur, ta)
    if cfo_assets is not None and roa_cur is not None and cfo_assets > roa_cur:
                                                                 score += 1  # F4

    ltd_cur  = _div(row.get("long_term_debt"), ta)
    ltd_prev = _div(p.get("long_term_debt"),   p.get("total_assets"))
    cr_cur   = _div(row.get("total_current_assets"), row.get("total_current_liab"))
    cr_prev  = _div(p.get("total_current_assets"),   p.get("total_current_liab"))
    eq_raised = _f(row.get("equity_raised"))

    if ltd_cur is not None and ltd_prev is not None and ltd_cur < ltd_prev:
                                                                 score += 1  # F5
    if cr_cur is not None and cr_prev is not None and cr_cur > cr_prev:
                                                                 score += 1  # F6
    if eq_raised is not None and eq_raised <= 0:                 score += 1  # F7

    gm_cur  = _f(row.get("gpm"))
    gm_prev = _f(p.get("gpm"))
    at_cur  = _div(row.get("revenue"), ta)
    at_prev = _div(p.get("revenue"),   p.get("total_assets"))

    if gm_cur is not None and gm_prev is not None and gm_cur > gm_prev:
                                                                 score += 1  # F8
    if at_cur is not None and at_prev is not None and at_cur > at_prev:
                                                                 score += 1  # F9
    return score


def altman_z_score(row: dict, market_cap: Optional[float]) -> Optional[float]:
    ta   = _f(row.get("total_assets"))
    wc   = _f(row.get("working_capital"))
    re   = _f(row.get("retained_earnings"))
    ebit = _f(row.get("ebit"))
    rev  = _f(row.get("revenue"))
    td   = _f(row.get("total_debt"))
    te   = _f(row.get("total_equity"))

    if any(v is None for v in [ta, wc, re, ebit, rev]) or ta == 0:
        return None

    x1 = wc   / ta
    x2 = re   / ta
    x3 = ebit / ta
    x5 = rev  / ta

    if market_cap is not None and td is not None and td > 0:
        x4 = market_cap / td
    elif te is not None and td is not None and td > 0:
        x4 = te / td
    else:
        x4 = 0.0

    z = 1.2*x1 + 1.4*x2 + 3.3*x3 + 0.6*x4 + 1.0*x5
    return round(z, 4) if np.isfinite(z) else None


def sharpe_drawdown_vol(prices: pd.Series):
    """Returns (sharpe_1y, max_drawdown_1y, volatility_1y) or (None, None, None)."""
    if len(prices) < 20:
        return None, None, None
    rets = prices.pct_change().dropna()
    if rets.empty:
        return None, None, None

    ann_vol = float(rets.std() * np.sqrt(252))
    ann_ret = float(prices.iloc[-1] / prices.iloc[0]) - 1
    sharpe  = round((ann_ret - RISK_FREE_RATE) / ann_vol, 4) if ann_vol > 0 else None

    cum_max = prices.cummax()
    max_dd  = round(float(((prices - cum_max) / cum_max).min()), 4)
    return sharpe, max_dd, round(ann_vol, 4)


def consecutive_div_years(df: pd.DataFrame) -> int:
    count = 0
    for _, row in df.sort_values("fiscal_year", ascending=False).iterrows():
        d = _f(row.get("dps"))
        if d is not None and d > 0:
            count += 1
        else:
            break
    return count


# ── Row Builder ───────────────────────────────────────────────────────────────

def build_yearly_rows(asx_code: str, fin: pd.DataFrame,
                      prices: pd.Series,
                      current_shares: Optional[float] = None) -> list[tuple]:
    """
    For each fiscal_year row, compute all metrics.
    prices:         full daily close history fetched once by caller.
    current_shares: fallback shares count (from staging.shares_stats) used
                    when annual_balance_sheet.shares_outstanding is NULL —
                    EODHD does not provide per-share data for ASX income
                    statements, so we approximate EPS from net_profit / shares.
    """
    if fin.empty:
        return []

    fin    = fin.reset_index(drop=True)
    yearly = fin.to_dict("records")
    now    = datetime.now(tz=timezone.utc)
    rows   = []

    # Rolling lists (chronological order)
    roe_l = []; roa_l  = []; roce_l = []
    gm_l  = []; em_l   = []; om_l   = []; nm_l = []
    epsg_l = []

    for i, row in enumerate(yearly):
        fy  = int(row["fiscal_year"])
        ped = row["period_end_date"]

        # Ensure ped is a valid Timestamp
        if pd.isna(ped):
            continue
        ped = pd.Timestamp(ped)

        prev = yearly[i - 1] if i > 0 else None

        # ── Raw values (safe floats) ───────────────────────────────────────
        ta     = _f(row.get("total_assets"))
        te     = _f(row.get("total_equity"))
        rev    = _f(row.get("revenue"))
        ebit   = _f(row.get("ebit"))
        ebitda = _f(row.get("ebitda"))
        ni     = _f(row.get("net_profit"))
        cfo    = _f(row.get("cfo"))
        capex  = _f(row.get("capex"))
        fcf    = _f(row.get("fcf"))
        # Prefer derived_dps (summed from market.dividends) over raw dps
        # which is NULL in EODHD's ASX income statement feed
        dps    = _f(row.get("derived_dps")) or _f(row.get("dps"))
        fpc_raw = _f(row.get("derived_franking_pct")) or _f(row.get("dps_franking_pct"))
        # Write back derived dps so div_cagr can find prior year values
        if dps is not None:
            yearly[i]["dps"] = dps
        eps    = _f(row.get("eps"))
        bvps   = _f(row.get("book_value_per_share"))
        td     = _f(row.get("total_debt"))
        nd     = _f(row.get("net_debt"))
        shares = _f(row.get("shares_outstanding"))
        tca    = _f(row.get("total_current_assets"))
        tcl    = _f(row.get("total_current_liab"))
        ltd    = _f(row.get("long_term_debt"))
        rec    = _f(row.get("trade_receivables"))
        inv    = _f(row.get("inventory"))
        fpc    = fpc_raw  # already set above from derived_franking_pct or dps_franking_pct

        # ── Shares fallback (EODHD omits shares from balance sheet) ──────
        if shares is None and current_shares is not None:
            shares = current_shares

        # ── Derive EPS from net income / shares ───────────────────────────
        # ni in AUD millions; shares in actual count → EPS in AUD per share.
        # Uses current_shares as proxy when historical shares unavailable —
        # approximate but enables EPS CAGR for most stable-cap stocks.
        if eps is None and ni is not None and shares is not None and shares > 0:
            eps = round(ni / (shares / 1_000_000), 4)
        # Write back so cn("eps", N) can find derived value for prior rows
        if eps is not None:
            yearly[i]["eps"] = eps

        # Stored margins (preferred) or compute from P&L
        gross_margin  = _f(row.get("gpm"))   or _div(row.get("gross_profit"), rev)
        ebitda_margin = _f(row.get("ebitda_margin")) or _div(ebitda, rev)
        ebit_margin   = _f(row.get("opm"))   or _div(ebit, rev)
        net_margin    = _f(row.get("npm"))   or _div(ni, rev)
        ocf_margin    = _div(cfo, rev)
        fcf_margin    = _div(fcf, rev)

        # ── Price at fiscal year end (in-memory lookup) ────────────────────
        px = price_at(prices, ped)
        mc = round(px * shares / 1e6, 2) if (px and shares) else None

        # ── Profitability ──────────────────────────────────────────────────
        p_ta = _f(prev.get("total_assets")) if prev else None
        p_te = _f(prev.get("total_equity")) if prev else None
        avg_assets = ((ta + p_ta) / 2 if (ta is not None and p_ta is not None) else ta)
        avg_equity = ((te + p_te) / 2 if (te is not None and p_te is not None) else te)

        roe  = _div(ni, avg_equity)
        roa  = _div(ni, avg_assets)
        cap_emp = ((ta - tcl) if (ta is not None and tcl is not None) else None)
        roce = _div(ebit, cap_emp)
        ic   = ((te + nd) if (te is not None and nd is not None) else None)
        roic = _div(ni, ic)

        # ── Efficiency ────────────────────────────────────────────────────
        asset_turn = _div(rev, avg_assets)
        rec_turn   = _div(rev, rec)
        rec_days   = round(365 / rec_turn, 2) if (rec_turn and rec_turn > 0) else None
        capex_int  = _div(abs(capex) if capex is not None else None, rev)

        # ── Leverage & liquidity ──────────────────────────────────────────
        cr       = _div(tca, tcl)
        de       = _div(td, te)
        da       = _div(td, ta)
        nd_eb    = _div(nd, ebitda)
        int_cov  = _div(ebit, row.get("interest_expense"))
        ltd_plus_te = ((ltd + te) if (ltd is not None and te is not None) else None)
        lt_d_cap = _div(ltd, ltd_plus_te)

        # ── Per share & valuation ─────────────────────────────────────────
        ev = round(mc + nd, 2) if (mc is not None and nd is not None) else None
        pe        = _div(px,  eps)
        pb        = _div(px,  bvps)
        ps        = _div(mc,  rev)
        ev_eb     = _div(ev,  ebitda)
        ev_ebit   = _div(ev,  ebit)
        ev_rev    = _div(ev,  rev)
        fcf_yield = _div(_div(fcf, shares / 1e6 if shares else None), px)
        earn_yld  = _div(eps, px)
        div_yld   = _div(dps, px)
        payout    = _div(dps, eps) if (eps and eps > 0) else None
        graham    = None
        if eps and bvps and eps > 0 and bvps > 0:
            graham = round(np.sqrt(22.5 * eps * bvps), 4)

        fr_yld = None
        if div_yld is not None and fpc is not None:
            fr_yld = round(div_yld * (1 + (fpc / 100) * 0.4286), 4)

        # ── YoY growth ────────────────────────────────────────────────────
        def yoy(f1, f2):
            return _cagr(row.get(f1), prev.get(f2) if prev else None, 1)

        rev_g1   = yoy("revenue",      "revenue")
        gp_g1    = yoy("gross_profit", "gross_profit")
        eb_g1    = yoy("ebitda",       "ebitda")
        ni_g1    = yoy("net_profit",   "net_profit")
        eps_g1   = yoy("eps",          "eps")
        cfo_g1   = yoy("cfo",          "cfo")
        fcf_g1   = yoy("fcf",          "fcf")
        bvps_g1  = yoy("book_value_per_share", "book_value_per_share")

        # ── Multi-year CAGRs ─────────────────────────────────────────────
        def cn(field, n):
            prior = yearly[i - n] if i >= n else None
            return _cagr(row.get(field), prior.get(field) if prior else None, n)

        # ── Rolling averages ──────────────────────────────────────────────
        roe_l .append(roe);   roa_l .append(roa)
        roce_l.append(roce);  gm_l  .append(gross_margin)
        em_l  .append(ebitda_margin); om_l.append(ebit_margin)
        nm_l  .append(net_margin);    epsg_l.append(eps_g1)

        # ── Quality ───────────────────────────────────────────────────────
        f_score = piotroski_f_score(row, prev)
        z_score = altman_z_score(row, mc)

        # ── Div consecutive (only for latest FY — expensive) ─────────────
        div_consec = consecutive_div_years(fin) if i == len(yearly) - 1 else None

        dps_prev3  = yearly[i - 3] if i >= 3 else None
        dps_prev5  = yearly[i - 5] if i >= 5 else None
        div_cagr3  = _cagr(dps, dps_prev3.get("dps") if dps_prev3 else None, 3)
        div_cagr5  = _cagr(dps, dps_prev5.get("dps") if dps_prev5 else None, 5)

        # ── Price-based risk metrics (in-memory window) ───────────────────
        pw      = price_window(prices, ped)
        sharpe, max_dd, vol_1y = sharpe_drawdown_vol(pw)

        # ── Multi-year price returns (in-memory lookups) ──────────────────
        ret_3y  = price_return(prices, ped, 3)
        ret_5y  = price_return(prices, ped, 5)
        ret_7y  = price_return(prices, ped, 7)
        ret_10y = price_return(prices, ped, 10)
        ret_15y = price_return(prices, ped, 15)

        # ── Raw financial values (denormalised for history queries) ───────
        wc = round(tca - tcl, 2) if (tca is not None and tcl is not None) else None

        rows.append((
            asx_code, fy, ped.date(),
            px, mc,
            int(shares) if shares and np.isfinite(shares) else None,
            # Valuation
            pe, pb, ps, ev, ev_eb, ev_ebit, ev_rev, earn_yld, fcf_yield, graham,
            # Per share
            eps, _f(row.get("eps_diluted")), bvps, dps, fpc,
            # Dividend
            div_yld, fr_yld, payout, div_cagr3, div_cagr5, div_consec,
            # Returns on capital
            roe, roa, roce, roic,
            # Margins
            gross_margin, ebitda_margin, ebit_margin, net_margin,
            ocf_margin, fcf_margin,
            # Efficiency
            asset_turn, rec_turn, rec_days, capex_int,
            # Leverage & liquidity
            cr, de, da, nd_eb, int_cov, lt_d_cap,
            # Quality
            f_score, z_score,
            # YoY growth
            rev_g1, gp_g1, eb_g1, ni_g1, eps_g1, cfo_g1, fcf_g1, bvps_g1,
            # Revenue CAGR
            cn("revenue", 3), cn("revenue", 5), cn("revenue", 7), cn("revenue", 10),
            # Net income CAGR
            cn("net_profit", 3), cn("net_profit", 5),
            # EPS CAGR
            cn("eps", 3), cn("eps", 5),
            # EBITDA CAGR
            cn("ebitda", 3), cn("ebitda", 5),
            # FCF CAGR
            cn("fcf", 3), cn("fcf", 5),
            # Gross profit CAGR
            cn("gross_profit", 3), cn("gross_profit", 5),
            # BVPS CAGR
            cn("book_value_per_share", 3), cn("book_value_per_share", 5),
            # Rolling averages
            _avg(roe_l, 3),  _avg(roe_l, 5),
            _avg(roa_l, 3),  _avg(roa_l, 5),
            _avg(roce_l, 3), _avg(roce_l, 5),
            _avg(gm_l, 3),   _avg(gm_l, 5),
            _avg(em_l, 3),   _avg(em_l, 5),
            _avg(om_l, 3),   _avg(om_l, 5),
            _avg(nm_l, 3),   _avg(nm_l, 5),
            _avg(epsg_l, 3), _avg(epsg_l, 5),
            # Risk
            vol_1y, sharpe, max_dd,
            # Raw financials (for history tables)
            rev, ebitda, ni, cfo, capex, _f(row.get("cfi")), fcf,
            _f(row.get("total_debt")), wc,
            _f(row.get("cash_equivalents")), _f(row.get("total_equity")),
            _f(row.get("inventory")),
            # Multi-year price returns
            ret_3y, ret_5y, ret_7y, ret_10y, ret_15y,
            COMPUTE_VERSION, now,
        ))

    return rows


# ── Database Write ────────────────────────────────────────────────────────────

INSERT_SQL = """
    INSERT INTO market.yearly_metrics (
        asx_code, fiscal_year, period_end_date, price_at_compute,
        market_cap, shares_outstanding,
        pe_ratio, pb_ratio, ps_ratio,
        enterprise_value, ev_ebitda, ev_ebit, ev_revenue,
        earnings_yield, fcf_yield, graham_number,
        eps, eps_diluted, bvps, dps, franking_pct,
        dividend_yield, franked_yield, payout_ratio,
        dividend_cagr_3y, dividend_cagr_5y, dividend_consecutive_yrs,
        roe, roa, roce, roic,
        gross_margin, ebitda_margin, ebit_margin, net_margin,
        ocf_margin, fcf_margin,
        asset_turnover, receivables_turnover, receivables_days, capex_intensity,
        current_ratio, debt_to_equity, debt_to_assets,
        net_debt_to_ebitda, interest_coverage, lt_debt_to_capital,
        piotroski_f_score, altman_z_score,
        revenue_growth_1y, gross_profit_growth_1y, ebitda_growth_1y,
        net_income_growth_1y, eps_growth_1y, ocf_growth_1y,
        fcf_growth_1y, bvps_growth_1y,
        revenue_cagr_3y, revenue_cagr_5y, revenue_cagr_7y, revenue_cagr_10y,
        net_income_cagr_3y, net_income_cagr_5y,
        eps_cagr_3y, eps_cagr_5y,
        ebitda_cagr_3y, ebitda_cagr_5y,
        fcf_cagr_3y, fcf_cagr_5y,
        gross_profit_cagr_3y, gross_profit_cagr_5y,
        bvps_cagr_3y, bvps_cagr_5y,
        avg_roe_3y, avg_roe_5y,
        avg_roa_3y, avg_roa_5y,
        avg_roce_3y, avg_roce_5y,
        avg_gross_margin_3y, avg_gross_margin_5y,
        avg_ebitda_margin_3y, avg_ebitda_margin_5y,
        avg_operating_margin_3y, avg_operating_margin_5y,
        avg_net_margin_3y, avg_net_margin_5y,
        avg_eps_growth_3y, avg_eps_growth_5y,
        volatility_1y, sharpe_1y, max_drawdown_1y,
        revenue, ebitda, net_profit,
        cfo, capex, cfi, fcf,
        total_debt, working_capital, cash, total_equity, inventory,
        return_3y, return_5y, return_7y, return_10y, return_15y,
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
        revenue                 = EXCLUDED.revenue,
        ebitda                  = EXCLUDED.ebitda,
        net_profit              = EXCLUDED.net_profit,
        cfo                     = EXCLUDED.cfo,
        capex                   = EXCLUDED.capex,
        cfi                     = EXCLUDED.cfi,
        fcf                     = EXCLUDED.fcf,
        total_debt              = EXCLUDED.total_debt,
        working_capital         = EXCLUDED.working_capital,
        cash                    = EXCLUDED.cash,
        total_equity            = EXCLUDED.total_equity,
        inventory               = EXCLUDED.inventory,
        return_3y               = EXCLUDED.return_3y,
        return_5y               = EXCLUDED.return_5y,
        return_7y               = EXCLUDED.return_7y,
        return_10y              = EXCLUDED.return_10y,
        return_15y              = EXCLUDED.return_15y,
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
            fin = fetch_annual_financials(cur, asx_code)
            if fin.empty:
                skipped += 1
                continue

            # ── Fetch ALL prices ONCE per stock (not per fiscal year) ──────
            prices = fetch_all_prices(cur, asx_code)

            # ── Current shares (proxy for historical EPS derivation) ───────
            current_shares = fetch_current_shares(cur, asx_code)

            rows = build_yearly_rows(asx_code, fin, prices, current_shares)
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
            log.warning(f"  {asx_code}: {e}", exc_info=(errors <= 3))
            conn.rollback()

    conn.commit()
    cur.close()
    conn.close()

    log.info("─" * 60)
    log.info(f"Done! {processed} stocks | {skipped} skipped | "
             f"{errors} errors | {total_rows:,} rows upserted")


if __name__ == "__main__":
    main()
