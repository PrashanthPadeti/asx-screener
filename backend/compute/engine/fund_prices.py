"""
ASX ETF & Managed Funds Ingestion Engine
=========================================
Two jobs:
  1. seed_fund_metadata()  — upserts fund definitions into market.funds (idempotent)
  2. run()                 — fetches daily prices from Yahoo Finance and upserts
                             into market.fund_prices

Yahoo Finance ticker convention for ASX ETFs: "<CODE>.AX"

Usage (standalone):
    python -m compute.engine.fund_prices [--date YYYY-MM-DD] [--backfill-days N]
                                         [--seed-only] [--dry-run]
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

# ── Fund metadata ─────────────────────────────────────────────────────────────
# (asx_code, fund_name, fund_type, asset_class, index_tracked,
#  fund_manager, mer_pct, funds_under_mgmt_bn, distribution_freq, is_hedged)

FUNDS: list[dict] = [
    # ── Australian Equity ETFs ────────────────────────────────────────────────
    dict(asx_code="VAS",  fund_name="Vanguard Australian Shares ETF",               fund_type="ETF", asset_class="Australian Equities", index_tracked="S&P/ASX 300 Index",           fund_manager="Vanguard",    mer_pct=0.0007, funds_under_mgmt_bn=15.2, distribution_freq="quarterly", is_hedged=False),
    dict(asx_code="STW",  fund_name="SPDR S&P/ASX 200 Fund",                        fund_type="ETF", asset_class="Australian Equities", index_tracked="S&P/ASX 200 Index",           fund_manager="State Street", mer_pct=0.0013, funds_under_mgmt_bn=6.1, distribution_freq="quarterly", is_hedged=False),
    dict(asx_code="IOZ",  fund_name="iShares Core S&P/ASX 200 ETF",                 fund_type="ETF", asset_class="Australian Equities", index_tracked="S&P/ASX 200 Index",           fund_manager="BlackRock",   mer_pct=0.0009, funds_under_mgmt_bn=5.8, distribution_freq="quarterly", is_hedged=False),
    dict(asx_code="A200", fund_name="BetaShares Australia 200 ETF",                 fund_type="ETF", asset_class="Australian Equities", index_tracked="Solactive Australia 200 Index", fund_manager="BetaShares", mer_pct=0.0004, funds_under_mgmt_bn=5.2, distribution_freq="quarterly", is_hedged=False),
    dict(asx_code="ILC",  fund_name="iShares S&P/ASX 20 ETF",                       fund_type="ETF", asset_class="Australian Equities", index_tracked="S&P/ASX 20 Index",            fund_manager="BlackRock",   mer_pct=0.0024, funds_under_mgmt_bn=0.6, distribution_freq="quarterly", is_hedged=False),
    dict(asx_code="SFY",  fund_name="SPDR S&P/ASX 50 Fund",                         fund_type="ETF", asset_class="Australian Equities", index_tracked="S&P/ASX 50 Index",            fund_manager="State Street", mer_pct=0.0029, funds_under_mgmt_bn=0.8, distribution_freq="quarterly", is_hedged=False),
    dict(asx_code="MVW",  fund_name="VanEck Australian Equal Weight ETF",            fund_type="ETF", asset_class="Australian Equities", index_tracked="MVIS Australia Equal Weight Index", fund_manager="VanEck", mer_pct=0.0035, funds_under_mgmt_bn=2.0, distribution_freq="quarterly", is_hedged=False),
    dict(asx_code="AUST", fund_name="BetaShares Managed Risk Australian Share Fund", fund_type="ETF", asset_class="Australian Equities", index_tracked=None,                          fund_manager="BetaShares",  mer_pct=0.0049, funds_under_mgmt_bn=0.3, distribution_freq="quarterly", is_hedged=False),
    dict(asx_code="OZF",  fund_name="BetaShares S&P/ASX 200 Financials Sector ETF", fund_type="ETF", asset_class="Australian Equities", index_tracked="S&P/ASX 200 Financials Index", fund_manager="BetaShares", mer_pct=0.0034, funds_under_mgmt_bn=0.2, distribution_freq="quarterly", is_hedged=False),
    dict(asx_code="OZR",  fund_name="BetaShares S&P/ASX 200 Resources Sector ETF",  fund_type="ETF", asset_class="Australian Equities", index_tracked="S&P/ASX 200 Materials Index",  fund_manager="BetaShares", mer_pct=0.0034, funds_under_mgmt_bn=0.2, distribution_freq="quarterly", is_hedged=False),
    dict(asx_code="HVST", fund_name="BetaShares Australian Dividend Harvester Fund", fund_type="ETF", asset_class="Australian Equities", index_tracked=None,                          fund_manager="BetaShares",  mer_pct=0.0080, funds_under_mgmt_bn=0.5, distribution_freq="monthly",   is_hedged=False),
    dict(asx_code="DIV",  fund_name="Plato Australian Shares Income ETF",            fund_type="ETF", asset_class="Australian Equities", index_tracked=None,                          fund_manager="Plato",       mer_pct=0.0080, funds_under_mgmt_bn=0.3, distribution_freq="monthly",   is_hedged=False),
    dict(asx_code="YMAX", fund_name="BetaShares Australia Top 20 Equity Yield Maximiser", fund_type="ETF", asset_class="Australian Equities", index_tracked=None,                   fund_manager="BetaShares",  mer_pct=0.0076, funds_under_mgmt_bn=0.2, distribution_freq="monthly",   is_hedged=False),
    # ── Global Equity ETFs ────────────────────────────────────────────────────
    dict(asx_code="VGS",  fund_name="Vanguard MSCI Index International Shares ETF",          fund_type="ETF", asset_class="Global Equities", index_tracked="MSCI World ex-Australia Index",       fund_manager="Vanguard",    mer_pct=0.0018, funds_under_mgmt_bn=15.8, distribution_freq="quarterly", is_hedged=False),
    dict(asx_code="IVV",  fund_name="iShares S&P 500 ETF",                                   fund_type="ETF", asset_class="Global Equities", index_tracked="S&P 500 Index",                      fund_manager="BlackRock",   mer_pct=0.0004, funds_under_mgmt_bn=8.4, distribution_freq="quarterly", is_hedged=False),
    dict(asx_code="NDQ",  fund_name="BetaShares NASDAQ 100 ETF",                              fund_type="ETF", asset_class="Global Equities", index_tracked="NASDAQ-100 Index",                   fund_manager="BetaShares",  mer_pct=0.0048, funds_under_mgmt_bn=7.1, distribution_freq="quarterly", is_hedged=False),
    dict(asx_code="QUAL", fund_name="VanEck MSCI International Quality ETF",                  fund_type="ETF", asset_class="Global Equities", index_tracked="MSCI World ex Australia Quality Index", fund_manager="VanEck",   mer_pct=0.0040, funds_under_mgmt_bn=4.6, distribution_freq="quarterly", is_hedged=False),
    dict(asx_code="VEU",  fund_name="Vanguard All-World ex-US Shares ETF",                    fund_type="ETF", asset_class="Global Equities", index_tracked="FTSE All-World ex US Index",         fund_manager="Vanguard",    mer_pct=0.0008, funds_under_mgmt_bn=1.1, distribution_freq="quarterly", is_hedged=False),
    dict(asx_code="IHVV", fund_name="iShares S&P 500 (AUD Hedged) ETF",                       fund_type="ETF", asset_class="Global Equities", index_tracked="S&P 500 Index",                      fund_manager="BlackRock",   mer_pct=0.0010, funds_under_mgmt_bn=2.8, distribution_freq="quarterly", is_hedged=True),
    dict(asx_code="VGAD", fund_name="Vanguard MSCI Index International Shares (Hedged) ETF",  fund_type="ETF", asset_class="Global Equities", index_tracked="MSCI World ex-Australia Index",       fund_manager="Vanguard",    mer_pct=0.0021, funds_under_mgmt_bn=3.2, distribution_freq="quarterly", is_hedged=True),
    dict(asx_code="FANG", fund_name="BetaShares FAANG+ ETF",                                  fund_type="ETF", asset_class="Global Equities", index_tracked=None,                                 fund_manager="BetaShares",  mer_pct=0.0057, funds_under_mgmt_bn=0.5, distribution_freq="semi-annual", is_hedged=False),
    dict(asx_code="RBTZ", fund_name="BetaShares Global Robotics and AI ETF",                  fund_type="ETF", asset_class="Global Equities", index_tracked=None,                                 fund_manager="BetaShares",  mer_pct=0.0057, funds_under_mgmt_bn=0.6, distribution_freq="annual",   is_hedged=False),
    dict(asx_code="HACK", fund_name="BetaShares Global Cybersecurity ETF",                    fund_type="ETF", asset_class="Global Equities", index_tracked=None,                                 fund_manager="BetaShares",  mer_pct=0.0067, funds_under_mgmt_bn=0.9, distribution_freq="annual",   is_hedged=False),
    dict(asx_code="SEMI", fund_name="BetaShares Global Semiconductor ETF",                    fund_type="ETF", asset_class="Global Equities", index_tracked=None,                                 fund_manager="BetaShares",  mer_pct=0.0057, funds_under_mgmt_bn=1.2, distribution_freq="annual",   is_hedged=False),
    # ── Fixed Income ETFs ─────────────────────────────────────────────────────
    dict(asx_code="VAF",  fund_name="Vanguard Australian Fixed Interest ETF",      fund_type="ETF", asset_class="Fixed Income", index_tracked="Bloomberg AusBond Composite 0+ Yr Index", fund_manager="Vanguard",   mer_pct=0.0020, funds_under_mgmt_bn=2.3, distribution_freq="monthly",   is_hedged=False),
    dict(asx_code="VGB",  fund_name="Vanguard Australian Government Bond ETF",     fund_type="ETF", asset_class="Fixed Income", index_tracked="Bloomberg AusBond Govt 0+ Yr Index",       fund_manager="Vanguard",   mer_pct=0.0020, funds_under_mgmt_bn=0.9, distribution_freq="monthly",   is_hedged=False),
    dict(asx_code="QPON", fund_name="BetaShares Australian Bank Senior Floating Rate Bond ETF", fund_type="ETF", asset_class="Fixed Income", index_tracked=None,                      fund_manager="BetaShares", mer_pct=0.0022, funds_under_mgmt_bn=2.8, distribution_freq="monthly",   is_hedged=False),
    dict(asx_code="CRED", fund_name="BetaShares Australian Investment Grade Corporate Bond ETF", fund_type="ETF", asset_class="Fixed Income", index_tracked=None,                     fund_manager="BetaShares", mer_pct=0.0025, funds_under_mgmt_bn=0.8, distribution_freq="monthly",   is_hedged=False),
    dict(asx_code="IAF",  fund_name="iShares Core Composite Bond ETF",             fund_type="ETF", asset_class="Fixed Income", index_tracked="Bloomberg AusBond Composite 0+ Yr Index", fund_manager="BlackRock",  mer_pct=0.0015, funds_under_mgmt_bn=1.6, distribution_freq="monthly",   is_hedged=False),
    # ── Property ETFs ─────────────────────────────────────────────────────────
    dict(asx_code="VAP",  fund_name="Vanguard Australian Property Securities ETF", fund_type="ETF", asset_class="Property", index_tracked="S&P/ASX 300 A-REIT Index", fund_manager="Vanguard",   mer_pct=0.0023, funds_under_mgmt_bn=3.1, distribution_freq="quarterly", is_hedged=False),
    dict(asx_code="MVA",  fund_name="VanEck Vectors Australian Property ETF",      fund_type="ETF", asset_class="Property", index_tracked="MVIS Australia A-REITs Index", fund_manager="VanEck", mer_pct=0.0035, funds_under_mgmt_bn=0.4, distribution_freq="quarterly", is_hedged=False),
    # ── Commodities ETFs ──────────────────────────────────────────────────────
    dict(asx_code="GOLD", fund_name="BetaShares Gold Bullion ETF (AUD Hedged)",    fund_type="ETF", asset_class="Commodities", index_tracked=None, fund_manager="BetaShares", mer_pct=0.0059, funds_under_mgmt_bn=1.8, distribution_freq=None, is_hedged=True),
    dict(asx_code="MNRS", fund_name="BetaShares Global Gold Miners ETF",           fund_type="ETF", asset_class="Commodities", index_tracked=None, fund_manager="BetaShares", mer_pct=0.0057, funds_under_mgmt_bn=0.3, distribution_freq=None, is_hedged=False),
    dict(asx_code="QAU",  fund_name="BetaShares Gold Bullion ETF (Unhedged)",      fund_type="ETF", asset_class="Commodities", index_tracked=None, fund_manager="BetaShares", mer_pct=0.0059, funds_under_mgmt_bn=0.3, distribution_freq=None, is_hedged=False),
    dict(asx_code="OOO",  fund_name="BetaShares Crude Oil Index ETF (Hedged)",     fund_type="ETF", asset_class="Commodities", index_tracked=None, fund_manager="BetaShares", mer_pct=0.0069, funds_under_mgmt_bn=0.1, distribution_freq=None, is_hedged=True),
    # ── Multi-Asset ETFs ──────────────────────────────────────────────────────
    dict(asx_code="VDGR", fund_name="Vanguard Diversified Growth ETF",             fund_type="ETF", asset_class="Multi-Asset", index_tracked=None, fund_manager="Vanguard",   mer_pct=0.0027, funds_under_mgmt_bn=2.2, distribution_freq="quarterly", is_hedged=False),
    dict(asx_code="VDHG", fund_name="Vanguard Diversified High Growth ETF",        fund_type="ETF", asset_class="Multi-Asset", index_tracked=None, fund_manager="Vanguard",   mer_pct=0.0027, funds_under_mgmt_bn=4.1, distribution_freq="quarterly", is_hedged=False),
    dict(asx_code="VDBA", fund_name="Vanguard Diversified Balanced ETF",           fund_type="ETF", asset_class="Multi-Asset", index_tracked=None, fund_manager="Vanguard",   mer_pct=0.0027, funds_under_mgmt_bn=0.8, distribution_freq="quarterly", is_hedged=False),
    dict(asx_code="VDCO", fund_name="Vanguard Diversified Conservative ETF",       fund_type="ETF", asset_class="Multi-Asset", index_tracked=None, fund_manager="Vanguard",   mer_pct=0.0027, funds_under_mgmt_bn=0.4, distribution_freq="quarterly", is_hedged=False),
    # ── LICs (Listed Investment Companies) ───────────────────────────────────
    dict(asx_code="AFI",  fund_name="Australian Foundation Investment Company",    fund_type="LIC", asset_class="Australian Equities", index_tracked=None, fund_manager="AFIC",        mer_pct=0.0013, funds_under_mgmt_bn=9.8, distribution_freq="semi-annual", is_hedged=False),
    dict(asx_code="ARG",  fund_name="Argo Investments",                            fund_type="LIC", asset_class="Australian Equities", index_tracked=None, fund_manager="Argo",        mer_pct=0.0015, funds_under_mgmt_bn=6.3, distribution_freq="semi-annual", is_hedged=False),
    # MLT (Milton Corporation) merged with SOL (Washington H. Soul Pattinson) Nov 2021 — delisted
    dict(asx_code="BKI",  fund_name="BKI Investment Company",                      fund_type="LIC", asset_class="Australian Equities", index_tracked=None, fund_manager="Contact Asset Management", mer_pct=0.0017, funds_under_mgmt_bn=1.3, distribution_freq="semi-annual", is_hedged=False),
    dict(asx_code="WHF",  fund_name="Whitefield Industrials",                      fund_type="LIC", asset_class="Australian Equities", index_tracked=None, fund_manager="Whitefield", mer_pct=0.0026, funds_under_mgmt_bn=0.7, distribution_freq="semi-annual", is_hedged=False),
    dict(asx_code="WAM",  fund_name="WAM Capital",                                 fund_type="LIC", asset_class="Australian Equities", index_tracked=None, fund_manager="Wilson Asset Management", mer_pct=0.0100, funds_under_mgmt_bn=2.0, distribution_freq="semi-annual", is_hedged=False),
    dict(asx_code="WAX",  fund_name="WAM Research",                                fund_type="LIC", asset_class="Australian Equities", index_tracked=None, fund_manager="Wilson Asset Management", mer_pct=0.0100, funds_under_mgmt_bn=0.4, distribution_freq="semi-annual", is_hedged=False),
    dict(asx_code="MFF",  fund_name="MFF Capital Investments",                     fund_type="LIC", asset_class="Global Equities",     index_tracked=None, fund_manager="Magellan Financial Group", mer_pct=0.0110, funds_under_mgmt_bn=2.3, distribution_freq="annual",      is_hedged=False),
    dict(asx_code="PMC",  fund_name="Platinum Capital",                            fund_type="LIC", asset_class="Global Equities",     index_tracked=None, fund_manager="Platinum",   mer_pct=0.0115, funds_under_mgmt_bn=0.6, distribution_freq="semi-annual", is_hedged=False),
]

# ── Yahoo Finance ticker map (ASX code → YF ticker) ──────────────────────────

def _yf_ticker(asx_code: str) -> str:
    return f"{asx_code}.AX"


# ── Return computation (reuse logic from index_prices) ───────────────────────

def _pct(series: pd.Series, i: int, lookback: int) -> float | None:
    if i < lookback:
        return None
    prior = series.iloc[i - lookback]
    cur   = series.iloc[i]
    if prior == 0 or pd.isna(prior) or pd.isna(cur):
        return None
    return float((cur - prior) / prior)


def _ytd(series: pd.Series, dates: pd.DatetimeIndex, i: int) -> float | None:
    cur_date  = dates[i]
    year_start = pd.Timestamp(cur_date.year, 1, 1)
    mask = dates < year_start
    if not mask.any():
        return None
    prior = series[mask].iloc[-1]
    cur   = series.iloc[i]
    if prior == 0 or pd.isna(prior) or pd.isna(cur):
        return None
    return float((cur - prior) / prior)


def _trailing_yield(closes: pd.Series, dates: pd.DatetimeIndex, i: int) -> float | None:
    """Approximate trailing 12M distribution yield — not available from price data alone."""
    return None


def compute_rows(df: pd.DataFrame) -> list[dict]:
    closes = df["close"]
    dates  = df.index
    rows   = []

    for i in range(len(df)):
        row   = df.iloc[i]
        close = row["close"]
        if pd.isna(close):
            continue

        window = closes.iloc[max(0, i - 251): i + 1].dropna()
        high_52w = float(window.max()) if len(window) >= 5 else None
        low_52w  = float(window.min()) if len(window) >= 5 else None

        rows.append({
            "price_date":  dates[i].date(),
            "close_price": float(close),
            "open_price":  float(row["open"])   if not pd.isna(row.get("open",   float("nan"))) else None,
            "high_price":  float(row["high"])   if not pd.isna(row.get("high",   float("nan"))) else None,
            "low_price":   float(row["low"])    if not pd.isna(row.get("low",    float("nan"))) else None,
            "volume":      int(row["volume"])   if not pd.isna(row.get("volume", float("nan"))) else None,
            "return_1d":   _pct(closes, i, 1),
            "return_1w":   _pct(closes, i, 5),
            "return_1m":   _pct(closes, i, 21),
            "return_3m":   _pct(closes, i, 63),
            "return_6m":   _pct(closes, i, 126),
            "return_1y":   _pct(closes, i, 252),
            "return_ytd":  _ytd(closes, dates, i),
            "high_52w":    high_52w,
            "low_52w":     low_52w,
            "nav":                None,
            "nav_discount_pct":   None,
            "distribution_yield": None,
            "return_3y_pa":       None,
            "return_5y_pa":       None,
        })
    return rows


# ── Fetch from Yahoo Finance ──────────────────────────────────────────────────

def fetch_fund_data(ticker: str, start_date: date, end_date: date, retries: int = 3) -> pd.DataFrame | None:
    import time
    try:
        import yfinance as yf
    except ImportError:
        log.error("yfinance not installed")
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
                log.warning(f"{ticker}: no data from Yahoo Finance")
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


# ── DB operations ─────────────────────────────────────────────────────────────

async def seed_fund_metadata(db, dry_run: bool = False) -> int:
    from sqlalchemy import text

    if dry_run:
        log.info(f"[dry-run] would seed {len(FUNDS)} fund records")
        return len(FUNDS)

    for f in FUNDS:
        await db.execute(text("""
            INSERT INTO market.funds (
                asx_code, fund_name, fund_type, asset_class, index_tracked,
                fund_manager, mer_pct, funds_under_mgmt_bn, distribution_freq,
                is_hedged, is_active
            ) VALUES (
                :asx_code, :fund_name, :fund_type, :asset_class, :index_tracked,
                :fund_manager, :mer_pct, :funds_under_mgmt_bn, :distribution_freq,
                :is_hedged, TRUE
            )
            ON CONFLICT (asx_code) DO UPDATE SET
                fund_name           = EXCLUDED.fund_name,
                fund_type           = EXCLUDED.fund_type,
                asset_class         = EXCLUDED.asset_class,
                index_tracked       = EXCLUDED.index_tracked,
                fund_manager        = EXCLUDED.fund_manager,
                mer_pct             = EXCLUDED.mer_pct,
                funds_under_mgmt_bn = EXCLUDED.funds_under_mgmt_bn,
                distribution_freq   = EXCLUDED.distribution_freq,
                is_hedged           = EXCLUDED.is_hedged,
                updated_at          = NOW()
        """), f)

    await db.commit()
    log.info(f"Seeded {len(FUNDS)} fund records")
    return len(FUNDS)


async def upsert_price_rows(db, asx_code: str, rows: list[dict], dry_run: bool) -> int:
    from sqlalchemy import text

    if not rows:
        return 0
    if dry_run:
        log.info(f"  [dry-run] would upsert {len(rows)} rows for {asx_code}")
        return len(rows)

    for row in rows:
        await db.execute(text("""
            INSERT INTO market.fund_prices (
                asx_code, price_date,
                close_price, open_price, high_price, low_price, volume,
                return_1d, return_1w, return_1m, return_3m, return_6m,
                return_1y, return_ytd, return_3y_pa, return_5y_pa,
                high_52w, low_52w,
                nav, nav_discount_pct, distribution_yield
            ) VALUES (
                :asx_code, :price_date,
                :close_price, :open_price, :high_price, :low_price, :volume,
                :return_1d, :return_1w, :return_1m, :return_3m, :return_6m,
                :return_1y, :return_ytd, :return_3y_pa, :return_5y_pa,
                :high_52w, :low_52w,
                :nav, :nav_discount_pct, :distribution_yield
            )
            ON CONFLICT (asx_code, price_date) DO UPDATE SET
                close_price       = EXCLUDED.close_price,
                open_price        = EXCLUDED.open_price,
                high_price        = EXCLUDED.high_price,
                low_price         = EXCLUDED.low_price,
                volume            = EXCLUDED.volume,
                return_1d         = EXCLUDED.return_1d,
                return_1w         = EXCLUDED.return_1w,
                return_1m         = EXCLUDED.return_1m,
                return_3m         = EXCLUDED.return_3m,
                return_6m         = EXCLUDED.return_6m,
                return_1y         = EXCLUDED.return_1y,
                return_ytd        = EXCLUDED.return_ytd,
                high_52w          = EXCLUDED.high_52w,
                low_52w           = EXCLUDED.low_52w
        """), {"asx_code": asx_code, **row})

    await db.commit()
    return len(rows)


# ── Main entry ────────────────────────────────────────────────────────────────

async def run(
    target_date: date | None = None,
    backfill_days: int = 3,
    seed_only: bool = False,
    dry_run: bool = False,
) -> None:
    from app.db.session import AsyncSessionLocal

    if target_date is None:
        target_date = date.today()
    start_date = target_date - timedelta(days=backfill_days)

    log.info(f"Fund prices: {start_date} → {target_date}  seed_only={seed_only}  dry_run={dry_run}")

    async with AsyncSessionLocal() as db:
        await seed_fund_metadata(db, dry_run)

        if seed_only:
            return

        import time
        total_rows = 0
        for i, fund in enumerate(FUNDS):
            code   = fund["asx_code"]
            ticker = _yf_ticker(code)
            log.info(f"  [{i+1}/{len(FUNDS)}] {code} ({ticker}) …")

            # Polite delay — avoid Yahoo Finance rate limits
            if i > 0:
                time.sleep(2)

            df = fetch_fund_data(ticker, start_date, target_date)
            if df is None:
                continue

            if df.empty:
                log.info(f"  {code}: no data returned")
                continue

            # Compute returns on the FULL fetched history (includes 400-day lookback
            # context needed for 1Y returns), then filter rows to the target window.
            all_rows = compute_rows(df)
            rows = [
                r for r in all_rows
                if start_date <= r["price_date"] <= target_date
            ]
            count = await upsert_price_rows(db, code, rows, dry_run)
            log.info(f"  {code}: {count} rows upserted")
            total_rows += count

    log.info(f"Fund prices complete — {total_rows} total rows across {len(FUNDS)} funds")


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest ASX ETF/Fund prices from Yahoo Finance")
    parser.add_argument("--date",          default=None,  help="Target date YYYY-MM-DD (default: today)")
    parser.add_argument("--backfill-days", type=int, default=3,
                        help="Calendar days to backfill (default: 3; use 1825 for 5Y initial load)")
    parser.add_argument("--seed-only",     action="store_true", help="Only upsert fund metadata, skip prices")
    parser.add_argument("--dry-run",       action="store_true", help="Print without writing to DB")
    args = parser.parse_args()

    target = date.fromisoformat(args.date) if args.date else date.today()

    DATABASE_URL = os.environ.get("DATABASE_URL", "")
    if not DATABASE_URL and not args.dry_run:
        log.error("DATABASE_URL not set")
        sys.exit(1)

    asyncio.run(run(
        target_date=target,
        backfill_days=args.backfill_days,
        seed_only=args.seed_only,
        dry_run=args.dry_run,
    ))
