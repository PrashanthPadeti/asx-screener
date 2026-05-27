"""
ASX Screener — Investment Research Tool
========================================
Admin-only endpoints powering the Research Assistant (3 modes).

POST /research/backtest  — Historical what-if: "$X in Stock A vs B from date"
POST /research/compare   — Side-by-side metric comparison (up to 6 stocks)
POST /research/ask       — AI Research Q&A (Claude, ASX-only, no buy/sell advice)

All endpoints require admin access via require_admin dependency.
"""
import re
import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import require_admin
from app.db.session import get_db

log    = logging.getLogger(__name__)
router = APIRouter()

# Australian corporate tax rate (for franking credit grossing-up)
_TAX_RATE = 0.30

# Common English words to exclude from ASX code detection
_ENGLISH_WORDS = {
    'THE', 'AND', 'FOR', 'ARE', 'BUT', 'NOT', 'YOU', 'ALL', 'CAN',
    'HAS', 'HER', 'WAS', 'ONE', 'OUR', 'OUT', 'DAY', 'GET', 'HOW',
    'ITS', 'NEW', 'NOW', 'OLD', 'SEE', 'TWO', 'WAY', 'WHO', 'DID',
    'LET', 'PUT', 'SAY', 'SHE', 'TOO', 'USE', 'OF', 'IN', 'TO',
    'AS', 'AT', 'BE', 'DO', 'GO', 'IF', 'IS', 'IT', 'ME', 'MY',
    'NO', 'ON', 'OR', 'SO', 'UP', 'US', 'WE', 'WOULD', 'COULD',
    'SHOULD', 'HAVE', 'BEEN', 'FROM', 'THEY', 'WILL', 'WITH', 'THIS',
    'THAT', 'THEIR', 'WHAT', 'WHEN', 'WHERE', 'WHICH', 'WHILE',
    'YIELD', 'RATE', 'RETURN', 'HIGH', 'LOW', 'BEST', 'MORE', 'LESS',
    'MOST', 'LAST', 'YEAR', 'OVER', 'BOTH', 'ALSO', 'EACH', 'MUCH',
    'SUCH', 'INTO', 'DOES', 'GIVE', 'JUST', 'THAN', 'THEM', 'THEN',
    'WELL', 'WERE', 'YOUR', 'STOCK', 'SHARE', 'PRICE', 'FUND', 'BANK',
    'MINE', 'GOLD', 'COAL', 'IRON', 'DATA', 'TELL', 'SHOW', 'WANT',
    'LIKE', 'GOOD', 'MAKE', 'TOOK', 'FROM', 'SOME', 'ONLY', 'COME',
    'THAN', 'BEEN', 'CALL', 'DOWN', 'LOOK', 'FIND', 'HERE', 'GIVE',
    'LIVE', 'MEAN', 'PLAN', 'KNOW', 'NEED', 'GROW', 'EARN', 'REAL',
    'RISK', 'SALE', 'SELL', 'HOLD', 'LONG', 'NEXT', 'SAME', 'TIME',
    'CASH', 'DEBT', 'LOSS', 'GAIN', 'FULL', 'HALF', 'PAST', 'ONCE',
    'FIVE', 'FOUR', 'NINE', 'ZERO', 'VERY', 'MUCH', 'ALSO', 'EVEN',
}


# ── Schemas ───────────────────────────────────────────────────────────────────

class BacktestRequest(BaseModel):
    codes:             list[str] = Field(..., min_length=1, max_length=4)
    amount:            float     = Field(10_000.0, ge=100.0, le=10_000_000.0)
    start_date:        Optional[date] = None   # None → 5 years ago
    end_date:          Optional[date] = None   # None → today
    include_dividends: bool = True


class CompareRequest(BaseModel):
    codes: list[str] = Field(..., min_length=2, max_length=6)


class AskRequest(BaseModel):
    question: str
    history:  list[dict] = []      # [{role, content}] for multi-turn context


# ── Helpers ───────────────────────────────────────────────────────────────────

def _cagr(end_val: float, start_val: float, years: float) -> Optional[float]:
    if start_val <= 0 or years <= 0 or end_val <= 0:
        return None
    return ((end_val / start_val) ** (1 / years) - 1) * 100


# ── Mode 1: Historical Backtester ────────────────────────────────────────────

@router.post("/backtest")
async def backtest(
    body: BacktestRequest,
    _admin: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Compare how $X invested in multiple ASX stocks would have performed
    over a given period, including dividends and franking credits.
    Uses unadjusted close price + separate dividend accumulation.
    """
    today    = date.today()
    end_dt   = body.end_date   or today
    start_dt = body.start_date or date(today.year - 5, today.month, today.day)

    if start_dt >= end_dt:
        raise HTTPException(status_code=400, detail="start_date must be before end_date")
    if start_dt < date(2000, 1, 1):
        raise HTTPException(status_code=400, detail="start_date cannot be before 2000-01-01")

    codes      = [c.upper().strip() for c in body.codes]
    years_held = (end_dt - start_dt).days / 365.25

    results = []

    for code in codes:
        try:
            # ── Company name ──────────────────────────────────────────
            name_r = await db.execute(
                text("SELECT company_name FROM market.companies WHERE asx_code = :c"),
                {"c": code},
            )
            name_row = name_r.fetchone()
            if not name_row:
                results.append({"code": code, "error": "Company not found"})
                continue

            # ── Buy price: first close on/after start_date ────────────
            # Pass Python date objects directly — asyncpg requires them (calls .toordinal())
            buy_r = await db.execute(text("""
                SELECT time::date AS d, close
                FROM market.daily_prices
                WHERE asx_code = :c
                  AND time::date >= :sd
                ORDER BY time ASC LIMIT 1
            """), {"c": code, "sd": start_dt})
            buy_row = buy_r.fetchone()
            if not buy_row or not buy_row.close:
                results.append({"code": code, "error": "No price data found for start date"})
                continue
            buy_price      = float(buy_row.close)
            actual_buy_dt  = buy_row.d   # Python date object returned by asyncpg

            # ── Sell price: last close on/before end_date ─────────────
            sell_r = await db.execute(text("""
                SELECT time::date AS d, close
                FROM market.daily_prices
                WHERE asx_code = :c
                  AND time::date <= :ed
                ORDER BY time DESC LIMIT 1
            """), {"c": code, "ed": end_dt})
            sell_row = sell_r.fetchone()
            if not sell_row or not sell_row.close:
                results.append({"code": code, "error": "No price data found for end date"})
                continue
            sell_price      = float(sell_row.close)
            actual_sell_dt  = sell_row.d  # Python date object

            shares          = body.amount / buy_price
            price_end_value = shares * sell_price

            # ── Dividends & franking credits ──────────────────────────
            div_total      = 0.0
            franking_total = 0.0
            div_events     = []

            if body.include_dividends:
                div_r = await db.execute(text("""
                    SELECT ex_date, amount, franking_pct
                    FROM market.dividends
                    WHERE asx_code = :c
                      AND ex_date >= :sd
                      AND ex_date <= :ed
                      AND amount IS NOT NULL
                    ORDER BY ex_date
                """), {"c": code, "sd": actual_buy_dt, "ed": actual_sell_dt})
                for dr in div_r.fetchall():
                    d_amt   = float(dr.amount or 0)
                    f_pct   = float(dr.franking_pct or 0) / 100.0
                    cash    = d_amt * shares
                    frank   = cash * f_pct * (_TAX_RATE / (1 - _TAX_RATE))
                    div_total      += cash
                    franking_total += frank
                    div_events.append({
                        "ex_date":      dr.ex_date.isoformat(),   # str for chart comparison
                        "amount_ps":    round(d_amt, 6),
                        "franking_pct": round(f_pct * 100, 1),
                        "cash":         round(cash, 2),
                    })

            total_end_value  = price_end_value + div_total
            price_return_pct = (sell_price - buy_price) / buy_price * 100
            total_return_pct = (total_end_value - body.amount) / body.amount * 100

            # ── Monthly chart: last close per month (standard SQL, no TimescaleDB) ─
            chart_r = await db.execute(text("""
                SELECT DISTINCT ON (date_trunc('month', time))
                    date_trunc('month', time)::date AS month,
                    close
                FROM market.daily_prices
                WHERE asx_code = :c
                  AND time::date >= :sd
                  AND time::date <= :ed
                ORDER BY date_trunc('month', time), time DESC
            """), {"c": code, "sd": actual_buy_dt, "ed": actual_sell_dt})
            chart_rows = chart_r.fetchall()

            # Accumulate dividends per month point (ISO string comparison — lexicographic = chronologic)
            chart         = []
            running_divs  = 0.0
            div_idx       = 0
            for crow in chart_rows:
                month_str = crow.month.isoformat()
                while div_idx < len(div_events) and div_events[div_idx]["ex_date"] <= month_str:
                    running_divs += div_events[div_idx]["cash"]
                    div_idx += 1
                c_price = float(crow.close)
                chart.append({
                    "date":        month_str,
                    "price_value": round(shares * c_price, 2),
                    "total_value": round(shares * c_price + running_divs, 2),
                })

        except Exception as exc:
            log.error("Backtest error for %s: %s", code, exc, exc_info=True)
            raise HTTPException(status_code=500, detail=f"Error processing {code}: {exc}")

        results.append({
            "code":               code,
            "company_name":       name_row.company_name,
            "buy_price":          round(buy_price, 4),
            "sell_price":         round(sell_price, 4),
            "actual_start_date":  actual_buy_dt.isoformat(),
            "actual_end_date":    actual_sell_dt.isoformat(),
            "shares_purchased":   round(shares, 4),
            "invested":           body.amount,
            "price_end_value":    round(price_end_value, 2),
            "dividends_received": round(div_total, 2),
            "franking_credits":   round(franking_total, 2),
            "total_end_value":    round(total_end_value, 2),
            "price_return_pct":   round(price_return_pct, 2),
            "total_return_pct":   round(total_return_pct, 2),
            "cagr_price":         round(_cagr(price_end_value, body.amount, years_held) or 0, 2),
            "cagr_total":         round(_cagr(total_end_value, body.amount, years_held) or 0, 2),
            "div_events":         div_events,
            "chart":              chart,
        })

    return {
        "amount":      body.amount,
        "start_date":  start_dt.isoformat(),
        "end_date":    end_dt.isoformat(),
        "years_held":  round(years_held, 2),
        "results":     results,
    }


# ── Mode 2: Side-by-Side Comparator ──────────────────────────────────────────

_COMPARE_METRICS = [
    # (column,               label,                  format,   section,      higher_better)
    ("last_price",           "Last Price",           "price",  "Price",      None),
    ("price_change_pct",     "Day Change %",         "pct",    "Price",      True),
    ("market_cap",           "Market Cap (A$M)",     "number", "Price",      None),
    ("week_52_high",         "52W High",             "price",  "Price",      None),
    ("week_52_low",          "52W Low",              "price",  "Price",      None),
    ("pe_ratio",             "P/E Ratio",            "x",      "Valuation",  False),
    ("forward_pe",           "Forward P/E",          "x",      "Valuation",  False),
    ("price_to_book",        "Price / Book",         "x",      "Valuation",  False),
    ("price_to_sales",       "Price / Sales",        "x",      "Valuation",  False),
    ("ev_to_ebitda",         "EV / EBITDA",          "x",      "Valuation",  False),
    ("peg_ratio",            "PEG Ratio",            "x",      "Valuation",  False),
    ("revenue_growth_1y",    "Revenue Growth 1Y",    "pct",    "Growth",     True),
    ("earnings_growth_1y",   "Earnings Growth 1Y",   "pct",    "Growth",     True),
    ("eps_fy0",              "EPS (FY0)",            "dollar", "Growth",     True),
    ("eps_fy1",              "EPS (FY1 est.)",       "dollar", "Growth",     True),
    ("roe",                  "ROE",                  "pct",    "Quality",    True),
    ("roa",                  "ROA",                  "pct",    "Quality",    True),
    ("net_margin",           "Net Margin",           "pct",    "Quality",    True),
    ("gross_margin",         "Gross Margin",         "pct",    "Quality",    True),
    ("debt_to_equity",       "D/E Ratio",            "x",      "Quality",    False),
    ("current_ratio",        "Current Ratio",        "x",      "Quality",    True),
    ("piotroski_f_score",    "Piotroski F-Score",    "number", "Quality",    True),
    ("composite_score",      "Composite Score",      "number", "Quality",    True),
    ("dividend_yield",       "Dividend Yield",       "pct",    "Dividends",  True),
    ("grossed_up_yield",     "Grossed-Up Yield",     "pct",    "Dividends",  True),
    ("franking_pct",         "Franking %",           "number", "Dividends",  True),
    ("dps_ttm",              "DPS (TTM)",            "dollar", "Dividends",  True),
    ("return_1m",            "Return 1M",            "pct",    "Returns",    True),
    ("return_3m",            "Return 3M",            "pct",    "Returns",    True),
    ("return_6m",            "Return 6M",            "pct",    "Returns",    True),
    ("return_1y",            "Return 1Y",            "pct",    "Returns",    True),
    ("rsi_14",               "RSI (14)",             "number", "Technical",  None),
    ("short_pct",            "Short Interest %",     "pct",    "Technical",  False),
]

_COMPARE_COLS = ", ".join(m[0] for m in _COMPARE_METRICS)


@router.post("/compare")
async def compare(
    body: CompareRequest,
    _admin: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Side-by-side metric comparison for up to 6 ASX stocks."""
    codes = [c.upper().strip() for c in body.codes]

    result = await db.execute(text(f"""
        SELECT asx_code, company_name, sector,
               {_COMPARE_COLS}
        FROM market.screener_universe
        WHERE asx_code = ANY(:codes)
    """), {"codes": codes})
    rows = result.fetchall()

    if not rows:
        raise HTTPException(status_code=404, detail="No data found for given codes")

    stocks = {dict(r._mapping)["asx_code"]: dict(r._mapping) for r in rows}

    return {
        "codes":   [c for c in codes if c in stocks],
        "stocks":  stocks,
        "metrics": [
            {"col": m[0], "label": m[1], "format": m[2],
             "section": m[3], "higher_better": m[4]}
            for m in _COMPARE_METRICS
        ],
    }


# ── Mode 3: AI Research Q&A ───────────────────────────────────────────────────

_RESEARCH_SYSTEM = """\
You are an ASX Investment Research Assistant for ASX Screener, \
an Australian stock market analysis platform.

STRICT RULES
1. ONLY answer questions about:
   - ASX-listed stocks, companies, and Australian securities
   - Australian investment metrics, financial analysis, and stock screening
   - Historical performance, data comparisons, backtesting context
   - Financial education (what metrics mean, how to analyse stocks)
   - Australian market sectors, indices, and economic context

2. NEVER:
   - Make buy, sell, hold, or any investment recommendations
   - Predict or forecast future stock prices or returns
   - Give personalised financial advice tailored to anyone's situation
   - Discuss crypto, unlisted assets, international stocks (unless ASX cross-listed),
     property investment, or other non-ASX securities
   - Suggest specific portfolio weights or allocations

3. When asked for a recommendation, respond:
   "I can show you the relevant data and metrics, but I'm unable to make buy or \
sell recommendations. Here's what the data shows: [provide factual metrics]"

4. If asked about non-ASX topics, politely decline and redirect.

5. Be direct, clear, and data-focused. Use specific numbers from the context below.

6. Format with markdown. Use bullet points, bold labels, and headers where helpful.
   Keep responses concise — aim for 200-400 words unless the question requires more.

COMPANY DATA FOR THIS QUERY (use these numbers in your answer):
{context}

END EVERY RESPONSE WITH THIS EXACT BLOCK (on a new line, verbatim):
---
⚠️ **Not financial advice.** For analysis and educational purposes only. \
Past performance is not indicative of future returns. \
Always consult a licensed financial adviser (AFSL holder) before making investment decisions.\
"""


@router.post("/ask")
async def ask(
    body: AskRequest,
    _admin: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """AI-powered research Q&A — ASX-only, no buy/sell advice, mandatory disclaimer."""
    if not settings.ANTHROPIC_API_KEY:
        raise HTTPException(status_code=503, detail="AI features are not configured.")

    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")
    if len(question) > 2000:
        raise HTTPException(status_code=400, detail="Question too long (max 2 000 chars).")

    # Extract ASX-style codes mentioned in question (2–5 uppercase letters),
    # filtering out common English words that match the pattern
    raw_codes = re.findall(r'\b([A-Z]{2,5})\b', question.upper())
    mentioned = list(dict.fromkeys(c for c in raw_codes if c not in _ENGLISH_WORDS))[:6]

    # Fetch company context for mentioned codes
    context_parts: list[str] = []
    if mentioned:
        ctx_r = await db.execute(text("""
            SELECT
                asx_code, company_name, sector,
                last_price, market_cap, pe_ratio, forward_pe, price_to_book,
                dividend_yield, grossed_up_yield, franking_pct, dps_ttm,
                roe, roa, net_margin, gross_margin, debt_to_equity, current_ratio,
                revenue_growth_1y, earnings_growth_1y, eps_fy0, eps_fy1,
                return_1m, return_3m, return_6m, return_1y,
                rsi_14, composite_score, piotroski_f_score,
                week_52_high, week_52_low, short_pct
            FROM market.screener_universe
            WHERE asx_code = ANY(:codes)
        """), {"codes": mentioned})
        for row in ctx_r.fetchall():
            d = dict(row._mapping)
            def _v(k): return d.get(k)
            context_parts.append(
                f"**{d['asx_code']} — {d['company_name']}** | {d['sector']}\n"
                f"  Price: ${_v('last_price')}  |  Market Cap: ${_v('market_cap')}M  |  52W: ${_v('week_52_low')}–${_v('week_52_high')}\n"
                f"  P/E: {_v('pe_ratio')}x  |  Fwd P/E: {_v('forward_pe')}x  |  P/B: {_v('price_to_book')}x  |  ROE: {_v('roe')}%  |  Net Margin: {_v('net_margin')}%\n"
                f"  Div Yield: {_v('dividend_yield')}%  |  Grossed-Up: {_v('grossed_up_yield')}%  |  Franking: {_v('franking_pct')}%  |  DPS TTM: ${_v('dps_ttm')}\n"
                f"  D/E: {_v('debt_to_equity')}x  |  Current Ratio: {_v('current_ratio')}x  |  EPS FY0: ${_v('eps_fy0')}  |  EPS FY1: ${_v('eps_fy1')}\n"
                f"  Rev Growth 1Y: {_v('revenue_growth_1y')}%  |  Earnings Growth 1Y: {_v('earnings_growth_1y')}%\n"
                f"  Return 1M: {_v('return_1m')}%  |  3M: {_v('return_3m')}%  |  6M: {_v('return_6m')}%  |  1Y: {_v('return_1y')}%\n"
                f"  RSI(14): {_v('rsi_14')}  |  Composite Score: {_v('composite_score')}  |  Piotroski F: {_v('piotroski_f_score')}  |  Short%: {_v('short_pct')}%"
            )

    context = "\n\n".join(context_parts) if context_parts else "No specific company data matched. Answer using general knowledge about ASX markets."
    system  = _RESEARCH_SYSTEM.format(context=context)

    # Build message list (cap history at 10 turns to control tokens)
    messages: list[dict] = []
    for h in body.history[-10:]:
        if h.get("role") in ("user", "assistant") and h.get("content"):
            messages.append({"role": h["role"], "content": str(h["content"])})
    messages.append({"role": "user", "content": question})

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        resp = client.messages.create(
            model=settings.CLAUDE_MODEL,
            max_tokens=2048,
            system=system,
            messages=messages,
        )
        answer = resp.content[0].text.strip()
    except Exception as exc:
        log.error("Claude API error in research/ask: %s", exc)
        raise HTTPException(status_code=500, detail=f"AI service error: {exc}")

    return {
        "answer":     answer,
        "codes_used": [c for c in mentioned if any(d.get("asx_code") == c for d in [])],
        "context_codes": mentioned,
    }
