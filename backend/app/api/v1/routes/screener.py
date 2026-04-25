"""
ASX Screener — Screener API Route
POST /api/v1/screener   — Run a screen with dynamic filters
GET  /api/v1/screener/fields — List all filterable fields with metadata
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import math

from app.db.session import get_db
from app.schemas.screener import (
    ScreenerRequest, ScreenerResponse, ScreenerRow
)

router = APIRouter()

# ── Allowed filter fields (whitelist — prevents SQL injection) ─
# Maps field name → SQL expression in our query
ALLOWED_FIELDS = {
    # Company fields
    "sector":           "c.gics_sector",
    "gics_sector":      "c.gics_sector",
    "industry":         "c.gics_industry_group",
    "is_reit":          "c.is_reit",
    "is_miner":         "c.is_miner",
    "is_asx200":        "c.is_asx200",
    "is_asx300":        "c.is_asx300",
    "is_all_ords":      "c.is_all_ords",

    # Price fields (from latest daily price)
    "close":            "p.close",
    "open":             "p.open",
    "high":             "p.high",
    "low":              "p.low",
    "volume":           "p.volume",
    "high_52w":         "p52.high_52w",
    "low_52w":          "p52.low_52w",
    "change_pct":       "p.change_pct",

    # Computed metrics (populated by compute engine)
    "market_cap":           "m.market_cap",
    "pe_ratio":             "m.pe_ratio",
    "pb_ratio":             "m.pb_ratio",
    "ps_ratio":             "m.ps_ratio",
    "ev_ebitda":            "m.ev_ebitda",
    "dividend_yield":       "m.dividend_yield",
    "grossed_up_yield":     "m.grossed_up_yield",
    "franking_pct":         "m.franking_pct",
    "roe":                  "m.roe",
    "roa":                  "m.roa",
    "roce":                 "m.roce",
    "roic":                 "m.roic",
    "opm":                  "m.opm",
    "npm":                  "m.npm",
    "debt_to_equity":       "m.debt_to_equity",
    "current_ratio":        "m.current_ratio",
    "revenue_growth_1y":    "m.revenue_growth_1y",
    "revenue_growth_3y":    "m.revenue_growth_3y",
    "profit_growth_1y":     "m.profit_growth_1y",
    "profit_growth_3y":     "m.profit_growth_3y",
    "piotroski_score":      "m.piotroski_score",
    "altman_z_score":       "m.altman_z_score",
    "short_interest_pct":   "m.short_interest_pct",
    "beta_1y":              "m.beta_1y",
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

VALID_SORT = set(ALLOWED_FIELDS.keys()) | {"asx_code", "company_name"}


def build_screener_sql(req: ScreenerRequest) -> tuple[str, dict]:
    """
    Builds the screener SQL query dynamically from filter list.
    Returns (sql_template, params_dict)
    """
    where_clauses = ["c.status = 'active'"]
    params: dict = {}

    for i, f in enumerate(req.filters):
        field = f.field.lower()
        if field not in ALLOWED_FIELDS:
            raise HTTPException(status_code=400, detail=f"Unknown filter field: '{f.field}'")

        sql_col  = ALLOWED_FIELDS[field]
        operator = OPERATOR_MAP.get(f.operator.value)
        param_key = f"p{i}"

        if f.operator.value == "in":
            if not isinstance(f.value, list):
                raise HTTPException(status_code=400, detail=f"Field '{f.field}': 'in' operator requires a list value")
            placeholders = ", ".join([f":{param_key}_{j}" for j in range(len(f.value))])
            where_clauses.append(f"{sql_col} IN ({placeholders})")
            for j, v in enumerate(f.value):
                params[f"{param_key}_{j}"] = v
        else:
            where_clauses.append(f"{sql_col} {operator} :{param_key}")
            params[param_key] = f.value

    where = " AND ".join(where_clauses)

    # Sort column
    sort_col = req.sort_by.lower()
    if sort_col in ALLOWED_FIELDS:
        sort_expr = ALLOWED_FIELDS[sort_col]
    elif sort_col == "asx_code":
        sort_expr = "c.asx_code"
    elif sort_col == "company_name":
        sort_expr = "c.company_name"
    else:
        sort_expr = "m.market_cap"

    sort_dir = "DESC" if req.sort_dir.lower() == "desc" else "ASC"

    base_sql = f"""
        FROM market.companies c

        -- Latest daily price
        LEFT JOIN LATERAL (
            SELECT
                p.close, p.open, p.high, p.low, p.volume,
                ROUND(((p.close - p2.close) / NULLIF(p2.close, 0) * 100)::numeric, 2) AS change_pct
            FROM market.daily_prices p
            LEFT JOIN LATERAL (
                SELECT close FROM market.daily_prices
                WHERE asx_code = p.asx_code
                  AND time < p.time
                ORDER BY time DESC LIMIT 1
            ) p2 ON TRUE
            WHERE p.asx_code = c.asx_code
            ORDER BY p.time DESC
            LIMIT 1
        ) p ON TRUE

        -- 52-week high/low
        LEFT JOIN LATERAL (
            SELECT
                MAX(high) AS high_52w,
                MIN(low)  AS low_52w
            FROM market.daily_prices
            WHERE asx_code = c.asx_code
              AND time >= NOW() - INTERVAL '52 weeks'
        ) p52 ON TRUE

        -- Latest computed metrics
        LEFT JOIN LATERAL (
            SELECT *
            FROM market.computed_metrics
            WHERE asx_code = c.asx_code
            ORDER BY time DESC
            LIMIT 1
        ) m ON TRUE

        WHERE {where}
    """

    count_sql = f"SELECT COUNT(*) {base_sql}"

    data_sql = f"""
        SELECT
            c.asx_code, c.company_name, c.gics_sector, c.gics_industry_group,
            c.is_reit, c.is_miner, c.is_asx200,
            p.close, p.open, p.high, p.low, p.volume, p.change_pct,
            p52.high_52w, p52.low_52w,
            m.market_cap, m.pe_ratio, m.pb_ratio,
            m.dividend_yield, m.grossed_up_yield, m.franking_pct,
            m.roe, m.debt_to_equity, m.revenue_growth_1y, m.piotroski_score
        {base_sql}
        ORDER BY {sort_expr} {sort_dir} NULLS LAST
        LIMIT :_limit OFFSET :_offset
    """

    return count_sql, data_sql, params


# ── POST /screener ────────────────────────────────────────────

@router.post("", response_model=ScreenerResponse)
async def run_screener(
    req: ScreenerRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Run a stock screen with dynamic filters.

    Example filters:
    - Sector = Materials, Price >= $1.00, Volume >= 100,000
    - PE < 20, ROE > 15%, Dividend Yield > 3%
    - Piotroski Score >= 7, Debt/Equity < 0.5
    - Is ASX200, Grossed-Up Yield > 5%
    """
    try:
        count_sql, data_sql, params = build_screener_sql(req)
    except HTTPException:
        raise

    # Count
    result = await db.execute(text(count_sql), params)
    total = result.scalar() or 0

    # Fetch page
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


# ── GET /screener/fields ──────────────────────────────────────

@router.get("/fields")
async def get_screener_fields():
    """
    Returns all available filter fields with categories.
    Used by the frontend to build the screener UI dynamically.
    """
    return {
        "fields": {
            "Company": [
                {"key": "sector",      "label": "Sector",       "type": "string"},
                {"key": "is_reit",     "label": "Is REIT",      "type": "boolean"},
                {"key": "is_miner",    "label": "Is Miner",     "type": "boolean"},
                {"key": "is_asx200",   "label": "In ASX 200",   "type": "boolean"},
            ],
            "Price": [
                {"key": "close",       "label": "Price (AUD)",  "type": "number", "unit": "AUD"},
                {"key": "volume",      "label": "Volume",       "type": "number"},
                {"key": "change_pct",  "label": "1D Change %",  "type": "number", "unit": "%"},
                {"key": "high_52w",    "label": "52W High",     "type": "number", "unit": "AUD"},
                {"key": "low_52w",     "label": "52W Low",      "type": "number", "unit": "AUD"},
            ],
            "Valuation": [
                {"key": "market_cap",     "label": "Market Cap (AUD M)", "type": "number"},
                {"key": "pe_ratio",       "label": "P/E Ratio",          "type": "number"},
                {"key": "pb_ratio",       "label": "P/B Ratio",          "type": "number"},
                {"key": "ev_ebitda",      "label": "EV/EBITDA",          "type": "number"},
                {"key": "dividend_yield", "label": "Dividend Yield %",   "type": "number", "unit": "%"},
                {"key": "grossed_up_yield","label": "Grossed-Up Yield %","type": "number", "unit": "%"},
                {"key": "franking_pct",   "label": "Franking %",         "type": "number", "unit": "%"},
            ],
            "Profitability": [
                {"key": "roe",  "label": "ROE %",          "type": "number", "unit": "%"},
                {"key": "roa",  "label": "ROA %",          "type": "number", "unit": "%"},
                {"key": "roce", "label": "ROCE %",         "type": "number", "unit": "%"},
                {"key": "opm",  "label": "Operating Margin %", "type": "number", "unit": "%"},
                {"key": "npm",  "label": "Net Margin %",   "type": "number", "unit": "%"},
            ],
            "Growth": [
                {"key": "revenue_growth_1y", "label": "Revenue Growth 1Y %", "type": "number", "unit": "%"},
                {"key": "revenue_growth_3y", "label": "Revenue Growth 3Y %", "type": "number", "unit": "%"},
                {"key": "profit_growth_1y",  "label": "Profit Growth 1Y %",  "type": "number", "unit": "%"},
                {"key": "profit_growth_3y",  "label": "Profit Growth 3Y %",  "type": "number", "unit": "%"},
            ],
            "Financial Health": [
                {"key": "debt_to_equity", "label": "Debt/Equity",    "type": "number"},
                {"key": "current_ratio",  "label": "Current Ratio",  "type": "number"},
                {"key": "altman_z_score", "label": "Altman Z-Score", "type": "number"},
            ],
            "Quality": [
                {"key": "piotroski_score",  "label": "Piotroski Score",  "type": "number"},
                {"key": "short_interest_pct","label": "Short Interest %", "type": "number", "unit": "%"},
                {"key": "beta_1y",          "label": "Beta (1Y)",        "type": "number"},
            ],
        },
        "operators": [
            {"value": "gt",  "label": ">"},
            {"value": "gte", "label": ">="},
            {"value": "lt",  "label": "<"},
            {"value": "lte", "label": "<="},
            {"value": "eq",  "label": "="},
            {"value": "in",  "label": "in list"},
        ]
    }
