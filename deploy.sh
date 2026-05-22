#!/bin/bash
# =============================================================================
# ASX Screener — Full Deploy Script
# =============================================================================
# Usage:
#   ./deploy.sh            # pull latest code + restart both services
#   ./deploy.sh --backend  # restart backend only
#   ./deploy.sh --frontend # restart frontend only
#   ./deploy.sh --status   # show status of both services
#
# Architecture:
#   Backend  → systemd  (asx-api.service)   — FastAPI/uvicorn on port 8000
#   Frontend → PM2      (asx-frontend)      — Next.js
#
# NOTE: Backend must NEVER be added to PM2. Systemd owns it exclusively.
# =============================================================================

set -e

BACKEND_DIR="/opt/asx-screener/backend"
FRONTEND_DIR="/opt/asx-screener/frontend"
VENV="/opt/asx-venv"
REPO_DIR="/opt/asx-screener"

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
    git pull origin main
    log "Code updated ✓"
}

# ── Backend ───────────────────────────────────────────────────────────────────
restart_backend() {
    log "Restarting backend (systemd)..."

    # Kill any stray uvicorn not owned by systemd (e.g. leftover PM2 process)
    if ss -tlnp sport = :8000 | grep -q uvicorn; then
        warn "Stray process on port 8000 — killing..."
        sudo fuser -k 8000/tcp 2>/dev/null || true
        sleep 2
    fi

    sudo systemctl reset-failed asx-api 2>/dev/null || true
    sudo systemctl restart asx-api
    sleep 5

    if systemctl is-active --quiet asx-api; then
        log "Backend running ✓  (PID: $(systemctl show asx-api -p MainPID --value))"
    else
        err "Backend failed to start — check: sudo journalctl -u asx-api -n 30"
    fi
}

# ── Frontend ──────────────────────────────────────────────────────────────────
restart_frontend() {
    log "Restarting frontend (PM2)..."
    cd "$FRONTEND_DIR"

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
        restart_backend
        ;;
    --frontend)
        restart_frontend
        ;;
    --status)
        show_status
        ;;
    "")
        pull_code
        restart_backend
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
