"""
ASX Screener — Compute Monthly Metrics (Seq 5)
==============================================
Computes monthly price-based metrics from market.daily_prices:
  - Monthly returns and cumulative returns (3m, 6m, 12m, YTD)
  - Monthly momentum signals
  - Monthly historical volatility
  - RSI, MACD, Bollinger Bands on monthly bars
  - Market cap snapshot

Usage:
    python jobs/compute/compute_monthly.py              # Last 2 months
    python jobs/compute/compute_monthly.py --codes BHP CBA
    python jobs/compute/compute_monthly.py --mode historical  # All months from 2000
    python jobs/compute/compute_monthly.py --months 6         # Last N months
"""

import os
import math
import time
import logging
import argparse
import statistics
from datetime import date, datetime, timedelta
from typing import Optional
from calendar import monthrange

import psycopg2
from psycopg2.extras import execute_values, RealDictCursor
from dotenv import load_dotenv

load_dotenv()

DB_URL          = os.getenv("DATABASE_URL_SYNC",
                    "postgresql://asx_user:asx_secure_2024@localhost:5432/asx_screener")
COMPUTE_VERSION = "monthly_v1.0"
SLEEP_SEC       = 0.02

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
#  Technical indicator helpers (operating on arrays)
# ─────────────────────────────────────────────────────────────

def rsi(prices: list, period: int = 14) -> Optional[float]:
    if len(prices) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(prices)):
        diff = prices[i] - prices[i-1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - 100 / (1 + rs), 2)


def ema(prices: list, period: int) -> list:
    if len(prices) < period:
        return []
    k = 2 / (period + 1)
    result = [sum(prices[:period]) / period]
    for p in prices[period:]:
        result.append(p * k + result[-1] * (1 - k))
    return result


def macd(prices: list) -> tuple:
    """Returns (macd_line, signal, histogram) for latest bar."""
    e12 = ema(prices, 12)
    e26 = ema(prices, 26)
    if not e12 or not e26:
        return None, None, None
    # Align
    n = min(len(e12), len(e26))
    macd_line = [e12[-n+i] - e26[i] for i in range(n)]
    if len(macd_line) < 9:
        return None, None, None
    sig = ema(macd_line, 9)
    if not sig:
        return None, None, None
    ml  = round(macd_line[-1], 6)
    sl  = round(sig[-1], 6)
    return ml, sl, round(ml - sl, 6)


def bollinger(prices: list, period: int = 20, std_mult: float = 2.0) -> tuple:
    """Returns (upper, mid, lower, pct_b, width) for latest bar."""
    if len(prices) < period:
        return None, None, None, None, None
    window = prices[-period:]
    mid    = sum(window) / period
    std    = statistics.stdev(window)
    upper  = mid + std_mult * std
    lower  = mid - std_mult * std
    curr   = prices[-1]
    pct_b  = (curr - lower) / (upper - lower) if upper != lower else None
    width  = (upper - lower) / mid if mid else None
    return (round(upper, 4), round(mid, 4), round(lower, 4),
            round(pct_b, 4) if pct_b is not None else None,
            round(width, 4) if width is not None else None)


def annualised_vol(daily_returns: list) -> Optional[float]:
    if len(daily_returns) < 10:
        return None
    return round(statistics.stdev(daily_returns) * math.sqrt(252) * 100, 4)


# ─────────────────────────────────────────────────────────────
#  Fetch & compute per stock
# ─────────────────────────────────────────────────────────────

def fetch_daily(cur, asx_code: str, from_date: date) -> list[dict]:
    cur.execute("""
        SELECT time::date AS dt,
               adjusted_close AS close,
               volume
        FROM market.daily_prices
        WHERE asx_code = %s AND time::date >= %s
          AND adjusted_close IS NOT NULL
        ORDER BY time ASC
    """, (asx_code, from_date))
    return cur.fetchall()


def fetch_shares(cur, asx_code: str) -> Optional[int]:
    cur.execute("""
        SELECT shares_outstanding FROM financials.annual_balance_sheet
        WHERE asx_code = %s AND shares_outstanding IS NOT NULL
        ORDER BY fiscal_year DESC LIMIT 1
    """, (asx_code,))
    row = cur.fetchone()
    return row["shares_outstanding"] if row else None


def get_months_to_compute(mode: str, n_months: int) -> list[date]:
    """Return list of month start dates to compute (first day of month)."""
    today = date.today()
    if mode == "historical":
        start = date(2000, 1, 1)
    else:
        # Go back n_months from this month
        y, m = today.year, today.month
        months = []
        for _ in range(n_months):
            months.append(date(y, m, 1))
            m -= 1
            if m == 0:
                m = 12
                y -= 1
        return sorted(months)

    # Generate all month starts from start to today
    months = []
    y, m = start.year, start.month
    while date(y, m, 1) <= today:
        months.append(date(y, m, 1))
        m += 1
        if m > 12:
            m = 1
            y += 1
    return months


def compute_monthly_for_stock(asx_code: str, daily_rows: list[dict],
                               shares: Optional[int],
                               months: list[date]) -> list[dict]:
    """Compute monthly metrics from daily price data."""
    if not daily_rows:
        return []

    # Build date → price/volume dict
    price_map  = {r["dt"]: float(r["close"]) for r in daily_rows}
    vol_map    = {r["dt"]: r["volume"] for r in daily_rows}
    all_dates  = sorted(price_map.keys())
    all_prices = [price_map[d] for d in all_dates]

    # Month-end prices: last trading day of each month
    def month_end_price(yr, mo):
        last_day = monthrange(yr, mo)[1]
        target = date(yr, mo, last_day)
        # walk back to last available trading day
        for delta in range(10):
            d = target - timedelta(days=delta)
            if d in price_map:
                return price_map[d], d
        return None, None

    results = []
    for month_start in months:
        yr, mo = month_start.year, month_start.month
        close, end_date = month_end_price(yr, mo)
        if close is None:
            continue

        # Previous month end price (for monthly return)
        prev_mo = mo - 1 if mo > 1 else 12
        prev_yr = yr if mo > 1 else yr - 1
        prev_close, _ = month_end_price(prev_yr, prev_mo)
        monthly_ret = None
        if prev_close and prev_close > 0:
            monthly_ret = round((close - prev_close) / prev_close * 100, 4)

        # Multi-period returns: use month-end prices N months ago
        def ret_n_months(n):
            t_mo = mo - n
            t_yr = yr
            while t_mo <= 0:
                t_mo += 12
                t_yr -= 1
            p, _ = month_end_price(t_yr, t_mo)
            return round((close - p) / p * 100, 4) if p and p > 0 else None

        ret_3m  = ret_n_months(3)
        ret_6m  = ret_n_months(6)
        ret_12m = ret_n_months(12)

        # YTD return: from Jan 1 of current year
        jan_price, _ = month_end_price(yr, 1)
        # Actually get Dec 31 prior year
        dec_price, _ = month_end_price(yr - 1, 12)
        ret_ytd = round((close - dec_price) / dec_price * 100, 4) \
            if dec_price and dec_price > 0 else None

        # Get prices up to this month for technical indicators (monthly bars)
        hist_prices = [month_end_price(
            (mo - i - 1 + yr * 12) // 12,
            ((mo - i - 1) % 12) or 12
        )[0] for i in range(36)]
        hist_prices = [p for p in reversed(hist_prices) if p is not None]
        hist_prices.append(close)

        rsi_v = rsi(hist_prices, 14)
        ml, sl, mh = macd(hist_prices)
        bb_u, bb_m, bb_l, bb_p, bb_w = bollinger(hist_prices, 20)

        # 12-month SMA (using monthly prices)
        sma_12m = None
        if len(hist_prices) >= 12:
            sma_12m = round(sum(hist_prices[-12:]) / 12, 4)

        # Monthly volatility: from daily returns within this month
        month_prices_daily = [price_map[d] for d in all_dates
                               if d.year == yr and d.month == mo]
        daily_rets_1m = []
        for j in range(1, len(month_prices_daily)):
            if month_prices_daily[j-1] > 0:
                daily_rets_1m.append(math.log(
                    month_prices_daily[j] / month_prices_daily[j-1]))
        vol_1m = annualised_vol(daily_rets_1m)

        # 3-month volatility
        cutoff_3m = date(yr - (mo <= 3), ((mo - 4) % 12) + 1, 1)
        d3m = [price_map[d] for d in all_dates if d >= cutoff_3m and d <= end_date]
        dr3m = [math.log(d3m[j]/d3m[j-1]) for j in range(1, len(d3m)) if d3m[j-1] > 0]
        vol_3m = annualised_vol(dr3m)

        # 12-month volatility
        cutoff_12m = date(yr - 1, mo, 1)
        d12m = [price_map[d] for d in all_dates if d >= cutoff_12m and d <= end_date]
        dr12m = [math.log(d12m[j]/d12m[j-1]) for j in range(1, len(d12m)) if d12m[j-1] > 0]
        vol_12m = annualised_vol(dr12m)

        # Average monthly volume
        month_vols = [vol_map[d] for d in all_dates
                      if d.year == yr and d.month == mo and vol_map.get(d)]
        avg_vol = int(sum(month_vols) / len(month_vols)) if month_vols else None

        # Market cap
        mcap = round(close * shares / 1_000_000, 2) if shares else None

        # Price to 52w high
        cutoff_52w = end_date - timedelta(days=365)
        prices_52w = [price_map[d] for d in all_dates if cutoff_52w <= d <= end_date]
        high_52w   = max(prices_52w) if prices_52w else None
        p_to_52wh  = round(close / high_52w, 4) if high_52w and high_52w > 0 else None

        # ATH drawdown
        ath = max(all_prices[:all_dates.index(end_date) + 1]) if end_date in price_map else None
        drawdown = round((close - ath) / ath * 100, 4) if ath and ath > 0 else None

        results.append({
            "asx_code":           asx_code,
            "month_date":         month_start,
            "close":              round(close, 4),
            "volume_avg":         avg_vol,
            "market_cap":         mcap,
            "monthly_return":     monthly_ret,
            "return_3m":          ret_3m,
            "return_6m":          ret_6m,
            "return_12m":         ret_12m,
            "return_ytd":         ret_ytd,
            "momentum_3m":        ret_3m,
            "momentum_6m":        ret_6m,
            "momentum_12m":       ret_12m,
            "relative_strength_xjo": None,   # computed separately vs XJO
            "volatility_1m":      vol_1m,
            "volatility_3m":      vol_3m,
            "volatility_12m":     vol_12m,
            "rsi_14":             rsi_v,
            "macd_line":          ml,
            "macd_signal":        sl,
            "macd_hist":          mh,
            "bb_pct":             bb_p,
            "bb_width":           bb_w,
            "sma_12m":            sma_12m,
            "price_to_52w_high":  p_to_52wh,
            "drawdown_from_ath":  drawdown,
            "compute_version":    COMPUTE_VERSION,
            "computed_at":        datetime.utcnow(),
        })

    return results


def upsert_monthly(cur, rows: list[dict]) -> int:
    if not rows:
        return 0
    cols = list(rows[0].keys())
    vals = [[r.get(c) for c in cols] for r in rows]
    upd  = ", ".join([f"{c} = EXCLUDED.{c}"
                      for c in cols if c not in ("asx_code", "month_date")])
    sql  = f"""
        INSERT INTO market.monthly_metrics ({', '.join(cols)})
        VALUES %s
        ON CONFLICT (asx_code, month_date) DO UPDATE SET {upd}
    """
    execute_values(cur, sql, vals, page_size=1000)
    return len(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--codes",  nargs="+")
    parser.add_argument("--mode",   choices=["latest", "historical"], default="latest")
    parser.add_argument("--months", type=int, default=2, help="Months back in latest mode")
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

    months = get_months_to_compute(args.mode, args.months)
    from_date = months[0] - timedelta(days=400)  # fetch extra history for indicators

    total = len(codes)
    log.info(f"compute_monthly.py — {total} stocks, {len(months)} months, mode={args.mode}")

    done = failed = rows_written = 0

    for i, asx_code in enumerate(codes, 1):
        try:
            daily  = fetch_daily(cur, asx_code, from_date)
            shares = fetch_shares(cur, asx_code)

            computed = compute_monthly_for_stock(asx_code, daily, shares, months)
            if computed:
                upsert_monthly(cur, computed)
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
