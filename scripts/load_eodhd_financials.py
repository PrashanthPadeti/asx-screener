"""
ASX Screener — EODHD Historical Financials Loader
==================================================
One-time bulk load of all annual financials for every active ASX stock.
Uses EODHD (official ASX licensed data distributor).

Loads from: https://eodhd.com/api/fundamentals/{ticker}.AU
Fetches one JSON per stock → parses Income Statement, Balance Sheet, Cash Flow.

All monetary values stored in AUD millions (raw values ÷ 1,000,000).
Values are in the company's reporting currency (AUD for most, USD for BHP/RIO etc.)

Usage:
    python scripts/load_eodhd_financials.py                   # All stocks
    python scripts/load_eodhd_financials.py --codes BHP CBA   # Specific stocks
    python scripts/load_eodhd_financials.py --limit 50        # First N stocks
    python scripts/load_eodhd_financials.py --from-code WBC   # Resume from code
    nohup python scripts/load_eodhd_financials.py > logs/eodhd_financials.log 2>&1 &

Expected runtime: ~3-5 hours for all 1,978 stocks (1 API call per stock).
EODHD ALL-IN-ONE: 100,000 calls/day — no throttle issues.
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
EODHD_KEY  = os.getenv("EODHD_API_KEY", "")
EODHD_BASE = "https://eodhd.com/api"

SLEEP_SEC    = 0.3          # ~3 req/sec — polite
MAX_RETRIES  = 3
BATCH_COMMIT = 50           # Commit every N stocks

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def safe_mil(val) -> Optional[float]:
    """Convert raw value to millions. Returns None if missing."""
    if val is None or val == "" or val == "None":
        return None
    try:
        f = float(val)
        return round(f / 1_000_000, 4) if f != 0 else None
    except (TypeError, ValueError):
        return None


def safe_float(val) -> Optional[float]:
    """Convert to float, return None on failure."""
    if val is None or val == "" or val == "None":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def parse_date(date_str: str) -> Optional[date]:
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def fiscal_year(d: date) -> int:
    """
    Infer fiscal year from period end date.
    ASX companies mostly end June 30 — period 2024-06-30 → FY2024.
    December year-end: 2023-12-31 → FY2023.
    """
    return d.year


# ── EODHD Fetcher ─────────────────────────────────────────────────────────────

def fetch_fundamentals(asx_code: str) -> Optional[dict]:
    """
    Fetch full fundamentals JSON for one ASX stock.
    Single API call returns: General, Financials (IS + BS + CF), SplitsDividends.
    """
    if not EODHD_KEY:
        raise RuntimeError("EODHD_API_KEY not set in .env")

    ticker = f"{asx_code}.AU"
    url    = f"{EODHD_BASE}/fundamentals/{ticker}"
    params = {"api_token": EODHD_KEY, "fmt": "json"}

    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, params=params, timeout=30)

            if resp.status_code == 401:
                raise RuntimeError("EODHD API key invalid")
            if resp.status_code == 404:
                return None
            if resp.status_code == 429:
                log.warning("Rate limited — sleeping 60s")
                time.sleep(60)
                continue
            resp.raise_for_status()

            data = resp.json()

            # EODHD returns "NA" string when no data
            if data == "NA" or not isinstance(data, dict):
                return None

            return data

        except requests.RequestException as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
            else:
                log.debug(f"  {asx_code}: fetch failed — {e}")
                return None

    return None


# ── Income Statement Parser ───────────────────────────────────────────────────

def parse_income_statement(asx_code: str, data: dict) -> list[dict]:
    """
    Parse EODHD Income_Statement::annual into rows for financials.annual_pnl.

    EODHD field names (confirmed):
        totalRevenue, grossProfit, ebitda, operatingIncome (≈EBIT),
        netIncome, interestExpense, incomeTaxExpense, depreciationAndAmortization
    """
    try:
        is_section = data.get("Financials", {}).get("Income_Statement", {})
        # EODHD uses 'yearly' key (not 'annual')
        annual = is_section.get("yearly") or is_section.get("annual") or {}
    except AttributeError:
        return []

    if not annual or annual == "NA":
        return []

    rows = []
    for date_str, r in annual.items():
        if not isinstance(r, dict):
            continue

        period_end = parse_date(date_str)
        if not period_end:
            continue

        fy   = fiscal_year(period_end)
        rev  = safe_mil(r.get("totalRevenue"))
        gp   = safe_mil(r.get("grossProfit"))
        ebit = safe_mil(r.get("operatingIncome"))
        ebitda = safe_mil(r.get("ebitda"))
        dep  = safe_mil(r.get("depreciationAndAmortization"))
        ni   = safe_mil(r.get("netIncome"))
        tax  = safe_mil(r.get("incomeTaxExpense"))
        int_ = safe_mil(r.get("interestExpense"))
        eps  = safe_float(r.get("eps") or r.get("epsActual"))
        eps_d = safe_float(r.get("epsDiluted") or r.get("dilutedEps"))

        # Derived margins
        opm = round(ebit   / rev, 6) if ebit   and rev and rev != 0 else None
        npm = round(ni     / rev, 6) if ni     and rev and rev != 0 else None
        gpm = round(gp     / rev, 6) if gp     and rev and rev != 0 else None
        ebitda_margin = round(ebitda / rev, 6) if ebitda and rev and rev != 0 else None

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
            "data_source":    "eodhd",
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


# ── Balance Sheet Parser ──────────────────────────────────────────────────────

def parse_balance_sheet(asx_code: str, data: dict) -> list[dict]:
    """
    Parse EODHD Balance_Sheet::annual into rows for financials.annual_balance_sheet.

    EODHD field names (confirmed):
        totalAssets, totalLiab, totalStockholderEquity,
        cash, longTermDebt, shortTermDebt,
        goodWill (capital W!), intangibleAssets, retainedEarnings,
        totalCurrentAssets, totalCurrentLiabilities,
        netReceivables, inventory
    """
    try:
        bs_section = data.get("Financials", {}).get("Balance_Sheet", {})
        # EODHD uses 'yearly' key (not 'annual')
        annual = bs_section.get("yearly") or bs_section.get("annual") or {}
    except AttributeError:
        return []

    if not annual or annual == "NA":
        return []

    rows = []
    for date_str, r in annual.items():
        if not isinstance(r, dict):
            continue

        period_end = parse_date(date_str)
        if not period_end:
            continue

        fy   = fiscal_year(period_end)
        ta   = safe_mil(r.get("totalAssets"))
        tl   = safe_mil(r.get("totalLiab"))
        te   = safe_mil(r.get("totalStockholderEquity"))
        cash = safe_mil(r.get("cash"))
        ltd  = safe_mil(r.get("longTermDebt"))
        std  = safe_mil(r.get("shortTermDebt"))
        gw   = safe_mil(r.get("goodWill"))      # Note: capital W in EODHD
        intg = safe_mil(r.get("intangibleAssets"))
        re   = safe_mil(r.get("retainedEarnings"))
        tca  = safe_mil(r.get("totalCurrentAssets"))
        tcl  = safe_mil(r.get("totalCurrentLiabilities"))
        rec  = safe_mil(r.get("netReceivables"))
        inv  = safe_mil(r.get("inventory"))

        # Derived
        td  = round((ltd or 0) + (std or 0), 4) if (ltd or std) else None
        nd  = round(td - cash, 4)                if (td and cash) else None
        wc  = round(tca - tcl, 4)               if (tca and tcl) else None
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
            "data_source":         "eodhd",
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
            cash_equivalents     = EXCLUDED.cash_equivalents,
            trade_receivables    = EXCLUDED.trade_receivables,
            inventory            = EXCLUDED.inventory,
            total_current_assets = EXCLUDED.total_current_assets,
            total_assets         = EXCLUDED.total_assets,
            short_term_debt      = EXCLUDED.short_term_debt,
            total_current_liab   = EXCLUDED.total_current_liab,
            long_term_debt       = EXCLUDED.long_term_debt,
            total_liabilities    = EXCLUDED.total_liabilities,
            total_equity         = EXCLUDED.total_equity,
            retained_earnings    = EXCLUDED.retained_earnings,
            goodwill             = EXCLUDED.goodwill,
            intangibles          = EXCLUDED.intangibles,
            total_debt           = EXCLUDED.total_debt,
            net_debt             = EXCLUDED.net_debt,
            working_capital      = EXCLUDED.working_capital,
            book_value_per_share = EXCLUDED.book_value_per_share,
            data_source          = EXCLUDED.data_source
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


# ── Cash Flow Parser ──────────────────────────────────────────────────────────

def parse_cash_flow(asx_code: str, data: dict) -> list[dict]:
    """
    Parse EODHD Cash_Flow::annual into rows for financials.annual_cashflow.

    EODHD field names:
        totalCashFromOperatingActivities, capitalExpenditures,
        totalCashFromInvestingActivities, totalCashFromFinancingActivities,
        dividendsPaid, freeCashFlow, depreciation, changeToNetincome
    """
    try:
        cf_section = data.get("Financials", {}).get("Cash_Flow", {})
        # EODHD uses 'yearly' key (not 'annual')
        annual = cf_section.get("yearly") or cf_section.get("annual") or {}
    except AttributeError:
        return []

    if not annual or annual == "NA":
        return []

    rows = []
    for date_str, r in annual.items():
        if not isinstance(r, dict):
            continue

        period_end = parse_date(date_str)
        if not period_end:
            continue

        fy  = fiscal_year(period_end)
        ni  = safe_mil(r.get("netIncome") or r.get("changeToNetincome"))
        dep = safe_mil(r.get("depreciation") or r.get("depreciationAndAmortization"))
        wcc = safe_mil(r.get("changeToWorkingCapital") or r.get("changeInWorkingCapital"))
        cfo = safe_mil(r.get("totalCashFromOperatingActivities"))
        capex = safe_mil(r.get("capitalExpenditures"))
        acq   = safe_mil(r.get("acquisitionsNet") or r.get("acquisitions"))
        cfi   = safe_mil(r.get("totalCashFromInvestingActivities"))
        div   = safe_mil(r.get("dividendsPaid"))
        cff   = safe_mil(r.get("totalCashFromFinancingActivities"))
        net_cash = safe_mil(r.get("changeInCash") or r.get("netChangeInCash"))
        fcf   = safe_mil(r.get("freeCashFlow"))

        # Calculate FCF if not provided: FCF = CFO + Capex (capex is negative)
        if fcf is None and cfo is not None and capex is not None:
            fcf = round(cfo + capex, 4)

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
            "cff":                  cff,
            "net_change_in_cash":   net_cash,
            "fcf":                  fcf,
            "data_source":          "eodhd",
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
             dividends_paid, cff, net_change_in_cash, fcf, data_source)
        VALUES %s
        ON CONFLICT (asx_code, fiscal_year) DO UPDATE SET
            net_income              = EXCLUDED.net_income,
            depreciation_amort      = EXCLUDED.depreciation_amort,
            working_capital_changes = EXCLUDED.working_capital_changes,
            cfo                     = EXCLUDED.cfo,
            capex                   = EXCLUDED.capex,
            acquisitions            = EXCLUDED.acquisitions,
            cfi                     = EXCLUDED.cfi,
            dividends_paid          = EXCLUDED.dividends_paid,
            cff                     = EXCLUDED.cff,
            net_change_in_cash      = EXCLUDED.net_change_in_cash,
            fcf                     = EXCLUDED.fcf,
            data_source             = EXCLUDED.data_source
    """
    vals = [(
        r["asx_code"], r["fiscal_year"], r["period_end_date"],
        r["net_income"], r["depreciation_amort"], r["working_capital_changes"],
        r["cfo"], r["capex"], r["acquisitions"], r["cfi"],
        r["dividends_paid"], r["cff"], r["net_change_in_cash"],
        r["fcf"], r["data_source"],
    ) for r in rows]
    execute_values(cur, sql, vals, page_size=100)


# ── DPS Parser (from SplitsDividends) ────────────────────────────────────────

def parse_dps(data: dict) -> dict:
    """
    Extract annual DPS from SplitsDividends.Dividends.
    Returns {fiscal_year: total_dps_for_year}
    """
    try:
        divs = data.get("SplitsDividends", {}).get("Dividends", {})
    except AttributeError:
        return {}

    if not divs or divs == "NA":
        return {}

    annual_dps = {}
    for date_str, d in divs.items():
        if not isinstance(d, dict):
            continue
        val = safe_float(d.get("value") or d.get("dividend"))
        if val is None:
            continue
        dt = parse_date(date_str)
        if not dt:
            continue
        fy = fiscal_year(dt)
        annual_dps[fy] = round((annual_dps.get(fy) or 0) + val, 4)

    return annual_dps


def update_dps(cur, asx_code: str, dps_by_year: dict):
    """Update DPS in annual_pnl for each year where we have dividend data."""
    if not dps_by_year:
        return
    for fy, dps in dps_by_year.items():
        cur.execute("""
            UPDATE financials.annual_pnl
            SET dps = %s
            WHERE asx_code = %s AND fiscal_year = %s
        """, (dps, asx_code, fy))


# ── Per-Stock Loader ──────────────────────────────────────────────────────────

def load_stock(cur, asx_code: str) -> dict:
    """Load all financials for one stock. Returns row counts."""
    data = fetch_fundamentals(asx_code)
    time.sleep(SLEEP_SEC)

    if not data:
        return {"pnl": 0, "bs": 0, "cf": 0}

    counts = {"pnl": 0, "bs": 0, "cf": 0}

    pnl_rows = parse_income_statement(asx_code, data)
    bs_rows  = parse_balance_sheet(asx_code, data)
    cf_rows  = parse_cash_flow(asx_code, data)
    dps      = parse_dps(data)

    if pnl_rows:
        upsert_income(cur, pnl_rows)
        counts["pnl"] = len(pnl_rows)

    if bs_rows:
        upsert_balance_sheet(cur, bs_rows)
        counts["bs"] = len(bs_rows)

    if cf_rows:
        upsert_cash_flow(cur, cf_rows)
        counts["cf"] = len(cf_rows)

    if dps and pnl_rows:
        update_dps(cur, asx_code, dps)

    return counts


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="EODHD Historical Financials Loader")
    parser.add_argument("--codes",       nargs="+", help="Specific ASX codes")
    parser.add_argument("--limit",       type=int,  help="Load first N stocks only")
    parser.add_argument("--from-code",   help="Resume from this ASX code (alphabetical)")
    parser.add_argument("--skip-errors", action="store_true")
    args = parser.parse_args()

    if not EODHD_KEY:
        print("ERROR: EODHD_API_KEY not set in .env")
        print("  Get your key at: https://eodhd.com/pricing")
        sys.exit(1)

    conn = psycopg2.connect(DB_URL)
    cur  = conn.cursor()

    if args.codes:
        codes = [c.upper() for c in args.codes]
    else:
        cur.execute("""
            SELECT asx_code FROM market.companies
            WHERE status = 'active' ORDER BY asx_code
        """)
        codes = [r[0] for r in cur.fetchall()]

    if args.from_code:
        start = args.from_code.upper()
        codes = [c for c in codes if c >= start]
        log.info(f"Resuming from {start} — {len(codes)} stocks remaining")

    if args.limit:
        codes = codes[:args.limit]

    total = len(codes)
    log.info(f"Loading financials for {total} stocks via EODHD...")
    log.info(f"Est. time: ~{total * SLEEP_SEC / 60:.0f} minutes")

    ok = err = no_data = 0
    total_pnl = total_bs = total_cf = 0

    for i, code in enumerate(codes, 1):
        try:
            counts = load_stock(cur, code)

            if all(v == 0 for v in counts.values()):
                no_data += 1
                log.debug(f"  {code}: no financial data")
            else:
                ok += 1
                total_pnl += counts["pnl"]
                total_bs  += counts["bs"]
                total_cf  += counts["cf"]

            if i % BATCH_COMMIT == 0:
                conn.commit()
                log.info(
                    f"[{i:4d}/{total}] {ok} loaded, {no_data} no data, {err} errors | "
                    f"P&L:{total_pnl} BS:{total_bs} CF:{total_cf}"
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
    log.info(f"DONE! {ok} loaded, {no_data} no data, {err} errors")
    log.info(f"Rows: P&L={total_pnl}  BS={total_bs}  CF={total_cf}")
    log.info(f"Total records: {total_pnl + total_bs + total_cf}")
    log.info("Next: python compute/engine/daily_compute.py")


if __name__ == "__main__":
    main()
