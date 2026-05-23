"""
ASX Screener — Monthly Compute Engine
=======================================
Computes monthly metrics for all ASX stocks from market.daily_prices.
No API calls — pure computation from existing price history.

Output: market.monthly_metrics (one row per asx_code per month_date)

Metrics computed:
  - Monthly close / volume avg      (last close + avg daily volume of the month)
  - Returns                         1m, 3m, 6m, 12m, YTD
  - Momentum                        3m, 6m, 12m  (same as returns — price change %)
  - Volatility                      1m (~21d), 3m (~63d), 12m (~252d)
                                    annualised std of daily returns, sampled at month-end
  - RSI 14                          on monthly close series
  - MACD (12, 26, 9)               on monthly close series
  - Bollinger Bands (20, 2σ)        on monthly close series
  - SMA 12m                         12-month simple moving average
  - Price levels                    price_to_52w_high, drawdown_from_ath

Note: relative_strength_xjo and market_cap are left NULL
      (XJO prices not in DB; market cap needs shares outstanding × price).

Usage:
    # Full historical backfill
    python compute/engine/monthly_compute.py

    # Incremental — only recent months (run on 1st of each month)
    python compute/engine/monthly_compute.py --from-date 2026-04-01

    # Specific stocks only
    python compute/engine/monthly_compute.py --codes BHP CBA ANZ

    # Limit for testing
    python compute/engine/monthly_compute.py --limit 20
"""

import os
import sys
import logging
import argparse
from datetime import datetime, timezone
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
BATCH_COMMIT    = 50       # commit every N stocks
WARMUP_MONTHS   = 36       # extra history for MACD(26) + Bollinger(20) to stabilise


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
    If from_date given, fetch WARMUP_MONTHS of extra history so
    slow indicators (MACD 26m, Bollinger 20m) are accurate from from_date.
    """
    params = [asx_code]
    where  = ""
    if from_date:
        cutoff = (pd.to_datetime(from_date) - pd.DateOffset(months=WARMUP_MONTHS)).date()
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


def calc_bollinger(series: pd.Series, period: int = 20, n_std: float = 2.0):
    sma     = series.rolling(period, min_periods=period).mean()
    std_dev = series.rolling(period, min_periods=period).std()
    upper   = (sma + n_std * std_dev).round(4)
    lower   = (sma - n_std * std_dev).round(4)
    width   = ((upper - lower) / sma.replace(0, np.nan)).round(6)
    pct     = ((series - lower) / (upper - lower).replace(0, np.nan)).round(6)
    return upper, lower, pct, width


def calc_rolling_vol(daily_returns: pd.Series, window_days: int) -> pd.Series:
    """Annualised rolling volatility from daily returns (252 trading days/year)."""
    return (
        daily_returns
        .rolling(window_days, min_periods=max(5, window_days // 4))
        .std() * np.sqrt(252)
    ).round(6)


def calc_ytd(close_monthly: pd.Series) -> pd.Series:
    """
    YTD return for each month: close / last-December-close-of-prior-year - 1.
    month_date labels are first-of-month (e.g. 2024-03-01 = March 2024 bar).
    """
    ytd = pd.Series(index=close_monthly.index, dtype=float)

    for year in close_monthly.index.year.unique():
        # Base = December of (year - 1) in our monthly series
        dec_mask = (
            (close_monthly.index.year == year - 1) &
            (close_monthly.index.month == 12)
        )
        dec_vals = close_monthly[dec_mask]

        if not dec_vals.empty:
            base = dec_vals.iloc[-1]
        else:
            # Fallback: last available close before this year
            prior = close_monthly[close_monthly.index.year < year]
            base  = prior.iloc[-1] if not prior.empty else None

        if base is not None and base != 0 and not np.isnan(base):
            year_mask       = close_monthly.index.year == year
            ytd[year_mask]  = (close_monthly[year_mask] / base - 1)

    return ytd.round(6)


# ── Monthly Computation ───────────────────────────────────────────────────────

def build_monthly_rows(asx_code: str, daily: pd.DataFrame,
                       from_date: Optional[str] = None) -> list[tuple]:
    """
    Compute monthly metrics from daily OHLCV.
    Returns list of tuples ready for execute_values INSERT.
    """
    if len(daily) < 22:          # need at least 1 full month of trading days
        return []

    # ── Daily-based series (computed on full daily history, sampled at month-end)
    daily_ret = daily["close"].pct_change()

    # Annualised volatility at 3 horizons
    vol_1m_daily  = calc_rolling_vol(daily_ret, 21)
    vol_3m_daily  = calc_rolling_vol(daily_ret, 63)
    vol_12m_daily = calc_rolling_vol(daily_ret, 252)

    # All-time-high drawdown: (price - cummax) / cummax
    ath            = daily["close"].cummax()
    dd_daily       = ((daily["close"] - ath) / ath).round(6)

    # 52-week high ratio: price / rolling 252-day max
    high_52w_daily = daily["close"].rolling(252, min_periods=5).max()
    px52_daily     = (daily["close"] / high_52w_daily.replace(0, np.nan)).round(6)

    # ── Resample daily → monthly bars (month-start label, i.e. 2024-03-01 = March)
    m = daily.resample("MS").agg(
        open=("open",     "first"),
        high=("high",     "max"),
        low=("low",       "min"),
        close=("close",   "last"),    # end-of-month close
        volume=("volume", "mean"),    # avg daily volume for the month
    ).dropna(subset=["close"])

    if len(m) < 2:
        return []

    # Sample daily series at month-end (last day per month)
    vol_1m  = vol_1m_daily .resample("MS").last()
    vol_3m  = vol_3m_daily .resample("MS").last()
    vol_12m = vol_12m_daily.resample("MS").last()
    dd_ath  = dd_daily     .resample("MS").last()
    px_52w  = px52_daily   .resample("MS").last()

    close  = m["close"]
    volume = m["volume"]

    # ── Returns ───────────────────────────────────────────────────────────────
    ret_1m  = close.pct_change(1).round(6)
    ret_3m  = close.pct_change(3).round(6)
    ret_6m  = close.pct_change(6).round(6)
    ret_12m = close.pct_change(12).round(6)
    ret_ytd = calc_ytd(close)

    # ── Momentum (price change over horizon — same formula as returns) ─────────
    mom_3m  = ret_3m.copy()
    mom_6m  = ret_6m.copy()
    mom_12m = ret_12m.copy()

    # ── Moving average ────────────────────────────────────────────────────────
    sma_12 = close.rolling(12, min_periods=12).mean().round(4)

    # ── Technical indicators on monthly close bars ────────────────────────────
    rsi_14              = calc_rsi(close, 14)
    macd_l, macd_s, macd_h = calc_macd(close)
    _, _, bb_pct, bb_width  = calc_bollinger(close, 20)

    # ── Filter to from_date if incremental run ────────────────────────────────
    if from_date:
        m = m[m.index >= pd.to_datetime(from_date)]

    if m.empty:
        return []

    # ── Build row tuples ──────────────────────────────────────────────────────
    now  = datetime.now(tz=timezone.utc)
    rows = []

    for dt in m.index:
        def g(series, default=None):
            val = series.get(dt, default)
            return _nan_to_none(val)

        vol_avg = g(volume)

        rows.append((
            asx_code,
            dt.date(),                                                  # month_date
            g(close),                                                   # close
            int(round(vol_avg)) if vol_avg is not None else None,       # volume_avg (BIGINT)
            # Returns
            g(ret_1m),
            g(ret_3m),
            g(ret_6m),
            g(ret_12m),
            g(ret_ytd),
            # Momentum
            g(mom_3m),
            g(mom_6m),
            g(mom_12m),
            # Volatility (annualised)
            g(vol_1m),
            g(vol_3m),
            g(vol_12m),
            # Technicals
            g(rsi_14),
            g(macd_l),
            g(macd_s),
            g(macd_h),
            g(bb_pct),
            g(bb_width),
            # Price levels
            g(sma_12),
            g(px_52w),
            g(dd_ath),
            COMPUTE_VERSION,
            now,
        ))

    return rows


# ── Database Write ────────────────────────────────────────────────────────────

INSERT_SQL = """
    INSERT INTO market.monthly_metrics (
        asx_code, month_date,
        close, volume_avg,
        monthly_return, return_3m, return_6m, return_12m, return_ytd,
        momentum_3m, momentum_6m, momentum_12m,
        volatility_1m, volatility_3m, volatility_12m,
        rsi_14, macd_line, macd_signal, macd_hist,
        bb_pct, bb_width,
        sma_12m, price_to_52w_high, drawdown_from_ath,
        compute_version, computed_at
    ) VALUES %s
    ON CONFLICT (asx_code, month_date) DO UPDATE SET
        close             = EXCLUDED.close,
        volume_avg        = EXCLUDED.volume_avg,
        monthly_return    = EXCLUDED.monthly_return,
        return_3m         = EXCLUDED.return_3m,
        return_6m         = EXCLUDED.return_6m,
        return_12m        = EXCLUDED.return_12m,
        return_ytd        = EXCLUDED.return_ytd,
        momentum_3m       = EXCLUDED.momentum_3m,
        momentum_6m       = EXCLUDED.momentum_6m,
        momentum_12m      = EXCLUDED.momentum_12m,
        volatility_1m     = EXCLUDED.volatility_1m,
        volatility_3m     = EXCLUDED.volatility_3m,
        volatility_12m    = EXCLUDED.volatility_12m,
        rsi_14            = EXCLUDED.rsi_14,
        macd_line         = EXCLUDED.macd_line,
        macd_signal       = EXCLUDED.macd_signal,
        macd_hist         = EXCLUDED.macd_hist,
        bb_pct            = EXCLUDED.bb_pct,
        bb_width          = EXCLUDED.bb_width,
        sma_12m           = EXCLUDED.sma_12m,
        price_to_52w_high = EXCLUDED.price_to_52w_high,
        drawdown_from_ath = EXCLUDED.drawdown_from_ath,
        compute_version   = EXCLUDED.compute_version,
        computed_at       = EXCLUDED.computed_at
"""


def upsert_rows(cur, rows: list[tuple]) -> int:
    if not rows:
        return 0
    execute_values(cur, INSERT_SQL, rows, page_size=500)
    return len(rows)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="ASX Monthly Compute Engine")
    parser.add_argument("--codes",     nargs="+", help="Specific ASX codes")
    parser.add_argument("--from-date", help="Only compute months >= YYYY-MM-DD (incremental)")
    parser.add_argument("--limit",     type=int,  help="Max stocks to process")
    args = parser.parse_args()

    conn = psycopg2.connect(DB_URL)
    cur  = conn.cursor()

    codes = fetch_codes(cur, args.codes, args.limit)
    total = len(codes)
    log.info(f"Monthly compute — {total} stocks"
             + (f" from {args.from_date}" if args.from_date else " (full history)"))
    log.info("─" * 60)

    processed = skipped = errors = total_rows = 0

    for i, asx_code in enumerate(codes, 1):
        try:
            daily = fetch_daily_prices(cur, asx_code, args.from_date)
            if daily.empty:
                skipped += 1
                continue

            rows = build_monthly_rows(asx_code, daily, args.from_date)
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
            conn.rollback()   # prevent "transaction aborted" cascade

    conn.commit()
    cur.close()
    conn.close()

    log.info("─" * 60)
    log.info(f"Done! {processed} stocks | {skipped} skipped | "
             f"{errors} errors | {total_rows:,} rows upserted")


if __name__ == "__main__":
    main()
