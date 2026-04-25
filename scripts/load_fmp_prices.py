"""
ASX Screener — FMP Historical Price Loader
==========================================
One-time bulk load of 2+ years of daily OHLCV price data for all ASX stocks.
Replaces load_prices.py (Yahoo Finance) with a commercially licensed source.

Source: Financial Modeling Prep (FMP) — commercial licence included.
Endpoint: /api/v3/historical-price-full/{symbol}

Usage:
    python scripts/load_fmp_prices.py                   # All active stocks
    python scripts/load_fmp_prices.py --codes BHP CBA   # Specific stocks
    python scripts/load_fmp_prices.py --limit 100        # Test first N
    python scripts/load_fmp_prices.py --from 2020-01-01  # Custom start date
    python scripts/load_fmp_prices.py --from-code XYZ    # Resume from code
    nohup python scripts/load_fmp_prices.py > logs/fmp_prices.log 2>&1 &

Expected runtime: ~2-4 hours for all 1,978 stocks.
"""

import os
import sys
import time
import logging
import argparse
from datetime import date, datetime, timedelta
from typing import Optional

import psycopg2
from psycopg2.extras import execute_values
import requests
from dotenv import load_dotenv

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────

DB_URL = os.getenv(
    "DATABASE_URL_SYNC",
    "postgresql://asx_user:asx_secure_2024@localhost:5432/asx_screener"
)
FMP_KEY = os.getenv("FMP_API_KEY", "")

FMP_BASE    = "https://financialmodelingprep.com/api/v3"
SLEEP_SEC   = 0.2          # 5 req/sec — polite for Starter plan
MAX_RETRIES = 3
BATCH_COMMIT = 100         # Commit every N stocks
DEFAULT_FROM = (datetime.now() - timedelta(days=730)).strftime("%Y-%m-%d")  # 2 years

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ── FMP Price Fetcher ─────────────────────────────────────────────────────────

def fetch_prices_fmp(asx_code: str, from_date: str, to_date: str) -> Optional[list]:
    """
    Fetch daily OHLCV data from FMP for a single ASX stock.
    FMP ticker for ASX: {CODE}.AX  (same convention as Yahoo)

    Returns list of row tuples ready for DB insert, or None on failure.
    """
    if not FMP_KEY:
        raise RuntimeError("FMP_API_KEY not set in .env")

    ticker = f"{asx_code}.AX"
    url    = f"{FMP_BASE}/historical-price-full/{ticker}"
    params = {
        "from":   from_date,
        "to":     to_date,
        "apikey": FMP_KEY,
    }

    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, params=params, timeout=30)

            if resp.status_code == 401:
                raise RuntimeError("FMP API key invalid")
            if resp.status_code in (404, 422):
                return None          # Stock not covered by FMP
            if resp.status_code == 429:
                log.warning("Rate limited — sleeping 60s")
                time.sleep(60)
                continue
            resp.raise_for_status()

            data = resp.json()

            # FMP returns: {"symbol": "BHP.AX", "historical": [...]}
            if isinstance(data, dict) and "Error Message" in data:
                return None
            historical = data.get("historical", [])
            if not historical:
                return None

            rows = []
            for r in historical:
                dt_str = r.get("date")
                close  = r.get("close") or r.get("adjClose")
                if not dt_str or close is None:
                    continue

                try:
                    price_date = datetime.strptime(dt_str, "%Y-%m-%d")
                except ValueError:
                    continue

                open_  = r.get("open")
                high   = r.get("high")
                low    = r.get("low")
                volume = r.get("volume")
                adj_close = r.get("adjClose") or close

                rows.append((
                    price_date,            # time
                    asx_code,              # asx_code
                    round(float(open_),  4) if open_  else None,
                    round(float(high),   4) if high   else None,
                    round(float(low),    4) if low    else None,
                    round(float(close),  4),
                    round(float(adj_close), 4),
                    int(volume)            if volume  else None,
                    "fmp",                 # data_source
                ))

            return rows

        except requests.RequestException as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
            else:
                log.debug(f"  {asx_code}: request failed — {e}")
                return None

    return None


# ── DB Upsert ─────────────────────────────────────────────────────────────────

def upsert_prices(cur, rows: list) -> int:
    if not rows:
        return 0
    sql = """
        INSERT INTO market.daily_prices
            (time, asx_code, open, high, low, close, adjusted_close, volume, data_source)
        VALUES %s
        ON CONFLICT (time, asx_code) DO UPDATE SET
            open           = EXCLUDED.open,
            high           = EXCLUDED.high,
            low            = EXCLUDED.low,
            close          = EXCLUDED.close,
            adjusted_close = EXCLUDED.adjusted_close,
            volume         = EXCLUDED.volume,
            data_source    = EXCLUDED.data_source
    """
    execute_values(cur, sql, rows, page_size=500)
    return len(rows)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="FMP Historical Price Loader")
    parser.add_argument("--codes",     nargs="+", help="Specific ASX codes")
    parser.add_argument("--limit",     type=int,  help="Load first N stocks only")
    parser.add_argument("--from",      dest="from_date", default=DEFAULT_FROM,
                        help=f"Start date YYYY-MM-DD (default: {DEFAULT_FROM})")
    parser.add_argument("--to",        dest="to_date",
                        default=date.today().strftime("%Y-%m-%d"),
                        help="End date YYYY-MM-DD (default: today)")
    parser.add_argument("--from-code", help="Resume from this ASX code (alphabetical)")
    args = parser.parse_args()

    if not FMP_KEY:
        print("ERROR: FMP_API_KEY not set. Add to .env file:")
        print("  FMP_API_KEY=your_key_here")
        print("  Get your key at: https://financialmodelingprep.com/pricing")
        sys.exit(1)

    conn = psycopg2.connect(DB_URL)
    cur  = conn.cursor()

    if args.codes:
        codes = [c.upper() for c in args.codes]
    else:
        cur.execute("""
            SELECT asx_code FROM market.companies
            WHERE status = 'active'
            ORDER BY asx_code
        """)
        codes = [r[0] for r in cur.fetchall()]

    if args.from_code:
        start = args.from_code.upper()
        codes = [c for c in codes if c >= start]
        log.info(f"Resuming from {start} — {len(codes)} stocks remaining")

    if args.limit:
        codes = codes[:args.limit]

    total = len(codes)
    log.info(f"Loading prices for {total} stocks via FMP ({args.from_date} → {args.to_date})")

    loaded = failed = no_data = 0
    total_rows = 0

    for i, code in enumerate(codes, 1):
        rows = fetch_prices_fmp(code, args.from_date, args.to_date)

        if rows:
            try:
                n = upsert_prices(cur, rows)
                total_rows += n
                loaded += 1
            except psycopg2.Error as e:
                conn.rollback()
                failed += 1
                log.warning(f"  {code}: DB error — {e}")
        else:
            no_data += 1

        if i % BATCH_COMMIT == 0:
            conn.commit()
            log.info(
                f"[{i:4d}/{total}] {loaded} loaded, {no_data} no data, {failed} failed | "
                f"{total_rows:,} total rows"
            )

        time.sleep(SLEEP_SEC)

    conn.commit()
    cur.close()
    conn.close()

    log.info("=" * 60)
    log.info(f"DONE! {loaded} stocks, {total_rows:,} price rows loaded")
    log.info(f"  No data: {no_data} | Failed: {failed}")
    log.info("Now update the nightly cron to use update_prices_fmp.py instead of update_prices.py")


if __name__ == "__main__":
    main()
