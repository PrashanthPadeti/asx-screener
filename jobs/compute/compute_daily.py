"""
ASX Screener — Compute Daily Metrics (Seq 7)
============================================
Computes the full daily technical indicator suite from market.daily_prices
and upserts into market.daily_metrics (TimescaleDB hypertable).

Indicators computed per day per stock:
  Moving Averages: SMA 5/10/20/50/100/200, EMA 9/12/20/26/50/200
  DMA Ratios: price/SMA ratios, prev-day SMA values
  MACD: line, signal, histogram + prev-day values
  RSI: 7, 14, 21 periods (Wilder smoothing)
  Stochastics: %K, %D (14,3)
  Bollinger Bands: 20-period, 2 std
  ADX: ADX, +DI, -DI (14-period Wilder)
  CCI: 20-period
  Williams %R: 14-period
  ROC: 10, 20 period
  ATR: 14-period Wilder
  OBV: On-Balance Volume
  VWAP: rolling 20-day
  CMF: Chaikin Money Flow 20
  MFI: Money Flow Index 14
  52w High/Low, ATH/ATL, % from each
  Volume: 20d average, relative volume, 52w avg volume
  Signals: golden/death cross, above/below SMAs, RSI zones

Usage:
    python jobs/compute/compute_daily.py                  # Yesterday (nightly mode)
    python jobs/compute/compute_daily.py --mode historical # All days from 2000
    python jobs/compute/compute_daily.py --days 30         # Last N days
    python jobs/compute/compute_daily.py --codes BHP CBA   # Specific stocks
    python jobs/compute/compute_daily.py --date 2024-01-15 # Specific date
"""

import os
import math
import time
import logging
import argparse
import statistics
from datetime import date, datetime, timedelta
from typing import Optional

import psycopg2
from psycopg2.extras import execute_values, RealDictCursor
from dotenv import load_dotenv

load_dotenv()

DB_URL          = os.getenv("DATABASE_URL_SYNC",
                    "postgresql://asx_user:asx_secure_2024@localhost:5432/asx_screener")
COMPUTE_VERSION = "daily_v1.0"
BATCH_SIZE      = 500      # rows per execute_values call
COMMIT_EVERY    = 50       # stocks between commits
RFR             = 0.043    # RBA cash rate for Sharpe

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
#  Core math helpers
# ─────────────────────────────────────────────────────────────

def sma(prices: list, period: int) -> Optional[float]:
    if len(prices) < period:
        return None
    return sum(prices[-period:]) / period


def ema_series(prices: list, period: int) -> list:
    """Full EMA series (same length as prices, None-padded for warmup)."""
    if len(prices) < period:
        return [None] * len(prices)
    k = 2.0 / (period + 1)
    out = [None] * (period - 1)
    out.append(sum(prices[:period]) / period)
    for p in prices[period:]:
        out.append(p * k + out[-1] * (1 - k))
    return out


def ema_latest(prices: list, period: int) -> Optional[float]:
    s = ema_series(prices, period)
    return s[-1] if s else None


def wilder_smooth(values: list, period: int) -> list:
    """Wilder smoothing (used for RSI, ATR, ADX)."""
    if len(values) < period:
        return [None] * len(values)
    out = [None] * (period - 1)
    out.append(sum(values[:period]) / period)
    for v in values[period:]:
        out.append((out[-1] * (period - 1) + v) / period)
    return out


# ─────────────────────────────────────────────────────────────
#  RSI (Wilder)
# ─────────────────────────────────────────────────────────────

def rsi_wilder(prices: list, period: int = 14) -> list:
    """Full RSI series using Wilder smoothing. Returns list aligned to prices."""
    if len(prices) < period + 1:
        return [None] * len(prices)

    gains, losses = [], []
    for i in range(1, len(prices)):
        diff = prices[i] - prices[i - 1]
        gains.append(max(diff, 0.0))
        losses.append(max(-diff, 0.0))

    ag = wilder_smooth(gains, period)
    al = wilder_smooth(losses, period)

    out = [None]  # first price has no RSI
    for g, l in zip(ag, al):
        if g is None or l is None:
            out.append(None)
        elif l == 0:
            out.append(100.0)
        else:
            rs = g / l
            out.append(round(100 - 100 / (1 + rs), 2))
    return out


# ─────────────────────────────────────────────────────────────
#  MACD
# ─────────────────────────────────────────────────────────────

def macd_series(prices: list, fast=12, slow=26, signal=9):
    """Returns (macd_line_series, signal_series, hist_series) aligned to prices."""
    e_fast = ema_series(prices, fast)
    e_slow = ema_series(prices, slow)
    n = len(prices)

    macd_line = []
    for i in range(n):
        f, s = e_fast[i], e_slow[i]
        macd_line.append(f - s if f is not None and s is not None else None)

    # Signal: EMA of MACD line values (skip Nones)
    valid_indices = [i for i, v in enumerate(macd_line) if v is not None]
    if len(valid_indices) < signal:
        return macd_line, [None] * n, [None] * n

    # Build signal on the valid slice
    valid_vals = [macd_line[i] for i in valid_indices]
    sig_vals = ema_series(valid_vals, signal)

    sig_full = [None] * n
    hist_full = [None] * n
    for j, idx in enumerate(valid_indices):
        sv = sig_vals[j]
        sig_full[idx] = sv
        if sv is not None and macd_line[idx] is not None:
            hist_full[idx] = round(macd_line[idx] - sv, 6)

    return macd_line, sig_full, hist_full


# ─────────────────────────────────────────────────────────────
#  Bollinger Bands
# ─────────────────────────────────────────────────────────────

def bollinger_series(prices: list, period=20, mult=2.0):
    """Returns (upper, mid, lower, pct_b, width) series aligned to prices."""
    n = len(prices)
    upper_s = [None] * n
    mid_s   = [None] * n
    lower_s = [None] * n
    pct_b_s = [None] * n
    width_s = [None] * n

    for i in range(period - 1, n):
        window = prices[i - period + 1:i + 1]
        mid = sum(window) / period
        if period > 1:
            std = statistics.stdev(window)
        else:
            std = 0.0
        upper = mid + mult * std
        lower = mid - mult * std
        curr  = prices[i]
        pct_b = (curr - lower) / (upper - lower) if upper != lower else None
        width = (upper - lower) / mid if mid else None
        upper_s[i] = round(upper, 4)
        mid_s[i]   = round(mid, 4)
        lower_s[i] = round(lower, 4)
        pct_b_s[i] = round(pct_b, 4) if pct_b is not None else None
        width_s[i] = round(width, 4) if width is not None else None

    return upper_s, mid_s, lower_s, pct_b_s, width_s


# ─────────────────────────────────────────────────────────────
#  Stochastics
# ─────────────────────────────────────────────────────────────

def stochastic_series(highs: list, lows: list, closes: list, k_period=14, d_period=3):
    """Returns (%K series, %D series) aligned to closes."""
    n = len(closes)
    k_s = [None] * n
    for i in range(k_period - 1, n):
        h = max(highs[i - k_period + 1:i + 1])
        l = min(lows[i - k_period + 1:i + 1])
        k_s[i] = round((closes[i] - l) / (h - l) * 100, 2) if h != l else 50.0

    # %D = 3-period SMA of %K (on valid values only)
    d_s = [None] * n
    valid_k = [(i, v) for i, v in enumerate(k_s) if v is not None]
    for j in range(d_period - 1, len(valid_k)):
        avg = sum(v for _, v in valid_k[j - d_period + 1:j + 1]) / d_period
        idx = valid_k[j][0]
        d_s[idx] = round(avg, 2)

    return k_s, d_s


# ─────────────────────────────────────────────────────────────
#  ATR (Wilder)
# ─────────────────────────────────────────────────────────────

def atr_series(highs: list, lows: list, closes: list, period=14):
    """ATR series using Wilder smoothing, aligned to closes."""
    n = len(closes)
    if n < 2:
        return [None] * n

    tr_list = [None]  # first bar has no previous close
    for i in range(1, n):
        hl  = highs[i] - lows[i]
        hpc = abs(highs[i] - closes[i - 1])
        lpc = abs(lows[i] - closes[i - 1])
        tr_list.append(max(hl, hpc, lpc))

    # Wilder on TR values (skip the first None)
    tr_valid = tr_list[1:]  # n-1 values
    smoothed = wilder_smooth(tr_valid, period)

    out = [None] + smoothed
    return out


# ─────────────────────────────────────────────────────────────
#  ADX / +DI / -DI (Wilder)
# ─────────────────────────────────────────────────────────────

def adx_series(highs: list, lows: list, closes: list, period=14):
    """Returns (adx, plus_di, minus_di) series aligned to closes."""
    n = len(closes)
    adx_s   = [None] * n
    pdi_s   = [None] * n
    mdi_s   = [None] * n

    if n < period * 2 + 1:
        return adx_s, pdi_s, mdi_s

    plus_dm_list, minus_dm_list, tr_list = [], [], []
    for i in range(1, n):
        h_diff = highs[i] - highs[i - 1]
        l_diff = lows[i - 1] - lows[i]
        pdm = h_diff if h_diff > l_diff and h_diff > 0 else 0.0
        mdm = l_diff if l_diff > h_diff and l_diff > 0 else 0.0
        plus_dm_list.append(pdm)
        minus_dm_list.append(mdm)
        hl  = highs[i] - lows[i]
        hpc = abs(highs[i] - closes[i - 1])
        lpc = abs(lows[i] - closes[i - 1])
        tr_list.append(max(hl, hpc, lpc))

    sm_pdm = wilder_smooth(plus_dm_list, period)
    sm_mdm = wilder_smooth(minus_dm_list, period)
    sm_tr  = wilder_smooth(tr_list, period)

    dx_list = []
    for i in range(len(sm_tr)):
        tr = sm_tr[i]
        if tr is None or tr == 0:
            dx_list.append(None)
            pdi_s[i + 1] = None
            mdi_s[i + 1] = None
            continue
        pdi = sm_pdm[i] / tr * 100
        mdi = sm_mdm[i] / tr * 100
        pdi_s[i + 1] = round(pdi, 2)
        mdi_s[i + 1] = round(mdi, 2)
        denom = pdi + mdi
        dx = abs(pdi - mdi) / denom * 100 if denom else 0.0
        dx_list.append(dx)

    # ADX = Wilder smooth of DX
    valid_dx = [(i, v) for i, v in enumerate(dx_list) if v is not None]
    if len(valid_dx) < period:
        return adx_s, pdi_s, mdi_s

    dx_vals = [v for _, v in valid_dx]
    adx_vals = wilder_smooth(dx_vals, period)
    for j, (orig_i, _) in enumerate(valid_dx):
        if adx_vals[j] is not None:
            adx_s[orig_i + 1] = round(adx_vals[j], 2)

    return adx_s, pdi_s, mdi_s


# ─────────────────────────────────────────────────────────────
#  CCI
# ─────────────────────────────────────────────────────────────

def cci_series(highs: list, lows: list, closes: list, period=20):
    """CCI series aligned to closes."""
    n = len(closes)
    out = [None] * n
    for i in range(period - 1, n):
        tp_window = [(highs[j] + lows[j] + closes[j]) / 3
                     for j in range(i - period + 1, i + 1)]
        tp_mean = sum(tp_window) / period
        md = sum(abs(tp - tp_mean) for tp in tp_window) / period
        tp_curr = (highs[i] + lows[i] + closes[i]) / 3
        out[i] = round((tp_curr - tp_mean) / (0.015 * md), 2) if md else None
    return out


# ─────────────────────────────────────────────────────────────
#  Williams %R
# ─────────────────────────────────────────────────────────────

def williams_r_series(highs: list, lows: list, closes: list, period=14):
    n = len(closes)
    out = [None] * n
    for i in range(period - 1, n):
        h = max(highs[i - period + 1:i + 1])
        l = min(lows[i - period + 1:i + 1])
        out[i] = round((h - closes[i]) / (h - l) * -100, 2) if h != l else -50.0
    return out


# ─────────────────────────────────────────────────────────────
#  ROC
# ─────────────────────────────────────────────────────────────

def roc_series(prices: list, period: int):
    n = len(prices)
    out = [None] * n
    for i in range(period, n):
        if prices[i - period] and prices[i - period] > 0:
            out[i] = round((prices[i] - prices[i - period]) / prices[i - period] * 100, 4)
    return out


# ─────────────────────────────────────────────────────────────
#  OBV
# ─────────────────────────────────────────────────────────────

def obv_series(closes: list, volumes: list):
    n = len(closes)
    out = [0]
    for i in range(1, n):
        v = volumes[i] or 0
        if closes[i] > closes[i - 1]:
            out.append(out[-1] + v)
        elif closes[i] < closes[i - 1]:
            out.append(out[-1] - v)
        else:
            out.append(out[-1])
    return out


# ─────────────────────────────────────────────────────────────
#  VWAP (rolling N-day)
# ─────────────────────────────────────────────────────────────

def vwap_series(highs: list, lows: list, closes: list, volumes: list, period=20):
    n = len(closes)
    out = [None] * n
    for i in range(period - 1, n):
        tp_vols = [(highs[j] + lows[j] + closes[j]) / 3 * (volumes[j] or 0)
                   for j in range(i - period + 1, i + 1)]
        vol_sum = sum(volumes[j] or 0 for j in range(i - period + 1, i + 1))
        out[i] = round(sum(tp_vols) / vol_sum, 4) if vol_sum else None
    return out


# ─────────────────────────────────────────────────────────────
#  CMF (Chaikin Money Flow)
# ─────────────────────────────────────────────────────────────

def cmf_series(highs: list, lows: list, closes: list, volumes: list, period=20):
    n = len(closes)
    out = [None] * n
    for i in range(period - 1, n):
        mfv_sum = 0.0
        vol_sum = 0.0
        for j in range(i - period + 1, i + 1):
            hl = highs[j] - lows[j]
            if hl > 0:
                mfm = ((closes[j] - lows[j]) - (highs[j] - closes[j])) / hl
            else:
                mfm = 0.0
            v = volumes[j] or 0
            mfv_sum += mfm * v
            vol_sum += v
        out[i] = round(mfv_sum / vol_sum, 4) if vol_sum else None
    return out


# ─────────────────────────────────────────────────────────────
#  MFI (Money Flow Index)
# ─────────────────────────────────────────────────────────────

def mfi_series(highs: list, lows: list, closes: list, volumes: list, period=14):
    n = len(closes)
    out = [None] * n
    tp = [(highs[i] + lows[i] + closes[i]) / 3 for i in range(n)]
    for i in range(period, n):
        pos_mf = neg_mf = 0.0
        for j in range(i - period + 1, i + 1):
            v = volumes[j] or 0
            raw = tp[j] * v
            if tp[j] > tp[j - 1]:
                pos_mf += raw
            elif tp[j] < tp[j - 1]:
                neg_mf += raw
        if neg_mf == 0:
            out[i] = 100.0
        else:
            mfr = pos_mf / neg_mf
            out[i] = round(100 - 100 / (1 + mfr), 2)
    return out


# ─────────────────────────────────────────────────────────────
#  Aroon
# ─────────────────────────────────────────────────────────────

def aroon_series(highs: list, lows: list, period=25):
    n = len(highs)
    up_s   = [None] * n
    down_s = [None] * n
    for i in range(period, n):
        window_h = highs[i - period:i + 1]
        window_l = lows[i - period:i + 1]
        hi_idx = window_h.index(max(window_h))
        lo_idx = window_l.index(min(window_l))
        up_s[i]   = round((hi_idx) / period * 100, 2)
        down_s[i] = round((lo_idx) / period * 100, 2)
    return up_s, down_s


# ─────────────────────────────────────────────────────────────
#  Data fetch
# ─────────────────────────────────────────────────────────────

def fetch_price_history(cur, asx_code: str, from_date: date) -> list[dict]:
    cur.execute("""
        SELECT time::date AS dt,
               open, high, low,
               adjusted_close AS close,
               volume
        FROM market.daily_prices
        WHERE asx_code = %s
          AND time::date >= %s
          AND adjusted_close IS NOT NULL
        ORDER BY time ASC
    """, (asx_code, from_date))
    return cur.fetchall()


def get_dates_to_compute(mode: str, n_days: int, specific_date: Optional[date]) -> list[date]:
    if specific_date:
        return [specific_date]
    today = date.today()
    if mode == "historical":
        start = date(2000, 1, 1)
        days = []
        d = start
        while d <= today:
            days.append(d)
            d += timedelta(days=1)
        return days
    else:
        yesterday = today - timedelta(days=1)
        return [yesterday - timedelta(days=i) for i in range(n_days - 1, -1, -1)]


# ─────────────────────────────────────────────────────────────
#  Core compute
# ─────────────────────────────────────────────────────────────

def compute_daily_for_stock(asx_code: str, rows: list[dict],
                             target_dates: set) -> list[dict]:
    if not rows:
        return []

    dates   = [r["dt"] for r in rows]
    opens   = [float(r["open"])   if r["open"]   else float(r["close"]) for r in rows]
    highs   = [float(r["high"])   if r["high"]   else float(r["close"]) for r in rows]
    lows    = [float(r["low"])    if r["low"]    else float(r["close"]) for r in rows]
    closes  = [float(r["close"]) for r in rows]
    volumes = [int(r["volume"]) if r["volume"] else 0 for r in rows]
    n = len(closes)

    # ── Moving averages ──────────────────────────────────────
    sma5_s   = [sma(closes[:i+1], 5)   for i in range(n)]
    sma10_s  = [sma(closes[:i+1], 10)  for i in range(n)]
    sma20_s  = [sma(closes[:i+1], 20)  for i in range(n)]
    sma50_s  = [sma(closes[:i+1], 50)  for i in range(n)]
    sma100_s = [sma(closes[:i+1], 100) for i in range(n)]
    sma200_s = [sma(closes[:i+1], 200) for i in range(n)]

    ema9_s   = ema_series(closes, 9)
    ema12_s  = ema_series(closes, 12)
    ema20_s  = ema_series(closes, 20)
    ema26_s  = ema_series(closes, 26)
    ema50_s  = ema_series(closes, 50)
    ema200_s = ema_series(closes, 200)

    # ── MACD ─────────────────────────────────────────────────
    macd_l_s, macd_sig_s, macd_hist_s = macd_series(closes)

    # ── RSI ──────────────────────────────────────────────────
    rsi7_s  = rsi_wilder(closes, 7)
    rsi14_s = rsi_wilder(closes, 14)
    rsi21_s = rsi_wilder(closes, 21)

    # ── Stochastics ──────────────────────────────────────────
    stoch_k_s, stoch_d_s = stochastic_series(highs, lows, closes)

    # ── Bollinger ─────────────────────────────────────────────
    bb_u_s, bb_m_s, bb_l_s, bb_pct_s, bb_w_s = bollinger_series(closes)

    # ── ADX ──────────────────────────────────────────────────
    adx_s, pdi_s, mdi_s = adx_series(highs, lows, closes)

    # ── CCI ──────────────────────────────────────────────────
    cci_s = cci_series(highs, lows, closes)

    # ── Williams %R ──────────────────────────────────────────
    wpr_s = williams_r_series(highs, lows, closes)

    # ── ROC ──────────────────────────────────────────────────
    roc10_s = roc_series(closes, 10)
    roc20_s = roc_series(closes, 20)

    # ── ATR ──────────────────────────────────────────────────
    atr_s = atr_series(highs, lows, closes)

    # ── OBV ──────────────────────────────────────────────────
    obv_s = obv_series(closes, volumes)

    # ── VWAP ─────────────────────────────────────────────────
    vwap_s = vwap_series(highs, lows, closes, volumes)

    # ── CMF ──────────────────────────────────────────────────
    cmf_s = cmf_series(highs, lows, closes, volumes)

    # ── MFI ──────────────────────────────────────────────────
    mfi_s = mfi_series(highs, lows, closes, volumes)

    # ── Aroon ─────────────────────────────────────────────────
    aroon_up_s, aroon_dn_s = aroon_series(highs, lows)

    # ── Volume average (20d) ──────────────────────────────────
    vol_avg20_s = [sma(volumes[:i+1], 20) for i in range(n)]

    # ── ATH / ATL running ────────────────────────────────────
    ath_s = [None] * n
    atl_s = [None] * n
    running_ath = highs[0]
    running_atl = lows[0]
    for i in range(n):
        running_ath = max(running_ath, highs[i])
        running_atl = min(running_atl, lows[i])
        ath_s[i] = running_ath
        atl_s[i] = running_atl

    results = []
    date_to_idx = {d: i for i, d in enumerate(dates)}

    for target_dt in sorted(target_dates):
        if target_dt not in date_to_idx:
            continue
        i = date_to_idx[target_dt]

        c  = closes[i]
        h  = highs[i]
        l  = lows[i]
        o  = opens[i]
        v  = volumes[i]

        # 52-week window
        cutoff_52w = target_dt - timedelta(days=365)
        prices_52w = [closes[j] for j in range(i + 1) if dates[j] >= cutoff_52w]
        highs_52w  = [highs[j]  for j in range(i + 1) if dates[j] >= cutoff_52w]
        lows_52w   = [lows[j]   for j in range(i + 1) if dates[j] >= cutoff_52w]
        vols_52w   = [volumes[j] for j in range(i + 1) if dates[j] >= cutoff_52w]

        high_52w  = max(highs_52w)  if highs_52w  else None
        low_52w   = min(lows_52w)   if lows_52w   else None
        vol_52w   = int(sum(vols_52w) / len(vols_52w)) if vols_52w else None

        pct_from_52wh = round((c - high_52w) / high_52w * 100, 2) if high_52w and high_52w > 0 else None
        pct_from_52wl = round((c - low_52w)  / low_52w  * 100, 2) if low_52w  and low_52w  > 0 else None

        ath = ath_s[i]
        atl = atl_s[i]
        pct_from_ath = round((c - ath) / ath * 100, 2) if ath and ath > 0 else None
        pct_from_atl = round((c - atl) / atl * 100, 2) if atl and atl > 0 else None

        # prev-day MA values
        s5_prev   = sma5_s[i-1]   if i > 0 else None
        s20_prev  = sma20_s[i-1]  if i > 0 else None
        s50_prev  = sma50_s[i-1]  if i > 0 else None
        s200_prev = sma200_s[i-1] if i > 0 else None
        macd_prev = round(macd_l_s[i-1], 6) if i > 0 and macd_l_s[i-1] is not None else None
        macd_sig_prev = round(macd_sig_s[i-1], 6) if i > 0 and macd_sig_s[i-1] is not None else None

        # DMA ratios
        def dma_ratio(price, ma_val):
            return round(price / ma_val, 4) if ma_val and ma_val > 0 else None

        # Signals
        s50 = sma50_s[i]
        s200 = sma200_s[i]
        golden_cross = (s50 is not None and s200 is not None and
                        s50 > s200 and
                        (sma50_s[i-1] is None or sma200_s[i-1] is None or
                         sma50_s[i-1] <= sma200_s[i-1])) if i > 0 else False
        death_cross  = (s50 is not None and s200 is not None and
                        s50 < s200 and
                        (sma50_s[i-1] is None or sma200_s[i-1] is None or
                         sma50_s[i-1] >= sma200_s[i-1])) if i > 0 else False

        rsi14 = rsi14_s[i]
        rsi_overbought  = rsi14 is not None and rsi14 >= 70
        rsi_oversold    = rsi14 is not None and rsi14 <= 30

        macd_curr = macd_l_s[i]
        macd_sig_curr = macd_sig_s[i]
        macd_bullish = (macd_curr is not None and macd_sig_curr is not None and
                        macd_curr > macd_sig_curr and
                        macd_prev is not None and macd_sig_prev is not None and
                        macd_prev <= macd_sig_prev)
        macd_bearish = (macd_curr is not None and macd_sig_curr is not None and
                        macd_curr < macd_sig_curr and
                        macd_prev is not None and macd_sig_prev is not None and
                        macd_prev >= macd_sig_prev)

        vol_avg20 = vol_avg20_s[i]
        rel_vol = round(v / vol_avg20, 4) if vol_avg20 and vol_avg20 > 0 else None

        # Returns
        def price_return(days_back):
            if i < days_back:
                return None
            p = closes[i - days_back]
            return round((c - p) / p * 100, 4) if p and p > 0 else None

        results.append({
            "asx_code":         asx_code,
            "date":             target_dt,

            # OHLCV
            "open":             round(o, 4),
            "high":             round(h, 4),
            "low":              round(l, 4),
            "close":            round(c, 4),
            "volume":           v,
            "volume_avg_20d":   int(vol_avg20) if vol_avg20 else None,
            "volume_avg_52w":   vol_52w,
            "relative_volume":  rel_vol,

            # Moving averages
            "sma_5":            round(sma5_s[i],   4) if sma5_s[i]   is not None else None,
            "sma_10":           round(sma10_s[i],  4) if sma10_s[i]  is not None else None,
            "sma_20":           round(sma20_s[i],  4) if sma20_s[i]  is not None else None,
            "sma_50":           round(sma50_s[i],  4) if sma50_s[i]  is not None else None,
            "sma_100":          round(sma100_s[i], 4) if sma100_s[i] is not None else None,
            "sma_200":          round(sma200_s[i], 4) if sma200_s[i] is not None else None,
            "ema_9":            round(ema9_s[i],   4) if ema9_s[i]   is not None else None,
            "ema_12":           round(ema12_s[i],  4) if ema12_s[i]  is not None else None,
            "ema_20":           round(ema20_s[i],  4) if ema20_s[i]  is not None else None,
            "ema_26":           round(ema26_s[i],  4) if ema26_s[i]  is not None else None,
            "ema_50":           round(ema50_s[i],  4) if ema50_s[i]  is not None else None,
            "ema_200":          round(ema200_s[i], 4) if ema200_s[i] is not None else None,

            # Prev-day MAs (for screener_universe yesterday's row)
            "sma_5_prev":       round(s5_prev,   4) if s5_prev   is not None else None,
            "sma_20_prev":      round(s20_prev,  4) if s20_prev  is not None else None,
            "sma_50_prev":      round(s50_prev,  4) if s50_prev  is not None else None,
            "sma_200_prev":     round(s200_prev, 4) if s200_prev is not None else None,

            # DMA ratios
            "dma_50_ratio":     dma_ratio(c, sma50_s[i]),
            "dma_200_ratio":    dma_ratio(c, sma200_s[i]),
            "price_to_sma20":   dma_ratio(c, sma20_s[i]),

            # MACD
            "macd_line":        round(macd_l_s[i],    6) if macd_l_s[i]    is not None else None,
            "macd_signal":      round(macd_sig_s[i],  6) if macd_sig_s[i]  is not None else None,
            "macd_hist":        round(macd_hist_s[i], 6) if macd_hist_s[i] is not None else None,
            "macd_line_prev":   macd_prev,
            "macd_signal_prev": macd_sig_prev,

            # RSI
            "rsi_7":            rsi7_s[i],
            "rsi_14":           rsi14_s[i],
            "rsi_21":           rsi21_s[i],

            # Stochastics
            "stoch_k":          stoch_k_s[i],
            "stoch_d":          stoch_d_s[i],

            # Bollinger
            "bb_upper":         bb_u_s[i],
            "bb_mid":           bb_m_s[i],
            "bb_lower":         bb_l_s[i],
            "bb_pct":           bb_pct_s[i],
            "bb_width":         bb_w_s[i],

            # ADX
            "adx":              adx_s[i],
            "di_plus":          pdi_s[i],
            "di_minus":         mdi_s[i],

            # CCI
            "cci":              cci_s[i],

            # Williams %R
            "williams_r":       wpr_s[i],

            # ROC
            "roc_10":           roc10_s[i],
            "roc_20":           roc20_s[i],

            # ATR
            "atr_14":           round(atr_s[i], 4) if atr_s[i] is not None else None,

            # OBV
            "obv":              obv_s[i],

            # VWAP
            "vwap_20d":         vwap_s[i],

            # CMF
            "cmf_20":           cmf_s[i],

            # MFI
            "mfi_14":           mfi_s[i],

            # Aroon
            "aroon_up":         aroon_up_s[i],
            "aroon_down":       aroon_dn_s[i],

            # 52-week
            "high_52w":         round(high_52w, 4) if high_52w else None,
            "low_52w":          round(low_52w,  4) if low_52w  else None,
            "pct_from_52w_high": pct_from_52wh,
            "pct_from_52w_low":  pct_from_52wl,

            # ATH / ATL
            "all_time_high":    round(ath, 4) if ath else None,
            "all_time_low":     round(atl, 4) if atl else None,
            "pct_from_ath":     pct_from_ath,
            "pct_from_atl":     pct_from_atl,

            # Returns
            "return_1d":        price_return(1),
            "return_5d":        price_return(5),
            "return_20d":       price_return(20),
            "return_60d":       price_return(60),

            # Signals
            "golden_cross":     golden_cross,
            "death_cross":      death_cross,
            "above_sma20":      c > sma20_s[i]  if sma20_s[i]  else None,
            "above_sma50":      c > sma50_s[i]  if sma50_s[i]  else None,
            "above_sma200":     c > sma200_s[i] if sma200_s[i] else None,
            "rsi_overbought":   rsi_overbought,
            "rsi_oversold":     rsi_oversold,
            "macd_bullish_cross": macd_bullish,
            "macd_bearish_cross": macd_bearish,

            "compute_version":  COMPUTE_VERSION,
            "computed_at":      datetime.utcnow(),
        })

    return results


# ─────────────────────────────────────────────────────────────
#  Upsert
# ─────────────────────────────────────────────────────────────

def upsert_daily(cur, rows: list[dict]) -> int:
    if not rows:
        return 0
    cols = list(rows[0].keys())
    vals = [[r.get(c) for c in cols] for r in rows]
    upd  = ", ".join([f"{c} = EXCLUDED.{c}"
                      for c in cols if c not in ("asx_code", "date")])
    sql  = f"""
        INSERT INTO market.daily_metrics ({', '.join(cols)})
        VALUES %s
        ON CONFLICT (asx_code, date) DO UPDATE SET {upd}
    """
    for start in range(0, len(vals), BATCH_SIZE):
        execute_values(cur, sql, vals[start:start + BATCH_SIZE], page_size=BATCH_SIZE)
    return len(rows)


# ─────────────────────────────────────────────────────────────
#  Main
# ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--codes",  nargs="+")
    parser.add_argument("--mode",   choices=["latest", "historical"], default="latest")
    parser.add_argument("--days",   type=int, default=1, help="Days back in latest mode")
    parser.add_argument("--date",   type=str, help="Specific date YYYY-MM-DD")
    args = parser.parse_args()

    specific_date = date.fromisoformat(args.date) if args.date else None
    target_dates_list = get_dates_to_compute(args.mode, args.days, specific_date)
    target_dates = set(target_dates_list)

    # Fetch enough history before the earliest target date for warmup (200+ days)
    from_date = min(target_dates) - timedelta(days=300)

    conn = psycopg2.connect(DB_URL)
    conn.autocommit = False
    cur  = conn.cursor(cursor_factory=RealDictCursor)

    if args.codes:
        codes = [c.upper() for c in args.codes]
    else:
        cur.execute("""
            SELECT asx_code FROM market.companies
            WHERE status = 'active' ORDER BY asx_code
        """)
        codes = [r["asx_code"] for r in cur.fetchall()]

    total = len(codes)
    mode_label = f"historical ({len(target_dates_list)} days)" if args.mode == "historical" else \
                 f"latest ({args.days}d)"
    log.info(f"compute_daily.py — {total} stocks, mode={mode_label}")

    done = failed = rows_written = 0

    for i, asx_code in enumerate(codes, 1):
        try:
            rows = fetch_price_history(cur, asx_code, from_date)
            if not rows:
                failed += 1
                continue

            computed = compute_daily_for_stock(asx_code, rows, target_dates)
            if computed:
                upsert_daily(cur, computed)
                rows_written += len(computed)
                done += 1
            else:
                failed += 1

        except Exception as e:
            conn.rollback()
            failed += 1
            log.warning(f"  {asx_code}: {e}")
            continue

        if i % COMMIT_EVERY == 0:
            conn.commit()
            log.info(f"  [{i:4d}/{total}] {done} done | {rows_written:,} rows")

    conn.commit()
    cur.close()
    conn.close()
    log.info(f"DONE — {done} stocks, {rows_written:,} rows. Failed: {failed}")


if __name__ == "__main__":
    main()
