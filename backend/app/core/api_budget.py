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

That share is advisory, not a cap. The account also carries a pool of extra
calls (extraLimit), and while any remain a job that would exceed the nominal
share proceeds and says so, rather than deferring work the account can plainly
afford. The share becomes a hard limit again only when the extras run out.

So the guard's job is no longer rationing. It is catching a runaway: the
original incident was one worker quietly issuing 28,800 requests a day, and
with a million spare calls that would burn for a week instead of failing in a
day. measure() comparing billed cost against ENDPOINT_COST is what catches
that, and it costs nothing.

Endpoint weights are not uniform — the news endpoint costs 5 calls per request
and fundamentals 10 — so "calls" here means EODHD's own accounting, not HTTP
requests. That distinction is what made the overrun invisible: the announcement
worker issued 28,800 requests a day, which EODHD billed as 144,000 calls,
exceeding the entire account limit before any other job ran.

ASX Screener is an end-of-day product. Nothing here needs intraday freshness,
so jobs should be scheduled daily and priced against this budget rather than
polled.
"""
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
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
    extra = int(d.get("extraLimit") or 0)
    return {
        "used":            used,
        "limit":           limit,
        "extra":           extra,
        "remaining":       max(limit - used, 0),
        "headroom":        max(limit - used, 0) + extra,
        "pct_of_account":  round(used / limit * 100, 1) if limit else None,
        "asx_budget":      asx_budget(limit),
        "date":            d.get("apiRequestsDate"),
    }


async def can_spend(cost: int, job: str, critical: bool = False) -> bool:
    """
    Whether a job should spend `cost` calls now.

    Nothing is deferred while the account can afford it. The only hard stop is
    genuine exhaustion — the daily allowance plus whatever extra calls remain.

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
    return _decide(cost, job, critical, usage)


def _decide(cost: int, job: str, critical: bool, usage: dict) -> bool:
    """
    Shared decision for the async and sync guards.

    The account carries extraLimit on top of the daily allowance, so the ASX
    share is a budgeting signal rather than a ceiling. Crossing it is logged and
    allowed; only running out of real capacity stops a job.
    """
    used, limit  = usage["used"], usage["limit"]
    extra        = usage.get("extra", 0)
    remaining    = usage["remaining"]
    headroom     = usage.get("headroom", remaining)
    pct          = used / limit if limit else 1.0

    # Genuine exhaustion — daily allowance and extras both gone.
    if cost > headroom:
        log.error(f"{job}: needs {cost:,} calls, only {headroom:,} available "
                  f"({remaining:,} of today's allowance + {extra:,} extra) — deferring")
        return False

    budget = asx_budget(limit)
    over_share = not critical and used + cost > budget

    if extra <= 0:
        # No spare pool: the old rationing applies, so this screener cannot
        # consume what the US Screener is relying on.
        if pct >= CRITICAL_PCT:
            log.error(f"{job}: EODHD at {pct:.0%} of {limit:,} with no extra calls "
                      f"— deferring ({remaining:,} left, needed {cost:,})")
            return False
        if pct >= HIGH_PCT and not critical:
            log.warning(f"{job}: EODHD at {pct:.0%} and no extra calls — deferring "
                        f"non-critical job")
            return False
        if over_share:
            log.warning(f"{job}: would take account usage to {used + cost:,}, over the "
                        f"{budget:,} ASX share, with no extra calls — deferring")
            return False
    elif over_share:
        log.info(f"{job}: past the {budget:,} nominal ASX share "
                 f"({used:,} used, job needs {cost:,}) — proceeding on the "
                 f"{extra:,} extra calls available")
    elif pct >= WARN_PCT:
        log.info(f"{job}: EODHD at {pct:.0%} of today's {limit:,}, "
                 f"{extra:,} extra calls in reserve")

    return True


# ── Synchronous helpers for the download scripts ─────────────────────────────
# The download scripts are plain psycopg2/requests programs, not async, and they
# are where the large per-symbol spends happen.

# Held back for core ingestion. Deliberately absolute rather than a share of
# the limit: it exists to cover one day of price and announcement work,
# which costs the same whatever the plan allows.
CRITICAL_RESERVE = 5_000

# ── Own-spend accounting ─────────────────────────────────────────────────────
# The EODHD key is shared with the US Stock Screener, so the account's usage
# counter is both screeners combined. Rationing this screener against that
# total is wrong in a way that fails silently: when the US Screener has spent
# 44,000 of the account, this screener computes 30,000 - 44,000 and defers
# every non-critical job, permanently, while reporting it as correct.
#
# The 30% share is a claim on the account, not a cap on what others may use, so
# it has to be measured against what THIS screener has spent. That number is
# recorded here as jobs complete.
SPEND_STATE = Path(__file__).resolve().parents[2] / "logs" / "eodhd_asx_spend.json"


def _usage_day(usage: Optional[dict] = None) -> str:
    """EODHD's own reset day, so local midnight cannot disagree with theirs."""
    if usage and usage.get("date"):
        return str(usage["date"])[:10]
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def asx_spent_today(usage: Optional[dict] = None) -> int:
    """Calls this screener has spent on EODHD's current day. 0 when unknown."""
    try:
        d = json.loads(SPEND_STATE.read_text())
    except Exception:
        return 0
    return int(d.get("spent", 0)) if d.get("date") == _usage_day(usage) else 0


def record_spend(calls: int, job: str, usage: Optional[dict] = None) -> None:
    """Add `calls` to today's total. Best effort — never breaks a running job."""
    if calls <= 0:
        return
    try:
        day = _usage_day(usage)
        total = asx_spent_today(usage) + calls
        SPEND_STATE.parent.mkdir(parents=True, exist_ok=True)
        SPEND_STATE.write_text(json.dumps(
            {"date": day, "spent": total, "last_job": job}, indent=2))
        log.info(f"{job}: ASX spend today now {total:,} of {ASX_BUDGET:,}")
    except Exception as exc:
        log.warning(f"{job}: could not record spend: {exc}")


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
    extra = int(d.get("extraLimit") or 0)
    return {"used": used, "limit": limit, "extra": extra,
            "remaining": max(limit - used, 0),
            "headroom": max(limit - used, 0) + extra,
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

    used, limit = usage["used"], usage["limit"]
    extra       = usage.get("extra", 0)
    remaining   = usage["remaining"]
    headroom    = usage.get("headroom", remaining)
    pct         = used / limit if limit else 1.0
    log.info(f"{job}: EODHD at {used:,}/{limit:,} ({pct:.0%}), {remaining:,} left "
             f"today plus {extra:,} extra, this job needs about {estimated_cost:,}")

    if extra > 0:
        # Spare capacity exists; the reserve only guards a genuinely scarce day.
        return _decide(estimated_cost, job, critical, usage)

    if critical:
        if estimated_cost > headroom:
            log.error(f"{job}: needs {estimated_cost:,}, only {headroom:,} left")
            return False
        return True

    # Account-level scarcity: at this point the shortage is real for everyone.
    if pct >= CRITICAL_PCT or estimated_cost > remaining:
        log.warning(f"{job}: account at {pct:.0%} with {remaining:,} left, "
                    f"job needs {estimated_cost:,} — deferring")
        return False
    if pct >= HIGH_PCT:
        log.warning(f"{job}: account at {pct:.0%} of {limit:,} — the shared key "
                    f"is under pressure, proceeding within this screener's share")

    # Share-level: measured against what THIS screener has spent, not the
    # account total, which includes the US Screener.
    budget = asx_budget(limit)
    spent = asx_spent_today(usage)
    spendable = budget - spent - CRITICAL_RESERVE
    if estimated_cost > spendable:
        log.warning(f"{job}: needs {estimated_cost:,} but only {max(spendable, 0):,} "
                    f"is spendable (ASX share {budget:,}, this screener has spent "
                    f"{spent:,}, reserve {CRITICAL_RESERVE:,}) — deferring")
        return False
    log.info(f"{job}: proceeding — ASX spent {spent:,}/{budget:,} today, "
             f"{spendable:,} spendable, job needs {estimated_cost:,}")
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
        self.job, self.expected = job, expected
        self.before = None
        self.before_day = None

    def __enter__(self):
        u = fetch_usage_sync()
        self.before = u["used"] if u else None
        self.before_day = _usage_day(u) if u else None
        if self.before is not None:
            log.info(f"{self.job}: EODHD usage before = {self.before:,} "
                     f"({self.before_day})")
        return self

    def __exit__(self, *exc):
        _finish_measure(self.job, self.expected, self.before, self.before_day,
                        fetch_usage_sync())
        return False


def _finish_measure(job: str, expected: Optional[int], before: Optional[int],
                    before_day: Optional[str], after: Optional[dict]) -> None:
    """Shared tail for measure and measure_async, so the two cannot drift."""
    if after is None or before is None:
        log.warning(f"{job}: could not measure billed cost")
        return

    # EODHD resets apiRequests at the start of its own day. A job running across
    # that boundary sees the counter go backwards, and the subtraction produces
    # a large negative number that looks exactly like a wrong ENDPOINT_COST
    # weight. Observed once as -18,163 on a job that had in fact billed
    # correctly.
    after_day = _usage_day(after)
    if before_day and after_day != before_day:
        log.warning(f"{job}: EODHD day rolled over mid-job ({before_day} to "
                    f"{after_day}) — billed cost is not measurable across the "
                    f"reset. Counter now at {after['used']:,}.")
        return

    billed = after["used"] - before
    log.info(f"{job}: usage after = {after['used']:,}  measured billed cost = {billed:,}")
    # Attribute it to this screener's share. Measured, not estimated — the gap
    # between the two is what the whole guard exists to close.
    record_spend(billed, job, after)
    if expected:
        delta = billed - expected
        if abs(delta) > max(50, expected * 0.1):
            log.warning(f"{job}: expected about {expected:,} calls but was billed "
                        f"{billed:,} ({delta:+,}). The per-endpoint cost in "
                        f"ENDPOINT_COST is probably wrong for this job.")


class measure_async:
    """
    Async twin of measure, for the in-process workers.

    measure() blocks on requests. Used inside the FastAPI event loop it would
    stall every other request for the length of the job, so the announcement
    worker needs this instead.

    `expected` may be set after entry, for a job that only knows its planned
    cost once it has queried the universe:

        async with measure_async("announcement_fetcher") as m:
            m.expected = await run_the_job()
    """
    def __init__(self, job: str, expected: Optional[int] = None):
        self.job, self.expected = job, expected
        self.before = None
        self.before_day = None

    async def __aenter__(self):
        u = await fetch_usage()
        self.before = u["used"] if u else None
        self.before_day = _usage_day(u) if u else None
        if self.before is not None:
            log.info(f"{self.job}: EODHD usage before = {self.before:,} "
                     f"({self.before_day})")
        return self

    async def __aexit__(self, *exc):
        _finish_measure(self.job, self.expected, self.before, self.before_day,
                        await fetch_usage())
        return False
