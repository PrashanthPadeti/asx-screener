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
import hashlib
import json
import math
import logging
from datetime import datetime, timedelta, timezone

from app.db.session import get_db
from app.core.config import settings
from app.core.deps import get_current_user
from app.core.plans import get_limits
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
    page:  int = 1


@router.post("/nl-screener")
async def nl_screener(
    body: NLScreenerRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Convert a natural language query into structured screener filters and run the screen.
    Requires Pro plan or higher.
    """
    if not get_limits(current_user.get("plan", "free"))["nl_screener"]:
        raise HTTPException(status_code=403, detail="NL Screener requires a Pro plan or higher.")
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
        page=max(1, body.page),
        page_size=50,
    )
    try:
        count_sql, data_sql, params = build_screener_sql(req)
        total  = (await db.execute(text(count_sql), params)).scalar() or 0
        params["_limit"]  = req.page_size
        params["_offset"] = (req.page - 1) * req.page_size
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


# ── v1.4: Portfolio AI Insights ──────────────────────────────────────────────

INSIGHTS_TTL_DAYS = 7


def _holdings_hash(holdings: dict) -> str:
    """MD5 fingerprint of sorted (code, qty, avg_cost) — changes on any buy/sell/DRP."""
    items = sorted(
        (code, round(h["quantity"], 2), round(h["avg_cost"], 3))
        for code, h in holdings.items()
    )
    return hashlib.md5(str(items).encode()).hexdigest()


@router.get("/portfolio-insights/{portfolio_id}")
async def get_portfolio_insights(
    portfolio_id: str,
    refresh: bool = False,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Claude analysis of a portfolio.
    Returns cached insights (up to 7 days) when holdings haven't changed.
    Pass ?refresh=true to force regeneration.
    """
    if not get_limits(current_user.get("plan", "free"))["nl_screener"]:
        raise HTTPException(status_code=403, detail="AI Insights requires a Pro plan or higher.")
    if not settings.ANTHROPIC_API_KEY:
        raise HTTPException(status_code=503, detail="AI features not configured.")

    p = (await db.execute(
        text("SELECT id, name FROM users.portfolios WHERE id = :pid AND user_id = :uid"),
        {"pid": portfolio_id, "uid": current_user["id"]},
    )).mappings().fetchone()
    if not p:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    txn_rows = (await db.execute(text("""
        SELECT asx_code, transaction_type, shares, price_per_share, brokerage
        FROM users.portfolio_transactions
        WHERE portfolio_id = :pid
        ORDER BY transaction_date ASC, id ASC
    """), {"pid": portfolio_id})).mappings().all()

    if not txn_rows:
        raise HTTPException(status_code=400, detail="Portfolio has no transactions")

    raw: dict[str, dict] = {}
    for r in txn_rows:
        code  = r["asx_code"]
        ttype = r["transaction_type"]
        qty   = float(r["shares"])
        price = float(r["price_per_share"])
        brok  = float(r["brokerage"] or 0)
        if code not in raw:
            raw[code] = {"quantity": 0.0, "total_buy_cost": 0.0, "total_buy_qty": 0.0}
        h = raw[code]
        if ttype in ("buy", "drp"):
            h["total_buy_cost"] += qty * price + brok
            h["total_buy_qty"]  += qty
            h["quantity"]       += qty
        elif ttype == "sell":
            h["quantity"] -= qty

    holdings = {
        code: {
            "quantity":   round(h["quantity"], 4),
            "avg_cost":   h["total_buy_cost"] / h["total_buy_qty"] if h["total_buy_qty"] > 0 else 0,
            "cost_basis": h["quantity"] * (h["total_buy_cost"] / h["total_buy_qty"] if h["total_buy_qty"] > 0 else 0),
        }
        for code, h in raw.items()
        if round(h["quantity"], 4) > 0
    }

    if not holdings:
        raise HTTPException(status_code=400, detail="Portfolio has no current holdings")

    # ── Cache check ───────────────────────────────────────────────────────────
    h_hash = _holdings_hash(holdings)

    if not refresh:
        cached = (await db.execute(text("""
            SELECT insights_json, holdings_json, sector_allocation_json,
                   total_value, total_cost, total_return_pct, annual_income,
                   portfolio_yield, top3_concentration, num_holdings,
                   generated_at, expires_at, holdings_hash
            FROM users.portfolio_insights
            WHERE portfolio_id = :pid
        """), {"pid": portfolio_id})).mappings().fetchone()

        if cached:
            now = datetime.now(timezone.utc)
            exp = cached["expires_at"]
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            still_fresh   = exp > now
            same_holdings = cached["holdings_hash"] == h_hash

            if still_fresh and same_holdings:
                log.info("portfolio-insights cache hit for %s", portfolio_id)
                return {
                    "portfolio_id":       portfolio_id,
                    "portfolio_name":     p["name"],
                    "total_value":        float(cached["total_value"] or 0),
                    "total_return_pct":   float(cached["total_return_pct"] or 0),
                    "portfolio_yield":    float(cached["portfolio_yield"] or 0),
                    "annual_income":      float(cached["annual_income"] or 0),
                    "num_holdings":       cached["num_holdings"] or 0,
                    "top3_concentration": float(cached["top3_concentration"] or 0),
                    "sector_allocation":  cached["sector_allocation_json"] or {},
                    "holdings":           cached["holdings_json"] or [],
                    "insights":           cached["insights_json"],
                    "cached":             True,
                    "generated_at":       cached["generated_at"].isoformat(),
                    "expires_at":         exp.isoformat(),
                    "cache_reason":       "same_holdings" if same_holdings else "fresh",
                }
            else:
                reason = "holdings_changed" if not same_holdings else "expired"
                log.info("portfolio-insights cache miss (%s) for %s", reason, portfolio_id)

    codes = list(holdings.keys())
    placeholders = ', '.join(f':c{i}' for i in range(len(codes)))
    code_params  = {f'c{i}': c for i, c in enumerate(codes)}

    universe_rows = (await db.execute(text(f"""
        SELECT asx_code, company_name, sector, price,
               dividend_yield, franking_pct, pe_ratio, dps_ttm
        FROM screener.universe
        WHERE asx_code IN ({placeholders})
    """), code_params)).mappings().all()
    live = {r["asx_code"]: r for r in universe_rows}

    holdings_data = []
    total_cost   = 0.0
    total_value  = 0.0
    total_income = 0.0
    sector_map: dict[str, float] = {}

    for code, h in holdings.items():
        u          = live.get(code)
        qty        = h["quantity"]
        cost_basis = h["cost_basis"]
        cur_price  = float(u["price"]) if u and u["price"] is not None else h["avg_cost"]
        cur_value  = qty * cur_price
        gain_pct   = (cur_value - cost_basis) / cost_basis * 100 if cost_basis > 0 else 0
        sector     = (u["sector"] if u else None) or "Unknown"
        dps        = float(u["dps_ttm"]) if u and u["dps_ttm"] is not None else 0

        total_cost   += cost_basis
        total_value  += cur_value
        total_income += qty * dps
        sector_map[sector] = sector_map.get(sector, 0.0) + cur_value

        holdings_data.append({
            "code":        code,
            "name":        (u["company_name"] if u else None) or code,
            "sector":      sector,
            "quantity":    round(qty, 0),
            "avg_cost":    round(h["avg_cost"], 3),
            "cur_price":   round(cur_price, 3),
            "cur_value":   round(cur_value, 2),
            "gain_pct":    round(gain_pct, 1),
            "weight_pct":  0.0,
            "div_yield":   round(float(u["dividend_yield"]) if u and u["dividend_yield"] else 0, 2),
            "franking_pct": round(float(u["franking_pct"]) if u and u["franking_pct"] else 0, 0),
        })

    for h in holdings_data:
        h["weight_pct"] = round(h["cur_value"] / total_value * 100, 1) if total_value > 0 else 0
    holdings_data.sort(key=lambda x: x["weight_pct"], reverse=True)

    total_gl_pct    = (total_value - total_cost) / total_cost * 100 if total_cost > 0 else 0
    portfolio_yield = total_income / total_value * 100 if total_value > 0 else 0
    top3_weight     = sum(h["weight_pct"] for h in holdings_data[:3])
    sector_alloc    = {
        s: round(v / total_value * 100, 1)
        for s, v in sorted(sector_map.items(), key=lambda x: -x[1])
    } if total_value > 0 else {}

    holdings_summary = "\n".join([
        f"- {h['code']} ({h['name']}): {h['weight_pct']:.1f}% of portfolio, "
        f"cost ${h['avg_cost']:.3f}, now ${h['cur_price']:.3f} ({h['gain_pct']:+.1f}%), "
        f"yield {h['div_yield']:.1f}% ({int(h['franking_pct'])}% franked)"
        for h in holdings_data[:20]
    ])
    sector_summary = "\n".join([f"- {s}: {pct:.1f}%" for s, pct in sector_alloc.items()])

    prompt = f"""Analyse this ASX portfolio and provide concise, actionable insights for an Australian investor.

PORTFOLIO SUMMARY:
- Total Value: ${total_value:,.0f}
- Total Return: {total_gl_pct:+.1f}% since average cost
- Annual Income: ${total_income:,.0f} (yield {portfolio_yield:.1f}% p.a.)
- Number of Holdings: {len(holdings_data)}
- Top 3 Concentration: {top3_weight:.1f}%

HOLDINGS (sorted by portfolio weight):
{holdings_summary}

SECTOR ALLOCATION:
{sector_summary}

Return ONLY valid JSON — no markdown, no explanation:
{{
  "summary": "2-3 sentence overall portfolio assessment",
  "concentration_risk": {{
    "level": "low|medium|high",
    "comment": "Assessment of top-holding concentration and diversification"
  }},
  "sector_analysis": {{
    "dominant_sector": "sector name",
    "comment": "Assessment of sector balance, over/under-weight sectors and implied risk"
  }},
  "income_analysis": {{
    "comment": "Assessment of dividend yield, franking credits, and income sustainability"
  }},
  "key_risks": ["specific risk 1", "specific risk 2", "specific risk 3"],
  "opportunities": ["specific opportunity 1", "specific opportunity 2"],
  "recommendations": ["actionable recommendation 1", "recommendation 2", "recommendation 3"]
}}

Reference specific ASX codes where relevant. Keep each item under 2 sentences."""

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1500,
            system="You are an expert Australian equities portfolio analyst. Return valid JSON only.",
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            parts = raw.split("```")
            raw = parts[1].lstrip("json").strip() if len(parts) > 1 else raw
    except Exception as e:
        log.error("Claude API error in portfolio-insights: %s", e)
        raise HTTPException(status_code=500, detail=f"AI generation failed: {e}")

    try:
        insights = json.loads(raw)
    except json.JSONDecodeError:
        log.error("Invalid JSON from Claude for portfolio-insights: %s", raw)
        raise HTTPException(status_code=500, detail="AI returned an unreadable response.")

    # ── Cache write (upsert) ──────────────────────────────────────────────────
    # Note: use CAST(x AS jsonb) / CAST(x AS uuid) — asyncpg doesn't support
    # the ::type shorthand in parameterised text() queries.
    now        = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=INSIGHTS_TTL_DAYS)
    try:
        await db.execute(text("""
            INSERT INTO users.portfolio_insights (
                portfolio_id, user_id, holdings_hash,
                total_value, total_cost, total_return_pct, annual_income,
                portfolio_yield, top3_concentration, num_holdings,
                sector_allocation_json, holdings_json, insights_json,
                generated_at, expires_at
            ) VALUES (
                CAST(:pid AS uuid), CAST(:uid AS uuid), :hash,
                :val, :cost, :ret_pct, :income,
                :yield_, :top3, :n_hold,
                CAST(:sector_json AS jsonb), CAST(:hold_json AS jsonb), CAST(:ins_json AS jsonb),
                :gen_at, :exp_at
            )
            ON CONFLICT (portfolio_id) DO UPDATE SET
                holdings_hash          = EXCLUDED.holdings_hash,
                total_value            = EXCLUDED.total_value,
                total_cost             = EXCLUDED.total_cost,
                total_return_pct       = EXCLUDED.total_return_pct,
                annual_income          = EXCLUDED.annual_income,
                portfolio_yield        = EXCLUDED.portfolio_yield,
                top3_concentration     = EXCLUDED.top3_concentration,
                num_holdings           = EXCLUDED.num_holdings,
                sector_allocation_json = EXCLUDED.sector_allocation_json,
                holdings_json          = EXCLUDED.holdings_json,
                insights_json          = EXCLUDED.insights_json,
                generated_at           = EXCLUDED.generated_at,
                expires_at             = EXCLUDED.expires_at
        """), {
            "pid":         portfolio_id,
            "uid":         current_user["id"],
            "hash":        h_hash,
            "val":         round(total_value, 2),
            "cost":        round(total_cost, 2),
            "ret_pct":     round(total_gl_pct, 2),
            "income":      round(total_income, 2),
            "yield_":      round(portfolio_yield, 2),
            "top3":        round(top3_weight, 1),
            "n_hold":      len(holdings_data),
            "sector_json": json.dumps(sector_alloc),
            "hold_json":   json.dumps(holdings_data),
            "ins_json":    json.dumps(insights),
            "gen_at":      now,
            "exp_at":      expires_at,
        })
        await db.commit()
        log.info("portfolio-insights cached for %s (expires %s)", portfolio_id, expires_at.date())
    except Exception as e:
        log.error("Failed to cache portfolio-insights for %s: %s", portfolio_id, e)
        await db.rollback()

    return {
        "portfolio_id":       portfolio_id,
        "portfolio_name":     p["name"],
        "total_value":        round(total_value, 2),
        "total_return_pct":   round(total_gl_pct, 2),
        "portfolio_yield":    round(portfolio_yield, 2),
        "annual_income":      round(total_income, 2),
        "num_holdings":       len(holdings_data),
        "top3_concentration": round(top3_weight, 1),
        "sector_allocation":  sector_alloc,
        "holdings":           holdings_data,
        "insights":           insights,
        "cached":             False,
        "generated_at":       now.isoformat(),
        "expires_at":         expires_at.isoformat(),
    }


# ── v1.4: Market-wide Anomaly Feed ───────────────────────────────────────────

@router.get("/anomalies")
async def list_market_anomalies(
    limit: int = 50,
    flag_type: str | None = None,
    severity: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Return recent market-wide anomaly flags, sorted by severity then recency."""
    where_parts = ["a.is_active = TRUE"]
    params: dict = {"limit": min(limit, 200)}
    if flag_type:
        where_parts.append("a.flag_type = :flag_type")
        params["flag_type"] = flag_type
    if severity:
        where_parts.append("a.severity = :severity")
        params["severity"] = severity

    where = " AND ".join(where_parts)
    rows = (await db.execute(text(f"""
        SELECT a.asx_code, a.flag_type, a.description, a.severity, a.detected_at,
               u.company_name, u.sector,
               u.price, u.return_1w, u.volume
        FROM market.anomalies a
        LEFT JOIN screener.universe u ON u.asx_code = a.asx_code
        WHERE {where}
        ORDER BY
            CASE a.severity WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
            a.detected_at DESC
        LIMIT :limit
    """), params)).mappings().all()

    flags = []
    for r in rows:
        f = dict(r)
        if f.get("detected_at"):
            f["detected_at"] = f["detected_at"].isoformat()
        for k in ("price", "return_1w"):
            if f.get(k) is not None:
                f[k] = float(f[k])
        f["return_1d"] = None  # not available in screener.universe
        flags.append(f)

    return {"flags": flags, "total": len(flags)}


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
