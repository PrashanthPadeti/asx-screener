"""
ASX Index Price Ingestion
=========================
Fetches historical and latest daily prices for ASX benchmark and sector indices
from Yahoo Finance and upserts into market.index_prices.

Returns computed fields:
  return_1d, return_1w, return_1m, return_3m, return_6m, return_1y,
  return_ytd, high_52w, low_52w

Usage:
    python compute/engine/index_prices.py               # fetch all, last 2 years
    python compute/engine/index_prices.py --days 30     # last 30 days only
    python compute/engine/index_prices.py --codes ASX200 ASX50
    python compute/engine/index_prices.py --today       # today only (intraday refresh)
"""

import os
import sys
import logging
import argparse
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import psycopg2
import psycopg2.extensions
from psycopg2.extras import execute_values
import pandas as pd
import numpy as np
from dotenv import load_dotenv

try:
    import yfinance as yf
except ImportError:
    print("ERROR: yfinance not installed. Run: pip install yfinance")
    sys.exit(1)

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

# ── Index code → Yahoo Finance ticker mapping ─────────────────────────────────
# Yahoo tickers for ASX indices use ^ prefix for broad indices,
# and ASX sector ETFs as proxies for GICS sector indices.
INDEX_TICKER_MAP = {
    "ASX20":  "^AORD",   # All Ords as proxy (no direct ASX20 Yahoo ticker)
    "ASX50":  "^AFLI",   # S&P/ASX 50
    "ASX100": "^ATOI",   # S&P/ASX 100
    "ASX200": "^AXJO",   # S&P/ASX 200 (primary benchmark)
    "ASX300": "^AXKO",   # S&P/ASX 300
    "AXJO":   "^AORD",   # All Ordinaries
    # GICS sector proxies via sector ETFs (best available via Yahoo)
    "AXFJ":   "OZF.AX",  # Financials — BetaShares Australian Financials
    "AXMJ":   "OZR.AX",  # Materials — BetaShares Australian Resources
    "AXEJ":   "OZE.AX",  # Energy — BetaShares Australian Energy
    "AXHJ":   "OZH.AX",  # Health Care — BetaShares Australian Health
}

# Authoritative Yahoo tickers with better coverage (fallback)
YAHOO_FALLBACK = {
    "ASX20":  "^AXJO",
    "ASX50":  "^AXJO",
    "AXFJ":   "^AXFJ",
    "AXMJ":   "^AXMJ",
    "AXEJ":   "^AXEJ",
    "AXHJ":   "^AXHJ",
}


def get_db():
    return psycopg2.connect(DB_URL)


def fetch_index_codes(cur, codes: Optional[list] = None) -> list[dict]:
    """Return active index records from market.indices."""
    if codes:
        placeholders = ",".join(["%s"] * len(codes))
        cur.execute(
            f"SELECT index_code, display_name FROM market.indices WHERE is_active = TRUE AND index_code IN ({placeholders})",
            codes,
        )
    else:
        cur.execute(
            "SELECT index_code, display_name FROM market.indices WHERE is_active = TRUE ORDER BY index_code"
        )
    rows = cur.fetchall()
    return [{"index_code": r[0], "display_name": r[1]} for r in rows]


def fetch_yahoo_prices(ticker: str, start: date, end: date) -> pd.DataFrame:
    """Download OHLCV data from Yahoo Finance. Returns empty DataFrame on failure."""
    try:
        df = yf.download(
            ticker,
            start=start.isoformat(),
            end=(end + timedelta(days=1)).isoformat(),
            auto_adjust=True,
            progress=False,
        )
        if df.empty:
            return pd.DataFrame()

        # Flatten MultiIndex columns if present (yfinance ≥ 0.2.x)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df = df.rename(columns={
            "Open": "open", "High": "high", "Low": "low",
            "Close": "close", "Volume": "volume",
        })
        df.index = pd.to_datetime(df.index).date
        df.index.name = "price_date"
        return df[["open", "high", "low", "close", "volume"]].dropna(subset=["close"])
    except Exception as e:
        log.warning(f"Yahoo fetch failed for {ticker}: {e}")
        return pd.DataFrame()


def compute_returns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add return columns to a OHLCV DataFrame sorted ascending by date.
    All returns are decimal ratios (0.05 = 5%).
    """
    df = df.sort_index()
    close = df["close"]

    df["return_1d"] = close.pct_change(1)

    # Rolling returns using available trading days
    df["return_1w"]  = close.pct_change(5)
    df["return_1m"]  = close.pct_change(21)
    df["return_3m"]  = close.pct_change(63)
    df["return_6m"]  = close.pct_change(126)
    df["return_1y"]  = close.pct_change(252)

    # YTD: return since last Dec 31
    df["year"] = [d.year for d in df.index]
    ytd_returns = []
    for d in df.index:
        dec31 = date(d.year - 1, 12, 31)
        prior = df.loc[df.index <= dec31, "close"]
        if not prior.empty:
            ytd_returns.append((close[d] - prior.iloc[-1]) / prior.iloc[-1])
        else:
            ytd_returns.append(None)
    df["return_ytd"] = ytd_returns
    df.drop(columns=["year"], inplace=True)

    # 52-week high/low (rolling 252 trading days)
    df["high_52w"] = df["high"].rolling(252, min_periods=1).max()
    df["low_52w"]  = df["low"].rolling(252, min_periods=1).min()

    return df


def upsert_prices(cur, index_code: str, df: pd.DataFrame):
    """Bulk upsert rows into market.index_prices."""
    if df.empty:
        return 0

    rows = []
    for price_date, row in df.iterrows():
        def _f(v):
            if v is None or (isinstance(v, float) and np.isnan(v)):
                return None
            return float(v)

        rows.append((
            index_code,
            price_date,
            _f(row.get("close")),
            _f(row.get("open")),
            _f(row.get("high")),
            _f(row.get("low")),
            int(row["volume"]) if row.get("volume") and not np.isnan(row["volume"]) else None,
            _f(row.get("return_1d")),
            _f(row.get("return_1w")),
            _f(row.get("return_1m")),
            _f(row.get("return_3m")),
            _f(row.get("return_6m")),
            _f(row.get("return_1y")),
            _f(row.get("return_ytd")),
            _f(row.get("high_52w")),
            _f(row.get("low_52w")),
        ))

    execute_values(cur, """
        INSERT INTO market.index_prices (
            index_code, price_date,
            close_price, open_price, high_price, low_price, volume,
            return_1d, return_1w, return_1m, return_3m, return_6m, return_1y,
            return_ytd, high_52w, low_52w
        ) VALUES %s
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
    """, rows)

    return len(rows)


def update_constituent_count(cur, index_code: str):
    """Update constituent_count in market.indices from screener.universe."""
    count_map = {
        "ASX20":  "is_asx200",  # approximate — no separate flag
        "ASX50":  None,
        "ASX100": None,
        "ASX200": "is_asx200",
        "ASX300": None,
        "AXJO":   None,
    }
    col = count_map.get(index_code)
    if col:
        cur.execute(
            f"UPDATE market.indices SET constituent_count = (SELECT COUNT(*) FROM screener.universe WHERE {col} = TRUE), updated_at = NOW() WHERE index_code = %s",
            (index_code,),
        )


def run(codes: Optional[list] = None, days: int = 730, today_only: bool = False):
    end_date   = date.today()
    start_date = end_date - timedelta(days=365 + days)  # extra year for 52W calc

    if today_only:
        start_date = end_date - timedelta(days=400)

    conn = get_db()
    cur  = conn.cursor()

    indices = fetch_index_codes(cur, codes)
    if not indices:
        log.warning("No active indices found in market.indices")
        conn.close()
        return

    log.info(f"Fetching prices for {len(indices)} indices | {start_date} → {end_date}")

    total_rows = 0
    for idx in indices:
        code    = idx["index_code"]
        ticker  = INDEX_TICKER_MAP.get(code)

        if not ticker:
            log.warning(f"  {code}: no Yahoo ticker mapping, skipping")
            continue

        log.info(f"  {code} ({idx['display_name']}) ← {ticker}")
        df = fetch_yahoo_prices(ticker, start_date, end_date)

        # Try fallback ticker if primary returned nothing
        if df.empty and code in YAHOO_FALLBACK:
            fallback = YAHOO_FALLBACK[code]
            log.info(f"  {code}: retrying with fallback ticker {fallback}")
            df = fetch_yahoo_prices(fallback, start_date, end_date)

        if df.empty:
            log.warning(f"  {code}: no price data returned, skipping")
            continue

        df = compute_returns(df)
        n  = upsert_prices(cur, code, df)
        update_constituent_count(cur, code)
        conn.commit()

        log.info(f"  {code}: upserted {n} rows")
        total_rows += n

    cur.close()
    conn.close()
    log.info(f"Done — {total_rows} total rows upserted across {len(indices)} indices")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest ASX index prices from Yahoo Finance")
    parser.add_argument("--codes",  nargs="+", help="Specific index codes (e.g. ASX200 ASX50)")
    parser.add_argument("--days",   type=int, default=730, help="Days of history to fetch (default 730)")
    parser.add_argument("--today",  action="store_true",   help="Fetch recent data only (today refresh)")
    args = parser.parse_args()

    run(codes=args.codes, days=args.days, today_only=args.today)
