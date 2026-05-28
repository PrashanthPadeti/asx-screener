"""
ASX Price Prediction Engine
============================
4 ML models trained per stock on last 250 days of OHLCV data.

Models:
  1. XGBoost   — gradient boosting regression (all 1 000 stocks)
  2. Random Forest — ensemble regression (all 1 000 stocks)
  3. SVM        — classification: bullish / neutral / bearish (all 1 000 stocks)
  4. LSTM       — PyTorch sequence deep learning (top 200 stocks only)
  5. Ensemble   — confidence-weighted average of above models

Horizons:  5, 10, 20, 30, 50 trading days
Stored in: market.price_predictions (upserted daily)

DISCLAIMER: Statistical models only. Past performance is not indicative
of future returns. These are not investment recommendations.
"""
import asyncio
import logging
import warnings
from datetime import date
from typing import Optional

import numpy as np

warnings.filterwarnings("ignore")
log = logging.getLogger(__name__)

HORIZONS      = [5, 10, 20, 30, 50]
MIN_ROWS      = 100      # minimum trading days required
SEQ_LEN       = 20       # LSTM lookback window
LSTM_EPOCHS   = 20
BULLISH_THR   =  2.0     # % change above which = bullish
BEARISH_THR   = -2.0     # % change below which = bearish

# ── Optional imports (graceful degradation) ──────────────────────────────────

try:
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.multioutput import MultiOutputRegressor
    from sklearn.preprocessing import StandardScaler
    from sklearn.svm import SVC
    import xgboost as xgb
    SKLEARN_OK = True
except ImportError as _e:
    log.warning("scikit-learn / xgboost unavailable: %s", _e)
    SKLEARN_OK = False

try:
    import torch
    import torch.nn as nn
    TORCH_OK = True
except ImportError:
    log.warning("PyTorch unavailable — LSTM model disabled")
    TORCH_OK = False


# ══════════════════════════════════════════════════════════════════════════════
# Feature Engineering
# ══════════════════════════════════════════════════════════════════════════════

def _sma(a: np.ndarray, p: int) -> np.ndarray:
    out = np.full(len(a), np.nan)
    for i in range(p - 1, len(a)):
        out[i] = a[i - p + 1 : i + 1].mean()
    return out


def _rsi(closes: np.ndarray, p: int = 14) -> np.ndarray:
    out = np.full(len(closes), np.nan)
    d   = np.diff(closes)
    for i in range(p, len(closes)):
        w    = d[i - p : i]
        gain = w[w > 0].mean() if (w > 0).any() else 0.0
        loss = (-w[w < 0]).mean() if (w < 0).any() else 1e-9
        out[i] = 100 - 100 / (1 + gain / loss)
    return out / 100.0   # normalise 0–1


def compute_features(
    closes: np.ndarray,
    highs:  Optional[np.ndarray] = None,
    lows:   Optional[np.ndarray] = None,
    volumes: Optional[np.ndarray] = None,
) -> np.ndarray:
    """
    Returns (N, F) feature matrix.  All NaN rows are kept — caller must mask.
    Features (13–15 depending on optional inputs):
      ret_1d, ret_5d, ret_10d, ret_20d, ret_60d,
      sma_r10, sma_r20, sma_r50,
      rsi_14, vol_20d, bb_pct, range_20d,
      [atr_r14],   [vol_ratio]
    """
    n = len(closes)
    cols = []

    # ── Returns ──────────────────────────────────────────────────────────────
    ret1 = np.concatenate([[np.nan], np.diff(closes) / (closes[:-1] + 1e-8)])
    cols.append(ret1)

    for p in (5, 10, 20, 60):
        r = np.full(n, np.nan)
        for i in range(p, n):
            r[i] = (closes[i] - closes[i - p]) / (closes[i - p] + 1e-8)
        cols.append(r)

    # ── SMA ratios ────────────────────────────────────────────────────────────
    for p in (10, 20, 50):
        sma = _sma(closes, p)
        cols.append(np.where(sma > 0, closes / sma - 1, np.nan))

    # ── RSI ───────────────────────────────────────────────────────────────────
    cols.append(_rsi(closes, 14))

    # ── 20-day rolling volatility ─────────────────────────────────────────────
    vol20 = np.full(n, np.nan)
    for i in range(20, n):
        vol20[i] = np.std(ret1[i - 20 : i])
    cols.append(vol20)

    # ── Bollinger %B ──────────────────────────────────────────────────────────
    bbp = np.full(n, np.nan)
    for i in range(20, n):
        w = closes[i - 20 : i]
        mu, sigma = w.mean(), w.std()
        if sigma > 0:
            bbp[i] = (closes[i] - (mu - 2 * sigma)) / (4 * sigma)
    cols.append(bbp)

    # ── 20-day price range position ───────────────────────────────────────────
    rng = np.full(n, np.nan)
    for i in range(20, n):
        lo, hi = closes[i - 20 : i].min(), closes[i - 20 : i].max()
        if hi > lo:
            rng[i] = (closes[i] - lo) / (hi - lo)
    cols.append(rng)

    # ── ATR ratio (requires high/low) ─────────────────────────────────────────
    if highs is not None and lows is not None:
        tr = np.maximum(highs - lows,
             np.maximum(np.abs(highs - np.roll(closes, 1)),
                        np.abs(lows  - np.roll(closes, 1))))
        tr[0] = highs[0] - lows[0]
        atr = _sma(tr, 14)
        cols.append(np.where(closes > 0, atr / closes, np.nan))

    # ── Volume ratio ──────────────────────────────────────────────────────────
    if volumes is not None:
        vsma = _sma(volumes.astype(float), 20)
        cols.append(np.where(vsma > 0, volumes / vsma, 1.0))

    return np.column_stack(cols)   # (N, F)


def compute_targets(closes: np.ndarray) -> np.ndarray:
    """Forward % returns at each horizon.  (N, 5) — NaN for last H rows."""
    n   = len(closes)
    out = np.full((n, len(HORIZONS)), np.nan)
    for j, h in enumerate(HORIZONS):
        for i in range(n - h):
            out[i, j] = (closes[i + h] - closes[i]) / (closes[i] + 1e-8) * 100
    return out


# ══════════════════════════════════════════════════════════════════════════════
# LSTM  (PyTorch)
# ══════════════════════════════════════════════════════════════════════════════

if TORCH_OK:
    class _LSTM(nn.Module):
        def __init__(self, in_sz: int, hidden: int = 32, out_sz: int = 5):
            super().__init__()
            self.lstm = nn.LSTM(in_sz, hidden, num_layers=1,
                                batch_first=True, dropout=0.0)
            self.drop = nn.Dropout(0.15)
            self.fc   = nn.Linear(hidden, out_sz)

        def forward(self, x):
            out, _ = self.lstm(x)
            return self.fc(self.drop(out[:, -1, :]))


def _train_lstm(X: np.ndarray, y: np.ndarray) -> "_LSTM":
    """X: (N, SEQ_LEN, F)  y: (N, 5)  → trained model"""
    model = _LSTM(in_sz=X.shape[2])
    opt   = torch.optim.Adam(model.parameters(), lr=0.005, weight_decay=1e-4)
    loss_fn = nn.MSELoss()
    Xt = torch.FloatTensor(X)
    yt = torch.FloatTensor(y)
    for _ in range(LSTM_EPOCHS):
        model.train()
        opt.zero_grad()
        loss = loss_fn(model(Xt), yt)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step()
    return model


def _mc_predict(model, X_last: np.ndarray, n_mc: int = 20):
    """Monte-Carlo dropout → (mean, std) both shape (5,)"""
    model.train()   # keep dropout active
    Xt = torch.FloatTensor(X_last)
    with torch.no_grad():
        preds = [model(Xt).numpy()[0] for _ in range(n_mc)]
    p = np.array(preds)
    return p.mean(0), p.std(0)


# ══════════════════════════════════════════════════════════════════════════════
# Per-stock pipeline
# ══════════════════════════════════════════════════════════════════════════════

def _direction(pct: float) -> str:
    if pct > BULLISH_THR:  return "bullish"
    if pct < BEARISH_THR:  return "bearish"
    return "neutral"


def _price_bounds(current: float, pct: float, spread: float) -> tuple:
    lo = current * (1 + (pct - 1.5 * spread) / 100)
    hi = current * (1 + (pct + 1.5 * spread) / 100)
    return round(lo, 4), round(hi, 4)


def predict_stock(
    asx_code:      str,
    closes:        np.ndarray,
    highs:         Optional[np.ndarray] = None,
    lows:          Optional[np.ndarray] = None,
    volumes:       Optional[np.ndarray] = None,
    current_price: float = None,
    run_lstm:      bool  = False,
) -> list[dict]:
    """
    Train 4 models on historical OHLCV and return prediction dicts
    (one per model × horizon).  Pure CPU, safe to run in ThreadPoolExecutor.
    """
    if not SKLEARN_OK:
        return []

    n = len(closes)
    if n < MIN_ROWS:
        return []

    if current_price is None:
        current_price = float(closes[-1])

    today = date.today()

    feat = compute_features(closes, highs, lows, volumes)   # (N, F)
    tgts = compute_targets(closes)                          # (N, 5)

    feat_ok  = ~np.any(np.isnan(feat), axis=1)
    tgt_ok   = ~np.any(np.isnan(tgts), axis=1)
    train_mask = feat_ok & tgt_ok

    if train_mask.sum() < 50:
        return []

    X_tr = feat[train_mask]
    y_tr = tgts[train_mask]

    # Latest feature row for inference
    last_i = np.where(feat_ok)[0][-1]
    X_inf  = feat[last_i : last_i + 1]

    scaler   = StandardScaler()
    X_tr_s   = scaler.fit_transform(X_tr)
    X_inf_s  = scaler.transform(X_inf)

    preds = []

    def _rec(model_name, pct_arr, conf_arr, r2=None, spread_factor=1.2):
        vol_spread = float(np.std(y_tr)) * spread_factor
        for j, h in enumerate(HORIZONS):
            pct  = float(pct_arr[j])
            conf = float(np.clip(conf_arr[j] if hasattr(conf_arr, '__len__') else conf_arr, 0, 1))
            lo, hi = _price_bounds(current_price, pct, vol_spread)
            preds.append({
                "asx_code":             asx_code,
                "prediction_date":      today,
                "model":                model_name,
                "horizon_days":         h,
                "current_price":        round(current_price, 4),
                "predicted_price":      round(current_price * (1 + pct / 100), 4),
                "lower_bound":          lo,
                "upper_bound":          hi,
                "predicted_change_pct": round(pct, 4),
                "direction":            _direction(pct),
                "confidence_score":     round(conf, 4),
                "r2_score":             round(r2, 4) if r2 is not None else None,
                "data_points":          n,
            })

    def _r2(y_true, y_pred):
        ss_res = ((y_true - y_pred) ** 2).sum()
        ss_tot = ((y_true - y_true.mean()) ** 2).sum()
        return max(0.0, 1 - ss_res / (ss_tot + 1e-8))

    # ── 1. XGBoost ────────────────────────────────────────────────────────────
    try:
        xgb_m = MultiOutputRegressor(
            xgb.XGBRegressor(
                n_estimators=150, max_depth=4, learning_rate=0.05,
                subsample=0.8, colsample_bytree=0.8,
                random_state=42, verbosity=0, tree_method="hist",
            )
        )
        xgb_m.fit(X_tr_s, y_tr)
        xgb_pct = xgb_m.predict(X_inf_s)[0]
        r2_val  = _r2(y_tr, xgb_m.predict(X_tr_s))
        _rec("xgboost", xgb_pct, np.full(5, r2_val), r2=r2_val, spread_factor=1.2)
    except Exception as exc:
        log.debug("XGBoost failed %s: %s", asx_code, exc)

    # ── 2. Random Forest ──────────────────────────────────────────────────────
    try:
        rf_m = MultiOutputRegressor(
            RandomForestRegressor(
                n_estimators=150, max_depth=8, min_samples_leaf=5,
                random_state=42, n_jobs=1,
            )
        )
        rf_m.fit(X_tr_s, y_tr)
        rf_pct  = rf_m.predict(X_inf_s)[0]
        r2_val  = _r2(y_tr, rf_m.predict(X_tr_s))
        _rec("rf", rf_pct, np.full(5, r2_val), r2=r2_val, spread_factor=1.3)
    except Exception as exc:
        log.debug("RF failed %s: %s", asx_code, exc)

    # ── 3. SVM (classification per horizon) ───────────────────────────────────
    try:
        svm_pcts  = np.zeros(5)
        svm_confs = np.zeros(5)
        for j, h in enumerate(HORIZONS):
            y_cls = np.where(y_tr[:, j] > BULLISH_THR,  1,
                    np.where(y_tr[:, j] < BEARISH_THR, -1, 0))
            if len(np.unique(y_cls)) < 2:
                svm_pcts[j], svm_confs[j] = 0.0, 0.5
                continue
            svm = SVC(kernel="rbf", C=1.0, gamma="scale",
                      probability=True, random_state=42)
            svm.fit(X_tr_s, y_cls)
            proba  = svm.predict_proba(X_inf_s)[0]
            cls_   = svm.predict(X_inf_s)[0]
            cmap   = {c: p for c, p in zip(svm.classes_, proba)}
            conf   = float(max(proba))
            # Convert classification to rough % estimate
            if   cls_ ==  1: pct_est =  3.0 * conf
            elif cls_ == -1: pct_est = -3.0 * conf
            else:             pct_est = 0.5 * (cmap.get(1, 0) - cmap.get(-1, 0))
            svm_pcts[j], svm_confs[j] = pct_est, conf
        _rec("svm", svm_pcts, svm_confs, r2=None, spread_factor=1.5)
    except Exception as exc:
        log.debug("SVM failed %s: %s", asx_code, exc)

    # ── 4. LSTM ───────────────────────────────────────────────────────────────
    if run_lstm and TORCH_OK:
        try:
            valid_idx = np.where(feat_ok)[0]
            seqs, seq_y = [], []
            for k in range(SEQ_LEN, len(valid_idx)):
                end = valid_idx[k]
                seg = feat[end - SEQ_LEN : end]
                if np.any(np.isnan(seg)) or np.any(np.isnan(tgts[end])):
                    continue
                seqs.append(seg)
                seq_y.append(tgts[end])
            if len(seqs) < 30:
                raise ValueError("too few sequences")

            Xs = np.array(seqs,  dtype=np.float32)   # (N, 20, F)
            ys = np.array(seq_y, dtype=np.float32)   # (N, 5)

            # Normalise
            fm  = Xs.mean((0, 1));  fs  = Xs.std((0, 1)) + 1e-8
            ym  = ys.mean(0);       ys_ = ys.std(0) + 1e-8
            Xn  = (Xs - fm) / fs
            yn  = (ys - ym) / ys_

            model = _train_lstm(Xn, yn)

            last_seq = feat[valid_idx[-SEQ_LEN] : valid_idx[-1] + 1]
            if len(last_seq) < SEQ_LEN:
                last_seq = feat[feat_ok][-SEQ_LEN:]
            last_seq_n = ((last_seq - fm) / fs).astype(np.float32)

            mean_, std_ = _mc_predict(model, last_seq_n[np.newaxis])
            lstm_pcts   = mean_ * ys_ + ym          # de-normalise
            lstm_confs  = np.clip(1.0 / (1.0 + std_), 0, 1)

            _rec("lstm", lstm_pcts, lstm_confs, r2=None,
                 spread_factor=float(1.0 + std_.mean()))
        except Exception as exc:
            log.debug("LSTM failed %s: %s", asx_code, exc)

    # ── 5. Ensemble ───────────────────────────────────────────────────────────
    for h in HORIZONS:
        hp = [p for p in preds if p["horizon_days"] == h and p["model"] != "ensemble"]
        if not hp:
            continue
        wts = np.array([p["confidence_score"] or 0.5 for p in hp])
        wts = wts / (wts.sum() + 1e-8)
        ens_pct  = float(np.dot(wts, [p["predicted_change_pct"] for p in hp]))
        ens_conf = float(np.mean([p["confidence_score"] or 0.5 for p in hp]))
        vol_sp   = float(np.std(y_tr)) * 1.0
        lo, hi   = _price_bounds(current_price, ens_pct, vol_sp)
        preds.append({
            "asx_code":             asx_code,
            "prediction_date":      today,
            "model":                "ensemble",
            "horizon_days":         h,
            "current_price":        round(current_price, 4),
            "predicted_price":      round(current_price * (1 + ens_pct / 100), 4),
            "lower_bound":          lo,
            "upper_bound":          hi,
            "predicted_change_pct": round(ens_pct, 4),
            "direction":            _direction(ens_pct),
            "confidence_score":     round(ens_conf, 4),
            "r2_score":             None,
            "data_points":          n,
        })

    return preds


# ══════════════════════════════════════════════════════════════════════════════
# Batch orchestration (async — called from API background task)
# ══════════════════════════════════════════════════════════════════════════════

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS market.price_predictions (
    id                   BIGSERIAL       PRIMARY KEY,
    asx_code             VARCHAR(10)     NOT NULL,
    prediction_date      DATE            NOT NULL,
    model                VARCHAR(30)     NOT NULL,
    horizon_days         SMALLINT        NOT NULL,
    current_price        NUMERIC(12, 4)  NOT NULL,
    predicted_price      NUMERIC(12, 4),
    lower_bound          NUMERIC(12, 4),
    upper_bound          NUMERIC(12, 4),
    predicted_change_pct NUMERIC(8,  4),
    direction            VARCHAR(10),
    confidence_score     NUMERIC(5,  4),
    r2_score             NUMERIC(6,  4),
    data_points          SMALLINT,
    created_at           TIMESTAMPTZ     DEFAULT NOW(),
    UNIQUE (asx_code, prediction_date, model, horizon_days)
);
CREATE INDEX IF NOT EXISTS idx_pp_date_model
    ON market.price_predictions (prediction_date, model, horizon_days);
CREATE INDEX IF NOT EXISTS idx_pp_code_date
    ON market.price_predictions (asx_code, prediction_date);
"""

_UPSERT_SQL = """
INSERT INTO market.price_predictions
    (asx_code, prediction_date, model, horizon_days,
     current_price, predicted_price, lower_bound, upper_bound,
     predicted_change_pct, direction, confidence_score, r2_score, data_points)
VALUES
    (:asx_code, :prediction_date, :model, :horizon_days,
     :current_price, :predicted_price, :lower_bound, :upper_bound,
     :predicted_change_pct, :direction, :confidence_score, :r2_score, :data_points)
ON CONFLICT (asx_code, prediction_date, model, horizon_days) DO UPDATE SET
    current_price        = EXCLUDED.current_price,
    predicted_price      = EXCLUDED.predicted_price,
    lower_bound          = EXCLUDED.lower_bound,
    upper_bound          = EXCLUDED.upper_bound,
    predicted_change_pct = EXCLUDED.predicted_change_pct,
    direction            = EXCLUDED.direction,
    confidence_score     = EXCLUDED.confidence_score,
    r2_score             = EXCLUDED.r2_score,
    data_points          = EXCLUDED.data_points,
    created_at           = NOW()
"""


async def run_predictions_async(
    db,
    top_n:    int  = 1000,
    force:    bool = False,
    job_state: dict = None,
) -> dict:
    """
    Fetch top_n stocks, run ML predictions, upsert into market.price_predictions.
    cpu-bound `predict_stock` is offloaded to a ThreadPoolExecutor so the
    async event loop stays responsive.
    """
    from sqlalchemy import text

    today = date.today()

    # Ensure table exists
    await db.execute(text(_CREATE_TABLE_SQL))
    await db.commit()

    # Skip if today's predictions already exist (unless forced)
    if not force:
        row = await db.execute(
            text("SELECT COUNT(*) FROM market.price_predictions WHERE prediction_date = :d AND model = 'ensemble'"),
            {"d": today},
        )
        count = row.scalar() or 0
        if count > 100:
            return {"skipped": True, "message": f"Today's predictions already exist ({count} records)"}

    # Top N stocks by market cap
    stocks_r = await db.execute(text("""
        SELECT asx_code, price AS current_price
        FROM screener.universe
        WHERE price IS NOT NULL
        ORDER BY market_cap DESC NULLS LAST
        LIMIT :n
    """), {"n": top_n})
    stocks = stocks_r.fetchall()

    if not stocks:
        return {"error": "No stocks found in screener.universe"}

    top200 = {s.asx_code for s in stocks[:200]}

    if job_state is not None:
        job_state["total_stocks"]  = len(stocks)
        job_state["stocks_done"]   = 0

    loop    = asyncio.get_event_loop()
    done    = errors = total_preds = 0

    for stock in stocks:
        code  = stock.asx_code
        cprice = float(stock.current_price or 0)

        try:
            pr = await db.execute(text("""
                SELECT close, open, high, low, volume
                FROM market.daily_prices
                WHERE asx_code = :c
                ORDER BY time DESC LIMIT 260
            """), {"c": code})
            rows = list(reversed(pr.fetchall()))

            if len(rows) < MIN_ROWS:
                continue

            closes  = np.array([float(r.close  or 0) for r in rows])
            highs   = np.array([float(r.high   or 0) for r in rows])
            lows    = np.array([float(r.low    or 0) for r in rows])
            volumes = np.array([float(r.volume or 0) for r in rows])

            # Run ML in thread pool (CPU-bound)
            preds = await loop.run_in_executor(
                None, predict_stock,
                code, closes, highs, lows, volumes,
                cprice, code in top200,
            )

            if preds:
                for p in preds:
                    await db.execute(text(_UPSERT_SQL), p)
                await db.commit()
                total_preds += len(preds)
                done += 1

        except Exception as exc:
            log.error("Prediction error %s: %s", code, exc)
            await db.rollback()
            errors += 1

        if job_state is not None:
            job_state["stocks_done"] = done

        if (done + errors) % 50 == 0:
            log.info("Predictions: %d done, %d errors", done, errors)

    summary = {
        "prediction_date":    str(today),
        "stocks_predicted":   done,
        "predictions_stored": total_preds,
        "errors":             errors,
        "lstm_stocks":        len(top200),
    }
    log.info("Prediction run complete: %s", summary)
    return summary
