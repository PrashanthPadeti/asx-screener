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

from fastapi import APIRouter, Depends, HTTPException, Body, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import csv
import hashlib
import io
import json
import math
from datetime import date as date_type
from typing import Any, Optional

from app.db.session import get_db
from app.schemas.screener import ScreenerRequest, ScreenerResponse, ScreenerRow, QueryScreenerRequest
from app.core.cache import cache_get, cache_set, make_key, SCREENER_TTL
from app.core.deps import get_optional_user, get_current_user, require_admin, require_query_access
from app.core.query_parser import parse_query, get_field_reference, QueryParseError

FREE_STOCK_LIMIT = 500   # max rows visible to free / unauthenticated users

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
    "sector":          {"col": "u.sector",         "scale": 1,    "type": "text",    "label": "Sector",               "unit": "",     "cat": "Market Data"},
    "industry":        {"col": "u.industry",        "scale": 1,    "type": "text",    "label": "Industry",             "unit": "",     "cat": "Market Data"},
    "stock_type":      {"col": "u.stock_type",      "scale": 1,    "type": "text",    "label": "Stock Type",           "unit": "",     "cat": "Market Data"},
    "is_reit":         {"col": "u.is_reit",         "scale": 1,    "type": "boolean", "label": "Is REIT",              "unit": "",     "cat": "Market Data"},
    "is_miner":        {"col": "u.is_miner",        "scale": 1,    "type": "boolean", "label": "Is Miner",             "unit": "",     "cat": "Market Data"},
    "is_asx20":        {"col": "u.is_asx20",        "scale": 1,    "type": "boolean", "label": "In ASX 20",            "unit": "",     "cat": "Market Data"},
    "is_asx50":        {"col": "u.is_asx50",        "scale": 1,    "type": "boolean", "label": "In ASX 50",            "unit": "",     "cat": "Market Data"},
    "is_asx100":       {"col": "u.is_asx100",       "scale": 1,    "type": "boolean", "label": "In ASX 100",           "unit": "",     "cat": "Market Data"},
    "is_asx200":       {"col": "u.is_asx200",       "scale": 1,    "type": "boolean", "label": "In ASX 200",           "unit": "",     "cat": "Market Data"},
    "is_asx300":       {"col": "u.is_asx300",       "scale": 1,    "type": "boolean", "label": "In ASX 300",           "unit": "",     "cat": "Market Data"},

    # ── Price & Market ────────────────────────────────────────────────────────
    "price":               {"col": "u.price",               "scale": 1,          "type": "number",  "label": "Price (AUD)",                    "unit": "AUD",   "cat": "Price"},
    "market_cap":          {"col": "u.market_cap",          "scale": 1_000_000,  "type": "number",  "label": "Market Cap (AUD M)",             "unit": "AUD M", "cat": "Price"},
    "enterprise_value":    {"col": "u.ev",                  "scale": 1_000_000,  "type": "number",  "label": "Enterprise Value (AUD M)",       "unit": "AUD M", "cat": "Price"},  # col=u.ev
    "volume":              {"col": "u.volume",              "scale": 1,          "type": "number",  "label": "Volume",                         "unit": "",      "cat": "Market Data"},
    "avg_volume_20d":      {"col": "u.avg_volume_20d",      "scale": 1,          "type": "number",  "label": "Avg Volume 20D",                 "unit": "",      "cat": "Market Data"},
    "dollar_volume_avg_20d":{"col": "u.dollar_volume_avg_20d","scale": 1_000_000,"type": "number",  "label": "Avg Dollar Volume 20D (AUD M)",  "unit": "AUD M", "cat": "Price"},
    "shares_outstanding":  {"col": "u.shares_outstanding",  "scale": 1,          "type": "number",  "label": "Shares Outstanding",             "unit": "",      "cat": "Market Data"},
    "high_52w":            {"col": "u.high_52w",            "scale": 1,          "type": "number",  "label": "52W High",                       "unit": "AUD",   "cat": "Price"},
    "low_52w":             {"col": "u.low_52w",             "scale": 1,          "type": "number",  "label": "52W Low",                        "unit": "AUD",   "cat": "Price"},
    "pct_from_52w_high":   {"col": "((u.price - u.high_52w) / NULLIF(u.high_52w, 0) * 100)", "scale": 1, "type": "number", "label": "% from 52W High", "unit": "%", "cat": "Price"},
    "pct_from_52w_low":    {"col": "((u.price - u.low_52w)  / NULLIF(u.low_52w,  0) * 100)", "scale": 1, "type": "number", "label": "% from 52W Low",  "unit": "%", "cat": "Price"},
    "volume_ratio":        {"col": "(u.volume::float / NULLIF(u.avg_volume_20d, 0))",         "scale": 1, "type": "number", "label": "Volume Ratio (vs 20D Avg)", "unit": "x", "cat": "Price"},
    "above_vwap":          {"col": "u.above_vwap",          "scale": 1,          "type": "boolean", "label": "Price Above VWAP",               "unit": "",      "cat": "Market Data"},

    # ── Valuation ─────────────────────────────────────────────────────────────
    "pe_ratio":        {"col": "u.pe_ratio",        "scale": 1,    "type": "number",  "label": "P/E Ratio",            "unit": "x",    "cat": "Valuation"},
    "forward_pe":      {"col": "u.forward_pe",      "scale": 1,    "type": "number",  "label": "Forward P/E",          "unit": "x",    "cat": "Valuation"},
    "peg_ratio":       {"col": "u.peg_ratio",       "scale": 1,    "type": "number",  "label": "PEG Ratio",            "unit": "x",    "cat": "Valuation"},
    "price_to_book":   {"col": "u.price_to_book",   "scale": 1,    "type": "number",  "label": "Price / Book",         "unit": "x",    "cat": "Valuation"},
    "price_to_sales":  {"col": "u.price_to_sales",  "scale": 1,    "type": "number",  "label": "Price / Sales",        "unit": "x",    "cat": "Valuation"},
    "price_to_fcf":    {"col": "u.price_to_fcf",    "scale": 1,    "type": "number",  "label": "Price / FCF",          "unit": "x",    "cat": "Valuation"},  # TODO: populate in build script
    "ev_to_ebitda":    {"col": "u.ev_to_ebitda",    "scale": 1,    "type": "number",  "label": "EV / EBITDA",          "unit": "x",    "cat": "Valuation"},
    "ev_to_revenue":   {"col": "u.ev_to_revenue",   "scale": 1,    "type": "number",  "label": "EV / Revenue",         "unit": "x",    "cat": "Valuation"},
    "ev_to_ebit":      {"col": "u.ev_to_ebit",      "scale": 1,    "type": "number",  "label": "EV / EBIT",            "unit": "x",    "cat": "Valuation"},
    "graham_number":   {"col": "u.graham_number",   "scale": 1,    "type": "number",  "label": "Graham Number",        "unit": "AUD",  "cat": "Valuation"},  # TODO: populate in build script
    "fcf_yield":       {"col": "u.fcf_yield",       "scale": 0.01, "type": "number",  "label": "FCF Yield %",          "unit": "%",    "cat": "Valuation"},
    "earnings_yield":  {"col": "(1.0 / NULLIF(u.pe_ratio, 0) * 100)", "scale": 1, "type": "number",  "label": "Earnings Yield %",     "unit": "%",    "cat": "Valuation"},  # inverse of P/E

    # ── Dividends & Franking ──────────────────────────────────────────────────
    "dividend_yield":           {"col": "u.dividend_yield",           "scale": 0.01, "type": "number", "label": "Dividend Yield %",          "unit": "%",   "cat": "Dividends"},
    "grossed_up_yield":         {"col": "u.grossed_up_yield",         "scale": 0.01, "type": "number", "label": "Grossed-Up Yield %",        "unit": "%",   "cat": "Dividends"},
    "franking_pct":             {"col": "u.franking_pct",             "scale": 1,    "type": "number", "label": "Franking %",                "unit": "%",   "cat": "Dividends"},
    "payout_ratio":             {"col": "u.payout_ratio",             "scale": 0.01, "type": "number", "label": "Payout Ratio %",            "unit": "%",   "cat": "Dividends"},  # TODO: fix eps in annual_pnl
    "dps":                      {"col": "u.dps_ttm",                  "scale": 1,    "type": "number", "label": "DPS TTM (AUD)",             "unit": "AUD", "cat": "Dividends"},   # col=u.dps_ttm
    "dividend_cagr_3y":         {"col": "u.dividend_cagr_3y",         "scale": 0.01, "type": "number", "label": "Dividend CAGR 3Y %",        "unit": "%",   "cat": "Dividends"},
    "dividend_cagr_5y":         {"col": "u.dividend_cagr_5y",         "scale": 0.01, "type": "number", "label": "Dividend CAGR 5Y %",        "unit": "%",   "cat": "Dividends"},
    "dividend_consecutive_yrs": {"col": "u.dividend_consecutive_yrs", "scale": 1,    "type": "number", "label": "Consecutive Dividend Yrs",  "unit": "yrs", "cat": "Dividends"},

    # ── Profitability ─────────────────────────────────────────────────────────
    "gross_margin":             {"col": "u.gross_margin",             "scale": 0.01, "type": "number", "label": "Gross Margin %",            "unit": "%",   "cat": "Profitability"},
    "ebitda_margin":            {"col": "u.ebitda_margin",            "scale": 0.01, "type": "number", "label": "EBITDA Margin %",           "unit": "%",   "cat": "Profitability"},
    "net_margin":               {"col": "u.net_margin",               "scale": 0.01, "type": "number", "label": "Net Margin %",              "unit": "%",   "cat": "Profitability"},
    "operating_margin":         {"col": "u.operating_margin",         "scale": 0.01, "type": "number", "label": "Operating Margin %",        "unit": "%",   "cat": "Profitability"},
    "roe":                      {"col": "u.roe",                      "scale": 0.01, "type": "number", "label": "ROE %",                     "unit": "%",   "cat": "Profitability"},
    "roa":                      {"col": "u.roa",                      "scale": 0.01, "type": "number", "label": "ROA %",                     "unit": "%",   "cat": "Profitability"},
    "roce":                     {"col": "u.roce",                     "scale": 0.01, "type": "number", "label": "ROCE %",                    "unit": "%",   "cat": "Profitability"},
    "avg_roe_3y":               {"col": "u.avg_roe_3y",               "scale": 0.01, "type": "number", "label": "Avg ROE 3Y %",              "unit": "%",   "cat": "Quality"},
    "avg_roic_3y":              {"col": "u.avg_roic_3y",              "scale": 0.01, "type": "number", "label": "Avg ROIC 3Y %",             "unit": "%",   "cat": "Quality"},
    "avg_roic_5y":              {"col": "u.avg_roic_5y",              "scale": 0.01, "type": "number", "label": "Avg ROIC 5Y %",             "unit": "%",   "cat": "Quality"},
    "capital_efficiency_score": {"col": "u.capital_efficiency_score", "scale": 1,    "type": "number", "label": "Capital Efficiency Score",  "unit": "",    "cat": "Quality"},
    "roic":                     {"col": "u.roic",                     "scale": 0.01, "type": "number", "label": "ROIC %",                    "unit": "%",   "cat": "Profitability"},
    "asset_turnover":           {"col": "u.asset_turnover",           "scale": 1,    "type": "number", "label": "Asset Turnover",            "unit": "x",   "cat": "Profitability"},
    "ocf_margin":               {"col": "u.ocf_margin",               "scale": 0.01, "type": "number", "label": "OCF Margin %",              "unit": "%",   "cat": "Profitability"},
    "fcf_margin":               {"col": "u.fcf_margin",               "scale": 0.01, "type": "number", "label": "FCF Margin %",              "unit": "%",   "cat": "Profitability"},
    "capex_intensity":          {"col": "u.capex_intensity",          "scale": 0.01, "type": "number", "label": "Capex Intensity %",         "unit": "%",   "cat": "Profitability"},
    "inventory_turnover":       {"col": "u.inventory_turnover",       "scale": 1,    "type": "number", "label": "Inventory Turnover",        "unit": "x",   "cat": "Profitability"},  # TODO: add to screener.universe schema

    # ── Per-Share (EPS → Profitability; BVPS → Financial Strength) ──────────────
    "eps":                  {"col": "u.eps_fy0",          "scale": 1,    "type": "number", "label": "EPS FY0 (AUD)",             "unit": "AUD", "cat": "Profitability"},   # col=u.eps_fy0
    "eps_fy0":              {"col": "u.eps_fy0",          "scale": 1,    "type": "number", "label": "EPS FY0 (AUD)",             "unit": "AUD", "cat": "Profitability"},
    "eps_fy1":              {"col": "u.eps_fy1",          "scale": 1,    "type": "number", "label": "EPS FY1 Est (AUD)",         "unit": "AUD", "cat": "Profitability"},   # TODO: populate from analyst_ratings
    "book_value_per_share": {"col": "u.book_value_per_share", "scale": 1, "type": "number", "label": "Book Value per Share (AUD)", "unit": "AUD", "cat": "Financial Strength"},

    # ── Growth ────────────────────────────────────────────────────────────────
    "revenue":                  {"col": "u.revenue_ttm",          "scale": 1_000_000, "type": "number", "label": "Revenue TTM (AUD M)",      "unit": "AUD M", "cat": "Financial Strength"},  # col=u.revenue_ttm
    "net_income":               {"col": "u.net_profit_fy0",       "scale": 1_000_000, "type": "number", "label": "Net Income FY0 (AUD M)",   "unit": "AUD M", "cat": "Financial Strength"},  # col=u.net_profit_fy0
    "revenue_growth_1y":        {"col": "u.revenue_growth_1y",        "scale": 0.01, "type": "number", "label": "Revenue Growth 1Y %",      "unit": "%",   "cat": "Growth"},
    "revenue_growth_3y_cagr":   {"col": "u.revenue_growth_3y_cagr",   "scale": 0.01, "type": "number", "label": "Revenue CAGR 3Y %",        "unit": "%",   "cat": "Growth"},
    "revenue_cagr_5y":          {"col": "u.revenue_cagr_5y",          "scale": 0.01, "type": "number", "label": "Revenue CAGR 5Y %",        "unit": "%",   "cat": "Growth"},
    "earnings_growth_1y":       {"col": "u.earnings_growth_1y",       "scale": 0.01, "type": "number", "label": "Earnings Growth 1Y %",     "unit": "%",   "cat": "Growth"},
    "earnings_growth_3y_cagr":  {"col": "u.earnings_growth_3y_cagr",  "scale": 0.01, "type": "number", "label": "Earnings CAGR 3Y %",       "unit": "%",   "cat": "Growth"},
    "eps_growth_3y_cagr":       {"col": "u.eps_growth_3y_cagr",       "scale": 0.01, "type": "number", "label": "EPS CAGR 3Y %",            "unit": "%",   "cat": "Growth"},
    "eps_cagr_5y":              {"col": "u.eps_cagr_5y",              "scale": 0.01, "type": "number", "label": "EPS CAGR 5Y %",            "unit": "%",   "cat": "Growth"},
    "revenue_growth_yoy_q":     {"col": "u.revenue_growth_yoy_q",     "scale": 0.01, "type": "number", "label": "Revenue Growth YoY Q %",   "unit": "%",   "cat": "Growth"},
    "eps_growth_yoy_q":         {"col": "u.eps_growth_yoy_q",         "scale": 0.01, "type": "number", "label": "EPS Growth YoY Q %",       "unit": "%",   "cat": "Growth"},
    "revenue_growth_hoh":       {"col": "u.revenue_growth_hoh",       "scale": 0.01, "type": "number", "label": "Revenue Growth HoH % ★",  "unit": "%",   "cat": "Growth"},
    "net_income_growth_hoh":    {"col": "u.net_income_growth_hoh",    "scale": 0.01, "type": "number", "label": "Net Income Growth HoH % ★","unit": "%",   "cat": "Growth"},
    "eps_growth_hoh":           {"col": "u.eps_growth_hoh",           "scale": 0.01, "type": "number", "label": "EPS Growth HoH % ★",      "unit": "%",   "cat": "Growth"},
    "net_income_growth_yoy_q":  {"col": "u.net_income_growth_yoy_q",  "scale": 0.01, "type": "number", "label": "Net Income Growth YoY Q %","unit": "%",   "cat": "Growth"},
    "ebitda_growth_1y":         {"col": "u.ebitda_growth_1y",         "scale": 0.01, "type": "number", "label": "EBITDA Growth 1Y %",        "unit": "%",   "cat": "Growth"},
    "fcf_growth_1y":            {"col": "u.fcf_growth_1y",            "scale": 0.01, "type": "number", "label": "FCF Growth 1Y %",           "unit": "%",   "cat": "Growth"},
    "eps_growth_1y":            {"col": "u.eps_growth_1y",            "scale": 0.01, "type": "number", "label": "EPS Growth 1Y %",           "unit": "%",   "cat": "Growth"},
    "revenue_cagr_7y":          {"col": "u.revenue_cagr_7y",          "scale": 0.01, "type": "number", "label": "Revenue CAGR 7Y %",         "unit": "%",   "cat": "Growth"},
    "revenue_cagr_10y":         {"col": "u.revenue_cagr_10y",         "scale": 0.01, "type": "number", "label": "Revenue CAGR 10Y %",        "unit": "%",   "cat": "Growth"},
    "net_income_cagr_5y":       {"col": "u.net_income_cagr_5y",       "scale": 0.01, "type": "number", "label": "Net Income CAGR 5Y %",      "unit": "%",   "cat": "Growth"},
    "ebitda_cagr_3y":           {"col": "u.ebitda_cagr_3y",           "scale": 0.01, "type": "number", "label": "EBITDA CAGR 3Y %",          "unit": "%",   "cat": "Growth"},
    "ebitda_cagr_5y":           {"col": "u.ebitda_cagr_5y",           "scale": 0.01, "type": "number", "label": "EBITDA CAGR 5Y %",          "unit": "%",   "cat": "Growth"},
    "fcf_cagr_3y":              {"col": "u.fcf_cagr_3y",              "scale": 0.01, "type": "number", "label": "FCF CAGR 3Y %",             "unit": "%",   "cat": "Growth"},
    "fcf_cagr_5y":              {"col": "u.fcf_cagr_5y",              "scale": 0.01, "type": "number", "label": "FCF CAGR 5Y %",             "unit": "%",   "cat": "Growth"},
    "bvps_cagr_3y":             {"col": "u.bvps_cagr_3y",             "scale": 0.01, "type": "number", "label": "BVPS CAGR 3Y %",            "unit": "%",   "cat": "Growth"},
    "bvps_cagr_5y":             {"col": "u.bvps_cagr_5y",             "scale": 0.01, "type": "number", "label": "BVPS CAGR 5Y %",            "unit": "%",   "cat": "Growth"},
    "momentum_3m":              {"col": "u.momentum_3m",              "scale": 0.01, "type": "number", "label": "Price Momentum 3M %",      "unit": "%",   "cat": "Technicals"},
    "momentum_6m":              {"col": "u.momentum_6m",              "scale": 0.01, "type": "number", "label": "Price Momentum 6M %",      "unit": "%",   "cat": "Technicals"},

    # ── Financial Health ──────────────────────────────────────────────────────
    "debt_to_equity":        {"col": "u.debt_to_equity",       "scale": 1,    "type": "number", "label": "Debt / Equity",               "unit": "x",    "cat": "Financial Strength"},
    "current_ratio":         {"col": "u.current_ratio",        "scale": 1,    "type": "number", "label": "Current Ratio",               "unit": "x",    "cat": "Financial Strength"},
    "quick_ratio":           {"col": "u.quick_ratio",          "scale": 1,    "type": "number", "label": "Quick Ratio",                 "unit": "x",    "cat": "Financial Strength"},  # TODO: add to screener.universe schema
    "interest_coverage":     {"col": "u.interest_coverage",    "scale": 1,    "type": "number", "label": "Interest Coverage",           "unit": "x",    "cat": "Financial Strength"},
    "debt_to_assets":        {"col": "u.debt_to_assets",       "scale": 1,    "type": "number", "label": "Debt / Assets",               "unit": "x",    "cat": "Financial Strength"},
    "lt_debt_to_capital":    {"col": "u.lt_debt_to_capital",   "scale": 1,    "type": "number", "label": "LT Debt / Capital",           "unit": "x",    "cat": "Financial Strength"},
    "net_debt":              {"col": "u.net_debt",             "scale": 1,    "type": "number", "label": "Net Debt (AUD M)",            "unit": "AUD M","cat": "Financial Health"},
    "total_debt":            {"col": "u.total_debt",           "scale": 1,    "type": "number", "label": "Total Debt (AUD M)",          "unit": "AUD M","cat": "Financial Health"},
    "debt_to_ebitda":        {"col": "u.debt_to_ebitda",       "scale": 1,    "type": "number", "label": "Debt / EBITDA",               "unit": "x",    "cat": "Financial Strength"},  # TODO: add to screener.universe schema
    "net_debt_to_ebitda":    {"col": "u.net_debt_to_ebitda",   "scale": 1,    "type": "number", "label": "Net Debt / EBITDA",           "unit": "x",    "cat": "Financial Strength"},
    "cash_conversion_cycle": {"col": "u.cash_conversion_cycle","scale": 1,    "type": "number", "label": "Cash Conversion Cycle (days)","unit": "days", "cat": "Financial Health"},  # TODO: add to screener.universe schema
    "fcf_fy0":               {"col": "u.fcf_fy0",              "scale": 1,    "type": "number", "label": "Free Cash Flow (AUD M)",      "unit": "AUD M","cat": "Financial Health"},
    "cfo_fy0":               {"col": "u.cfo_fy0",              "scale": 1,    "type": "number", "label": "Operating CF (AUD M)",        "unit": "AUD M","cat": "Financial Health"},
    "total_assets":          {"col": "u.total_assets",         "scale": 1,    "type": "number", "label": "Total Assets (AUD M)",        "unit": "AUD M","cat": "Financial Health"},
    "total_equity":          {"col": "u.total_equity",         "scale": 1,    "type": "number", "label": "Total Equity (AUD M)",        "unit": "AUD M","cat": "Financial Health"},
    "cash":                  {"col": "u.cash",                 "scale": 1,    "type": "number", "label": "Cash & Equivalents (AUD M)",  "unit": "AUD M","cat": "Financial Health"},
    "capital_employed":      {"col": "(u.total_equity + u.total_debt)", "scale": 1, "type": "number", "label": "Capital Employed (AUD M)",  "unit": "AUD M","cat": "Financial Health"},  # equity + total debt

    # ── Quality Scores ────────────────────────────────────────────────────────
    "piotroski_f_score":       {"col": "u.piotroski_f_score",        "scale": 1,    "type": "number", "label": "Piotroski F-Score",          "unit": "",    "cat": "Quality"},
    "altman_z_score":          {"col": "u.altman_z_score",           "scale": 1,    "type": "number", "label": "Altman Z-Score",             "unit": "",    "cat": "Quality"},   # TODO: compute in yearly_metrics
    "beneish_m_score":         {"col": "u.beneish_m_score",          "scale": 1,    "type": "number", "label": "Beneish M-Score",            "unit": "",    "cat": "Quality"},   # TODO: add to screener.universe schema
    "ocf_to_net_profit":       {"col": "u.ocf_to_net_profit",        "scale": 1,    "type": "number", "label": "CFO / Net Profit",           "unit": "x",   "cat": "Quality"},
    "fcf_payout_ratio":        {"col": "u.fcf_payout_ratio",         "scale": 0.01, "type": "number", "label": "FCF Payout Ratio %",         "unit": "%",   "cat": "Quality"},
    "eps_volatility_5y":       {"col": "u.eps_volatility_5y",        "scale": 1,    "type": "number", "label": "EPS Volatility 5Y",          "unit": "",    "cat": "Quality"},
    "fcf_positive_years":      {"col": "u.fcf_positive_years",       "scale": 1,    "type": "number", "label": "FCF +ve Years (0-5)",        "unit": "",    "cat": "Quality"},
    "earnings_stability_score":{"col": "u.earnings_stability_score", "scale": 1,    "type": "number", "label": "Earnings Stability Score",   "unit": "",    "cat": "Quality"},
    "percent_insiders":        {"col": "u.percent_insiders",         "scale": 1,    "type": "number", "label": "Insider Ownership %",        "unit": "%",   "cat": "Quality"},
    "percent_institutions":    {"col": "u.percent_institutions",     "scale": 1,    "type": "number", "label": "Institutional Ownership %",  "unit": "%",   "cat": "Quality"},
    "short_pct":               {"col": "u.short_pct",                "scale": 1,    "type": "number", "label": "Short Interest %",           "unit": "%",   "cat": "Quality"},   # TODO: populate short_positions from ASIC
    "short_interest_chg_1w":   {"col": "u.short_interest_chg_1w",   "scale": 1,    "type": "number", "label": "Short Interest Change 1W",   "unit": "%",   "cat": "Quality"},   # TODO: populate short_positions from ASIC
    "shares_dilution_3y":      {"col": "u.shares_dilution_3y",       "scale": 0.01, "type": "number", "label": "Share Dilution 3Y %",        "unit": "%",   "cat": "Quality"},   # TODO: compute in yearly_metrics
    "analyst_count":           {"col": "u.analyst_count",            "scale": 1,    "type": "number", "label": "Analyst Count",              "unit": "",    "cat": "Quality"},   # TODO: populate analyst_ratings
    "analyst_buy_pct":         {"col": "u.analyst_buy_pct",          "scale": 1,    "type": "number", "label": "Analyst Buy %",              "unit": "%",   "cat": "Quality"},   # TODO: populate analyst_ratings
    "analyst_consensus_score": {"col": "u.analyst_consensus_score",  "scale": 1,    "type": "number", "label": "Analyst Consensus Score",    "unit": "",    "cat": "Quality"},   # TODO: populate analyst_ratings

    # ── Quality / Rolling Averages ────────────────────────────────────────────
    "avg_roe_5y":              {"col": "u.avg_roe_5y",              "scale": 0.01, "type": "number", "label": "Avg ROE 5Y %",              "unit": "%",   "cat": "Quality"},
    "avg_roa_3y":              {"col": "u.avg_roa_3y",              "scale": 0.01, "type": "number", "label": "Avg ROA 3Y %",              "unit": "%",   "cat": "Quality"},
    "avg_roa_5y":              {"col": "u.avg_roa_5y",              "scale": 0.01, "type": "number", "label": "Avg ROA 5Y %",              "unit": "%",   "cat": "Quality"},
    "avg_roce_3y":             {"col": "u.avg_roce_3y",             "scale": 0.01, "type": "number", "label": "Avg ROCE 3Y %",             "unit": "%",   "cat": "Quality"},
    "avg_roce_5y":             {"col": "u.avg_roce_5y",             "scale": 0.01, "type": "number", "label": "Avg ROCE 5Y %",             "unit": "%",   "cat": "Quality"},
    "avg_gross_margin_3y":     {"col": "u.avg_gross_margin_3y",     "scale": 0.01, "type": "number", "label": "Avg Gross Margin 3Y %",     "unit": "%",   "cat": "Quality"},
    "avg_gross_margin_5y":     {"col": "u.avg_gross_margin_5y",     "scale": 0.01, "type": "number", "label": "Avg Gross Margin 5Y %",     "unit": "%",   "cat": "Quality"},
    "avg_ebitda_margin_3y":    {"col": "u.avg_ebitda_margin_3y",    "scale": 0.01, "type": "number", "label": "Avg EBITDA Margin 3Y %",    "unit": "%",   "cat": "Quality"},
    "avg_ebitda_margin_5y":    {"col": "u.avg_ebitda_margin_5y",    "scale": 0.01, "type": "number", "label": "Avg EBITDA Margin 5Y %",    "unit": "%",   "cat": "Quality"},
    "avg_operating_margin_3y": {"col": "u.avg_operating_margin_3y", "scale": 0.01, "type": "number", "label": "Avg Op Margin 3Y %",        "unit": "%",   "cat": "Quality"},
    "avg_operating_margin_5y": {"col": "u.avg_operating_margin_5y", "scale": 0.01, "type": "number", "label": "Avg Op Margin 5Y %",        "unit": "%",   "cat": "Quality"},
    "avg_net_margin_3y":       {"col": "u.avg_net_margin_3y",       "scale": 0.01, "type": "number", "label": "Avg Net Margin 3Y %",       "unit": "%",   "cat": "Quality"},
    "avg_net_margin_5y":       {"col": "u.avg_net_margin_5y",       "scale": 0.01, "type": "number", "label": "Avg Net Margin 5Y %",       "unit": "%",   "cat": "Quality"},
    "avg_eps_growth_3y":       {"col": "u.avg_eps_growth_3y",       "scale": 0.01, "type": "number", "label": "Avg EPS Growth 3Y %",       "unit": "%",   "cat": "Quality"},
    "avg_eps_growth_5y":       {"col": "u.avg_eps_growth_5y",       "scale": 0.01, "type": "number", "label": "Avg EPS Growth 5Y %",       "unit": "%",   "cat": "Quality"},

    # ── Technicals ────────────────────────────────────────────────────────────
    "rsi_14":              {"col": "u.rsi_14",        "scale": 1,    "type": "number",  "label": "RSI (14)",                "unit": "",    "cat": "Technicals"},
    "adx_14":              {"col": "u.adx_14",        "scale": 1,    "type": "number",  "label": "ADX (14)",                "unit": "",    "cat": "Technicals"},
    "macd":                {"col": "u.macd",          "scale": 1,    "type": "number",  "label": "MACD Line",               "unit": "",    "cat": "Technicals"},
    "sma_20":              {"col": "u.sma_20",        "scale": 1,    "type": "number",  "label": "SMA 20",                  "unit": "AUD", "cat": "Technicals"},
    "sma_50":              {"col": "u.sma_50",        "scale": 1,    "type": "number",  "label": "SMA 50",                  "unit": "AUD", "cat": "Technicals"},
    "sma_200":             {"col": "u.sma_200",       "scale": 1,    "type": "number",  "label": "SMA 200",                 "unit": "AUD", "cat": "Technicals"},
    "ema_20":              {"col": "u.ema_20",        "scale": 1,    "type": "number",  "label": "EMA 20",                  "unit": "AUD", "cat": "Technicals"},
    "above_sma20":         {"col": "(u.price > u.sma_20 AND u.sma_20 IS NOT NULL)",   "scale": 1, "type": "boolean", "label": "Above SMA 20",  "unit": "", "cat": "Technicals"},
    "above_sma50":         {"col": "(u.price > u.sma_50 AND u.sma_50 IS NOT NULL)",   "scale": 1, "type": "boolean", "label": "Above SMA 50",  "unit": "", "cat": "Technicals"},
    "above_sma200":        {"col": "(u.price > u.sma_200 AND u.sma_200 IS NOT NULL)", "scale": 1, "type": "boolean", "label": "Above SMA 200", "unit": "", "cat": "Technicals"},
    "golden_cross":        {"col": "(u.sma_50 > u.sma_200 AND u.sma_50 IS NOT NULL AND u.sma_200 IS NOT NULL)", "scale": 1, "type": "boolean", "label": "Golden Cross (SMA50 > SMA200)", "unit": "", "cat": "Technicals"},
    "death_cross":         {"col": "(u.sma_50 < u.sma_200 AND u.sma_50 IS NOT NULL AND u.sma_200 IS NOT NULL)", "scale": 1, "type": "boolean", "label": "Death Cross (SMA50 < SMA200)",  "unit": "", "cat": "Technicals"},
    "bb_pct":              {"col": "((u.price - u.bb_lower) / NULLIF(u.bb_upper - u.bb_lower, 0) * 100)", "scale": 1, "type": "number", "label": "BB %B (position in band)", "unit": "%", "cat": "Technicals"},
    "bb_width":            {"col": "((u.bb_upper - u.bb_lower) / NULLIF(u.sma_20, 0) * 100)",             "scale": 1, "type": "number", "label": "BB Width %",               "unit": "%", "cat": "Technicals"},
    "volatility_20d":      {"col": "u.volatility_20d","scale": 0.01, "type": "number",  "label": "Volatility 20D %",        "unit": "%",   "cat": "Technicals"},
    "volatility_60d":      {"col": "u.volatility_60d","scale": 0.01, "type": "number",  "label": "Volatility 60D %",        "unit": "%",   "cat": "Technicals"},
    "beta_1y":             {"col": "u.beta_1y",       "scale": 1,    "type": "number",  "label": "Beta (1Y)",               "unit": "",    "cat": "Technicals"},  # TODO: compute in yearly_metrics
    "beta_3y":             {"col": "u.beta_3y",       "scale": 1,    "type": "number",  "label": "Beta (3Y)",               "unit": "",    "cat": "Technicals"},  # TODO: add to screener.universe schema
    "sharpe_1y":           {"col": "u.sharpe_1y",     "scale": 1,    "type": "number",  "label": "Sharpe Ratio (1Y)",       "unit": "",    "cat": "Technicals"},
    "sharpe_3y":           {"col": "u.sharpe_3y",     "scale": 1,    "type": "number",  "label": "Sharpe Ratio (3Y)",       "unit": "",    "cat": "Technicals"},  # TODO: add to screener.universe schema
    "sortino_1y":          {"col": "u.sortino_1y",    "scale": 1,    "type": "number",  "label": "Sortino Ratio (1Y)",      "unit": "",    "cat": "Technicals"},  # TODO: add to screener.universe schema
    "max_drawdown_1y":     {"col": "u.max_drawdown_1y","scale": 0.01,"type": "number",  "label": "Max Drawdown 1Y %",       "unit": "%",   "cat": "Technicals"},  # TODO: add to screener.universe schema
    "relative_strength_xjo":{"col": "u.relative_strength_xjo","scale": 0.01,"type": "number", "label": "Relative Strength vs XJO %","unit": "%", "cat": "Technicals"},  # TODO: add to screener.universe schema
    "drawdown_from_ath":   {"col": "u.drawdown_from_ath","scale": 0.01,"type": "number", "label": "Drawdown from ATH %",    "unit": "%",   "cat": "Technicals"},

    # ── Price Returns ─────────────────────────────────────────────────────────
    "return_1w":   {"col": "u.return_1w",   "scale": 0.01, "type": "number", "label": "Return 1W %",   "unit": "%", "cat": "Returns"},
    "return_1m":   {"col": "u.return_1m",   "scale": 0.01, "type": "number", "label": "Return 1M %",   "unit": "%", "cat": "Returns"},
    "return_3m":   {"col": "u.return_3m",   "scale": 0.01, "type": "number", "label": "Return 3M %",   "unit": "%", "cat": "Returns"},
    "return_6m":   {"col": "u.return_6m",   "scale": 0.01, "type": "number", "label": "Return 6M %",   "unit": "%", "cat": "Returns"},
    "return_1y":   {"col": "u.return_1y",   "scale": 0.01, "type": "number", "label": "Return 1Y %",   "unit": "%", "cat": "Returns"},
    "return_ytd":  {"col": "u.return_ytd",  "scale": 0.01, "type": "number", "label": "Return YTD %",  "unit": "%", "cat": "Returns"},
    "return_3y":   {"col": "u.return_3y",   "scale": 0.01, "type": "number", "label": "Return 3Y %",   "unit": "%", "cat": "Returns"},
    "return_5y":   {"col": "u.return_5y",   "scale": 0.01, "type": "number", "label": "Return 5Y %",   "unit": "%", "cat": "Returns"},
    "return_7y":   {"col": "u.return_7y",   "scale": 0.01, "type": "number", "label": "Return 7Y %",   "unit": "%", "cat": "Returns"},
    "return_10y":  {"col": "u.return_10y",  "scale": 0.01, "type": "number", "label": "Return 10Y %",  "unit": "%", "cat": "Returns"},
    "return_15y":  {"col": "u.return_15y",  "scale": 0.01, "type": "number", "label": "Return 15Y %",  "unit": "%", "cat": "Returns"},

    # ── Tier 2: Technical signals & ratios ───────────────────────────────────
    "dma50_ratio":       {"col": "u.dma50_ratio",       "scale": 1,    "type": "number", "label": "Price / SMA50",          "unit": "x",   "cat": "Technicals"},
    "dma200_ratio":      {"col": "u.dma200_ratio",      "scale": 1,    "type": "number", "label": "Price / SMA200",         "unit": "x",   "cat": "Technicals"},
    "relative_volume":   {"col": "u.relative_volume",   "scale": 1,    "type": "number", "label": "Relative Volume",        "unit": "x",   "cat": "Technicals"},
    "bb_pct":            {"col": "u.bb_pct",            "scale": 1,    "type": "number", "label": "Bollinger %B",           "unit": "",    "cat": "Technicals"},
    "rsi_21":            {"col": "u.rsi_21",            "scale": 1,    "type": "number", "label": "RSI 21",                 "unit": "",    "cat": "Technicals"},
    "stoch_k":           {"col": "u.stoch_k",           "scale": 1,    "type": "number", "label": "Stochastic %K",         "unit": "",    "cat": "Technicals"},
    "stoch_d":           {"col": "u.stoch_d",           "scale": 1,    "type": "number", "label": "Stochastic %D",         "unit": "",    "cat": "Technicals"},
    "above_sma50":       {"col": "u.above_sma50",       "scale": 1,    "type": "boolean","label": "Above SMA50",           "unit": "",    "cat": "Technicals"},
    "above_sma200":      {"col": "u.above_sma200",      "scale": 1,    "type": "boolean","label": "Above SMA200",          "unit": "",    "cat": "Technicals"},
    "golden_cross":      {"col": "u.golden_cross",      "scale": 1,    "type": "boolean","label": "Golden Cross",          "unit": "",    "cat": "Technicals"},
    "death_cross":       {"col": "u.death_cross",       "scale": 1,    "type": "boolean","label": "Death Cross",           "unit": "",    "cat": "Technicals"},
    "new_52w_high":      {"col": "u.new_52w_high",      "scale": 1,    "type": "boolean","label": "New 52W High",          "unit": "",    "cat": "Technicals"},
    "new_52w_low":       {"col": "u.new_52w_low",       "scale": 1,    "type": "boolean","label": "New 52W Low",           "unit": "",    "cat": "Technicals"},
    "rsi_overbought":    {"col": "u.rsi_overbought",    "scale": 1,    "type": "boolean","label": "RSI Overbought (≥70)",  "unit": "",    "cat": "Technicals"},
    "rsi_oversold":      {"col": "u.rsi_oversold",      "scale": 1,    "type": "boolean","label": "RSI Oversold (≤30)",   "unit": "",    "cat": "Technicals"},
    "macd_bullish_cross":{"col": "u.macd_bullish_cross","scale": 1,    "type": "boolean","label": "MACD Bullish Cross",   "unit": "",    "cat": "Technicals"},
    "macd_bearish_cross":{"col": "u.macd_bearish_cross","scale": 1,    "type": "boolean","label": "MACD Bearish Cross",   "unit": "",    "cat": "Technicals"},

    # ── Tier 3: Inline calculations ───────────────────────────────────────────
    "price_to_52w_high":  {"col": "u.price_to_52w_high",  "scale": 1, "type": "number", "label": "Price / 52W High",       "unit": "x",    "cat": "Market Data"},
    "price_to_52w_low":   {"col": "u.price_to_52w_low",   "scale": 1, "type": "number", "label": "Price / 52W Low",        "unit": "x",    "cat": "Market Data"},
    "fcf_per_share":      {"col": "u.fcf_per_share",      "scale": 1, "type": "number", "label": "FCF per Share (AUD)",    "unit": "AUD",  "cat": "Financial Strength"},
    "ocf_per_share":      {"col": "u.ocf_per_share",      "scale": 1, "type": "number", "label": "OCF per Share (AUD)",    "unit": "AUD",  "cat": "Financial Strength"},
    "revenue_per_share":  {"col": "u.revenue_per_share",  "scale": 1, "type": "number", "label": "Revenue per Share (AUD)","unit": "AUD",  "cat": "Financial Strength"},
    "working_capital":    {"col": "u.working_capital",    "scale": 1, "type": "number", "label": "Working Capital (AUD M)","unit": "AUD M","cat": "Financial Strength"},

    # ── ASX REIT-Specific ★ ───────────────────────────────────────────────────
    # (★ = ASX-unique field not common on US screeners)
    "nta_per_share":            {"col": "u.nta_per_share",            "scale": 1,    "type": "number", "label": "NTA per Share (AUD) ★",       "unit": "AUD",  "cat": "REIT"},   # TODO: add to screener.universe schema
    "nta_discount_premium":     {"col": "u.nta_discount_premium",     "scale": 0.01, "type": "number", "label": "NTA Discount/Premium % ★",    "unit": "%",    "cat": "REIT"},   # TODO: add to screener.universe schema
    "gearing_ratio":            {"col": "u.gearing_ratio",            "scale": 0.01, "type": "number", "label": "Gearing Ratio % ★",           "unit": "%",    "cat": "REIT"},   # TODO: add to screener.universe schema
    "wale_years":               {"col": "u.wale_years",               "scale": 1,    "type": "number", "label": "WALE (years) ★",              "unit": "yrs",  "cat": "REIT"},   # TODO: add to screener.universe schema
    "management_expense_ratio": {"col": "u.management_expense_ratio", "scale": 0.01, "type": "number", "label": "MER % ★",                     "unit": "%",    "cat": "REIT"},   # TODO: add to screener.universe schema

    # ── ASX Mining-Specific ★ ─────────────────────────────────────────────────
    "aisc_per_oz":              {"col": "u.aisc_per_oz",              "scale": 1,    "type": "number", "label": "AISC per oz (USD) ★",         "unit": "USD",  "cat": "Mining"}, # TODO: add to screener.universe schema

    # ── Quick-win fields ─────────────────────────────────────────────────────────
    "revenue_fy2": {"col": "u.revenue_fy2", "scale": 1, "type": "number", "label": "Sales (2Y ago) (AUD M)", "unit": "AUD M", "cat": "Income Statement"},
    "price_to_cash_flow": {"col": "u.price_to_cash_flow", "scale": 1, "type": "number", "label": "Price / Cash Flow", "unit": "x", "cat": "Valuation"},

    # ── Derived ratios (Tier B) ─────────────────────────────────────────────────
    "cash_ratio": {"col": "u.cash_ratio", "scale": 1, "type": "number", "label": "Cash Ratio", "unit": "x", "cat": "Financial Strength"},
    "days_sales_outstanding": {"col": "u.days_sales_outstanding", "scale": 1, "type": "number", "label": "Days Sales Outstanding", "unit": "days", "cat": "Profitability"},
    "days_inventory_outstanding": {"col": "u.days_inventory_outstanding", "scale": 1, "type": "number", "label": "Days Inventory Outstanding", "unit": "days", "cat": "Profitability"},
    "receivables_turnover": {"col": "u.receivables_turnover", "scale": 1, "type": "number", "label": "Receivables Turnover", "unit": "x", "cat": "Profitability"},
    "pretax_margin": {"col": "u.pretax_margin", "scale": 0.01, "type": "number", "label": "Pre-tax Margin %", "unit": "%", "cat": "Profitability"},
    "nopat": {"col": "u.nopat", "scale": 1, "type": "number", "label": "NOPAT (AUD M)", "unit": "AUD M", "cat": "Profitability"},
    "ebitda_interest_coverage": {"col": "u.ebitda_interest_coverage", "scale": 1, "type": "number", "label": "EBITDA Interest Coverage", "unit": "x", "cat": "Financial Strength"},
    "equity_ratio": {"col": "u.equity_ratio", "scale": 0.01, "type": "number", "label": "Equity Ratio %", "unit": "%", "cat": "Financial Strength"},
    "liabilities_to_assets": {"col": "u.liabilities_to_assets", "scale": 0.01, "type": "number", "label": "Liabilities / Assets %", "unit": "%", "cat": "Financial Strength"},
    "fixed_asset_turnover": {"col": "u.fixed_asset_turnover", "scale": 1, "type": "number", "label": "Fixed Asset Turnover", "unit": "x", "cat": "Profitability"},
    "capex_to_revenue": {"col": "u.capex_to_revenue", "scale": 0.01, "type": "number", "label": "Capex / Revenue %", "unit": "%", "cat": "Profitability"},
    "tangible_book_value_per_share": {"col": "u.tangible_book_value_per_share", "scale": 1, "type": "number", "label": "Tangible Book Value per Share (AUD)", "unit": "AUD", "cat": "Financial Strength"},
    "cash_per_share": {"col": "u.cash_per_share", "scale": 1, "type": "number", "label": "Cash per Share (AUD)", "unit": "AUD", "cat": "Financial Strength"},

    # ── Line items (income statement / balance sheet / cash flow, AUD M) ─────────
    "cogs": {"col": "u.cogs", "scale": 1, "type": "number", "label": "Cost of Goods Sold (AUD M)", "unit": "AUD M", "cat": "Income Statement"},
    "ebit": {"col": "u.ebit", "scale": 1, "type": "number", "label": "EBIT / Operating Profit (AUD M)", "unit": "AUD M", "cat": "Income Statement"},
    "income_tax_expense": {"col": "u.income_tax_expense", "scale": 1, "type": "number", "label": "Income Tax Expense (AUD M)", "unit": "AUD M", "cat": "Income Statement"},
    "interest_expense": {"col": "u.interest_expense", "scale": 1, "type": "number", "label": "Interest Expense (AUD M)", "unit": "AUD M", "cat": "Income Statement"},
    "depreciation": {"col": "u.depreciation", "scale": 1, "type": "number", "label": "Depreciation & Amortisation (AUD M)", "unit": "AUD M", "cat": "Income Statement"},
    "trade_receivables": {"col": "u.trade_receivables", "scale": 1, "type": "number", "label": "Trade Receivables (AUD M)", "unit": "AUD M", "cat": "Balance Sheet"},
    "inventory": {"col": "u.inventory", "scale": 1, "type": "number", "label": "Inventory (AUD M)", "unit": "AUD M", "cat": "Balance Sheet"},
    "goodwill": {"col": "u.goodwill", "scale": 1, "type": "number", "label": "Goodwill (AUD M)", "unit": "AUD M", "cat": "Balance Sheet"},
    "intangibles": {"col": "u.intangibles", "scale": 1, "type": "number", "label": "Intangible Assets (AUD M)", "unit": "AUD M", "cat": "Balance Sheet"},
    "ppe_net": {"col": "u.ppe_net", "scale": 1, "type": "number", "label": "PP&E Net / Fixed Assets (AUD M)", "unit": "AUD M", "cat": "Balance Sheet"},
    "total_current_assets": {"col": "u.total_current_assets", "scale": 1, "type": "number", "label": "Current Assets (AUD M)", "unit": "AUD M", "cat": "Balance Sheet"},
    "total_current_liabilities": {"col": "u.total_current_liabilities", "scale": 1, "type": "number", "label": "Current Liabilities (AUD M)", "unit": "AUD M", "cat": "Balance Sheet"},
    "total_liabilities": {"col": "u.total_liabilities", "scale": 1, "type": "number", "label": "Total Liabilities (AUD M)", "unit": "AUD M", "cat": "Balance Sheet"},
    "long_term_debt": {"col": "u.long_term_debt", "scale": 1, "type": "number", "label": "Long-term Debt (AUD M)", "unit": "AUD M", "cat": "Balance Sheet"},
    "retained_earnings": {"col": "u.retained_earnings", "scale": 1, "type": "number", "label": "Retained Earnings (AUD M)", "unit": "AUD M", "cat": "Balance Sheet"},
    "cfi": {"col": "u.cfi", "scale": 1, "type": "number", "label": "Investing Cash Flow (AUD M)", "unit": "AUD M", "cat": "Cash Flow"},
    "dividends_paid": {"col": "u.dividends_paid", "scale": 1, "type": "number", "label": "Dividends Paid (AUD M)", "unit": "AUD M", "cat": "Cash Flow"},

    # ── Profit growth (PBT) & sales growth prior year ────────────────────────────
    "sales_growth_prev_y": {"col": "u.sales_growth_prev_y", "scale": 0.01, "type": "number", "label": "Sales Growth (last yr) %", "unit": "%", "cat": "Growth"},
    "pbt_growth_1y": {"col": "u.pbt_growth_1y", "scale": 0.01, "type": "number", "label": "Pre-tax Profit Growth %", "unit": "%", "cat": "Growth"},
    "pbt_growth_prev_y": {"col": "u.pbt_growth_prev_y", "scale": 0.01, "type": "number", "label": "Pre-tax Profit Growth (last yr) %", "unit": "%", "cat": "Growth"},
    "pbt_cagr_3y": {"col": "u.pbt_cagr_3y", "scale": 0.01, "type": "number", "label": "Pre-tax Profit CAGR 3Y %", "unit": "%", "cat": "Growth"},
    "pbt_cagr_5y": {"col": "u.pbt_cagr_5y", "scale": 0.01, "type": "number", "label": "Pre-tax Profit CAGR 5Y %", "unit": "%", "cat": "Growth"},
    "pbt_cagr_7y": {"col": "u.pbt_cagr_7y", "scale": 0.01, "type": "number", "label": "Pre-tax Profit CAGR 7Y %", "unit": "%", "cat": "Growth"},
    "pbt_cagr_10y": {"col": "u.pbt_cagr_10y", "scale": 0.01, "type": "number", "label": "Pre-tax Profit CAGR 10Y %", "unit": "%", "cat": "Growth"},

    # ── Income Statement history (annual levels, AUD M) ──────────────────────────
    "revenue_fy0": {"col": "u.revenue_fy0", "scale": 1, "type": "number", "label": "Sales (FY0) (AUD M)", "unit": "AUD M", "cat": "Income Statement"},
    "revenue_fy1": {"col": "u.revenue_fy1", "scale": 1, "type": "number", "label": "Sales (last yr) (AUD M)", "unit": "AUD M", "cat": "Income Statement"},
    "revenue_fy3": {"col": "u.revenue_fy3", "scale": 1, "type": "number", "label": "Sales (3Y ago) (AUD M)", "unit": "AUD M", "cat": "Income Statement"},
    "revenue_fy5": {"col": "u.revenue_fy5", "scale": 1, "type": "number", "label": "Sales (5Y ago) (AUD M)", "unit": "AUD M", "cat": "Income Statement"},
    "revenue_fy7": {"col": "u.revenue_fy7", "scale": 1, "type": "number", "label": "Sales (7Y ago) (AUD M)", "unit": "AUD M", "cat": "Income Statement"},
    "revenue_fy10": {"col": "u.revenue_fy10", "scale": 1, "type": "number", "label": "Sales (10Y ago) (AUD M)", "unit": "AUD M", "cat": "Income Statement"},
    "gross_profit_fy0": {"col": "u.gross_profit_fy0", "scale": 1, "type": "number", "label": "Gross Profit (FY0) (AUD M)", "unit": "AUD M", "cat": "Income Statement"},
    "gross_profit_fy1": {"col": "u.gross_profit_fy1", "scale": 1, "type": "number", "label": "Gross Profit (last yr) (AUD M)", "unit": "AUD M", "cat": "Income Statement"},
    "gross_profit_fy3": {"col": "u.gross_profit_fy3", "scale": 1, "type": "number", "label": "Gross Profit (3Y ago) (AUD M)", "unit": "AUD M", "cat": "Income Statement"},
    "gross_profit_fy5": {"col": "u.gross_profit_fy5", "scale": 1, "type": "number", "label": "Gross Profit (5Y ago) (AUD M)", "unit": "AUD M", "cat": "Income Statement"},
    "gross_profit_fy7": {"col": "u.gross_profit_fy7", "scale": 1, "type": "number", "label": "Gross Profit (7Y ago) (AUD M)", "unit": "AUD M", "cat": "Income Statement"},
    "gross_profit_fy10": {"col": "u.gross_profit_fy10", "scale": 1, "type": "number", "label": "Gross Profit (10Y ago) (AUD M)", "unit": "AUD M", "cat": "Income Statement"},
    "pbt_fy0": {"col": "u.pbt_fy0", "scale": 1, "type": "number", "label": "Pre-tax Profit (FY0) (AUD M)", "unit": "AUD M", "cat": "Income Statement"},
    "pbt_fy1": {"col": "u.pbt_fy1", "scale": 1, "type": "number", "label": "Pre-tax Profit (last yr) (AUD M)", "unit": "AUD M", "cat": "Income Statement"},
    "pbt_fy3": {"col": "u.pbt_fy3", "scale": 1, "type": "number", "label": "Pre-tax Profit (3Y ago) (AUD M)", "unit": "AUD M", "cat": "Income Statement"},
    "pbt_fy5": {"col": "u.pbt_fy5", "scale": 1, "type": "number", "label": "Pre-tax Profit (5Y ago) (AUD M)", "unit": "AUD M", "cat": "Income Statement"},
    "pbt_fy7": {"col": "u.pbt_fy7", "scale": 1, "type": "number", "label": "Pre-tax Profit (7Y ago) (AUD M)", "unit": "AUD M", "cat": "Income Statement"},
    "pbt_fy10": {"col": "u.pbt_fy10", "scale": 1, "type": "number", "label": "Pre-tax Profit (10Y ago) (AUD M)", "unit": "AUD M", "cat": "Income Statement"},
    "net_profit_fy0": {"col": "u.net_profit_fy0", "scale": 1, "type": "number", "label": "Net Profit (FY0) (AUD M)", "unit": "AUD M", "cat": "Income Statement"},
    "net_profit_fy1": {"col": "u.net_profit_fy1", "scale": 1, "type": "number", "label": "Net Profit (last yr) (AUD M)", "unit": "AUD M", "cat": "Income Statement"},
    "net_profit_fy3": {"col": "u.net_profit_fy3", "scale": 1, "type": "number", "label": "Net Profit (3Y ago) (AUD M)", "unit": "AUD M", "cat": "Income Statement"},
    "net_profit_fy5": {"col": "u.net_profit_fy5", "scale": 1, "type": "number", "label": "Net Profit (5Y ago) (AUD M)", "unit": "AUD M", "cat": "Income Statement"},
    "net_profit_fy7": {"col": "u.net_profit_fy7", "scale": 1, "type": "number", "label": "Net Profit (7Y ago) (AUD M)", "unit": "AUD M", "cat": "Income Statement"},
    "net_profit_fy10": {"col": "u.net_profit_fy10", "scale": 1, "type": "number", "label": "Net Profit (10Y ago) (AUD M)", "unit": "AUD M", "cat": "Income Statement"},
}

# ── Category display order ────────────────────────────────────────────────────
# Controls the order in which category groups appear in the filter-builder
# dropdown on the frontend.  Categories not listed here sort alphabetically
# at the end.

CATEGORY_ORDER: list[str] = [
    "Market Data",        # Sector, index membership, price, market cap, volume
    "Valuation",          # P/E, P/B, EV/EBITDA, FCF yield, …
    "Profitability",      # Margins, ROE, ROA, ROCE, EPS
    "Quality",            # Avg ROE/ROA/ROCE 3Y & 5Y, Piotroski, Altman, …
    "Growth",             # Revenue / EPS / EBITDA growth rates (1Y, 3Y CAGR, …)
    "Financial Strength", # Debt ratios, liquidity, cash flow, net income
    "Dividends",          # Yield, grossed-up yield, franking, payout, CAGR
    "Returns",            # Price returns over various time horizons
    "Technicals",         # RSI, MACD, SMA, momentum, volatility, beta
    "REIT",               # NTA, gearing, WALE, MER
    "Mining",             # AISC
]


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
# Note: expression-based fields (above_sma*, golden_cross, bb_pct, bb_width, etc.)
# and TODO schema columns are excluded — unknown sort_by falls back to market_cap.
SORTABLE_COLS: dict[str, str] = {
    # Identity
    "asx_code":           "u.asx_code",
    "company_name":       "u.company_name",
    # Price
    "price":              "u.price",
    "market_cap":         "u.market_cap",
    "enterprise_value":   "u.ev",
    "volume":             "u.volume",
    "avg_volume_20d":     "u.avg_volume_20d",
    "dollar_volume_avg_20d": "u.dollar_volume_avg_20d",
    "shares_outstanding": "u.shares_outstanding",
    "high_52w":           "u.high_52w",
    "low_52w":            "u.low_52w",
    # Valuation
    "pe_ratio":           "u.pe_ratio",
    "forward_pe":         "u.forward_pe",
    "peg_ratio":          "u.peg_ratio",
    "price_to_book":      "u.price_to_book",
    "price_to_sales":     "u.price_to_sales",
    "price_to_fcf":       "u.price_to_fcf",
    "ev_to_ebitda":       "u.ev_to_ebitda",
    "ev_to_revenue":      "u.ev_to_revenue",
    "ev_to_ebit":         "u.ev_to_ebit",
    "graham_number":      "u.graham_number",
    "fcf_yield":          "u.fcf_yield",
    # Dividends
    "dividend_yield":     "u.dividend_yield",
    "grossed_up_yield":   "u.grossed_up_yield",
    "franking_pct":       "u.franking_pct",
    "payout_ratio":       "u.payout_ratio",
    "dps":                "u.dps_ttm",
    "dividend_cagr_3y":   "u.dividend_cagr_3y",
    "dividend_consecutive_yrs": "u.dividend_consecutive_yrs",
    # Profitability
    "gross_margin":       "u.gross_margin",
    "ebitda_margin":      "u.ebitda_margin",
    "net_margin":         "u.net_margin",
    "operating_margin":   "u.operating_margin",
    "roe":                "u.roe",
    "roa":                "u.roa",
    "roce":               "u.roce",
    "avg_roe_3y":         "u.avg_roe_3y",
    "avg_roic_3y":        "u.avg_roic_3y",
    "avg_roic_5y":        "u.avg_roic_5y",
    "capital_efficiency_score": "u.capital_efficiency_score",
    "ocf_margin":         "u.ocf_margin",
    "fcf_margin":         "u.fcf_margin",
    "capex_intensity":    "u.capex_intensity",
    # Per-Share
    "eps":                "u.eps_fy0",
    "eps_fy0":            "u.eps_fy0",
    "eps_fy1":            "u.eps_fy1",
    "book_value_per_share":"u.book_value_per_share",
    # Growth
    "revenue":            "u.revenue_ttm",
    "net_income":         "u.net_profit_fy0",
    "revenue_growth_1y":  "u.revenue_growth_1y",
    "revenue_growth_3y_cagr": "u.revenue_growth_3y_cagr",
    "revenue_cagr_5y":    "u.revenue_cagr_5y",
    "earnings_growth_1y": "u.earnings_growth_1y",
    "earnings_growth_3y_cagr": "u.earnings_growth_3y_cagr",
    "eps_growth_3y_cagr": "u.eps_growth_3y_cagr",
    "eps_cagr_5y":        "u.eps_cagr_5y",
    "revenue_growth_yoy_q": "u.revenue_growth_yoy_q",
    "eps_growth_yoy_q":   "u.eps_growth_yoy_q",
    "revenue_growth_hoh": "u.revenue_growth_hoh",
    "net_income_growth_hoh": "u.net_income_growth_hoh",
    "eps_growth_hoh":     "u.eps_growth_hoh",
    "net_income_growth_yoy_q": "u.net_income_growth_yoy_q",
    "ebitda_growth_1y":   "u.ebitda_growth_1y",
    "fcf_growth_1y":      "u.fcf_growth_1y",
    "eps_growth_1y":      "u.eps_growth_1y",
    "revenue_cagr_7y":    "u.revenue_cagr_7y",
    "revenue_cagr_10y":   "u.revenue_cagr_10y",
    "net_income_cagr_5y": "u.net_income_cagr_5y",
    "ebitda_cagr_3y":     "u.ebitda_cagr_3y",
    "ebitda_cagr_5y":     "u.ebitda_cagr_5y",
    "fcf_cagr_3y":        "u.fcf_cagr_3y",
    "fcf_cagr_5y":        "u.fcf_cagr_5y",
    "dividend_cagr_5y":   "u.dividend_cagr_5y",
    "bvps_cagr_3y":       "u.bvps_cagr_3y",
    "bvps_cagr_5y":       "u.bvps_cagr_5y",
    "momentum_3m":        "u.momentum_3m",
    "momentum_6m":        "u.momentum_6m",
    # Financial Health
    "debt_to_equity":     "u.debt_to_equity",
    "current_ratio":      "u.current_ratio",
    "debt_to_assets":     "u.debt_to_assets",
    "lt_debt_to_capital": "u.lt_debt_to_capital",
    "net_debt":           "u.net_debt",
    "total_debt":         "u.total_debt",
    "fcf_fy0":            "u.fcf_fy0",
    "cfo_fy0":            "u.cfo_fy0",
    # Tier 3 inline calculations
    "price_to_52w_high":  "u.price_to_52w_high",
    "price_to_52w_low":   "u.price_to_52w_low",
    "fcf_per_share":      "u.fcf_per_share",
    "ocf_per_share":      "u.ocf_per_share",
    "revenue_per_share":  "u.revenue_per_share",
    "working_capital":    "u.working_capital",
    # Quality
    "piotroski_f_score":  "u.piotroski_f_score",
    "altman_z_score":     "u.altman_z_score",
    "ocf_to_net_profit":  "u.ocf_to_net_profit",
    "fcf_payout_ratio":   "u.fcf_payout_ratio",
    "eps_volatility_5y":  "u.eps_volatility_5y",
    "fcf_positive_years": "u.fcf_positive_years",
    "earnings_stability_score": "u.earnings_stability_score",
    "percent_insiders":   "u.percent_insiders",
    "percent_institutions": "u.percent_institutions",
    "short_pct":          "u.short_pct",
    "short_interest_chg_1w": "u.short_interest_chg_1w",
    "shares_dilution_3y": "u.shares_dilution_3y",
    "analyst_count":      "u.analyst_count",
    "analyst_buy_pct":    "u.analyst_buy_pct",
    "analyst_consensus_score": "u.analyst_consensus_score",
    # Quality / Rolling Averages
    "avg_roe_5y":              "u.avg_roe_5y",
    "avg_roa_3y":              "u.avg_roa_3y",
    "avg_roa_5y":              "u.avg_roa_5y",
    "avg_roce_3y":             "u.avg_roce_3y",
    "avg_roce_5y":             "u.avg_roce_5y",
    "avg_gross_margin_3y":     "u.avg_gross_margin_3y",
    "avg_gross_margin_5y":     "u.avg_gross_margin_5y",
    "avg_ebitda_margin_3y":    "u.avg_ebitda_margin_3y",
    "avg_ebitda_margin_5y":    "u.avg_ebitda_margin_5y",
    "avg_operating_margin_3y": "u.avg_operating_margin_3y",
    "avg_operating_margin_5y": "u.avg_operating_margin_5y",
    "avg_net_margin_3y":       "u.avg_net_margin_3y",
    "avg_net_margin_5y":       "u.avg_net_margin_5y",
    "avg_eps_growth_3y":       "u.avg_eps_growth_3y",
    "avg_eps_growth_5y":       "u.avg_eps_growth_5y",
    # Technicals
    "rsi_14":             "u.rsi_14",
    "rsi_21":             "u.rsi_21",
    "adx_14":             "u.adx_14",
    "sma_20":             "u.sma_20",
    "sma_50":             "u.sma_50",
    "sma_200":            "u.sma_200",
    "ema_20":             "u.ema_20",
    "bb_pct":             "u.bb_pct",
    "stoch_k":            "u.stoch_k",
    "stoch_d":            "u.stoch_d",
    "dma50_ratio":        "u.dma50_ratio",
    "dma200_ratio":       "u.dma200_ratio",
    "relative_volume":    "u.relative_volume",
    "volatility_20d":     "u.volatility_20d",
    "volatility_60d":     "u.volatility_60d",
    "beta_1y":            "u.beta_1y",
    "sharpe_1y":          "u.sharpe_1y",
    "drawdown_from_ath":  "u.drawdown_from_ath",
    # Returns
    "return_1w":          "u.return_1w",
    "return_1m":          "u.return_1m",
    "return_3m":          "u.return_3m",
    "return_6m":          "u.return_6m",
    "return_1y":          "u.return_1y",
    "return_ytd":         "u.return_ytd",
    "return_3y":          "u.return_3y",
    "return_5y":          "u.return_5y",
    "return_7y":          "u.return_7y",
    "return_10y":         "u.return_10y",
    "return_15y":         "u.return_15y",
}


def build_screener_sql(req: ScreenerRequest) -> tuple[str, str, dict]:
    """
    Build COUNT + DATA queries from the filter list.
    Queries screener.universe directly — no JOINs.
    Returns (count_sql, data_sql, params).
    """
    where_clauses: list[str] = [
        "u.price IS NOT NULL",      # exclude no-price stocks
        "u.status = 'active'",      # match sector heatmap — active stocks only
    ]
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
            # Cast to int before comparing so this works for BOTH:
            #   - smallint columns (is_reit, is_asx50, above_vwap, etc.) stored as 0/1
            #   - boolean expression fields (above_sma50, golden_cross, etc.)
            # PostgreSQL: true::int=1, false::int=0, 1::smallint::int=1
            if isinstance(f.value, bool):
                bool_val = f.value
            elif isinstance(f.value, str):
                bool_val = f.value.lower() in ("true", "1", "yes")
            else:
                bool_val = bool(f.value)
            if bool_val:
                where_clauses.append(f"({sql_col})::int != 0")
            else:
                where_clauses.append(f"({sql_col})::int = 0")

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
    user: Optional[dict] = Depends(get_optional_user),
):
    """
    Run a stock screen with dynamic filters against screener.universe.

    Free / unauthenticated users see at most 500 rows total.
    Pro and above see all results.

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

    # Determine if this user is on a free tier
    is_free = user is None or user.get("plan", "free") == "free"

    # ── Cache check (skip for page > 1 to keep key space small) ─────────────
    cache_key: str | None = None
    if req.page == 1:
        req_hash  = hashlib.md5(req.model_dump_json().encode()).hexdigest()
        tier_tag  = "free" if is_free else "paid"
        cache_key = make_key("screener", tier_tag, req_hash)
        cached    = await cache_get(cache_key)
        if cached:
            return ScreenerResponse(**cached)

    result = await db.execute(text(count_sql), params)
    total_raw = result.scalar() or 0

    # ── Apply free-tier cap ───────────────────────────────────────────────────
    if is_free:
        total     = min(total_raw, FREE_STOCK_LIMIT)
        is_capped = total_raw > FREE_STOCK_LIMIT
        # Cap offset so free users can never paginate past row 500
        offset        = (req.page - 1) * req.page_size
        capped_offset = min(offset, max(0, FREE_STOCK_LIMIT - req.page_size))
        capped_limit  = min(req.page_size, max(0, FREE_STOCK_LIMIT - capped_offset))
    else:
        total     = total_raw
        is_capped = False
        capped_offset = (req.page - 1) * req.page_size
        capped_limit  = req.page_size

    params["_limit"]  = capped_limit
    params["_offset"] = capped_offset

    if capped_limit > 0:
        result = await db.execute(text(data_sql), params)
        rows = result.mappings().all()
    else:
        rows = []

    response = ScreenerResponse(
        data=[ScreenerRow(**dict(r)) for r in rows],
        total=total,
        page=req.page,
        page_size=req.page_size,
        total_pages=math.ceil(total / req.page_size) if total else 0,
        filters_applied=len(req.filters),
        is_capped=is_capped,
        free_limit=FREE_STOCK_LIMIT if is_free else None,
    )

    if cache_key:
        await cache_set(cache_key, response.model_dump(), ttl=SCREENER_TTL)

    return response


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
    user: dict = Depends(get_current_user),
):
    """
    Stream screener results as a CSV file download (max 5,000 rows).
    Requires Pro plan or higher — free users receive HTTP 403.

    Takes the same request body as POST /screener (filters + sort),
    ignores page/page_size, and returns all matching rows up to the cap.

    Percentage fields (ROE, yields, margins, returns) are scaled to human-
    readable % values in the CSV (e.g. 0.15 → 15.00).

    Response: Content-Disposition: attachment; filename="asx_screener_YYYY-MM-DD.csv"
    """
    if user.get("plan", "free") == "free":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSV export is available on Pro and Premium plans. Upgrade to download data.",
        )

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
    Categories are returned in CATEGORY_ORDER order so the dropdown
    shows a logical, user-friendly hierarchy.
    """
    # Group fields by category (unordered first pass)
    raw_cats: dict[str, list] = {}
    for key, info in ALLOWED_FIELDS.items():
        cat = info["cat"]
        if cat not in raw_cats:
            raw_cats[cat] = []
        raw_cats[cat].append({
            "key":   key,
            "label": info["label"],
            "type":  info["type"],
            "unit":  info.get("unit", ""),
            "scale": info.get("scale", 1.0),
        })

    # Sort categories by CATEGORY_ORDER; unlisted ones go alphabetically at end
    order_map = {cat: i for i, cat in enumerate(CATEGORY_ORDER)}
    categories: dict[str, list] = {
        cat: fields
        for cat, fields in sorted(
            raw_cats.items(),
            key=lambda kv: (order_map.get(kv[0], len(CATEGORY_ORDER)), kv[0]),
        )
    }

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
                    {"field": "dividend_yield",  "operator": "gte", "value": 4},
                    {"field": "franking_pct",    "operator": "gte", "value": 70},
                    {"field": "net_margin",      "operator": "gt",  "value": 0},
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
                "sort_by": "piotroski_f_score", "sort_dir": "desc",
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
                "sort_by": "return_1m", "sort_dir": "desc",
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
                    {"field": "revenue_growth_hoh",    "operator": "gte", "value": 10},
                    {"field": "net_income_growth_hoh", "operator": "gte", "value": 10},
                    {"field": "net_margin",            "operator": "gt",  "value": 0},
                ],
                "sort_by": "revenue_growth_hoh", "sort_dir": "desc",
            },
            {
                "id":          "new_52w_lows",
                "name":        "Near 52-Week Lows",
                "description": "Stocks hammered to multi-month lows — mean-reversion and recovery candidates",
                "icon":        "arrow-down",
                "premium":     True,
                "min_plan":    "pro",
                "filters": [
                    {"field": "pct_from_52w_low", "operator": "lte", "value": 10},
                    {"field": "rsi_14",           "operator": "lte", "value": 40},
                    {"field": "market_cap",       "operator": "gte", "value": 50},
                    {"field": "volume",           "operator": "gte", "value": 50000},
                ],
                "sort_by": "rsi_14", "sort_dir": "asc",
            },
            {
                "id":          "volume_breakout",
                "name":        "Volume Breakout",
                "description": "Unusual volume surge with positive price action — institutional accumulation signal",
                "icon":        "bar-chart-2",
                "premium":     True,
                "min_plan":    "pro",
                "filters": [
                    {"field": "volume_ratio", "operator": "gte", "value": 2.0},
                    {"field": "return_1w",    "operator": "gte", "value": 3},
                    {"field": "market_cap",   "operator": "gte", "value": 50},
                    {"field": "adx_14",       "operator": "gte", "value": 20},
                ],
                "sort_by": "volume", "sort_dir": "desc",
            },
            {
                "id":          "rsi_oversold",
                "name":        "RSI Oversold (< 30)",
                "description": "Technically oversold stocks — potential snap-back rally candidates",
                "icon":        "trending-down",
                "premium":     True,
                "min_plan":    "pro",
                "filters": [
                    {"field": "rsi_14",     "operator": "lte", "value": 30},
                    {"field": "market_cap", "operator": "gte", "value": 100},
                    {"field": "volume",     "operator": "gte", "value": 50000},
                ],
                "sort_by": "rsi_14", "sort_dir": "asc",
            },
            {
                "id":          "rsi_overbought",
                "name":        "RSI Overbought (> 70)",
                "description": "Technically extended stocks — watch for profit-taking or confirm with strong trend",
                "icon":        "flame",
                "premium":     True,
                "min_plan":    "pro",
                "filters": [
                    {"field": "rsi_14",     "operator": "gte", "value": 70},
                    {"field": "market_cap", "operator": "gte", "value": 100},
                    {"field": "return_3m",  "operator": "gte", "value": 5},
                ],
                "sort_by": "rsi_14", "sort_dir": "desc",
            },


            # ── New Pro Screens ──────────────────────────────────────────────────
            {
                "id":          "cash_flow_champion",
                "name":        "Cash Flow Champion",
                "description": "Superior FCF generators — high free cash flow yield with strong returns and low debt",
                "icon":        "dollar-sign",
                "premium":     True,
                "min_plan":    "pro",
                "filters": [
                    {"field": "fcf_yield",      "operator": "gte", "value": 5},
                    {"field": "fcf_fy0",        "operator": "gt",  "value": 0},
                    {"field": "roe",            "operator": "gte", "value": 12},
                    {"field": "debt_to_equity", "operator": "lte", "value": 0.5},
                    {"field": "market_cap",     "operator": "gte", "value": 200},
                ],
                "sort_by": "fcf_yield", "sort_dir": "desc",
            },
            {
                "id":          "dividend_growth_machine",
                "name":        "Dividend Growth Machine",
                "description": "Consistent dividend growers — 5+ years consecutive payments with accelerating payout growth",
                "icon":        "trending-up",
                "premium":     True,
                "min_plan":    "pro",
                "filters": [
                    {"field": "dividend_consecutive_yrs", "operator": "gte", "value": 5},
                    {"field": "dividend_cagr_3y",         "operator": "gte", "value": 5},
                    {"field": "payout_ratio",             "operator": "lte", "value": 80},
                    {"field": "net_margin",               "operator": "gt",  "value": 0},
                    {"field": "market_cap",               "operator": "gte", "value": 200},
                ],
                "sort_by": "dividend_cagr_3y", "sort_dir": "desc",
            },
            {
                "id":          "earnings_momentum_surge",
                "name":        "Earnings Momentum Surge",
                "description": "Accelerating EPS and revenue growth with price trend confirmation — tomorrow's leaders today",
                "icon":        "zap",
                "premium":     True,
                "min_plan":    "pro",
                "filters": [
                    {"field": "earnings_growth_1y", "operator": "gte", "value": 25},
                    {"field": "revenue_growth_1y",  "operator": "gte", "value": 15},
                    {"field": "net_margin",         "operator": "gte", "value": 5},
                    {"field": "above_sma200",       "operator": "eq",  "value": True},
                    {"field": "market_cap",         "operator": "gte", "value": 100},
                ],
                "sort_by": "earnings_growth_1y", "sort_dir": "desc",
            },
            {
                "id":          "roic_compounder",
                "name":        "ROIC Compounder",
                "description": "Capital-efficient businesses with durable above-cost returns on invested capital",
                "icon":        "activity",
                "premium":     True,
                "min_plan":    "pro",
                "filters": [
                    {"field": "avg_roic_3y",       "operator": "gte", "value": 15},
                    {"field": "roic",              "operator": "gte", "value": 12},
                    {"field": "revenue_growth_1y", "operator": "gte", "value": 8},
                    {"field": "net_margin",        "operator": "gte", "value": 6},
                    {"field": "market_cap",        "operator": "gte", "value": 200},
                ],
                "sort_by": "avg_roic_3y", "sort_dir": "desc",
            },
            {
                "id":          "gross_margin_fortress",
                "name":        "Gross Margin Fortress",
                "description": "Durable pricing power — sustained high gross margins signal a genuine competitive moat",
                "icon":        "shield",
                "premium":     True,
                "min_plan":    "pro",
                "filters": [
                    {"field": "avg_gross_margin_5y", "operator": "gte", "value": 40},
                    {"field": "gross_margin",        "operator": "gte", "value": 35},
                    {"field": "roe",                 "operator": "gte", "value": 15},
                    {"field": "net_margin",          "operator": "gte", "value": 8},
                    {"field": "revenue_growth_1y",   "operator": "gte", "value": 5},
                    {"field": "market_cap",          "operator": "gte", "value": 200},
                ],
                "sort_by": "avg_gross_margin_5y", "sort_dir": "desc",
            },

            # ── Premium-only presets ──────────────────────────────────────────
            {
                "id":          "ai_top5",
                "name":        "AI Ranked Top 5",
                "description": "Composite quality + momentum model — mirrors the monthly AI-ranked Top 5 picks from ASX200",
                "icon":        "sparkles",
                "premium":     True,
                "min_plan":    "premium",
                "filters": [
                    {"field": "piotroski_f_score",  "operator": "gte", "value": 7},
                    {"field": "roe",                "operator": "gte", "value": 15},
                    {"field": "earnings_growth_1y", "operator": "gte", "value": 10},
                    {"field": "net_margin",         "operator": "gte", "value": 8},
                    {"field": "above_sma200",       "operator": "eq",  "value": True},
                    {"field": "market_cap",         "operator": "gte", "value": 500},
                ],
                "sort_by": "piotroski_f_score", "sort_dir": "desc",
            },
            {
                "id":          "mining_value",
                "name":        "Advanced Mining Value Screen",
                "description": "ASX miners with low PE, positive margins, strong balance sheet — value-grade mining exposure",
                "icon":        "pickaxe",
                "premium":     True,
                "min_plan":    "premium",
                "filters": [
                    {"field": "is_miner",           "operator": "eq",  "value": True},
                    {"field": "pe_ratio",           "operator": "lte", "value": 15},
                    {"field": "pe_ratio",           "operator": "gt",  "value": 0},
                    {"field": "piotroski_f_score",  "operator": "gte", "value": 6},
                    {"field": "net_margin",         "operator": "gt",  "value": 0},
                    {"field": "market_cap",         "operator": "gte", "value": 100},
                ],
                "sort_by": "pe_ratio", "sort_dir": "asc",
            },
            {
                "id":          "areit_income",
                "name":        "A-REIT Income Screen",
                "description": "Australian REITs with high distribution yield and positive earnings — income investor's shortlist",
                "icon":        "building-2",
                "premium":     True,
                "min_plan":    "premium",
                "filters": [
                    {"field": "is_reit",        "operator": "eq",  "value": True},
                    {"field": "dividend_yield", "operator": "gte", "value": 5},
                    {"field": "net_margin",     "operator": "gt",  "value": 0},
                ],
                "sort_by": "dividend_yield", "sort_dir": "desc",
            },
            {
                "id":          "franking_optimiser",
                "name":        "Franking Credit Optimiser",
                "description": "100% fully-franked stocks with grossed-up yield ≥ 7% and solid Piotroski score",
                "icon":        "dollar-sign",
                "premium":     True,
                "min_plan":    "premium",
                "filters": [
                    {"field": "franking_pct",       "operator": "eq",  "value": 100},
                    {"field": "grossed_up_yield",   "operator": "gte", "value": 7},
                    {"field": "net_margin",         "operator": "gt",  "value": 0},
                    {"field": "piotroski_f_score",  "operator": "gte", "value": 5},
                ],
                "sort_by": "grossed_up_yield", "sort_dir": "desc",
            },
            {
                "id":          "short_interest_risk",
                "name":        "Short Interest Risk Screen",
                "description": "High short interest stocks — identify squeeze candidates or distribution risk using ASIC data",
                "icon":        "alert-triangle",
                "premium":     True,
                "min_plan":    "premium",
                "filters": [
                    {"field": "short_pct",  "operator": "gte", "value": 5},
                    {"field": "market_cap", "operator": "gte", "value": 100},
                ],
                "sort_by": "short_pct", "sort_dir": "desc",
            },
            {
                "id":          "multi_factor_qm",
                "name":        "Multi-Factor Quality + Momentum",
                "description": "Elite compounders — strong ROE, growing revenue, high Piotroski, above 200-day MA with positive 3M return",
                "icon":        "layers",
                "premium":     True,
                "min_plan":    "premium",
                "filters": [
                    {"field": "roe",                "operator": "gte", "value": 15},
                    {"field": "net_margin",         "operator": "gte", "value": 8},
                    {"field": "revenue_growth_1y",  "operator": "gte", "value": 10},
                    {"field": "piotroski_f_score",  "operator": "gte", "value": 6},
                    {"field": "return_3m",          "operator": "gte", "value": 5},
                    {"field": "above_sma200",       "operator": "eq",  "value": True},
                ],
                "sort_by": "piotroski_f_score", "sort_dir": "desc",
            },

            # ── New Premium Screens ──────────────────────────────────────────────
            {
                "id":          "asx_dividend_aristocrats",
                "name":        "ASX Dividend Aristocrats",
                "description": "7+ years of consecutive dividends with 5-year CAGR growth and franking credits — the gold standard for income",
                "icon":        "award",
                "premium":     True,
                "min_plan":    "premium",
                "filters": [
                    {"field": "dividend_consecutive_yrs", "operator": "gte", "value": 7},
                    {"field": "dividend_cagr_5y",         "operator": "gte", "value": 5},
                    {"field": "franking_pct",             "operator": "gte", "value": 50},
                    {"field": "payout_ratio",             "operator": "lte", "value": 75},
                    {"field": "debt_to_equity",           "operator": "lte", "value": 1},
                    {"field": "market_cap",               "operator": "gte", "value": 500},
                ],
                "sort_by": "dividend_consecutive_yrs", "sort_dir": "desc",
            },
            {
                "id":          "quality_elite_compounder",
                "name":        "Quality Elite Compounder",
                "description": "Best-in-class ASX businesses — elite ROE, 5-year ROIC track record, minimal debt and consistent growth",
                "icon":        "star",
                "premium":     True,
                "min_plan":    "premium",
                "filters": [
                    {"field": "roe",            "operator": "gte", "value": 20},
                    {"field": "avg_roic_5y",    "operator": "gte", "value": 15},
                    {"field": "net_margin",     "operator": "gte", "value": 12},
                    {"field": "revenue_growth_1y", "operator": "gte", "value": 12},
                    {"field": "debt_to_equity", "operator": "lte", "value": 0.3},
                    {"field": "piotroski_f_score", "operator": "gte", "value": 7},
                    {"field": "market_cap",     "operator": "gte", "value": 500},
                ],
                "sort_by": "roe", "sort_dir": "desc",
            },
            {
                "id":          "altman_safety_screen",
                "name":        "Altman Z-Score Safety",
                "description": "Financially bulletproof companies — Altman Z > 3 with strong liquidity and zero distress risk",
                "icon":        "shield",
                "premium":     True,
                "min_plan":    "premium",
                "filters": [
                    {"field": "altman_z_score",    "operator": "gte", "value": 3},
                    {"field": "current_ratio",     "operator": "gte", "value": 2},
                    {"field": "debt_to_equity",    "operator": "lte", "value": 0.5},
                    {"field": "net_margin",        "operator": "gte", "value": 5},
                    {"field": "piotroski_f_score", "operator": "gte", "value": 6},
                    {"field": "market_cap",        "operator": "gte", "value": 100},
                ],
                "sort_by": "altman_z_score", "sort_dir": "desc",
            },
            {
                "id":          "low_beta_income_shield",
                "name":        "Low Beta Income Shield",
                "description": "Defensive income fortress — low market correlation with franked dividends for capital preservation",
                "icon":        "dollar-sign",
                "premium":     True,
                "min_plan":    "premium",
                "filters": [
                    {"field": "beta_1y",        "operator": "lte", "value": 0.8},
                    {"field": "dividend_yield", "operator": "gte", "value": 3},
                    {"field": "franking_pct",   "operator": "gte", "value": 50},
                    {"field": "net_margin",     "operator": "gt",  "value": 0},
                    {"field": "piotroski_f_score", "operator": "gte", "value": 5},
                    {"field": "market_cap",     "operator": "gte", "value": 500},
                ],
                "sort_by": "grossed_up_yield", "sort_dir": "desc",
            },
            {
                "id":          "small_cap_hidden_gems",
                "name":        "Small Cap Hidden Gems",
                "description": "Quality small caps before they go mainstream — strong fundamentals in the $50M-$500M space",
                "icon":        "search",
                "premium":     True,
                "min_plan":    "premium",
                "filters": [
                    {"field": "market_cap",        "operator": "gte", "value": 50},
                    {"field": "market_cap",        "operator": "lte", "value": 500},
                    {"field": "piotroski_f_score", "operator": "gte", "value": 7},
                    {"field": "revenue_growth_1y", "operator": "gte", "value": 20},
                    {"field": "net_margin",        "operator": "gte", "value": 5},
                    {"field": "debt_to_equity",    "operator": "lte", "value": 0.5},
                ],
                "sort_by": "revenue_growth_1y", "sort_dir": "desc",
            },

        ]
    }


# ── GET /screener/query/fields ────────────────────────────────────────────────

@router.get("/query/fields")
async def get_query_fields(
    _user: dict = Depends(require_query_access),
):
    """
    Returns all filterable fields with their keys, labels, units, categories,
    and human-readable aliases for use in the Query Mode field reference panel.

    Admin-only endpoint (same access control as the query runner).
    """
    return {"fields": get_field_reference(ALLOWED_FIELDS)}


# ── POST /screener/query ──────────────────────────────────────────────────────

@router.post("/query", response_model=ScreenerResponse)
async def query_screener(
    req: QueryScreenerRequest,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(require_query_access),
):
    """
    Run a stock screen using a SQL-like WHERE expression against screener.universe.

    Supports AND / OR logic and parenthesised grouping — unlike the standard
    filter endpoint which only supports AND.

    Admin-only for now; planned for Pro / Premium once the feature matures.

    Example queries:
        roe > 10 AND roce > 10 AND roic > 10
        roe > 10 AND (roce > 10 OR roic > 10)
        sales growth 5years > 10 AND average return on equity 3years > 15
        sector = 'Materials' AND market_cap > 1000
        is_reit = true AND dividend_yield > 5
        is_miner AND pe_ratio < 15 AND sector != 'Energy'

    Field names are case-insensitive. The field reference endpoint
    (GET /api/v1/screener/query/fields) lists all available fields and aliases.

    Value types:
      number  — enter the human-readable value (e.g. "roe > 10" means ROE > 10%)
      text    — quote the value, e.g. sector = 'Materials' (use = or !=)
      boolean — is_reit = true / false, or just "is_reit" to mean true
    """
    # Parse the text query into a parameterized SQL WHERE fragment
    try:
        custom_where, params = parse_query(req.query, ALLOWED_FIELDS)
    except QueryParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # Baseline WHERE clauses (same as the standard screener)
    base_where = "u.price IS NOT NULL AND u.status = 'active'"
    where      = f"{base_where} AND ({custom_where})"

    # Sort column — whitelist only (same logic as build_screener_sql)
    sort_key  = req.sort_by.lower()
    sort_expr = SORTABLE_COLS.get(sort_key, "u.market_cap")
    sort_dir  = "DESC" if req.sort_dir.lower() == "desc" else "ASC"

    count_sql = f"SELECT COUNT(*) FROM screener.universe u WHERE {where}"

    data_sql = f"""
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
        WHERE {where}
        ORDER BY {sort_expr} {sort_dir} NULLS LAST
        LIMIT :_limit OFFSET :_offset
    """

    # Execute count
    count_result = await db.execute(text(count_sql), params)
    total = count_result.scalar() or 0

    offset = (req.page - 1) * req.page_size
    params["_limit"]  = req.page_size
    params["_offset"] = offset

    if req.page_size > 0:
        data_result = await db.execute(text(data_sql), params)
        rows = data_result.mappings().all()
    else:
        rows = []

    return ScreenerResponse(
        data=[ScreenerRow(**dict(r)) for r in rows],
        total=total,
        page=req.page,
        page_size=req.page_size,
        total_pages=math.ceil(total / req.page_size) if total else 0,
        filters_applied=1,   # 1 = the custom query counts as one expression
        is_capped=False,
        free_limit=None,
    )


# ── POST /screener/query/export ───────────────────────────────────────────────

@router.post("/query/export")
async def export_query_screener(
    req: QueryScreenerRequest,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_query_access),
):
    """CSV export for Query Mode — same as /query but streams a CSV file."""
    if user.get("plan", "free") == "free":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSV export is available on Pro and Premium plans.",
        )

    try:
        custom_where, params = parse_query(req.query, ALLOWED_FIELDS)
    except QueryParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    base_where = "u.price IS NOT NULL AND u.status = 'active'"
    where      = f"{base_where} AND ({custom_where})"
    sort_key   = req.sort_by.lower()
    sort_expr  = SORTABLE_COLS.get(sort_key, "u.market_cap")
    sort_dir   = "DESC" if req.sort_dir.lower() == "desc" else "ASC"

    export_sql = f"""
        SELECT {', '.join(f'u.{c}' for c in _EXPORT_COLS)}
        FROM screener.universe u
        WHERE {where}
        ORDER BY {sort_expr} {sort_dir} NULLS LAST
        LIMIT {_EXPORT_MAX_ROWS}
    """
    result = await db.execute(text(export_sql), params)
    rows = result.mappings().all()

    def generate() -> Any:
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow([_HEADER_LABELS.get(c, c) for c in _EXPORT_COLS])
        yield buf.getvalue()
        for row in rows:
            buf.truncate(0)
            buf.seek(0)
            writer.writerow([_fmt_val(col, row.get(col)) for col in _EXPORT_COLS])
            yield buf.getvalue()

    filename = f"asx_query_export_{date_type.today().isoformat()}.csv"
    return StreamingResponse(
        generate(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
