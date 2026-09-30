"""
Staging Load — Fundamentals
============================
Reads raw fundamentals files from the Raw Zone and loads them into:
  staging_au.fundamentals       (full JSON blob + key fields)
  staging_au.company_profile    (General section)
  staging_au.highlights         (Highlights section)
  staging_au.valuation          (Valuation section)
  staging_au.income_statement   (Financials.Income_Statement yearly + quarterly)
  staging_au.balance_sheet      (Financials.Balance_Sheet yearly + quarterly)
  staging_au.cash_flow          (Financials.Cash_Flow yearly + quarterly)
  staging_au.earnings           (Earnings.History)
  staging_au.analyst_ratings    (AnalystRatings)
  staging_au.shares_stats       (SharesStats)

Design: TRUNCATE AND RELOAD
  A full run truncates all fundamentals-derived staging tables before loading.
  Staging always holds the latest snapshot only — history lives in Raw Zone files.
  Partial runs (--codes / --date) do NOT truncate; they upsert into the live table.

NO business logic. Column names match EODHD fields (snake_case only).
All NULLs are passed through. No unit conversion.

Usage:
    # Full reload (truncates first)
    python scripts/eodhd/v2/load_to_staging_fundamentals.py

    # Partial — specific stocks (no truncate)
    python scripts/eodhd/v2/load_to_staging_fundamentals.py --codes BHP CBA

    # Partial — specific date snapshot (no truncate)
    python scripts/eodhd/v2/load_to_staging_fundamentals.py --date 2026-04-27

    # Resume from code (no truncate)
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

# The database credential lives in the environment, never in source.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from app.core.db import get_database_url_sync  # noqa: E402


load_dotenv()

DB_URL = get_database_url_sync()
RAW_BASE = Path(os.getenv("RAW_DATA_DIR", "/opt/asx-screener/data/raw"))

FUND_DIR    = RAW_BASE / "eodhd" / "exchange=AU" / "fundamentals" / "full_snapshot"
BATCH_COMMIT = 50

# The schema's numeric columns are sized for AUD. A statement reported in
# rupiah is ~10^6 times larger and overflows them -- which is how ATM (Aneka
# Tambang, an Indonesian listing) failed ten snapshots on 30 Sep 2026 and,
# before per-file savepoints existed, took ATH and ATHDA down with it.
#
# Do NOT "fix" this by widening the column. ATM's stated revenue is
# 88,851,053,565,000.00 IDR; stored in a wider column it would sit beside
# AUD revenues and dominate every size-ranked screen -- silently, and
# wrongly. The overflow was accidentally protective. Comparability, not
# capacity, is what is missing.
#
# Rejecting here is the honest model: a rupiah-denominated income statement
# is not a value this loader failed to obtain, it is a value that cannot
# exist in the terms this schema holds. That is an explained absence, and it
# is counted as one.
REPORTING_CURRENCY = "AUD"


class ForeignCurrency(Exception):
    """Statements denominated in something this schema cannot represent."""


def period_key(period_date_str, rec):
    """The source-stated period this record will be filed under, or None.

    One definition, used both by the upserts that admit records and by the
    population proof that counts them, because a proof that re-implements the
    admission test is a proof that can drift away from what actually happened.

    Before this existed, each section dropped unparseable periods with a bare
    `continue`. A file could lose half its years and still be counted as
    loaded -- a within-file loss that a file-grain proof cannot see, which is
    why the proof is keyed at (file, section, period) rather than at the file.
    """
    if not isinstance(rec, dict):
        return None
    return sd(period_date_str)

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


# ─── Insert: staging_au.fundamentals ─────────────────────────────────────────────

def upsert_fundamentals(cur, asx_code: str, snapshot_date: date, raw_json: dict,
                         source_file: str, checksum: str) -> int:
    general = raw_json.get("General", {})
    cur.execute("""
        INSERT INTO staging_au.fundamentals
            (asx_code, snapshot_date, raw_json, general_code, general_name,
             general_sector, general_industry, updated_at_eodhd,
             source_file, checksum)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (asx_code) DO UPDATE SET
            snapshot_date    = EXCLUDED.snapshot_date,
            raw_json         = EXCLUDED.raw_json,
            general_code     = EXCLUDED.general_code,
            general_name     = EXCLUDED.general_name,
            general_sector   = EXCLUDED.general_sector,
            general_industry = EXCLUDED.general_industry,
            updated_at_eodhd = EXCLUDED.updated_at_eodhd,
            source_file      = EXCLUDED.source_file,
            checksum         = EXCLUDED.checksum,
            loaded_at        = NOW()
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


# ─── Insert: staging_au.company_profile ──────────────────────────────────────────

def upsert_company_profile(cur, asx_code: str, snapshot_date: date,
                            general: dict, fund_id: int) -> None:
    cur.execute("""
        INSERT INTO staging_au.company_profile
            (asx_code, snapshot_date, code, type, name, exchange, currency_code,
             country_name, isin, cusip, cik, employer_id_number, fiscal_year_end,
             ipo_date, sector, industry, gic_sector, gic_group, gic_industry,
             gic_sub_industry, description, address, phone, web_url,
             full_time_employees, updated_at, source_file)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (asx_code) DO UPDATE SET
            snapshot_date = EXCLUDED.snapshot_date,
            code = EXCLUDED.code, name = EXCLUDED.name, type = EXCLUDED.type,
            sector = EXCLUDED.sector, industry = EXCLUDED.industry,
            updated_at = EXCLUDED.updated_at, loaded_at = NOW()
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


# ─── Insert: staging_au.highlights ───────────────────────────────────────────────

def upsert_highlights(cur, asx_code: str, snapshot_date: date,
                       h: dict, fund_id: int) -> None:
    cur.execute("""
        INSERT INTO staging_au.highlights
            (asx_code, snapshot_date,
             market_capitalization, ebitda, pe_ratio, peg_ratio,
             wall_street_target_price, book_value, dividend_share, dividend_yield,
             earnings_share, eps_estimate_current_year, eps_estimate_next_year,
             eps_estimate_next_quarter, revenue_per_share_ttm, profit_margin,
             operating_margin_ttm, return_on_assets_ttm, return_on_equity_ttm,
             revenue_ttm, gross_profit_ttm, diluted_eps_ttm,
             quarterly_earnings_growth_yoy, quarterly_revenue_growth_yoy,
             most_recent_quarter, source_file)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (asx_code) DO UPDATE SET
            snapshot_date = EXCLUDED.snapshot_date,
            market_capitalization = EXCLUDED.market_capitalization,
            pe_ratio = EXCLUDED.pe_ratio, dividend_yield = EXCLUDED.dividend_yield,
            loaded_at = NOW()
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


# ─── Insert: staging_au.valuation ────────────────────────────────────────────────

def upsert_valuation(cur, asx_code: str, snapshot_date: date,
                      v: dict, fund_id: int) -> None:
    cur.execute("""
        INSERT INTO staging_au.valuation
            (asx_code, snapshot_date, trailing_pe, forward_pe, price_sales_ttm,
             price_book_mrq, enterprise_value, enterprise_value_revenue,
             enterprise_value_ebitda, source_file)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (asx_code) DO UPDATE SET
            snapshot_date = EXCLUDED.snapshot_date,
            trailing_pe = EXCLUDED.trailing_pe,
            enterprise_value = EXCLUDED.enterprise_value,
            loaded_at = NOW()
    """, (
        asx_code, snapshot_date,
        sf(v.get("TrailingPE")), sf(v.get("ForwardPE")),
        sf(v.get("PriceSalesTTM")), sf(v.get("PriceBookMRQ")),
        sf(v.get("EnterpriseValue")), sf(v.get("EnterpriseValueRevenue")),
        sf(v.get("EnterpriseValueEbitda")), None,
    ))


# ─── Insert: staging_au.analyst_ratings ─────────────────────────────────────────

def upsert_analyst_ratings(cur, asx_code: str, snapshot_date: date,
                             ar: dict, fund_id: int) -> None:
    cur.execute("""
        INSERT INTO staging_au.analyst_ratings
            (asx_code, snapshot_date, rating, target_price,
             strong_buy, buy, hold, sell, strong_sell, source_file)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (asx_code) DO UPDATE SET
            snapshot_date = EXCLUDED.snapshot_date,
            rating        = EXCLUDED.rating,
            target_price  = EXCLUDED.target_price,
            strong_buy    = EXCLUDED.strong_buy,
            buy           = EXCLUDED.buy,
            hold          = EXCLUDED.hold,
            sell          = EXCLUDED.sell,
            strong_sell   = EXCLUDED.strong_sell,
            loaded_at     = NOW()
    """, (
        asx_code, snapshot_date,
        sf(ar.get("Rating")), sf(ar.get("TargetPrice")),
        si(ar.get("StrongBuy")), si(ar.get("Buy")),
        si(ar.get("Hold")), si(ar.get("Sell")), si(ar.get("StrongSell")),
        None,
    ))


# ─── Insert: staging_au.shares_stats ─────────────────────────────────────────────

def upsert_shares_stats(cur, asx_code: str, snapshot_date: date,
                         ss: dict, fund_id: int) -> None:
    cur.execute("""
        INSERT INTO staging_au.shares_stats
            (asx_code, snapshot_date, shares_outstanding, shares_float,
             percent_insiders, percent_institutions, shares_short,
             short_ratio, short_percent_outstanding, short_percent_float,
             source_file)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (asx_code) DO UPDATE SET
            snapshot_date = EXCLUDED.snapshot_date,
            shares_outstanding = EXCLUDED.shares_outstanding,
            loaded_at = NOW()
    """, (
        asx_code, snapshot_date,
        sf(ss.get("SharesOutstanding")), sf(ss.get("SharesFloat")),
        sf(ss.get("PercentInsiders")), sf(ss.get("PercentInstitutions")),
        sf(ss.get("SharesShort")), sf(ss.get("ShortRatio")),
        sf(ss.get("ShortPercentOutstanding")), sf(ss.get("ShortPercentFloat")),
        None,
    ))


# ─── Insert: staging_au.income_statement ─────────────────────────────────────────

def upsert_income_statement(cur, asx_code: str, periods: dict,
                             period_type: str, fund_id: int) -> int:
    rows = []
    for period_date_str, rec in periods.items():
        dt = period_key(period_date_str, rec)
        if dt is None:
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
        ))
    if not rows:
        return 0
    execute_values(cur, """
        INSERT INTO staging_au.income_statement
            (asx_code, date, period_type,
             total_revenue, cost_of_revenue, gross_profit,
             total_operating_expenses, operating_income, ebitda,
             interest_expense, income_before_tax, income_tax_expense,
             net_income, eps, eps_diluted, depreciation_amortization)
        VALUES %s
        ON CONFLICT (asx_code, date, period_type) DO UPDATE SET
            total_revenue = EXCLUDED.total_revenue,
            net_income    = EXCLUDED.net_income
    """, rows, page_size=200)
    return len(rows)


# ─── Insert: staging_au.balance_sheet ────────────────────────────────────────────

def upsert_balance_sheet(cur, asx_code: str, periods: dict,
                          period_type: str, fund_id: int) -> int:
    rows = []
    for period_date_str, rec in periods.items():
        dt = period_key(period_date_str, rec)
        if dt is None:
            continue
        rows.append((
            asx_code, dt, period_type,
            sf(rec.get("totalAssets")), sf(rec.get("totalCurrentAssets")),
            sf(rec.get("cashAndShortTermInvestments")), sf(rec.get("netReceivables")),
            sf(rec.get("inventory")), sf(rec.get("totalNonCurrentAssets")),
            sf(rec.get("propertyPlantEquipment") or rec.get("propertyPlantEquipmentNet")),
            sf(rec.get("goodWill")), sf(rec.get("intangibleAssets")),
            sf(rec.get("totalLiab")), sf(rec.get("totalCurrentLiabilities")),
            sf(rec.get("shortLongTermDebtTotal")), sf(rec.get("longTermDebt")),
            sf(rec.get("totalStockholderEquity")), sf(rec.get("retainedEarnings")),
            sf(rec.get("commonStock")),
        ))
    if not rows:
        return 0
    execute_values(cur, """
        INSERT INTO staging_au.balance_sheet
            (asx_code, date, period_type,
             total_assets, total_current_assets,
             cash_and_short_term_investments, net_receivables, inventory,
             total_non_current_assets, property_plant_equipment_net,
             goodwill, intangible_assets,
             total_liabilities, total_current_liabilities,
             short_long_term_debt_total, long_term_debt,
             total_stockholder_equity, retained_earnings, common_stock)
        VALUES %s
        ON CONFLICT (asx_code, date, period_type) DO UPDATE SET
            total_assets = EXCLUDED.total_assets,
            total_stockholder_equity = EXCLUDED.total_stockholder_equity
    """, rows, page_size=200)
    return len(rows)


# ─── Insert: staging_au.cash_flow ────────────────────────────────────────────────

def upsert_cash_flow(cur, asx_code: str, periods: dict,
                      period_type: str, fund_id: int) -> int:
    rows = []
    for period_date_str, rec in periods.items():
        dt = period_key(period_date_str, rec)
        if dt is None:
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
        ))
    if not rows:
        return 0
    execute_values(cur, """
        INSERT INTO staging_au.cash_flow
            (asx_code, date, period_type,
             total_cash_from_operating_activities, capital_expenditures,
             total_cash_from_investing_activities,
             total_cash_from_financing_activities,
             dividends_paid, change_to_cash, free_cash_flow)
        VALUES %s
        ON CONFLICT (asx_code, date, period_type) DO UPDATE SET
            total_cash_from_operating_activities =
                EXCLUDED.total_cash_from_operating_activities,
            free_cash_flow = EXCLUDED.free_cash_flow
    """, rows, page_size=200)
    return len(rows)


# ─── Insert: staging_au.earnings ─────────────────────────────────────────────────

def upsert_earnings(cur, asx_code: str, history: dict, fund_id: int) -> int:
    rows = []
    for period_date_str, rec in history.items():
        dt = period_key(period_date_str, rec)
        if dt is None:
            continue
        rows.append((
            asx_code, dt, "actual",
            sf(rec.get("epsActual")), sf(rec.get("epsEstimate")),
            sf(rec.get("epsDifference")), sf(rec.get("surprisePercent")),
        ))
    if not rows:
        return 0
    execute_values(cur, """
        INSERT INTO staging_au.earnings
            (asx_code, date, period_type,
             eps_actual, eps_estimate, eps_difference, surprise_percent)
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
        return {}, set(), set()

    # Two different currencies are stated in one file, and only one of them
    # is about the numbers. Measured on ATM.AU_2026-06-14 (30 Sep 2026):
    #
    #   General.CurrencyCode             AUD   <- the LISTING currency
    #   Income_Statement currency_symbol IDR   <- the STATEMENTS
    #   totalRevenue                     88,851,053,565,000.00 IDR
    #
    # Checking General alone passes ATM straight through, which is what the
    # first version of this guard did.
    currency = ((raw.get("General") or {}).get("CurrencyCode") or "").upper()
    if currency and currency != REPORTING_CURRENCY:
        raise ForeignCurrency(currency)

    for _section in ("Income_Statement", "Balance_Sheet", "Cash_Flow"):
        stated = (((raw.get("Financials") or {}).get(_section) or {})
                  .get("currency_symbol") or "").upper()
        if stated and stated != REPORTING_CURRENCY:
            raise ForeignCurrency(f"{stated} ({_section})")

    import hashlib
    checksum = hashlib.sha256(path.read_bytes()).hexdigest()

    fund_id = upsert_fundamentals(cur, asx_code, snapshot_date, raw,
                                   path.name, checksum)
    if fund_id is None:
        return {}, set(), set()

    counts: dict[str, int] = {"fundamentals": 1}

    # The within-file population, at the finest key the source states.
    # `expected` is every period the JSON offers; `written` is every period
    # admitted. A period the source states and the loader drops shows up as
    # the difference, which is invisible at file grain.
    expected: set[str] = set()
    written:  set[str] = set()

    def account(section: str, ptype: str, periods: dict) -> None:
        for k, rec in periods.items():
            expected.add(f"{path.name}|{section}|{ptype}|{k}")
            if period_key(k, rec) is not None:
                written.add(f"{path.name}|{section}|{ptype}|{k}")

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
                account("income", ptype, periods)
                n = upsert_income_statement(cur, asx_code, periods, ptype, fund_id)
                counts[f"income_{ptype}"] = n

        bs = fin.get("Balance_Sheet", {})
        for ptype in ("yearly", "quarterly"):
            periods = bs.get(ptype, {})
            if isinstance(periods, dict):
                account("balance", ptype, periods)
                n = upsert_balance_sheet(cur, asx_code, periods, ptype, fund_id)
                counts[f"balance_{ptype}"] = n

        cf = fin.get("Cash_Flow", {})
        for ptype in ("yearly", "quarterly"):
            periods = cf.get(ptype, {})
            if isinstance(periods, dict):
                account("cashflow", ptype, periods)
                n = upsert_cash_flow(cur, asx_code, periods, ptype, fund_id)
                counts[f"cashflow_{ptype}"] = n

    earnings = raw.get("Earnings", {})
    history  = earnings.get("History", {}) if isinstance(earnings, dict) else {}
    if isinstance(history, dict) and history:
        account("earnings", "history", history)
        n = upsert_earnings(cur, asx_code, history, fund_id)
        counts["earnings"] = n

    return counts, expected, written


# ─── The load loop, and what it is allowed to claim ──────────────────────────

def population_proof(expected, written, empty, skipped, failed) -> dict:
    """Did every key the source stated reach one of the four terminal states?

    Extracted so the proof a test exercises is the proof the loader runs. A
    test that re-implements this arithmetic proves only that the test agrees
    with itself.
    """
    accounted = set(written) | set(empty) | set(skipped) | set(failed)
    return {
        "unaccounted": set(expected) - accounted,   # stated, never resolved
        "surplus":     accounted - set(expected),   # resolved, never stated
        "failed":      set(failed),
    }



def load_files(conn, cur, files, batch_commit: int = BATCH_COMMIT):
    """Load every file, and return what can honestly be said about each one.

    Five terminal states, and every file reaches exactly one:

      written   its rows survived an outer COMMIT
      pending   admitted but not yet durable -- never promoted to `written`
                until the enclosing transaction commits, because releasing a
                savepoint does not make anything durable: a later rollback of
                the outer transaction erases released savepoints too
      empty     parsed cleanly and offered nothing (an ETF with no Financials
                block). Observed absence, not failure.
      skipped   deliberately excluded, with a stated reason (ForeignCurrency)
      failed    raised. The load does not succeed with any of these.

    `expected` accumulates the file AND every period the file's own JSON
    states, so a company that silently loses one year is as visible as one
    that loses all of them -- the within-file loss a file-grain proof is
    structurally blind to.

    Extracted from main() so the promotion rule can be driven directly by a
    test: the defect being guarded against is a success recorded before the
    transaction that would have made it true.
    """
    expected: set[str] = set()
    written:  set[str] = set()
    pending:  set[str] = set()
    empty:    set[str] = set()
    skipped:  dict[str, str] = {}
    failed:   dict[str, str] = {}
    total = len(files)

    for i, path in enumerate(files, 1):
        expected.add(path.name)
        # A per-file savepoint, because conn.rollback() is per-connection: it
        # discards everything staged since the last commit, which on 30 Sep
        # 2026 meant one overflowing file destroyed up to 49 other companies'
        # rows -- and they had already been counted as loaded.
        cur.execute("SAVEPOINT one_file")
        try:
            counts, file_expected, file_written = load_file(cur, path)
        except ForeignCurrency as exc:
            cur.execute("ROLLBACK TO SAVEPOINT one_file")
            skipped[path.name] = f"reported in {exc}"
        except Exception as exc:                                  # noqa: BLE001
            cur.execute("ROLLBACK TO SAVEPOINT one_file")
            failed[path.name] = str(exc)
            log.warning("  %s: %s", path.name, exc)
        else:
            cur.execute("RELEASE SAVEPOINT one_file")
            expected |= file_expected
            pending  |= file_written
            (pending if counts else empty).add(path.name)

        if i % batch_commit == 0:
            conn.commit()
            written |= pending          # durable only now
            pending.clear()
            log.info("  [%4d/%d]  written=%d  empty=%d  skipped=%d  failed=%d",
                     i, total, len(written), len(empty), len(skipped),
                     len(failed))

    conn.commit()
    written |= pending
    pending.clear()
    return expected, written, empty, skipped, failed


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
    is_full_run = not args.codes and not args.date and not args.from_code
    log.info(f"Loading {total} fundamentals files from {FUND_DIR}")
    if is_full_run:
        log.info("Full run — will TRUNCATE all fundamentals staging tables before loading")

    conn = psycopg2.connect(DB_URL)
    cur  = conn.cursor()

    if is_full_run:
        cur.execute("""
            TRUNCATE TABLE
                staging_au.income_statement,
                staging_au.balance_sheet,
                staging_au.cash_flow,
                staging_au.earnings,
                staging_au.company_profile,
                staging_au.highlights,
                staging_au.valuation,
                staging_au.analyst_ratings,
                staging_au.shares_stats,
                staging_au.fundamentals
            RESTART IDENTITY
        """)
        conn.commit()
        log.info("Staging tables truncated.")

    expected, written, empty, skipped, failed = load_files(conn, cur, files)
    cur.close()
    conn.close()

    # ── Population proof ─────────────────────────────────────────────────────
    proof       = population_proof(expected, written, empty, skipped, failed)
    unaccounted = proof["unaccounted"]
    surplus     = proof["surplus"]

    log.info("── files → staging  (grain: file, and file|section|period)")
    log.info("   expected (manifest) : %d  from %d files", len(expected), total)
    log.info("   written (committed) : %d", len(written))
    log.info("   empty (no content)  : %d", len(empty))
    log.info("   skipped (explained) : %d", len(skipped))
    log.info("   failed              : %d", len(failed))
    log.info("   unaccounted         : %d", len(unaccounted))
    log.info("   surplus             : %d", len(surplus))

    for name, why in sorted(skipped.items())[:10]:
        log.info("   skipped: %s — %s", name, why)
    if len(skipped) > 10:
        log.info("   skipped: … and %d more", len(skipped) - 10)

    if failed or unaccounted or surplus:
        for name, why in sorted(failed.items())[:20]:
            log.error("   failed: %s — %s", name, why)
        for name in sorted(unaccounted)[:20]:
            log.error("   unaccounted: %s", name)
        for name in sorted(surplus)[:20]:
            log.error("   surplus: %s", name)
        log.error(
            "LOAD FAILED — %d failed, %d unaccounted, %d surplus. Downstream "
            "stages derive their expected populations from staging, so a "
            "silently shrunken staging makes every one of their set-equality "
            "proofs pass on an incomplete refresh. This stops here instead.",
            len(failed), len(unaccounted), len(surplus))
        sys.exit(1)

    log.info("DONE — %d files offered, %d keys expected, %d written, %d empty, "
             "%d skipped, 0 failed",
             total, len(expected), len(written), len(empty), len(skipped))


if __name__ == "__main__":
    main()
