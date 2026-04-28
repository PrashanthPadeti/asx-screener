#!/usr/bin/env bash
# =============================================================================
# setup_cron.sh — Install EODHD download cron jobs on the server
# =============================================================================
# Run once on the Linux server after deploying the code:
#   chmod +x scripts/eodhd/v2/jobs/setup_cron.sh
#   ./scripts/eodhd/v2/jobs/setup_cron.sh
#
# What it installs:
#   1. Daily incremental prices     — weekdays at 18:30 AEST (08:30 UTC)
#   2. Weekly refresh               — Sunday at 22:00 AEST (12:00 UTC)
#      (fundamentals + dividends + splits, checksum-dedup skips unchanged)
#
# Separate historical job is run MANUALLY — see bottom of this script.
# =============================================================================

set -e

# ── Config — edit these if different on your server ──────────────────────────
PROJECT_DIR="/opt/asx-screener"
VENV_PYTHON="${PROJECT_DIR}/.venv/bin/python"
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
DAILY_CMD="30 8 * * 1-5  cd ${PROJECT_DIR} && ${VENV_PYTHON} scripts/eodhd/v2/jobs/incremental_daily.py >> ${LOG_DIR}/incremental_daily.log 2>&1"
WEEKLY_CMD="0 12 * * 0  cd ${PROJECT_DIR} && ${VENV_PYTHON} scripts/eodhd/v2/jobs/weekly_refresh.py >> ${LOG_DIR}/weekly_refresh.log 2>&1"

# ── Install (append only if not already present) ─────────────────────────────
TMPFILE=$(mktemp)
crontab -l 2>/dev/null > "$TMPFILE" || true

CHANGED=0
if ! grep -qF "incremental_daily.py" "$TMPFILE"; then
    echo "$DAILY_CMD" >> "$TMPFILE"
    echo "  ✓ Added: daily incremental prices (weekdays 18:30 AEST)"
    CHANGED=1
else
    echo "  - Daily incremental already in crontab — skipped"
fi

if ! grep -qF "weekly_refresh.py" "$TMPFILE"; then
    echo "$WEEKLY_CMD" >> "$TMPFILE"
    echo "  ✓ Added: weekly refresh (Sunday 22:00 AEST)"
    CHANGED=1
else
    echo "  - Weekly refresh already in crontab — skipped"
fi

if [ "$CHANGED" = "1" ]; then
    crontab "$TMPFILE"
    echo ""
    echo "Crontab updated. Current schedule:"
    crontab -l | grep -E "incremental_daily|weekly_refresh"
fi

rm "$TMPFILE"

echo ""
echo "============================================================"
echo "CRON SETUP COMPLETE"
echo "============================================================"
echo ""
echo "Scheduled jobs:"
echo "  Daily   — Mon–Fri 18:30 AEST: incremental prices download"
echo "  Weekly  — Sunday  22:00 AEST: fundamentals + dividends + splits"
echo ""
echo "Logs:"
echo "  tail -f ${LOG_DIR}/incremental_daily.log"
echo "  tail -f ${LOG_DIR}/weekly_refresh.log"
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
