#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  migrate.sh — Run all SQL migrations in order
#  Usage:
#    ./database/migrate.sh                   # uses .env values
#    DB_URL=postgresql://... ./database/migrate.sh
# ─────────────────────────────────────────────────────────────

set -euo pipefail

# Load .env if present and DB_URL not already set
if [ -z "${DATABASE_URL_SYNC:-}" ] && [ -f ".env" ]; then
    export $(grep -v '^#' .env | grep DATABASE_URL_SYNC | xargs)
fi

DB_URL="${DATABASE_URL_SYNC:-postgresql://asx_user:changeme@localhost:5432/asx_screener}"
MIGRATIONS_DIR="$(dirname "$0")/migrations"

echo "=== ASX Screener — Database Migration ==="
echo "Target: $DB_URL"
echo ""

for file in "$MIGRATIONS_DIR"/*.sql; do
    name=$(basename "$file")
    echo "▶  Running $name ..."
    psql "$DB_URL" -f "$file" -v ON_ERROR_STOP=1 --quiet
    echo "✅ $name done"
done

echo ""
echo "=== All migrations complete ==="
