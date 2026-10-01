#!/usr/bin/env bash
# =============================================================================
# setup_cron.sh — Install nightly pipeline cron jobs on the server
# =============================================================================
# Run once on the Linux server after deploying the code:
#   chmod +x scripts/eodhd/v2/jobs/setup_cron.sh
#   ./scripts/eodhd/v2/jobs/setup_cron.sh
#
# What it installs:
#   1. Daily full pipeline          — weekdays at 18:30 AEST (08:30 UTC)
#      Steps: download → staging → daily_prices → computed_metrics
#             → daily_metrics (technical indicators) → screener.universe
#   2. Weekly refresh               — Sunday at 22:00 AEST (12:00 UTC)
#      (fundamentals + dividends + splits, checksum-dedup skips unchanged)
#
# Separate historical job is run MANUALLY — see bottom of this script.
# =============================================================================

set -e

# ── Config — edit these if different on your server ──────────────────────────
PROJECT_DIR="/opt/asx-screener"
VENV_PYTHON="${PROJECT_DIR}/asx-venv/bin/python"
LOG_DIR="${PROJECT_DIR}/logs"

# Every scheduled process is defined by four things together — working
# directory, source tree, environment source and Python environment. Treat them
# as one contract; changing any one of them alone is how drift starts.
#
# Source tree: backend/. Copies of these scripts also exist at the repository
# root, last updated in April. Cron pointed at those for months, so fixes that
# were correct in git were not what the server executed.
#
# Environment: `. backend/.env` alone sets shell variables without exporting
# them, so a Python child sees none of them unless the file uses `export`.
# `set -a` around the source is what actually makes them inherited.
ENV_PREFIX="set -a && . ${PROJECT_DIR}/backend/.env && set +a"
SCRIPTS_REL="backend/scripts/eodhd/v2/jobs"

# ── Verify ────────────────────────────────────────────────────────────────────
if [ ! -f "$VENV_PYTHON" ]; then
    echo "ERROR: Python not found at $VENV_PYTHON"
    echo "  Adjust VENV_PYTHON in this script."
    exit 1
fi

if [ ! -f "${PROJECT_DIR}/backend/.env" ]; then
    echo "ERROR: .env not found at ${PROJECT_DIR}/backend/.env"
    echo "  Make sure EODHD_API_KEY and RAW_DATA_DIR are set."
    exit 1
fi

if ! grep -q "EODHD_API_KEY" "${PROJECT_DIR}/backend/.env"; then
    echo "ERROR: EODHD_API_KEY not found in ${PROJECT_DIR}/backend/.env"
    echo "  The budget guard cannot price jobs without it and they will defer."
    exit 1
fi

mkdir -p "$LOG_DIR"

# ── Build the new cron lines ──────────────────────────────────────────────────
# Times are UTC — the server clock is UTC, so 12:00 here is 22:00 AEST.
# ── DISABLED, deliberately ───────────────────────────────────────────────────
# daily_pipeline and weekly_pipeline both call build_screener_universe, which
# invalidates the canonical contract atomically (metric_states = NULL,
# compute_run_id = NULL) — correct and by design — and NEITHER ends in a
# canonical run. Left enabled they revoke a valid published snapshot
# unattended, and the governed surface fails closed until a human repairs
# authority. The decision was to move the human choice BEFORE that destructive
# boundary rather than after it.
#
# They are declared here in their disabled form on purpose. This file is
# DESIRED state; if it declared them enabled while runtime had them off,
# rerunning it would not reproduce the running system, and the reconciliation
# in compute/engine/launch_authority.py would be comparing against a fiction.
#
# Re-enable only when the prefix → admission/lease → canonical driver →
# finalisation → suffix orchestration is deployed and proven. See
# docs/canonical_orchestration.md.
# Re-enabled 2026-10-01. The 23 Sep bridge disabled both of these because the
# legacy path revoked canonical attribution unattended: it rebuilt
# screener.universe outside any run, leaving governed values with no
# finalisation behind them and nobody awake to notice.
#
# That is no longer what these scripts are. Both are now wrappers: prefix,
# then the canonical execution lease, then the driver, then a gated suffix
# that runs only if the driver published. Rehearsed end to end on a clone
# (docs/canonical_rehearsal_record.md, phases 1-5) and proven in production
# on 1 Oct 2026 -- run 2, 2,114 rows, 0 violations, Gate B green.
#
# Restoring the schedule is the last step precisely because it is the one
# that removes the operator from the loop. Everything before it exists so
# that an unattended run either publishes correctly or refuses.
DAILY_CMD="30 8 * * 1-5  cd ${PROJECT_DIR} && ${ENV_PREFIX} && ${VENV_PYTHON} ${SCRIPTS_REL}/daily_pipeline.py >> ${LOG_DIR}/daily_pipeline.log 2>&1"
WEEKLY_COMPUTE_CMD="0 21 * * 0   cd ${PROJECT_DIR} && ${ENV_PREFIX} && ${VENV_PYTHON} ${SCRIPTS_REL}/weekly_pipeline.py >> ${LOG_DIR}/weekly_pipeline.log 2>&1"

WEEKLY_DOWNLOAD_CMD="0 12 * * 0   cd ${PROJECT_DIR} && ${ENV_PREFIX} && ${VENV_PYTHON} ${SCRIPTS_REL}/weekly_refresh.py >> ${LOG_DIR}/weekly_refresh.log 2>&1"

# ── Previously undeclared ────────────────────────────────────────────────────
# These were installed in the crontab and absent from this file, so
# production ran work that code review could not see. Two of them touch
# canonical tables and fired INSIDE the daily pipeline's own window, which is
# a shared input race rather than untidy scheduling.
#
# The yfinance backfill is deliberately NOT declared here any more: the job
# was deleted on 30 Sep 2026. Its entire contribution was eight instruments
# whose prices were 35-49 days stale, and serving a stale price as though it
# were current is the failure this programme exists to remove. Its cron entry
# still exists at runtime, so reconciliation will report UNDECLARED until an
# operator removes it — which is the drift being visible, not a bug.
ANNOUNCEMENTS_CMD="45 8 * * 1-5   cd ${PROJECT_DIR} && ${ENV_PREFIX} && ${VENV_PYTHON} backend/scripts/asx/download_announcements.py >> ${LOG_DIR}/download_announcements.log 2>&1"
PREDICTIONS_CMD="0 21 * * 1-5 ASX_ENV_FILE=${PROJECT_DIR}/backend/.env.predictions ${PROJECT_DIR}/scripts/run_predictions.sh"
# AlphaFive: 22:00 UTC Sunday = Monday 8am AEST, after the weekly pipeline.
# Output freshness: 10:00 UTC daily, after the daily wrapper's window.
#
# A job that defers because a canonical run holds the lease exits 0 and
# writes nothing, which is indistinguishable from a quiet week. This asserts
# the OUTPUT advanced, per [[engineering-rule-output-freshness]].
#
# Known limit, stated rather than hidden: its own failures land in a log.
# A check nobody reads has the same problem it was built to solve, so this
# belongs on the admin system-health surface as well -- tracked separately.
FRESHNESS_CMD="0 10 * * *   cd ${PROJECT_DIR} && ${ENV_PREFIX} && ${VENV_PYTHON} backend/scripts/assert_output_freshness.py >> ${LOG_DIR}/output_freshness.log 2>&1"

ALPHAFIVE_CMD="0 22 * * 0   cd ${PROJECT_DIR}/backend && ${ENV_PREFIX} && ${VENV_PYTHON} -m compute.engine.top5_strategy --force >> ${LOG_DIR}/alphafive.log 2>&1"

# ── Install ──────────────────────────────────────────────────────────────────
#
# Reconciling, not append-if-absent.
#
# The previous form asked `grep -qF "daily_pipeline.py"` and skipped when it
# matched. A DISABLED entry is a comment that still CONTAINS the script name,
# so once a line was commented out the generator could never bring it back:
# it reported "already in crontab — skipped" and changed nothing. Observed
# 1 Oct 2026, when both pipelines were re-enabled in this file and the runtime
# stayed disabled. The reconciler named it ENABLED-STATE DRIFT and said
# exactly the right thing -- "rerunning the generator would not reproduce the
# running system" -- which is the property this file exists to provide.
#
# So each managed entry now REPLACES whatever matches it, commented or not.
# The generator owns these lines; anything else in the crontab is left alone.
TMPFILE=$(mktemp)
crontab -l 2>/dev/null > "$TMPFILE" || true

CHANGED=0

# upsert <match-string> <desired-line> <label>
upsert() {
    local match="$1" desired="$2" label="$3"
    if grep -qxF "$desired" "$TMPFILE"; then
        echo "  - ${label}: already correct"
        return
    fi
    if grep -qF "$match" "$TMPFILE"; then
        grep -vF "$match" "$TMPFILE" > "${TMPFILE}.new" && mv "${TMPFILE}.new" "$TMPFILE"
        echo "  ✓ ${label}: replaced (enabled-state or cadence differed)"
    else
        echo "  ✓ ${label}: added"
    fi
    echo "$desired" >> "$TMPFILE"
    CHANGED=1
}

# Superseded by the full pipeline; drop it wherever it still lives.
if grep -qF "incremental_daily.py" "$TMPFILE"; then
    grep -vF "incremental_daily.py" "$TMPFILE" > "${TMPFILE}.new" && mv "${TMPFILE}.new" "$TMPFILE"
    echo "  ✓ removed superseded incremental_daily entry"
    CHANGED=1
fi

upsert "daily_pipeline.py"        "$DAILY_CMD"           "daily full pipeline (weekdays 18:30 AEST)"
upsert "weekly_refresh.py"        "$WEEKLY_DOWNLOAD_CMD" "weekly download (Sunday 22:00 AEST)"
upsert "weekly_pipeline.py"       "$WEEKLY_COMPUTE_CMD"  "weekly compute pipeline (Monday 07:00 AEST)"
upsert "top5_strategy"            "$ALPHAFIVE_CMD"       "AlphaFive weekly picks (Monday 08:00 AEST)"
upsert "download_announcements.py" "$ANNOUNCEMENTS_CMD"  "ASX announcements download (weekdays 18:45 AEST)"
upsert "run_predictions.sh"       "$PREDICTIONS_CMD"     "nightly predictions (weekdays 07:00 AEST)"
upsert "assert_output_freshness.py" "$FRESHNESS_CMD"      "output freshness check (daily 20:00 AEST)"

if [ "$CHANGED" = "1" ]; then
    crontab "$TMPFILE"
    echo ""
    echo "Crontab updated. Current schedule:"
    crontab -l | grep -E "daily_pipeline|weekly_refresh"
fi

rm "$TMPFILE"

echo ""
echo "============================================================"
echo "CRON SETUP COMPLETE"
echo "============================================================"
echo ""
echo "Scheduled jobs:"
echo "  Daily        — Mon–Fri 18:30 AEST: full daily pipeline"
echo "                 (download → staging → daily_prices → computed_metrics"
echo "                  → daily_metrics → halfyearly_metrics → screener.universe)"
echo "  Sun download — Sunday  22:00 AEST: fundamentals + dividends + splits download"
echo "  Mon compute  — Monday  07:00 AEST: load staging → transforms → yearly/"
echo "                 halfyearly/weekly/monthly compute → screener.universe"
echo "  AlphaFive    — Monday  08:00 AEST: weekly top-5 picks (AlphaFive strategy)"
echo ""
echo "Logs:"
echo "  tail -f ${LOG_DIR}/daily_pipeline.log"
echo "  tail -f ${LOG_DIR}/weekly_refresh.log"
echo "  tail -f ${LOG_DIR}/weekly_pipeline.log"
echo ""
echo "------------------------------------------------------------"
echo "TO START HISTORICAL DOWNLOAD NOW (run in background):"
echo "------------------------------------------------------------"
echo ""
echo "  mkdir -p ${LOG_DIR}"
echo ""
echo "  nohup ${VENV_PYTHON} scripts/eodhd/v2/jobs/historical_download.py \\"
echo "    > ${LOG_DIR}/historical_download.log 2>&1 &"
echo ""
echo "  echo \$! > ${LOG_DIR}/historical_download.pid"
echo "  tail -f ${LOG_DIR}/historical_download.log"
echo ""
echo "TO RESUME IF INTERRUPTED:"
echo "  nohup ${VENV_PYTHON} scripts/eodhd/v2/jobs/historical_download.py \\"
echo "    --from-code <LAST_CODE_SEEN> \\"
echo "    > ${LOG_DIR}/historical_download_resume.log 2>&1 &"
echo ""
echo "TO CHECK DOWNLOAD PROGRESS:"
echo "  ls -lh /opt/asx-screener/data/raw/eodhd/exchange=AU/fundamentals/full_snapshot/ | wc -l"
echo "  ls -lh /opt/asx-screener/data/raw/eodhd/exchange=AU/eod_prices/historical/ | wc -l"
