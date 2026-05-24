#!/bin/bash
# =============================================================================
# ASX Screener — Restore to v5.0.0
# =============================================================================
# Usage:
#   ./restore_v5.sh          # full restore (backend + frontend)
#   ./restore_v5.sh --check  # dry-run — show what will happen, make no changes
#   ./restore_v5.sh --status # show current service status
#
# What this script does:
#   1. Fetches the v5.0.0 tag from GitHub
#   2. Hard-resets the codebase to v5.0.0
#   3. Creates a pre-restore backup of current code
#   4. Restarts backend (systemd)
#   5. Rebuilds and restarts frontend (Next.js / PM2)
#   6. Runs health checks
#
# Safety:
#   - Current code is backed up to /opt/backups/pre_restore_<timestamp>.zip
#   - Database is NOT touched — only application code is rolled back
#   - If anything fails the script exits immediately (set -e)
#
# Version: v5.0.0
# Date:    2026-05-24
# =============================================================================

set -e

# ── Config ────────────────────────────────────────────────────────────────────
TARGET_VERSION="v5.0.0"
REPO_DIR="/opt/asx-screener"
FRONTEND_DIR="/opt/asx-screener/frontend"
BACKUP_DIR="/opt/backups"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
PRE_RESTORE_BACKUP="$BACKUP_DIR/pre_restore_${TIMESTAMP}.zip"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

log()  { echo -e "${GREEN}[RESTORE]${NC} $1"; }
info() { echo -e "${BLUE}[INFO]${NC}    $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC}    $1"; }
err()  { echo -e "${RED}[ERROR]${NC}   $1"; exit 1; }
ok()   { echo -e "${GREEN}[OK]${NC}      $1"; }

# ── Status ────────────────────────────────────────────────────────────────────
show_status() {
    echo ""
    log "=== Backend (systemd) ==="
    systemctl status asx-api --no-pager | head -8

    echo ""
    log "=== Frontend (PM2) ==="
    pm2 list 2>/dev/null || warn "PM2 not running"

    echo ""
    log "=== Port 8000 ==="
    ss -tlnp sport = :8000 || true
}

# ── Dry run ───────────────────────────────────────────────────────────────────
dry_run_check() {
    echo ""
    echo -e "${BLUE}============================================================${NC}"
    echo -e "${BLUE}  DRY RUN — Restore to ${TARGET_VERSION}${NC}"
    echo -e "${BLUE}============================================================${NC}"
    echo ""

    info "Target version  : $TARGET_VERSION"
    info "Repo directory  : $REPO_DIR"
    info "Frontend dir    : $FRONTEND_DIR"
    info "Backup will be  : $PRE_RESTORE_BACKUP"
    echo ""

    cd "$REPO_DIR"

    info "Current HEAD:"
    git log --oneline -1

    info "Current branch/tag:"
    git describe --tags --always 2>/dev/null || git rev-parse --short HEAD

    echo ""
    info "Checking if $TARGET_VERSION exists on remote..."
    git fetch --tags --quiet
    if git rev-parse "$TARGET_VERSION" >/dev/null 2>&1; then
        ok "$TARGET_VERSION tag found ✓"
        info "Tag points to commit: $(git rev-parse $TARGET_VERSION)"
    else
        err "$TARGET_VERSION tag NOT found. Aborting."
    fi

    echo ""
    info "Services that will be restarted:"
    echo "  • asx-api.service  (systemd — backend)"
    echo "  • asx-frontend     (PM2 — frontend)"
    echo ""
    warn "DATABASE: NOT touched — only application code will be rolled back."
    warn "Run with no flags to perform the actual restore."
    echo ""
}

# ── Pre-restore backup ────────────────────────────────────────────────────────
backup_current() {
    log "Creating pre-restore backup of current code..."
    mkdir -p "$BACKUP_DIR"
    cd "$REPO_DIR"
    git archive --format=zip --output="$PRE_RESTORE_BACKUP" HEAD
    ok "Backup saved: $PRE_RESTORE_BACKUP  ($(du -sh $PRE_RESTORE_BACKUP | cut -f1))"
}

# ── Checkout v5.0.0 ───────────────────────────────────────────────────────────
checkout_version() {
    log "Fetching tags from remote..."
    cd "$REPO_DIR"
    git fetch --tags

    if ! git rev-parse "$TARGET_VERSION" >/dev/null 2>&1; then
        err "Tag $TARGET_VERSION not found after fetch. Check GitHub."
    fi

    log "Checking out $TARGET_VERSION..."
    git checkout "$TARGET_VERSION"
    ok "Code is now at $TARGET_VERSION ✓"

    info "Commit: $(git log --oneline -1)"
}

# ── Backend ───────────────────────────────────────────────────────────────────
restart_backend() {
    log "Restarting backend (systemd)..."
    sudo systemctl reset-failed asx-api 2>/dev/null || true
    sudo systemctl restart asx-api
    sleep 5

    if systemctl is-active --quiet asx-api; then
        ok "Backend running ✓  (PID: $(systemctl show asx-api -p MainPID --value))"
    else
        err "Backend failed to start. Check: sudo journalctl -u asx-api -n 50"
    fi
}

# ── Frontend ──────────────────────────────────────────────────────────────────
build_and_restart_frontend() {
    log "Installing frontend dependencies..."
    cd "$FRONTEND_DIR"
    npm ci --silent

    log "Building frontend (Next.js)..."
    npm run build

    # Copy static assets into standalone output
    cp -r .next/static  .next/standalone/.next/static
    cp -r public        .next/standalone/public
    ok "Frontend built ✓"

    log "Restarting frontend (PM2)..."
    if pm2 describe asx-frontend > /dev/null 2>&1; then
        pm2 restart asx-frontend
    else
        warn "asx-frontend not in PM2 — starting fresh..."
        pm2 start npm --name "asx-frontend" -- start
    fi

    pm2 save --force
    sleep 4

    if pm2 describe asx-frontend | grep -q "online"; then
        ok "Frontend running ✓"
    else
        err "Frontend failed. Check: pm2 logs asx-frontend"
    fi
}

# ── Health checks ─────────────────────────────────────────────────────────────
health_checks() {
    log "Running health checks..."

    # Backend API
    sleep 2
    if curl -sf http://localhost:8000/health >/dev/null 2>&1; then
        ok "Backend /health → 200 ✓"
    else
        warn "Backend /health did not respond — check manually: curl http://localhost:8000/health"
    fi

    # Frontend
    if curl -sf http://localhost:3000 >/dev/null 2>&1; then
        ok "Frontend → 200 ✓"
    else
        warn "Frontend did not respond on :3000 — check: pm2 logs asx-frontend"
    fi
}

# ── Main ──────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}============================================================${NC}"
echo -e "${GREEN}  ASX Screener — Restore to ${TARGET_VERSION}${NC}"
echo -e "${GREEN}============================================================${NC}"
echo ""

case "${1:-}" in
    --check)
        dry_run_check
        ;;
    --status)
        show_status
        ;;
    "")
        warn "This will restore the application to $TARGET_VERSION."
        warn "Current code will be backed up first."
        echo ""
        read -p "Continue? (yes/no): " CONFIRM
        if [[ "$CONFIRM" != "yes" ]]; then
            echo "Aborted."
            exit 0
        fi
        echo ""

        backup_current
        checkout_version
        restart_backend
        build_and_restart_frontend
        health_checks

        echo ""
        log "============================================"
        log " Restore to $TARGET_VERSION complete ✓"
        log "============================================"
        show_status

        echo ""
        info "Pre-restore backup: $PRE_RESTORE_BACKUP"
        info "To return to latest: git checkout main && ./deploy.sh"
        ;;
    *)
        echo "Usage: $0 [--check|--status]"
        exit 1
        ;;
esac
