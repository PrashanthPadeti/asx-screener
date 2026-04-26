"""
ASX Screener — Compute Weekly Metrics (Seq 6)
=============================================
Aggregates daily OHLCV into weekly bars and computes:
  - Weekly returns and multi-week returns
  - RSI, MACD, Stochastics on weekly bars
  - ADX, Aroon trend indicators
  - Bollinger Bands on weekly bars
  - Volume indicators
  - Golden/death cross signals

Usage:
    python jobs/compute/compute_weekly.py              # Last 2 weeks
    python jobs/compute/compute_weekly.py --codes BHP
    python jobs/compute/compute_weekly.py --mode historical
    python jobs/compute/compute_weekly.py --weeks 8
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
COMPUTE_VERSION = "weekly_v1.0"
SLEEP_SEC       = 0.02

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
#  Indicator helpers
# ─────────────────────────────────────────────────────────────

def ema_series(values: list, period: int) -> list:
    if len(values) < period:
        return []
    k = 2 / (period + 1)
    out = [sum(values[:period]) / period]
    for v in values[period:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def rsi_series(closes: list, period: int = 14) -> list:
    """Returns RSI for each bar after period."""
    if len(closes) < period + 1:
        return []
    gains = [max(closes[i] - closes[i-1], 0) for i in range(1, len(closes))]
    losses = [max(closes[i-1] - closes[i], 0) for i in range(1, len(closes))]
    result = []
    avg_g = sum(gains[:period]) / period
    avg_l = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_g = (avg_g * (period - 1) + gains[i]) / period
        avg_l = (avg_l * (period - 1) + losses[i]) / period
        rs = avg_g / avg_l if avg_l != 0 else float('inf')
        result.append(round(100 - 100 / (1 + rs), 2))
    return result


def stochastic(highs, lows, closes, k_period=14, d_period=3) -> tuple:
    """Returns latest (%K, %D)."""
    if len(closes) < k_period:
        return None, None
    k_vals = []
    for i in range(k_period - 1, len(closes)):
        h = max(highs[i - k_period + 1:i + 1])
        l = min(lows[i - k_period + 1:i + 1])
        if h == l:
            k_vals.append(50.0)
        else:
            k_vals.append(round((closes[i] - l) / (h - l) * 100, 2))
    if not k_vals:
        return None, None
    d_vals = [sum(k_vals[max(0, i-d_period+1):i+1]) / min(i+1, d_period)
              for i in range(len(k_vals))]
    return k_vals[-1], round(d_vals[-1], 2)


def adx_series(highs, lows, closes, period=14) -> tuple:
    """Returns latest (ADX, +DI, -DI)."""
    if len(closes) < period + 1:
        return None, None, None
    tr_list, pdm_list, ndm_list = [], [], []
    for i in range(1, len(closes)):
        hl = highs[i] - lows[i]
        hc = abs(highs[i] - closes[i-1])
        lc = abs(lows[i] - closes[i-1])
        tr_list.append(max(hl, hc, lc))
        pdm = highs[i] - highs[i-1] if highs[i] > highs[i-1] else 0
        ndm = lows[i-1] - lows[i]   if lows[i] < lows[i-1]   else 0
        if pdm > ndm:
            ndm = 0
        elif ndm > pdm:
            pdm = 0
        pdm_list.append(pdm)
        ndm_list.append(ndm)

    if len(tr_list) < period:
        return None, None, None

    atr_sm = sum(tr_list[:period])
    pdm_sm = sum(pdm_list[:period])
    ndm_sm = sum(ndm_list[:period])
    dx_vals = []
    for i in range(period, len(tr_list)):
        atr_sm = atr_sm - atr_sm / period + tr_list[i]
        pdm_sm = pdm_sm - pdm_sm / period + pdm_list[i]
        ndm_sm = ndm_sm - ndm_sm / period + ndm_list[i]
        pdi = 100 * pdm_sm / atr_sm if atr_sm else 0
        ndi = 100 * ndm_sm / atr_sm if atr_sm else 0
        dx = 100 * abs(pdi - ndi) / (pdi + ndi) if (pdi + ndi) else 0
        dx_vals.append((dx, pdi, ndi))

    if not dx_vals:
        return None, None, None

    # Smooth DX to get ADX
    adx_val = sum(d[0] for d in dx_vals[:period]) / period
    for d in dx_vals[period:]:
        adx_val = (adx_val * (period - 1) + d[0]) / period

    return round(adx_val, 2), round(dx_vals[-1][1], 2), round(dx_vals[-1][2], 2)


def aroon(highs, lows, period=25) -> tuple:
    """Returns latest (aroon_up, aroon_down)."""
    if len(highs) < period + 1:
        return None, None
    h_window = highs[-period-1:]
    l_window = lows[-period-1:]
    periods_since_high = period - h_window.index(max(h_window))
    periods_since_low  = period - l_window.index(min(l_window))
    up   = round((period - periods_since_high) / period * 100, 2)
    down = round((period - periods_since_low)  / period * 100, 2)
    return up, down


def cci(highs, lows, closes, period=20) -> Optional[float]:
    if len(closes) < period:
        return None
    tp = [(highs[i] + lows[i] + closes[i]) / 3 for i in range(len(closes))]
    tp_window = tp[-period:]
    tp_mean = sum(tp_window) / period
    md = sum(abs(v - tp_mean) for v in tp_window) / period
    return round((tp[-1] - tp_mean) / (0.015 * md), 4) if md else None


def williams_r(highs, lows, closes, period=14) -> Optional[float]:
    if len(closes) < period:
        return None
    h = max(highs[-period:])
    l = min(lows[-period:])
    return round(-100 * (h - closes[-1]) / (h - l), 2) if h != l else None


def atr(highs, lows, closes, period=14) -> Optional[float]:
    if len(closes) < 2:
        return None
    trs = [max(highs[i] - lows[i],
               abs(highs[i] - closes[i-1]),
               abs(lows[i]  - closes[i-1]))
           for i in range(1, len(closes))]
    if len(trs) < period:
        return None
    # Wilder smoothing
    atr_val = sum(trs[:period]) / period
    for tr in trs[period:]:
        atr_val = (atr_val * (period - 1) + tr) / period
    return round(atr_val, 4)


def obv_series(closes, volumes) -> int:
    """Returns latest OBV."""
    obv_val = 0
    for i in range(1, len(closes)):
        v = volumes[i] or 0
        if closes[i] > closes[i-1]:
            obv_val += v
        elif closes[i] < closes[i-1]:
            obv_val -= v
    return obv_val


# ─────────────────────────────────────────────────────────────
#  Weekly bar aggregation
# ─────────────────────────────────────────────────────────────

def to_monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def aggregate_to_weekly(daily_rows: list[dict]) -> dict:
    """Group daily rows into weekly OHLCV dict keyed by Monday."""
    weekly = {}
    for r in daily_rows:
        d     = r["dt"]
        week  = to_monday(d)
        price = float(r["close"] or 0)
        vol   = r["volume"] or 0
        if week not in weekly:
            weekly[week] = {"open": price, "high": price, "low": price,
                            "close": price, "volume": vol, "days": [r]}
        else:
            wk = weekly[week]
            wk["high"]   = max(wk["high"], price)
            wk["low"]    = min(wk["low"],  price)
            wk["close"]  = price
            wk["volume"] += vol
            wk["days"].append(r)
    return weekly


def get_weeks_to_compute(mode: str, n_weeks: int) -> list[date]:
    today  = date.today()
    monday = to_monday(today)
    if mode == "historical":
        start = date(2000, 1, 3)   # first Monday in 2000
        weeks = []
        d = start
        while d <= monday:
            weeks.append(d)
            d += timedelta(weeks=1)
        return weeks
    else:
        return [monday - timedelta(weeks=i) for i in range(n_weeks - 1, -1, -1)]


def compute_weekly_for_stock(asx_code: str, daily_rows: list[dict],
                              shares: Optional[int],
                              weeks: list[date]) -> list[dict]:
    if not daily_rows:
        return []

    weekly_bars = aggregate_to_weekly(daily_rows)
    sorted_weeks = sorted(weekly_bars.keys())

    all_closes  = [weekly_bars[w]["close"]  for w in sorted_weeks]
    all_highs   = [weekly_bars[w]["high"]   for w in sorted_weeks]
    all_lows    = [weekly_bars[w]["low"]    for w in sorted_weeks]
    all_volumes = [weekly_bars[w]["volume"] for w in sorted_weeks]

    # Pre-compute indicator series
    rsi14_series  = rsi_series(all_closes, 14)
    rsi7_series   = rsi_series(all_closes, 7)
    ema13_series  = ema_series(all_closes, 13)
    ema26_series  = ema_series(all_closes, 26)
    sma10_series  = [sum(all_closes[max(0,i-9):i+1]) / min(i+1,10)
                     for i in range(len(all_closes))]
    sma20_series  = [sum(all_closes[max(0,i-19):i+1]) / min(i+1,20)
                     for i in range(len(all_closes))]
    sma40_series  = [sum(all_closes[max(0,i-39):i+1]) / min(i+1,40)
                     for i in range(len(all_closes))]

    # MACD on weekly closes
    macd_vals = []
    if len(all_closes) >= 26:
        e12 = ema_series(all_closes, 12)
        e26 = ema_series(all_closes, 26)
        n   = min(len(e12), len(e26))
        ml_series = [e12[-n+j] - e26[j] for j in range(n)]
        sig_series = ema_series(ml_series, 9)
        if sig_series:
            macd_vals = list(zip(ml_series[-len(sig_series):], sig_series))

    results = []
    for week in weeks:
        if week not in weekly_bars:
            continue
        idx = sorted_weeks.index(week)
        wk  = weekly_bars[week]

        close  = wk["close"]
        high   = wk["high"]
        low    = wk["low"]
        vol    = wk["volume"]

        # Returns
        prev_close  = all_closes[idx - 1] if idx > 0 else None
        weekly_ret  = round((close - prev_close) / prev_close * 100, 4) \
                      if prev_close and prev_close > 0 else None

        def ret_n_weeks(n):
            i = idx - n
            if i < 0 or all_closes[i] <= 0:
                return None
            return round((close - all_closes[i]) / all_closes[i] * 100, 4)

        ret_4w  = ret_n_weeks(4)
        ret_13w = ret_n_weeks(13)
        ret_52w = ret_n_weeks(52)

        # Technical indicators
        rsi14 = rsi14_series[idx - (len(all_closes) - len(rsi14_series))] \
                if idx >= len(all_closes) - len(rsi14_series) else None
        rsi7  = rsi7_series[idx - (len(all_closes) - len(rsi7_series))] \
                if idx >= len(all_closes) - len(rsi7_series) else None

        stoch_k, stoch_d = stochastic(
            all_highs[:idx+1], all_lows[:idx+1], all_closes[:idx+1])

        adx_v, pdi, ndi = adx_series(
            all_highs[:idx+1], all_lows[:idx+1], all_closes[:idx+1])

        aroon_up, aroon_down = aroon(all_highs[:idx+1], all_lows[:idx+1])

        cci_v  = cci(all_highs[:idx+1], all_lows[:idx+1], all_closes[:idx+1])
        wpr    = williams_r(all_highs[:idx+1], all_lows[:idx+1], all_closes[:idx+1])
        atr_v  = atr(all_highs[:idx+1], all_lows[:idx+1], all_closes[:idx+1])

        # Bollinger Bands (20-period weekly)
        bb_window = all_closes[max(0, idx-19):idx+1]
        if len(bb_window) >= 10:
            bb_mid  = sum(bb_window) / len(bb_window)
            bb_std  = statistics.stdev(bb_window) if len(bb_window) > 1 else 0
            bb_u    = round(bb_mid + 2 * bb_std, 4)
            bb_l    = round(bb_mid - 2 * bb_std, 4)
            bb_m    = round(bb_mid, 4)
            bb_p    = round((close - bb_l) / (bb_u - bb_l), 4) if bb_u != bb_l else None
            bb_w    = round((bb_u - bb_l) / bb_mid, 4) if bb_mid else None
        else:
            bb_u = bb_m = bb_l = bb_p = bb_w = None

        # MACD
        ml = sl = mh = None
        if macd_vals:
            macd_idx = idx - (len(all_closes) - len(macd_vals))
            if 0 <= macd_idx < len(macd_vals):
                ml = round(macd_vals[macd_idx][0], 6)
                sl = round(macd_vals[macd_idx][1], 6)
                mh = round(ml - sl, 6)

        # Moving averages
        sma10 = round(sma10_series[idx], 4) if idx < len(sma10_series) else None
        sma20 = round(sma20_series[idx], 4) if idx < len(sma20_series) else None
        sma40 = round(sma40_series[idx], 4) if idx < len(sma40_series) else None

        ema13_off = idx - (len(all_closes) - len(ema13_series))
        ema13 = round(ema13_series[ema13_off], 4) \
                if ema13_off >= 0 and ema13_off < len(ema13_series) else None
        ema26_off = idx - (len(all_closes) - len(ema26_series))
        ema26 = round(ema26_series[ema26_off], 4) \
                if ema26_off >= 0 and ema26_off < len(ema26_series) else None

        # Signals
        prev_sma10 = sma10_series[idx-1] if idx > 0 and idx-1 < len(sma10_series) else None
        prev_sma40 = sma40_series[idx-1] if idx > 0 and idx-1 < len(sma40_series) else None
        golden_cross = (sma10 and sma40 and prev_sma10 and prev_sma40
                        and sma10 > sma40 and prev_sma10 <= prev_sma40)
        death_cross  = (sma10 and sma40 and prev_sma10 and prev_sma40
                        and sma10 < sma40 and prev_sma10 >= prev_sma40)

        # Volume metrics
        vol_window = all_volumes[max(0, idx-3):idx+1]
        vol_avg_4w = int(sum(vol_window) / len(vol_window)) if vol_window else None
        rel_vol = round(vol / vol_avg_4w, 4) if vol_avg_4w and vol_avg_4w > 0 else None

        obv_v = obv_series(all_closes[:idx+1], all_volumes[:idx+1])

        # Market cap
        mcap = round(close * shares / 1_000_000, 2) if shares else None

        results.append({
            "asx_code":       asx_code,
            "week_date":      week,
            "open":           round(wk["open"], 4),
            "high":           round(high, 4),
            "low":            round(low, 4),
            "close":          round(close, 4),
            "volume":         vol,
            "market_cap":     mcap,
            "weekly_return":  weekly_ret,
            "return_4w":      ret_4w,
            "return_13w":     ret_13w,
            "return_52w":     ret_52w,
            "adx_14":         adx_v,
            "plus_di":        pdi,
            "minus_di":       ndi,
            "aroon_up":       aroon_up,
            "aroon_down":     aroon_down,
            "rsi_14":         rsi14,
            "rsi_7":          rsi7,
            "macd_line":      ml,
            "macd_signal":    sl,
            "macd_hist":      mh,
            "stoch_k":        stoch_k,
            "stoch_d":        stoch_d,
            "cci_20":         cci_v,
            "williams_r":     wpr,
            "sma_10w":        sma10,
            "sma_20w":        sma20,
            "sma_40w":        sma40,
            "ema_13w":        ema13,
            "ema_26w":        ema26,
            "atr_14":         atr_v,
            "bb_upper":       bb_u,
            "bb_lower":       bb_l,
            "bb_pct":         bb_p,
            "bb_width":       bb_w,
            "volume_avg_4w":  vol_avg_4w,
            "relative_volume": rel_vol,
            "obv":            obv_v,
            "golden_cross":   bool(golden_cross),
            "death_cross":    bool(death_cross),
            "above_sma10w":   close > sma10 if sma10 else None,
            "above_sma40w":   close > sma40 if sma40 else None,
            "compute_version": COMPUTE_VERSION,
            "computed_at":    datetime.utcnow(),
        })

    return results


def upsert_weekly(cur, rows: list[dict]) -> int:
    if not rows:
        return 0
    cols = list(rows[0].keys())
    vals = [[r.get(c) for c in cols] for r in rows]
    upd  = ", ".join([f"{c} = EXCLUDED.{c}"
                      for c in cols if c not in ("asx_code", "week_date")])
    sql  = f"""
        INSERT INTO market.weekly_metrics ({', '.join(cols)})
        VALUES %s
        ON CONFLICT (asx_code, week_date) DO UPDATE SET {upd}
    """
    execute_values(cur, sql, vals, page_size=1000)
    return len(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--codes", nargs="+")
    parser.add_argument("--mode",  choices=["latest", "historical"], default="latest")
    parser.add_argument("--weeks", type=int, default=2)
    args = parser.parse_args()

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

    weeks     = get_weeks_to_compute(args.mode, args.weeks)
    from_date = weeks[0] - timedelta(weeks=60)   # extra history for indicators

    total = len(codes)
    log.info(f"compute_weekly.py — {total} stocks, {len(weeks)} weeks, mode={args.mode}")

    done = failed = rows_written = 0

    for i, asx_code in enumerate(codes, 1):
        try:
            cur.execute("""
                SELECT time::date AS dt, adjusted_close AS close, high, low, volume
                FROM market.daily_prices
                WHERE asx_code = %s AND time::date >= %s
                  AND adjusted_close IS NOT NULL
                ORDER BY time ASC
            """, (asx_code, from_date))
            daily = cur.fetchall()

            cur.execute("""
                SELECT shares_outstanding FROM financials.annual_balance_sheet
                WHERE asx_code = %s AND shares_outstanding IS NOT NULL
                ORDER BY fiscal_year DESC LIMIT 1
            """, (asx_code,))
            sh_row = cur.fetchone()
            shares = sh_row["shares_outstanding"] if sh_row else None

            computed = compute_weekly_for_stock(asx_code, daily, shares, weeks)
            if computed:
                upsert_weekly(cur, computed)
                rows_written += len(computed)
                done += 1
            else:
                failed += 1

        except Exception as e:
            conn.rollback()
            failed += 1
            log.warning(f"  {asx_code}: {e}")
            continue

        if i % 100 == 0:
            conn.commit()
            log.info(f"  [{i:4d}/{total}] {done} done | {rows_written:,} rows")

        time.sleep(SLEEP_SEC)

    conn.commit()
    cur.close()
    conn.close()
    log.info(f"DONE — {done} stocks, {rows_written:,} rows. Failed: {failed}")


if __name__ == "__main__":
    main()
