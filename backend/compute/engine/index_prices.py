"""
ASX Index Prices Engine
=======================
Fetches daily OHLCV data for ASX benchmark and GICS sector indices from
Yahoo Finance, computes period returns and 52W range, then upserts into
market.index_prices.

Supported indices (our code → Yahoo Finance ticker):
    ASX20  → ^ATLI     ASX50  → ^AFLI     ASX100 → ^AXTO
    ASX200 → ^AXJO     ASX300 → ^AXKO     AXJO   → ^AXJO  (accumulation)
    AXFJ   → ^AXFJ     AXMJ   → ^AXMJ     AXEJ   → ^AXEJ   AXHJ   → ^AXHJ

Usage (standalone):
    python -m compute.engine.index_prices [--date YYYY-MM-DD] [--backfill-days N] [--dry-run]

Returns (via async function):
    await run(target_date, backfill_days, dry_run)
"""

import argparse
import asyncio
import logging
import os
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# ── Ticker mapping ────────────────────────────────────────────────────────────

TICKER_MAP: dict[str, str] = {
    "ASX20":  "^ATLI",
    "ASX50":  "^AFLI",
    "ASX100": "^AXTO",
    "ASX200": "^AXJO",
    "ASX300": "^AXKO",
    "AXJO":   "^AXJO",   # accumulation — same price series as ASX200 on Yahoo
    "AXFJ":   "^AXFJ",
    "AXMJ":   "^AXMJ",
    "AXEJ":   "^AXEJ",
    "AXHJ":   "^AXHJ",
}

# ── Return computation ────────────────────────────────────────────────────────

def _pct_return(series: pd.Series, current_idx: int, lookback: int) -> float | None:
    """Return (current - prior) / prior for a rolling lookback in trading days."""
    if current_idx < lookback:
        return None
    prior_idx = current_idx - lookback
    prior = series.iloc[prior_idx]
    current = series.iloc[current_idx]
    if prior is None or prior == 0 or pd.isna(prior) or pd.isna(current):
        return None
    return float((current - prior) / prior)


def _ytd_return(series: pd.Series, dates: pd.DatetimeIndex, current_idx: int) -> float | None:
    """Return from last trading day of prior year to current."""
    current_date = dates[current_idx]
    year_start = pd.Timestamp(current_date.year, 1, 1)
    prior_mask = dates < year_start
    if not prior_mask.any():
        return None
    prior_close = series[prior_mask].iloc[-1]
    current_close = series.iloc[current_idx]
    if prior_close == 0 or pd.isna(prior_close) or pd.isna(current_close):
        return None
    return float((current_close - prior_close) / prior_close)


def compute_rows(df: pd.DataFrame) -> list[dict]:
    """
    Given a DataFrame with columns [open, high, low, close, volume] indexed by date,
    return a list of dicts ready for upsert into market.index_prices.
    """
    closes = df["close"]
    dates = df.index

    rows = []
    for i in range(len(df)):
        row = df.iloc[i]
        close = row["close"]
        if pd.isna(close):
            continue

        # 52W range: up to 252 prior trading days
        window_start = max(0, i - 251)
        window = closes.iloc[window_start : i + 1].dropna()
        high_52w = float(window.max()) if len(window) >= 5 else None
        low_52w  = float(window.min()) if len(window) >= 5 else None

        rows.append({
            "price_date":  dates[i].date(),
            "close_price": float(close),
            "open_price":  float(row["open"])   if not pd.isna(row.get("open",  float("nan"))) else None,
            "high_price":  float(row["high"])   if not pd.isna(row.get("high",  float("nan"))) else None,
            "low_price":   float(row["low"])    if not pd.isna(row.get("low",   float("nan"))) else None,
            "volume":      int(row["volume"])   if not pd.isna(row.get("volume", float("nan"))) else None,
            "return_1d":   _pct_return(closes, i, 1),
            "return_1w":   _pct_return(closes, i, 5),
            "return_1m":   _pct_return(closes, i, 21),
            "return_3m":   _pct_return(closes, i, 63),
            "return_6m":   _pct_return(closes, i, 126),
            "return_1y":   _pct_return(closes, i, 252),
            "return_ytd":  _ytd_return(closes, dates, i),
            "high_52w":    high_52w,
            "low_52w":     low_52w,
        })
    return rows


# ── Fetch from Yahoo Finance ──────────────────────────────────────────────────

def fetch_index_data(
    ticker: str,
    start_date: date,
    end_date: date,
    retries: int = 3,
) -> pd.DataFrame | None:
    """Download OHLCV from Yahoo Finance. Returns None on failure."""
    import time
    try:
        import yfinance as yf
    except ImportError:
        log.error("yfinance not installed — run: pip install yfinance")
        return None

    for attempt in range(retries):
        try:
            t = yf.Ticker(ticker)
            hist = t.history(
                start=(start_date - timedelta(days=400)).isoformat(),
                end=(end_date + timedelta(days=1)).isoformat(),
                auto_adjust=True,
            )
            if hist.empty:
                log.warning(f"{ticker}: no data returned from Yahoo Finance")
                return None

            hist.index = hist.index.tz_localize(None)
            df = hist[["Open", "High", "Low", "Close", "Volume"]].copy()
            df.columns = ["open", "high", "low", "close", "volume"]
            return df.sort_index()

        except Exception as exc:
            msg = str(exc)
            if "Too Many Requests" in msg or "rate limit" in msg.lower():
                wait = 30 * (attempt + 1)
                log.warning(f"{ticker}: rate limited — waiting {wait}s (attempt {attempt+1}/{retries})")
                time.sleep(wait)
            else:
                log.warning(f"{ticker}: fetch failed — {exc}")
                return None

    log.warning(f"{ticker}: all {retries} attempts failed")
    return None


# ── DB upsert ─────────────────────────────────────────────────────────────────

async def upsert_rows(db, index_code: str, rows: list[dict], dry_run: bool) -> int:
    """Upsert a batch of price rows for one index. Returns count inserted/updated."""
    from sqlalchemy import text

    if not rows:
        return 0

    if dry_run:
        log.info(f"  [dry-run] would upsert {len(rows)} rows for {index_code}")
        return len(rows)

    for row in rows:
        await db.execute(text("""
            INSERT INTO market.index_prices (
                index_code, price_date,
                close_price, open_price, high_price, low_price, volume,
                return_1d, return_1w, return_1m, return_3m, return_6m,
                return_1y, return_ytd,
                high_52w, low_52w
            ) VALUES (
                :code, :price_date,
                :close_price, :open_price, :high_price, :low_price, :volume,
                :return_1d, :return_1w, :return_1m, :return_3m, :return_6m,
                :return_1y, :return_ytd,
                :high_52w, :low_52w
            )
            ON CONFLICT (index_code, price_date) DO UPDATE SET
                close_price  = EXCLUDED.close_price,
                open_price   = EXCLUDED.open_price,
                high_price   = EXCLUDED.high_price,
                low_price    = EXCLUDED.low_price,
                volume       = EXCLUDED.volume,
                return_1d    = EXCLUDED.return_1d,
                return_1w    = EXCLUDED.return_1w,
                return_1m    = EXCLUDED.return_1m,
                return_3m    = EXCLUDED.return_3m,
                return_6m    = EXCLUDED.return_6m,
                return_1y    = EXCLUDED.return_1y,
                return_ytd   = EXCLUDED.return_ytd,
                high_52w     = EXCLUDED.high_52w,
                low_52w      = EXCLUDED.low_52w
        """), {"code": index_code, **row})

    await db.commit()
    return len(rows)


# ── Main entry ────────────────────────────────────────────────────────────────

async def run(
    target_date: date | None = None,
    backfill_days: int = 1,
    dry_run: bool = False,
) -> None:
    """
    Fetch and store index prices.

    Args:
        target_date:   End date (inclusive). Defaults to today.
        backfill_days: How many calendar days back to fetch and upsert.
                       Use a large number (e.g. 1825) for an initial backfill.
        dry_run:       Print what would be written without touching the DB.
    """
    from app.db.session import AsyncSessionLocal

    if target_date is None:
        target_date = date.today()
    start_date = target_date - timedelta(days=backfill_days)

    log.info(f"Index prices: fetching {start_date} → {target_date} (dry_run={dry_run})")

    async with AsyncSessionLocal() as db:
        total_rows = 0
        for index_code, ticker in TICKER_MAP.items():
            log.info(f"  {index_code} ({ticker}) …")
            df = fetch_index_data(ticker, start_date, target_date)
            if df is None:
                continue

            # Filter to requested window
            df = df[df.index.date >= start_date]
            df = df[df.index.date <= target_date]
            if df.empty:
                log.info(f"  {index_code}: no rows in date range")
                continue

            rows = compute_rows(df)
            count = await upsert_rows(db, index_code, rows, dry_run)
            log.info(f"  {index_code}: {count} rows upserted")
            total_rows += count

    log.info(f"Index prices complete — {total_rows} total rows")


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest ASX index prices from Yahoo Finance")
    parser.add_argument("--date",          default=None,  help="Target date YYYY-MM-DD (default: today)")
    parser.add_argument("--backfill-days", type=int, default=3,
                        help="Calendar days to backfill (default: 3 for daily run; use 1825 for initial 5Y backfill)")
    parser.add_argument("--dry-run",       action="store_true", help="Print without writing to DB")
    args = parser.parse_args()

    target = date.fromisoformat(args.date) if args.date else date.today()

    DATABASE_URL = os.environ.get("DATABASE_URL", "")
    if not DATABASE_URL and not args.dry_run:
        log.error("DATABASE_URL not set")
        sys.exit(1)

    asyncio.run(run(target_date=target, backfill_days=args.backfill_days, dry_run=args.dry_run))
