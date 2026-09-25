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
DISABLED_REASON="# DISABLED 2026-09-23 p0a bridge — legacy path revokes canonical attribution unattended:"
DAILY_CMD="${DISABLED_REASON} 30 8 * * 1-5  cd ${PROJECT_DIR} && ${ENV_PREFIX} && ${VENV_PYTHON} ${SCRIPTS_REL}/daily_pipeline.py >> ${LOG_DIR}/daily_pipeline.log 2>&1"
WEEKLY_COMPUTE_CMD="${DISABLED_REASON} 0 21 * * 0   cd ${PROJECT_DIR} && ${ENV_PREFIX} && ${VENV_PYTHON} ${SCRIPTS_REL}/weekly_pipeline.py >> ${LOG_DIR}/weekly_pipeline.log 2>&1"

WEEKLY_DOWNLOAD_CMD="0 12 * * 0   cd ${PROJECT_DIR} && ${ENV_PREFIX} && ${VENV_PYTHON} ${SCRIPTS_REL}/weekly_refresh.py >> ${LOG_DIR}/weekly_refresh.log 2>&1"

# ── Previously undeclared ────────────────────────────────────────────────────
# These three were installed in the crontab and absent from this file, so
# production ran work that code review could not see. Two of them touch
# canonical tables and both fire INSIDE the daily pipeline's own window —
# 08:45 and 09:00 against a pipeline starting at 08:30 — which is a shared
# input race, not merely untidy scheduling. Declared here so the drift is
# visible; their placement relative to the canonical lease is a separate
# decision the wrapper refactor settles.
ANNOUNCEMENTS_CMD="45 8 * * 1-5   cd ${PROJECT_DIR} && ${ENV_PREFIX} && ${VENV_PYTHON} backend/scripts/asx/download_announcements.py >> ${LOG_DIR}/download_announcements.log 2>&1"
YFINANCE_BACKFILL_CMD="0 9 * * 1-5   cd ${PROJECT_DIR} && ${ENV_PREFIX} && ${VENV_PYTHON} backend/scripts/eodhd/v2/backfill_yfinance_prices.py --days 3 >> ${LOG_DIR}/yfinance_backfill.log 2>&1"
PREDICTIONS_CMD="0 21 * * 1-5 ASX_ENV_FILE=${PROJECT_DIR}/backend/.env.predictions ${PROJECT_DIR}/scripts/run_predictions.sh"
# AlphaFive: 22:00 UTC Sunday = Monday 8am AEST, after the weekly pipeline.
ALPHAFIVE_CMD="0 22 * * 0   cd ${PROJECT_DIR}/backend && ${ENV_PREFIX} && ${VENV_PYTHON} -m compute.engine.top5_strategy --force >> ${LOG_DIR}/alphafive.log 2>&1"

# ── Install (append only if not already present) ─────────────────────────────
TMPFILE=$(mktemp)
crontab -l 2>/dev/null > "$TMPFILE" || true

CHANGED=0
if ! grep -qF "daily_pipeline.py" "$TMPFILE"; then
    # Remove old incremental_daily entry if present (replaced by full pipeline)
    grep -vF "incremental_daily.py" "$TMPFILE" > "${TMPFILE}.new" && mv "${TMPFILE}.new" "$TMPFILE"
    echo "$DAILY_CMD" >> "$TMPFILE"
    echo "  ✓ Added: daily full pipeline (weekdays 18:30 AEST)"
    CHANGED=1
else
    echo "  - Daily pipeline already in crontab — skipped"
fi

if ! grep -qF "weekly_refresh.py" "$TMPFILE"; then
    echo "$WEEKLY_DOWNLOAD_CMD" >> "$TMPFILE"
    echo "  ✓ Added: weekly download (Sunday 22:00 AEST)"
    CHANGED=1
else
    echo "  - Weekly download already in crontab — skipped"
fi

if ! grep -qF "weekly_pipeline.py" "$TMPFILE"; then
    echo "$WEEKLY_COMPUTE_CMD" >> "$TMPFILE"
    echo "  ✓ Added: weekly compute pipeline (Monday 07:00 AEST)"
    CHANGED=1
else
    echo "  - Weekly compute pipeline already in crontab — skipped"
fi

if ! grep -qF "top5_strategy" "$TMPFILE"; then
    echo "$ALPHAFIVE_CMD" >> "$TMPFILE"
    echo "  ✓ Added: AlphaFive weekly picks (Monday 08:00 AEST)"
    CHANGED=1
else
    echo "  - AlphaFive picks already in crontab — skipped"
fi

if ! grep -qF "download_announcements.py" "$TMPFILE"; then
    echo "$ANNOUNCEMENTS_CMD" >> "$TMPFILE"
    echo "  ✓ Added: ASX announcements download (weekdays 18:45 AEST)"
    CHANGED=1
else
    echo "  - Announcements download already in crontab — skipped"
fi

if ! grep -qF "backfill_yfinance_prices.py" "$TMPFILE"; then
    echo "$YFINANCE_BACKFILL_CMD" >> "$TMPFILE"
    echo "  ✓ Added: yfinance price backfill (weekdays 19:00 AEST)"
    CHANGED=1
else
    echo "  - yfinance backfill already in crontab — skipped"
fi

if ! grep -qF "run_predictions.sh" "$TMPFILE"; then
    echo "$PREDICTIONS_CMD" >> "$TMPFILE"
    echo "  ✓ Added: nightly predictions (weekdays 07:00 AEST)"
    CHANGED=1
else
    echo "  - Predictions run already in crontab — skipped"
fi

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
