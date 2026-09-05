"""
EODHD API budget
================
The EODHD key is shared with the US Stock Screener, which has priority. This
module holds the split and the guard that stops ASX jobs starving it.

    US Stock Screener   70%
    ASX Screener        30%

The split is proportional, not fixed: the denominator is whatever EODHD reports
as dailyRateLimit. On a 100,000/day plan this screener gets 30,000; double the
plan and it gets 60,000, with nothing to edit.

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
import os
from typing import Optional

import httpx

log = logging.getLogger(__name__)


def _api_key() -> str:
    """
    The EODHD key, without importing app settings.

    app.core.config instantiates Settings() at import and JWT_SECRET has no
    default, so importing it makes every consumer depend on the whole
    application config being present. The download scripts run from cron with
    a different working directory to the API, where that dependency turns a
    missing unrelated variable into an import-time crash. This module needs
    one key, so it reads one key, and falls back to settings only if the
    environment does not carry it.
    """
    key = os.getenv("EODHD_API_KEY")
    if key:
        return key
    try:
        from app.core.config import settings
        return getattr(settings, "EODHD_API_KEY", "") or ""
    except Exception:
        return ""


# Fallback only. The real limit is whatever EODHD reports as dailyRateLimit,
# which is read on every usage check — so raising the plan raises this
# screener's share automatically, with no code change and no redeploy.
EODHD_DAILY_LIMIT = 100_000
ASX_SHARE         = 0.30
ASX_BUDGET        = int(EODHD_DAILY_LIMIT * ASX_SHARE)   # 30,000 at the fallback


def asx_budget(limit: Optional[int] = None) -> int:
    """The ASX share of `limit`, defaulting to the fallback when unknown."""
    return int((limit or EODHD_DAILY_LIMIT) * ASX_SHARE)

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
    key = _api_key()
    if not key:
        return None
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.get("https://eodhd.com/api/user",
                                 params={"api_token": key, "fmt": "json"})
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
        "asx_budget":      asx_budget(limit),
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

    budget = asx_budget(limit)
    if not critical and used + cost > budget:
        log.warning(f"{job}: would take ASX usage to {used + cost:,}, over the "
                    f"{budget:,} share reserved from the US Screener — deferring")
        return False

    if cost > remaining:
        log.error(f"{job}: needs {cost:,} calls, only {remaining:,} left — deferring")
        return False
    return True


# ── Synchronous helpers for the download scripts ─────────────────────────────
# The download scripts are plain psycopg2/requests programs, not async, and they
# are where the large per-symbol spends happen.

# Held back for core ingestion. Deliberately absolute rather than a share of
# the limit: it exists to cover one day of price and announcement work,
# which costs the same whatever the plan allows.
CRITICAL_RESERVE = 5_000


def fetch_usage_sync(timeout: float = 10.0) -> Optional[dict]:
    """Blocking version of fetch_usage for the download scripts."""
    key = _api_key()
    if not key:
        return None
    try:
        import requests
        r = requests.get("https://eodhd.com/api/user",
                         params={"api_token": key, "fmt": "json"}, timeout=timeout)
        if r.status_code != 200:
            return None
        d = r.json()
    except Exception as exc:
        log.warning(f"EODHD usage check failed: {exc}")
        return None
    used  = int(d.get("apiRequests") or 0)
    limit = int(d.get("dailyRateLimit") or EODHD_DAILY_LIMIT)
    return {"used": used, "limit": limit, "remaining": max(limit - used, 0),
            "date": d.get("apiRequestsDate")}


def may_start_sync(estimated_cost: int, job: str, critical: bool = False) -> bool:
    """
    Whether a job may start, holding CRITICAL_RESERVE back for core ingestion.

    "Can this job technically start?" is the weaker question. What matters is
    whether it can finish without eating the reserve that price and fundamentals
    ingestion depend on.
    """
    usage = fetch_usage_sync()
    if usage is None:
        log.warning(f"{job}: EODHD usage unknown — "
                    f"{'proceeding (critical)' if critical else 'deferring'}")
        return critical

    used, limit, remaining = usage["used"], usage["limit"], usage["remaining"]
    pct = used / limit if limit else 1.0
    log.info(f"{job}: EODHD at {used:,}/{limit:,} ({pct:.0%}), "
             f"{remaining:,} left, this job needs about {estimated_cost:,}")

    if critical:
        if estimated_cost > remaining:
            log.error(f"{job}: needs {estimated_cost:,}, only {remaining:,} left")
            return False
        return True

    if pct >= HIGH_PCT:
        log.warning(f"{job}: account at {pct:.0%} — deferring non-critical job")
        return False
    budget = asx_budget(limit)
    budget_left = budget - used
    if estimated_cost > (budget_left - CRITICAL_RESERVE):
        log.warning(f"{job}: needs {estimated_cost:,} but only "
                    f"{max(budget_left - CRITICAL_RESERVE, 0):,} is spendable "
                    f"(ASX budget {budget:,}, used {used:,}, "
                    f"reserve {CRITICAL_RESERVE:,}) — deferring")
        return False
    return True


class measure:
    """
    Records EODHD usage either side of a job so billed cost is measured, not
    assumed. The original overrun hid precisely in the gap between HTTP requests
    issued and calls billed.

        with measure("fundamentals_refresh", expected=20_870):
            ...
    """
    def __init__(self, job: str, expected: Optional[int] = None):
        self.job, self.expected, self.before = job, expected, None

    def __enter__(self):
        u = fetch_usage_sync()
        self.before = u["used"] if u else None
        if self.before is not None:
            log.info(f"{self.job}: EODHD usage before = {self.before:,}")
        return self

    def __exit__(self, *exc):
        u = fetch_usage_sync()
        if u is None or self.before is None:
            log.warning(f"{self.job}: could not measure billed cost")
            return False
        billed = u["used"] - self.before
        log.info(f"{self.job}: usage after = {u['used']:,}  measured billed cost = {billed:,}")
        if self.expected:
            delta = billed - self.expected
            if abs(delta) > max(50, self.expected * 0.1):
                log.warning(f"{self.job}: expected about {self.expected:,} calls but was "
                            f"billed {billed:,} ({delta:+,}). The per-endpoint cost in "
                            f"ENDPOINT_COST is probably wrong for this job.")
        return False
