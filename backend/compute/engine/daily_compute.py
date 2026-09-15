"""
ASX Screener — Daily Compute Engine
=====================================
Computes all daily metrics for each stock and inserts into
market.computed_metrics (TimescaleDB hypertable).

Metrics computed:
  - Market cap, Enterprise Value
  - P/E, P/B, P/S, EV/EBITDA ratios
  - Dividend yield, Grossed-up yield (franking credits)
  - ROE, ROA, ROCE
  - Debt/Equity, Current ratio, Interest coverage
  - Revenue/Profit growth (1Y, 3Y, 5Y)
  - Piotroski F-Score (9 criteria)
  - FCF yield, OCF margin

Run after market close:
    python compute/engine/daily_compute.py
    python compute/engine/daily_compute.py --codes BHP CBA  # specific stocks
    python compute/engine/daily_compute.py --limit 100      # first N stocks
"""

import os
import sys
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
from pathlib import Path

# The database credential lives in the environment, never in source.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.core.db import get_database_url_sync  # noqa: E402
from compute.engine.dividends import (  # noqa: E402
    FEED_STALENESS_DAYS, DividendSource, FeedHealth,
    # fetch_feed_health now lives beside the thresholds and the dataclass
    # it returns. Re-exported here because composite_score,
    # sector_benchmarks and several scripts import it from this module,
    # and moving a symbol is not a reason to break its callers.
    fetch_feed_health,  # noqa: F401
)


# Auto-cast PostgreSQL NUMERIC/DECIMAL → Python float on read.
# Prevents "unsupported operand type(s) for +: decimal.Decimal and float" errors
# throughout all metric calculations.
_DEC2FLOAT = psycopg2.extensions.new_type(
    psycopg2.extensions.DECIMAL.values,
    "DEC2FLOAT",
    lambda value, curs: float(value) if value is not None else None,
)
psycopg2.extensions.register_type(_DEC2FLOAT)

load_dotenv()

DB_URL = get_database_url_sync()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

COMPUTE_VERSION = "1.0.0"


# ── Data Fetchers ─────────────────────────────────────────────

def fetch_latest_price(cur, asx_code: str) -> Optional[dict]:
    cur.execute("""
        SELECT close, volume, time::date as price_date
        FROM market.daily_prices
        WHERE asx_code = %s
        ORDER BY time DESC LIMIT 1
    """, (asx_code,))
    row = cur.fetchone()
    if not row:
        return None
    return {"close": row[0], "volume": row[1], "price_date": row[2]}


def fetch_financials(cur, asx_code: str) -> dict:
    """Fetch latest annual P&L, Balance Sheet, Cash Flow."""
    # Annual P&L — last 5 years
    cur.execute("""
        SELECT fiscal_year, revenue, gross_profit, ebitda, ebit,
               net_profit, pat, eps, dps, dps_franking_pct,
               interest_expense, tax, depreciation
        FROM financials.annual_pnl
        WHERE asx_code = %s
        ORDER BY fiscal_year DESC
        LIMIT 5
    """, (asx_code,))
    pnl_rows = cur.fetchall()
    pnl_cols = ["fiscal_year","revenue","gross_profit","ebitda","ebit",
                "net_profit","pat","eps","dps","dps_franking_pct",
                "interest_expense","tax","depreciation"]
    pnl = [dict(zip(pnl_cols, r)) for r in pnl_rows]

    # Balance Sheet — latest
    cur.execute("""
        SELECT total_assets, total_liabilities, total_equity,
               total_debt, net_debt, cash_equivalents,
               total_current_assets, total_current_liab,
               shares_outstanding, book_value_per_share,
               goodwill, intangibles, inventory, trade_receivables
        FROM financials.annual_balance_sheet
        WHERE asx_code = %s
        ORDER BY fiscal_year DESC LIMIT 1
    """, (asx_code,))
    bs_row = cur.fetchone()
    bs_cols = ["total_assets","total_liabilities","total_equity",
               "total_debt","net_debt","cash_equivalents",
               "total_current_assets","total_current_liab",
               "shares_outstanding","book_value_per_share",
               "goodwill","intangibles","inventory","trade_receivables"]
    bs = dict(zip(bs_cols, bs_row)) if bs_row else {}

    # Cash Flow — latest
    cur.execute("""
        SELECT cfo, cfi, cff, capex, fcf, dividends_paid
        FROM financials.annual_cashflow
        WHERE asx_code = %s
        ORDER BY fiscal_year DESC LIMIT 1
    """, (asx_code,))
    cf_row = cur.fetchone()
    cf_cols = ["cfo","cfi","cff","capex","fcf","dividends_paid"]
    cf = dict(zip(cf_cols, cf_row)) if cf_row else {}

    return {"pnl": pnl, "bs": bs, "cf": cf}


def fetch_company(cur, asx_code: str) -> dict:
    cur.execute("""
        SELECT shares_outstanding, is_reit, is_miner
        FROM market.companies WHERE asx_code = %s
    """, (asx_code,))
    row = cur.fetchone()
    if not row:
        return {}
    return {"shares_outstanding": row[0], "is_reit": row[1], "is_miner": row[2]}


def fetch_dividends(cur, asx_code: str) -> list:
    """Fetch last 3 years of dividends."""
    cur.execute("""
        SELECT ex_date, amount_per_share, franking_pct, grossed_up_amount
        FROM market.dividends
        WHERE asx_code = %s AND ex_date >= NOW() - INTERVAL '3 years'
        ORDER BY ex_date DESC
    """, (asx_code,))
    rows = cur.fetchall()
    return [{"ex_date": r[0], "amount": r[1], "franking_pct": r[2], "grossed_up": r[3]} for r in rows]


# ── Metric Calculations ───────────────────────────────────────

def safe_div(a, b, default=None):
    """Safe division — returns default if b is None/0."""
    try:
        if a is None or b is None or b == 0:
            return default
        return float(a) / float(b)
    except Exception:
        return default


def _observed(row: dict, field: str) -> Optional[float]:
    """One observation, distinguishing an economic zero from missing data.

    Truthiness is what made this necessary. The previous code filtered with
    ``if p.get("revenue")``, which discards 0.0 as readily as None — so a
    year of zero revenue vanished from the series entirely rather than being
    recorded as a year in which revenue was zero.
    """
    value = row.get(field)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def growth_over(pnl: list, field: str, n: int) -> Optional[float]:
    """CAGR over exactly n fiscal years, anchored to the latest reported year.

    FACTOR_MODEL_V2. The previous form took values[n] from a list built as
    ``[p[field] for p in pnl if p.get(field)]`` — n POSITIONS back, in a
    series that had already dropped every year whose value was null or zero.

    Both halves did damage, and the second was worse. Dropping zero years
    removed the *latest* observation too, so values[0] was not the current
    year: for a company whose revenue had fallen to zero, this compared two
    historical non-zero years and served the result as current growth.
    Measured on production, EXR reported +450.7% where the exact Y-3
    comparison gives -100%, and seven other companies showed the same
    signature.

    The contract now:

        required fiscal year absent   -> None (unavailable, no observation)
        base observation is 0         -> None (undefined, not "no history")
        latest observation is 0       -> -1.0, i.e. -100%

    Zero is an observation. A value that fell to nothing did not go missing,
    and reporting -100% is the honest answer; only the absence of the period
    itself makes the metric unavailable. That distinction is what the
    truthiness check destroyed.
    """
    by_year = {int(p["fiscal_year"]): p for p in pnl
               if p.get("fiscal_year") is not None}
    if not by_year:
        return None

    latest_year = max(by_year)
    prior = by_year.get(latest_year - n)
    if prior is None:
        return None

    latest = _observed(by_year[latest_year], field)
    base = _observed(prior, field)
    if latest is None or base is None:
        return None
    # A zero or negative base leaves the ratio undefined, which is a property
    # of the arithmetic and not of the history. It must not be reported as an
    # absent period.
    if base <= 0 or latest < 0:
        return None
    if latest == 0:
        return -1.0
    try:
        return (latest / base) ** (1 / n) - 1
    except Exception:
        return None


class UnsupportedComputation(RuntimeError):
    """A method that cannot be executed faithfully must not be executed."""


def calc_piotroski(pnl: list, bs: dict, cf: dict) -> Optional[int]:
    """Refuses. The implementation below it is not a Piotroski F-Score.

    An upstream suppression already withholds piotroski_f_score
    (UNAVAILABLE / COMPUTATION_UNSUPPORTED), so nothing reaches a customer
    today. That protects the current path and not the next developer: a
    function with this name returning a plausible 2-9 integer is exactly what
    someone restores when the suppression looks like over-caution.

    What the legacy body actually does, measured rather than suspected:

      F5 and F7 award a point unconditionally, so no company can score below
      2 and the range is 2-9 rather than 0-9.
      F3 and F9 claim year-over-year comparisons while dividing both years by
      the CURRENT balance sheet, so they compare numerators.
      F3, F8 and F9 score an absent prior year as a failed criterion rather
      than as unassessable.

    And it cannot be repaired from the data that exists. Of the 1,599 active
    companies carrying annual statements, 1,596 have the exact Y-1 pair — so
    period coverage is not the constraint — but prior-year shares_outstanding
    is NULL for all 1,596, making F7 unevaluable universally, and prior
    long_term_debt is NULL for 915, capping F5 at 594. No company anywhere in
    the universe, including the ASX 200, can have all nine criteria assessed.

    The body is preserved as _legacy_invalid_piotroski for the record, not for
    use.
    """
    raise UnsupportedComputation(
        "the legacy Piotroski implementation is methodologically invalid: two "
        "of nine criteria award a point unconditionally, two compare years "
        "against a single balance sheet, and a missing prior year scores as a "
        "failure. It cannot be repaired from current data — prior-year "
        "shares_outstanding is absent for every company. Do not use it until "
        "all nine criteria have supported inputs.")


def _legacy_invalid_piotroski(pnl: list, bs: dict, cf: dict) -> Optional[int]:
    """SUPERSEDED AND INVALID — kept as evidence, never called.

    See calc_piotroski above for what is wrong with it and why it cannot be
    fixed from the data available. Retained so that "what did the old score
    actually compute" has an answer that is not archaeology.
    """
    if not pnl or not bs or not cf:
        return None

    p = pnl[0]       # Latest year
    p1 = pnl[1] if len(pnl) > 1 else {}  # Prior year
    score = 0

    # Profitability (4 signals)
    # F1: ROA > 0
    roa = safe_div(p.get("net_profit"), bs.get("total_assets"))
    if roa and roa > 0: score += 1

    # F2: CFO > 0
    if cf.get("cfo") and cf["cfo"] > 0: score += 1

    # F3: ROA improved YoY
    if p1:
        roa_prev = safe_div(p1.get("net_profit"), bs.get("total_assets"))
        if roa and roa_prev and roa > roa_prev: score += 1

    # F4: CFO > Net Income (accruals)
    net = p.get("net_profit") or 0
    cfo = cf.get("cfo") or 0
    if cfo > net: score += 1

    # Leverage (3 signals)
    # F5: Lower long-term debt ratio YoY (skip — need 2 BS years)
    score += 1  # Give benefit of doubt for now

    # F6: Higher current ratio YoY (skip — need 2 BS years)
    cr = safe_div(bs.get("total_current_assets"), bs.get("total_current_liab"))
    if cr and cr > 1: score += 1

    # F7: No new shares issued (skip — need share count history)
    score += 1  # Neutral for now

    # Operating efficiency (2 signals)
    # F8: Higher gross margin YoY
    if p1 and p.get("revenue") and p.get("gross_profit"):
        gm_cur  = safe_div(p.get("gross_profit"), p.get("revenue"))
        gm_prev = safe_div(p1.get("gross_profit"), p1.get("revenue"))
        if gm_cur and gm_prev and gm_cur > gm_prev: score += 1

    # F9: Higher asset turnover YoY
    if p1 and p.get("revenue") and bs.get("total_assets"):
        at_cur  = safe_div(p.get("revenue"), bs.get("total_assets"))
        at_prev = safe_div(p1.get("revenue"), bs.get("total_assets"))
        if at_cur and at_prev and at_cur > at_prev: score += 1

    return min(score, 9)


def compute_metrics(asx_code: str, price: dict, fin: dict, company: dict,
                    divs: list, dividend_source: DividendSource) -> dict:
    """Compute all metrics for a stock. Returns dict matching computed_metrics columns."""

    m = {}  # metrics dict
    now = datetime.now(tz=timezone.utc)

    pnl = fin.get("pnl", [])
    bs  = fin.get("bs", {})
    cf  = fin.get("cf", {})

    close  = price.get("close")
    p0     = pnl[0] if pnl else {}
    shares = bs.get("shares_outstanding") or company.get("shares_outstanding")

    # Market Cap (AUD millions)
    if close and shares:
        m["market_cap"] = round(close * shares / 1_000_000, 2)

    # Enterprise Value = Market Cap + Net Debt
    net_debt = bs.get("net_debt")
    if m.get("market_cap") and net_debt is not None:
        m["enterprise_value"] = round(m["market_cap"] + float(net_debt), 2)

    # ── Valuation Ratios ──────────────────────────────────────

    # P/E
    eps = p0.get("eps")
    if close and eps and eps > 0:
        m["pe_ratio"] = round(close / float(eps), 2)

    # P/B
    bvps = bs.get("book_value_per_share")
    if close and bvps and float(bvps) > 0:
        m["pb_ratio"] = round(close / float(bvps), 2)

    # P/S
    rev = p0.get("revenue")
    if m.get("market_cap") and rev and float(rev) > 0:
        m["ps_ratio"] = round(m["market_cap"] / float(rev), 2)

    # EV/EBITDA
    ebitda = p0.get("ebitda")
    if m.get("enterprise_value") and ebitda and float(ebitda) > 0:
        m["ev_ebitda"] = round(m["enterprise_value"] / float(ebitda), 2)

    # EV/EBIT
    ebit = p0.get("ebit")
    if m.get("enterprise_value") and ebit and float(ebit) > 0:
        m["ev_ebit"] = round(m["enterprise_value"] / float(ebit), 2)

    # ── Dividend Yield ────────────────────────────────────────

    # The five dividend fields come from the canonical module, which selects a
    # period-based trailing-twelve-month window rather than a fixed four
    # payments, grosses up per payment from market.dividends.grossed_up_amount
    # rather than averaging franking across an aggregate, and declines to
    # report anything at all when the feed has not observed the end of the
    # window. All five keys are always present: upsert_metrics builds its
    # UPDATE clause from the keys in this dict, so an omitted field keeps
    # whatever the last run wrote — which is how OEL carried a 480%
    # grossed-up yield against a zero dividend.
    m.update(dividend_source.metrics(divs, close, as_of=price["price_date"]))

    ttm_dps = m["dividend_per_share"]

    # Payout ratio rides on the same TTM figure, so a refused dividend cannot
    # leave a payout ratio behind that implies one.
    net_profit = p0.get("net_profit")
    if ttm_dps and shares and net_profit and float(net_profit) > 0:
        total_div = float(ttm_dps) * float(shares) / 1_000_000
        m["dividend_payout_ratio"] = round(safe_div(total_div, float(net_profit)) or 0, 4)
    else:
        m["dividend_payout_ratio"] = None

    # ── Profitability ─────────────────────────────────────────

    equity   = bs.get("total_equity")
    assets   = bs.get("total_assets")
    net_prof = p0.get("net_profit")

    if net_prof and equity and float(equity) > 0:
        m["roe"] = round(float(net_prof) / float(equity), 6)

    if net_prof and assets and float(assets) > 0:
        m["roa"] = round(float(net_prof) / float(assets), 6)

    if ebit and equity and assets:
        capital_employed = float(assets) - (bs.get("total_current_liab") or 0)
        if capital_employed > 0:
            m["roce"] = round(float(ebit) / capital_employed, 6)

    if rev:
        rev_f = float(rev)
        if p0.get("gross_profit") and rev_f > 0:
            m["gpm"] = round(float(p0["gross_profit"]) / rev_f, 6)
        if ebit and rev_f > 0:
            m["opm"] = round(float(ebit) / rev_f, 6)
        if net_prof and rev_f > 0:
            m["npm"] = round(float(net_prof) / rev_f, 6)
        if ebitda and rev_f > 0:
            m["ebitda_margin"] = round(float(ebitda) / rev_f, 6)

    # ── Financial Health ──────────────────────────────────────

    total_debt = bs.get("total_debt")
    if total_debt is not None and equity and float(equity) > 0:
        m["debt_to_equity"] = round(float(total_debt) / float(equity), 4)

    cur_assets = bs.get("total_current_assets")
    cur_liab   = bs.get("total_current_liab")
    if cur_assets and cur_liab and float(cur_liab) > 0:
        m["current_ratio"] = round(float(cur_assets) / float(cur_liab), 4)

    cash = bs.get("cash_equivalents")
    if cash and cur_liab and float(cur_liab) > 0:
        m["cash_ratio"] = round(float(cash) / float(cur_liab), 4)

    int_exp = p0.get("interest_expense")
    if ebit and int_exp and float(int_exp) > 0:
        m["interest_coverage"] = round(float(ebit) / abs(float(int_exp)), 4)

    if net_debt is not None and ebitda and float(ebitda) > 0:
        m["net_debt_to_ebitda"] = round(float(net_debt) / float(ebitda), 4)

    # ── Cash Flow ─────────────────────────────────────────────

    cfo = cf.get("cfo")
    fcf = cf.get("fcf")

    if fcf and m.get("market_cap") and m["market_cap"] > 0:
        m["fcf_yield"] = round(float(fcf) / m["market_cap"], 6)

    if cfo and net_prof and float(net_prof) != 0:
        m["ocf_to_net_income"] = round(float(cfo) / abs(float(net_prof)), 4)

    if cfo and rev and float(rev) > 0:
        m["ocf_margin"] = round(float(cfo) / float(rev), 6)

    # ── Growth ───────────────────────────────────────────────

    # Year-anchored, not positional. growth_over locates the required fiscal
    # year itself, so the length guards that used to stand in for history
    # ("at least 4 rows exist, therefore a 3-year window exists") are gone —
    # they were counting rows in a list that had already been compacted.
    m["revenue_growth_1y"] = growth_over(pnl, "revenue", 1)
    m["revenue_growth_3y"] = growth_over(pnl, "revenue", 3)
    m["profit_growth_1y"]  = growth_over(pnl, "net_profit", 1)
    m["profit_growth_3y"]  = growth_over(pnl, "net_profit", 3)

    # ── Quality Scores ────────────────────────────────────────

    # Not computed. The legacy implementation is not a Piotroski F-Score —
    # see calc_piotroski — and the metric is withheld downstream as
    # UNAVAILABLE / COMPUTATION_UNSUPPORTED. Continuing to write it would keep
    # the fabricated number in market.computed_metrics, where the next reader
    # finds a plausible 2-9 integer with nothing to say it is meaningless.
    #
    # NULL is the honest column value: no score exists, rather than a score
    # that happens to be missing.
    m["piotroski_score"] = None

    # ── TTM Reference Values ──────────────────────────────────

    if rev:        m["revenue_ttm"]    = float(rev)
    if ebitda:     m["ebitda_ttm"]     = float(ebitda)
    if ebit:       m["ebit_ttm"]       = float(ebit)
    if net_prof:   m["net_profit_ttm"] = float(net_prof)
    if eps:        m["eps_ttm"]        = float(eps)

    # ── Per Share ─────────────────────────────────────────────

    if eps:   m["eps_ttm_ref"] = float(eps)
    if bvps:  m["book_value_per_share"] = float(bvps)

    # Metadata
    m["compute_version"] = COMPUTE_VERSION
    m["computed_at"]     = now

    return m


# ── Database Write ────────────────────────────────────────────

def upsert_metrics(cur, asx_code: str, price_date, metrics: dict):
    """Insert one row into market.computed_metrics."""
    # Build dynamic INSERT for only the non-None columns
    time_val = datetime.combine(price_date, datetime.min.time()).replace(tzinfo=timezone.utc)

    cols   = ["time", "asx_code"] + list(metrics.keys())
    vals   = [time_val, asx_code] + list(metrics.values())
    placeholders = ", ".join(["%s"] * len(cols))
    col_str      = ", ".join(cols)
    update_str   = ", ".join([f"{c} = EXCLUDED.{c}" for c in metrics.keys()])

    sql = f"""
        INSERT INTO market.computed_metrics ({col_str})
        VALUES ({placeholders})
        ON CONFLICT (time, asx_code) DO UPDATE SET {update_str}
    """
    cur.execute(sql, vals)


# ── Main ──────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="ASX Compute Engine — daily metrics")
    parser.add_argument("--codes", nargs="+", help="Specific ASX codes")
    parser.add_argument("--run-id", type=int,
                        help="The compute run this stage belongs to. Given, a "
                             "FULL run records terminal stage evidence that it "
                             "covered its own source domain — which the "
                             "canonical writer requires before it may attribute "
                             "a row to this run.")
    parser.add_argument("--limit", type=int, help="Max stocks to process")
    args = parser.parse_args()

    conn = psycopg2.connect(DB_URL)
    cur  = conn.cursor()

    # The producer's source domain, stated once and used for both the work
    # and the proof.
    #
    # A price and annual financials are what compute_metrics actually needs;
    # a company with neither cannot be computed and is legitimately outside
    # the domain. Listing status is NOT part of it, and used to be: the
    # selection required market.companies.status = 'active' while
    # build_screener_universe reads market.companies_current, which includes
    # delisted codes. That is the identical mismatch that left 2,954
    # yearly_metrics rows with a live source untouched -- a producer narrower
    # than its own consumer, so the consumer reads rows the producer never
    # rewrites.
    SOURCE_DOMAIN_SQL = """
        SELECT DISTINCT p.asx_code
          FROM market.daily_prices p
          JOIN financials.annual_pnl f ON f.asx_code = p.asx_code
         ORDER BY p.asx_code
    """

    # Derived independently of the loop's selection, because comparing a run
    # against its own selection is circular: it agrees by construction and
    # proves nothing.
    cur.execute(SOURCE_DOMAIN_SQL)
    expected_codes = {r[0] for r in cur.fetchall()}
    written_codes: set[str] = set()

    # Get codes to process
    if args.codes:
        codes = [c.upper() for c in args.codes]
    else:
        sql = SOURCE_DOMAIN_SQL
        if args.limit:
            sql = sql.replace("ORDER BY p.asx_code",
                              f"ORDER BY p.asx_code LIMIT {args.limit}")
        cur.execute(sql)
        codes = [r[0] for r in cur.fetchall()]

    # One watermark for the whole run, obtained once and shared, so no
    # per-company path reimplements feed health and eventually forgets to.
    feed_health = fetch_feed_health(cur)
    dividend_source = DividendSource(feed_health)
    if not feed_health.healthy:
        log.warning("Dividend feed unhealthy: %s. Dividend metrics will be "
                    "written as unavailable rather than computed over a "
                    "window the feed has not observed.", feed_health.reason)

    log.info(f"Computing metrics for {len(codes)} stocks...")
    log.info("─" * 60)

    processed = 0
    skipped   = 0
    errors    = 0

    for i, asx_code in enumerate(codes, 1):
        try:
            price   = fetch_latest_price(cur, asx_code)
            if not price:
                skipped += 1
                continue

            fin     = fetch_financials(cur, asx_code)
            company = fetch_company(cur, asx_code)
            divs    = fetch_dividends(cur, asx_code)

            metrics = compute_metrics(asx_code, price, fin, company, divs,
                                      dividend_source)
            upsert_metrics(cur, asx_code, price["price_date"], metrics)
            processed += 1
            written_codes.add(asx_code)

            if i % 50 == 0:
                conn.commit()
                log.info(f"  [{i:4d}/{len(codes)}] {processed} computed, {skipped} skipped, {errors} errors")

        except Exception as e:
            errors += 1
            log.warning(f"  {asx_code}: {e}")

    conn.commit()

    # ── Terminal stage evidence ──────────────────────────────────────────────
    # universe_build consumes market.computed_metrics, so a canonical run
    # cannot truthfully claim its computed inputs were current while this
    # producer sits outside the lifecycle with no completeness proof. A scoped
    # run records nothing: its expected population is not the source domain,
    # and a stage row saying otherwise would be a false claim.
    scoped = bool(args.codes or args.limit)
    stage_ok = True
    if args.run_id is not None and not scoped:
        from compute.engine.run_stages import StageResult, record_stage

        result = StageResult(
            "daily_compute",
            frozenset(expected_codes), frozenset(written_codes),
            {"skipped_no_price": skipped, "errors": errors,
             "dividend_feed_healthy": feed_health.healthy})
        stage_ok = record_stage(cur, args.run_id, result)
        conn.commit()
        log.info("stage daily_compute: %s — %s", result.status, result.summary())
        if not stage_ok:
            log.error("daily_compute did not cover its source domain. No "
                      "canonical run can be published from this run.")
    elif args.run_id is not None:
        log.info("Stage evidence skipped: a scoped run's expected population "
                 "is not the source domain.")

    cur.close()
    conn.close()

    log.info("─" * 60)
    log.info(f"Done! {processed} computed | {skipped} skipped (no price) | {errors} errors")


if __name__ == "__main__":
    main()
