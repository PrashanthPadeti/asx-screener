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

# ── Verify ────────────────────────────────────────────────────────────────────
if [ ! -f "$VENV_PYTHON" ]; then
    echo "ERROR: Python not found at $VENV_PYTHON"
    echo "  Adjust VENV_PYTHON in this script."
    exit 1
fi

if [ ! -f "${PROJECT_DIR}/.env" ]; then
    echo "ERROR: .env not found at ${PROJECT_DIR}/.env"
    echo "  Make sure EODHD_API_KEY and RAW_DATA_DIR are set."
    exit 1
fi

mkdir -p "$LOG_DIR"

# ── Build the new cron lines ──────────────────────────────────────────────────
DAILY_CMD="30 8 * * 1-5  cd ${PROJECT_DIR} && ${VENV_PYTHON} scripts/eodhd/v2/jobs/daily_pipeline.py >> ${LOG_DIR}/daily_pipeline.log 2>&1"
WEEKLY_DOWNLOAD_CMD="0 12 * * 0   cd ${PROJECT_DIR} && ${VENV_PYTHON} scripts/eodhd/v2/jobs/weekly_refresh.py >> ${LOG_DIR}/weekly_refresh.log 2>&1"
WEEKLY_COMPUTE_CMD="0 21 * * 0   cd ${PROJECT_DIR} && ${VENV_PYTHON} scripts/eodhd/v2/jobs/weekly_pipeline.py >> ${LOG_DIR}/weekly_pipeline.log 2>&1"

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
