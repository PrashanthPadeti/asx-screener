"""
EODHD budget audit
==================
Closes the quota audit with measured numbers instead of estimates.

The announcement overrun was invisible because nobody had compared requests
issued against calls billed — EODHD charges 5 per /news request and 10 per
/fundamentals request, so 28,800 requests became 144,000 calls against a
100,000 limit. ENDPOINT_COST now encodes those weights, but an encoded weight
is still an assumption until it is checked against the account.

Two modes:

  measure           Run each EODHD job once, recording account usage either
                    side of it, and print the variance table. Spends real
                    budget (~10,800 calls) — that is the point.

  verify-coverage   After four Sunday rotations, confirm every active symbol
                    has had a fundamentals refresh. The union test proves the
                    shards partition a fixed universe; this proves the
                    schedule survives listings being added and removed.

Usage:
    python scripts/eodhd/v2/jobs/budget_audit.py measure
    python scripts/eodhd/v2/jobs/budget_audit.py measure --only fundamentals splits
    python scripts/eodhd/v2/jobs/budget_audit.py verify-coverage
    python scripts/eodhd/v2/jobs/budget_audit.py verify-coverage --window-days 28
"""
import argparse
import logging
import os
import re
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

JOBS_DIR = Path(__file__).resolve().parent
V2_DIR   = JOBS_DIR.parent
BACKEND  = JOBS_DIR.parents[3]

sys.path.insert(0, str(BACKEND))
from app.core.api_budget import (  # noqa: E402
    fetch_usage_sync, cost_of, asx_budget, CRITICAL_RESERVE,
)
from scripts.eodhd.utils.sharding import (  # noqa: E402
    SHARD_COUNT, current_shard, filter_to_shard,
)

# No hardcoded fallback: this repository is public, and the surrounding scripts
# already carry the credential inline. Read it from the environment or fail.
DB_URL = os.getenv("DATABASE_URL_SYNC")
RAW_BASE = Path(os.getenv("RAW_DATA_DIR", "/opt/asx-screener/data/raw"))
FUND_DIR = RAW_BASE / "eodhd" / "exchange=AU" / "fundamentals" / "full_snapshot"

# The measure() warning threshold in api_budget, restated so the table's
# PASS/WARN column and the job logs agree.
TOLERANCE = 0.10
FLOOR     = 50          # absolute slack for jobs costing only a handful of calls

REPORT = BACKEND / "logs" / "eodhd_budget_audit.md"


def active_codes() -> list[str]:
    if not DB_URL:
        raise SystemExit("DATABASE_URL_SYNC is not set — source backend/.env first.")
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute("SELECT asx_code FROM market.companies "
                "WHERE status='active' ORDER BY asx_code")
    codes = [r[0] for r in cur.fetchall()]
    cur.close(); conn.close()
    return codes


def build_plan(codes: list[str]) -> list[dict]:
    """Each job, its expected billed cost, and how to run it."""
    shard = current_shard()
    n_shard = len(filter_to_shard(codes, shard))
    n_all   = len(codes)
    py = sys.executable
    return [
        {"job": f"Fundamentals shard {shard}/{SHARD_COUNT}",
         "expected": cost_of("fundamentals", n_shard),
         "cmd": [py, str(V2_DIR / "download_fundamentals.py"), "--shard-this-week"]},
        {"job": "Dividends",
         "expected": cost_of("div", n_all),
         "cmd": [py, str(V2_DIR / "download_dividends.py")]},
        {"job": "Splits",
         "expected": cost_of("splits", n_all),
         "cmd": [py, str(V2_DIR / "download_splits.py")]},
        {"job": "Announcements",
         "expected": cost_of("news", 200),
         "cmd": [py, "-c",
                 "import asyncio; from app.workers.announcement_worker import "
                 "fetch_announcements; asyncio.run(fetch_announcements())"]},
        {"job": "Bulk incremental prices",
         "expected": cost_of("eod-bulk", 1),
         "cmd": [py, str(V2_DIR / "download_eod_prices.py"), "--mode", "incremental"]},
    ]


def run_measured(step: dict) -> dict:
    """Run one job with account usage captured either side of it."""
    before = fetch_usage_sync()
    if before is None:
        log.error(f"{step['job']}: cannot read EODHD usage — skipping (unmeasurable)")
        return {**step, "measured": None, "status": "UNMEASURED"}

    log.info(f"─── {step['job']} — expecting ~{step['expected']:,} calls "
             f"(account at {before['used']:,}) ───")
    proc = subprocess.run(step["cmd"], cwd=str(BACKEND))

    after = fetch_usage_sync()
    if after is None:
        return {**step, "measured": None, "status": "UNMEASURED"}

    measured = after["used"] - before["used"]

    # A job the guard deferred spends nothing; that is a correct outcome, not a
    # cost estimate that came in low.
    if proc.returncode == 2 and measured < FLOOR:
        return {**step, "measured": measured, "status": "DEFERRED"}
    if proc.returncode not in (0, 2):
        return {**step, "measured": measured, "status": "JOB FAILED"}

    slack = max(FLOOR, step["expected"] * TOLERANCE)
    status = "PASS" if abs(measured - step["expected"]) <= slack else "WARN"
    return {**step, "measured": measured, "status": status}


def render(rows: list[dict], opening: int, closing: int, limit: int) -> str:
    out = [f"# EODHD budget audit — {date.today().isoformat()}", "",
           "Billed calls measured from the EODHD account either side of each job.",
           "", "| Job | Estimated | Measured | Variance | Status |",
           "|---|---:|---:|---:|---|"]
    for r in rows:
        if r["measured"] is None:
            out.append(f"| {r['job']} | {r['expected']:,} | — | — | {r['status']} |")
            continue
        if r["expected"]:
            var = f"{(r['measured'] - r['expected']) / r['expected'] * 100:+.1f}%"
        else:
            var = "—"
        out.append(f"| {r['job']} | {r['expected']:,} | {r['measured']:,} | "
                   f"{var} | {r['status']} |")

    total_est  = sum(r["expected"] for r in rows)
    total_meas = sum(r["measured"] for r in rows if r["measured"] is not None)
    out += ["", f"**Total** — estimated {total_est:,}, measured {total_meas:,}.",
            f"Account moved {opening:,} → {closing:,} over the run.",
            f"ASX allocation {asx_budget(limit):,} (30% of the {limit:,} EODHD "
            f"plan), reserve {CRITICAL_RESERVE:,}, so "
            f"{asx_budget(limit) - total_meas - CRITICAL_RESERVE:,} spendable "
            f"headroom remained after a full Sunday workload.", ""]

    warns = [r for r in rows if r["status"] == "WARN"]
    if warns:
        out.append("A WARN means the ENDPOINT_COST weight for that endpoint is "
                   "wrong and the budget must be recomputed before the audit "
                   "closes: " + ", ".join(r["job"] for r in warns) + ".")
    else:
        out.append("Every job billed within tolerance of its ENDPOINT_COST "
                   "weight. The budget rests on measurement, not assumption.")
    return "\n".join(out)


def cmd_measure(args) -> int:
    codes = active_codes()
    plan = build_plan(codes)
    if args.only:
        want = [o.lower() for o in args.only]
        plan = [s for s in plan if any(w in s["job"].lower() for w in want)]
        if not plan:
            log.error(f"--only {args.only} matched no job"); return 1

    opening = fetch_usage_sync()
    if opening is None:
        log.error("Cannot read EODHD usage — the audit would measure nothing.")
        return 1
    log.info(f"Universe {len(codes)} active codes. Account opens at "
             f"{opening['used']:,}/{opening['limit']:,}.")

    rows = [run_measured(step) for step in plan]

    closing = fetch_usage_sync()
    report = render(rows, opening["used"],
                    closing["used"] if closing else opening["used"],
                    opening["limit"])
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(report, encoding="utf-8")
    print("\n" + report)
    log.info(f"Written to {REPORT}")

    return 1 if any(r["status"] in ("WARN", "JOB FAILED") for r in rows) else 0


def cmd_verify_coverage(args) -> int:
    """
    Every active symbol should carry a fundamentals file from within the last
    four Sundays. A symbol missing one has fallen through the rotation — most
    likely listed after its own shard last ran.
    """
    if not FUND_DIR.exists():
        log.error(f"No fundamentals directory at {FUND_DIR}"); return 1

    cutoff = date.today() - timedelta(days=args.window_days)
    latest: dict[str, date] = {}
    pat = re.compile(r"^([A-Z0-9.]+)\.AU_(\d{4}-\d{2}-\d{2})\.json\.gz$")
    for f in FUND_DIR.iterdir():
        m = pat.match(f.name)
        if not m:
            continue
        code, d = m.group(1), date.fromisoformat(m.group(2))
        if code not in latest or d > latest[code]:
            latest[code] = d

    codes = active_codes()
    stale   = [c for c in codes if c in latest and latest[c] < cutoff]
    missing = [c for c in codes if c not in latest]

    log.info(f"{len(codes)} active symbols | window {args.window_days} days "
             f"(since {cutoff.isoformat()})")
    for shard in range(SHARD_COUNT):
        members = filter_to_shard(codes, shard)
        fresh = sum(1 for c in members if c in latest and latest[c] >= cutoff)
        log.info(f"  shard {shard}: {fresh}/{len(members)} refreshed in window")

    if not stale and not missing:
        log.info("PASS — every active symbol refreshed within the window.")
        return 0

    if missing:
        log.error(f"{len(missing)} active symbols have NO fundamentals file: "
                  f"{', '.join(missing[:20])}"
                  f"{' …' if len(missing) > 20 else ''}")
    if stale:
        log.error(f"{len(stale)} active symbols are older than the window: "
                  + ", ".join(f"{c}({latest[c].isoformat()})" for c in stale[:20])
                  + (" …" if len(stale) > 20 else ""))
    log.error("Newly listed symbols whose shard has already passed will appear "
              "here. Backfill them with --codes, or wait one full rotation.")
    return 1


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="mode", required=True)

    m = sub.add_parser("measure", help="Run each job once and measure billed cost")
    m.add_argument("--only", nargs="+", metavar="NAME",
                   help="Substring match — measure only these jobs")
    m.set_defaults(func=cmd_measure)

    v = sub.add_parser("verify-coverage",
                       help="Confirm every active symbol got a fundamentals refresh")
    v.add_argument("--window-days", type=int, default=30,
                   help="Days a refresh stays current (default 30 — four "
                        "rotations plus slack for a missed Sunday)")
    v.set_defaults(func=cmd_verify_coverage)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
