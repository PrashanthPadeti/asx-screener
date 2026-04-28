"""
Transform: staging IS/BS/CF → financials.annual_pnl / balance_sheet / cashflow
===============================================================================
Processes only period_type = 'yearly' rows from staging.
Monetary values: EODHD returns full AUD dollars → stored as AUD millions (÷ 1,000,000).
fiscal_year: year extracted from the period end date.

SCD behaviour: UPSERT on (asx_code, fiscal_year). Existing rows are updated in-place.
data_as_of timestamp is set to NOW() on each load.

Full run: truncates all three financials tables first.
Partial run (--codes / --fiscal-year): upsert only.

Usage:
    python scripts/eodhd/v2/transforms/transform_financials.py
    python scripts/eodhd/v2/transforms/transform_financials.py --codes BHP CBA
    python scripts/eodhd/v2/transforms/transform_financials.py --fiscal-year 2024
"""

import logging
import os
import argparse

import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv("DATABASE_URL_SYNC",
           "postgresql://asx_user:asx_secure_2024@localhost:5432/asx_screener")

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

M = 1_000_000  # EODHD full AUD → AUD millions divisor


def _m(v) -> float | None:
    """Divide by 1,000,000 for AUD millions; None if NULL."""
    return round(float(v) / M, 2) if v is not None else None


def _f(v) -> float | None:
    return float(v) if v is not None else None


def _fy(period_end_date) -> int:
    """Fiscal year = year of the period end date."""
    return period_end_date.year


# ─── Income Statement ─────────────────────────────────────────────────────────

def transform_pnl(cur, codes, fiscal_year) -> int:
    filters, params = _build_filters(codes, fiscal_year)
    cur.execute(f"""
        SELECT
            asx_code, date,
            total_revenue, cost_of_revenue, gross_profit,
            total_operating_expenses, operating_income, ebitda,
            interest_expense, income_before_tax, income_tax_expense,
            net_income, eps, eps_diluted, depreciation_amortization
        FROM staging.income_statement
        WHERE period_type = 'yearly' {filters}
        ORDER BY asx_code, date
    """, params)

    rows = cur.fetchall()
    log.info(f"  income_statement: {len(rows)} yearly rows")
    if not rows:
        return 0

    transformed = []
    for r in rows:
        (asx_code, period_end_date,
         total_revenue, cost_of_revenue, gross_profit,
         total_operating_expenses, operating_income, ebitda,
         interest_expense, income_before_tax, income_tax_expense,
         net_income, eps, eps_diluted, depreciation_amortization) = r

        fy = _fy(period_end_date)

        # Derived margins (if revenue available)
        rev = _m(total_revenue)
        gp  = _m(gross_profit)
        op  = _m(operating_income)
        ni  = _m(net_income)
        eb  = _m(ebitda)

        gpm = round(gp / rev, 6) if rev and gp is not None and rev != 0 else None
        opm = round(op / rev, 6) if rev and op is not None and rev != 0 else None
        npm = round(ni / rev, 6) if rev and ni is not None and rev != 0 else None
        ebitda_margin = round(eb / rev, 6) if rev and eb is not None and rev != 0 else None

        transformed.append((
            asx_code, fy, period_end_date,
            rev, _m(cost_of_revenue), gp,
            _m(total_operating_expenses), op, eb,
            _m(depreciation_amortization),
            _m(interest_expense), _m(income_before_tax), _m(income_tax_expense), ni,
            ni,  # net_profit same as net_income from EODHD
            opm, npm, gpm, ebitda_margin,
            _f(eps), _f(eps_diluted),
            "eodhd",
        ))

    execute_values(cur, """
        INSERT INTO financials.annual_pnl (
            asx_code, fiscal_year, period_end_date,
            revenue, cost_of_sales, gross_profit,
            operating_expenses, ebit, ebitda,
            depreciation,
            interest_expense, pbt, tax, pat,
            net_profit,
            opm, npm, gpm, ebitda_margin,
            eps, eps_diluted,
            data_source
        ) VALUES %s
        ON CONFLICT (asx_code, fiscal_year) DO UPDATE SET
            period_end_date  = EXCLUDED.period_end_date,
            revenue          = EXCLUDED.revenue,
            cost_of_sales    = EXCLUDED.cost_of_sales,
            gross_profit     = EXCLUDED.gross_profit,
            operating_expenses = EXCLUDED.operating_expenses,
            ebit             = EXCLUDED.ebit,
            ebitda           = EXCLUDED.ebitda,
            depreciation     = EXCLUDED.depreciation,
            interest_expense = EXCLUDED.interest_expense,
            pbt              = EXCLUDED.pbt,
            tax              = EXCLUDED.tax,
            pat              = EXCLUDED.pat,
            net_profit       = EXCLUDED.net_profit,
            opm              = EXCLUDED.opm,
            npm              = EXCLUDED.npm,
            gpm              = EXCLUDED.gpm,
            ebitda_margin    = EXCLUDED.ebitda_margin,
            eps              = EXCLUDED.eps,
            eps_diluted      = EXCLUDED.eps_diluted,
            data_source      = EXCLUDED.data_source,
            data_as_of       = NOW()
    """, transformed, page_size=1000)

    return len(transformed)


# ─── Balance Sheet ────────────────────────────────────────────────────────────

def transform_balance_sheet(cur, codes, fiscal_year) -> int:
    filters, params = _build_filters(codes, fiscal_year)
    cur.execute(f"""
        SELECT
            asx_code, date,
            total_assets, total_current_assets,
            cash_and_short_term_investments, net_receivables, inventory,
            total_non_current_assets, property_plant_equipment_net,
            goodwill, intangible_assets,
            total_liabilities, total_current_liabilities,
            short_long_term_debt_total, long_term_debt,
            total_stockholder_equity, retained_earnings, common_stock
        FROM staging.balance_sheet
        WHERE period_type = 'yearly' {filters}
        ORDER BY asx_code, date
    """, params)

    rows = cur.fetchall()
    log.info(f"  balance_sheet: {len(rows)} yearly rows")
    if not rows:
        return 0

    transformed = []
    for r in rows:
        (asx_code, period_end_date,
         total_assets, total_current_assets,
         cash, receivables, inventory,
         total_non_current, ppe, goodwill, intangibles,
         total_liab, current_liab, short_term_debt, long_term_debt,
         total_equity, retained_earnings, common_stock) = r

        fy = _fy(period_end_date)

        # Derived
        total_debt = _m(short_term_debt) or 0
        if long_term_debt is not None:
            total_debt = (total_debt or 0) + _m(long_term_debt)
        cash_m = _m(cash)
        net_debt = round(total_debt - cash_m, 2) if total_debt and cash_m is not None else None

        transformed.append((
            asx_code, fy, period_end_date,
            cash_m, _m(receivables), _m(inventory),
            None,  # other_current_assets
            _m(total_current_assets),
            _m(ppe), None, None,  # gross_block, accumulated_depreciation, net_block = ppe approx
            _m(goodwill), _m(intangibles),
            None,  # investments
            None,  # other_non_current
            _m(total_assets),
            None,  # trade_payables
            None,  # advance_from_customers
            _m(short_term_debt),
            None,  # other_current_liab
            _m(current_liab),
            _m(long_term_debt),
            None,  # lease_liabilities
            None,  # contingent_liabilities
            None,  # other_non_current_liab
            _m(total_liab),
            None,  # equity_capital
            None,  # preference_capital
            None,  # reserves
            _m(retained_earnings),
            None,  # minority_interest_bs
            _m(total_equity),
            round(total_debt, 2) if isinstance(total_debt, float) else total_debt,
            net_debt,
            None,  # working_capital
            None,  # book_value_per_share
            None,  # face_value
            None,  # shares_outstanding
            "eodhd",
        ))

    execute_values(cur, """
        INSERT INTO financials.annual_balance_sheet (
            asx_code, fiscal_year, period_end_date,
            cash_equivalents, trade_receivables, inventory,
            other_current_assets, total_current_assets,
            gross_block, accumulated_depreciation, net_block,
            goodwill, intangibles, investments, other_non_current,
            total_assets,
            trade_payables, advance_from_customers,
            short_term_debt, other_current_liab, total_current_liab,
            long_term_debt, lease_liabilities, contingent_liabilities,
            other_non_current_liab, total_liabilities,
            equity_capital, preference_capital, reserves,
            retained_earnings, minority_interest_bs, total_equity,
            total_debt, net_debt, working_capital,
            book_value_per_share, face_value, shares_outstanding,
            data_source
        ) VALUES %s
        ON CONFLICT (asx_code, fiscal_year) DO UPDATE SET
            period_end_date        = EXCLUDED.period_end_date,
            cash_equivalents       = EXCLUDED.cash_equivalents,
            trade_receivables      = EXCLUDED.trade_receivables,
            inventory              = EXCLUDED.inventory,
            total_current_assets   = EXCLUDED.total_current_assets,
            gross_block            = EXCLUDED.gross_block,
            goodwill               = EXCLUDED.goodwill,
            intangibles            = EXCLUDED.intangibles,
            total_assets           = EXCLUDED.total_assets,
            short_term_debt        = EXCLUDED.short_term_debt,
            total_current_liab     = EXCLUDED.total_current_liab,
            long_term_debt         = EXCLUDED.long_term_debt,
            total_liabilities      = EXCLUDED.total_liabilities,
            retained_earnings      = EXCLUDED.retained_earnings,
            total_equity           = EXCLUDED.total_equity,
            total_debt             = EXCLUDED.total_debt,
            net_debt               = EXCLUDED.net_debt,
            data_source            = EXCLUDED.data_source,
            data_as_of             = NOW()
    """, transformed, page_size=1000)

    return len(transformed)


# ─── Cash Flow ────────────────────────────────────────────────────────────────

def transform_cashflow(cur, codes, fiscal_year) -> int:
    filters, params = _build_filters(codes, fiscal_year)
    cur.execute(f"""
        SELECT
            asx_code, date,
            total_cash_from_operating_activities,
            capital_expenditures,
            total_cash_from_investing_activities,
            total_cash_from_financing_activities,
            dividends_paid,
            change_to_cash,
            free_cash_flow
        FROM staging.cash_flow
        WHERE period_type = 'yearly' {filters}
        ORDER BY asx_code, date
    """, params)

    rows = cur.fetchall()
    log.info(f"  cash_flow: {len(rows)} yearly rows")
    if not rows:
        return 0

    transformed = []
    for r in rows:
        (asx_code, period_end_date,
         cfo, capex, cfi, cff, div_paid, change_cash, fcf) = r

        fy = _fy(period_end_date)
        cfo_m = _m(cfo)
        capex_m = _m(capex)

        # fcf = cfo + capex (capex is negative in EODHD)
        if fcf is not None:
            fcf_m = _m(fcf)
        elif cfo_m is not None and capex_m is not None:
            fcf_m = round(cfo_m + capex_m, 2)
        else:
            fcf_m = None

        transformed.append((
            asx_code, fy, period_end_date,
            None,   # net_income (not in CF staging)
            None,   # depreciation_amort
            None,   # working_capital_changes
            None,   # other_operating
            cfo_m,
            capex_m,
            None,   # acquisitions
            None,   # disposals
            None,   # investment_purchases
            None,   # other_investing
            _m(cfi),
            _m(div_paid),
            None,   # debt_raised
            None,   # debt_repaid
            None,   # equity_raised
            None,   # buybacks
            None,   # other_financing
            _m(cff),
            _m(change_cash),
            None,   # opening_cash
            None,   # closing_cash
            fcf_m,
            "eodhd",
        ))

    execute_values(cur, """
        INSERT INTO financials.annual_cashflow (
            asx_code, fiscal_year, period_end_date,
            net_income, depreciation_amort, working_capital_changes, other_operating, cfo,
            capex, acquisitions, disposals, investment_purchases, other_investing, cfi,
            dividends_paid, debt_raised, debt_repaid, equity_raised, buybacks,
            other_financing, cff,
            net_change_in_cash, opening_cash, closing_cash, fcf,
            data_source
        ) VALUES %s
        ON CONFLICT (asx_code, fiscal_year) DO UPDATE SET
            period_end_date        = EXCLUDED.period_end_date,
            cfo                    = EXCLUDED.cfo,
            capex                  = EXCLUDED.capex,
            cfi                    = EXCLUDED.cfi,
            dividends_paid         = EXCLUDED.dividends_paid,
            cff                    = EXCLUDED.cff,
            net_change_in_cash     = EXCLUDED.net_change_in_cash,
            fcf                    = EXCLUDED.fcf,
            data_source            = EXCLUDED.data_source,
            data_as_of             = NOW()
    """, transformed, page_size=1000)

    return len(transformed)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _build_filters(codes, fiscal_year) -> tuple[str, list]:
    parts = []
    params = []
    if codes:
        placeholders = ",".join(["%s"] * len(codes))
        parts.append(f"AND asx_code IN ({placeholders})")
        params.extend([c.upper() for c in codes])
    if fiscal_year:
        parts.append("AND EXTRACT(YEAR FROM date)::INT = %s")
        params.append(fiscal_year)
    return " ".join(parts), params


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--codes",       nargs="+")
    parser.add_argument("--fiscal-year", type=int)
    args = parser.parse_args()

    is_full_run = not args.codes and not args.fiscal_year

    conn = psycopg2.connect(DB_URL)
    cur  = conn.cursor()

    if is_full_run:
        log.info("Full run — truncating financials tables …")
        cur.execute("TRUNCATE TABLE financials.annual_pnl RESTART IDENTITY CASCADE")
        cur.execute("TRUNCATE TABLE financials.annual_balance_sheet RESTART IDENTITY CASCADE")
        cur.execute("TRUNCATE TABLE financials.annual_cashflow RESTART IDENTITY CASCADE")
        conn.commit()
        log.info("Truncated.")

    log.info("Transforming staging financials → financials.annual_* …")

    n_pnl = transform_pnl(cur, args.codes, args.fiscal_year)
    conn.commit()

    n_bs = transform_balance_sheet(cur, args.codes, args.fiscal_year)
    conn.commit()

    n_cf = transform_cashflow(cur, args.codes, args.fiscal_year)
    conn.commit()

    cur.close()
    conn.close()
    log.info(f"DONE — pnl={n_pnl}  balance_sheet={n_bs}  cashflow={n_cf}")


if __name__ == "__main__":
    main()
