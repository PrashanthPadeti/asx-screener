"""
ASX Screener — Screener API Route  (Phase 1 Week 1 rewrite)
============================================================
Queries screener.universe directly — the single pre-computed Golden Record
table with 70+ columns per stock, rebuilt nightly by build_screener_universe.py.

Endpoints:
  POST /api/v1/screener           — Run a screen with dynamic filters
  GET  /api/v1/screener/fields    — All filterable fields with metadata
  GET  /api/v1/screener/presets   — Pre-built screen templates
"""

from fastapi import APIRouter, Depends, HTTPException, Body
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import csv
import io
import math
from datetime import date as date_type
from typing import Any

from app.db.session import get_db
from app.schemas.screener import ScreenerRequest, ScreenerResponse, ScreenerRow

router = APIRouter()

# ── Field registry ────────────────────────────────────────────────────────────
# col   : SQL column name or expression in screener.universe (alias: u)
# scale : multiply user-supplied filter value by this before comparing
#         0.01 → user types "15" meaning 15%, stored value is 0.15
#         1.0  → user types the raw stored value
# type  : "number" | "boolean" | "text"
# label : human-readable name for frontend
# unit  : display unit hint for frontend ("%", "AUD", "AUD M", "x", "")
# cat   : category group for UI rendering

ALLOWED_FIELDS: dict[str, dict] = {

    # ── Identity ──────────────────────────────────────────────────────────────
    "sector":          {"col": "u.sector",         "scale": 1,    "type": "text",    "label": "Sector",               "unit": "",     "cat": "Company"},
    "industry":        {"col": "u.industry",        "scale": 1,    "type": "text",    "label": "Industry",             "unit": "",     "cat": "Company"},
    "stock_type":      {"col": "u.stock_type",      "scale": 1,    "type": "text",    "label": "Stock Type",           "unit": "",     "cat": "Company"},
    "is_reit":         {"col": "u.is_reit",         "scale": 1,    "type": "boolean", "label": "Is REIT",              "unit": "",     "cat": "Company"},
    "is_miner":        {"col": "u.is_miner",        "scale": 1,    "type": "boolean", "label": "Is Miner",             "unit": "",     "cat": "Company"},
    "is_asx20":        {"col": "u.is_asx20",        "scale": 1,    "type": "boolean", "label": "In ASX 20",            "unit": "",     "cat": "Company"},
    "is_asx50":        {"col": "u.is_asx50",        "scale": 1,    "type": "boolean", "label": "In ASX 50",            "unit": "",     "cat": "Company"},
    "is_asx100":       {"col": "u.is_asx100",       "scale": 1,    "type": "boolean", "label": "In ASX 100",           "unit": "",     "cat": "Company"},
    "is_asx200":       {"col": "u.is_asx200",       "scale": 1,    "type": "boolean", "label": "In ASX 200",           "unit": "",     "cat": "Company"},
    "is_asx300":       {"col": "u.is_asx300",       "scale": 1,    "type": "boolean", "label": "In ASX 300",           "unit": "",     "cat": "Company"},

    # ── Price & Market ────────────────────────────────────────────────────────
    "price":           {"col": "u.price",           "scale": 1,    "type": "number",  "label": "Price (AUD)",          "unit": "AUD",  "cat": "Price"},
    "market_cap":      {"col": "u.market_cap",      "scale": 1_000_000, "type": "number",  "label": "Market Cap (AUD M)",   "unit": "AUD M","cat": "Price"},
    "volume":          {"col": "u.volume",          "scale": 1,    "type": "number",  "label": "Volume",               "unit": "",     "cat": "Price"},
    "avg_volume_20d":  {"col": "u.avg_volume_20d",  "scale": 1,    "type": "number",  "label": "Avg Volume 20D",       "unit": "",     "cat": "Price"},
    "high_52w":        {"col": "u.high_52w",        "scale": 1,    "type": "number",  "label": "52W High",             "unit": "AUD",  "cat": "Price"},
    "low_52w":         {"col": "u.low_52w",         "scale": 1,    "type": "number",  "label": "52W Low",              "unit": "AUD",  "cat": "Price"},

    # ── Valuation ─────────────────────────────────────────────────────────────
    "pe_ratio":        {"col": "u.pe_ratio",        "scale": 1,    "type": "number",  "label": "P/E Ratio",            "unit": "x",    "cat": "Valuation"},
    "forward_pe":      {"col": "u.forward_pe",      "scale": 1,    "type": "number",  "label": "Forward P/E",          "unit": "x",    "cat": "Valuation"},
    "peg_ratio":       {"col": "u.peg_ratio",       "scale": 1,    "type": "number",  "label": "PEG Ratio",            "unit": "x",    "cat": "Valuation"},
    "price_to_book":   {"col": "u.price_to_book",   "scale": 1,    "type": "number",  "label": "Price / Book",         "unit": "x",    "cat": "Valuation"},
    "price_to_sales":  {"col": "u.price_to_sales",  "scale": 1,    "type": "number",  "label": "Price / Sales",        "unit": "x",    "cat": "Valuation"},
    "price_to_fcf":    {"col": "u.price_to_fcf",    "scale": 1,    "type": "number",  "label": "Price / FCF",          "unit": "x",    "cat": "Valuation"},
    "ev_to_ebitda":    {"col": "u.ev_to_ebitda",    "scale": 1,    "type": "number",  "label": "EV / EBITDA",          "unit": "x",    "cat": "Valuation"},
    "ev_to_ebit":      {"col": "u.ev_to_ebit",      "scale": 1,    "type": "number",  "label": "EV / EBIT",            "unit": "x",    "cat": "Valuation"},
    "ev_to_revenue":   {"col": "u.ev_to_revenue",   "scale": 1,    "type": "number",  "label": "EV / Revenue",         "unit": "x",    "cat": "Valuation"},
    "graham_number":   {"col": "u.graham_number",   "scale": 1,    "type": "number",  "label": "Graham Number",        "unit": "AUD",  "cat": "Valuation"},
    "fcf_yield":       {"col": "u.fcf_yield",       "scale": 0.01, "type": "number",  "label": "FCF Yield %",          "unit": "%",    "cat": "Valuation"},

    # ── Dividends & Franking ──────────────────────────────────────────────────
    "dividend_yield":          {"col": "u.dividend_yield",          "scale": 0.01, "type": "number",  "label": "Dividend Yield %",         "unit": "%",   "cat": "Dividends"},
    "grossed_up_yield":        {"col": "u.grossed_up_yield",        "scale": 0.01, "type": "number",  "label": "Grossed-Up Yield %",       "unit": "%",   "cat": "Dividends"},
    "franking_pct":            {"col": "u.franking_pct",            "scale": 1,    "type": "number",  "label": "Franking %",               "unit": "%",   "cat": "Dividends"},
    "payout_ratio":            {"col": "u.payout_ratio",            "scale": 0.01, "type": "number",  "label": "Payout Ratio %",           "unit": "%",   "cat": "Dividends"},
    "dividend_cagr_3y":        {"col": "u.dividend_cagr_3y",        "scale": 0.01, "type": "number",  "label": "Dividend CAGR 3Y %",       "unit": "%",   "cat": "Dividends"},
    "dividend_consecutive_yrs":{"col": "u.dividend_consecutive_yrs","scale": 1,    "type": "number",  "label": "Consecutive Dividend Yrs", "unit": "yrs", "cat": "Dividends"},

    # ── Profitability & Returns ───────────────────────────────────────────────
    "gross_margin":     {"col": "u.gross_margin",    "scale": 0.01, "type": "number",  "label": "Gross Margin %",       "unit": "%",   "cat": "Profitability"},
    "ebitda_margin":    {"col": "u.ebitda_margin",   "scale": 0.01, "type": "number",  "label": "EBITDA Margin %",      "unit": "%",   "cat": "Profitability"},
    "net_margin":       {"col": "u.net_margin",      "scale": 0.01, "type": "number",  "label": "Net Margin %",         "unit": "%",   "cat": "Profitability"},
    "operating_margin": {"col": "u.operating_margin","scale": 0.01, "type": "number",  "label": "Operating Margin %",   "unit": "%",   "cat": "Profitability"},
    "roe":              {"col": "u.roe",             "scale": 0.01, "type": "number",  "label": "ROE %",                "unit": "%",   "cat": "Profitability"},
    "roa":              {"col": "u.roa",             "scale": 0.01, "type": "number",  "label": "ROA %",                "unit": "%",   "cat": "Profitability"},
    "roce":             {"col": "u.roce",            "scale": 0.01, "type": "number",  "label": "ROCE %",               "unit": "%",   "cat": "Profitability"},
    "avg_roe_3y":       {"col": "u.avg_roe_3y",      "scale": 0.01, "type": "number",  "label": "Avg ROE 3Y %",         "unit": "%",   "cat": "Profitability"},

    # ── Growth ────────────────────────────────────────────────────────────────
    "revenue_growth_1y":       {"col": "u.revenue_growth_1y",       "scale": 0.01, "type": "number", "label": "Revenue Growth 1Y %",      "unit": "%",   "cat": "Growth"},
    "revenue_growth_3y_cagr":  {"col": "u.revenue_growth_3y_cagr",  "scale": 0.01, "type": "number", "label": "Revenue CAGR 3Y %",        "unit": "%",   "cat": "Growth"},
    "revenue_cagr_5y":         {"col": "u.revenue_cagr_5y",         "scale": 0.01, "type": "number", "label": "Revenue CAGR 5Y %",        "unit": "%",   "cat": "Growth"},
    "earnings_growth_1y":      {"col": "u.earnings_growth_1y",      "scale": 0.01, "type": "number", "label": "Earnings Growth 1Y %",     "unit": "%",   "cat": "Growth"},
    "earnings_growth_3y_cagr": {"col": "u.earnings_growth_3y_cagr", "scale": 0.01, "type": "number", "label": "Earnings CAGR 3Y %",       "unit": "%",   "cat": "Growth"},
    "eps_growth_3y_cagr":      {"col": "u.eps_growth_3y_cagr",      "scale": 0.01, "type": "number", "label": "EPS CAGR 3Y %",           "unit": "%",   "cat": "Growth"},
    "revenue_growth_yoy_q":    {"col": "u.revenue_growth_yoy_q",    "scale": 0.01, "type": "number", "label": "Revenue Growth YoY Q %",   "unit": "%",   "cat": "Growth"},
    "revenue_growth_hoh":      {"col": "u.revenue_growth_hoh",      "scale": 0.01, "type": "number", "label": "Revenue Growth HoH % ★",  "unit": "%",   "cat": "Growth"},
    "net_income_growth_hoh":   {"col": "u.net_income_growth_hoh",   "scale": 0.01, "type": "number", "label": "Net Income Growth HoH % ★","unit": "%",  "cat": "Growth"},
    "eps_growth_hoh":          {"col": "u.eps_growth_hoh",          "scale": 0.01, "type": "number", "label": "EPS Growth HoH % ★",      "unit": "%",   "cat": "Growth"},

    # ── Balance Sheet & Leverage ──────────────────────────────────────────────
    "debt_to_equity":      {"col": "u.debt_to_equity",      "scale": 1,    "type": "number", "label": "Debt / Equity",        "unit": "x",   "cat": "Financial Health"},
    "current_ratio":       {"col": "u.current_ratio",       "scale": 1,    "type": "number", "label": "Current Ratio",        "unit": "x",   "cat": "Financial Health"},
    "net_debt":            {"col": "u.net_debt",            "scale": 1,    "type": "number", "label": "Net Debt (AUD M)",     "unit": "AUD M","cat": "Financial Health"},
    "total_debt":          {"col": "u.total_debt",          "scale": 1,    "type": "number", "label": "Total Debt (AUD M)",   "unit": "AUD M","cat": "Financial Health"},
    "book_value_per_share":{"col": "u.book_value_per_share","scale": 1,    "type": "number", "label": "Book Value Per Share", "unit": "AUD", "cat": "Financial Health"},
    "fcf_fy0":             {"col": "u.fcf_fy0",             "scale": 1,    "type": "number", "label": "Free Cash Flow (AUD M)","unit": "AUD M","cat": "Financial Health"},
    "cfo_fy0":             {"col": "u.cfo_fy0",             "scale": 1,    "type": "number", "label": "Operating CF (AUD M)", "unit": "AUD M","cat": "Financial Health"},

    # ── Quality Scores ────────────────────────────────────────────────────────
    "piotroski_f_score":    {"col": "u.piotroski_f_score",   "scale": 1,    "type": "number", "label": "Piotroski F-Score",    "unit": "",    "cat": "Quality"},
    "altman_z_score":       {"col": "u.altman_z_score",      "scale": 1,    "type": "number", "label": "Altman Z-Score",       "unit": "",    "cat": "Quality"},
    "percent_insiders":     {"col": "u.percent_insiders",    "scale": 1,    "type": "number", "label": "Insider Holding %",    "unit": "%",   "cat": "Quality"},
    "percent_institutions": {"col": "u.percent_institutions","scale": 1,    "type": "number", "label": "Institutional Holding %","unit": "%", "cat": "Quality"},
    "short_pct":            {"col": "u.short_pct",           "scale": 1,    "type": "number", "label": "Short Interest %",     "unit": "%",   "cat": "Quality"},

    # ── Technicals ────────────────────────────────────────────────────────────
    "rsi_14":        {"col": "u.rsi_14",        "scale": 1,    "type": "number",  "label": "RSI (14)",             "unit": "",    "cat": "Technicals"},
    "adx_14":        {"col": "u.adx_14",        "scale": 1,    "type": "number",  "label": "ADX (14)",             "unit": "",    "cat": "Technicals"},
    "macd":          {"col": "u.macd",          "scale": 1,    "type": "number",  "label": "MACD Line",            "unit": "",    "cat": "Technicals"},
    "sma_20":        {"col": "u.sma_20",        "scale": 1,    "type": "number",  "label": "SMA 20",               "unit": "AUD", "cat": "Technicals"},
    "sma_50":        {"col": "u.sma_50",        "scale": 1,    "type": "number",  "label": "SMA 50",               "unit": "AUD", "cat": "Technicals"},
    "sma_200":       {"col": "u.sma_200",       "scale": 1,    "type": "number",  "label": "SMA 200",              "unit": "AUD", "cat": "Technicals"},
    "above_sma50":   {"col": "(u.price > u.sma_50 AND u.sma_50 IS NOT NULL)",  "scale": 1, "type": "boolean", "label": "Above SMA 50",  "unit": "", "cat": "Technicals"},
    "above_sma200":  {"col": "(u.price > u.sma_200 AND u.sma_200 IS NOT NULL)","scale": 1, "type": "boolean", "label": "Above SMA 200", "unit": "", "cat": "Technicals"},
    "volatility_20d":{"col": "u.volatility_20d","scale": 0.01, "type": "number",  "label": "Volatility 20D %",     "unit": "%",   "cat": "Technicals"},
    "volatility_60d":{"col": "u.volatility_60d","scale": 0.01, "type": "number",  "label": "Volatility 60D %",     "unit": "%",   "cat": "Technicals"},
    "beta_1y":       {"col": "u.beta_1y",       "scale": 1,    "type": "number",  "label": "Beta (1Y)",            "unit": "",    "cat": "Technicals"},
    "sharpe_1y":     {"col": "u.sharpe_1y",     "scale": 1,    "type": "number",  "label": "Sharpe Ratio (1Y)",    "unit": "",    "cat": "Technicals"},
    "drawdown_from_ath": {"col": "u.drawdown_from_ath", "scale": 0.01, "type": "number", "label": "Drawdown from ATH %", "unit": "%", "cat": "Technicals"},

    # ── Price Returns ─────────────────────────────────────────────────────────
    "return_1w":  {"col": "u.return_1w",  "scale": 0.01, "type": "number", "label": "Return 1W %",  "unit": "%", "cat": "Returns"},
    "return_1m":  {"col": "u.return_1m",  "scale": 0.01, "type": "number", "label": "Return 1M %",  "unit": "%", "cat": "Returns"},
    "return_3m":  {"col": "u.return_3m",  "scale": 0.01, "type": "number", "label": "Return 3M %",  "unit": "%", "cat": "Returns"},
    "return_6m":  {"col": "u.return_6m",  "scale": 0.01, "type": "number", "label": "Return 6M %",  "unit": "%", "cat": "Returns"},
    "return_1y":  {"col": "u.return_1y",  "scale": 0.01, "type": "number", "label": "Return 1Y %",  "unit": "%", "cat": "Returns"},
    "return_ytd": {"col": "u.return_ytd", "scale": 0.01, "type": "number", "label": "Return YTD %", "unit": "%", "cat": "Returns"},
    "return_3y":  {"col": "u.return_3y",  "scale": 0.01, "type": "number", "label": "Return 3Y %",  "unit": "%", "cat": "Returns"},
    "return_5y":  {"col": "u.return_5y",  "scale": 0.01, "type": "number", "label": "Return 5Y %",  "unit": "%", "cat": "Returns"},
}

OPERATOR_MAP = {
    "gt":  ">",
    "gte": ">=",
    "lt":  "<",
    "lte": "<=",
    "eq":  "=",
    "neq": "!=",
    "in":  "IN",
}

# Columns allowed in ORDER BY (must be real columns, not expressions)
SORTABLE_COLS: dict[str, str] = {
    "asx_code":           "u.asx_code",
    "company_name":       "u.company_name",
    "price":              "u.price",
    "market_cap":         "u.market_cap",
    "volume":             "u.volume",
    "pe_ratio":           "u.pe_ratio",
    "price_to_book":      "u.price_to_book",
    "dividend_yield":     "u.dividend_yield",
    "grossed_up_yield":   "u.grossed_up_yield",
    "franking_pct":       "u.franking_pct",
    "roe":                "u.roe",
    "roa":                "u.roa",
    "roce":               "u.roce",
    "avg_roe_3y":         "u.avg_roe_3y",
    "net_margin":         "u.net_margin",
    "gross_margin":       "u.gross_margin",
    "ebitda_margin":      "u.ebitda_margin",
    "revenue_growth_1y":  "u.revenue_growth_1y",
    "earnings_growth_1y": "u.earnings_growth_1y",
    "revenue_cagr_5y":    "u.revenue_cagr_5y",
    "revenue_growth_hoh": "u.revenue_growth_hoh",
    "piotroski_f_score":  "u.piotroski_f_score",
    "altman_z_score":     "u.altman_z_score",
    "debt_to_equity":     "u.debt_to_equity",
    "rsi_14":             "u.rsi_14",
    "adx_14":             "u.adx_14",
    "return_1m":          "u.return_1m",
    "return_3m":          "u.return_3m",
    "return_1y":          "u.return_1y",
    "return_ytd":         "u.return_ytd",
    "volatility_20d":     "u.volatility_20d",
    "short_pct":          "u.short_pct",
    "high_52w":           "u.high_52w",
    "low_52w":            "u.low_52w",
    "fcf_yield":          "u.fcf_yield",
    "ev_to_ebitda":       "u.ev_to_ebitda",
}


def build_screener_sql(req: ScreenerRequest) -> tuple[str, str, dict]:
    """
    Build COUNT + DATA queries from the filter list.
    Queries screener.universe directly — no JOINs.
    Returns (count_sql, data_sql, params).
    """
    where_clauses: list[str] = ["u.price IS NOT NULL"]   # exclude no-price stocks
    params: dict[str, Any] = {}

    for i, f in enumerate(req.filters):
        field_key = f.field.lower()
        field_info = ALLOWED_FIELDS.get(field_key)
        if not field_info:
            raise HTTPException(status_code=400, detail=f"Unknown filter field: '{f.field}'")

        sql_col  = field_info["col"]
        ftype    = field_info["type"]
        scale    = field_info.get("scale", 1.0)
        operator = OPERATOR_MAP.get(f.operator.value)
        param_key = f"p{i}"

        if f.operator.value == "in":
            if not isinstance(f.value, list):
                raise HTTPException(
                    status_code=400,
                    detail=f"Field '{f.field}': 'in' operator requires a list value"
                )
            placeholders = ", ".join([f":{param_key}_{j}" for j in range(len(f.value))])
            where_clauses.append(f"({sql_col}) IN ({placeholders})")
            for j, v in enumerate(f.value):
                params[f"{param_key}_{j}"] = v

        elif ftype == "boolean":
            # Embed literal TRUE/FALSE to avoid asyncpg type inference issues with boolean params
            if isinstance(f.value, bool):
                bool_val = f.value
            elif isinstance(f.value, str):
                bool_val = f.value.lower() in ("true", "1", "yes")
            else:
                bool_val = bool(f.value)
            literal = "TRUE" if bool_val else "FALSE"
            where_clauses.append(f"({sql_col}) = {literal}")

        else:
            # number or text
            val = f.value
            if ftype == "number":
                try:
                    val = float(val) * scale
                except (TypeError, ValueError):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Field '{f.field}': expected a numeric value"
                    )
            where_clauses.append(f"({sql_col}) {operator} :{param_key}")
            params[param_key] = val

    where = " AND ".join(where_clauses)

    # Sort column — whitelist only
    sort_key = req.sort_by.lower()
    sort_expr = SORTABLE_COLS.get(sort_key, "u.market_cap")
    sort_dir  = "DESC" if req.sort_dir.lower() == "desc" else "ASC"

    count_sql = f"SELECT COUNT(*) FROM screener.universe u WHERE {where}"

    data_sql = f"""
        SELECT
            -- Identity
            u.asx_code, u.company_name, u.sector, u.industry, u.stock_type, u.status,
            u.is_reit, u.is_miner, u.is_asx200, u.is_asx300,

            -- Price
            u.price, u.high_52w, u.low_52w, u.volume, u.avg_volume_20d, u.market_cap,

            -- Valuation
            u.pe_ratio, u.forward_pe, u.price_to_book, u.price_to_sales,
            u.ev_to_ebitda, u.peg_ratio, u.price_to_fcf, u.fcf_yield,

            -- Dividends
            u.dividend_yield, u.grossed_up_yield, u.franking_pct,
            u.dps_ttm, u.payout_ratio, u.dividend_consecutive_yrs, u.dividend_cagr_3y,

            -- Profitability
            u.gross_margin, u.ebitda_margin, u.net_margin, u.operating_margin,
            u.roe, u.roa, u.roce, u.avg_roe_3y,

            -- Growth
            u.revenue_growth_1y, u.revenue_growth_3y_cagr, u.revenue_cagr_5y,
            u.earnings_growth_1y, u.eps_growth_3y_cagr,
            u.revenue_growth_yoy_q, u.eps_growth_yoy_q,
            u.revenue_growth_hoh, u.net_income_growth_hoh, u.eps_growth_hoh,

            -- Balance Sheet
            u.debt_to_equity, u.current_ratio, u.net_debt, u.total_debt,
            u.book_value_per_share, u.total_assets, u.total_equity,
            u.fcf_fy0, u.cfo_fy0,

            -- Quality Scores
            u.piotroski_f_score, u.altman_z_score,
            u.percent_insiders, u.percent_institutions, u.short_pct,

            -- Technicals
            u.rsi_14, u.adx_14, u.macd, u.macd_signal,
            u.sma_20, u.sma_50, u.sma_200, u.ema_20,
            u.bb_upper, u.bb_lower, u.atr_14, u.obv,
            u.volatility_20d, u.volatility_60d, u.beta_1y, u.sharpe_1y,

            -- Returns
            u.return_1w, u.return_1m, u.return_3m, u.return_6m,
            u.return_1y, u.return_ytd, u.return_3y, u.return_5y,
            u.drawdown_from_ath,

            -- Metadata
            u.price_date, u.universe_built_at

        FROM screener.universe u
        WHERE {where}
        ORDER BY {sort_expr} {sort_dir} NULLS LAST
        LIMIT :_limit OFFSET :_offset
    """

    return count_sql, data_sql, params


# ── POST /screener/batch ─────────────────────────────────────────────────────

@router.post("/batch", response_model=list[ScreenerRow])
async def batch_screener(
    codes: list[str] = Body(
        ...,
        min_length=1,
        max_length=50,
        embed=True,
        description="List of ASX codes (max 50) to fetch screener data for",
        example=["CBA", "BHP", "ANZ"],
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns screener.universe rows for a specific list of ASX codes.
    Used by the watchlist page to show live prices and key metrics.
    Input order is preserved in the response.
    """
    if not codes:
        return []

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for c in codes:
        u = c.strip().upper()
        if u and u not in seen:
            seen.add(u)
            unique.append(u)

    if not unique:
        return []

    # Build IN clause and CASE-based ORDER BY with individual named parameters.
    # asyncpg does not reliably convert Python lists to PG arrays in text() queries,
    # so we avoid ANY(:array) and array_position() entirely.
    placeholders = ", ".join(f":c{i}" for i in range(len(unique)))
    order_cases  = "\n            ".join(
        f"WHEN :c{i} THEN {i}" for i in range(len(unique))
    )
    params = {f"c{i}": code for i, code in enumerate(unique)}

    sql = f"""
        SELECT
            u.asx_code, u.company_name, u.sector, u.industry, u.stock_type, u.status,
            u.is_reit, u.is_miner, u.is_asx200, u.is_asx300,
            u.price, u.high_52w, u.low_52w, u.volume, u.avg_volume_20d, u.market_cap,
            u.pe_ratio, u.forward_pe, u.price_to_book, u.price_to_sales,
            u.ev_to_ebitda, u.peg_ratio, u.price_to_fcf, u.fcf_yield,
            u.dividend_yield, u.grossed_up_yield, u.franking_pct,
            u.dps_ttm, u.payout_ratio, u.dividend_consecutive_yrs, u.dividend_cagr_3y,
            u.gross_margin, u.ebitda_margin, u.net_margin, u.operating_margin,
            u.roe, u.roa, u.roce, u.avg_roe_3y,
            u.revenue_growth_1y, u.revenue_growth_3y_cagr, u.revenue_cagr_5y,
            u.earnings_growth_1y, u.eps_growth_3y_cagr,
            u.revenue_growth_yoy_q, u.eps_growth_yoy_q,
            u.revenue_growth_hoh, u.net_income_growth_hoh, u.eps_growth_hoh,
            u.debt_to_equity, u.current_ratio, u.net_debt, u.total_debt,
            u.book_value_per_share, u.total_assets, u.total_equity,
            u.fcf_fy0, u.cfo_fy0,
            u.piotroski_f_score, u.altman_z_score,
            u.percent_insiders, u.percent_institutions, u.short_pct,
            u.rsi_14, u.adx_14, u.macd, u.macd_signal,
            u.sma_20, u.sma_50, u.sma_200, u.ema_20,
            u.bb_upper, u.bb_lower, u.atr_14, u.obv,
            u.volatility_20d, u.volatility_60d, u.beta_1y, u.sharpe_1y,
            u.return_1w, u.return_1m, u.return_3m, u.return_6m,
            u.return_1y, u.return_ytd, u.return_3y, u.return_5y,
            u.drawdown_from_ath,
            u.price_date, u.universe_built_at
        FROM screener.universe u
        WHERE u.asx_code IN ({placeholders})
        ORDER BY
            CASE u.asx_code
            {order_cases}
            ELSE {len(unique)}
            END
    """
    result = await db.execute(text(sql), params)
    rows = result.mappings().all()
    return [ScreenerRow(**dict(r)) for r in rows]


# ── POST /screener ────────────────────────────────────────────────────────────

@router.post("", response_model=ScreenerResponse)
async def run_screener(
    req: ScreenerRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Run a stock screen with dynamic filters against screener.universe.

    All percentage fields accept human-readable % values:
    - ROE >= 15    → means ROE ≥ 15%
    - Div Yield >= 4 → means dividend yield ≥ 4%
    - Franking = 100 → means 100% franked (enter 0-100)

    Non-percentage fields use their raw values:
    - PE <= 20, Market Cap >= 500 (AUD M), Piotroski >= 7
    """
    try:
        count_sql, data_sql, params = build_screener_sql(req)
    except HTTPException:
        raise

    result = await db.execute(text(count_sql), params)
    total = result.scalar() or 0

    params["_limit"]  = req.page_size
    params["_offset"] = (req.page - 1) * req.page_size
    result = await db.execute(text(data_sql), params)
    rows = result.mappings().all()

    return ScreenerResponse(
        data=[ScreenerRow(**dict(r)) for r in rows],
        total=total,
        page=req.page,
        page_size=req.page_size,
        total_pages=math.ceil(total / req.page_size) if total else 0,
        filters_applied=len(req.filters),
    )


# ── POST /screener/export ─────────────────────────────────────────────────────

# Fields stored as decimal ratios (0.15 = 15%) that should be rendered as % in CSV
_PCT_COLS = {
    "fcf_yield", "dividend_yield", "grossed_up_yield", "payout_ratio",
    "dividend_cagr_3y", "gross_margin", "ebitda_margin", "net_margin",
    "operating_margin", "roe", "roa", "roce", "avg_roe_3y",
    "revenue_growth_1y", "revenue_growth_3y_cagr", "revenue_cagr_5y",
    "earnings_growth_1y", "eps_growth_3y_cagr",
    "revenue_growth_yoy_q", "eps_growth_yoy_q",
    "revenue_growth_hoh", "net_income_growth_hoh", "eps_growth_hoh",
    "return_1w", "return_1m", "return_3m", "return_6m",
    "return_1y", "return_ytd", "return_3y", "return_5y",
    "drawdown_from_ath", "volatility_20d", "volatility_60d",
}

# Human-readable header overrides
_HEADER_LABELS: dict[str, str] = {
    "asx_code":               "ASX Code",
    "company_name":           "Company Name",
    "sector":                 "Sector",
    "industry":               "Industry",
    "stock_type":             "Stock Type",
    "status":                 "Status",
    "is_reit":                "REIT",
    "is_miner":               "Miner",
    "is_asx200":              "ASX 200",
    "is_asx300":              "ASX 300",
    "price":                  "Price (AUD)",
    "high_52w":               "52W High",
    "low_52w":                "52W Low",
    "volume":                 "Volume",
    "avg_volume_20d":         "Avg Vol 20D",
    "market_cap":             "Market Cap (AUD M)",
    "pe_ratio":               "P/E",
    "forward_pe":             "Fwd P/E",
    "price_to_book":          "P/B",
    "price_to_sales":         "P/S",
    "ev_to_ebitda":           "EV/EBITDA",
    "peg_ratio":              "PEG",
    "price_to_fcf":           "P/FCF",
    "fcf_yield":              "FCF Yield %",
    "dividend_yield":         "Div Yield %",
    "grossed_up_yield":       "Grossed-Up Yield %",
    "franking_pct":           "Franking %",
    "dps_ttm":                "DPS TTM (AUD)",
    "payout_ratio":           "Payout Ratio %",
    "dividend_consecutive_yrs": "Consec. Div Yrs",
    "dividend_cagr_3y":       "Div CAGR 3Y %",
    "gross_margin":           "Gross Margin %",
    "ebitda_margin":          "EBITDA Margin %",
    "net_margin":             "Net Margin %",
    "operating_margin":       "Op. Margin %",
    "roe":                    "ROE %",
    "roa":                    "ROA %",
    "roce":                   "ROCE %",
    "avg_roe_3y":             "Avg ROE 3Y %",
    "revenue_growth_1y":      "Rev Growth 1Y %",
    "revenue_growth_3y_cagr": "Rev CAGR 3Y %",
    "revenue_cagr_5y":        "Rev CAGR 5Y %",
    "earnings_growth_1y":     "Earnings Growth 1Y %",
    "eps_growth_3y_cagr":     "EPS CAGR 3Y %",
    "revenue_growth_yoy_q":   "Rev Growth YoY Q %",
    "eps_growth_yoy_q":       "EPS Growth YoY Q %",
    "revenue_growth_hoh":     "Rev Growth HoH % ★",
    "net_income_growth_hoh":  "NI Growth HoH % ★",
    "eps_growth_hoh":         "EPS Growth HoH % ★",
    "debt_to_equity":         "D/E",
    "current_ratio":          "Current Ratio",
    "net_debt":               "Net Debt (AUD M)",
    "total_debt":             "Total Debt (AUD M)",
    "book_value_per_share":   "BVPS (AUD)",
    "total_assets":           "Total Assets (AUD M)",
    "total_equity":           "Total Equity (AUD M)",
    "fcf_fy0":                "FCF FY0 (AUD M)",
    "cfo_fy0":                "CFO FY0 (AUD M)",
    "piotroski_f_score":      "Piotroski F",
    "altman_z_score":         "Altman Z",
    "percent_insiders":       "Insider %",
    "percent_institutions":   "Institutional %",
    "short_pct":              "Short %",
    "rsi_14":                 "RSI(14)",
    "adx_14":                 "ADX(14)",
    "macd":                   "MACD",
    "macd_signal":            "MACD Signal",
    "sma_20":                 "SMA 20",
    "sma_50":                 "SMA 50",
    "sma_200":                "SMA 200",
    "ema_20":                 "EMA 20",
    "bb_upper":               "BB Upper",
    "bb_lower":               "BB Lower",
    "atr_14":                 "ATR(14)",
    "obv":                    "OBV",
    "volatility_20d":         "Volatility 20D %",
    "volatility_60d":         "Volatility 60D %",
    "beta_1y":                "Beta (1Y)",
    "sharpe_1y":              "Sharpe (1Y)",
    "return_1w":              "Return 1W %",
    "return_1m":              "Return 1M %",
    "return_3m":              "Return 3M %",
    "return_6m":              "Return 6M %",
    "return_1y":              "Return 1Y %",
    "return_ytd":             "Return YTD %",
    "return_3y":              "Return 3Y %",
    "return_5y":              "Return 5Y %",
    "drawdown_from_ath":      "Drawdown from ATH %",
    "price_date":             "Price Date",
    "universe_built_at":      "Data Updated At",
}

# Ordered export columns (subset of ScreenerRow — skip noisy technicals by default)
_EXPORT_COLS: list[str] = [
    "asx_code", "company_name", "sector", "industry", "stock_type",
    "is_reit", "is_miner", "is_asx200", "is_asx300",
    # Price
    "price", "market_cap", "volume", "high_52w", "low_52w",
    # Valuation
    "pe_ratio", "forward_pe", "price_to_book", "price_to_sales",
    "ev_to_ebitda", "peg_ratio", "fcf_yield",
    # Dividends
    "dividend_yield", "grossed_up_yield", "franking_pct",
    "dps_ttm", "payout_ratio", "dividend_consecutive_yrs", "dividend_cagr_3y",
    # Profitability
    "gross_margin", "ebitda_margin", "net_margin", "operating_margin",
    "roe", "roa", "roce", "avg_roe_3y",
    # Growth
    "revenue_growth_1y", "revenue_growth_3y_cagr", "revenue_cagr_5y",
    "earnings_growth_1y", "eps_growth_3y_cagr",
    "revenue_growth_hoh", "net_income_growth_hoh", "eps_growth_hoh",
    # Balance Sheet
    "debt_to_equity", "current_ratio", "net_debt", "total_debt",
    "book_value_per_share", "total_assets", "total_equity",
    "fcf_fy0", "cfo_fy0",
    # Quality
    "piotroski_f_score", "altman_z_score",
    "percent_insiders", "percent_institutions", "short_pct",
    # Technicals
    "rsi_14", "adx_14", "sma_50", "sma_200",
    "volatility_20d", "beta_1y", "sharpe_1y",
    # Returns
    "return_1w", "return_1m", "return_3m", "return_6m",
    "return_1y", "return_ytd", "return_3y", "return_5y",
    "drawdown_from_ath",
    # Meta
    "price_date",
]

_EXPORT_MAX_ROWS = 5_000


def _fmt_val(col: str, val: Any) -> str:
    """Format a value for CSV output. Converts decimal ratios → percentage strings."""
    if val is None:
        return ""
    if col in _PCT_COLS and isinstance(val, (int, float)):
        return f"{val * 100:.2f}"
    if isinstance(val, float):
        # Round to 4 dp for cleanliness
        return f"{val:.4f}".rstrip("0").rstrip(".")
    return str(val)


@router.post("/export")
async def export_screener(
    req: ScreenerRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Stream screener results as a CSV file download (max 5,000 rows).

    Takes the same request body as POST /screener (filters + sort),
    ignores page/page_size, and returns all matching rows up to the cap.

    Percentage fields (ROE, yields, margins, returns) are scaled to human-
    readable % values in the CSV (e.g. 0.15 → 15.00).

    Response: Content-Disposition: attachment; filename="asx_screener_YYYY-MM-DD.csv"
    """
    try:
        _, data_sql, params = build_screener_sql(req)
    except HTTPException:
        raise

    # Strip pagination and apply hard cap
    export_sql = data_sql.replace(
        "LIMIT :_limit OFFSET :_offset",
        f"LIMIT {_EXPORT_MAX_ROWS}"
    )
    # Remove pagination params if present
    params.pop("_limit",  None)
    params.pop("_offset", None)

    result = await db.execute(text(export_sql), params)
    rows = result.mappings().all()

    def generate() -> Any:
        buf = io.StringIO()
        writer = csv.writer(buf)

        # Header row
        writer.writerow([_HEADER_LABELS.get(c, c) for c in _EXPORT_COLS])
        yield buf.getvalue()

        for row in rows:
            buf.truncate(0)
            buf.seek(0)
            writer.writerow([_fmt_val(col, row.get(col)) for col in _EXPORT_COLS])
            yield buf.getvalue()

    filename = f"asx_screener_{date_type.today().isoformat()}.csv"
    return StreamingResponse(
        generate(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── GET /screener/fields ──────────────────────────────────────────────────────

@router.get("/fields")
async def get_screener_fields():
    """
    Returns all filterable fields grouped by category.
    Drives the dynamic filter builder in the frontend.
    """
    # Group fields by category
    categories: dict[str, list] = {}
    for key, info in ALLOWED_FIELDS.items():
        cat = info["cat"]
        if cat not in categories:
            categories[cat] = []
        categories[cat].append({
            "key":   key,
            "label": info["label"],
            "type":  info["type"],
            "unit":  info.get("unit", ""),
            "scale": info.get("scale", 1.0),
        })

    return {
        "categories": categories,
        "operators": {
            "number":  [
                {"value": "gte", "label": "≥"},
                {"value": "lte", "label": "≤"},
                {"value": "gt",  "label": ">"},
                {"value": "lt",  "label": "<"},
                {"value": "eq",  "label": "="},
                {"value": "neq", "label": "≠"},
            ],
            "boolean": [{"value": "eq", "label": "is"}],
            "text":    [
                {"value": "eq",  "label": "="},
                {"value": "neq", "label": "≠"},
                {"value": "in",  "label": "in list"},
            ],
        },
        "total_fields": len(ALLOWED_FIELDS),
    }


# ── GET /screener/presets ─────────────────────────────────────────────────────

@router.get("/presets")
async def get_screener_presets():
    """Pre-built screen templates. premium=True presets require Pro plan or higher."""
    return {
        "presets": [
            # ── Free presets ──────────────────────────────────────────────────
            {
                "id":          "value_franked",
                "name":        "Value + Fully Franked",
                "description": "Low PE, 100% franked dividends, profitable ASX stocks",
                "icon":        "shield",
                "premium":     False,
                "filters": [
                    {"field": "pe_ratio",      "operator": "lte", "value": 15},
                    {"field": "franking_pct",  "operator": "eq",  "value": 100},
                    {"field": "dividend_yield","operator": "gte", "value": 3},
                    {"field": "net_margin",    "operator": "gt",  "value": 0},
                ],
                "sort_by": "grossed_up_yield", "sort_dir": "desc",
            },
            {
                "id":          "momentum",
                "name":        "Price Momentum",
                "description": "Strong trend — above all key MAs with ADX confirmation",
                "icon":        "zap",
                "premium":     False,
                "filters": [
                    {"field": "return_3m",    "operator": "gte", "value": 10},
                    {"field": "above_sma200", "operator": "eq",  "value": True},
                    {"field": "adx_14",       "operator": "gte", "value": 25},
                    {"field": "rsi_14",       "operator": "lte", "value": 65},
                ],
                "sort_by": "return_3m", "sort_dir": "desc",
            },
            {
                "id":          "piotroski_strong",
                "name":        "Piotroski Strong (F ≥ 7)",
                "description": "Financially healthy stocks by Piotroski F-Score",
                "icon":        "award",
                "premium":     False,
                "filters": [
                    {"field": "piotroski_f_score", "operator": "gte", "value": 7},
                    {"field": "market_cap",        "operator": "gte", "value": 100},
                ],
                "sort_by": "piotroski_f_score", "sort_dir": "desc",
            },
            {
                "id":          "turnaround",
                "name":        "Potential Turnaround",
                "description": "Oversold stocks near 52W low with positive FCF",
                "icon":        "rotate-ccw",
                "premium":     False,
                "filters": [
                    {"field": "rsi_14",            "operator": "lte", "value": 35},
                    {"field": "fcf_fy0",           "operator": "gt",  "value": 0},
                    {"field": "debt_to_equity",    "operator": "lte", "value": 1.5},
                ],
                "sort_by": "rsi_14", "sort_dir": "asc",
            },

            # ── Pro+ presets ──────────────────────────────────────────────────
            {
                "id":          "dividend_income",
                "name":        "Dividend Income Portfolio",
                "description": "High-yield franked stocks with sustainable payouts for income investors",
                "icon":        "dollar-sign",
                "premium":     True,
                "min_plan":    "pro",
                "filters": [
                    {"field": "dividend_yield",         "operator": "gte", "value": 4},
                    {"field": "franking_pct",           "operator": "gte", "value": 70},
                    {"field": "payout_ratio",           "operator": "lte", "value": 85},
                    {"field": "dividend_consecutive_yrs","operator": "gte", "value": 3},
                    {"field": "net_margin",             "operator": "gt",  "value": 0},
                ],
                "sort_by": "grossed_up_yield", "sort_dir": "desc",
            },
            {
                "id":          "quality_undervalued",
                "name":        "Quality Undervalued",
                "description": "High-quality businesses trading at a discount — low PE with strong fundamentals",
                "icon":        "search",
                "premium":     True,
                "min_plan":    "pro",
                "filters": [
                    {"field": "pe_ratio",          "operator": "lte", "value": 15},
                    {"field": "piotroski_f_score", "operator": "gte", "value": 7},
                    {"field": "roe",               "operator": "gte", "value": 12},
                    {"field": "debt_to_equity",    "operator": "lte", "value": 0.5},
                    {"field": "net_margin",        "operator": "gt",  "value": 5},
                ],
                "sort_by": "quality_score", "sort_dir": "desc",
            },
            {
                "id":          "high_growth",
                "name":        "Fast Growing Companies",
                "description": "Top-line and earnings accelerating — identify tomorrow's compounders today",
                "icon":        "trending-up",
                "premium":     True,
                "min_plan":    "pro",
                "filters": [
                    {"field": "revenue_growth_1y",  "operator": "gte", "value": 20},
                    {"field": "earnings_growth_1y", "operator": "gte", "value": 15},
                    {"field": "net_margin",         "operator": "gt",  "value": 0},
                    {"field": "market_cap",         "operator": "gte", "value": 50},
                ],
                "sort_by": "earnings_growth_1y", "sort_dir": "desc",
            },
            {
                "id":          "ma_crossover",
                "name":        "50/200-Day MA Crossover",
                "description": "Golden cross signal — price above both key moving averages with momentum",
                "icon":        "bar-chart-2",
                "premium":     True,
                "min_plan":    "pro",
                "filters": [
                    {"field": "above_sma50",  "operator": "eq",  "value": True},
                    {"field": "above_sma200", "operator": "eq",  "value": True},
                    {"field": "return_1m",    "operator": "gte", "value": 3},
                    {"field": "market_cap",   "operator": "gte", "value": 100},
                ],
                "sort_by": "momentum_score", "sort_dir": "desc",
            },
            {
                "id":          "new_52w_highs",
                "name":        "New 52-Week Highs",
                "description": "Stocks at or near all-time highs — breakout candidates with strong momentum",
                "icon":        "arrow-up",
                "premium":     True,
                "min_plan":    "pro",
                "filters": [
                    {"field": "pct_from_52w_high", "operator": "gte", "value": -5},
                    {"field": "return_3m",         "operator": "gte", "value": 5},
                    {"field": "volume",            "operator": "gte", "value": 100000},
                ],
                "sort_by": "return_3m", "sort_dir": "desc",
            },
            {
                "id":          "deep_value_growth",
                "name":        "P/E < 10 + EPS Growth",
                "description": "Deep value stocks with earnings growth — the rarest and most rewarding combination",
                "icon":        "star",
                "premium":     True,
                "min_plan":    "pro",
                "filters": [
                    {"field": "pe_ratio",          "operator": "lte", "value": 10},
                    {"field": "pe_ratio",          "operator": "gt",  "value": 0},
                    {"field": "earnings_growth_1y","operator": "gte", "value": 5},
                    {"field": "market_cap",        "operator": "gte", "value": 50},
                ],
                "sort_by": "earnings_growth_1y", "sort_dir": "desc",
            },
            {
                "id":          "halfyearly_acceleration",
                "name":        "Half-Yearly Acceleration",
                "description": "Revenue and EPS accelerating half-over-half — unique ASX reporting insight",
                "icon":        "activity",
                "premium":     True,
                "min_plan":    "pro",
                "filters": [
                    {"field": "revenue_growth_hoh", "operator": "gte", "value": 10},
                    {"field": "eps_growth_hoh",     "operator": "gte", "value": 10},
                    {"field": "net_margin",         "operator": "gt",  "value": 0},
                ],
                "sort_by": "revenue_growth_hoh", "sort_dir": "desc",
            },
        ]
    }
