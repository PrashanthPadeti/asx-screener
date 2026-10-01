#!/usr/bin/env python
"""
Detect Cloudflare range drift. Never repair it.
================================================
The origin trusts Cloudflare in two places, both generated from a single fetch
on 1 Oct 2026:

    nginx   set_real_ip_from   — whose CF-Connecting-IP is believed
    ufw     allow :80/:443     — who may reach the web ports at all

Cloudflare changes those prefixes. A range added without us knowing means some
visitors from some edge locations intermittently cannot reach the site. A
range removed that we still trust means someone else's address space can
assert visitor identity.

This reads, compares and reports. It runs no `ufw` command that changes
anything and rewrites no nginx config: a bad upstream response, a parsing
defect or an unexpected format must not be able to rewrite the origin
firewall. Automated reconciliation is a separate decision, after this has
accumulated evidence.

Needs root, because `ufw status` does. It writes its structured verdict to
STATE_FILE so the admin surface can report it without needing privilege --
and the surface reports the ARTIFACT'S AGE too, so a checker that stopped
running shows up as `unverified` rather than as the last good answer.

Usage:
    sudo python scripts/assert_cloudflare_ranges.py          # gate
    sudo python scripts/assert_cloudflare_ranges.py --json
    sudo python scripts/assert_cloudflare_ranges.py --report # never fails

Exit codes:  0 current · 1 drift · 2 unverified
"""

import argparse
import json
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from compute.engine.cloudflare_ranges import (                     # noqa: E402
    SOURCE_V4, SOURCE_V6, ConsumerResult, evaluate, parse_nginx,
    parse_published, parse_ufw, render, ufw_allows_anywhere,
)

NGINX_CONF = Path("/etc/nginx/conf.d/cloudflare-realip.conf")
STATE_FILE = Path("/var/lib/asx-screener/cloudflare_ranges.json")
TIMEOUT = 20


def _fetch(url: str) -> str:
    with urllib.request.urlopen(url, timeout=TIMEOUT) as r:
        if r.status != 200:
            raise RuntimeError(f"{url} returned HTTP {r.status}")
        return r.read().decode("utf-8", "replace")


def collect() -> dict:
    """Gather all three views, then hand them to the shared evaluator."""
    published, fetch_error = None, ""
    try:
        published = parse_published(_fetch(SOURCE_V4), _fetch(SOURCE_V6))
    except (urllib.error.URLError, OSError, RuntimeError) as exc:
        # Explicitly NOT "no drift". An unreachable source proves nothing.
        fetch_error = f"could not fetch the published ranges: {exc}"

    consumers = []

    if NGINX_CONF.exists():
        v4, v6, bad = parse_nginx(NGINX_CONF.read_text(encoding="utf-8"))
        consumers.append(ConsumerResult("nginx", v4, v6, bad))
    else:
        consumers.append(ConsumerResult(
            "nginx", malformed=[f"{NGINX_CONF} does not exist"]))

    try:
        status = subprocess.run(["ufw", "status"], capture_output=True,
                                text=True, timeout=30, check=True).stdout
        for port in (80, 443):
            v4, v6, bad = parse_ufw(status, port)
            consumers.append(ConsumerResult(
                f"ufw :{port}", v4, v6, bad,
                anywhere=ufw_allows_anywhere(status, port)))
    except (subprocess.SubprocessError, FileNotFoundError, OSError) as exc:
        for port in (80, 443):
            consumers.append(ConsumerResult(
                f"ufw :{port}", malformed=[f"could not read ufw status: {exc}"]))

    result = evaluate(published, consumers, fetch_error)
    result["checked_at"] = datetime.now(timezone.utc).isoformat()
    return result


def persist(result: dict) -> None:
    """Atomic write, so a reader never sees a half-written verdict."""
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
                "w", dir=STATE_FILE.parent, delete=False,
                encoding="utf-8") as tmp:
            json.dump(result, tmp, indent=2)
            temp = Path(tmp.name)
        temp.replace(STATE_FILE)
        STATE_FILE.chmod(0o644)
    except OSError as exc:
        print(f"  (could not write {STATE_FILE}: {exc})", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--report", action="store_true",
                        help="print the verdict and exit 0 regardless")
    args = parser.parse_args()

    result = collect()
    persist(result)

    print(json.dumps(result, indent=2) if args.json else render(result))

    if args.report:
        return 0
    return {"current": 0, "drift": 1, "unverified": 2}[result["state"]]


if __name__ == "__main__":
    sys.exit(main())
