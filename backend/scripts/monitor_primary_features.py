#!/usr/bin/env python3
"""
Continuous monitor — the three primary features, on a timer
===========================================================
Layer 3 of four, and the one that answers the actual question: customers
should never be left on a broken site.

  layer 1  contract tests   catch it before merge
  layer 2  post-deploy smoke catch it before the deploy is called done
  layer 3  this             catch everything else

"Everything else" is the important part. Layers 1 and 2 only fire when
someone deploys. They cannot catch a feature that breaks because the data
went stale, a scheduled job corrupted the universe, a dependency failed,
or a certificate expired. Nothing was deployed in those cases and the site
is still broken.

The checks are NOT reimplemented here: this runs
scripts/smoke_primary_features.py, the same script deploy.sh runs. A
second copy of "is the screener working" would drift from the first, and
the two would disagree at the worst moment.

Alerting, and why it is on TRANSITIONS
-------------------------------------
An email every five minutes for three days is how a signal dies. The CI
failure emails in this project were ignored for days for exactly that
reason, and a real outage was inside them.

So this emails when the state CHANGES:

    healthy -> broken    one alert, naming what failed
    broken  -> healthy   one recovery notice, with the duration

While broken it stays quiet, and re-alerts only after
MONITOR_REMIND_HOURS (default 12) so a long outage cannot be forgotten
entirely. State lives in a file, so a restart of the timer does not
re-alert.

Usage:
    ALERT_EMAIL=you@example.com python3 monitor_primary_features.py
    ALERT_EMAIL=... MONITOR_BASE=https://asxscreener.com.au python3 ...
"""

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent

SMOKE = HERE / "smoke_primary_features.py"
STATE = Path(os.environ.get(
    "MONITOR_STATE", "/var/lib/asx-screener/primary_features.state"))
BASE = os.environ.get("MONITOR_BASE", "http://localhost:8000")
REMIND_HOURS = float(os.environ.get("MONITOR_REMIND_HOURS", "12"))


def _read_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:                                          # noqa: BLE001
        # No state, unreadable state, corrupt state: treat as healthy so the
        # FIRST transition to broken still alerts. Assuming "broken" instead
        # would fire a recovery notice on the first clean run after any
        # restart, which trains the reader to ignore them.
        return {"healthy": True, "since": None, "last_alert": None}


def _write_state(state: dict) -> None:
    try:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(state), encoding="utf-8")
    except Exception as exc:                                   # noqa: BLE001
        # Not fatal: a monitor that cannot persist still reports, it just
        # loses transition tracking and will re-alert. Say so rather than
        # failing silently.
        print(f"monitor: WARNING could not write {STATE}: {exc}")


def _redact(text: str) -> str:
    """Never let a credential reach the monitor log.

    The first version called the app's notification service, which
    constructs Settings. When that failed, pydantic's ValidationError
    included input_value -- and a fragment of a live API key was printed
    into this script's own log file. Pydantic puts values in its errors.

    So: report the exception TYPE and a redacted message, never the raw
    text of anything that touched configuration.
    """
    out = text
    for key in ("RESEND_API_KEY", "ANTHROPIC_API_KEY", "JWT_SECRET",
                "DATABASE_URL", "DATABASE_URL_SYNC", "EODHD_API_KEY"):
        val = os.environ.get(key)
        if val and len(val) > 6:
            out = out.replace(val, f"<{key}>")
    return out[:400]


def _send(subject: str, body: str) -> bool:
    """Alert through Resend's HTTP API directly — no app import.

    DELIBERATELY does not use app.services.notification_service. That
    imports Settings, which requires DATABASE_URL, so the alerting path
    would share fate with the application: if the app's configuration is
    broken, the monitor detects the outage and cannot tell anyone. A
    monitor must not depend on the thing it monitors.

    This needs only RESEND_API_KEY and EMAIL_FROM from the environment,
    which the systemd unit supplies via EnvironmentFile.
    """
    to = os.environ.get("ALERT_EMAIL", "").strip()
    if not to:
        print("monitor: ALERT_EMAIL is not set — nothing was sent. This "
              "monitor can see a broken site and tell nobody.")
        return False

    api_key = os.environ.get("RESEND_API_KEY", "").strip()
    if not api_key:
        print("monitor: RESEND_API_KEY is not set — nothing was sent. The "
              "outage was detected and not reported.")
        return False

    sender = os.environ.get("EMAIL_FROM", "noreply@asxscreener.com.au")
    html = ("<pre style='font:13px ui-monospace,monospace;white-space:pre-wrap'>"
            + body.replace("&", "&amp;").replace("<", "&lt;") + "</pre>")
    payload = json.dumps({"from": sender, "to": [to],
                          "subject": subject, "html": html}).encode()

    req = urllib.request.Request("https://api.resend.com/emails",
                                 data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {api_key}")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            ok = 200 <= r.status < 300
        print(f"monitor: alert {'sent' if ok else 'rejected'} to {to}")
        return ok
    except Exception as exc:                                   # noqa: BLE001
        # Type and a redacted message only. The exception body can echo the
        # request, and the request carries the key.
        print(f"monitor: could not send alert: {type(exc).__name__}: "
              f"{_redact(str(exc))}")
        return False


def main() -> int:
    proc = subprocess.run(
        [sys.executable, str(SMOKE), "--base", BASE],
        capture_output=True, text=True, timeout=180)
    output = (proc.stdout or "") + (proc.stderr or "")
    healthy = proc.returncode == 0
    print(output, end="")

    state = _read_state()
    was_healthy = bool(state.get("healthy", True))
    now = datetime.now(timezone.utc)
    stamp = now.isoformat(timespec="seconds")

    if healthy and was_healthy:
        print("monitor: healthy (no change, no alert)")
        _write_state({"healthy": True, "since": state.get("since"),
                      "last_alert": state.get("last_alert")})
        return 0

    if healthy and not was_healthy:
        broke_at = state.get("since")
        dur = ""
        if broke_at:
            try:
                delta = now - datetime.fromisoformat(broke_at)
                dur = f" after {int(delta.total_seconds() // 60)} minutes"
            except Exception:                                  # noqa: BLE001
                pass
        _send(f"[ASX Screener] Primary features RECOVERED{dur}",
              f"Recovered at {stamp}.\n\n{output}")
        _write_state({"healthy": True, "since": None, "last_alert": None})
        return 0

    # Broken.
    if was_healthy:
        _send("[ASX Screener] PRIMARY FEATURE DOWN",
              f"Detected at {stamp} against {BASE}.\n\n"
              f"Stock screening, the market overview or the company pages "
              f"are not working for customers.\n\n{output}")
        _write_state({"healthy": False, "since": stamp, "last_alert": stamp})
        return 1

    # Still broken: stay quiet unless the reminder window has passed.
    last = state.get("last_alert")
    due = True
    if last:
        try:
            due = (now - datetime.fromisoformat(last)) >= timedelta(
                hours=REMIND_HOURS)
        except Exception:                                      # noqa: BLE001
            due = True
    if due:
        _send("[ASX Screener] PRIMARY FEATURE STILL DOWN",
              f"Still failing at {stamp}, first seen "
              f"{state.get('since')}.\n\n{output}")
        state["last_alert"] = stamp
    else:
        print("monitor: still broken; alert suppressed until the reminder "
              f"window ({REMIND_HOURS}h) elapses")
    state["healthy"] = False
    _write_state(state)
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except subprocess.TimeoutExpired:
        print("monitor: the smoke run timed out — treating as a failure")
        sys.exit(1)
