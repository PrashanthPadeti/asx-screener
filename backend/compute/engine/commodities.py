"""
Commodities Engine
==================
Fetches daily OHLCV for key global commodities from stooq.com (free, no API key),
computes period returns and 52W range, then upserts into market.commodity_prices.

Commodities (our code → stooq ticker):
    GC  → gc.f   (Gold futures,           USD/oz)
    SI  → si.f   (Silver futures,         USD/oz)
    PL  → pl.f   (Platinum futures,       USD/oz)
    HG  → hg.f   (Copper futures,         USD/lb)
    CL  → cl.f   (WTI Crude Oil futures,  USD/bbl)
    BZ  → cb.f   (Brent Crude futures,    USD/bbl)
    NG  → ng.f   (Natural Gas futures,    USD/MMBtu)

Usage (standalone):
    python -m compute.engine.commodities [--date YYYY-MM-DD] [--backfill-days N] [--dry-run]
"""

import argparse
import asyncio
import logging
import os
import sys
from datetime import date, timedelta
from io import StringIO
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

STOOQ_BASE = "https://stooq.com/q/d/l/"

# ── Config ────────────────────────────────────────────────────────────────────

COMMODITIES = [
    # Precious Metals
    {"code": "GC", "name": "Gold",           "category": "Precious Metals", "unit": "USD/oz",    "ticker": "gc.f"},
    {"code": "SI", "name": "Silver",          "category": "Precious Metals", "unit": "USD/oz",    "ticker": "si.f"},
    {"code": "PL", "name": "Platinum",        "category": "Precious Metals", "unit": "USD/oz",    "ticker": "pl.f"},
    # Base Metals
    {"code": "HG", "name": "Copper",          "category": "Base Metals",     "unit": "USD/lb",    "ticker": "hg.f"},
    # Energy
    {"code": "CL", "name": "WTI Crude Oil",   "category": "Energy",          "unit": "USD/bbl",   "ticker": "cl.f"},
    {"code": "BZ", "name": "Brent Crude Oil", "category": "Energy",          "unit": "USD/bbl",   "ticker": "cb.f"},
    {"code": "NG", "name": "Natural Gas",     "category": "Energy",          "unit": "USD/MMBtu", "ticker": "ng.f"},
]

# ── Return computation ────────────────────────────────────────────────────────

def _pct_return(series: pd.Series, current_idx: int, lookback: int) -> float | None:
    if current_idx < lookback:
        return None
    prior   = series.iloc[current_idx - lookback]
    current = series.iloc[current_idx]
    if prior is None or prior == 0 or pd.isna(prior) or pd.isna(current):
        return None
    return float((current - prior) / prior)


def _ytd_return(series: pd.Series, dates: pd.DatetimeIndex, current_idx: int) -> float | None:
    current_date = dates[current_idx]
    year_start   = pd.Timestamp(current_date.year, 1, 1)
    prior_mask   = dates < year_start
    if not prior_mask.any():
        return None
    prior_close   = series[prior_mask].iloc[-1]
    current_close = series.iloc[current_idx]
    if prior_close == 0 or pd.isna(prior_close) or pd.isna(current_close):
        return None
    return float((current_close - prior_close) / prior_close)


def compute_price_rows(df: pd.DataFrame, meta: dict) -> list[dict]:
    closes = df["close"]
    dates  = df.index
    rows   = []
    for i in range(len(df)):
        row   = df.iloc[i]
        close = row["close"]
        if pd.isna(close):
            continue
        window_start = max(0, i - 251)
        window = closes.iloc[window_start : i + 1].dropna()
        high_52w = float(window.max()) if len(window) >= 5 else None
        low_52w  = float(window.min()) if len(window) >= 5 else None
        rows.append({
            "commodity_code": meta["code"],
            "commodity_name": meta["name"],
            "category":       meta["category"],
            "unit":           meta["unit"],
            "price_date":     dates[i].date(),
            "close_price":    float(close),
            "open_price":     float(row["open"])   if not pd.isna(row.get("open",   float("nan"))) else None,
            "high_price":     float(row["high"])   if not pd.isna(row.get("high",   float("nan"))) else None,
            "low_price":      float(row["low"])    if not pd.isna(row.get("low",    float("nan"))) else None,
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


# ── Fetch from stooq ─────────────────────────────────────────────────────────

def fetch_stooq_data(
    ticker:     str,
    start_date: date,
    end_date:   date,
) -> pd.DataFrame | None:
    """Download OHLCV from stooq.com (free, no API key). Returns None on failure."""
    params = {
        "s":  ticker,
        "d1": (start_date - timedelta(days=400)).strftime("%Y%m%d"),
        "d2": (end_date + timedelta(days=1)).strftime("%Y%m%d"),
        "i":  "d",
    }
    headers = {"User-Agent": "Mozilla/5.0 (compatible; ASX-Screener/1.0)"}
    try:
        resp = requests.get(STOOQ_BASE, params=params, headers=headers, timeout=30)
        resp.raise_for_status()
        text = resp.text.strip()
        if not text or text.startswith("No data"):
            log.warning(f"{ticker}: no data returned from stooq")
            return None

        df = pd.read_csv(StringIO(text))
        if df.empty or "Date" not in df.columns:
            log.warning(f"{ticker}: unexpected stooq response format")
            return None

        df.columns = [c.lower() for c in df.columns]
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()

        if "close" not in df.columns:
            df["close"] = float("nan")
        for col in ["open", "high", "low", "volume"]:
            if col not in df.columns:
                df[col] = float("nan")

        df = df[~df.index.duplicated(keep="last")]
        return df[["open", "high", "low", "close", "volume"]]

    except Exception as exc:
        log.warning(f"{ticker}: stooq fetch failed — {exc}")
        return None


# ── DB upsert ─────────────────────────────────────────────────────────────────

async def upsert_rows(db, rows: list[dict], dry_run: bool) -> int:
    from sqlalchemy import text
    if not rows:
        return 0
    if dry_run:
        log.info(f"  [dry-run] would upsert {len(rows)} rows")
        return len(rows)
    for row in rows:
        await db.execute(text("""
            INSERT INTO market.commodity_prices (
                commodity_code, commodity_name, category, unit, price_date,
                close_price, open_price, high_price, low_price,
                return_1d, return_1w, return_1m, return_3m,
                return_6m, return_1y, return_ytd, high_52w, low_52w
            ) VALUES (
                :commodity_code, :commodity_name, :category, :unit, :price_date,
                :close_price, :open_price, :high_price, :low_price,
                :return_1d, :return_1w, :return_1m, :return_3m,
                :return_6m, :return_1y, :return_ytd, :high_52w, :low_52w
            )
            ON CONFLICT (commodity_code, price_date) DO UPDATE SET
                commodity_name = EXCLUDED.commodity_name,
                category       = EXCLUDED.category,
                unit           = EXCLUDED.unit,
                close_price    = EXCLUDED.close_price,
                open_price     = EXCLUDED.open_price,
                high_price     = EXCLUDED.high_price,
                low_price      = EXCLUDED.low_price,
                return_1d      = EXCLUDED.return_1d,
                return_1w      = EXCLUDED.return_1w,
                return_1m      = EXCLUDED.return_1m,
                return_3m      = EXCLUDED.return_3m,
                return_6m      = EXCLUDED.return_6m,
                return_1y      = EXCLUDED.return_1y,
                return_ytd     = EXCLUDED.return_ytd,
                high_52w       = EXCLUDED.high_52w,
                low_52w        = EXCLUDED.low_52w
        """), row)
    await db.commit()
    return len(rows)


# ── Main entry ────────────────────────────────────────────────────────────────

async def run(
    target_date:   date | None = None,
    backfill_days: int = 3,
    dry_run:       bool = False,
) -> None:
    from app.db.session import AsyncSessionLocal

    if target_date is None:
        target_date = date.today()
    start_date = target_date - timedelta(days=backfill_days)

    log.info(f"Commodities (stooq): fetching {start_date} → {target_date} (dry_run={dry_run})")

    async with AsyncSessionLocal() as db:
        total_rows = 0
        for i, commodity in enumerate(COMMODITIES):
            log.info(f"  [{i+1}/{len(COMMODITIES)}] {commodity['code']} ({commodity['ticker']}) …")
            df = fetch_stooq_data(commodity["ticker"], start_date, target_date)
            if df is None:
                log.warning(f"  {commodity['code']}: skipped (fetch failed)")
                continue
            if df.empty:
                log.info(f"  {commodity['code']}: no rows returned")
                continue
            rows = compute_price_rows(df, commodity)
            rows_in_range = [r for r in rows if start_date <= r["price_date"] <= target_date]
            count = await upsert_rows(db, rows_in_range, dry_run)
            log.info(f"  {commodity['code']}: {count} rows upserted")
            total_rows += count

    log.info(f"Commodities complete — {total_rows} total rows")


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest commodity prices from EODHD")
    parser.add_argument("--date",          default=None, help="Target date YYYY-MM-DD (default: today)")
    parser.add_argument("--backfill-days", type=int, default=3,
                        help="Calendar days to backfill (default: 3; use 1825 for 5Y)")
    parser.add_argument("--dry-run",       action="store_true")
    args = parser.parse_args()

    target = date.fromisoformat(args.date) if args.date else date.today()

    DATABASE_URL = os.environ.get("DATABASE_URL", "")
    if not DATABASE_URL and not args.dry_run:
        log.error("DATABASE_URL not set")
        sys.exit(1)

    asyncio.run(run(target_date=target, backfill_days=args.backfill_days, dry_run=args.dry_run))
