"""
ASX ETF & Managed Fund Price Ingestion
=======================================
Seeds a curated list of major ASX-listed ETFs, LICs and managed funds into
market.funds, then fetches daily prices from Yahoo Finance into market.fund_prices.

Computed fields per row:
  return_1d/1w/1m/3m/6m/1y/3y_pa/5y_pa/ytd, high_52w, low_52w,
  distribution_yield (trailing 12M dividends / price)

Usage:
    python compute/engine/fund_prices.py              # seed + full price history
    python compute/engine/fund_prices.py --days 30    # last 30 days only
    python compute/engine/fund_prices.py --codes VAS VGS IOZ
    python compute/engine/fund_prices.py --seed-only  # only upsert fund metadata
    python compute/engine/fund_prices.py --prices-only  # skip metadata, just prices
"""

import os
import sys
import logging
import argparse
from datetime import date, timedelta
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


# ── Curated fund catalogue ────────────────────────────────────────────────────
# Fields: asx_code, fund_name, fund_type, asset_class, index_tracked,
#         fund_manager, mer_pct (decimal), distribution_freq, is_hedged
# mer_pct stored as decimal (0.0007 = 0.07% p.a.)

FUND_CATALOGUE = [
    # ── Australian Equity ETFs ────────────────────────────────────────────────
    ("VAS",  "Vanguard Australian Shares Index ETF",        "ETF", "Australian Equities",
     "S&P/ASX 300 Index",                 "Vanguard",       0.0007,  "quarterly",  False),
    ("STW",  "SPDR S&P/ASX 200 Fund",                       "ETF", "Australian Equities",
     "S&P/ASX 200 Index",                 "State Street",   0.0013,  "semi-annual", False),
    ("IOZ",  "iShares Core S&P/ASX 200 ETF",                "ETF", "Australian Equities",
     "S&P/ASX 200 Index",                 "BlackRock",      0.0009,  "quarterly",  False),
    ("A200", "BetaShares Australia 200 ETF",                 "ETF", "Australian Equities",
     "Solactive Australia 200 Index",     "BetaShares",     0.0004,  "quarterly",  False),
    ("MVW",  "VanEck Australian Equal Weight ETF",           "ETF", "Australian Equities",
     "MVIS Australia Equal Weight Index", "VanEck",         0.0035,  "semi-annual", False),
    ("EX20", "BetaShares Ex-20 Australian Equities ETF",    "ETF", "Australian Equities",
     "Solactive Ex-20 Index",             "BetaShares",     0.0025,  "quarterly",  False),
    ("AUST", "BetaShares Managed Risk Australian Share Fund","ETF", "Australian Equities",
     None,                                "BetaShares",     0.0049,  "quarterly",  False),

    # ── Global Equity ETFs ────────────────────────────────────────────────────
    ("VGS",  "Vanguard MSCI Index International Shares ETF","ETF", "Global Equities",
     "MSCI World ex-Australia Index",     "Vanguard",       0.0018,  "quarterly",  False),
    ("VGAD", "Vanguard MSCI Index International Shares (Hedged) ETF","ETF","Global Equities",
     "MSCI World ex-Australia Index",     "Vanguard",       0.0021,  "quarterly",  True),
    ("IVV",  "iShares S&P 500 ETF",                         "ETF", "Global Equities",
     "S&P 500 Index",                     "BlackRock",      0.0004,  "quarterly",  False),
    ("IHVV", "iShares S&P 500 AUD Hedged ETF",              "ETF", "Global Equities",
     "S&P 500 Index",                     "BlackRock",      0.0010,  "quarterly",  True),
    ("NDQ",  "BetaShares NASDAQ 100 ETF",                   "ETF", "Global Equities",
     "NASDAQ-100 Index",                  "BetaShares",     0.0048,  "quarterly",  False),
    ("HNDQ", "BetaShares NASDAQ 100 (Hedged) ETF",          "ETF", "Global Equities",
     "NASDAQ-100 Index",                  "BetaShares",     0.0051,  "quarterly",  True),
    ("VEU",  "Vanguard All-World ex-US Shares Index ETF",   "ETF", "Global Equities",
     "FTSE All-World ex US Index",        "Vanguard",       0.0008,  "quarterly",  False),
    ("VESG", "Vanguard Ethically Conscious International Shares ETF","ETF","Global Equities",
     "FTSE Developed ex-Australia Index", "Vanguard",       0.0018,  "quarterly",  False),
    ("ETHI", "BetaShares Global Sustainability Leaders ETF","ETF","Global Equities",
     None,                                "BetaShares",     0.0059,  "semi-annual", False),
    ("QUAL", "VanEck MSCI International Quality ETF",       "ETF", "Global Equities",
     "MSCI World ex-Australia Quality",   "VanEck",         0.0040,  "quarterly",  False),

    # ── Fixed Income ──────────────────────────────────────────────────────────
    ("VAF",  "Vanguard Australian Fixed Interest Index ETF","ETF","Fixed Income",
     "Bloomberg AusBond Composite Index", "Vanguard",       0.0010,  "monthly",    False),
    ("VGB",  "Vanguard Australian Government Bond Index ETF","ETF","Fixed Income",
     "Bloomberg AusBond Govt Index",      "Vanguard",       0.0010,  "monthly",    False),
    ("IAF",  "iShares Core Composite Bond ETF",             "ETF","Fixed Income",
     "Bloomberg AusBond Composite Index", "BlackRock",      0.0015,  "monthly",    False),
    ("QPON", "BetaShares Australian Bank Senior Floating Rate Bond ETF","ETF","Fixed Income",
     None,                                "BetaShares",     0.0022,  "monthly",    False),
    ("VBND", "Vanguard Global Aggregate Bond Index (Hedged) ETF","ETF","Fixed Income",
     "Bloomberg Global Aggregate Index",  "Vanguard",       0.0020,  "monthly",    True),

    # ── Property ──────────────────────────────────────────────────────────────
    ("VAP",  "Vanguard Australian Property Securities Index ETF","ETF","Property",
     "S&P/ASX 300 A-REIT Index",          "Vanguard",       0.0023,  "quarterly",  False),
    ("SLF",  "SPDR S&P/ASX 200 Listed Property Fund",       "ETF","Property",
     "S&P/ASX 200 A-REIT Index",          "State Street",   0.0040,  "quarterly",  False),

    # ── Commodities ───────────────────────────────────────────────────────────
    ("GOLD", "BetaShares Gold Bullion ETF (AUD Hedged)",    "ETF","Commodities",
     "Gold spot price",                   "BetaShares",     0.0059,  None,         True),
    ("ETPMAG","ETF Securities Physical Silver",             "ETF","Commodities",
     "Silver spot price",                 "ETF Securities", 0.0049,  None,         False),
    ("QCB",  "BetaShares Crude Oil Index (Hedged)",         "ETF","Commodities",
     "Bloomberg Crude Oil Subindex",      "BetaShares",     0.0069,  None,         True),

    # ── Multi-Asset ───────────────────────────────────────────────────────────
    ("VDGR", "Vanguard Diversified Growth Index ETF",       "ETF","Multi-Asset",
     None,                                "Vanguard",       0.0027,  "quarterly",  False),
    ("VDHG", "Vanguard Diversified High Growth Index ETF",  "ETF","Multi-Asset",
     None,                                "Vanguard",       0.0027,  "quarterly",  False),
    ("VDBA", "Vanguard Diversified Balanced Index ETF",     "ETF","Multi-Asset",
     None,                                "Vanguard",       0.0027,  "quarterly",  False),
    ("DZZF", "BetaShares Diversified All Growth ETF",       "ETF","Multi-Asset",
     None,                                "BetaShares",     0.0019,  "quarterly",  False),

    # ── LICs (Listed Investment Companies) ───────────────────────────────────
    ("AFI",  "Australian Foundation Investment Co",         "LIC","Australian Equities",
     None,                                "AFIC",           0.0014,  "semi-annual", False),
    ("ARG",  "Argo Investments",                            "LIC","Australian Equities",
     None,                                "Argo",           0.0015,  "semi-annual", False),
    ("MLT",  "Milton Corporation",                          "LIC","Australian Equities",
     None,                                "Milton",         0.0011,  "semi-annual", False),
    ("BKI",  "BKI Investment Company",                      "LIC","Australian Equities",
     None,                                "Contact Asset Mgmt",0.0017,"quarterly", False),
    ("WHF",  "Whitefield Industrials",                      "LIC","Australian Equities",
     None,                                "Whitefield",     0.0030,  "semi-annual", False),
    ("MFF",  "MFF Capital Investments",                     "LIC","Global Equities",
     None,                                "MFF",            0.0113,  "semi-annual", False),
    ("PMC",  "Platinum Capital",                            "LIC","Global Equities",
     None,                                "Platinum",       0.0154,  "semi-annual", False),
]


def get_db():
    return psycopg2.connect(DB_URL)


def seed_funds(cur, codes: Optional[list] = None):
    """Upsert fund metadata from FUND_CATALOGUE into market.funds."""
    catalogue = FUND_CATALOGUE
    if codes:
        codes_upper = {c.upper() for c in codes}
        catalogue = [f for f in catalogue if f[0] in codes_upper]

    rows = [
        (
            row[0],   # asx_code
            row[1],   # fund_name
            row[2],   # fund_type
            row[3],   # asset_class
            row[4],   # index_tracked
            row[5],   # fund_manager
            row[6],   # mer_pct
            row[7],   # distribution_freq
            row[8],   # is_hedged
        )
        for row in catalogue
    ]

    execute_values(cur, """
        INSERT INTO market.funds (
            asx_code, fund_name, fund_type, asset_class, index_tracked,
            fund_manager, mer_pct, distribution_freq, is_hedged, is_active
        ) VALUES %s
        ON CONFLICT (asx_code) DO UPDATE SET
            fund_name        = EXCLUDED.fund_name,
            fund_type        = EXCLUDED.fund_type,
            asset_class      = EXCLUDED.asset_class,
            index_tracked    = EXCLUDED.index_tracked,
            fund_manager     = EXCLUDED.fund_manager,
            mer_pct          = EXCLUDED.mer_pct,
            distribution_freq= EXCLUDED.distribution_freq,
            is_hedged        = EXCLUDED.is_hedged,
            is_active        = TRUE,
            updated_at       = NOW()
    """, rows)

    log.info(f"Seeded {len(rows)} funds into market.funds")


def fetch_yahoo_prices(ticker: str, start: date, end: date) -> pd.DataFrame:
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


def fetch_yahoo_dividends(ticker: str) -> pd.Series:
    """Return Series of dividend amounts indexed by ex-date."""
    try:
        t = yf.Ticker(ticker)
        divs = t.dividends
        if divs.empty:
            return pd.Series(dtype=float)
        divs.index = pd.to_datetime(divs.index).tz_localize(None).date
        return divs
    except Exception as e:
        log.warning(f"Yahoo dividends failed for {ticker}: {e}")
        return pd.Series(dtype=float)


def compute_fund_returns(df: pd.DataFrame, dividends: pd.Series) -> pd.DataFrame:
    """Compute return columns and distribution yield."""
    df = df.sort_index()
    close = df["close"]

    df["return_1d"] = close.pct_change(1)
    df["return_1w"]  = close.pct_change(5)
    df["return_1m"]  = close.pct_change(21)
    df["return_3m"]  = close.pct_change(63)
    df["return_6m"]  = close.pct_change(126)
    df["return_1y"]  = close.pct_change(252)
    df["return_3y_pa"] = (1 + close.pct_change(252 * 3)).pow(1 / 3) - 1
    df["return_5y_pa"] = (1 + close.pct_change(252 * 5)).pow(1 / 5) - 1

    # YTD
    ytd_returns = []
    for d in df.index:
        dec31 = date(d.year - 1, 12, 31)
        prior = df.loc[df.index <= dec31, "close"]
        if not prior.empty:
            ytd_returns.append((close[d] - prior.iloc[-1]) / prior.iloc[-1])
        else:
            ytd_returns.append(None)
    df["return_ytd"] = ytd_returns

    # 52W high/low
    df["high_52w"] = df["high"].rolling(252, min_periods=1).max()
    df["low_52w"]  = df["low"].rolling(252, min_periods=1).min()

    # Trailing 12M distribution yield = sum of last 12M dividends / current price
    if not dividends.empty:
        dist_yield_vals = []
        for d in df.index:
            one_yr_ago = date(d.year - 1, d.month, d.day)
            ttm_divs = dividends[(dividends.index > one_yr_ago) & (dividends.index <= d)]
            ttm_sum = float(ttm_divs.sum()) if not ttm_divs.empty else 0.0
            price = float(close[d])
            dist_yield_vals.append(ttm_sum / price if price > 0 and ttm_sum > 0 else None)
        df["distribution_yield"] = dist_yield_vals
    else:
        df["distribution_yield"] = None

    return df


def upsert_fund_prices(cur, asx_code: str, df: pd.DataFrame):
    if df.empty:
        return 0

    rows = []
    for price_date, row in df.iterrows():
        def _f(v):
            if v is None or (isinstance(v, float) and np.isnan(v)):
                return None
            return float(v)

        rows.append((
            asx_code,
            price_date,
            _f(row.get("close")),
            _f(row.get("open")),
            _f(row.get("high")),
            _f(row.get("low")),
            int(row["volume"]) if row.get("volume") and not np.isnan(row["volume"]) else None,
            _f(row.get("distribution_yield")),
            _f(row.get("return_1d")),
            _f(row.get("return_1w")),
            _f(row.get("return_1m")),
            _f(row.get("return_3m")),
            _f(row.get("return_6m")),
            _f(row.get("return_1y")),
            _f(row.get("return_3y_pa")),
            _f(row.get("return_5y_pa")),
            _f(row.get("return_ytd")),
            _f(row.get("high_52w")),
            _f(row.get("low_52w")),
        ))

    execute_values(cur, """
        INSERT INTO market.fund_prices (
            asx_code, price_date,
            close_price, open_price, high_price, low_price, volume,
            distribution_yield,
            return_1d, return_1w, return_1m, return_3m, return_6m, return_1y,
            return_3y_pa, return_5y_pa, return_ytd,
            high_52w, low_52w
        ) VALUES %s
        ON CONFLICT (asx_code, price_date) DO UPDATE SET
            close_price        = EXCLUDED.close_price,
            open_price         = EXCLUDED.open_price,
            high_price         = EXCLUDED.high_price,
            low_price          = EXCLUDED.low_price,
            volume             = EXCLUDED.volume,
            distribution_yield = EXCLUDED.distribution_yield,
            return_1d          = EXCLUDED.return_1d,
            return_1w          = EXCLUDED.return_1w,
            return_1m          = EXCLUDED.return_1m,
            return_3m          = EXCLUDED.return_3m,
            return_6m          = EXCLUDED.return_6m,
            return_1y          = EXCLUDED.return_1y,
            return_3y_pa       = EXCLUDED.return_3y_pa,
            return_5y_pa       = EXCLUDED.return_5y_pa,
            return_ytd         = EXCLUDED.return_ytd,
            high_52w           = EXCLUDED.high_52w,
            low_52w            = EXCLUDED.low_52w
    """, rows)

    return len(rows)


def update_aum_from_yahoo(cur, asx_code: str):
    """Try to update AUM from Yahoo Finance info."""
    try:
        t = yf.Ticker(f"{asx_code}.AX")
        info = t.info
        aum = info.get("totalAssets")
        if aum and aum > 0:
            aum_bn = aum / 1_000_000_000
            cur.execute(
                "UPDATE market.funds SET funds_under_mgmt_bn = %s, updated_at = NOW() WHERE asx_code = %s",
                (aum_bn, asx_code),
            )
    except Exception:
        pass


def run(
    codes: Optional[list] = None,
    days: int = 730,
    seed_only: bool = False,
    prices_only: bool = False,
):
    end_date   = date.today()
    start_date = end_date - timedelta(days=365 + days)

    conn = get_db()
    cur  = conn.cursor()

    # Step 1: Seed fund metadata
    if not prices_only:
        seed_funds(cur, codes)
        conn.commit()

    if seed_only:
        cur.close()
        conn.close()
        log.info("Seed-only mode — skipping price fetch")
        return

    # Step 2: Fetch which funds to price
    if codes:
        placeholders = ",".join(["%s"] * len(codes))
        cur.execute(
            f"SELECT asx_code FROM market.funds WHERE is_active = TRUE AND asx_code IN ({placeholders})",
            [c.upper() for c in codes],
        )
    else:
        cur.execute("SELECT asx_code FROM market.funds WHERE is_active = TRUE ORDER BY asx_code")
    fund_codes = [r[0] for r in cur.fetchall()]

    log.info(f"Fetching prices for {len(fund_codes)} funds | {start_date} → {end_date}")

    total_rows = 0
    for asx_code in fund_codes:
        ticker = f"{asx_code}.AX"
        log.info(f"  {asx_code} ← {ticker}")

        df   = fetch_yahoo_prices(ticker, start_date, end_date)
        divs = fetch_yahoo_dividends(ticker)

        if df.empty:
            log.warning(f"  {asx_code}: no price data, skipping")
            continue

        df = compute_fund_returns(df, divs)
        n  = upsert_fund_prices(cur, asx_code, df)
        update_aum_from_yahoo(cur, asx_code)
        conn.commit()

        log.info(f"  {asx_code}: upserted {n} rows")
        total_rows += n

    cur.close()
    conn.close()
    log.info(f"Done — {total_rows} total rows upserted across {len(fund_codes)} funds")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest ASX ETF/fund prices from Yahoo Finance")
    parser.add_argument("--codes",       nargs="+", help="Specific fund codes (e.g. VAS VGS NDQ)")
    parser.add_argument("--days",        type=int, default=730, help="Days of history to fetch (default 730)")
    parser.add_argument("--seed-only",   action="store_true",   help="Only upsert fund metadata, skip prices")
    parser.add_argument("--prices-only", action="store_true",   help="Skip metadata seed, only fetch prices")
    args = parser.parse_args()

    run(
        codes=args.codes,
        days=args.days,
        seed_only=args.seed_only,
        prices_only=args.prices_only,
    )
