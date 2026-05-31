#!/bin/bash
# =============================================================================
# ASX Screener — Full Deploy Script
# =============================================================================
# Usage:
#   ./deploy.sh            # pull + build frontend + restart both services
#   ./deploy.sh --backend  # restart backend only (no build)
#   ./deploy.sh --frontend # build + restart frontend only
#   ./deploy.sh --status   # show status of both services
#
# Architecture:
#   Backend  → systemd  (asx-api.service)   — FastAPI/uvicorn on port 8000
#   Frontend → PM2      (asx-frontend)      — Next.js standalone
#
# IMPORTANT: Backend must NEVER be added to PM2.
#            Systemd owns it exclusively to prevent port 8000 conflicts.
# =============================================================================

set -e

REPO_DIR="/opt/asx-screener"
FRONTEND_DIR="/opt/asx-screener/frontend"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log()  { echo -e "${GREEN}[DEPLOY]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC}  $1"; }
err()  { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

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

# ── Pull latest code ──────────────────────────────────────────────────────────
pull_code() {
    log "Pulling latest code..."
    cd "$REPO_DIR"
    git pull
    log "Code updated ✓"
}

# ── Backend Python dependencies ───────────────────────────────────────────────
install_backend_deps() {
    VENV_PIP="/opt/asx-venv/bin/pip"
    REQUIREMENTS="$REPO_DIR/backend/requirements.txt"
    HASH_FILE="$REPO_DIR/.requirements_hash"

    if [ ! -f "$VENV_PIP" ]; then
        err "Python venv not found at /opt/asx-venv — run setup first"
    fi
    if [ ! -f "$REQUIREMENTS" ]; then
        warn "requirements.txt not found — skipping pip install"
        return
    fi

    CURRENT_HASH=$(md5sum "$REQUIREMENTS" | cut -d' ' -f1)
    STORED_HASH=$(cat "$HASH_FILE" 2>/dev/null || echo "")

    if [ "$CURRENT_HASH" = "$STORED_HASH" ]; then
        log "Python dependencies unchanged — skipping install ✓"
        return
    fi

    log "requirements.txt changed — installing dependencies..."
    "$VENV_PIP" install -q -r "$REQUIREMENTS"
    echo "$CURRENT_HASH" > "$HASH_FILE"
    log "Python dependencies updated ✓"
}

# ── Backend ───────────────────────────────────────────────────────────────────
restart_backend() {
    log "Restarting backend (systemd)..."

    sudo systemctl reset-failed asx-api 2>/dev/null || true
    sudo systemctl restart asx-api
    sleep 5

    if systemctl is-active --quiet asx-api; then
        log "Backend running ✓  (PID: $(systemctl show asx-api -p MainPID --value))"
    else
        err "Backend failed — check: sudo journalctl -u asx-api -n 30"
    fi
}

# ── Frontend ──────────────────────────────────────────────────────────────────
build_frontend() {
    log "Building frontend..."
    cd "$FRONTEND_DIR"

    npm run build

    # Copy static assets into standalone output (required for Next.js standalone mode)
    cp -r .next/static   .next/standalone/.next/static
    cp -r public         .next/standalone/public

    log "Frontend built ✓"
}

restart_frontend() {
    cd "$FRONTEND_DIR"

    log "Restarting frontend (PM2)..."
    if pm2 describe asx-frontend > /dev/null 2>&1; then
        pm2 restart asx-frontend
    else
        log "asx-frontend not in PM2 — starting fresh..."
        pm2 start npm --name "asx-frontend" -- start
    fi

    pm2 save --force
    sleep 3

    if pm2 describe asx-frontend | grep -q "online"; then
        log "Frontend running ✓"
    else
        err "Frontend failed — check: pm2 logs asx-frontend"
    fi
}

# ── Main ──────────────────────────────────────────────────────────────────────
case "${1:-}" in
    --backend)
        pull_code
        install_backend_deps
        restart_backend
        ;;
    --frontend)
        pull_code
        build_frontend
        restart_frontend
        ;;
    --status)
        show_status
        ;;
    "")
        pull_code
        install_backend_deps
        restart_backend
        build_frontend
        restart_frontend
        echo ""
        log "============================================"
        log " Deploy complete ✓"
        log "============================================"
        show_status
        ;;
    *)
        echo "Usage: $0 [--backend|--frontend|--status]"
        exit 1
        ;;
esac
