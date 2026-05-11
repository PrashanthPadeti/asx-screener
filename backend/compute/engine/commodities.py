"""
Commodities Engine
==================
Fetches daily commodity prices from three sources:
  • EODHD FOREX  — precious metals (Gold, Silver, Platinum) as XAU/XAG/XPT vs USD
  • Alpha Vantage — energy & base metals (WTI, Brent, Natural Gas, Copper)
  • Yahoo Finance — bulk commodities (Iron Ore 62% TIO=F futures, free, no key)

EODHD FOREX pairs (confirmed working on all plans):
    GC  → XAUUSD.FOREX   (Gold spot,      USD/oz)
    SI  → XAGUSD.FOREX   (Silver spot,    USD/oz)
    PL  → XPTUSD.FOREX   (Platinum spot,  USD/oz)

Alpha Vantage commodity functions (free tier: 25 req/day; we use 4):
    CL  → WTI            (WTI Crude Oil,  USD/bbl)
    BZ  → BRENT          (Brent Crude,    USD/bbl)
    NG  → NATURAL_GAS    (Natural Gas,    USD/MMBtu)
    HG  → COPPER         (Copper,         USD/lb)

Yahoo Finance (free, no API key, daily):
    IO  → TIO=F          (SGX TSI Iron Ore 62% Fe CFR China futures, USD/t)

Requires:
    EODHD_API_KEY         (already in .env)
    ALPHA_VANTAGE_API_KEY (free key from alphavantage.co/support/#api-key)

Usage (standalone):
    python -m compute.engine.commodities [--date YYYY-MM-DD] [--backfill-days N] [--dry-run]
"""

import argparse
import asyncio
import logging
import os
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

EODHD_BASE  = "https://eodhd.com/api"
AV_BASE     = "https://www.alphavantage.co/query"
YAHOO_BASE  = "https://query1.finance.yahoo.com/v8/finance/chart"

# ── Config ────────────────────────────────────────────────────────────────────

# source="eodhd"  → fetched as FOREX pair via EODHD
# source="av"     → fetched via Alpha Vantage commodity function
# source="yahoo"  → fetched via Yahoo Finance v8 API (free, no key)
COMMODITIES = [
    # Precious Metals — EODHD FOREX
    {"code": "GC", "name": "Gold",           "category": "Precious Metals", "unit": "USD/oz",    "source": "eodhd", "ticker": "XAUUSD.FOREX"},
    {"code": "SI", "name": "Silver",          "category": "Precious Metals", "unit": "USD/oz",    "source": "eodhd", "ticker": "XAGUSD.FOREX"},
    {"code": "PL", "name": "Platinum",        "category": "Precious Metals", "unit": "USD/oz",    "source": "eodhd", "ticker": "XPTUSD.FOREX"},
    # Energy — Alpha Vantage
    {"code": "CL", "name": "WTI Crude Oil",   "category": "Energy",          "unit": "USD/bbl",   "source": "av",    "ticker": "WTI"},
    {"code": "BZ", "name": "Brent Crude Oil", "category": "Energy",          "unit": "USD/bbl",   "source": "av",    "ticker": "BRENT"},
    {"code": "NG", "name": "Natural Gas",     "category": "Energy",          "unit": "USD/MMBtu", "source": "av",    "ticker": "NATURAL_GAS"},
    # Base Metals — Alpha Vantage
    {"code": "HG", "name": "Copper",          "category": "Base Metals",     "unit": "USD/lb",    "source": "av",    "ticker": "COPPER"},
    # Bulk — Yahoo Finance (SGX TSI Iron Ore 62% Fe CFR China, daily, no key)
    {"code": "IO", "name": "Iron Ore 62%",    "category": "Bulk",            "unit": "USD/t",     "source": "yahoo", "ticker": "TIO=F"},
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


# ── Fetch from EODHD FOREX ────────────────────────────────────────────────────

def fetch_eodhd_forex(
    ticker:     str,
    start_date: date,
    end_date:   date,
    api_key:    str,
) -> pd.DataFrame | None:
    """Fetch a FOREX pair from EODHD (e.g. XAUUSD.FOREX for gold spot)."""
    url    = f"{EODHD_BASE}/eod/{ticker}"
    params = {
        "api_token": api_key,
        "fmt":       "json",
        "period":    "d",
        "from":      (start_date - timedelta(days=400)).isoformat(),
        "to":        (end_date + timedelta(days=1)).isoformat(),
    }
    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if not data or not isinstance(data, list):
            log.warning(f"{ticker}: empty EODHD response")
            return None

        df = pd.DataFrame(data)
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()

        if "adjusted_close" in df.columns:
            df["close"] = df["adjusted_close"]
            df = df.drop(columns=["adjusted_close"])
        elif "close" not in df.columns:
            df["close"] = float("nan")

        for col in ["open", "high", "low", "volume"]:
            if col not in df.columns:
                df[col] = float("nan")

        df = df[~df.index.duplicated(keep="last")]
        return df[["open", "high", "low", "close", "volume"]]

    except Exception as exc:
        log.warning(f"{ticker}: EODHD fetch failed — {exc}")
        return None


# ── Fetch from Alpha Vantage ──────────────────────────────────────────────────

def fetch_av_commodity(
    function:   str,
    start_date: date,
    end_date:   date,
    api_key:    str,
) -> pd.DataFrame | None:
    """
    Fetch daily commodity data from Alpha Vantage.
    function: WTI | BRENT | NATURAL_GAS | COPPER | GOLD | SILVER | etc.
    Free tier: 25 req/day. Response: {data: [{date, value}, ...]}
    """
    params = {
        "function":  function,
        "interval":  "daily",
        "apikey":    api_key,
        "datatype":  "json",
    }
    try:
        resp = requests.get(AV_BASE, params=params, timeout=30)
        resp.raise_for_status()
        payload = resp.json()

        if "Information" in payload:
            log.warning(f"{function}: Alpha Vantage rate limit — {payload['Information'][:80]}")
            return None
        if "data" not in payload:
            log.warning(f"{function}: unexpected Alpha Vantage response: {list(payload.keys())}")
            return None

        rows = payload["data"]
        if not rows:
            return None

        df = pd.DataFrame(rows)
        df["date"]  = pd.to_datetime(df["date"])
        df["close"] = pd.to_numeric(df["value"], errors="coerce")
        df = df.set_index("date").sort_index()

        # Alpha Vantage commodity endpoint returns close only — fill OHLV with NaN
        df["open"]   = float("nan")
        df["high"]   = float("nan")
        df["low"]    = float("nan")
        df["volume"] = float("nan")

        df = df[~df.index.duplicated(keep="last")]
        return df[["open", "high", "low", "close", "volume"]]

    except Exception as exc:
        log.warning(f"{function}: Alpha Vantage fetch failed — {exc}")
        return None


# ── Fetch from Yahoo Finance ──────────────────────────────────────────────────

def fetch_yahoo_commodity(
    ticker:     str,
    start_date: date,
    end_date:   date,
) -> pd.DataFrame | None:
    """
    Fetch daily commodity data from Yahoo Finance v8 API (free, no API key).
    ticker: e.g. 'TIO=F' for SGX TSI Iron Ore 62% Fe CFR China futures.
    """
    import time as _time
    period1 = int(pd.Timestamp(start_date - timedelta(days=400)).timestamp())
    period2 = int(pd.Timestamp(end_date   + timedelta(days=1)  ).timestamp())
    url     = f"{YAHOO_BASE}/{ticker}"
    params  = {"period1": period1, "period2": period2, "interval": "1d"}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept":     "application/json",
    }
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=30)
        resp.raise_for_status()
        payload = resp.json()
        result = payload.get("chart", {}).get("result")
        if not result:
            err = payload.get("chart", {}).get("error", {})
            log.warning(f"{ticker}: Yahoo Finance error — {err}")
            return None

        r          = result[0]
        timestamps = r.get("timestamp", [])
        quote      = r["indicators"]["quote"][0]
        if not timestamps:
            log.warning(f"{ticker}: Yahoo Finance returned no timestamps")
            return None

        df = pd.DataFrame({
            "date":   pd.to_datetime(timestamps, unit="s", utc=True).tz_convert("UTC").tz_localize(None),
            "open":   quote.get("open"),
            "high":   quote.get("high"),
            "low":    quote.get("low"),
            "close":  quote.get("close"),
            "volume": quote.get("volume"),
        })
        df = df.set_index("date").sort_index()
        # Normalise index to date-only
        df.index = df.index.normalize()
        for col in ["open", "high", "low", "close"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df[df["close"].notna()]
        df = df[~df.index.duplicated(keep="last")]
        return df[["open", "high", "low", "close", "volume"]]
    except Exception as exc:
        log.warning(f"{ticker}: Yahoo Finance fetch failed — {exc}")
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

    # Resolve API keys
    try:
        from app.core.config import settings
        eodhd_key = settings.EODHD_API_KEY
    except Exception:
        eodhd_key = os.environ.get("EODHD_API_KEY", "")

    av_key = os.environ.get("ALPHA_VANTAGE_API_KEY", "")
    try:
        from app.core.config import settings
        av_key = av_key or getattr(settings, "ALPHA_VANTAGE_API_KEY", "")
    except Exception:
        pass

    if not eodhd_key:
        log.error("EODHD_API_KEY not set")
        return
    if not av_key:
        log.warning("ALPHA_VANTAGE_API_KEY not set — energy/base metals will be skipped")

    if target_date is None:
        target_date = date.today()
    start_date = target_date - timedelta(days=backfill_days)

    log.info(f"Commodities: fetching {start_date} → {target_date} (dry_run={dry_run})")

    async with AsyncSessionLocal() as db:
        total_rows = 0
        for i, commodity in enumerate(COMMODITIES):
            code   = commodity["code"]
            source = commodity["source"]
            ticker = commodity["ticker"]
            log.info(f"  [{i+1}/{len(COMMODITIES)}] {code} ({ticker}, {source}) …")

            if source == "eodhd":
                df = fetch_eodhd_forex(ticker, start_date, target_date, eodhd_key)
            elif source == "av":
                if not av_key:
                    log.warning(f"  {code}: skipped (no ALPHA_VANTAGE_API_KEY)")
                    continue
                df = fetch_av_commodity(ticker, start_date, target_date, av_key)
            elif source == "yahoo":
                df = fetch_yahoo_commodity(ticker, start_date, target_date)
            else:
                log.warning(f"  {code}: unknown source '{source}'")
                continue

            if df is None or df.empty:
                log.warning(f"  {code}: skipped (no data)")
                continue

            rows = compute_price_rows(df, commodity)
            rows_in_range = [r for r in rows if start_date <= r["price_date"] <= target_date]
            count = await upsert_rows(db, rows_in_range, dry_run)
            log.info(f"  {code}: {count} rows upserted")
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
