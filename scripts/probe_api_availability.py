#!/usr/bin/env python3
"""
Does the API keep answering while a scheduled job runs?

On 2 Oct 2026 production was unavailable for ~40 minutes while an in-process
job made hundreds of serial outbound calls. The backend was listening with 35
connections queued and answering none. Nothing measured that; it was inferred
afterwards from log lines that happened to be there.

This measures it. The same script, unchanged, is used before and after
`announcement_fetcher` is moved out of the API process, so the two runs are
comparable observations rather than two different ones:

    A  historical overlap, old architecture   outage observed, not measured
    B  pre-move, announcements in-process     this probe
    C  post-move, announcements external      this probe, unchanged
    D  weekday post-move, pipeline overlapping this probe, unchanged

── What it is not ──────────────────────────────────────────────────────────────
It does not measure how long the job took. `ops.job_executions` is the
authority for start, end and duration; inferring a worker's runtime from probe
symptoms would be reading the shadow instead of the object.

It is an instrument: GETs only, no writes, no retries, and a failure to probe
can never stop the measurement.

── Design points that matter ───────────────────────────────────────────────────
Monotonic elapsed time is recorded alongside the wall clock, so an NTP
correction mid-window cannot distort a latency or a gap.

Every request is bounded well below the sampling interval. A probe that can
block longer than its own period stops being a time series.

No retry inside a sample. A timeout IS the observation — retrying until
success would erase exactly the evidence being collected.

Append-only JSONL, flushed per sample, so an interrupted run keeps everything
up to the interruption.

    python3 scripts/probe_api_availability.py --minutes 75 --out /tmp/baseline.jsonl
    python3 scripts/probe_api_availability.py --self-test
"""

from __future__ import annotations

import argparse
import hashlib
import json
import socket
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Callable, Optional

USER_AGENT = "asx-screener-availability-probe (+ops instrument, read-only)"

#: Shorter than the sampling interval by a wide margin. A request allowed to
#: outlive its own period turns the series into something that cannot be read.
TIMEOUT_SECONDS = 8.0
DEFAULT_INTERVAL = 15.0


def _health_body(body: str) -> tuple[bool, str]:
    try:
        data = json.loads(body)
    except ValueError:
        return False, "not JSON"
    if data.get("status") != "ok":
        return False, f"status={data.get('status')!r}"
    return True, f"version={data.get('version')}"


def _frontend_body(body: str) -> tuple[bool, str]:
    # Minimal: the frontend server-renders through the API, so a shell-only
    # answer is itself a symptom worth distinguishing from a clean failure.
    if "<html" not in body.lower():
        return False, "no html"
    return True, f"{len(body)} bytes"


TARGETS: list[dict[str, Any]] = [
    # The origin API, direct. This is the measurement: no Cloudflare, no
    # network, nothing between the probe and the process that queued 35
    # connections during the incident.
    {"name": "api", "url": "http://localhost:8000/health", "body": _health_body},
    # The frontend, which server-renders through that API. Included because its
    # dependency on the API is part of what made the outage user-visible.
    {"name": "frontend", "url": "http://localhost:3000/", "body": _frontend_body},
]

#: Secondary. Cloudflare and the network sit in the path, so it is the
#: end-to-end experience rather than a diagnostic of the origin.
PUBLIC_TARGET = {"name": "public", "url": "https://asxscreener.com.au/",
                 "body": lambda b: (len(b) > 10_000, f"{len(b)} bytes")}


def sample(target: dict[str, Any], started_mono: float) -> dict[str, Any]:
    """One observation. Never raises; a failure is a recorded fact."""
    t0 = time.monotonic()
    row: dict[str, Any] = {
        "at": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "elapsed_s": round(t0 - started_mono, 3),
        "target": target["name"],
    }
    try:
        req = urllib.request.Request(target["url"], headers={
            "User-Agent": USER_AGENT, "Cache-Control": "no-cache"})
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            status, body = resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        row.update(ok=False, status=exc.code, latency_ms=_ms(t0),
                   error_class="HTTPError", note=f"HTTP {exc.code}")
        return row
    except socket.timeout:
        row.update(ok=False, status=None, latency_ms=_ms(t0),
                   error_class="Timeout", note=f"no answer in {TIMEOUT_SECONDS}s")
        return row
    except Exception as exc:                                    # noqa: BLE001
        row.update(ok=False, status=None, latency_ms=_ms(t0),
                   error_class=type(exc).__name__, note=str(exc)[:120])
        return row

    body_ok, note = target["body"](body)
    row.update(ok=bool(body_ok), status=status, latency_ms=_ms(t0),
               error_class=None if body_ok else "BodyAssertion", note=note)
    return row


def _ms(t0: float) -> int:
    return round((time.monotonic() - t0) * 1000)


def run(minutes: float, interval: float, out_path: str,
        include_public: bool) -> int:
    targets = list(TARGETS) + ([PUBLIC_TARGET] if include_public else [])
    started_mono = time.monotonic()
    deadline = started_mono + minutes * 60
    n = 0

    # The pre-move and post-move runs are comparable only if both used the
    # same instrument. Recording this file's own digest makes that checkable
    # afterwards rather than assumed: two runs whose probe_sha256 differs were
    # not measured the same way, whatever anyone intended at the time.
    meta = {
        "record": "probe_meta",
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "probe_sha256": hashlib.sha256(
            open(__file__, "rb").read()).hexdigest()[:16],
        "interval_s": interval,
        "timeout_s": TIMEOUT_SECONDS,
        "targets": [t["name"] for t in targets],
        "minutes": minutes,
    }

    print(f"probing {meta['targets']} every {interval}s "
          f"for {minutes} min -> {out_path}")
    print(f"probe_sha256={meta['probe_sha256']}  "
          f"(must match between the before and after runs)")
    print("ctrl-c to stop early; the file keeps everything written so far\n")

    with open(out_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(meta) + "\n")
        fh.flush()
        while time.monotonic() < deadline:
            tick = time.monotonic()

            # Targets are sampled CONCURRENTLY, so a cycle costs the slowest
            # target rather than the sum of all of them.
            #
            # Sequentially, three targets timing out at 8s each would take 24s
            # against a 15s interval — the series would stretch precisely when
            # the API is hanging, which is the condition being measured. An
            # instrument must not lose resolution exactly where it is needed.
            with ThreadPoolExecutor(max_workers=len(targets)) as pool:
                futures = {pool.submit(sample, t, started_mono): t
                           for t in targets}
                rows = []
                for fut, target in futures.items():
                    try:
                        rows.append(fut.result())
                    except Exception as exc:                    # noqa: BLE001
                        # The instrument failing must never end the measurement.
                        rows.append({
                            "at": datetime.now(timezone.utc).isoformat(),
                            "elapsed_s": round(time.monotonic() - started_mono, 3),
                            "target": target["name"], "ok": False,
                            "error_class": "ProbeFault", "note": str(exc)[:120]})

            for row in sorted(rows, key=lambda r: r["target"]):
                fh.write(json.dumps(row) + "\n")
                fh.flush()
                n += 1
                flag = "ok  " if row.get("ok") else "FAIL"
                print(f"  {row['elapsed_s']:>7.1f}s  {row['target']:<9} {flag} "
                      f"status={row.get('status')} {row.get('latency_ms')}ms "
                      f"{row.get('note', '')}")
            # Align to the interval rather than sleeping a fixed amount, so
            # slow samples do not make the series drift.
            time.sleep(max(0.0, interval - (time.monotonic() - tick)))

    print(f"\n{n} observations written to {out_path}")
    return 0


# ── Self-test: no network ─────────────────────────────────────────────────────

def _self_test() -> int:
    failures = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  - {detail}" if not cond and detail else ""))
        if not cond:
            failures.append(name)

    ok, note = _health_body('{"status":"ok","version":"11.2.0"}')
    check("healthy body accepted", ok and "11.2.0" in note)
    check("degraded body rejected", not _health_body('{"status":"degraded"}')[0])
    check("non-JSON rejected", not _health_body("<html>502</html>")[0])
    check("frontend html accepted", _frontend_body("<html><body>x</body></html>")[0])
    check("frontend non-html rejected", not _frontend_body("502 Bad Gateway")[0])

    check("timeout is shorter than the interval",
          TIMEOUT_SECONDS < DEFAULT_INTERVAL,
          f"{TIMEOUT_SECONDS} vs {DEFAULT_INTERVAL}")

    bad = {"name": "unreachable", "url": "http://127.0.0.1:1/",
           "body": lambda b: (True, "")}
    row = sample(bad, time.monotonic())
    check("an unreachable target is a recorded observation, not an exception",
          row["ok"] is False and row["error_class"] is not None)
    check("a failed sample still carries elapsed and latency",
          "elapsed_s" in row and "latency_ms" in row)

    # Scan only the operational half. The self-test below necessarily contains
    # the very strings it searches for, and a scanner that includes itself
    # reports its own assertion as a violation — which is exactly what happened
    # the first time this ran.
    src = open(__file__, encoding="utf-8").read()
    operational = src[:src.index("def _self_test(")]
    body = operational[operational.index("def sample("):operational.index("def _ms(")]
    check("no retry inside a sample",
          "for attempt" not in body and "retry" not in body.lower())
    check("GETs only — no method override, no request body",
          "method=" not in operational and "data=" not in operational)
    check("a fully-failing cycle still fits inside one interval",
          TIMEOUT_SECONDS < DEFAULT_INTERVAL,
          "targets are sampled concurrently, so a cycle costs the slowest "
          "target, not the sum")
    check("targets are sampled concurrently",
          "ThreadPoolExecutor" in operational,
          "sequential sampling would stretch the series during an outage")

    print(f"\n{'all self-tests passed' if not failures else f'{len(failures)} failed'}")
    return 1 if failures else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--minutes", type=float, default=75)
    ap.add_argument("--interval", type=float, default=DEFAULT_INTERVAL)
    ap.add_argument("--out", default="/tmp/api_availability.jsonl")
    ap.add_argument("--public", action="store_true",
                    help="also probe the public URL (secondary: network and "
                         "Cloudflare sit in the path)")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    sys.exit(_self_test() if a.self_test
             else run(a.minutes, a.interval, a.out, a.public))
