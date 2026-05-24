"""
ASX Screener — AlphaFive Strategy API
=======================================
Endpoints:
  GET /api/v1/top5/current   — latest week's top-5 picks
  GET /api/v1/top5/history   — last N weeks of picks (grouped by week)
"""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.core.deps import require_plan
from app.db.session import get_db

router = APIRouter()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _f(v) -> Optional[float]:
    return float(v) if v is not None else None

def _i(v) -> Optional[int]:
    return int(v) if v is not None else None

def _row_to_dict(r) -> dict:
    return {
        "rank":             _i(r["rank"]),
        "asx_code":         r["asx_code"],
        "company_name":     r["company_name"],
        "sector":           r["sector"],
        "industry":         r["industry"],
        "composite_score":  _f(r["composite_score"]),
        "momentum_score":   _f(r["momentum_score"]),
        "quality_score":    _f(r["quality_score"]),
        "value_score":      _f(r["value_score"]),
        "income_score":     _f(r["income_score"]),
        "growth_score":     _f(r["growth_score"]),
        "price":            _f(r["price"]),
        "market_cap":       _f(r["market_cap"]),
        "pe_ratio":         _f(r["pe_ratio"]),
        "dividend_yield":   _f(r["dividend_yield"]),
        "grossed_up_yield": _f(r["grossed_up_yield"]),
        "franking_pct":     _f(r["franking_pct"]),
        "return_3m":        _f(r["return_3m"]),
        "return_1y":        _f(r["return_1y"]),
        "roe":              _f(r["roe"]),
        "piotroski_f_score":_i(r["piotroski_f_score"]),
        "computed_at":      r["computed_at"].isoformat() if r["computed_at"] else None,
    }


# ── GET /top5/current ─────────────────────────────────────────────────────────

@router.get("/current")
async def get_current_picks(
    _user: dict = Depends(require_plan("premium")),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns the most recent weekly top-5 picks (AlphaFive).
    Falls back to the latest available week if current week has no data yet.
    """
    result = await db.execute(text("""
        SELECT *
        FROM strategy.monthly_picks
        WHERE is_active = TRUE
        ORDER BY rank
    """))
    rows = result.mappings().all()

    if not rows:
        return {"pick_week": None, "picks": [], "total_weeks": 0}

    result2 = await db.execute(text(
        "SELECT COUNT(DISTINCT pick_month) AS n FROM strategy.monthly_picks"
    ))
    total_weeks = (result2.scalar() or 0)

    return {
        "pick_week":   rows[0]["pick_month"].isoformat(),
        "picks":       [_row_to_dict(r) for r in rows],
        "total_weeks": total_weeks,
    }


# ── GET /top5/history ─────────────────────────────────────────────────────────

@router.get("/history")
async def get_pick_history(
    weeks: int = Query(default=12, ge=1, le=104),
    _user: dict = Depends(require_plan("premium")),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns the last `weeks` weekly cohorts of AlphaFive picks, newest first.
    Each cohort contains all picks for that week ordered by rank.
    """
    result = await db.execute(text("""
        SELECT *
        FROM strategy.monthly_picks
        WHERE pick_month >= (
            SELECT MAX(pick_month) - (:weeks - 1) * INTERVAL '1 week'
            FROM strategy.monthly_picks
        )
        ORDER BY pick_month DESC, rank
    """), {"weeks": weeks})
    rows = result.mappings().all()

    # Group by pick_month (which now stores the Monday of the week)
    cohorts: dict[str, list] = {}
    for r in rows:
        key = r["pick_month"].isoformat()
        if key not in cohorts:
            cohorts[key] = []
        cohorts[key].append(_row_to_dict(r))

    return {
        "history": [
            {"pick_week": k, "picks": v}
            for k, v in cohorts.items()
        ]
    }
