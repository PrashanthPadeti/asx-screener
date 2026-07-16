#!/bin/bash
# =============================================================================
# ASX Screener — Full Backup Script
# =============================================================================
# Backs up:
#   1. PostgreSQL database (pg_dump, custom format)
#   2. Config & secrets (.env, nginx, systemd, crontab, PM2)
#   3. Logs the git commit + version for reference
#
# Usage:
#   ./backup.sh              # create backup now
#   ./backup.sh --list       # list existing backups
#   ./backup.sh --clean      # remove backups older than 30 days
#
# Scheduled automatically via cron (see crontab).
# Backups live in /opt/backups/asx-screener/
# =============================================================================

set -e

BACKUP_ROOT="/opt/backups/asx-screener"
REPO_DIR="/opt/asx-screener"
DATE=$(date +%Y%m%d_%H%M%S)
VERSION=$(cat "$REPO_DIR/VERSION" 2>/dev/null || echo "unknown")
COMMIT=$(cd "$REPO_DIR" && git rev-parse --short HEAD 2>/dev/null || echo "unknown")
BACKUP_PATH="$BACKUP_ROOT/v${VERSION}_${DATE}"

DB_NAME="asx_screener"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log()  { echo -e "${GREEN}[BACKUP]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC}  $1"; }
err()  { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# ── List backups ──────────────────────────────────────────────────────────────
if [ "$1" = "--list" ]; then
    echo ""
    echo "Existing backups in $BACKUP_ROOT:"
    echo "─────────────────────────────────────────"
    if ls -dt "$BACKUP_ROOT"/v*/ 2>/dev/null | head -20 | while read d; do
        size=$(du -sh "$d" 2>/dev/null | cut -f1)
        ver=$(cat "$d/version.txt" 2>/dev/null || basename "$d")
        echo "  $size  $ver"
    done; then
        :
    else
        echo "  No backups found."
    fi
    echo ""
    total=$(du -sh "$BACKUP_ROOT" 2>/dev/null | cut -f1)
    echo "Total backup size: $total"
    exit 0
fi

# ── Clean old backups ─────────────────────────────────────────────────────────
if [ "$1" = "--clean" ]; then
    log "Removing backups older than 30 days..."
    find "$BACKUP_ROOT" -maxdepth 1 -type d -name "v*" -mtime +30 -exec rm -rf {} + 2>/dev/null || true
    log "Clean complete."
    exit 0
fi

# ── Create backup ─────────────────────────────────────────────────────────────
log "Starting backup  →  v${VERSION} (${COMMIT})"
mkdir -p "$BACKUP_PATH"

# 1. Database
log "Dumping PostgreSQL database '${DB_NAME}'..."
sudo -u postgres pg_dump -Fc "$DB_NAME" > "$BACKUP_PATH/database.dump"
DB_SIZE=$(du -sh "$BACKUP_PATH/database.dump" | cut -f1)
log "Database dump complete  (${DB_SIZE}) ✓"

# 2. Config & secrets
log "Backing up config files..."
CONFIG_FILES=(
    "$REPO_DIR/backend/.env"
    "/etc/systemd/system/asx-backend.service"
    "/etc/nginx/sites-enabled/asx-screener"
    "/etc/nginx/sites-available/asx-screener"
    "/root/.pm2/dump.pm2"
)

EXISTING_CONFIGS=()
for f in "${CONFIG_FILES[@]}"; do
    [ -f "$f" ] && EXISTING_CONFIGS+=("$f")
done

tar -czf "$BACKUP_PATH/config.tar.gz" "${EXISTING_CONFIGS[@]}" 2>/dev/null || warn "Some config files missing — skipped"
log "Config files backed up ✓"

# 3. Crontab
log "Saving crontab..."
crontab -l > "$BACKUP_PATH/crontab.txt" 2>/dev/null || echo "# no crontab" > "$BACKUP_PATH/crontab.txt"
log "Crontab saved ✓"

# 4. Version manifest
cat > "$BACKUP_PATH/version.txt" <<EOF
Version:  v${VERSION}
Commit:   ${COMMIT}
Date:     $(date -u '+%Y-%m-%d %H:%M:%S UTC')
Host:     $(hostname)
Branch:   $(cd "$REPO_DIR" && git branch --show-current 2>/dev/null || echo "unknown")
Tag:      $(cd "$REPO_DIR" && git describe --tags --exact-match 2>/dev/null || echo "untagged")

Restore with:
  ./restore.sh $BACKUP_PATH
EOF
log "Version manifest saved ✓"

# 5. Keep last 14 backups (2 weeks of daily backups)
KEPT=14
OLD_COUNT=$(ls -dt "$BACKUP_ROOT"/v*/ 2>/dev/null | tail -n +$((KEPT+1)) | wc -l)
if [ "$OLD_COUNT" -gt 0 ]; then
    ls -dt "$BACKUP_ROOT"/v*/ | tail -n +$((KEPT+1)) | xargs rm -rf
    log "Removed ${OLD_COUNT} old backup(s) (keeping last ${KEPT}) ✓"
fi

TOTAL_SIZE=$(du -sh "$BACKUP_PATH" | cut -f1)
echo ""
log "════════════════════════════════════"
log "  Backup complete ✓"
log "  Location : $BACKUP_PATH"
log "  Size     : $TOTAL_SIZE"
log "  Version  : v${VERSION} (${COMMIT})"
log "════════════════════════════════════"
echo ""
