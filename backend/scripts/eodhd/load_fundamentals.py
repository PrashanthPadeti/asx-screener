"""
EODHD Raw Zone — Load Fundamentals from Disk → DB
==================================================
Step 2: disk → database.  Reads gzipped JSON files saved by
download_historical_fundamentals.py (or download_daily_fundamentals.py)
and upserts all financial data into the relevant DB tables.

Tables written:
    financials.annual_pnl              (annual income statement)
    financials.annual_balance_sheet    (annual balance sheet)
    financials.annual_cashflow         (annual cash flow)
    market.quarterly_metrics           (quarterly IS raw columns)
    market.dividends                   (full dividend history)
    market.splits                      (split history)
    market.analyst_ratings             (consensus snapshot)
    market.companies                   (shares_outstanding, website, etc.)

All monetary values in AUD millions (raw ÷ 1,000,000).

Usage:
    # Load from historical raw files (after download_historical_fundamentals.py)
    python scripts/eodhd/load_fundamentals.py

    # Load from an incremental date folder
    python scripts/eodhd/load_fundamentals.py --date 2026-04-27

    # Specific stocks (from historical folder)
    python scripts/eodhd/load_fundamentals.py --codes BHP CBA

    # Resume from a code
    python scripts/eodhd/load_fundamentals.py --from-code WBC
"""

import gzip
import json
import logging
import os
import sys
import argparse
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import psycopg2
from psycopg2.extras import execute_values, RealDictCursor
from dotenv import load_dotenv

load_dotenv()

DB_URL       = os.getenv("DATABASE_URL_SYNC",
                  "postgresql://asx_user:asx_secure_2024@localhost:5432/asx_screener")
RAW_BASE     = Path(os.getenv("RAW_DATA_DIR", "/opt/asx-screener/data/raw"))
HIST_DIR     = RAW_BASE / "eodhd" / "historical" / "fundamentals"
INCR_DIR     = RAW_BASE / "eodhd" / "incremental" / "fundamentals"
BATCH_COMMIT = 50

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)


# ── Type helpers ─────────────────────────────────────────────────────────────

def sf(val) -> Optional[float]:
    if val is None or val == "" or val == "None" or val == "NA":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def sm(val) -> Optional[float]:
    """Convert raw value to AUD millions."""
    f = sf(val)
    if f is None:
        return None
    return round(f / 1_000_000, 4) if f != 0 else None


def sd(val) -> Optional[date]:
    if not val or val in ("", "None", "NA", "0000-00-00"):
        return None
    try:
        return datetime.strptime(str(val)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def si(val) -> Optional[int]:
    f = sf(val)
    return int(f) if f is not None else None


def margin(num, denom) -> Optional[float]:
    if not num or not denom or denom == 0:
        return None
    m = num / denom
    return round(m, 6) if abs(m) < 9999 else None


def fiscal_year(d: date) -> int:
    return d.year


def fy_quarter(d: date) -> tuple[int, int]:
    """(fiscal_year, quarter) using calendar quarters."""
    q = (d.month - 1) // 3 + 1
    return d.year, q


def dedup_fy(rows: list[dict]) -> list[dict]:
    seen: dict[int, dict] = {}
    for r in rows:
        fy  = r["fiscal_year"]
        ped = r.get("period_end_date")
        if fy not in seen or (ped and ped > seen[fy].get("period_end_date", date.min)):
            seen[fy] = r
    return list(seen.values())


def dedup_fy_q(rows: list[dict]) -> list[dict]:
    seen: dict[tuple, dict] = {}
    for r in rows:
        key = (r["fiscal_year"], r["quarter"])
        ped = r.get("period_end_date")
        if key not in seen or (ped and ped > seen[key].get("period_end_date", date.min)):
            seen[key] = r
    return list(seen.values())


# ── Annual parsers ────────────────────────────────────────────────────────────

def parse_annual_pnl(asx_code: str, data: dict) -> list[dict]:
    section = data.get("Financials", {}).get("Income_Statement", {})
    annual  = section.get("yearly") or section.get("annual") or {}
    if not annual or annual == "NA":
        return []

    rows = []
    for date_str, r in annual.items():
        if not isinstance(r, dict):
            continue
        ped = sd(date_str)
        if not ped:
            continue

        rev    = sm(r.get("totalRevenue"))
        gp     = sm(r.get("grossProfit"))
        ebit   = sm(r.get("operatingIncome"))
        ebitda = sm(r.get("ebitda"))
        dep    = sm(r.get("depreciationAndAmortization"))
        ni     = sm(r.get("netIncome"))
        tax    = sm(r.get("incomeTaxExpense"))
        int_   = sm(r.get("interestExpense"))
        eps    = sf(r.get("eps") or r.get("epsActual"))
        eps_d  = sf(r.get("epsDiluted") or r.get("dilutedEps"))
        shares = si(r.get("commonStockSharesOutstanding"))

        rows.append({
            "asx_code":        asx_code,
            "fiscal_year":     fiscal_year(ped),
            "period_end_date": ped,
            "revenue":         rev,
            "gross_profit":    gp,
            "ebitda":          ebitda,
            "ebit":            ebit,
            "net_profit":      ni,
            "pat":             ni,
            "interest_expense": int_,
            "tax":             tax,
            "depreciation":    dep,
            "opm":             margin(ebit,   rev),
            "npm":             margin(ni,     rev),
            "gpm":             margin(gp,     rev),
            "ebitda_margin":   margin(ebitda, rev),
            "eps":             eps,
            "eps_diluted":     eps_d,
            "shares_used":     shares,
            "data_source":     "eodhd",
        })
    return dedup_fy(rows)


def parse_annual_bs(asx_code: str, data: dict) -> list[dict]:
    section = data.get("Financials", {}).get("Balance_Sheet", {})
    annual  = section.get("yearly") or section.get("annual") or {}
    if not annual or annual == "NA":
        return []

    rows = []
    for date_str, r in annual.items():
        if not isinstance(r, dict):
            continue
        ped = sd(date_str)
        if not ped:
            continue

        ta   = sm(r.get("totalAssets"))
        tl   = sm(r.get("totalLiab"))
        te   = sm(r.get("totalStockholderEquity"))
        cash = sm(r.get("cash"))
        ltd  = sm(r.get("longTermDebt"))
        std  = sm(r.get("shortTermDebt"))
        gw   = sm(r.get("goodWill"))
        intg = sm(r.get("intangibleAssets"))
        re_  = sm(r.get("retainedEarnings"))
        tca  = sm(r.get("totalCurrentAssets"))
        tcl  = sm(r.get("totalCurrentLiabilities"))
        rec  = sm(r.get("netReceivables"))
        inv  = sm(r.get("inventory"))
        prop = sm(r.get("propertyPlantEquipment") or r.get("netPPE"))
        nb   = sm(r.get("netTangibleAssets"))
        bvps = sf(r.get("bookValuePerShare"))
        deferred_rev = sm(r.get("deferredLongTermLiab") or r.get("otherLiab"))

        td = round((ltd or 0) + (std or 0), 4) if (ltd or std) else None
        nd = round(td - cash, 4) if (td and cash) else None
        wc = round(tca - tcl,  4) if (tca and tcl) else None

        rows.append({
            "asx_code":              asx_code,
            "fiscal_year":           fiscal_year(ped),
            "period_end_date":       ped,
            "cash_equivalents":      cash,
            "trade_receivables":     rec,
            "inventory":             inv,
            "total_current_assets":  tca,
            "total_assets":          ta,
            "short_term_debt":       std,
            "total_current_liab":    tcl,
            "long_term_debt":        ltd,
            "total_liabilities":     tl,
            "total_equity":          te,
            "retained_earnings":     re_,
            "goodwill":              gw,
            "intangibles":           intg,
            "total_debt":            td,
            "net_debt":              nd,
            "working_capital":       wc,
            "book_value_per_share":  bvps,
            "net_block":             prop,
            "net_tangible_assets":   nb,
            "data_source":           "eodhd",
        })
    return dedup_fy(rows)


def parse_annual_cf(asx_code: str, data: dict) -> list[dict]:
    section = data.get("Financials", {}).get("Cash_Flow", {})
    annual  = section.get("yearly") or section.get("annual") or {}
    if not annual or annual == "NA":
        return []

    rows = []
    for date_str, r in annual.items():
        if not isinstance(r, dict):
            continue
        ped = sd(date_str)
        if not ped:
            continue

        cfo  = sm(r.get("totalCashFromOperatingActivities"))
        capex = sm(r.get("capitalExpenditures"))
        cfi  = sm(r.get("totalCashFromInvestingActivities"))
        div  = sm(r.get("dividendsPaid"))
        cff  = sm(r.get("totalCashFromFinancingActivities"))
        ncash = sm(r.get("changeInCash") or r.get("netChangeInCash"))
        fcf  = sm(r.get("freeCashFlow"))
        dep  = sm(r.get("depreciation") or r.get("depreciationAndAmortization"))
        wcc  = sm(r.get("changeToWorkingCapital") or r.get("changeInWorkingCapital"))
        ni   = sm(r.get("netIncome") or r.get("changeToNetincome"))
        acq  = sm(r.get("acquisitionsNet") or r.get("acquisitions"))

        if fcf is None and cfo is not None and capex is not None:
            fcf = round(cfo + capex, 4)

        rows.append({
            "asx_code":               asx_code,
            "fiscal_year":            fiscal_year(ped),
            "period_end_date":        ped,
            "net_income":             ni,
            "depreciation_amort":     dep,
            "working_capital_changes": wcc,
            "cfo":                    cfo,
            "capex":                  capex,
            "acquisitions":           acq,
            "cfi":                    cfi,
            "dividends_paid":         div,
            "cff":                    cff,
            "net_change_in_cash":     ncash,
            "fcf":                    fcf,
            "data_source":            "eodhd",
        })
    return dedup_fy(rows)


def parse_annual_dps(data: dict) -> dict[int, float]:
    """Sum dividends per fiscal year → {fy: total_dps}."""
    divs = data.get("SplitsDividends", {}).get("Dividends", {})
    if not divs or divs == "NA":
        return {}
    annual: dict[int, float] = {}
    for date_str, d in divs.items():
        if not isinstance(d, dict):
            continue
        val = sf(d.get("value") or d.get("dividend") or d.get("unadjustedValue"))
        if val is None:
            continue
        dt = sd(date_str)
        if not dt:
            continue
        fy = fiscal_year(dt)
        annual[fy] = round((annual.get(fy) or 0) + val, 6)
    return annual


# ── Quarterly IS parser ───────────────────────────────────────────────────────

def parse_quarterly_pnl(asx_code: str, data: dict) -> list[dict]:
    section   = data.get("Financials", {}).get("Income_Statement", {})
    quarterly = section.get("quarterly") or {}
    if not quarterly or quarterly == "NA":
        return []

    rows = []
    for date_str, r in quarterly.items():
        if not isinstance(r, dict):
            continue
        ped = sd(date_str)
        if not ped:
            continue

        fy, q  = fy_quarter(ped)
        rev    = sm(r.get("totalRevenue"))
        gp     = sm(r.get("grossProfit"))
        ebit   = sm(r.get("operatingIncome"))
        ebitda = sm(r.get("ebitda"))
        dep    = sm(r.get("depreciationAndAmortization"))
        ni     = sm(r.get("netIncome"))
        tax    = sm(r.get("incomeTaxExpense"))
        int_   = sm(r.get("interestExpense"))
        eps    = sf(r.get("eps") or r.get("epsActual"))

        rows.append({
            "asx_code":        asx_code,
            "fiscal_year":     fy,
            "quarter":         q,
            "period_end_date": ped,
            "period_label":    f"Q{q} {fy}",
            "revenue":         rev,
            "gross_profit":    gp,
            "ebitda":          ebitda,
            "ebit":            ebit,
            "other_income":    None,
            "interest_expense": int_,
            "depreciation":    dep,
            "tax":             tax,
            "net_income":      ni,
            "extraordinary_items": None,
            "equity_capital":  None,
            "eps":             eps,
            "gross_margin":    margin(gp,  rev),
            "ebit_margin":     margin(ebit, rev),
            "net_margin":      margin(ni,   rev),
        })
    return dedup_fy_q(rows)


# ── Dividends parser ──────────────────────────────────────────────────────────

def parse_dividends(asx_code: str, data: dict) -> list[dict]:
    # The fundamentals endpoint does NOT include per-dividend history.
    # It only has summary fields (ForwardAnnualDividendRate, ExDividendDate, etc.)
    # Full dividend history is fetched separately via /div/{ticker} endpoint.
    # Use download_historical_dividends.py + load_dividends.py for that data.
    return []


# ── Splits parser ─────────────────────────────────────────────────────────────

def parse_splits(asx_code: str, data: dict) -> list[dict]:
    splits = data.get("SplitsDividends", {}).get("Splits", {})
    if not splits or splits == "NA":
        return []

    rows = []
    for date_str, s in splits.items():
        if not isinstance(s, dict):
            continue
        split_date = sd(date_str)
        if not split_date:
            continue

        ratio_str  = s.get("split") or s.get("splitFactor") or ""
        # Format is usually "2/1" or "1/2"
        ratio: Optional[float] = None
        if ratio_str and "/" in str(ratio_str):
            try:
                parts = str(ratio_str).split("/")
                ratio = round(float(parts[0]) / float(parts[1]), 6)
            except (ValueError, ZeroDivisionError):
                pass
        elif ratio_str:
            ratio = sf(ratio_str)

        rows.append({
            "asx_code":   asx_code,
            "split_date": split_date,
            "ratio":      ratio,
            "data_source": "eodhd",
        })
    return rows


# ── Analyst ratings parser ───────────────────────────────────────────────────

def parse_analyst_ratings(asx_code: str, data: dict) -> Optional[dict]:
    ar = data.get("AnalystRatings")
    if not ar or ar == "NA" or not isinstance(ar, dict):
        return None

    rating       = sf(ar.get("Rating"))
    target_price = sf(ar.get("TargetPrice"))
    strong_buy   = si(ar.get("StrongBuy"))
    buy          = si(ar.get("Buy"))
    hold         = si(ar.get("Hold"))
    sell         = si(ar.get("Sell"))
    strong_sell  = si(ar.get("StrongSell"))

    if all(v is None for v in (rating, target_price, strong_buy, buy, hold, sell, strong_sell)):
        return None

    return {
        "asx_code":    asx_code,
        "rating":      round(rating, 2) if rating else None,
        "target_price": round(target_price, 4) if target_price else None,
        "strong_buy":  strong_buy,
        "buy":         buy,
        "hold":        hold,
        "sell":        sell,
        "strong_sell": strong_sell,
        "data_source": "eodhd",
        "updated_at":  datetime.utcnow(),
    }


# ── Company info (SharesStats + General) ─────────────────────────────────────

def parse_company_update(asx_code: str, data: dict) -> Optional[dict]:
    """Extract fields to update in market.companies."""
    general = data.get("General") or {}
    ss      = data.get("SharesStats") or {}

    shares_out  = si(ss.get("SharesOutstanding") or general.get("SharesOutstanding"))
    shares_float = si(ss.get("SharesFloat"))
    pct_insider = sf(ss.get("PercentInsiders"))
    pct_inst    = sf(ss.get("PercentInstitutions"))
    website     = general.get("WebURL") or general.get("HomePage")
    description = general.get("Description")
    employees   = si(general.get("FullTimeEmployees"))
    fy_end      = si(general.get("FiscalYearEnd"))     # month number or name like "June"

    # Convert month name to number
    if isinstance(fy_end, str):
        months = {"january":1,"february":2,"march":3,"april":4,"may":5,"june":6,
                  "july":7,"august":8,"september":9,"october":10,"november":11,"december":12}
        fy_end = months.get(fy_end.lower())

    if all(v is None for v in (shares_out, shares_float, pct_insider, pct_inst,
                                website, description, employees, fy_end)):
        return None

    return {
        "asx_code":              asx_code,
        "shares_outstanding":    shares_out,
        "shares_float":          shares_float,
        "percent_insiders":      round(pct_insider, 2) if pct_insider else None,
        "percent_institutions":  round(pct_inst, 2)    if pct_inst    else None,
        "website":               website[:255] if website else None,
        "description":           description,
        "employee_count":        employees,
        "fiscal_year_end_month": fy_end,
    }


# ── Upsert functions ──────────────────────────────────────────────────────────

def upsert_annual_pnl(cur, rows: list[dict]):
    if not rows:
        return
    sql = """
        INSERT INTO financials.annual_pnl
            (asx_code, fiscal_year, period_end_date,
             revenue, gross_profit, ebitda, ebit, net_profit, pat,
             interest_expense, tax, depreciation,
             opm, npm, gpm, ebitda_margin, eps, eps_diluted, data_source)
        VALUES %s
        ON CONFLICT (asx_code, fiscal_year) DO UPDATE SET
            period_end_date  = EXCLUDED.period_end_date,
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
    vals = [(r["asx_code"], r["fiscal_year"], r["period_end_date"],
             r["revenue"], r["gross_profit"], r["ebitda"], r["ebit"],
             r["net_profit"], r["pat"], r["interest_expense"], r["tax"], r["depreciation"],
             r["opm"], r["npm"], r["gpm"], r["ebitda_margin"],
             r["eps"], r["eps_diluted"], r["data_source"]) for r in rows]
    execute_values(cur, sql, vals, page_size=100)


def upsert_annual_bs(cur, rows: list[dict]):
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
    vals = [(r["asx_code"], r["fiscal_year"], r["period_end_date"],
             r["cash_equivalents"], r["trade_receivables"], r["inventory"],
             r["total_current_assets"], r["total_assets"],
             r["short_term_debt"], r["total_current_liab"], r["long_term_debt"],
             r["total_liabilities"], r["total_equity"], r["retained_earnings"],
             r["goodwill"], r["intangibles"], r["total_debt"], r["net_debt"],
             r["working_capital"], r["book_value_per_share"], r["data_source"]) for r in rows]
    execute_values(cur, sql, vals, page_size=100)


def upsert_annual_cf(cur, rows: list[dict]):
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
    vals = [(r["asx_code"], r["fiscal_year"], r["period_end_date"],
             r["net_income"], r["depreciation_amort"], r["working_capital_changes"],
             r["cfo"], r["capex"], r["acquisitions"], r["cfi"],
             r["dividends_paid"], r["cff"], r["net_change_in_cash"],
             r["fcf"], r["data_source"]) for r in rows]
    execute_values(cur, sql, vals, page_size=100)


def update_dps(cur, asx_code: str, dps_by_fy: dict):
    for fy, dps in dps_by_fy.items():
        cur.execute("""
            UPDATE financials.annual_pnl SET dps = %s
            WHERE asx_code = %s AND fiscal_year = %s
        """, (dps, asx_code, fy))


def upsert_quarterly(cur, rows: list[dict]):
    if not rows:
        return
    sql = """
        INSERT INTO market.quarterly_metrics
            (asx_code, fiscal_year, quarter, period_end_date, period_label,
             revenue, gross_profit, ebitda, ebit, other_income,
             interest_expense, depreciation, tax, net_income,
             extraordinary_items, equity_capital, eps,
             gross_margin, ebit_margin, net_margin)
        VALUES %s
        ON CONFLICT (asx_code, fiscal_year, quarter) DO UPDATE SET
            period_end_date  = EXCLUDED.period_end_date,
            period_label     = EXCLUDED.period_label,
            revenue          = EXCLUDED.revenue,
            gross_profit     = EXCLUDED.gross_profit,
            ebitda           = EXCLUDED.ebitda,
            ebit             = EXCLUDED.ebit,
            interest_expense = EXCLUDED.interest_expense,
            depreciation     = EXCLUDED.depreciation,
            tax              = EXCLUDED.tax,
            net_income       = EXCLUDED.net_income,
            eps              = EXCLUDED.eps,
            gross_margin     = EXCLUDED.gross_margin,
            ebit_margin      = EXCLUDED.ebit_margin,
            net_margin       = EXCLUDED.net_margin
    """
    vals = [(r["asx_code"], r["fiscal_year"], r["quarter"],
             r["period_end_date"], r["period_label"],
             r["revenue"], r["gross_profit"], r["ebitda"], r["ebit"],
             r["other_income"], r["interest_expense"], r["depreciation"],
             r["tax"], r["net_income"], r["extraordinary_items"],
             r["equity_capital"], r["eps"],
             r["gross_margin"], r["ebit_margin"], r["net_margin"]) for r in rows]
    execute_values(cur, sql, vals, page_size=200)


def upsert_dividends(cur, rows: list[dict]):
    if not rows:
        return
    sql = """
        INSERT INTO market.dividends
            (asx_code, ex_date, payment_date, record_date, declared_date,
             amount, unadjusted_value, currency, div_type, data_source)
        VALUES %s
        ON CONFLICT (asx_code, ex_date) DO UPDATE SET
            payment_date     = EXCLUDED.payment_date,
            record_date      = EXCLUDED.record_date,
            declared_date    = EXCLUDED.declared_date,
            amount           = EXCLUDED.amount,
            unadjusted_value = EXCLUDED.unadjusted_value,
            currency         = EXCLUDED.currency,
            div_type         = EXCLUDED.div_type
    """
    vals = [(r["asx_code"], r["ex_date"], r["payment_date"], r["record_date"],
             r["declared_date"], r["amount"], r["unadjusted_value"],
             r["currency"], r["div_type"], r["data_source"]) for r in rows]
    execute_values(cur, sql, vals, page_size=500)


def upsert_splits(cur, rows: list[dict]):
    if not rows:
        return
    sql = """
        INSERT INTO market.splits (asx_code, split_date, ratio, data_source)
        VALUES %s
        ON CONFLICT (asx_code, split_date) DO UPDATE SET
            ratio       = EXCLUDED.ratio,
            data_source = EXCLUDED.data_source
    """
    vals = [(r["asx_code"], r["split_date"], r["ratio"], r["data_source"]) for r in rows]
    execute_values(cur, sql, vals, page_size=200)


def upsert_analyst_ratings(cur, row: dict):
    cur.execute("""
        INSERT INTO market.analyst_ratings
            (asx_code, rating, target_price, strong_buy, buy, hold, sell, strong_sell,
             data_source, updated_at)
        VALUES (%(asx_code)s, %(rating)s, %(target_price)s, %(strong_buy)s, %(buy)s,
                %(hold)s, %(sell)s, %(strong_sell)s, %(data_source)s, %(updated_at)s)
        ON CONFLICT (asx_code) DO UPDATE SET
            rating       = EXCLUDED.rating,
            target_price = EXCLUDED.target_price,
            strong_buy   = EXCLUDED.strong_buy,
            buy          = EXCLUDED.buy,
            hold         = EXCLUDED.hold,
            sell         = EXCLUDED.sell,
            strong_sell  = EXCLUDED.strong_sell,
            updated_at   = EXCLUDED.updated_at
    """, row)


def update_company(cur, row: dict):
    sets   = []
    params = {}
    for col in ("shares_outstanding", "shares_float", "percent_insiders",
                "percent_institutions", "website", "description",
                "employee_count", "fiscal_year_end_month"):
        if row.get(col) is not None:
            sets.append(f"{col} = %({col})s")
            params[col] = row[col]
    if not sets:
        return
    params["asx_code"] = row["asx_code"]
    cur.execute(
        f"UPDATE market.companies SET {', '.join(sets)}, updated_at = NOW() "
        f"WHERE asx_code = %(asx_code)s",
        params
    )


# ── Per-stock loader ──────────────────────────────────────────────────────────

def load_from_file(cur, path: Path) -> dict:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        data = json.load(f)

    asx_code = path.stem  # filename without .json.gz — wait, stem gives us the first extension removal

    # Handle double extension: BHP.json.gz → stem = 'BHP.json', we need 'BHP'
    code = path.name
    if code.endswith(".json.gz"):
        code = code[:-len(".json.gz")]

    counts = {}

    pnl_rows   = parse_annual_pnl(code, data)
    bs_rows    = parse_annual_bs(code, data)
    cf_rows    = parse_annual_cf(code, data)
    dps_by_fy  = parse_annual_dps(data)
    qpnl_rows  = parse_quarterly_pnl(code, data)
    div_rows   = parse_dividends(code, data)
    spl_rows   = parse_splits(code, data)
    ar_row     = parse_analyst_ratings(code, data)
    co_update  = parse_company_update(code, data)

    if pnl_rows:
        upsert_annual_pnl(cur, pnl_rows)
        counts["pnl"] = len(pnl_rows)
    if bs_rows:
        upsert_annual_bs(cur, bs_rows)
        counts["bs"] = len(bs_rows)
    if cf_rows:
        upsert_annual_cf(cur, cf_rows)
        counts["cf"] = len(cf_rows)
    if dps_by_fy and pnl_rows:
        update_dps(cur, code, dps_by_fy)
    if qpnl_rows:
        upsert_quarterly(cur, qpnl_rows)
        counts["quarterly"] = len(qpnl_rows)
    if div_rows:
        upsert_dividends(cur, div_rows)
        counts["dividends"] = len(div_rows)
    if spl_rows:
        upsert_splits(cur, spl_rows)
        counts["splits"] = len(spl_rows)
    if ar_row:
        upsert_analyst_ratings(cur, ar_row)
    if co_update:
        update_company(cur, co_update)

    return counts


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date",      help="Load from incremental/{date}/ folder")
    parser.add_argument("--codes",     nargs="+")
    parser.add_argument("--from-code", help="Resume from this code (historical only)")
    parser.add_argument("--limit",     type=int)
    args = parser.parse_args()

    # Determine source directory
    if args.date:
        src_dir = INCR_DIR / args.date
    else:
        src_dir = HIST_DIR

    if not src_dir.exists():
        print(f"ERROR: source directory not found: {src_dir}")
        print("Run download_historical_fundamentals.py first.")
        sys.exit(1)

    # Collect files to process
    if args.codes:
        files = [src_dir / f"{c.upper()}.json.gz" for c in args.codes
                 if (src_dir / f"{c.upper()}.json.gz").exists()]
    else:
        files = sorted(src_dir.glob("*.json.gz"))

    if args.from_code:
        files = [f for f in files if f.name >= f"{args.from_code.upper()}.json.gz"]
    if args.limit:
        files = files[:args.limit]

    total = len(files)
    log.info(f"Loading fundamentals from {src_dir}")
    log.info(f"  {total} files to process")

    conn = psycopg2.connect(DB_URL)
    cur  = conn.cursor()

    done = failed = 0
    total_pnl = total_bs = total_cf = total_q = total_div = 0

    for i, path in enumerate(files, 1):
        try:
            counts = load_from_file(cur, path)
            done += 1
            total_pnl += counts.get("pnl", 0)
            total_bs  += counts.get("bs", 0)
            total_cf  += counts.get("cf", 0)
            total_q   += counts.get("quarterly", 0)
            total_div += counts.get("dividends", 0)

        except Exception as e:
            conn.rollback()
            failed += 1
            log.warning(f"  {path.name}: {e}")
            continue

        if i % BATCH_COMMIT == 0:
            conn.commit()
            log.info(
                f"  [{i:4d}/{total}] {done} ok, {failed} err | "
                f"P&L:{total_pnl} BS:{total_bs} CF:{total_cf} "
                f"Q:{total_q} Div:{total_div}"
            )

    conn.commit()
    cur.close()
    conn.close()

    log.info("=" * 60)
    log.info(f"DONE — {done} loaded, {failed} errors")
    log.info(f"Rows: P&L={total_pnl}  BS={total_bs}  CF={total_cf}  "
             f"Quarterly={total_q}  Dividends={total_div}")


if __name__ == "__main__":
    main()
