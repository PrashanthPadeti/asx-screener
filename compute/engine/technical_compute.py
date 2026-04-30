"""
ASX Screener — Technical Compute Engine
=========================================
Computes daily technical indicators from market.daily_prices and writes
to market.daily_metrics (TimescaleDB hypertable).

All indicators are computed with pure pandas/numpy — no external TA library
required.  Full OHLCV history is fetched per stock to ensure accurate
warm-up for long-period indicators (e.g. EMA-200, SMA-200, ATR, ADX).

Indicators:
  Trend       SMA 5/10/20/50/100/200, EMA 9/12/20/26/50/200, DMA ratios
  MACD        12/26/9 — line, signal, histogram, crossover prev-day values
  Momentum    RSI 7/14/21 (Wilder), Stochastic %K/%D (14,3,3), CCI 20,
              Williams %R 14, ROC 10/20
  Volatility  ATR 14, Bollinger Bands (20, 2σ), HV 20d/60d annualised
  Volume      OBV, OBV EMA 20, CMF 20, MFI 14, avg volumes, relative vol
  Levels      52-week high/low, ATH/ATL, % from each
  Signals     above SMA 20/50/100/200, golden/death cross, new 52w/ATH highs
  Returns     1w, 1m, 3m, 6m, ytd, 1y

Usage:
    python compute/engine/technical_compute.py                 # latest date only
    python compute/engine/technical_compute.py --days 365      # last N calendar days
    python compute/engine/technical_compute.py --codes BHP CBA
    python compute/engine/technical_compute.py --limit 50
    python compute/engine/technical_compute.py --full          # all history (slow)
"""

import os
import logging
import argparse
from datetime import datetime, date, timezone, timedelta
from typing import Optional

import psycopg2
import psycopg2.extensions
from psycopg2.extras import execute_values
import pandas as pd
import numpy as np
from dotenv import load_dotenv

# Cast NUMERIC → Python float automatically
_DEC2FLOAT = psycopg2.extensions.new_type(
    psycopg2.extensions.DECIMAL.values,
    "DEC2FLOAT",
    lambda value, curs: float(value) if value is not None else None,
)
psycopg2.extensions.register_type(_DEC2FLOAT)

load_dotenv()

DB_URL = os.getenv(
    "DATABASE_URL_SYNC",
    "postgresql://asx_user:asx_secure_2024@localhost:5432/asx_screener"
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

COMPUTE_VERSION = "1.0.0"
BATCH_COMMIT    = 50


# ── Helpers ───────────────────────────────────────────────────────────────────

def _v(val):
    if val is None:
        return None
    if isinstance(val, (np.integer,)):
        return int(val)
    if isinstance(val, (np.floating, float)):
        return None if (np.isnan(val) or np.isinf(val)) else float(val)
    if isinstance(val, (bool, np.bool_)):
        return bool(val)
    return val


def _s(series: pd.Series, idx: int):
    """Safe scalar from Series at integer position — returns None on NaN/OOB."""
    try:
        val = series.iloc[idx]
        if pd.isna(val):
            return None
        return _v(val)
    except (IndexError, KeyError):
        return None


# ── Data Fetchers ─────────────────────────────────────────────────────────────

def fetch_codes(cur, codes=None, limit=None) -> list:
    if codes:
        return [c.upper() for c in codes]
    sql = """
        SELECT DISTINCT p.asx_code
        FROM market.daily_prices p
        JOIN market.companies c ON c.asx_code = p.asx_code
        WHERE c.status = 'active'
        ORDER BY p.asx_code
    """
    if limit:
        sql += f" LIMIT {limit}"
    cur.execute(sql)
    return [r[0] for r in cur.fetchall()]


def fetch_ohlcv(cur, asx_code: str) -> pd.DataFrame:
    """
    Fetch full OHLCV history for a stock.
    Groups by date to handle intraday duplicates — takes last price of day.
    """
    cur.execute("""
        SELECT
            DATE(time AT TIME ZONE 'Australia/Sydney') AS day,
            (array_agg(open       ORDER BY time DESC))[1]  AS open,
            MAX(high)                                       AS high,
            MIN(low)                                        AS low,
            (array_agg(close      ORDER BY time DESC))[1]  AS close,
            (array_agg(adjusted_close ORDER BY time DESC))[1] AS adj_close,
            SUM(volume)                                     AS volume
        FROM market.daily_prices
        WHERE asx_code = %s
        GROUP BY day
        ORDER BY day ASC
    """, [asx_code])

    rows = cur.fetchall()
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows, columns=["date", "open", "high", "low",
                                      "close", "adj_close", "volume"])
    df["date"]      = pd.to_datetime(df["date"])
    df["open"]      = df["open"].astype(float)
    df["high"]      = df["high"].astype(float)
    df["low"]       = df["low"].astype(float)
    df["close"]     = df["close"].astype(float)
    df["adj_close"] = df["adj_close"].astype(float)
    df["volume"]    = pd.to_numeric(df["volume"], errors="coerce").fillna(0).astype("int64")
    return df.reset_index(drop=True)


def fetch_shares(cur, asx_code: str) -> Optional[float]:
    cur.execute("""
        SELECT shares_outstanding FROM staging.shares_stats
        WHERE asx_code = %s LIMIT 1
    """, [asx_code])
    row = cur.fetchone()
    return float(row[0]) if row and row[0] else None


# ── Indicator Computation ─────────────────────────────────────────────────────

def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False, min_periods=span).mean()


def _wilder_smooth(series: pd.Series, period: int) -> pd.Series:
    """Wilder's smoothing (used in RSI, ATR, ADX)."""
    result = np.full(len(series), np.nan)
    data   = series.to_numpy(dtype=float)
    # Find first valid window
    start = period - 1
    while start < len(data) and np.isnan(data[start - period + 1:start + 1]).any():
        start += 1
    if start >= len(data):
        return pd.Series(result, index=series.index)
    result[start] = np.nanmean(data[start - period + 1:start + 1])
    for i in range(start + 1, len(data)):
        if np.isnan(data[i]):
            result[i] = result[i - 1]
        else:
            result[i] = (result[i - 1] * (period - 1) + data[i]) / period
    return pd.Series(result, index=series.index)


def compute_rsi(close: pd.Series, period: int) -> pd.Series:
    delta = close.diff()
    gain  = delta.clip(lower=0)
    loss  = (-delta).clip(lower=0)
    avg_g = _wilder_smooth(gain, period)
    avg_l = _wilder_smooth(loss, period)
    rs    = avg_g / avg_l.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).round(2)


def compute_atr(high: pd.Series, low: pd.Series, close: pd.Series,
                period: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs(),
    ], axis=1).max(axis=1)
    return _wilder_smooth(tr, period)


def compute_adx(high: pd.Series, low: pd.Series, close: pd.Series,
                period: int = 14):
    """Returns (adx, plus_di, minus_di) as three pd.Series."""
    prev_high  = high.shift(1)
    prev_low   = low.shift(1)
    prev_close = close.shift(1)

    up_move   = high - prev_high
    down_move = prev_low - low

    plus_dm  = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    plus_dm_s  = pd.Series(plus_dm,  index=high.index)
    minus_dm_s = pd.Series(minus_dm, index=high.index)

    tr        = compute_atr(high, low, close, 1)   # True Range per bar
    atr14     = _wilder_smooth(tr,        period)
    plus_di14 = _wilder_smooth(plus_dm_s, period)
    minus_di14= _wilder_smooth(minus_dm_s,period)

    plus_di  = (100 * plus_di14  / atr14.replace(0, np.nan)).round(2)
    minus_di = (100 * minus_di14 / atr14.replace(0, np.nan)).round(2)

    dx  = (100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan))
    adx = _wilder_smooth(dx.fillna(0), period).round(2)
    return adx, plus_di, minus_di


def compute_cci(high: pd.Series, low: pd.Series, close: pd.Series,
                period: int = 20) -> pd.Series:
    typical = (high + low + close) / 3
    sma_tp  = typical.rolling(period).mean()
    mad     = typical.rolling(period).apply(lambda x: np.mean(np.abs(x - x.mean())), raw=True)
    return ((typical - sma_tp) / (0.015 * mad.replace(0, np.nan))).round(4)


def compute_obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    sign = np.sign(close.diff()).fillna(0)
    return (sign * volume).cumsum().astype("int64")


def compute_cmf(high: pd.Series, low: pd.Series, close: pd.Series,
                volume: pd.Series, period: int = 20) -> pd.Series:
    hl_range = (high - low).replace(0, np.nan)
    mfv = ((close - low - (high - close)) / hl_range) * volume
    return (mfv.rolling(period).sum() / volume.rolling(period).sum().replace(0, np.nan)).round(4)


def compute_mfi(high: pd.Series, low: pd.Series, close: pd.Series,
                volume: pd.Series, period: int = 14) -> pd.Series:
    typical = (high + low + close) / 3
    raw_mf  = typical * volume
    prev_tp = typical.shift(1)
    pos_mf  = raw_mf.where(typical > prev_tp, 0)
    neg_mf  = raw_mf.where(typical < prev_tp, 0)
    mf_ratio = (pos_mf.rolling(period).sum() /
                neg_mf.rolling(period).sum().replace(0, np.nan))
    return (100 - 100 / (1 + mf_ratio)).round(2)


def compute_williams_r(high: pd.Series, low: pd.Series, close: pd.Series,
                       period: int = 14) -> pd.Series:
    h14 = high.rolling(period).max()
    l14 = low.rolling(period).min()
    return (-100 * (h14 - close) / (h14 - l14).replace(0, np.nan)).round(2)


def compute_vwap_rolling(close: pd.Series, volume: pd.Series,
                          period: int = 20) -> pd.Series:
    """Rolling VWAP: Σ(price×vol) / Σ(vol) over N days."""
    pv = close * volume
    return (pv.rolling(period).sum() /
            volume.rolling(period).sum().replace(0, np.nan)).round(4)


def compute_indicators(df: pd.DataFrame, shares: Optional[float]) -> pd.DataFrame:
    """
    Given full OHLCV history, compute all technical indicators.
    Returns the same DataFrame with new indicator columns appended.
    """
    if df.empty or len(df) < 2:
        return df

    o = df["open"]
    h = df["high"]
    l = df["low"]
    c = df["close"]
    a = df["adj_close"]
    v = df["volume"].astype(float)

    # ── Returns ───────────────────────────────────────────────────────────────
    df["daily_return"] = c.pct_change().round(6)
    df["log_return"]   = np.log(c / c.shift(1)).round(6)
    df["gap_pct"]      = ((o - c.shift(1)) / c.shift(1).replace(0, np.nan)).round(4)

    # ── SMAs ──────────────────────────────────────────────────────────────────
    for p in [5, 10, 20, 50, 100, 200]:
        df[f"sma_{p}"] = c.rolling(p).mean().round(4)

    # ── EMAs ──────────────────────────────────────────────────────────────────
    for p in [9, 12, 20, 26, 50, 200]:
        df[f"ema_{p}"] = _ema(c, p).round(4)

    # ── DMA Ratios ────────────────────────────────────────────────────────────
    df["dma20_ratio"]  = (c / df["sma_20"].replace(0, np.nan)).round(4)
    df["dma50_ratio"]  = (c / df["sma_50"].replace(0, np.nan)).round(4)
    df["dma200_ratio"] = (c / df["sma_200"].replace(0, np.nan)).round(4)

    # ── SMA prev-day (for crossover detection) ────────────────────────────────
    df["sma_50_prev"]  = df["sma_50"].shift(1).round(4)
    df["sma_200_prev"] = df["sma_200"].shift(1).round(4)

    # ── MACD 12/26/9 ─────────────────────────────────────────────────────────
    df["macd_line"]   = (df["ema_12"] - df["ema_26"]).round(4)
    df["macd_signal"] = _ema(df["macd_line"], 9).round(4)
    df["macd_hist"]   = (df["macd_line"] - df["macd_signal"]).round(4)
    df["macd_line_prev"]   = df["macd_line"].shift(1).round(4)
    df["macd_signal_prev"] = df["macd_signal"].shift(1).round(4)

    # ── RSI ───────────────────────────────────────────────────────────────────
    df["rsi_7"]  = compute_rsi(c, 7)
    df["rsi_14"] = compute_rsi(c, 14)
    df["rsi_21"] = compute_rsi(c, 21)

    # ── Stochastic %K/%D (14, 3, 3) ──────────────────────────────────────────
    l14 = l.rolling(14).min()
    h14 = h.rolling(14).max()
    raw_k        = (100 * (c - l14) / (h14 - l14).replace(0, np.nan))
    df["stoch_k"] = raw_k.rolling(3).mean().round(2)     # fast → slow
    df["stoch_d"] = df["stoch_k"].rolling(3).mean().round(2)

    # ── Bollinger Bands (20, 2σ) ──────────────────────────────────────────────
    sma20 = df["sma_20"]
    std20 = c.rolling(20).std()
    df["bb_upper"] = (sma20 + 2 * std20).round(4)
    df["bb_mid"]   = sma20.round(4)
    df["bb_lower"] = (sma20 - 2 * std20).round(4)
    band_width     = df["bb_upper"] - df["bb_lower"]
    df["bb_pct"]   = ((c - df["bb_lower"]) / band_width.replace(0, np.nan)).round(4)
    df["bb_width"] = (band_width / sma20.replace(0, np.nan)).round(4)

    # ── ATR 14 ────────────────────────────────────────────────────────────────
    atr14 = compute_atr(h, l, c, 14)
    df["atr_14"]     = atr14.round(4)
    df["true_range"] = pd.concat([
        h - l, (h - c.shift(1)).abs(), (l - c.shift(1)).abs()
    ], axis=1).max(axis=1).round(4)
    df["atr_pct"]    = (atr14 / c.replace(0, np.nan)).round(4)

    # ── ADX 14 ────────────────────────────────────────────────────────────────
    adx14, plus_di, minus_di = compute_adx(h, l, c, 14)
    df["adx_14"]   = adx14.round(2)
    df["plus_di"]  = plus_di.round(2)
    df["minus_di"] = minus_di.round(2)

    # ── CCI 20 ────────────────────────────────────────────────────────────────
    df["cci_20"] = compute_cci(h, l, c, 20)

    # ── Williams %R 14 ───────────────────────────────────────────────────────
    df["williams_r"] = compute_williams_r(h, l, c, 14)

    # ── ROC ───────────────────────────────────────────────────────────────────
    df["roc_10"] = ((c / c.shift(10).replace(0, np.nan) - 1) * 100).round(4)
    df["roc_20"] = ((c / c.shift(20).replace(0, np.nan) - 1) * 100).round(4)

    # ── Historical Volatility (annualised) ───────────────────────────────────
    log_ret = np.log(c / c.shift(1))
    df["hv_20d"] = (log_ret.rolling(20).std() * np.sqrt(252)).round(4)
    df["hv_60d"] = (log_ret.rolling(60).std() * np.sqrt(252)).round(4)

    # ── OBV ───────────────────────────────────────────────────────────────────
    obv            = compute_obv(c, v.astype("int64"))
    df["obv"]      = obv
    df["obv_ema"]  = _ema(obv.astype(float), 20).round(0).astype("int64")

    # ── CMF 20, MFI 14 ────────────────────────────────────────────────────────
    df["cmf_20"] = compute_cmf(h, l, c, v, 20)
    df["mfi_14"] = compute_mfi(h, l, c, v, 14)

    # ── Rolling VWAP (20d) ────────────────────────────────────────────────────
    df["vwap"] = compute_vwap_rolling(c, v, 20)

    # ── Volume Averages ───────────────────────────────────────────────────────
    df["volume_avg_5d"]  = v.rolling(5).mean().round(0).astype("Int64")
    df["volume_avg_20d"] = v.rolling(20).mean().round(0).astype("Int64")
    df["volume_avg_50d"] = v.rolling(50).mean().round(0).astype("Int64")
    avg20 = v.rolling(20).mean().replace(0, np.nan)
    df["relative_volume"] = (v / avg20).round(4)

    # ── 52-week & ATH/ATL ─────────────────────────────────────────────────────
    df["high_52w"]          = h.rolling(252).max().round(4)
    df["low_52w"]           = l.rolling(252).min().round(4)
    df["ath_price"]         = h.expanding().max().round(4)
    df["atl_price"]         = l.expanding().min().round(4)
    df["pct_from_52w_high"] = ((c - df["high_52w"]) / df["high_52w"].replace(0, np.nan)).round(4)
    df["pct_from_52w_low"]  = ((c - df["low_52w"])  / df["low_52w"].replace(0, np.nan)).round(4)
    df["pct_from_ath"]      = ((c - df["ath_price"]) / df["ath_price"].replace(0, np.nan)).round(4)

    # ── Market Cap (AUD millions) ─────────────────────────────────────────────
    if shares and shares > 0:
        df["market_cap"] = (c * shares / 1_000_000).round(2)

    # ── Price Signals ─────────────────────────────────────────────────────────
    df["above_sma20"]   = c > df["sma_20"]
    df["above_sma50"]   = c > df["sma_50"]
    df["above_sma100"]  = c > df["sma_100"]
    df["above_sma200"]  = c > df["sma_200"]
    df["golden_cross"]  = (df["sma_50"] > df["sma_200"]) & (df["sma_50_prev"] <= df["sma_200_prev"])
    df["death_cross"]   = (df["sma_50"] < df["sma_200"]) & (df["sma_50_prev"] >= df["sma_200_prev"])
    df["new_52w_high"]  = (h >= df["high_52w"]) & (h > h.shift(1))
    df["new_52w_low"]   = (l <= df["low_52w"])  & (l < l.shift(1))
    df["new_ath"]       = (h >= df["ath_price"]) & (h > h.shift(1))

    # ── Returns ───────────────────────────────────────────────────────────────
    df["return_1w"]  = (c / c.shift(5).replace(0, np.nan)   - 1).round(4)
    df["return_1m"]  = (c / c.shift(21).replace(0, np.nan)  - 1).round(4)
    df["return_3m"]  = (c / c.shift(63).replace(0, np.nan)  - 1).round(4)
    df["return_6m"]  = (c / c.shift(126).replace(0, np.nan) - 1).round(4)
    df["return_1y"]  = (c / c.shift(252).replace(0, np.nan) - 1).round(4)

    # YTD: return from last close of previous calendar year
    df["_year"] = df["date"].dt.year
    year_starts = df.groupby("_year")["date"].transform("min")
    idx_year_start = df["date"].searchsorted(year_starts) - 1
    idx_year_start = idx_year_start.clip(lower=0)
    prev_year_close = c.iloc[idx_year_start.values].values
    df["return_ytd"] = ((c.values - prev_year_close) /
                        np.where(prev_year_close == 0, np.nan, prev_year_close)).round(4)
    df.drop(columns=["_year"], inplace=True)

    return df


# ── Column → DB mapping ───────────────────────────────────────────────────────

INSERT_COLS = [
    "asx_code", "date",
    "close", "adj_close", "volume",
    "market_cap",
    # Returns
    "daily_return", "log_return", "gap_pct",
    # SMAs
    "sma_5", "sma_10", "sma_20", "sma_50", "sma_100", "sma_200",
    # EMAs
    "ema_9", "ema_12", "ema_20", "ema_26", "ema_50", "ema_200",
    # DMA ratios
    "dma20_ratio", "dma50_ratio", "dma200_ratio",
    # Prev day MAs
    "sma_50_prev", "sma_200_prev",
    # MACD
    "macd_line", "macd_signal", "macd_hist",
    "macd_line_prev", "macd_signal_prev",
    # RSI
    "rsi_7", "rsi_14", "rsi_21",
    # Stochastic
    "stoch_k", "stoch_d",
    # Bollinger
    "bb_upper", "bb_mid", "bb_lower", "bb_pct", "bb_width",
    # Trend
    "adx_14", "plus_di", "minus_di",
    "cci_20", "williams_r", "roc_10", "roc_20",
    # Volatility
    "atr_14", "atr_pct", "true_range",
    "hv_20d", "hv_60d",
    # Volume
    "obv", "obv_ema", "vwap", "cmf_20", "mfi_14",
    "volume_avg_5d", "volume_avg_20d", "volume_avg_50d",
    "relative_volume",
    # Levels
    "high_52w", "low_52w", "ath_price", "atl_price",
    "pct_from_52w_high", "pct_from_52w_low", "pct_from_ath",
    # Signals
    "above_sma20", "above_sma50", "above_sma100", "above_sma200",
    "golden_cross", "death_cross", "new_52w_high", "new_52w_low", "new_ath",
    # Returns
    "return_1w", "return_1m", "return_3m", "return_6m", "return_ytd", "return_1y",
    # Metadata
    "compute_version", "computed_at",
]

INSERT_SQL = f"""
    INSERT INTO market.daily_metrics ({", ".join(INSERT_COLS)})
    VALUES %s
    ON CONFLICT (asx_code, date) DO UPDATE SET
        {", ".join(f"{c} = EXCLUDED.{c}" for c in INSERT_COLS if c not in ("asx_code", "date"))}
"""


def build_rows(asx_code: str, df: pd.DataFrame, since: Optional[date] = None) -> list:
    """Convert the indicator DataFrame to a list of tuples for execute_values."""
    now = datetime.now(tz=timezone.utc)

    if since:
        df = df[df["date"].dt.date >= since]

    # Need at least one indicator to be non-null (skip warm-up rows)
    df = df[df["rsi_14"].notna()]

    rows = []
    for _, row in df.iterrows():
        def g(col):
            return _v(row.get(col)) if col in row.index else None

        # Integer volume columns
        def gi(col):
            v = g(col)
            if v is None:
                return None
            try:
                return int(v)
            except Exception:
                return None

        rows.append((
            asx_code,
            row["date"].date(),
            g("close"), g("adj_close"), gi("volume"),
            g("market_cap"),
            g("daily_return"), g("log_return"), g("gap_pct"),
            g("sma_5"),  g("sma_10"),  g("sma_20"),
            g("sma_50"), g("sma_100"), g("sma_200"),
            g("ema_9"),  g("ema_12"),  g("ema_20"),
            g("ema_26"), g("ema_50"),  g("ema_200"),
            g("dma20_ratio"), g("dma50_ratio"), g("dma200_ratio"),
            g("sma_50_prev"), g("sma_200_prev"),
            g("macd_line"), g("macd_signal"), g("macd_hist"),
            g("macd_line_prev"), g("macd_signal_prev"),
            g("rsi_7"),  g("rsi_14"), g("rsi_21"),
            g("stoch_k"), g("stoch_d"),
            g("bb_upper"), g("bb_mid"), g("bb_lower"), g("bb_pct"), g("bb_width"),
            g("adx_14"), g("plus_di"), g("minus_di"),
            g("cci_20"), g("williams_r"), g("roc_10"), g("roc_20"),
            g("atr_14"), g("atr_pct"), g("true_range"),
            g("hv_20d"), g("hv_60d"),
            gi("obv"), gi("obv_ema"), g("vwap"), g("cmf_20"), g("mfi_14"),
            gi("volume_avg_5d"), gi("volume_avg_20d"), gi("volume_avg_50d"),
            g("relative_volume"),
            g("high_52w"), g("low_52w"), g("ath_price"), g("atl_price"),
            g("pct_from_52w_high"), g("pct_from_52w_low"), g("pct_from_ath"),
            g("above_sma20"), g("above_sma50"), g("above_sma100"), g("above_sma200"),
            g("golden_cross"), g("death_cross"),
            g("new_52w_high"), g("new_52w_low"), g("new_ath"),
            g("return_1w"), g("return_1m"), g("return_3m"),
            g("return_6m"), g("return_ytd"), g("return_1y"),
            COMPUTE_VERSION, now,
        ))
    return rows


def upsert_rows(cur, rows: list) -> int:
    if not rows:
        return 0
    execute_values(cur, INSERT_SQL, rows, page_size=500)
    return len(rows)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="ASX Technical Compute Engine")
    parser.add_argument("--codes",  nargs="+", help="Specific ASX codes")
    parser.add_argument("--limit",  type=int,  help="Max stocks to process")
    parser.add_argument("--days",   type=int,  default=None,
                        help="Only write rows for last N calendar days "
                             "(default: latest date only)")
    parser.add_argument("--full",   action="store_true",
                        help="Write all computed rows (full history — slow)")
    args = parser.parse_args()

    conn = psycopg2.connect(DB_URL)
    cur  = conn.cursor()

    codes = fetch_codes(cur, args.codes, args.limit)
    total = len(codes)

    # Determine the 'since' date for filtering output rows
    since: Optional[date] = None
    if args.full:
        since = None   # write everything
    elif args.days:
        since = (datetime.now() - timedelta(days=args.days)).date()
    # else: latest date only — handled per stock below

    mode = "full history" if args.full else (f"last {args.days}d" if args.days else "latest date only")
    log.info(f"Technical compute — {total} stocks | mode: {mode}")
    log.info("─" * 60)

    processed = skipped = errors = total_rows = 0

    for idx, asx_code in enumerate(codes, 1):
        try:
            df = fetch_ohlcv(cur, asx_code)
            if df.empty or len(df) < 20:
                skipped += 1
                continue

            shares = fetch_shares(cur, asx_code)
            df     = compute_indicators(df, shares)

            if not args.full and not args.days:
                # Latest date only
                last_date = df["date"].max().date()
                since_latest = last_date - timedelta(days=0)
                rows = build_rows(asx_code, df, since=since_latest)
            else:
                rows = build_rows(asx_code, df, since=since)

            if not rows:
                skipped += 1
                continue

            n = upsert_rows(cur, rows)
            total_rows += n
            processed  += 1

            if idx % BATCH_COMMIT == 0:
                conn.commit()
                log.info(f"  [{idx:4d}/{total}] {processed} done | "
                         f"{skipped} skipped | {errors} errors | "
                         f"{total_rows:,} rows so far")

        except Exception as e:
            errors += 1
            log.warning(f"  {asx_code}: {e}", exc_info=(errors <= 3))
            conn.rollback()

    conn.commit()
    cur.close()
    conn.close()

    log.info("─" * 60)
    log.info(f"Done! {processed} stocks | {skipped} skipped | "
             f"{errors} errors | {total_rows:,} rows upserted")


if __name__ == "__main__":
    main()
