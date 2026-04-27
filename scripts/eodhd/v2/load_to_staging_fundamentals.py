"""
Staging Load — Fundamentals
============================
Reads raw fundamentals files from the Raw Zone and loads them into:
  staging.fundamentals       (full JSON blob + key fields)
  staging.company_profile    (General section)
  staging.highlights         (Highlights section)
  staging.valuation          (Valuation section)
  staging.income_statement   (Financials.Income_Statement yearly + quarterly)
  staging.balance_sheet      (Financials.Balance_Sheet yearly + quarterly)
  staging.cash_flow          (Financials.Cash_Flow yearly + quarterly)
  staging.earnings           (Earnings.History)
  staging.analyst_ratings    (AnalystRatings)
  staging.shares_stats       (SharesStats)

NO business logic. Column names match EODHD fields (snake_case only).
All NULLs are passed through. No unit conversion.

Usage:
    python scripts/eodhd/v2/load_to_staging_fundamentals.py
    python scripts/eodhd/v2/load_to_staging_fundamentals.py --codes BHP CBA
    python scripts/eodhd/v2/load_to_staging_fundamentals.py --date 2026-04-27
    python scripts/eodhd/v2/load_to_staging_fundamentals.py --from-code WBC
"""

import gzip
import json
import logging
import os
import sys
import argparse
from datetime import datetime, date
from pathlib import Path
from typing import Optional

import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv()

DB_URL   = os.getenv("DATABASE_URL_SYNC",
             "postgresql://asx_user:asx_secure_2024@localhost:5432/asx_screener")
RAW_BASE = Path(os.getenv("RAW_DATA_DIR", "/opt/asx-screener/data/raw"))

FUND_DIR    = RAW_BASE / "eodhd" / "exchange=AU" / "fundamentals" / "full_snapshot"
BATCH_COMMIT = 50

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)


# ─── Type helpers (no transforms — just safe parsing) ─────────────────────────

def sf(v) -> Optional[float]:
    if v is None or v in ("", "None", "N/A", "NA", "-", "0.00%"):
        return None
    try:
        s = str(v).strip().rstrip("%")
        return float(s) if s else None
    except (TypeError, ValueError):
        return None

def si(v) -> Optional[int]:
    f = sf(v)
    return int(f) if f is not None else None

def sd(v) -> Optional[date]:
    if not v or str(v) in ("", "None", "NA", "0000-00-00", "N/A"):
        return None
    try:
        return datetime.strptime(str(v)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None

def st(v) -> Optional[str]:
    if v is None or str(v) in ("", "None", "N/A", "NA"):
        return None
    return str(v)[:2048]


# ─── Insert: staging.fundamentals ─────────────────────────────────────────────

def upsert_fundamentals(cur, asx_code: str, snapshot_date: date, raw_json: dict,
                         source_file: str, checksum: str) -> int:
    general = raw_json.get("General", {})

    # Mark previous rows for this code as not-latest
    cur.execute("""
        UPDATE staging.fundamentals SET is_latest = FALSE
        WHERE asx_code = %s AND is_latest = TRUE
          AND snapshot_date < %s
    """, (asx_code, snapshot_date))

    cur.execute("""
        INSERT INTO staging.fundamentals
            (asx_code, snapshot_date, raw_json, general_code, general_name,
             general_sector, general_industry, updated_at_eodhd,
             source_file, checksum, is_latest, is_archived)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,TRUE,FALSE)
        ON CONFLICT (asx_code, snapshot_date, source_file) DO UPDATE SET
            raw_json         = EXCLUDED.raw_json,
            general_code     = EXCLUDED.general_code,
            general_name     = EXCLUDED.general_name,
            general_sector   = EXCLUDED.general_sector,
            general_industry = EXCLUDED.general_industry,
            updated_at_eodhd = EXCLUDED.updated_at_eodhd,
            checksum         = EXCLUDED.checksum,
            is_latest        = TRUE
        RETURNING id
    """, (
        asx_code, snapshot_date, json.dumps(raw_json),
        st(general.get("Code")), st(general.get("Name")),
        st(general.get("Sector")), st(general.get("Industry")),
        sd(general.get("UpdatedAt")),
        source_file, checksum,
    ))
    row = cur.fetchone()
    return row[0] if row else None


# ─── Insert: staging.company_profile ──────────────────────────────────────────

def upsert_company_profile(cur, asx_code: str, snapshot_date: date,
                            general: dict, fund_id: int) -> None:
    cur.execute("""
        UPDATE staging.company_profile SET is_latest = FALSE
        WHERE asx_code = %s AND is_latest = TRUE AND snapshot_date < %s
    """, (asx_code, snapshot_date))

    cur.execute("""
        INSERT INTO staging.company_profile
            (asx_code, snapshot_date, code, type, name, exchange, currency_code,
             country_name, isin, cusip, cik, employer_id_number, fiscal_year_end,
             ipo_date, sector, industry, gic_sector, gic_group, gic_industry,
             gic_sub_industry, description, address, phone, web_url,
             full_time_employees, updated_at, source_fundamentals_id, is_latest)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,TRUE)
        ON CONFLICT (asx_code, snapshot_date) DO UPDATE SET
            code = EXCLUDED.code, name = EXCLUDED.name, type = EXCLUDED.type,
            sector = EXCLUDED.sector, industry = EXCLUDED.industry,
            updated_at = EXCLUDED.updated_at, is_latest = TRUE
    """, (
        asx_code, snapshot_date,
        st(general.get("Code")), st(general.get("Type")), st(general.get("Name")),
        st(general.get("Exchange")), st(general.get("CurrencyCode")),
        st(general.get("CountryName")), st(general.get("ISIN")),
        st(general.get("CUSIP")), st(general.get("CIK")),
        st(general.get("EmployerIdNumber")), st(general.get("FiscalYearEnd")),
        sd(general.get("IPODate")),
        st(general.get("Sector")), st(general.get("Industry")),
        st(general.get("GicSector")), st(general.get("GicGroup")),
        st(general.get("GicIndustry")), st(general.get("GicSubIndustry")),
        st(general.get("Description")), st(general.get("Address")),
        st(general.get("Phone")), st(general.get("WebURL")),
        si(general.get("FullTimeEmployees")),
        sd(general.get("UpdatedAt")), fund_id,
    ))


# ─── Insert: staging.highlights ───────────────────────────────────────────────

def upsert_highlights(cur, asx_code: str, snapshot_date: date,
                       h: dict, fund_id: int) -> None:
    cur.execute("""
        UPDATE staging.highlights SET is_latest = FALSE
        WHERE asx_code = %s AND is_latest = TRUE AND snapshot_date < %s
    """, (asx_code, snapshot_date))

    cur.execute("""
        INSERT INTO staging.highlights
            (asx_code, snapshot_date,
             market_capitalization, ebitda, pe_ratio, peg_ratio,
             wall_street_target_price, book_value, dividend_share, dividend_yield,
             earnings_share, eps_estimate_current_year, eps_estimate_next_year,
             eps_estimate_next_quarter, revenue_per_share_ttm, profit_margin,
             operating_margin_ttm, return_on_assets_ttm, return_on_equity_ttm,
             revenue_ttm, gross_profit_ttm, diluted_eps_ttm,
             quarterly_earnings_growth_yoy, quarterly_revenue_growth_yoy,
             most_recent_quarter, source_fundamentals_id, is_latest)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,TRUE)
        ON CONFLICT (asx_code, snapshot_date) DO UPDATE SET
            market_capitalization = EXCLUDED.market_capitalization,
            pe_ratio = EXCLUDED.pe_ratio, dividend_yield = EXCLUDED.dividend_yield,
            is_latest = TRUE
    """, (
        asx_code, snapshot_date,
        sf(h.get("MarketCapitalization")), sf(h.get("EBITDA")),
        sf(h.get("PERatio")), sf(h.get("PEGRatio")),
        sf(h.get("WallStreetTargetPrice")), sf(h.get("BookValue")),
        sf(h.get("DividendShare")), sf(h.get("DividendYield")),
        sf(h.get("EarningsShare")), sf(h.get("EPSEstimateCurrentYear")),
        sf(h.get("EPSEstimateNextYear")), sf(h.get("EPSEstimateNextQuarter")),
        sf(h.get("RevenuePerShareTTM")), sf(h.get("ProfitMargin")),
        sf(h.get("OperatingMarginTTM")), sf(h.get("ReturnOnAssetsTTM")),
        sf(h.get("ReturnOnEquityTTM")), sf(h.get("RevenueTTM")),
        sf(h.get("GrossProfitTTM")), sf(h.get("DilutedEpsTTM")),
        sf(h.get("QuarterlyEarningsGrowthYOY")), sf(h.get("QuarterlyRevenueGrowthYOY")),
        sd(h.get("MostRecentQuarter")), fund_id,
    ))


# ─── Insert: staging.valuation ────────────────────────────────────────────────

def upsert_valuation(cur, asx_code: str, snapshot_date: date,
                      v: dict, fund_id: int) -> None:
    cur.execute("""
        UPDATE staging.valuation SET is_latest = FALSE
        WHERE asx_code = %s AND is_latest = TRUE AND snapshot_date < %s
    """, (asx_code, snapshot_date))

    cur.execute("""
        INSERT INTO staging.valuation
            (asx_code, snapshot_date, trailing_pe, forward_pe, price_sales_ttm,
             price_book_mrq, enterprise_value, enterprise_value_revenue,
             enterprise_value_ebitda, source_fundamentals_id, is_latest)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,TRUE)
        ON CONFLICT (asx_code, snapshot_date) DO UPDATE SET
            trailing_pe = EXCLUDED.trailing_pe, is_latest = TRUE
    """, (
        asx_code, snapshot_date,
        sf(v.get("TrailingPE")), sf(v.get("ForwardPE")),
        sf(v.get("PriceSalesTTM")), sf(v.get("PriceBookMRQ")),
        sf(v.get("EnterpriseValue")), sf(v.get("EnterpriseValueRevenue")),
        sf(v.get("EnterpriseValueEbitda")), fund_id,
    ))


# ─── Insert: staging.analyst_ratings ─────────────────────────────────────────

def upsert_analyst_ratings(cur, asx_code: str, snapshot_date: date,
                             ar: dict, fund_id: int) -> None:
    cur.execute("""
        UPDATE staging.analyst_ratings SET is_latest = FALSE
        WHERE asx_code = %s AND is_latest = TRUE AND snapshot_date < %s
    """, (asx_code, snapshot_date))

    cur.execute("""
        INSERT INTO staging.analyst_ratings
            (asx_code, snapshot_date, rating, target_price,
             strong_buy, buy, hold, sell, strong_sell,
             source_fundamentals_id, is_latest)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,TRUE)
        ON CONFLICT (asx_code, snapshot_date) DO UPDATE SET
            rating = EXCLUDED.rating, target_price = EXCLUDED.target_price,
            is_latest = TRUE
    """, (
        asx_code, snapshot_date,
        sf(ar.get("Rating")), sf(ar.get("TargetPrice")),
        si(ar.get("StrongBuy")), si(ar.get("Buy")),
        si(ar.get("Hold")), si(ar.get("Sell")), si(ar.get("StrongSell")),
        fund_id,
    ))


# ─── Insert: staging.shares_stats ─────────────────────────────────────────────

def upsert_shares_stats(cur, asx_code: str, snapshot_date: date,
                         ss: dict, fund_id: int) -> None:
    cur.execute("""
        UPDATE staging.shares_stats SET is_latest = FALSE
        WHERE asx_code = %s AND is_latest = TRUE AND snapshot_date < %s
    """, (asx_code, snapshot_date))

    cur.execute("""
        INSERT INTO staging.shares_stats
            (asx_code, snapshot_date, shares_outstanding, shares_float,
             percent_insiders, percent_institutions, shares_short,
             short_ratio, short_percent_outstanding, short_percent_float,
             source_fundamentals_id, is_latest)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,TRUE)
        ON CONFLICT (asx_code, snapshot_date) DO UPDATE SET
            shares_outstanding = EXCLUDED.shares_outstanding, is_latest = TRUE
    """, (
        asx_code, snapshot_date,
        sf(ss.get("SharesOutstanding")), sf(ss.get("SharesFloat")),
        sf(ss.get("PercentInsiders")), sf(ss.get("PercentInstitutions")),
        sf(ss.get("SharesShort")), sf(ss.get("ShortRatio")),
        sf(ss.get("ShortPercentOutstanding")), sf(ss.get("ShortPercentFloat")),
        fund_id,
    ))


# ─── Insert: staging.income_statement ─────────────────────────────────────────

def upsert_income_statement(cur, asx_code: str, periods: dict,
                             period_type: str, fund_id: int) -> int:
    rows = []
    for period_date_str, rec in periods.items():
        if not isinstance(rec, dict):
            continue
        dt = sd(period_date_str)
        if not dt:
            continue
        rows.append((
            asx_code, dt, period_type,
            sf(rec.get("totalRevenue")), sf(rec.get("costOfRevenue")),
            sf(rec.get("grossProfit")), sf(rec.get("totalOperatingExpenses")),
            sf(rec.get("operatingIncome")), sf(rec.get("ebitda")),
            sf(rec.get("interestExpense")), sf(rec.get("incomeBeforeTax")),
            sf(rec.get("incomeTaxExpense")), sf(rec.get("netIncome")),
            sf(rec.get("eps")), sf(rec.get("epsDiluted")),
            sf(rec.get("depreciationAndAmortization")),
            fund_id,
        ))
    if not rows:
        return 0
    execute_values(cur, """
        INSERT INTO staging.income_statement
            (asx_code, date, period_type,
             total_revenue, cost_of_revenue, gross_profit,
             total_operating_expenses, operating_income, ebitda,
             interest_expense, income_before_tax, income_tax_expense,
             net_income, eps, eps_diluted, depreciation_amortization,
             source_fundamentals_id)
        VALUES %s
        ON CONFLICT (asx_code, date, period_type) DO UPDATE SET
            total_revenue = EXCLUDED.total_revenue,
            net_income    = EXCLUDED.net_income,
            is_latest     = TRUE
    """, rows, page_size=200)
    return len(rows)


# ─── Insert: staging.balance_sheet ────────────────────────────────────────────

def upsert_balance_sheet(cur, asx_code: str, periods: dict,
                          period_type: str, fund_id: int) -> int:
    rows = []
    for period_date_str, rec in periods.items():
        if not isinstance(rec, dict):
            continue
        dt = sd(period_date_str)
        if not dt:
            continue
        rows.append((
            asx_code, dt, period_type,
            sf(rec.get("totalAssets")), sf(rec.get("totalCurrentAssets")),
            sf(rec.get("cashAndShortTermInvestments")), sf(rec.get("netReceivables")),
            sf(rec.get("inventory")), sf(rec.get("totalNonCurrentAssets")),
            sf(rec.get("propertyPlantEquipmentNet")),
            sf(rec.get("goodWill")), sf(rec.get("intangibleAssets")),
            sf(rec.get("totalLiab")), sf(rec.get("totalCurrentLiabilities")),
            sf(rec.get("shortLongTermDebtTotal")), sf(rec.get("longTermDebt")),
            sf(rec.get("totalStockholderEquity")), sf(rec.get("retainedEarnings")),
            sf(rec.get("commonStock")),
            fund_id,
        ))
    if not rows:
        return 0
    execute_values(cur, """
        INSERT INTO staging.balance_sheet
            (asx_code, date, period_type,
             total_assets, total_current_assets,
             cash_and_short_term_investments, net_receivables, inventory,
             total_non_current_assets, property_plant_equipment_net,
             goodwill, intangible_assets,
             total_liabilities, total_current_liabilities,
             short_long_term_debt_total, long_term_debt,
             total_stockholder_equity, retained_earnings, common_stock,
             source_fundamentals_id)
        VALUES %s
        ON CONFLICT (asx_code, date, period_type) DO UPDATE SET
            total_assets = EXCLUDED.total_assets,
            total_stockholder_equity = EXCLUDED.total_stockholder_equity
    """, rows, page_size=200)
    return len(rows)


# ─── Insert: staging.cash_flow ────────────────────────────────────────────────

def upsert_cash_flow(cur, asx_code: str, periods: dict,
                      period_type: str, fund_id: int) -> int:
    rows = []
    for period_date_str, rec in periods.items():
        if not isinstance(rec, dict):
            continue
        dt = sd(period_date_str)
        if not dt:
            continue
        rows.append((
            asx_code, dt, period_type,
            sf(rec.get("totalCashFromOperatingActivities")),
            sf(rec.get("capitalExpenditures")),
            sf(rec.get("totalCashflowsFromInvestingActivities")),
            sf(rec.get("totalCashFromFinancingActivities")),
            sf(rec.get("dividendsPaid")),
            sf(rec.get("changeInCash")),
            sf(rec.get("freeCashFlow")),
            fund_id,
        ))
    if not rows:
        return 0
    execute_values(cur, """
        INSERT INTO staging.cash_flow
            (asx_code, date, period_type,
             total_cash_from_operating_activities, capital_expenditures,
             total_cash_from_investing_activities,
             total_cash_from_financing_activities,
             dividends_paid, change_to_cash, free_cash_flow,
             source_fundamentals_id)
        VALUES %s
        ON CONFLICT (asx_code, date, period_type) DO UPDATE SET
            total_cash_from_operating_activities =
                EXCLUDED.total_cash_from_operating_activities,
            free_cash_flow = EXCLUDED.free_cash_flow
    """, rows, page_size=200)
    return len(rows)


# ─── Insert: staging.earnings ─────────────────────────────────────────────────

def upsert_earnings(cur, asx_code: str, history: dict, fund_id: int) -> int:
    rows = []
    for period_date_str, rec in history.items():
        if not isinstance(rec, dict):
            continue
        dt = sd(period_date_str)
        if not dt:
            continue
        rows.append((
            asx_code, dt, "actual",
            sf(rec.get("epsActual")), sf(rec.get("epsEstimate")),
            sf(rec.get("epsDifference")), sf(rec.get("surprisePercent")),
            fund_id,
        ))
    if not rows:
        return 0
    execute_values(cur, """
        INSERT INTO staging.earnings
            (asx_code, date, period_type,
             eps_actual, eps_estimate, eps_difference, surprise_percent,
             source_fundamentals_id)
        VALUES %s
        ON CONFLICT (asx_code, date, period_type) DO UPDATE SET
            eps_actual = EXCLUDED.eps_actual,
            surprise_percent = EXCLUDED.surprise_percent
    """, rows, page_size=200)
    return len(rows)


# ─── Process one file ─────────────────────────────────────────────────────────

def load_file(cur, path: Path) -> dict[str, int]:
    # Extract code and date from filename: {CODE}.AU_{YYYY-MM-DD}.json.gz
    stem = path.name[:-len(".json.gz")]
    parts = stem.split("_")
    code_part = parts[0]   # e.g. "BHP.AU"
    date_part = parts[1] if len(parts) > 1 else ""
    asx_code = code_part.replace(".AU", "")
    snapshot_date = datetime.strptime(date_part[:10], "%Y-%m-%d").date() \
                    if date_part else date.today()

    with gzip.open(path, "rt", encoding="utf-8") as f:
        raw = json.load(f)

    if not isinstance(raw, dict) or not raw:
        return {}

    import hashlib
    checksum = hashlib.sha256(path.read_bytes()).hexdigest()

    fund_id = upsert_fundamentals(cur, asx_code, snapshot_date, raw,
                                   path.name, checksum)
    if fund_id is None:
        return {}

    counts: dict[str, int] = {"fundamentals": 1}

    general = raw.get("General", {})
    if general:
        upsert_company_profile(cur, asx_code, snapshot_date, general, fund_id)
        counts["company_profile"] = 1

    highlights = raw.get("Highlights", {})
    if highlights:
        upsert_highlights(cur, asx_code, snapshot_date, highlights, fund_id)
        counts["highlights"] = 1

    valuation = raw.get("Valuation", {})
    if valuation:
        upsert_valuation(cur, asx_code, snapshot_date, valuation, fund_id)
        counts["valuation"] = 1

    ar = raw.get("AnalystRatings", {})
    if ar:
        upsert_analyst_ratings(cur, asx_code, snapshot_date, ar, fund_id)
        counts["analyst_ratings"] = 1

    ss = raw.get("SharesStats", {})
    if ss:
        upsert_shares_stats(cur, asx_code, snapshot_date, ss, fund_id)
        counts["shares_stats"] = 1

    fin = raw.get("Financials", {})
    if fin:
        is_ = fin.get("Income_Statement", {})
        for ptype in ("yearly", "quarterly"):
            periods = is_.get(ptype, {})
            if isinstance(periods, dict):
                n = upsert_income_statement(cur, asx_code, periods, ptype, fund_id)
                counts[f"income_{ptype}"] = n

        bs = fin.get("Balance_Sheet", {})
        for ptype in ("yearly", "quarterly"):
            periods = bs.get(ptype, {})
            if isinstance(periods, dict):
                n = upsert_balance_sheet(cur, asx_code, periods, ptype, fund_id)
                counts[f"balance_{ptype}"] = n

        cf = fin.get("Cash_Flow", {})
        for ptype in ("yearly", "quarterly"):
            periods = cf.get(ptype, {})
            if isinstance(periods, dict):
                n = upsert_cash_flow(cur, asx_code, periods, ptype, fund_id)
                counts[f"cashflow_{ptype}"] = n

    earnings = raw.get("Earnings", {})
    history  = earnings.get("History", {}) if isinstance(earnings, dict) else {}
    if isinstance(history, dict) and history:
        n = upsert_earnings(cur, asx_code, history, fund_id)
        counts["earnings"] = n

    return counts


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--codes",     nargs="+")
    parser.add_argument("--from-code")
    parser.add_argument("--limit",     type=int)
    parser.add_argument("--date",      help="Only load files from this date YYYY-MM-DD")
    args = parser.parse_args()

    if not FUND_DIR.exists():
        print(f"ERROR: {FUND_DIR} not found. Run download_fundamentals.py first.")
        sys.exit(1)

    # Build file list
    if args.codes:
        if args.date:
            files = [FUND_DIR / f"{c.upper()}.AU_{args.date}.json.gz" for c in args.codes]
        else:
            files = []
            for c in args.codes:
                files.extend(sorted(FUND_DIR.glob(f"{c.upper()}.AU_*.json.gz")))
    elif args.date:
        files = sorted(FUND_DIR.glob(f"*.AU_{args.date}.json.gz"))
    else:
        files = sorted(FUND_DIR.glob("*.json.gz"))

    files = [f for f in files if f.exists()]

    if args.from_code:
        files = [f for f in files
                 if f.name >= f"{args.from_code.upper()}.AU"]
    if args.limit:
        files = files[:args.limit]

    total = len(files)
    log.info(f"Loading {total} fundamentals files from {FUND_DIR}")

    conn = psycopg2.connect(DB_URL)
    cur  = conn.cursor()
    done = failed = 0

    for i, path in enumerate(files, 1):
        try:
            counts = load_file(cur, path)
            if counts:
                done += 1
        except Exception as e:
            conn.rollback()
            failed += 1
            log.warning(f"  {path.name}: {e}")
            continue

        if i % BATCH_COMMIT == 0:
            conn.commit()
            log.info(f"  [{i:4d}/{total}]  ok={done}  err={failed}")

    conn.commit()
    cur.close()
    conn.close()
    log.info(f"DONE — {done} files loaded, {failed} errors")


if __name__ == "__main__":
    main()
