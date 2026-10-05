#!/usr/bin/env python3
"""
External sentinel — does the site answer, and is the answer meaningful?

On 2 Oct 2026 production was unavailable for roughly 40 minutes and nothing
reported it; the operator discovered it by failing to sign in. A cron asserted
that the *data* was fresh. Nothing asserted that the *site answered*.

This runs on GitHub's infrastructure, outside the host and outside the
application stack it observes, so it keeps working precisely when the thing it
watches does not.

What it is, stated honestly:

    external detection and a durable, version-controlled record
    NOT operational paging

GitHub's scheduler can run minutes late and a workflow-failure email is not a
pager. A real monitor with notifications is a separate, still-necessary thing.

── Design decisions worth keeping ──────────────────────────────────────────────

Three observations per target, performed INDEPENDENTLY. The probe never stops
early on success: a run that goes 200 / timeout / 200 is materially different
from 200 / 200 / 200, and short-circuiting would erase the failed sample. Every
observation's status, latency and failure reason is printed.

A target is DOWN only when all three observations fail, so one transient does
not raise an alarm. A target with some failures is DEGRADED: loudly logged,
exit code unchanged. Only DOWN fails the run.

Status alone is not enough. A site can answer 200 while serving nothing, which
is close to what a shell-only render looks like, so each target also asserts a
minimal semantic property of the body.

The request identifies itself. Cloudflare answers urllib's default user agent
with 403 — this project has already had a checker report UNVERIFIED forever for
exactly that reason. A 403 from an anonymous agent would look like an outage.

No secrets. Every URL here is public, and a sentinel that needs credentials
cannot run in a public workflow.

    python .github/scripts/uptime_probe.py            # probe production
    python .github/scripts/uptime_probe.py --self-test  # evaluation logic only
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Optional

#: Production by default. Overridable ONLY so the notification path can be
#: proven against a deliberately unreachable target -- "the notify step exists"
#: is not evidence that an alert arrives. An unset variable probes production,
#: so a forgotten override cannot silently point the sentinel at nothing.
BASE = os.environ.get("SENTINEL_BASE_URL") or "https://asxscreener.com.au"

#: Identify honestly. Borrowing a browser's agent would be a lie that also
#: makes the sentinel's traffic indistinguishable from a visitor's.
USER_AGENT = "asx-screener-uptime-sentinel (+https://github.com/PrashanthPadeti/asx-screener)"

OBSERVATIONS = 3
SPACING_SECONDS = 20
TIMEOUT_SECONDS = 15


def _homepage_is_substantive(body: str) -> Optional[str]:
    """The homepage must carry its own content, not just the shared shell.

    A 200 proves the server answered. In Oct 2026 this site shipped 68 KB of
    HTML containing about 1,000 characters of navbar and footer, so "answered"
    and "served the page" are genuinely different conditions here.
    """
    if "ASX Stock Screener" not in body:
        return "homepage markup missing its heading text"
    if len(body) < 20_000:
        return f"homepage body implausibly small ({len(body)} bytes)"
    return None


def _summary_is_meaningful(body: str) -> Optional[str]:
    """The API must report a populated universe, not an empty one."""
    try:
        data = json.loads(body)
    except ValueError as exc:
        return f"response is not JSON: {exc}"
    total = data.get("total_stocks")
    if not isinstance(total, int):
        return f"total_stocks missing or not an integer: {total!r}"
    if total <= 0:
        return f"total_stocks is {total}; the universe is empty"
    return None


TARGETS: list[dict[str, Any]] = [
    {
        "name": "homepage",
        "url": f"{BASE}/",
        "expect_status": 200,
        "assert_body": _homepage_is_substantive,
    },
    {
        "name": "market_summary",
        "url": f"{BASE}/api/v1/market/summary",
        "expect_status": 200,
        "assert_body": _summary_is_meaningful,
    },
]


# ── One observation ───────────────────────────────────────────────────────────

def observe(url: str,
            expect_status: int,
            assert_body: Callable[[str], Optional[str]],
            *,
            timeout: float = TIMEOUT_SECONDS,
            opener: Optional[Callable[[str, float], tuple[int, str]]] = None,
            ) -> dict[str, Any]:
    """One request, always returning a record rather than raising.

    `opener` exists so the evaluation logic can be exercised without a network.
    """
    started = time.monotonic()
    try:
        if opener is not None:
            status, body = opener(url, timeout)
        else:
            req = urllib.request.Request(url, headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/json",
                "Cache-Control": "no-cache",
            })
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                status = resp.status
                body = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return _record(started, exc.code, f"HTTP {exc.code}")
    except Exception as exc:                                   # noqa: BLE001
        # Timeouts, DNS, connection refused, TLS. All are "did not answer".
        return _record(started, None, f"{type(exc).__name__}: {exc}")

    if status != expect_status:
        return _record(started, status, f"expected {expect_status}, got {status}")

    problem = assert_body(body)
    if problem:
        return _record(started, status, problem)
    return _record(started, status, None)


def _record(started: float, status: Optional[int],
            failure: Optional[str]) -> dict[str, Any]:
    return {
        "ok": failure is None,
        "status": status,
        "latency_ms": round((time.monotonic() - started) * 1000),
        "failure": failure,
    }


# ── Verdict (pure) ────────────────────────────────────────────────────────────

def verdict(observations: list[dict[str, Any]]) -> str:
    """up | degraded | down.

    DOWN requires every observation to have failed — one transient must not
    page anyone. DEGRADED is reported rather than smoothed away, because a
    partial failure is the shape a developing outage has.
    """
    if not observations:
        return "down"
    failures = sum(1 for o in observations if not o["ok"])
    if failures == 0:
        return "up"
    if failures == len(observations):
        return "down"
    return "degraded"


def exit_code(verdicts: dict[str, str]) -> int:
    """Only a sustained failure fails the run."""
    return 1 if any(v == "down" for v in verdicts.values()) else 0


# ── Run ───────────────────────────────────────────────────────────────────────

def main() -> int:
    verdicts: dict[str, str] = {}
    for target in TARGETS:
        print(f"\n=== {target['name']} — {target['url']}")
        observations = []
        for i in range(OBSERVATIONS):
            if i:
                time.sleep(SPACING_SECONDS)
            # Deliberately no early exit: every observation is recorded, so a
            # later success cannot hide an earlier failure.
            o = observe(target["url"], target["expect_status"],
                        target["assert_body"])
            observations.append(o)
            mark = "ok  " if o["ok"] else "FAIL"
            print(f"  [{i + 1}/{OBSERVATIONS}] {mark} "
                  f"status={o['status']} latency={o['latency_ms']}ms"
                  + (f" — {o['failure']}" if o["failure"] else ""))
        v = verdict(observations)
        verdicts[target["name"]] = v
        print(f"  verdict: {v.upper()}")

    print("\n=== summary")
    for name, v in verdicts.items():
        print(f"  {name:16} {v}")

    code = exit_code(verdicts)
    if code:
        print("\nFAIL — a target failed every observation. The site is not "
              "answering; this is an external detection, not a diagnosis.")
    elif "degraded" in verdicts.values():
        print("\nPASS with DEGRADED samples — some observations failed. Not an "
              "alarm, but the failed samples above are the record.")
    else:
        print("\nPASS — every observation succeeded.")
    return code


# ── Self-test: the verdict logic, no network ──────────────────────────────────

def _self_test() -> int:
    ok = {"ok": True, "status": 200, "latency_ms": 10, "failure": None}
    bad = {"ok": False, "status": None, "latency_ms": 15000, "failure": "timeout"}
    cases = [
        ("all good is up",                [ok, ok, ok],   "up"),
        ("all failed is down",            [bad, bad, bad], "down"),
        ("one transient is not down",     [bad, ok, ok],  "degraded"),
        ("two failures still not down",   [bad, bad, ok], "degraded"),
        ("no observations is down",       [],             "down"),
    ]
    failures = []
    for name, obs, expected in cases:
        got = verdict(obs)
        print(f"  {'PASS' if got == expected else 'FAIL'}  {name} -> {got}")
        if got != expected:
            failures.append(name)

    # exit code: only `down` fails the run
    for name, verdicts, expected in [
        ("down fails",      {"a": "down", "b": "up"},       1),
        ("degraded passes", {"a": "degraded", "b": "up"},   0),
        ("all up passes",   {"a": "up", "b": "up"},         0),
    ]:
        got = exit_code(verdicts)
        print(f"  {'PASS' if got == expected else 'FAIL'}  {name} -> {got}")
        if got != expected:
            failures.append(name)

    # body assertions reject the shapes that motivated them
    checks = [
        ("empty universe rejected",
         _summary_is_meaningful('{"total_stocks": 0}') is not None),
        ("populated universe accepted",
         _summary_is_meaningful('{"total_stocks": 2121}') is None),
        ("non-JSON rejected",
         _summary_is_meaningful("<html>502</html>") is not None),
        ("shell-only homepage rejected",
         _homepage_is_substantive("<html><body>ASX Stock Screener</body></html>")
         is not None),
        ("full homepage accepted",
         _homepage_is_substantive("ASX Stock Screener" + "x" * 20_000) is None),
    ]
    for name, passed in checks:
        print(f"  {'PASS' if passed else 'FAIL'}  {name}")
        if not passed:
            failures.append(name)

    print(f"\n{'all self-tests passed' if not failures else f'{len(failures)} failed'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(_self_test() if "--self-test" in sys.argv else main())
