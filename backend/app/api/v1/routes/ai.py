"""
ASX Screener — AI Routes
POST /api/v1/ai/nl-screener   — Natural language → structured screener + results
POST /api/v1/ai/anomalies     — Detect anomalies across the universe (batch, admin)
GET  /api/v1/ai/anomalies/{code} — Anomaly flags for a specific stock
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from pydantic import BaseModel
import json
import math
import logging

from app.db.session import get_db
from app.core.config import settings
from app.schemas.screener import ScreenerRequest, ScreenerFilter
from app.api.v1.routes.screener import ALLOWED_FIELDS, build_screener_sql, SORTABLE_COLS

log = logging.getLogger(__name__)
router = APIRouter()


# ── Field reference for the prompt ───────────────────────────────────────────

def _build_field_reference() -> str:
    lines: list[str] = []
    current_cat = None
    for field, meta in ALLOWED_FIELDS.items():
        if meta["cat"] != current_cat:
            current_cat = meta["cat"]
            lines.append(f"\n[{current_cat}]")
        unit = f" ({meta['unit']})" if meta["unit"] else ""
        note = ""
        if meta["scale"] == 0.01:
            note = " [enter as percentage, e.g. 15 means 15%]"
        elif meta["scale"] == 1_000_000:
            note = " [enter in AUD millions, e.g. 500 means $500M]"
        lines.append(f"  {field}: {meta['label']}{unit}{note}  type={meta['type']}")
    return "\n".join(lines)

_FIELD_REF = _build_field_reference()

_NL_SYSTEM = """You are an expert Australian equities analyst assistant. Convert natural language stock screening queries into structured filter objects for the ASX screener."""

_NL_PROMPT = """Convert this query into ASX screener filters.

Query: "{query}"

Available fields:
{fields}

Operator options: gte (>=), lte (<=), gt (>), lt (<), eq (=), neq (!=), in (IN list)
Boolean fields: operator must be "eq", value true or false
Text fields (sector, industry): operator "eq" or "in"

Common sector values: "Materials", "Financials", "Energy", "Health Care", "Consumer Discretionary", "Consumer Staples", "Industrials", "Information Technology", "Communication Services", "Real Estate", "Utilities"

Interpretation rules:
- "miners" → is_miner eq true
- "REITs" → is_reit eq true
- "ASX200" → is_asx200 eq true
- "profitable" → net_margin gte 5, roe gte 10
- "low debt" → debt_to_equity lte 0.5
- "high dividends" → dividend_yield gte 4
- "franked" → franking_pct gte 70
- "growth stocks" → revenue_growth_1y gte 15, earnings_growth_1y gte 10
- "value/cheap" → pe_ratio lte 15
- "quality" → piotroski_f_score gte 7
- "small cap" → market_cap lte 300 (AUD M)
- "large cap" → market_cap gte 2000 (AUD M)
- "oversold" → rsi_14 lte 35
- "momentum" → return_3m gte 10, above_sma50 eq true

Return ONLY valid JSON — no markdown, no explanation:
{{
  "interpretation": "Plain English description of what this screen finds, including key thresholds",
  "filters": [
    {{"field": "field_name", "operator": "operator", "value": value}}
  ],
  "sort_by": "field_name",
  "sort_dir": "desc"
}}

Use correct JSON types: numbers as numbers (not strings), booleans as true/false."""


# ── Week 11: Natural Language Screener ───────────────────────────────────────

class NLScreenerRequest(BaseModel):
    query: str


@router.post("/nl-screener")
async def nl_screener(
    body: NLScreenerRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Convert a natural language query into structured screener filters and run the screen.
    Returns: query, interpretation, filters applied, and paginated results.
    """
    if not settings.ANTHROPIC_API_KEY:
        raise HTTPException(status_code=503, detail="AI features not configured.")

    query = body.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    # Call Claude Haiku to parse the query
    prompt = _NL_PROMPT.format(query=query, fields=_FIELD_REF)

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            system=_NL_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()

        # Strip markdown code fences if Claude wrapped the JSON
        if raw.startswith("```"):
            parts = raw.split("```")
            raw = parts[1].lstrip("json").strip() if len(parts) > 1 else raw
    except Exception as e:
        log.error("Claude API error in nl-screener: %s", e)
        raise HTTPException(status_code=500, detail=f"AI generation failed: {e}")

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        log.error("Invalid JSON from Claude for nl-screener: %s", raw)
        raise HTTPException(
            status_code=500,
            detail="AI returned an unreadable response. Try rephrasing your query.",
        )

    # Validate filters — drop anything Claude hallucinated
    valid: list[ScreenerFilter] = []
    for f in parsed.get("filters", []):
        field    = f.get("field", "")
        operator = f.get("operator", "")
        value    = f.get("value")

        if field not in ALLOWED_FIELDS:
            log.warning("nl-screener: unknown field '%s' — dropped", field)
            continue
        if operator not in ("gt", "gte", "lt", "lte", "eq", "neq", "in"):
            log.warning("nl-screener: invalid operator '%s' — dropped", operator)
            continue
        valid.append(ScreenerFilter(field=field, operator=operator, value=value))

    if not valid:
        raise HTTPException(
            status_code=422,
            detail="Could not interpret that query. Try something like 'profitable miners with low debt and high dividends'.",
        )

    # Resolve sort
    sort_by  = parsed.get("sort_by", "market_cap")
    sort_dir = parsed.get("sort_dir", "desc")
    if sort_by not in SORTABLE_COLS:
        sort_by = "market_cap"
    if sort_dir not in ("asc", "desc"):
        sort_dir = "desc"

    # Run the screener
    req = ScreenerRequest(
        filters=valid,
        sort_by=sort_by,
        sort_dir=sort_dir,
        page=1,
        page_size=50,
    )
    try:
        count_sql, data_sql, params = build_screener_sql(req)
        total  = (await db.execute(text(count_sql), params)).scalar() or 0
        rows   = (await db.execute(text(data_sql),  params)).mappings().all()
    except Exception as e:
        log.error("nl-screener DB error: %s", e)
        raise HTTPException(status_code=500, detail="Database error running the screen.")

    return {
        "query":          query,
        "interpretation": parsed.get("interpretation", ""),
        "filters":        [{"field": f.field, "operator": f.operator, "value": f.value} for f in valid],
        "sort_by":        sort_by,
        "sort_dir":       sort_dir,
        "total":          total,
        "total_pages":    math.ceil(total / 50) if total else 0,
        "data":           [dict(r) for r in rows],
    }


# ── Week 13: Anomaly flags ────────────────────────────────────────────────────

@router.get("/anomalies/{asx_code}")
async def get_anomalies(
    asx_code: str,
    db: AsyncSession = Depends(get_db),
):
    """Return active anomaly flags for a stock (detected by anomaly_detect.py)."""
    code = asx_code.upper()
    rows = await db.execute(text("""
        SELECT flag_type, description, severity, detected_at
        FROM market.anomalies
        WHERE asx_code = :code
          AND is_active = TRUE
        ORDER BY detected_at DESC
    """), {"code": code})
    flags = [dict(r) for r in rows.mappings().all()]
    for f in flags:
        if f.get("detected_at"):
            f["detected_at"] = f["detected_at"].isoformat()
    return {"asx_code": code, "flags": flags}
