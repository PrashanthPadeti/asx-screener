"""
ASX Screener — Weekly Compute Engine
======================================
Computes weekly metrics for all ASX stocks from market.daily_prices.
No API calls — pure computation from existing price history.

Output: market.weekly_metrics (one row per asx_code per week_date)

Metrics computed:
  - Weekly OHLCV bars   (aggregated from daily)
  - Returns             weekly, 4w, 13w, 52w
  - Moving averages     SMA 10w/20w/40w, EMA 13w/26w
  - RSI 14, RSI 7       (on weekly closes)
  - MACD (12,26,9)      (on weekly closes)
  - ATR 14              (weekly true range)
  - Bollinger Bands     (20, 2σ)
  - Volume              avg 4w, relative volume, OBV
  - Signals             golden_cross, death_cross, above_sma10w, above_sma40w

Usage:
    # Full historical backfill (all stocks, all weeks)
    python compute/engine/weekly_compute.py

    # Incremental — only recent weeks (e.g. Monday morning job)
    python compute/engine/weekly_compute.py --from-date 2026-04-21

    # Specific stocks only
    python compute/engine/weekly_compute.py --codes BHP CBA ANZ

    # Limit for testing
    python compute/engine/weekly_compute.py --limit 20
"""

import os
import sys
import logging
import argparse
from datetime import datetime, timezone, date, timedelta
from typing import Optional

import psycopg2
import psycopg2.extensions
from psycopg2.extras import execute_values
import pandas as pd
import numpy as np
from dotenv import load_dotenv

# Cast PostgreSQL NUMERIC → Python float automatically
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
BATCH_COMMIT    = 50      # commit every N stocks
WARMUP_WEEKS    = 60      # extra history needed for SMA 40w to stabilise


# ── Data Fetchers ─────────────────────────────────────────────────────────────

def fetch_codes(cur, codes: list = None, limit: int = None) -> list:
    """Return list of asx_codes to process."""
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


def fetch_daily_prices(cur, asx_code: str, from_date: str = None) -> pd.DataFrame:
    """
    Fetch daily OHLCV from market.daily_prices.
    If from_date given, fetch extra WARMUP_WEEKS of history so
    slow indicators (SMA 40w) are accurate from from_date onwards.
    """
    params = [asx_code]
    where  = ""
    if from_date:
        cutoff = (pd.to_datetime(from_date) - timedelta(weeks=WARMUP_WEEKS)).date()
        where  = "AND DATE(time AT TIME ZONE 'Australia/Sydney') >= %s"
        params.append(cutoff)

    cur.execute(f"""
        SELECT
            DATE(time AT TIME ZONE 'Australia/Sydney') AS day,
            open, high, low, close,
            COALESCE(volume, 0)::BIGINT AS volume
        FROM market.daily_prices
        WHERE asx_code = %s {where}
        ORDER BY time ASC
    """, params)

    rows = cur.fetchall()
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows, columns=["day", "open", "high", "low", "close", "volume"])
    df["day"] = pd.to_datetime(df["day"])
    df.set_index("day", inplace=True)
    df = df.apply(pd.to_numeric, errors="coerce")
    return df


# ── Indicator Calculations ────────────────────────────────────────────────────

def _nan_to_none(val):
    """Convert NaN / NaT / numpy scalars to Python None for psycopg2."""
    if val is None:
        return None
    if isinstance(val, (bool, np.bool_)):
        return bool(val)
    if isinstance(val, float) and np.isnan(val):
        return None
    if isinstance(val, (np.integer,)):
        return int(val)
    if isinstance(val, (np.floating,)):
        return None if np.isnan(val) else float(val)
    return val


def calc_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta    = series.diff()
    gain     = delta.clip(lower=0)
    loss     = (-delta).clip(lower=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs       = avg_gain / avg_loss.replace(0, np.nan)
    return (100 - (100 / (1 + rs))).round(4)


def calc_macd(series: pd.Series, fast=12, slow=26, signal=9):
    ema_fast    = series.ewm(span=fast,   adjust=False).mean()
    ema_slow    = series.ewm(span=slow,   adjust=False).mean()
    macd_line   = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist        = macd_line - signal_line
    return macd_line.round(4), signal_line.round(4), hist.round(4)


def calc_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(com=period - 1, min_periods=period).mean().round(4)


def calc_bollinger(series: pd.Series, period: int = 20, n_std: float = 2.0):
    sma     = series.rolling(period, min_periods=period).mean()
    std_dev = series.rolling(period, min_periods=period).std()
    upper   = (sma + n_std * std_dev).round(4)
    lower   = (sma - n_std * std_dev).round(4)
    width   = ((upper - lower) / sma.replace(0, np.nan)).round(4)
    pct     = ((series - lower) / (upper - lower).replace(0, np.nan)).round(4)
    return upper, lower, pct, width


# ── Weekly Computation ────────────────────────────────────────────────────────

def build_weekly_rows(asx_code: str, daily: pd.DataFrame,
                      from_date: Optional[str] = None) -> list[tuple]:
    """
    Resample daily OHLCV → weekly bars, compute all indicators,
    return list of tuples ready for execute_values INSERT.
    """
    if len(daily) < 5:          # need at least 1 full week
        return []

    # ── Weekly OHLCV bars (week starts Monday) ────────────────────────────────
    w = daily.resample("W-MON", label="left", closed="left").agg(
        open=("open",   "first"),
        high=("high",   "max"),
        low=("low",     "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
    ).dropna(subset=["close"])

    if len(w) < 2:
        return []

    close  = w["close"]
    high   = w["high"]
    low    = w["low"]
    volume = w["volume"]

    # ── Returns ───────────────────────────────────────────────────────────────
    ret_1w  = close.pct_change(1).round(6)
    ret_4w  = close.pct_change(4).round(6)
    ret_13w = close.pct_change(13).round(6)
    ret_52w = close.pct_change(52).round(6)

    # ── Moving averages ───────────────────────────────────────────────────────
    sma_10 = close.rolling(10, min_periods=10).mean().round(4)
    sma_20 = close.rolling(20, min_periods=20).mean().round(4)
    sma_40 = close.rolling(40, min_periods=40).mean().round(4)
    ema_13 = close.ewm(span=13, adjust=False).mean().round(4)
    ema_26 = close.ewm(span=26, adjust=False).mean().round(4)

    # ── Momentum indicators ───────────────────────────────────────────────────
    rsi_14     = calc_rsi(close, 14)
    rsi_7      = calc_rsi(close, 7)
    macd_l, macd_s, macd_h = calc_macd(close)

    # ── Volatility ────────────────────────────────────────────────────────────
    atr_14              = calc_atr(high, low, close, 14)
    bb_upper, bb_lower, bb_pct, bb_width = calc_bollinger(close, 20)

    # ── Volume ────────────────────────────────────────────────────────────────
    vol_avg_4w   = volume.rolling(4, min_periods=1).mean().round(0)
    rel_vol      = (volume / vol_avg_4w.replace(0, np.nan)).round(4)
    obv          = (volume * np.sign(close.diff()).fillna(0)).cumsum().round(0)

    # ── Signals ───────────────────────────────────────────────────────────────
    sma10_prev   = sma_10.shift(1)
    sma40_prev   = sma_40.shift(1)
    golden_cross = (sma_10 > sma_40) & (sma10_prev <= sma40_prev)
    death_cross  = (sma_10 < sma_40) & (sma10_prev >= sma40_prev)
    above_sma10  = close > sma_10
    above_sma40  = close > sma_40

    # ── Filter to from_date if incremental run ────────────────────────────────
    if from_date:
        w = w[w.index >= pd.to_datetime(from_date)]

    if w.empty:
        return []

    # ── Build row tuples ──────────────────────────────────────────────────────
    now  = datetime.now(tz=timezone.utc)
    rows = []

    for dt in w.index:
        def g(series, default=None):
            val = series.get(dt, default)
            return _nan_to_none(val)

        rows.append((
            asx_code,
            dt.date(),                     # week_date (Monday)
            g(w["open"]),
            g(high),
            g(low),
            g(close),
            int(g(volume)) if g(volume) is not None else None,
            g(ret_1w),
            g(ret_4w),
            g(ret_13w),
            g(ret_52w),
            g(sma_10),
            g(sma_20),
            g(sma_40),
            g(ema_13),
            g(ema_26),
            g(rsi_14),
            g(rsi_7),
            g(macd_l),
            g(macd_s),
            g(macd_h),
            g(atr_14),
            g(bb_upper),
            g(bb_lower),
            g(bb_pct),
            g(bb_width),
            int(g(vol_avg_4w)) if g(vol_avg_4w) is not None else None,
            g(rel_vol),
            int(g(obv)) if g(obv) is not None else None,
            bool(g(golden_cross, False)),
            bool(g(death_cross,  False)),
            bool(g(above_sma10,  False)),
            bool(g(above_sma40,  False)),
            COMPUTE_VERSION,
            now,
        ))

    return rows


# ── Database Write ────────────────────────────────────────────────────────────

INSERT_SQL = """
    INSERT INTO market.weekly_metrics (
        asx_code, week_date,
        open, high, low, close, volume,
        weekly_return, return_4w, return_13w, return_52w,
        sma_10w, sma_20w, sma_40w, ema_13w, ema_26w,
        rsi_14, rsi_7,
        macd_line, macd_signal, macd_hist,
        atr_14,
        bb_upper, bb_lower, bb_pct, bb_width,
        volume_avg_4w, relative_volume, obv,
        golden_cross, death_cross, above_sma10w, above_sma40w,
        compute_version, computed_at
    ) VALUES %s
    ON CONFLICT (asx_code, week_date) DO UPDATE SET
        open            = EXCLUDED.open,
        high            = EXCLUDED.high,
        low             = EXCLUDED.low,
        close           = EXCLUDED.close,
        volume          = EXCLUDED.volume,
        weekly_return   = EXCLUDED.weekly_return,
        return_4w       = EXCLUDED.return_4w,
        return_13w      = EXCLUDED.return_13w,
        return_52w      = EXCLUDED.return_52w,
        sma_10w         = EXCLUDED.sma_10w,
        sma_20w         = EXCLUDED.sma_20w,
        sma_40w         = EXCLUDED.sma_40w,
        ema_13w         = EXCLUDED.ema_13w,
        ema_26w         = EXCLUDED.ema_26w,
        rsi_14          = EXCLUDED.rsi_14,
        rsi_7           = EXCLUDED.rsi_7,
        macd_line       = EXCLUDED.macd_line,
        macd_signal     = EXCLUDED.macd_signal,
        macd_hist       = EXCLUDED.macd_hist,
        atr_14          = EXCLUDED.atr_14,
        bb_upper        = EXCLUDED.bb_upper,
        bb_lower        = EXCLUDED.bb_lower,
        bb_pct          = EXCLUDED.bb_pct,
        bb_width        = EXCLUDED.bb_width,
        volume_avg_4w   = EXCLUDED.volume_avg_4w,
        relative_volume = EXCLUDED.relative_volume,
        obv             = EXCLUDED.obv,
        golden_cross    = EXCLUDED.golden_cross,
        death_cross     = EXCLUDED.death_cross,
        above_sma10w    = EXCLUDED.above_sma10w,
        above_sma40w    = EXCLUDED.above_sma40w,
        compute_version = EXCLUDED.compute_version,
        computed_at     = EXCLUDED.computed_at
"""


def upsert_rows(cur, rows: list[tuple]) -> int:
    if not rows:
        return 0
    execute_values(cur, INSERT_SQL, rows, page_size=500)
    return len(rows)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="ASX Weekly Compute Engine")
    parser.add_argument("--codes",     nargs="+", help="Specific ASX codes")
    parser.add_argument("--from-date", help="Only compute weeks >= YYYY-MM-DD (incremental)")
    parser.add_argument("--limit",     type=int,  help="Max stocks to process")
    args = parser.parse_args()

    conn = psycopg2.connect(DB_URL)
    cur  = conn.cursor()

    codes = fetch_codes(cur, args.codes, args.limit)
    total = len(codes)
    log.info(f"Weekly compute — {total} stocks"
             + (f" from {args.from_date}" if args.from_date else " (full history)"))
    log.info("─" * 60)

    processed = skipped = errors = total_rows = 0

    for i, asx_code in enumerate(codes, 1):
        try:
            daily = fetch_daily_prices(cur, asx_code, args.from_date)
            if daily.empty:
                skipped += 1
                continue

            rows = build_weekly_rows(asx_code, daily, args.from_date)
            if not rows:
                skipped += 1
                continue

            n = upsert_rows(cur, rows)
            total_rows += n
            processed  += 1

            if i % BATCH_COMMIT == 0:
                conn.commit()
                log.info(f"  [{i:4d}/{total}] {processed} done | "
                         f"{skipped} skipped | {errors} errors | "
                         f"{total_rows:,} rows so far")

        except Exception as e:
            errors += 1
            log.warning(f"  {asx_code}: {e}")
            conn.rollback()   # prevent "transaction aborted" cascade to next stock

    conn.commit()
    cur.close()
    conn.close()

    log.info("─" * 60)
    log.info(f"Done! {processed} stocks | {skipped} skipped | "
             f"{errors} errors | {total_rows:,} rows upserted")


if __name__ == "__main__":
    main()
