#!/bin/bash
# =============================================================================
# ASX Screener — Restore / New Server Setup Script
# =============================================================================
# Restores a backup to the current server, OR sets up a brand new server
# from scratch using a backup archive.
#
# Usage:
#   # Restore to current server from a specific backup:
#   ./restore.sh /opt/backups/asx-screener/v9.0.0_20260716_120000
#
#   # Full new-server setup (run as root on fresh Ubuntu 22.04):
#   ./restore.sh /opt/backups/asx-screener/v9.0.0_20260716_120000 --new-server
#
# What this restores:
#   1. Code  — clones repo and checks out the backed-up version
#   2. DB    — restores PostgreSQL from pg_dump
#   3. Config — restores .env, nginx, systemd, crontab
#   4. Services — starts backend (systemd) + frontend (PM2)
# =============================================================================

set -e

BACKUP_PATH="$1"
MODE="${2:-restore}"   # restore | --new-server

REPO_URL="https://github.com/PrashanthPadeti/asx-screener.git"
INSTALL_DIR="/opt/asx-screener"
VENV_DIR="/opt/asx-screener/asx-venv"
DB_NAME="asx_screener"
DB_USER="asx_user"
DB_PASS="asx_secure_2024"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log()  { echo -e "${GREEN}[RESTORE]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC}   $1"; }
err()  { echo -e "${RED}[ERROR]${NC}  $1"; exit 1; }

# ── Validate ──────────────────────────────────────────────────────────────────
[ -z "$BACKUP_PATH" ] && err "Usage: ./restore.sh <backup-path> [--new-server]"
[ ! -d "$BACKUP_PATH" ] && err "Backup not found: $BACKUP_PATH"
[ ! -f "$BACKUP_PATH/database.dump" ] && err "No database.dump in $BACKUP_PATH"

VERSION=$(cat "$BACKUP_PATH/version.txt" 2>/dev/null | grep "^Version" | awk '{print $2}')
log "Restoring from backup: $BACKUP_PATH"
log "Version: $VERSION"
echo ""

# ── NEW SERVER: Install system dependencies ───────────────────────────────────
if [ "$MODE" = "--new-server" ]; then
    log "=== NEW SERVER SETUP ==="
    log "Installing system packages..."

    apt-get update -q
    apt-get install -y -q \
        git curl wget nginx \
        postgresql-16 postgresql-client-16 \
        python3.12 python3.12-venv python3.12-dev \
        build-essential libpq-dev \
        redis-server

    # Node.js 20
    if ! command -v node &>/dev/null; then
        log "Installing Node.js 20..."
        curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
        apt-get install -y nodejs
    fi

    # PM2
    npm install -g pm2 2>/dev/null || true

    log "System packages installed ✓"

    # Start PostgreSQL
    systemctl start postgresql@16-main
    systemctl enable postgresql@16-main
    log "PostgreSQL started ✓"

    # Create DB user and database
    sudo -u postgres psql <<SQL
DO \$\$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '$DB_USER') THEN
        CREATE USER $DB_USER WITH PASSWORD '$DB_PASS';
    END IF;
END \$\$;
CREATE DATABASE $DB_NAME OWNER $DB_USER;
GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;
SQL
    log "Database user and schema created ✓"

    # Clone repo
    log "Cloning repository..."
    git clone "$REPO_URL" "$INSTALL_DIR"
    log "Repository cloned ✓"
fi

# ── CODE: checkout the backed-up version ─────────────────────────────────────
log "=== CODE ==="
cd "$INSTALL_DIR"
TAG=$(cat "$BACKUP_PATH/version.txt" 2>/dev/null | grep "^Tag" | awk '{print $2}')
if [ -n "$TAG" ] && [ "$TAG" != "untagged" ]; then
    git fetch --tags
    git checkout "$TAG"
    log "Checked out $TAG ✓"
else
    COMMIT=$(cat "$BACKUP_PATH/version.txt" | grep "^Commit" | awk '{print $2}')
    git checkout "$COMMIT"
    log "Checked out commit $COMMIT ✓"
fi

# ── CONFIG: restore .env and server config ────────────────────────────────────
log "=== CONFIG ==="
if [ -f "$BACKUP_PATH/config.tar.gz" ]; then
    tar -xzf "$BACKUP_PATH/config.tar.gz" -C / 2>/dev/null || warn "Some config files could not be restored"
    log "Config files restored ✓"
    log "  ⚠  Review backend/.env — API keys and secrets may need updating"
else
    warn "No config.tar.gz found — you must manually create backend/.env"
fi

# ── DATABASE: restore from dump ───────────────────────────────────────────────
log "=== DATABASE ==="
log "Restoring database '${DB_NAME}' (this may take several minutes)..."

# Drop existing data if restoring over existing install
sudo -u postgres psql -c "DROP DATABASE IF EXISTS ${DB_NAME};" 2>/dev/null || true
sudo -u postgres psql -c "CREATE DATABASE ${DB_NAME} OWNER ${DB_USER};" 2>/dev/null || true

pg_restore -U "$DB_USER" -d "$DB_NAME" --no-owner --role="$DB_USER" \
    "$BACKUP_PATH/database.dump"
log "Database restored ✓"

# ── CRONTAB: restore scheduled jobs ──────────────────────────────────────────
log "=== CRONTAB ==="
if [ -f "$BACKUP_PATH/crontab.txt" ]; then
    crontab "$BACKUP_PATH/crontab.txt"
    log "Crontab restored ✓"
fi

# ── PYTHON VENV ───────────────────────────────────────────────────────────────
if [ ! -d "$VENV_DIR" ]; then
    log "=== PYTHON ENV ==="
    python3.12 -m venv "$VENV_DIR"
    "$VENV_DIR/bin/pip" install -q -r "$INSTALL_DIR/backend/requirements.txt"
    log "Python venv created ✓"
fi

# ── SYSTEMD: backend service ──────────────────────────────────────────────────
log "=== SERVICES ==="
systemctl daemon-reload
systemctl enable asx-backend
systemctl restart asx-backend
sleep 3
systemctl is-active asx-backend && log "Backend running ✓" || warn "Backend may not have started — check: journalctl -u asx-backend -n 30"

# ── FRONTEND: build + PM2 ────────────────────────────────────────────────────
log "Building frontend..."
cd "$INSTALL_DIR/frontend"
npm ci --quiet
npm run build
cp -r .next/static   .next/standalone/.next/static
cp -r public         .next/standalone/public

pm2 delete asx-frontend 2>/dev/null || true
pm2 start .next/standalone/server.js \
    --name "asx-frontend" \
    --interpreter node \
    --env production
pm2 save --force
pm2 startup 2>/dev/null || true
log "Frontend running ✓"

# ── NGINX ─────────────────────────────────────────────────────────────────────
nginx -t && systemctl reload nginx && log "Nginx reloaded ✓" || warn "Nginx config issue — check manually"

echo ""
log "════════════════════════════════════════════"
log "  Restore complete ✓"
log "  Version : $VERSION"
log "  Site    : check https://asxscreener.com.au"
log ""
log "  Post-restore checklist:"
log "  □ Verify login works"
log "  □ Check backend/.env has correct API keys"
log "  □ Update DNS if on a new server"
log "  □ Re-issue SSL cert if new server:"
log "    certbot --nginx -d asxscreener.com.au"
log "════════════════════════════════════════════"
