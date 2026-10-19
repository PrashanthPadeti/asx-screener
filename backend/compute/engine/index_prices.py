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
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from compute.engine.producer_contract import ProducerTally, SourceRefused

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# ── Per-index source, provider and effective date ────────────────────────────
#
# ASX100 stopped publishing on 2026-05-29 while every other index stayed
# current. MEASURED 12 Oct 2026, with ^AXJO as a control:
#
#   ^AXJO  21 rows, current          <- control, Yahoo is answering
#   ^AXTO   0 rows, no data returned
#   ^ATOI  21 rows, current          <- a live Yahoo ASX 100 symbol
#
# What that establishes: the CONFIGURED SYMBOL returns no data while the
# provider is reachable and an alternative symbol responds. yfinance prints
# "possibly delisted" for any empty result, so it is the library guessing,
# not Yahoo stating a retirement. The provider's reason is UNCONFIRMED.
#
# The failure is therefore an unavailable configured symbol, and the
# producer could not tell: fetch_index_data returns None for an empty frame,
# the tally counts it as nothing_available, and nine of ten succeeding keeps
# the run green. A dead symbol is indistinguishable from "no data today"
# under an all-or-nothing contract.
#
# ^ATOI would be a smaller repair -- same provider, one line. It is
# NOT taken, for two reasons. First, its values could not be verified:
# yfinance refused this host on three consecutive attempts, including the
# comparison needed to choose it. Second, the failure mode being repaired is
# a Yahoo symbol retiring silently, and moving to another Yahoo symbol leaves
# that intact. EODHD is authenticated, answered every request, and its series
# identity IS verified below.
#
# Identity evidence (12 Oct 2026), recorded so the switch is auditable:
#
#   every stored ASX100 date since 2026-01-01 exists in EODHD ATOI.INDX  (103/103)
#   96 of those 103 closes agree to within 0.01
#   control: AXJO.INDX differs from the stored ASX100 by ~1,427 points
#
# RETURN TYPE -- CONFIRMED BY THE INDEX OWNER, 12 Oct 2026.
#
# S&P Dow Jones Indices' own page for the S&P/ASX 100 states:
#
#   7,328.88 AUD    PRICE RETURN    0.66% 1 Day    As of Oct 09, 2026
#
# and EODHD's ATOI.INDX close for that date is 7328.8999 -- a difference of
# 0.0199 points, 0.0003%.
#
# The cause of that difference is NOT established. EODHD's storage
# representation has not been verified, so attributing it to float precision
# would be a guess; vendor rounding, a different snapshot time, or a revision
# are equally consistent with what was observed. Recorded as an unexplained
# 0.0199-point difference. At that magnitude it does not disturb the mapping,
# which is what this evidence is for.
#
# So price-return and AUD rest on the vendor of record, not on inference.
# EODHD's own metadata does NOT state return type -- Type is "INDEX" and
# Category is null -- which is exactly why the index owner was consulted.
# Corroborating: Morningstar names it "S&P/ASX 100 PR" under code XTO, and
# Market Index reports 4.09% p.a. ex-dividend against 8.50% including.
#
# WHERE RETURNS COME FROM. compute_rows() reads `df["close"]` and nothing
# else: every return_1d..return_1y, return_ytd and the 52-week range is
# computed from the FETCHED frame. Stored history is never an input. So a
# post-switch row's returns are single-source EODHD over a continuous ~400
# days -- correct precisely BECAUSE the gap rows are fetched; computing them
# from stored history would span a 95-session hole.
#
# What is mixed is the DISPLAYED SERIES, not any individual figure: the chart
# shows Yahoo-derived rows to 2026-05-29, then a gap, then EODHD-derived rows
# from the switch date. Each row's returns stay within one source.
#
# UNRESOLVED: seven of the 103 dates differ by up to 38.2 points (~0.5%),
# scattered across January-March, signs in both directions. Cause unknown.
# The overlap supports identity FOR THE TESTED PERIOD. It does not validate
# all 778 stored rows, 675 of which predate 2026 and were never compared.

@dataclass(frozen=True)
class IndexSource:
    """Where an index's prices come from, and from when.

    `effective_from` is the FORWARD-ONLY boundary. Rows dated before it are
    never written, so a source switch cannot rewrite history that a different
    provider produced. Fetching still reaches further back, because a 1-year
    return needs a year of context -- but that context is used for
    COMPUTATION only, never persisted.

    Leaving it None means "this source has always been the source", which is
    true of every Yahoo index here.
    """
    provider: str                    # "yahoo" | "eodhd"
    symbol: str
    effective_from: date | None = None

    def first_writable(self, start_date: date) -> date:
        return max(start_date, self.effective_from) if self.effective_from else start_date


#: The switch date for ASX100. Declared as a constant so the boundary is one
#: reviewable value rather than a literal buried in a map.
ASX100_SWITCH_DATE = date(2026, 10, 13)

#: Five more indices move to EODHD, 19 Oct 2026.
#:
#: WHY THIS DATE: the last stored row for every index switched here is
#: 2026-10-16 -- Yahoo has refused this host since the 17th. 2026-10-17 is
#: therefore the first session with no existing row, so EODHD cannot
#: overwrite anything Yahoo produced while still recovering the outage gap.
#: Filling dates that hold no rows is not a historical overwrite; the
#: forward-only rule exists to stop one provider silently restating
#: another's values, and there are none here to restate.
#:
#: Had any of these carried a row on or after this date, the date would have
#: to move forward. That is a property of the DATABASE, not of this file, so
#: no unit test can establish it -- it is an acceptance check, run against
#: production before release:
#:
#:   SELECT index_code, max(price_date) FROM market.index_prices
#:    WHERE index_code IN ('ASX50','ASX200','ASX300','AXEJ','AXHJ')
#:    GROUP BY index_code;        -- every row must be < 2026-10-17
#:
#: What the unit tests CAN establish, and do, is that nothing before the
#: effective date is ever writable whatever that date is.
INDEX_EODHD_SWITCH = date(2026, 10, 17)

#: EVIDENCE for each mapping below, measured 19 Oct 2026 over 1,351 stored
#: sessions (2021-05-10 .. 2026-10-16) by
#: `backend/scripts/eodhd_index_discovery.py`:
#:
#:   code    symbol       level med   return med   outliers >1%
#:   ASX50   AFLI.INDX    0.00000%    0.00000pp    0/1351
#:   ASX200  AXJO.INDX    0.00000%    0.00000pp    0/1351
#:   ASX300  AXKO.INDX    0.00000%    0.00000pp    0/1351
#:   AXEJ    AXEJ.INDX    0.00000%    0.00000pp    0/1351
#:   AXHJ    AXHJ.INDX    0.00000%    0.00000pp    0/1351
#:
#: The rule was fixed before the results were read: shared >= 20 sessions,
#: median level < 0.05%, median daily-return < 0.02pp, outliers <= 2%, and
#: the symbol's NAME must name the intended index. ASX100/ATOI.INDX was the
#: control -- a mapping established independently -- and the method
#: reproduced it, which is why the rest of its output is usable at all.
#:
#: ASX200 had TWO passing candidates, AXJO.INDX and XJO.INDX, identical on
#: all 1,351 sessions. Tie broken on `asx_indices.py`, which already uses
#: AXJO.INDX for ASX 200 constituents: one symbol per index across the
#: codebase, rather than two names for one series in different modules.
#: A documented reason, not a coin toss.
SOURCES: dict[str, IndexSource] = {
    # STAYS ON YAHOO -- not because Yahoo is working (it is refusing) but
    # because the evidence to switch does not exist. Our own stored history
    # for these three holds the wrong series from 2025-05 to 2026-05, so
    # "does this symbol continue what we publish" cannot be answered: what we
    # publish is not one series. ATLI.INDX, AXFJ.INDX and AXMJ.INDX each
    # failed the outlier cap at ~19.6% against their OWN code's history.
    # They become switchable when the repair makes them one series again.
    # See docs/finding_2026-10-19_three_indices_wrong_for_13_months.md
    "ASX20":  IndexSource("yahoo", "^ATLI"),
    "AXFJ":   IndexSource("yahoo", "^AXFJ"),
    "AXMJ":   IndexSource("yahoo", "^AXMJ"),

    # SWITCHED -- exact agreement across the full stored history.
    "ASX50":  IndexSource("eodhd", "AFLI.INDX", effective_from=INDEX_EODHD_SWITCH),
    "ASX100": IndexSource("eodhd", "ATOI.INDX", effective_from=ASX100_SWITCH_DATE),
    "ASX200": IndexSource("eodhd", "AXJO.INDX", effective_from=INDEX_EODHD_SWITCH),
    "ASX300": IndexSource("eodhd", "AXKO.INDX", effective_from=INDEX_EODHD_SWITCH),
    "AXEJ":   IndexSource("eodhd", "AXEJ.INDX", effective_from=INDEX_EODHD_SWITCH),
    "AXHJ":   IndexSource("eodhd", "AXHJ.INDX", effective_from=INDEX_EODHD_SWITCH),
}

#: Published indices that this producer deliberately does NOT fetch.
#:
#: An index served to customers but absent from SOURCES is invisible to this
#: producer. `expected` is len(SOURCES) + len(this), so without the second
#: term the population is defined by the fetch list and cannot count what the
#: fetch list omits -- the exact defect v11.2.22 fixed in fund_prices, where
#: eight ETFs served June prices for four months inside a job reporting
#: success every day.
#:
#: AXJO has been standing in that blind spot since v11.2.18: correctly
#: withheld, documented in the comment below, and recorded in no run. On
#: 14 Oct 2026 the run logged "9/9 obtained" -- a perfect score over a
#: population that had quietly excluded its tenth member.
#:
#: A comment explains a decision to whoever opens the file. An outcome
#: reports it to whoever reads the run. Declared here, AXJO is counted in
#: `expected` and recorded every run as EXCLUDED with its reason, so the log
#: accounts for ten indices and says why one of them has no new rows.
#:
#: Removing an entry here without adding it to SOURCES puts that index back
#: into the blind spot, which is why `excluded()` refuses a reason-less
#: exclusion.
#: NOTE the collision hazard: our internal code `AXJO` (excluded below) and
#: EODHD's symbol `AXJO.INDX` (which SOURCES maps to our ASX200) are
#: different things. EODHD's AXJO is the S&P/ASX 200 price index. Our AXJO
#: is a code that was published as the ASX 200 ACCUMULATION index and served
#: price data -- the defect v11.2.18 contained. EODHD lists that series
#: separately as AXJOA.INDX, which is the lead for resolving it and is
#: deliberately not acted on here.
EXCLUDED_SOURCES: dict[str, str] = {
    "AXJO": "series provenance unverified — ^AXJO is the price-only series "
            "while AXJO is published as a total-return index; nothing "
            "correct to fetch until the intended index and a verified "
            "provider series are settled",
}


# ── Ticker mapping ────────────────────────────────────────────────────────────
#
# Derived from SOURCES so there is one population, not two that can drift.
# SOURCES is authoritative: it carries the provider and the effective date,
# which a bare ticker map cannot express.
#
# AXJO is DELIBERATELY ABSENT. See
# docs/finding_2026-10-09_axjo_accumulation_is_price_series.md
#
# It was mapped to "^AXJO" with the comment "accumulation — same price
# series as ASX200 on Yahoo", while the API presented it as "S&P/ASX 200
# Accumulation ... the total return version ... incorporating
# reinvestment of dividends". ^AXJO is the price-only series, so the
# surface advertised as a total-return benchmark was served price data.
#
# The codebase does not agree on what AXJO even is: index_prices called
# it the ASX200 accumulation series, indices_funds describes it as the
# ASX 200 total return with ~200 constituents, and three frontend
# comments call it "All Ordinaries, ~500 stocks". Until the intended
# index is settled AND a provider series is verified for return type,
# currency, dividend treatment and date coverage, there is nothing
# correct to fetch. Existing rows are preserved for investigation; this
# only stops new ones being written under a provenance we cannot support.

TICKER_MAP: dict[str, str] = {
    code: src.symbol for code, src in SOURCES.items() if src.provider == "yahoo"
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
) -> pd.DataFrame | None:
    """Download OHLCV from Yahoo Finance.

    Returns None when the source legitimately has nothing for this ticker.
    Raises SourceRefused when the source declines to serve us — those are
    different events and the caller must be able to tell them apart.

    No retry on refusal, deliberately. The previous implementation tried three
    times with 5s/10s/15s backoff. Measured on 4, 5 and 6 October 2026: the
    very first request of the day was refused at 06:30:03-06:30:07, every
    ticker then failed all three attempts, and the whole cascade bought
    nothing at a cost of ~30s per ticker — 375s per run for a job whose work
    takes under a second when the source is willing. Retrying inside a window
    that is already closed cannot succeed; and if refusals count toward the
    upstream's rolling quota, the retries feed the block they are retrying
    against.
    """
    try:
        import yfinance as yf
    except ImportError:
        log.error("yfinance not installed — run: pip install yfinance")
        return None

    try:
        t = yf.Ticker(ticker)
        hist = t.history(
            start=(start_date - timedelta(days=400)).isoformat(),
            end=(end_date + timedelta(days=1)).isoformat(),
            auto_adjust=True,
        )
    except Exception as exc:
        msg = str(exc)
        if "Too Many Requests" in msg or "rate limit" in msg.lower():
            log.warning(f"{ticker}: source refused the request — {msg[:120]}")
            raise SourceRefused(ticker, msg[:120]) from exc
        log.warning(f"{ticker}: fetch failed — {exc}")
        return None

    if hist.empty:
        log.warning(f"{ticker}: no data returned from Yahoo Finance")
        return None

    hist.index = hist.index.tz_localize(None)
    df = hist[["Open", "High", "Low", "Close", "Volume"]].copy()
    df.columns = ["open", "high", "low", "close", "volume"]
    return df.sort_index()


def fetch_eodhd_index(
    symbol: str,
    start_date: date,
    end_date: date,
) -> pd.DataFrame | None:
    """Download daily OHLCV from EODHD.

    Same contract as `fetch_index_data`: returns None when the source
    legitimately has nothing, raises SourceRefused when it declines to serve
    us. The caller must be able to tell those apart -- conflating them is the
    defect `producer_contract` exists to prevent.

    Returns the same frame shape as the Yahoo path (lowercase OHLCV columns,
    DatetimeIndex) so `compute_rows` is untouched by the provider change.

    The 400-day lookback matches the Yahoo path and exists for computation
    only: a 1-year return needs a year of context. Rows outside the writable
    window are discarded by the caller, so reaching back here does NOT
    backfill history.
    """
    import httpx                                               # noqa: PLC0415

    from app.core.config import settings                       # noqa: PLC0415
    key = settings.EODHD_API_KEY
    if not key:
        log.error("EODHD_API_KEY not set — cannot fetch %s", symbol)
        return None

    try:
        r = httpx.get(
            f"https://eodhd.com/api/eod/{symbol}",
            params={"api_token": key, "fmt": "json", "order": "a",
                    "from": (start_date - timedelta(days=400)).isoformat(),
                    "to": end_date.isoformat()},
            timeout=30,
        )
    except Exception as exc:                                   # noqa: BLE001
        # Type only. An exception's text can carry the request URL, and the
        # URL carries the api_token.
        log.warning("%s: fetch failed — %s", symbol, type(exc).__name__)
        return None

    if r.status_code in (429, 402, 403):
        log.warning("%s: source refused the request — HTTP %s", symbol, r.status_code)
        raise SourceRefused(symbol, f"HTTP {r.status_code}")
    if r.status_code != 200:
        log.warning("%s: HTTP %s", symbol, r.status_code)
        return None

    payload = r.json() or []
    if not payload:
        log.warning("%s: no data returned from EODHD", symbol)
        return None

    df = pd.DataFrame(payload)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    for col in ("open", "high", "low", "close", "volume"):
        if col not in df.columns:
            log.warning("%s: response has no %s column", symbol, col)
            return None
    return df[["open", "high", "low", "close", "volume"]].copy()


def fetch_for(source: "IndexSource", start_date: date, end_date: date):
    """Dispatch to the provider named by the source."""
    if source.provider == "eodhd":
        return fetch_eodhd_index(source.symbol, start_date, end_date)
    return fetch_index_data(source.symbol, start_date, end_date)


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
) -> ProducerTally:
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

    # Expected covers what is fetched AND what is deliberately not. Taking it
    # from SOURCES alone makes the fetch list its own population, which is
    # how a withheld index disappeared from the accounting entirely.
    tally = ProducerTally("index_prices",
                          expected=len(SOURCES) + len(EXCLUDED_SOURCES))

    # Recorded first, so an exclusion is reported even by a run that goes on
    # to fail before reaching any provider.
    for excluded_code, reason in EXCLUDED_SOURCES.items():
        tally.excluded(excluded_code, reason)
        log.info(f"  {excluded_code}: excluded — {reason}")

    async with AsyncSessionLocal() as db:
        total_rows = 0
        for index_code, source in SOURCES.items():
            ticker = source.symbol
            # Provenance on every run: provider, symbol and -- where a switch
            # happened -- the date from which this provider's rows are
            # authoritative. A source change should be visible in the log of
            # the run that first used it, not only in a commit message.
            since = (f" since {source.effective_from}"
                     if source.effective_from else "")
            log.info(f"  {index_code} ({source.provider}:{ticker}{since}) …")
            # Off the loop. AsyncIOScheduler runs this coroutine ON the
            # event loop; a blocking fetch here stops the API answering
            # anything. index_prices did exactly that for five minutes on
            # 6 Oct 2026, the morning after the fund_prices fix shipped.
            try:
                df = await asyncio.to_thread(
                    fetch_for, source, start_date, target_date)
            except SourceRefused:
                # Counted, not swallowed. A refusal is why this run has no
                # data, and the run must be able to say so at the end.
                tally.refusal(index_code, f"provider refused {ticker}")
                continue

            if df is None or df.empty:
                log.info(f"  {index_code}: no data returned")
                tally.nothing_available(index_code)
                continue

            # Compute returns on the FULL fetched history (includes 400-day lookback
            # context needed for 1Y returns), then filter rows to the target window.
            all_rows = compute_rows(df)
            # FORWARD-ONLY. `first_writable` is the effective date of this
            # index's source; nothing before it is ever written, so switching
            # provider cannot rewrite rows another provider produced. The
            # fetch above deliberately reached 400 days further back, but
            # that context is for computing returns, not for persisting --
            # writing it would be the gap backfill, which is a separate
            # decision and not this change.
            writable_from = source.first_writable(start_date)
            rows = [
                r for r in all_rows
                if writable_from <= r["price_date"] <= target_date
            ]
            withheld = sum(1 for r in all_rows
                           if start_date <= r["price_date"] < writable_from)
            if withheld:
                log.info(f"  {index_code}: {withheld} row(s) before "
                         f"{writable_from} withheld (forward-only)")
            count = await upsert_rows(db, index_code, rows, dry_run)
            log.info(f"  {index_code}: {count} rows upserted")
            total_rows += count
            tally.obtained(index_code, count)

    # Partial results are kept: each ticker committed as it went, and a run
    # that obtained some of its population is reported as it is rather than
    # discarded. Only a total failure raises.
    log.info(f"Index prices complete — {tally.summary}")

    # Per-entity outcomes, named. See the matching note in fund_prices: the
    # counters were being emitted and the outcomes behind them discarded.
    for line in tally.report():
        log.warning("  OUTCOME: %s", line)
    if tally.degraded:
        log.warning("Index prices DEGRADED — %d of %d eligible indices did "
                    "not publish; the rest are written",
                    len(tally.failures) + len(tally.unaccounted), tally.expected)

    tally.verify()
    return tally


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
