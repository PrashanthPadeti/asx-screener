"""
Global Markets Engine
=====================
Fetches daily OHLCV for global equity indices and AUD FX rates from Yahoo Finance,
computes period returns and 52W range, then upserts into:
  market.global_index_prices  and  market.fx_rates

Global Indices (our code → Yahoo Finance ticker):
    SP500   → ^GSPC      NDX100 → ^NDX      DJIA   → ^DJI
    FTSE100 → ^FTSE      DAX    → ^GDAXI    CAC40  → ^FCHI
    NKY225  → ^N225      HSI    → ^HSI      SHCOMP → 000001.SS    KOSPI → ^KS11

FX pairs (AUD base):
    AUDUSD → AUDUSD=X    AUDEUR → AUDEUR=X    AUDGBP → AUDGBP=X
    AUDJPY → AUDJPY=X    AUDCNY → AUDCNY=X

Usage (standalone):
    python -m compute.engine.global_markets [--date YYYY-MM-DD] [--backfill-days N] [--dry-run]
"""

import argparse
import asyncio
import logging
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# ── Config ────────────────────────────────────────────────────────────────────

GLOBAL_INDICES = [
    # US
    {"code": "SP500",   "name": "S&P 500",           "region": "US",     "country": "United States",  "currency": "USD", "ticker": "^GSPC"},
    {"code": "NDX100",  "name": "NASDAQ 100",         "region": "US",     "country": "United States",  "currency": "USD", "ticker": "^NDX"},
    {"code": "DJIA",    "name": "Dow Jones",          "region": "US",     "country": "United States",  "currency": "USD", "ticker": "^DJI"},
    # Europe
    {"code": "FTSE100", "name": "FTSE 100",           "region": "Europe", "country": "United Kingdom", "currency": "GBP", "ticker": "^FTSE"},
    {"code": "DAX",     "name": "DAX",                "region": "Europe", "country": "Germany",        "currency": "EUR", "ticker": "^GDAXI"},
    {"code": "CAC40",   "name": "CAC 40",             "region": "Europe", "country": "France",         "currency": "EUR", "ticker": "^FCHI"},
    # Asia
    {"code": "NKY225",  "name": "Nikkei 225",         "region": "Asia",   "country": "Japan",          "currency": "JPY", "ticker": "^N225"},
    {"code": "HSI",     "name": "Hang Seng",          "region": "Asia",   "country": "Hong Kong",      "currency": "HKD", "ticker": "^HSI"},
    {"code": "SHCOMP",  "name": "Shanghai Composite", "region": "Asia",   "country": "China",          "currency": "CNY", "ticker": "000001.SS"},
    {"code": "KOSPI",   "name": "KOSPI",              "region": "Asia",   "country": "South Korea",    "currency": "KRW", "ticker": "^KS11"},
]

FX_PAIRS = [
    {"pair": "AUDUSD", "name": "AUD/USD", "ticker": "AUDUSD=X"},
    {"pair": "AUDEUR", "name": "AUD/EUR", "ticker": "AUDEUR=X"},
    {"pair": "AUDGBP", "name": "AUD/GBP", "ticker": "AUDGBP=X"},
    {"pair": "AUDJPY", "name": "AUD/JPY", "ticker": "AUDJPY=X"},
    {"pair": "AUDCNY", "name": "AUD/CNY", "ticker": "AUDCNY=X"},
]

# ── Return computation ────────────────────────────────────────────────────────

def _pct_return(series: pd.Series, current_idx: int, lookback: int) -> float | None:
    if current_idx < lookback:
        return None
    prior = series.iloc[current_idx - lookback]
    current = series.iloc[current_idx]
    if prior is None or prior == 0 or pd.isna(prior) or pd.isna(current):
        return None
    return float((current - prior) / prior)


def _ytd_return(series: pd.Series, dates: pd.DatetimeIndex, current_idx: int) -> float | None:
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


def compute_price_rows(df: pd.DataFrame) -> list[dict]:
    closes = df["close"]
    dates = df.index
    rows = []
    for i in range(len(df)):
        row = df.iloc[i]
        close = row["close"]
        if pd.isna(close):
            continue
        window_start = max(0, i - 251)
        window = closes.iloc[window_start : i + 1].dropna()
        high_52w = float(window.max()) if len(window) >= 5 else None
        low_52w  = float(window.min()) if len(window) >= 5 else None
        rows.append({
            "price_date":  dates[i].date(),
            "close_price": float(close),
            "open_price":  float(row["open"])   if not pd.isna(row.get("open",   float("nan"))) else None,
            "high_price":  float(row["high"])   if not pd.isna(row.get("high",   float("nan"))) else None,
            "low_price":   float(row["low"])    if not pd.isna(row.get("low",    float("nan"))) else None,
            "volume":      int(row["volume"])   if not pd.isna(row.get("volume", float("nan"))) else None,
            "return_1d":  _pct_return(closes, i, 1),
            "return_1w":  _pct_return(closes, i, 5),
            "return_1m":  _pct_return(closes, i, 21),
            "return_3m":  _pct_return(closes, i, 63),
            "return_6m":  _pct_return(closes, i, 126),
            "return_1y":  _pct_return(closes, i, 252),
            "return_ytd": _ytd_return(closes, dates, i),
            "high_52w":   high_52w,
            "low_52w":    low_52w,
        })
    return rows


def compute_fx_rows(df: pd.DataFrame) -> list[dict]:
    rates = df["close"]
    dates = df.index
    rows = []
    for i in range(len(df)):
        row = df.iloc[i]
        rate = row["close"]
        if pd.isna(rate):
            continue
        rows.append({
            "rate_date":  dates[i].date(),
            "rate":       float(rate),
            "open_rate":  float(row["open"]) if not pd.isna(row.get("open", float("nan"))) else None,
            "high_rate":  float(row["high"]) if not pd.isna(row.get("high", float("nan"))) else None,
            "low_rate":   float(row["low"])  if not pd.isna(row.get("low",  float("nan"))) else None,
            "return_1d":  _pct_return(rates, i, 1),
            "return_1w":  _pct_return(rates, i, 5),
            "return_1m":  _pct_return(rates, i, 21),
            "return_ytd": _ytd_return(rates, dates, i),
        })
    return rows


# ── Fetch from Yahoo Finance ──────────────────────────────────────────────────

def fetch_yf_data(
    ticker: str,
    start_date: date,
    end_date: date,
    retries: int = 3,
) -> pd.DataFrame | None:
    """Download OHLCV from Yahoo Finance with retry on rate limit."""
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

async def seed_index_metadata(db) -> None:
    from sqlalchemy import text
    for idx in GLOBAL_INDICES:
        await db.execute(text("""
            INSERT INTO market.global_indices (index_code, index_name, region, country, currency, yf_ticker)
            VALUES (:code, :name, :region, :country, :currency, :ticker)
            ON CONFLICT (index_code) DO UPDATE SET
                index_name = EXCLUDED.index_name,
                region     = EXCLUDED.region,
                country    = EXCLUDED.country,
                currency   = EXCLUDED.currency,
                yf_ticker  = EXCLUDED.yf_ticker
        """), {
            "code": idx["code"], "name": idx["name"], "region": idx["region"],
            "country": idx["country"], "currency": idx["currency"], "ticker": idx["ticker"],
        })
    await db.commit()
    log.info(f"Seeded {len(GLOBAL_INDICES)} global index metadata rows")


async def upsert_index_rows(db, index_code: str, rows: list[dict], dry_run: bool) -> int:
    from sqlalchemy import text
    if not rows:
        return 0
    if dry_run:
        log.info(f"  [dry-run] would upsert {len(rows)} rows for {index_code}")
        return len(rows)
    for row in rows:
        await db.execute(text("""
            INSERT INTO market.global_index_prices (
                index_code, price_date,
                close_price, open_price, high_price, low_price, volume,
                return_1d, return_1w, return_1m, return_3m, return_6m,
                return_1y, return_ytd, high_52w, low_52w
            ) VALUES (
                :code, :price_date,
                :close_price, :open_price, :high_price, :low_price, :volume,
                :return_1d, :return_1w, :return_1m, :return_3m, :return_6m,
                :return_1y, :return_ytd, :high_52w, :low_52w
            )
            ON CONFLICT (index_code, price_date) DO UPDATE SET
                close_price = EXCLUDED.close_price, open_price  = EXCLUDED.open_price,
                high_price  = EXCLUDED.high_price,  low_price   = EXCLUDED.low_price,
                volume      = EXCLUDED.volume,
                return_1d   = EXCLUDED.return_1d,   return_1w   = EXCLUDED.return_1w,
                return_1m   = EXCLUDED.return_1m,   return_3m   = EXCLUDED.return_3m,
                return_6m   = EXCLUDED.return_6m,   return_1y   = EXCLUDED.return_1y,
                return_ytd  = EXCLUDED.return_ytd,
                high_52w    = EXCLUDED.high_52w,    low_52w     = EXCLUDED.low_52w
        """), {"code": index_code, **row})
    await db.commit()
    return len(rows)


async def upsert_fx_rows(db, fx_pair: str, rows: list[dict], dry_run: bool) -> int:
    from sqlalchemy import text
    if not rows:
        return 0
    if dry_run:
        log.info(f"  [dry-run] would upsert {len(rows)} FX rows for {fx_pair}")
        return len(rows)
    for row in rows:
        await db.execute(text("""
            INSERT INTO market.fx_rates (
                fx_pair, rate_date, rate, open_rate, high_rate, low_rate,
                return_1d, return_1w, return_1m, return_ytd
            ) VALUES (
                :pair, :rate_date, :rate, :open_rate, :high_rate, :low_rate,
                :return_1d, :return_1w, :return_1m, :return_ytd
            )
            ON CONFLICT (fx_pair, rate_date) DO UPDATE SET
                rate       = EXCLUDED.rate,       open_rate  = EXCLUDED.open_rate,
                high_rate  = EXCLUDED.high_rate,  low_rate   = EXCLUDED.low_rate,
                return_1d  = EXCLUDED.return_1d,  return_1w  = EXCLUDED.return_1w,
                return_1m  = EXCLUDED.return_1m,  return_ytd = EXCLUDED.return_ytd
        """), {"pair": fx_pair, **row})
    await db.commit()
    return len(rows)


# ── Main entry ────────────────────────────────────────────────────────────────

async def run(
    target_date: date | None = None,
    backfill_days: int = 3,
    dry_run: bool = False,
) -> None:
    """
    Fetch and store global market data.

    Args:
        target_date:   End date (inclusive). Defaults to today.
        backfill_days: Calendar days back to fetch. Use 1825 for initial 5Y backfill.
        dry_run:       Print what would be written without touching the DB.
    """
    from app.db.session import AsyncSessionLocal

    if target_date is None:
        target_date = date.today()
    start_date = target_date - timedelta(days=backfill_days)

    log.info(f"Global markets: fetching {start_date} → {target_date} (dry_run={dry_run})")

    async with AsyncSessionLocal() as db:
        if not dry_run:
            await seed_index_metadata(db)

        total_rows = 0

        # Indices
        for i, idx in enumerate(GLOBAL_INDICES):
            log.info(f"  [{i+1}/{len(GLOBAL_INDICES)}] {idx['code']} ({idx['ticker']}) …")
            if i > 0:
                time.sleep(2)
            df = fetch_yf_data(idx["ticker"], start_date, target_date)
            if df is None:
                continue
            df = df[df.index.date >= start_date]
            df = df[df.index.date <= target_date]
            if df.empty:
                log.info(f"  {idx['code']}: no rows in date range")
                continue
            rows = compute_price_rows(df)
            count = await upsert_index_rows(db, idx["code"], rows, dry_run)
            log.info(f"  {idx['code']}: {count} rows upserted")
            total_rows += count

        # FX pairs
        for j, fx in enumerate(FX_PAIRS):
            log.info(f"  [{j+1}/{len(FX_PAIRS)}] {fx['pair']} ({fx['ticker']}) …")
            time.sleep(2)
            df = fetch_yf_data(fx["ticker"], start_date, target_date)
            if df is None:
                continue
            df = df[df.index.date >= start_date]
            df = df[df.index.date <= target_date]
            if df.empty:
                continue
            rows = compute_fx_rows(df)
            count = await upsert_fx_rows(db, fx["pair"], rows, dry_run)
            log.info(f"  {fx['pair']}: {count} rows upserted")
            total_rows += count

    log.info(f"Global markets complete — {total_rows} total rows")


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest global index and AUD FX data from Yahoo Finance")
    parser.add_argument("--date",          default=None, help="Target date YYYY-MM-DD (default: today)")
    parser.add_argument("--backfill-days", type=int, default=3,
                        help="Calendar days to backfill (default: 3; use 1825 for 5Y backfill)")
    parser.add_argument("--dry-run",       action="store_true", help="Print without writing to DB")
    args = parser.parse_args()

    target = date.fromisoformat(args.date) if args.date else date.today()

    DATABASE_URL = os.environ.get("DATABASE_URL", "")
    if not DATABASE_URL and not args.dry_run:
        log.error("DATABASE_URL not set")
        sys.exit(1)

    asyncio.run(run(target_date=target, backfill_days=args.backfill_days, dry_run=args.dry_run))
