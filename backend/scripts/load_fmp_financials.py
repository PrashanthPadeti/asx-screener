"""
ASX Screener — FMP Historical Financials Loader
================================================
One-time bulk load of all annual financials for every active ASX stock.

Loads from Financial Modeling Prep (FMP) API:
  • Income Statement  → financials.annual_pnl
  • Balance Sheet     → financials.annual_balance_sheet
  • Cash Flow         → financials.annual_cashflow

FMP returns values in the company's reporting currency (usually AUD for ASX).
All monetary values are stored in AUD millions (divided by 1,000,000).

Usage:
    python scripts/load_fmp_financials.py                  # All 1,978 stocks
    python scripts/load_fmp_financials.py --codes BHP CBA  # Specific stocks
    python scripts/load_fmp_financials.py --limit 50       # First N stocks
    python scripts/load_fmp_financials.py --skip-errors    # Continue on failures
    nohup python scripts/load_fmp_financials.py > logs/fmp_financials.log 2>&1 &

Expected runtime: ~3-6 hours for all 1,978 stocks (rate limited to ~5 req/sec).
FMP Starter plan: unlimited calls/day — no throttle needed beyond politeness.
"""

import os
import sys
import time
import logging
import argparse
from datetime import date, datetime
from typing import Optional

import psycopg2
from psycopg2.extras import execute_values
import requests
from dotenv import load_dotenv

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────

DB_URL = os.getenv(
    "DATABASE_URL_SYNC",
    "postgresql://asx_user:asx_secure_2024@localhost:5432/asx_screener"
)
FMP_KEY = os.getenv("FMP_API_KEY", "")

FMP_BASE    = "https://financialmodelingprep.com/api/v3"
YEARS_BACK  = 10          # Load up to 10 years of annual data
SLEEP_SEC   = 0.25        # 4 req/sec — polite for Starter plan
MAX_RETRIES = 3
BATCH_COMMIT = 50         # Commit to DB every N stocks

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ── FMP API Helpers ───────────────────────────────────────────────────────────

def fmp_get(endpoint: str, params: dict = None) -> Optional[list]:
    """Call FMP API with retry logic. Returns list or None."""
    if not FMP_KEY:
        raise RuntimeError("FMP_API_KEY not set in .env — get your key at financialmodelingprep.com")

    url = f"{FMP_BASE}/{endpoint}"
    p   = {"apikey": FMP_KEY, "limit": YEARS_BACK}
    if params:
        p.update(params)

    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, params=p, timeout=20)
            if resp.status_code == 401:
                raise RuntimeError("FMP API key invalid or expired")
            if resp.status_code == 404:
                return None
            if resp.status_code == 429:
                log.warning("Rate limited — sleeping 60s")
                time.sleep(60)
                continue
            resp.raise_for_status()
            data = resp.json()
            # FMP returns {"Error Message": "..."} on bad ticker
            if isinstance(data, dict) and "Error Message" in data:
                return None
            if not data:
                return None
            return data
        except requests.RequestException as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
            else:
                log.debug(f"Request failed after {MAX_RETRIES} attempts: {e}")
                return None
    return None


def safe_div(val, divisor=1_000_000) -> Optional[float]:
    """Divide by divisor (to convert to millions), return None if None/zero."""
    if val is None:
        return None
    try:
        return round(float(val) / divisor, 4)
    except (TypeError, ValueError):
        return None


def safe_float(val) -> Optional[float]:
    """Convert to float, return None on failure."""
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def parse_period_end(date_str: str) -> Optional[date]:
    """Parse FMP date string 'YYYY-MM-DD' to Python date."""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def fiscal_year_from_date(d: date) -> int:
    """
    Infer fiscal year from period end date.
    ASX companies mostly end in June (FY = calendar year of June end).
    e.g. period_end=2024-06-30 → fiscal_year=2024
         period_end=2023-12-31 → fiscal_year=2023
    """
    return d.year


# ── Income Statement ──────────────────────────────────────────────────────────

def load_income_statement(asx_code: str) -> list[dict]:
    ticker = f"{asx_code}.AX"
    data   = fmp_get(f"income-statement/{ticker}")
    if not data:
        return []

    rows = []
    for r in data:
        period_end = parse_period_end(r.get("date"))
        if not period_end:
            continue

        fy   = fiscal_year_from_date(period_end)
        rev  = safe_div(r.get("revenue"))
        gp   = safe_div(r.get("grossProfit"))
        ebit = safe_div(r.get("operatingIncome"))  # FMP: operatingIncome ≈ EBIT
        ebitda = safe_div(r.get("ebitda"))
        dep  = safe_div(r.get("depreciationAndAmortization"))
        ni   = safe_div(r.get("netIncome"))         # PAT
        tax  = safe_div(r.get("incomeTaxExpense"))
        int_ = safe_div(r.get("interestExpense"))
        eps  = safe_float(r.get("eps"))
        eps_d = safe_float(r.get("epsdiluted"))

        # Derived margins
        opm = round(ebit / rev, 6) if ebit and rev else None
        npm = round(ni   / rev, 6) if ni   and rev else None
        gpm = round(gp   / rev, 6) if gp   and rev else None
        ebitda_margin = round(ebitda / rev, 6) if ebitda and rev else None

        rows.append({
            "asx_code":       asx_code,
            "fiscal_year":    fy,
            "period_end_date": period_end,
            "revenue":        rev,
            "gross_profit":   gp,
            "ebitda":         ebitda,
            "ebit":           ebit,
            "net_profit":     ni,
            "pat":            ni,
            "interest_expense": int_,
            "tax":            tax,
            "depreciation":   dep,
            "opm":            opm,
            "npm":            npm,
            "gpm":            gpm,
            "ebitda_margin":  ebitda_margin,
            "eps":            eps,
            "eps_diluted":    eps_d,
            "data_source":    "fmp",
        })
    return rows


def upsert_income(cur, rows: list[dict]):
    if not rows:
        return
    sql = """
        INSERT INTO financials.annual_pnl
            (asx_code, fiscal_year, period_end_date,
             revenue, gross_profit, ebitda, ebit, net_profit, pat,
             interest_expense, tax, depreciation,
             opm, npm, gpm, ebitda_margin,
             eps, eps_diluted, data_source)
        VALUES %s
        ON CONFLICT (asx_code, fiscal_year) DO UPDATE SET
            revenue          = EXCLUDED.revenue,
            gross_profit     = EXCLUDED.gross_profit,
            ebitda           = EXCLUDED.ebitda,
            ebit             = EXCLUDED.ebit,
            net_profit       = EXCLUDED.net_profit,
            pat              = EXCLUDED.pat,
            interest_expense = EXCLUDED.interest_expense,
            tax              = EXCLUDED.tax,
            depreciation     = EXCLUDED.depreciation,
            opm              = EXCLUDED.opm,
            npm              = EXCLUDED.npm,
            gpm              = EXCLUDED.gpm,
            ebitda_margin    = EXCLUDED.ebitda_margin,
            eps              = EXCLUDED.eps,
            eps_diluted      = EXCLUDED.eps_diluted,
            data_source      = EXCLUDED.data_source
    """
    vals = [(
        r["asx_code"], r["fiscal_year"], r["period_end_date"],
        r["revenue"], r["gross_profit"], r["ebitda"], r["ebit"],
        r["net_profit"], r["pat"], r["interest_expense"], r["tax"], r["depreciation"],
        r["opm"], r["npm"], r["gpm"], r["ebitda_margin"],
        r["eps"], r["eps_diluted"], r["data_source"],
    ) for r in rows]
    execute_values(cur, sql, vals, page_size=100)


# ── Balance Sheet ─────────────────────────────────────────────────────────────

def load_balance_sheet(asx_code: str) -> list[dict]:
    ticker = f"{asx_code}.AX"
    data   = fmp_get(f"balance-sheet-statement/{ticker}")
    if not data:
        return []

    rows = []
    for r in data:
        period_end = parse_period_end(r.get("date"))
        if not period_end:
            continue

        fy  = fiscal_year_from_date(period_end)
        ta  = safe_div(r.get("totalAssets"))
        tl  = safe_div(r.get("totalLiabilities"))
        te  = safe_div(r.get("totalEquity") or r.get("totalStockholdersEquity"))
        tca = safe_div(r.get("totalCurrentAssets"))
        tcl = safe_div(r.get("totalCurrentLiabilities"))
        cash = safe_div(r.get("cashAndCashEquivalents"))
        rec  = safe_div(r.get("netReceivables"))
        inv  = safe_div(r.get("inventory"))
        gw   = safe_div(r.get("goodwill"))
        intg = safe_div(r.get("intangibleAssets"))
        std  = safe_div(r.get("shortTermDebt"))  # or shortTermDebt
        ltd  = safe_div(r.get("longTermDebt"))
        re   = safe_div(r.get("retainedEarnings"))
        td   = safe_div(r.get("totalDebt"))
        nd   = safe_div(r.get("netDebt"))
        shares = r.get("commonStock")  # FMP: shares in units

        # Derived
        wc  = round(tca - tcl, 4) if tca and tcl else None
        bvps = safe_float(r.get("bookValuePerShare"))

        rows.append({
            "asx_code":            asx_code,
            "fiscal_year":         fy,
            "period_end_date":     period_end,
            "cash_equivalents":    cash,
            "trade_receivables":   rec,
            "inventory":           inv,
            "total_current_assets": tca,
            "total_assets":        ta,
            "short_term_debt":     std,
            "total_current_liab":  tcl,
            "long_term_debt":      ltd,
            "total_liabilities":   tl,
            "total_equity":        te,
            "retained_earnings":   re,
            "goodwill":            gw,
            "intangibles":         intg,
            "total_debt":          td,
            "net_debt":            nd,
            "working_capital":     wc,
            "book_value_per_share": bvps,
            "data_source":         "fmp",
        })
    return rows


def upsert_balance_sheet(cur, rows: list[dict]):
    if not rows:
        return
    sql = """
        INSERT INTO financials.annual_balance_sheet
            (asx_code, fiscal_year, period_end_date,
             cash_equivalents, trade_receivables, inventory,
             total_current_assets, total_assets,
             short_term_debt, total_current_liab, long_term_debt,
             total_liabilities, total_equity, retained_earnings,
             goodwill, intangibles, total_debt, net_debt,
             working_capital, book_value_per_share, data_source)
        VALUES %s
        ON CONFLICT (asx_code, fiscal_year) DO UPDATE SET
            cash_equivalents    = EXCLUDED.cash_equivalents,
            trade_receivables   = EXCLUDED.trade_receivables,
            inventory           = EXCLUDED.inventory,
            total_current_assets = EXCLUDED.total_current_assets,
            total_assets        = EXCLUDED.total_assets,
            short_term_debt     = EXCLUDED.short_term_debt,
            total_current_liab  = EXCLUDED.total_current_liab,
            long_term_debt      = EXCLUDED.long_term_debt,
            total_liabilities   = EXCLUDED.total_liabilities,
            total_equity        = EXCLUDED.total_equity,
            retained_earnings   = EXCLUDED.retained_earnings,
            goodwill            = EXCLUDED.goodwill,
            intangibles         = EXCLUDED.intangibles,
            total_debt          = EXCLUDED.total_debt,
            net_debt            = EXCLUDED.net_debt,
            working_capital     = EXCLUDED.working_capital,
            book_value_per_share = EXCLUDED.book_value_per_share,
            data_source         = EXCLUDED.data_source
    """
    vals = [(
        r["asx_code"], r["fiscal_year"], r["period_end_date"],
        r["cash_equivalents"], r["trade_receivables"], r["inventory"],
        r["total_current_assets"], r["total_assets"],
        r["short_term_debt"], r["total_current_liab"], r["long_term_debt"],
        r["total_liabilities"], r["total_equity"], r["retained_earnings"],
        r["goodwill"], r["intangibles"], r["total_debt"], r["net_debt"],
        r["working_capital"], r["book_value_per_share"], r["data_source"],
    ) for r in rows]
    execute_values(cur, sql, vals, page_size=100)


# ── Cash Flow ─────────────────────────────────────────────────────────────────

def load_cash_flow(asx_code: str) -> list[dict]:
    ticker = f"{asx_code}.AX"
    data   = fmp_get(f"cash-flow-statement/{ticker}")
    if not data:
        return []

    rows = []
    for r in data:
        period_end = parse_period_end(r.get("date"))
        if not period_end:
            continue

        fy  = fiscal_year_from_date(period_end)
        ni  = safe_div(r.get("netIncome"))
        dep = safe_div(r.get("depreciationAndAmortization"))
        wcc = safe_div(r.get("changeInWorkingCapital"))
        cfo = safe_div(r.get("netCashProvidedByOperatingActivities"))
        capex = safe_div(r.get("capitalExpenditure"))
        acq   = safe_div(r.get("acquisitionsNet"))
        cfi   = safe_div(r.get("netCashUsedForInvestingActivites"))
        div   = safe_div(r.get("dividendsPaid"))
        drepay = safe_div(r.get("debtRepayment"))
        eq_issued = safe_div(r.get("commonStockIssued"))
        buyback   = safe_div(r.get("commonStockRepurchased"))
        cff = safe_div(r.get("netCashUsedProvidedByFinancingActivities"))
        net_cash = safe_div(r.get("netChangeInCash"))
        fcf  = safe_div(r.get("freeCashFlow"))

        rows.append({
            "asx_code":             asx_code,
            "fiscal_year":          fy,
            "period_end_date":      period_end,
            "net_income":           ni,
            "depreciation_amort":   dep,
            "working_capital_changes": wcc,
            "cfo":                  cfo,
            "capex":                capex,
            "acquisitions":         acq,
            "cfi":                  cfi,
            "dividends_paid":       div,
            "debt_repaid":          drepay,
            "equity_raised":        eq_issued,
            "buybacks":             buyback,
            "cff":                  cff,
            "net_change_in_cash":   net_cash,
            "fcf":                  fcf,
            "data_source":          "fmp",
        })
    return rows


def upsert_cash_flow(cur, rows: list[dict]):
    if not rows:
        return
    sql = """
        INSERT INTO financials.annual_cashflow
            (asx_code, fiscal_year, period_end_date,
             net_income, depreciation_amort, working_capital_changes,
             cfo, capex, acquisitions, cfi,
             dividends_paid, debt_repaid, equity_raised, buybacks, cff,
             net_change_in_cash, fcf, data_source)
        VALUES %s
        ON CONFLICT (asx_code, fiscal_year) DO UPDATE SET
            net_income           = EXCLUDED.net_income,
            depreciation_amort   = EXCLUDED.depreciation_amort,
            working_capital_changes = EXCLUDED.working_capital_changes,
            cfo                  = EXCLUDED.cfo,
            capex                = EXCLUDED.capex,
            acquisitions         = EXCLUDED.acquisitions,
            cfi                  = EXCLUDED.cfi,
            dividends_paid       = EXCLUDED.dividends_paid,
            debt_repaid          = EXCLUDED.debt_repaid,
            equity_raised        = EXCLUDED.equity_raised,
            buybacks             = EXCLUDED.buybacks,
            cff                  = EXCLUDED.cff,
            net_change_in_cash   = EXCLUDED.net_change_in_cash,
            fcf                  = EXCLUDED.fcf,
            data_source          = EXCLUDED.data_source
    """
    vals = [(
        r["asx_code"], r["fiscal_year"], r["period_end_date"],
        r["net_income"], r["depreciation_amort"], r["working_capital_changes"],
        r["cfo"], r["capex"], r["acquisitions"], r["cfi"],
        r["dividends_paid"], r["debt_repaid"], r["equity_raised"],
        r["buybacks"], r["cff"], r["net_change_in_cash"], r["fcf"], r["data_source"],
    ) for r in rows]
    execute_values(cur, sql, vals, page_size=100)


# ── Key Metrics (DPS + Franking) ──────────────────────────────────────────────

def load_key_metrics(asx_code: str) -> dict:
    """
    FMP key-metrics gives dividendYield and some DPS data.
    We'll use this to update dps in annual_pnl where available.
    Returns {fiscal_year: {dps, dividend_yield}}
    """
    ticker = f"{asx_code}.AX"
    data   = fmp_get(f"key-metrics/{ticker}")
    if not data:
        return {}

    out = {}
    for r in data:
        period_end = parse_period_end(r.get("date"))
        if not period_end:
            continue
        fy = fiscal_year_from_date(period_end)
        dps = safe_float(r.get("dividendPerShareTTM") or r.get("dividendPerShare"))
        out[fy] = {"dps": dps}
    return out


# ── Per-Stock Loader ──────────────────────────────────────────────────────────

def load_stock(cur, asx_code: str) -> dict:
    """Load all financials for one stock. Returns counts."""
    counts = {"pnl": 0, "bs": 0, "cf": 0}

    # 1 — Income Statement
    pnl_rows = load_income_statement(asx_code)
    time.sleep(SLEEP_SEC)

    # 2 — Balance Sheet
    bs_rows = load_balance_sheet(asx_code)
    time.sleep(SLEEP_SEC)

    # 3 — Cash Flow
    cf_rows = load_cash_flow(asx_code)
    time.sleep(SLEEP_SEC)

    # 4 — Key Metrics (DPS)
    metrics = load_key_metrics(asx_code)
    time.sleep(SLEEP_SEC)

    # Merge DPS into pnl rows
    for row in pnl_rows:
        fy = row["fiscal_year"]
        if fy in metrics and metrics[fy]["dps"]:
            row["dps"] = metrics[fy]["dps"]

    # Upsert
    if pnl_rows:
        upsert_income(cur, pnl_rows)
        counts["pnl"] = len(pnl_rows)

    if bs_rows:
        upsert_balance_sheet(cur, bs_rows)
        counts["bs"] = len(bs_rows)

    if cf_rows:
        upsert_cash_flow(cur, cf_rows)
        counts["cf"] = len(cf_rows)

    return counts


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="FMP Historical Financials Loader")
    parser.add_argument("--codes",       nargs="+", help="Specific ASX codes to load")
    parser.add_argument("--limit",       type=int,  help="Load first N stocks only")
    parser.add_argument("--skip-errors", action="store_true", help="Continue on DB errors")
    parser.add_argument("--from-code",   help="Resume from this ASX code (alphabetical)")
    args = parser.parse_args()

    if not FMP_KEY:
        print("ERROR: FMP_API_KEY not set. Add to .env file:")
        print("  FMP_API_KEY=your_key_here")
        print("  Get your key at: https://financialmodelingprep.com/pricing")
        sys.exit(1)

    conn = psycopg2.connect(DB_URL)
    cur  = conn.cursor()

    if args.codes:
        codes = [c.upper() for c in args.codes]
    else:
        cur.execute("""
            SELECT asx_code FROM market.companies
            WHERE status = 'active'
            ORDER BY asx_code
        """)
        codes = [r[0] for r in cur.fetchall()]

    if args.from_code:
        start_code = args.from_code.upper()
        codes = [c for c in codes if c >= start_code]
        log.info(f"Resuming from {start_code} — {len(codes)} stocks remaining")

    if args.limit:
        codes = codes[:args.limit]

    total = len(codes)
    log.info(f"Loading financials for {total} stocks via FMP...")
    log.info(f"Estimated time: {total * 4 * SLEEP_SEC / 60:.0f}–{total * 4 * SLEEP_SEC * 2 / 60:.0f} minutes")

    ok = err = no_data = 0
    total_pnl = total_bs = total_cf = 0

    for i, code in enumerate(codes, 1):
        try:
            counts = load_stock(cur, code)

            if counts["pnl"] == 0 and counts["bs"] == 0 and counts["cf"] == 0:
                no_data += 1
                log.debug(f"  {code}: no data (micro-cap/new listing)")
            else:
                ok += 1
                total_pnl += counts["pnl"]
                total_bs  += counts["bs"]
                total_cf  += counts["cf"]

            # Commit every BATCH_COMMIT stocks
            if i % BATCH_COMMIT == 0:
                conn.commit()
                log.info(
                    f"[{i:4d}/{total}] {ok} loaded, {no_data} no data, {err} errors | "
                    f"P&L:{total_pnl} BS:{total_bs} CF:{total_cf} rows"
                )

        except psycopg2.Error as e:
            err += 1
            conn.rollback()
            log.warning(f"  {code}: DB error — {e}")
            if not args.skip_errors:
                raise
        except Exception as e:
            err += 1
            log.warning(f"  {code}: Error — {e}")
            if not args.skip_errors:
                raise

    conn.commit()
    cur.close()
    conn.close()

    log.info("=" * 60)
    log.info(f"DONE! {ok} stocks loaded, {no_data} no data, {err} errors")
    log.info(f"Rows loaded: P&L={total_pnl}, BS={total_bs}, CF={total_cf}")
    log.info(f"Total financial records: {total_pnl + total_bs + total_cf}")
    log.info("Next step: run compute engine to calculate all metrics")
    log.info("  python compute/engine/daily_compute.py")


if __name__ == "__main__":
    main()
