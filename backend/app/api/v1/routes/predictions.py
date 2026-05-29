"""
ASX Price Predictions — Admin-only API
=======================================
Endpoints:
  POST /predictions/trigger       — Start a prediction run (background task)
  GET  /predictions/status        — Job status / last-run info
  GET  /predictions/latest        — All predictions for the most recent run
  GET  /predictions/dates         — Available prediction dates
  GET  /predictions/{code}        — All models × horizons for a single stock

All endpoints require admin access.
"""
import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_admin
from app.db.session import get_db, AsyncSessionLocal

log    = logging.getLogger(__name__)
router = APIRouter()

# ── In-process job state (single-process uvicorn) ────────────────────────────
_job: dict = {
    "running":       False,
    "started_at":    None,
    "completed_at":  None,
    "stocks_done":   0,
    "total_stocks":  0,
    "last_summary":  None,
    "error":         None,
}


# ── Background task wrapper ───────────────────────────────────────────────────

async def _bg_run(force: bool, top_n: int):
    from compute.engine.price_predictions import run_predictions_async

    _job["running"]      = True
    _job["started_at"]   = datetime.now(timezone.utc).isoformat()
    _job["stocks_done"]  = 0
    _job["total_stocks"] = 0
    _job["error"]        = None
    _job["last_summary"] = None

    try:
        async with AsyncSessionLocal() as db:
            summary = await run_predictions_async(db, top_n=top_n, force=force, job_state=_job)
        _job["last_summary"]  = summary
        _job["completed_at"]  = datetime.now(timezone.utc).isoformat()
    except Exception as exc:
        log.error("Prediction background task failed: %s", exc, exc_info=True)
        _job["error"]        = str(exc)
        _job["completed_at"] = datetime.now(timezone.utc).isoformat()
    finally:
        _job["running"] = False


# ══════════════════════════════════════════════════════════════════════════════
# Endpoints
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/trigger")
async def trigger_predictions(
    background_tasks: BackgroundTasks,
    force:  bool = Query(False, description="Re-run even if today's predictions exist"),
    top_n:  int  = Query(1000,  ge=10, le=2000, description="Number of stocks to predict"),
    _admin       = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Start an ML prediction run as a background task."""
    from datetime import date as _date
    if _job["running"]:
        raise HTTPException(status_code=409, detail="A prediction job is already running")

    # Pre-check: block same-day re-run before the background task even starts
    if not force:
        try:
            row = await db.execute(
                text("SELECT COUNT(*) FROM market.price_predictions "
                     "WHERE prediction_date = :d AND model = 'ensemble'"),
                {"d": _date.today()},
            )
            count = row.scalar() or 0
            if count > 0:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"Today's predictions already ran ({count} stocks). "
                        "Pass force=true to overwrite."
                    ),
                )
        except HTTPException:
            raise
        except Exception:
            await db.rollback()
            # Table doesn't exist yet on first ever run — let the job create it

    background_tasks.add_task(_bg_run, force=force, top_n=top_n)
    return {
        "message":  f"Prediction job started for top {top_n} stocks",
        "top_n":    top_n,
        "force":    force,
    }


@router.get("/status")
async def prediction_status(_admin = Depends(require_admin)):
    """Return current job state and last-run summary."""
    return {
        "running":       _job["running"],
        "started_at":    _job["started_at"],
        "completed_at":  _job["completed_at"],
        "stocks_done":   _job["stocks_done"],
        "total_stocks":  _job["total_stocks"],
        "progress_pct":  round(
            _job["stocks_done"] / max(_job["total_stocks"], 1) * 100, 1
        ),
        "last_summary":  _job["last_summary"],
        "error":         _job["error"],
    }


@router.get("/latest")
async def latest_predictions(
    model:     str           = Query("ensemble", description="xgboost|rf|svm|lstm|ensemble"),
    horizon:   int           = Query(10,         description="5|10|20|30|50"),
    direction: str           = Query("",         description="bullish|neutral|bearish"),
    sector:    str           = Query(""),
    search:    str           = Query(""),
    limit:     int           = Query(100, ge=1, le=500),
    offset:    int           = Query(0,   ge=0),
    _admin                   = Depends(require_admin),
    db: AsyncSession         = Depends(get_db),
):
    """Paginated predictions for the most recent run date."""

    _empty = {
        "prediction_date": None, "model": model, "horizon_days": horizon,
        "total": 0, "direction_summary": {}, "results": [],
    }

    # Get latest prediction date — table may not exist yet before first run
    try:
        date_r = await db.execute(
            text("SELECT MAX(prediction_date) FROM market.price_predictions")
        )
        latest_date = date_r.scalar()
    except Exception:
        await db.rollback()
        return _empty   # table doesn't exist yet — return empty, not error

    if not latest_date:
        return _empty   # no runs yet

    # Direction, sector, search filters
    extra = ""
    params: dict = {
        "dt": latest_date, "model": model, "horizon": horizon,
        "lim": limit, "off": offset,
    }
    if direction:
        extra += " AND p.direction = :direction"
        params["direction"] = direction
    if sector:
        extra += " AND u.sector = :sector"
        params["sector"] = sector
    if search:
        extra += " AND (p.asx_code ILIKE :q OR c.company_name ILIKE :q)"
        params["q"] = f"%{search}%"

    sql = f"""
        SELECT
            p.asx_code,
            c.company_name,
            u.sector,
            p.horizon_days,
            p.model,
            p.current_price,
            p.predicted_price,
            p.predicted_change_pct,
            p.lower_bound,
            p.upper_bound,
            p.direction,
            p.confidence_score,
            p.r2_score,
            p.data_points
        FROM market.price_predictions p
        JOIN market.companies c ON c.asx_code = p.asx_code
        LEFT JOIN screener.universe u ON u.asx_code = p.asx_code
        WHERE p.prediction_date = :dt
          AND p.model            = :model
          AND p.horizon_days     = :horizon
          {extra}
        ORDER BY p.predicted_change_pct DESC NULLS LAST
        LIMIT :lim OFFSET :off
    """

    count_sql = f"""
        SELECT COUNT(*)
        FROM market.price_predictions p
        JOIN market.companies c ON c.asx_code = p.asx_code
        LEFT JOIN screener.universe u ON u.asx_code = p.asx_code
        WHERE p.prediction_date = :dt
          AND p.model            = :model
          AND p.horizon_days     = :horizon
          {extra}
    """

    rows_r  = await db.execute(text(sql),       params)
    count_r = await db.execute(text(count_sql),
                               {k: v for k, v in params.items() if k not in ("lim", "off")})

    rows  = rows_r.fetchall()
    total = count_r.scalar() or 0

    # Direction summary for this date/model/horizon
    sum_r = await db.execute(text("""
        SELECT direction, COUNT(*) AS cnt
        FROM market.price_predictions
        WHERE prediction_date = :dt AND model = :model AND horizon_days = :horizon
        GROUP BY direction
    """), {"dt": latest_date, "model": model, "horizon": horizon})
    direction_summary = {r.direction: r.cnt for r in sum_r.fetchall()}

    return {
        "prediction_date":    str(latest_date),
        "model":              model,
        "horizon_days":       horizon,
        "total":              total,
        "direction_summary":  direction_summary,
        "results": [
            {
                "asx_code":             r.asx_code,
                "company_name":         r.company_name,
                "sector":               r.sector,
                "current_price":        float(r.current_price) if r.current_price else None,
                "predicted_price":      float(r.predicted_price) if r.predicted_price else None,
                "predicted_change_pct": float(r.predicted_change_pct) if r.predicted_change_pct else None,
                "lower_bound":          float(r.lower_bound) if r.lower_bound else None,
                "upper_bound":          float(r.upper_bound) if r.upper_bound else None,
                "direction":            r.direction,
                "confidence_score":     float(r.confidence_score) if r.confidence_score else None,
                "r2_score":             float(r.r2_score) if r.r2_score else None,
                "data_points":          r.data_points,
            }
            for r in rows
        ],
    }


@router.get("/dates")
async def prediction_dates(
    _admin       = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """List all available prediction dates."""
    try:
        r = await db.execute(text("""
            SELECT prediction_date, COUNT(DISTINCT asx_code) AS stocks
            FROM market.price_predictions
            WHERE model = 'ensemble'
            GROUP BY prediction_date
            ORDER BY prediction_date DESC
            LIMIT 30
        """))
        return [{"date": str(row.prediction_date), "stocks": row.stocks} for row in r.fetchall()]
    except Exception:
        await db.rollback()
        return []


@router.get("/history/{code}")
async def stock_prediction_history(
    code:        str,
    days:        int  = Query(30, ge=1, le=60, description="How many days back to retrieve"),
    model:       str  = Query("ensemble", description="xgboost|rf|svm|lstm|ensemble"),
    _admin       = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Historical predictions for one stock over the last N days (max 60).
    Returns a time-series suitable for charting: one row per prediction_date,
    columns for each horizon (5/10/20/30/50d predicted_change_pct).
    Also returns the current_price on each date so you can overlay actuals later.
    """
    from datetime import date, timedelta

    code = code.upper().strip()
    since = date.today() - timedelta(days=days)

    # Company name
    name_r = await db.execute(
        text("SELECT company_name FROM market.companies WHERE asx_code = :c"),
        {"c": code},
    )
    name_row = name_r.fetchone()
    if not name_row:
        raise HTTPException(status_code=404, detail=f"Company {code} not found")

    try:
        r = await db.execute(text("""
            SELECT
                prediction_date,
                horizon_days,
                current_price,
                predicted_price,
                predicted_change_pct,
                direction,
                confidence_score
            FROM market.price_predictions
            WHERE asx_code   = :c
              AND model       = :m
              AND prediction_date >= :since
            ORDER BY prediction_date ASC, horizon_days ASC
        """), {"c": code, "m": model, "since": since})
        rows = r.fetchall()
    except Exception:
        await db.rollback()
        return {
            "asx_code": code, "company_name": name_row.company_name,
            "model": model, "days": days, "series": [], "dates": [],
        }

    if not rows:
        return {
            "asx_code": code, "company_name": name_row.company_name,
            "model": model, "days": days, "series": [], "dates": [],
        }

    # Build: {date_str: {horizon: pct, ...}}
    by_date: dict = {}
    for row in rows:
        ds = str(row.prediction_date)
        if ds not in by_date:
            by_date[ds] = {"current_price": float(row.current_price) if row.current_price else None}
        h = row.horizon_days
        by_date[ds][f"h{h}"] = round(float(row.predicted_change_pct), 4) if row.predicted_change_pct is not None else None
        by_date[ds][f"h{h}_dir"] = row.direction

    # Flat list sorted by date
    series = [
        {"date": ds, **vals}
        for ds, vals in sorted(by_date.items())
    ]

    return {
        "asx_code":    code,
        "company_name": name_row.company_name,
        "model":       model,
        "days":        days,
        "horizons":    [5, 10, 20, 30, 50],
        "series":      series,
    }


@router.get("/features/{code}")
async def stock_features(
    code: str,
    _admin       = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Return the latest feature vector used to generate predictions for a stock.
    Includes 13–15 technical indicators plus model/training metadata.
    """
    import numpy as np
    from compute.engine.price_predictions import compute_features

    code = code.upper().strip()

    # Company info
    name_r = await db.execute(
        text("SELECT company_name FROM market.companies WHERE asx_code = :c"),
        {"c": code},
    )
    name_row = name_r.fetchone()
    if not name_row:
        raise HTTPException(status_code=404, detail=f"Company {code} not found")

    # Fetch last 100 days of OHLCV
    try:
        pr = await db.execute(text("""
            SELECT close, high, low, volume, time
            FROM market.daily_prices
            WHERE asx_code = :c
            ORDER BY time DESC LIMIT 100
        """), {"c": code})
        rows = list(reversed(pr.fetchall()))
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Failed to fetch price data")

    if len(rows) < 60:
        raise HTTPException(
            status_code=404,
            detail=f"Insufficient price history for {code} ({len(rows)} days; need 60+)"
        )

    closes  = np.array([float(r.close  or 0) for r in rows])
    highs   = np.array([float(r.high   or 0) for r in rows])
    lows    = np.array([float(r.low    or 0) for r in rows])
    volumes = np.array([float(r.volume or 0) for r in rows])

    feat = compute_features(closes, highs, lows, volumes)   # (N, F)

    # Last row with no NaNs = the inference row
    valid = ~np.any(np.isnan(feat), axis=1)
    if not valid.any():
        raise HTTPException(
            status_code=404, detail=f"Could not compute valid features for {code}"
        )
    last_i = int(np.where(valid)[0][-1])
    f = feat[last_i]
    n_feats = feat.shape[1]

    # Feature key list (matches compute_features column order)
    keys = ["ret_1d", "ret_5d", "ret_10d", "ret_20d", "ret_60d",
            "sma_r10", "sma_r20", "sma_r50",
            "rsi_14", "vol_20d", "bb_pct", "range_20d"]
    if n_feats >= 13:
        keys.append("atr_r14")
    if n_feats >= 14:
        keys.append("vol_ratio")

    _META = {
        "ret_1d":    {"label": "1d Return",           "group": "Momentum",    "unit": "%",  "fmt": "pct",   "desc": "Yesterday's close-to-close % change"},
        "ret_5d":    {"label": "5d Return",            "group": "Momentum",    "unit": "%",  "fmt": "pct",   "desc": "5 trading-day cumulative return"},
        "ret_10d":   {"label": "10d Return",           "group": "Momentum",    "unit": "%",  "fmt": "pct",   "desc": "10 trading-day cumulative return"},
        "ret_20d":   {"label": "20d Return",           "group": "Momentum",    "unit": "%",  "fmt": "pct",   "desc": "20 trading-day cumulative return"},
        "ret_60d":   {"label": "60d Return",           "group": "Momentum",    "unit": "%",  "fmt": "pct",   "desc": "60 trading-day cumulative return (~3 months)"},
        "sma_r10":   {"label": "Price vs SMA-10",      "group": "Trend",       "unit": "%",  "fmt": "pct",   "desc": "How far price is above/below 10-day moving average"},
        "sma_r20":   {"label": "Price vs SMA-20",      "group": "Trend",       "unit": "%",  "fmt": "pct",   "desc": "How far price is above/below 20-day moving average"},
        "sma_r50":   {"label": "Price vs SMA-50",      "group": "Trend",       "unit": "%",  "fmt": "pct",   "desc": "How far price is above/below 50-day moving average"},
        "rsi_14":    {"label": "RSI (14)",              "group": "Oscillator",  "unit": "",   "fmt": "0-1",   "desc": "Relative Strength Index normalised 0–1 (>0.7 overbought, <0.3 oversold)"},
        "vol_20d":   {"label": "20d Volatility",        "group": "Risk",        "unit": "",   "fmt": "float", "desc": "Rolling 20-day std deviation of daily returns"},
        "bb_pct":    {"label": "Bollinger %B",          "group": "Oscillator",  "unit": "",   "fmt": "0-1",   "desc": "Position within Bollinger Bands (0=lower band, 1=upper band)"},
        "range_20d": {"label": "20d Range Position",    "group": "Oscillator",  "unit": "",   "fmt": "0-1",   "desc": "Where current price sits in the 20-day high-low range"},
        "atr_r14":   {"label": "ATR/Price Ratio",       "group": "Risk",        "unit": "%",  "fmt": "pct",   "desc": "14-day Average True Range as % of price (proxy for intraday volatility)"},
        "vol_ratio": {"label": "Volume Ratio",          "group": "Volume",      "unit": "×",  "fmt": "float", "desc": "Today's volume divided by 20-day average volume"},
    }

    features = []
    for i, key in enumerate(keys):
        if i >= len(f):
            break
        raw = float(f[i])
        meta = _META.get(key, {"label": key, "group": "Other", "unit": "", "fmt": "float", "desc": ""})
        # Convert to human-readable units
        if meta["fmt"] == "pct":
            display = round(raw * 100, 3)   # ratio → %
        elif meta["fmt"] == "0-1":
            display = round(raw, 4)
        else:
            display = round(raw, 4)
        features.append({
            "key":    key,
            "label":  meta["label"],
            "group":  meta["group"],
            "unit":   meta["unit"],
            "fmt":    meta["fmt"],
            "value":  display,
            "desc":   meta["desc"],
        })

    # Safe date extraction
    try:
        as_of_row = rows[last_i]
        as_of = str(as_of_row.time)[:10]
    except Exception:
        as_of = "unknown"

    return {
        "asx_code":      code,
        "company_name":  name_row.company_name,
        "current_price": round(float(closes[-1]), 4),
        "as_of_date":    as_of,
        "n_features":    n_feats,
        "data_points":   len(rows),
        "features":      features,
        "model_info": {
            "training_window": "260 trading days (~1 year of history)",
            "min_rows":        100,
            "horizons":        [5, 10, 20, 30, 50],
            "models": [
                {
                    "key":   "xgboost",
                    "label": "XGBoost",
                    "color": "orange",
                    "desc":  "Gradient boosting regressor — 150 trees, max depth 4, learning rate 0.05",
                },
                {
                    "key":   "rf",
                    "label": "Random Forest",
                    "color": "emerald",
                    "desc":  "100 decision trees, each trained on a random feature subset",
                },
                {
                    "key":   "svm",
                    "label": "SVM",
                    "color": "purple",
                    "desc":  "Support Vector Classifier predicting direction (bullish / neutral / bearish)",
                },
                {
                    "key":   "lstm",
                    "label": "LSTM",
                    "color": "blue",
                    "desc":  "PyTorch LSTM with 32 hidden units, 20-day sequence, Monte-Carlo dropout — top 200 stocks only",
                },
                {
                    "key":   "ensemble",
                    "label": "Ensemble",
                    "color": "indigo",
                    "desc":  "Confidence-weighted average of XGBoost + RF + SVM (+ LSTM where available)",
                },
            ],
        },
    }


@router.get("/{code}")
async def stock_predictions(
    code:        str,
    _admin       = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """All models × all horizons for a single stock (most recent prediction date)."""
    code = code.upper().strip()

    date_r = await db.execute(
        text("SELECT MAX(prediction_date) FROM market.price_predictions WHERE asx_code = :c"),
        {"c": code},
    )
    latest_date = date_r.scalar()
    if not latest_date:
        raise HTTPException(status_code=404, detail=f"No predictions found for {code}")

    r = await db.execute(text("""
        SELECT model, horizon_days,
               current_price, predicted_price,
               predicted_change_pct, lower_bound, upper_bound,
               direction, confidence_score, r2_score
        FROM market.price_predictions
        WHERE asx_code = :c AND prediction_date = :d
        ORDER BY model, horizon_days
    """), {"c": code, "d": latest_date})

    rows = r.fetchall()

    # Pivot: {model: {horizon: {...}}}
    by_model: dict = {}
    for row in rows:
        m = row.model
        h = row.horizon_days
        if m not in by_model:
            by_model[m] = {}
        by_model[m][h] = {
            "predicted_change_pct": float(row.predicted_change_pct) if row.predicted_change_pct else None,
            "predicted_price":      float(row.predicted_price)      if row.predicted_price      else None,
            "lower_bound":          float(row.lower_bound)          if row.lower_bound          else None,
            "upper_bound":          float(row.upper_bound)          if row.upper_bound          else None,
            "direction":            row.direction,
            "confidence_score":     float(row.confidence_score)     if row.confidence_score     else None,
            "r2_score":             float(row.r2_score)             if row.r2_score             else None,
        }

    name_r = await db.execute(
        text("SELECT company_name FROM market.companies WHERE asx_code = :c"), {"c": code}
    )
    name_row = name_r.fetchone()

    return {
        "asx_code":        code,
        "company_name":    name_row.company_name if name_row else code,
        "prediction_date": str(latest_date),
        "horizons":        sorted(HORIZONS_LIST),
        "by_model":        by_model,
        "current_price":   float(rows[0].current_price) if rows else None,
    }


# Import horizons list for stock detail response
HORIZONS_LIST = [5, 10, 20, 30, 50]
