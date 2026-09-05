"""
EODHD API budget
================
The EODHD key is shared with the US Stock Screener, which has priority. This
module holds the split and the guard that stops ASX jobs starving it.

    US Stock Screener   70%   70,000 calls/day
    ASX Screener        30%   30,000 calls/day

Endpoint weights are not uniform — the news endpoint costs 5 calls per request
and fundamentals 10 — so "calls" here means EODHD's own accounting, not HTTP
requests. That distinction is what made the overrun invisible: the announcement
worker issued 28,800 requests a day, which EODHD billed as 144,000 calls,
exceeding the entire account limit before any other job ran.

ASX Screener is an end-of-day product. Nothing here needs intraday freshness,
so jobs should be scheduled daily and priced against this budget rather than
polled.
"""
import logging
from typing import Optional

import httpx

from app.core.config import settings

log = logging.getLogger(__name__)

EODHD_DAILY_LIMIT = 100_000
ASX_SHARE         = 0.30
ASX_BUDGET        = int(EODHD_DAILY_LIMIT * ASX_SHARE)   # 30,000

# Warn early, defer non-critical work before core ingestion is at risk.
WARN_PCT   = 0.70
HIGH_PCT   = 0.85
CRITICAL_PCT = 0.95

# EODHD's published per-request cost, so a job can price itself before running.
ENDPOINT_COST = {
    "news":         5,
    "fundamentals": 10,
    "eod":          1,
    "eod-bulk":     1,
    "div":          1,
    "splits":       1,
    "exchange-symbol-list": 1,
    "user":         0,   # the usage endpoint itself is free
}


def cost_of(endpoint: str, requests: int = 1) -> int:
    """Calls EODHD will bill for `requests` hits of `endpoint`."""
    return ENDPOINT_COST.get(endpoint, 1) * requests


async def fetch_usage(timeout: float = 10.0) -> Optional[dict]:
    """
    Current usage from EODHD. Returns None when unavailable — callers must treat
    that as "unknown", never as "plenty left".
    """
    if not settings.EODHD_API_KEY:
        return None
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.get("https://eodhd.com/api/user",
                                 params={"api_token": settings.EODHD_API_KEY, "fmt": "json"})
            if r.status_code != 200:
                log.warning(f"EODHD usage check returned HTTP {r.status_code}")
                return None
            d = r.json()
    except Exception as exc:
        log.warning(f"EODHD usage check failed: {exc}")
        return None

    used  = int(d.get("apiRequests") or 0)
    limit = int(d.get("dailyRateLimit") or EODHD_DAILY_LIMIT)
    return {
        "used":            used,
        "limit":           limit,
        "remaining":       max(limit - used, 0),
        "pct_of_account":  round(used / limit * 100, 1) if limit else None,
        "asx_budget":      ASX_BUDGET,
        "date":            d.get("apiRequestsDate"),
    }


async def can_spend(cost: int, job: str, critical: bool = False) -> bool:
    """
    Whether a job should spend `cost` calls now.

    Critical jobs (price and fundamentals ingestion) proceed unless the account
    is genuinely exhausted. Everything else stops at the ASX share so it cannot
    consume budget the US Screener is relying on.

    Unknown usage allows critical work and blocks the rest: failing closed on a
    non-essential job is cheap, failing closed on price ingestion is not.
    """
    usage = await fetch_usage()
    if usage is None:
        if critical:
            log.warning(f"{job}: EODHD usage unknown — proceeding because job is critical")
            return True
        log.warning(f"{job}: EODHD usage unknown — deferring non-critical job")
        return False

    used, limit, remaining = usage["used"], usage["limit"], usage["remaining"]
    pct = used / limit if limit else 1.0

    if pct >= CRITICAL_PCT:
        log.error(f"{job}: EODHD at {pct:.0%} of {limit:,} — deferring "
                  f"({remaining:,} calls left, needed {cost:,})")
        return False
    if pct >= HIGH_PCT and not critical:
        log.warning(f"{job}: EODHD at {pct:.0%} — deferring non-critical job")
        return False
    if pct >= WARN_PCT:
        log.warning(f"{job}: EODHD at {pct:.0%} of daily limit, {remaining:,} calls left")

    if not critical and used + cost > ASX_BUDGET:
        log.warning(f"{job}: would take ASX usage to {used + cost:,}, over the "
                    f"{ASX_BUDGET:,} share reserved from the US Screener — deferring")
        return False

    if cost > remaining:
        log.error(f"{job}: needs {cost:,} calls, only {remaining:,} left — deferring")
        return False
    return True
