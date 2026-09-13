#!/usr/bin/env bash
#
# Production dividend reload — a historical source correction
# ===========================================================
# Lives in the repo rather than being pasted. A long block through a wrapped
# console has now been corrupted twice in this rollout, and this one performs
# a destructive full-table replacement on production.
#
# What this is, precisely: NOT a four-month catch-up. Comparison with the
# repaired source shows material historical undercoverage across prior periods
# -- January 2025 held 26 rows against the source's 216 -- so dividend-history
# metrics derived from the old table may have been incorrect for substantially
# longer than the stall. P0-A treats the repaired table as a source correction
# requiring downstream recomputation.
#
# The outage cause, stated exactly: the upstream raw dividend acquisition
# remained current; the staging-load and market-transform stages were not on a
# production schedule, so market.dividends advanced only when that path was
# manually executed. The provider did not stop working.
#
# Preconditions, all refused rather than warned about:
#     the resolver reaches the production database
#     cron shows zero live entries (the writer freeze is in force)
#     a verified, readable table backup exists
#
# AFTER THIS RUNS, screener.universe still holds dividend metrics derived from
# the OLD table. dividend_yield, grossed_up_yield, payout_ratio,
# dividend_cagr_3y/5y, dividend_consecutive_yrs, income_score and
# composite_score are superseded evidence until the canonical V2 recompute
# regenerates them. They must not be read as validated against the repaired
# source. No derived column is patched separately.
#
# Usage:
#   backend/scripts/p0a_dividend_reload.sh            # preconditions only
#   backend/scripts/p0a_dividend_reload.sh --execute

set -u

HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
BACKEND=$(cd -- "$HERE/.." && pwd)
cd "$BACKEND" || { echo "ERROR: cannot enter $BACKEND" >&2; exit 2; }

ASX_ROOT=${ASX_ROOT:-/opt/asx-screener}
PYBIN=${PYBIN:-$ASX_ROOT/asx-venv/bin/python}
BACKUP_DIR=${BACKUP_DIR:-/var/backups/p0a/dividends}
STAMP=$(date -u +%Y%m%dT%H%M%SZ)

[ -x "$PYBIN" ] || { echo "ERROR: $PYBIN not found — wrong host?" >&2; exit 2; }
[ -f "$BACKEND/.env" ] || { echo "ERROR: $BACKEND/.env not found" >&2; exit 2; }

set -a; . "$BACKEND/.env"; set +a

EXECUTE=0
[ "${1:-}" = "--execute" ] && EXECUTE=1

# ── Preconditions ────────────────────────────────────────────────────────────

# Identity through the same resolver the loaders use, not through a name we
# assembled ourselves.
REACHED=$("$PYBIN" -c "
import psycopg2
from app.core.db import get_database_url_sync
c = psycopg2.connect(get_database_url_sync()); cur = c.cursor()
cur.execute('SELECT current_database()'); print(cur.fetchone()[0])" 2>&1 | tail -1)

PROD=$("$PYBIN" -c "
import os, urllib.parse as u
print(u.urlparse(os.environ['DATABASE_URL']).path.lstrip('/'))" 2>/dev/null)

CRON_LIVE=$(crontab -l 2>/dev/null | grep -cE '^[^#[:space:]]')

echo "host:            $(hostname)"
echo "resolver reaches: $REACHED"
echo "expected:        $PROD"
echo "cron live:       $CRON_LIVE (must be 0 — the writer freeze)"
echo "revision:        $(git log --oneline -1 2>/dev/null || echo 'not a checkout')"
echo

fail=0
[ "$REACHED" = "$PROD" ] || { echo "REFUSING: resolver reached '$REACHED', not '$PROD'" >&2; fail=1; }
[ "$CRON_LIVE" = "0" ]   || { echo "REFUSING: $CRON_LIVE live cron entries; the freeze is not in force" >&2; fail=1; }
[ $fail -eq 0 ] || exit 2

echo "=== current state ==="
sudo -u postgres psql -X -d "$PROD" -c "
SELECT count(*) AS rows, count(DISTINCT asx_code) AS issuers,
       max(ex_date) AS latest_any,
       max(ex_date) FILTER (WHERE ex_date <= current_date) AS latest_occurred
  FROM market.dividends;" || exit 2

if [ $EXECUTE -eq 0 ]; then
    echo
    echo "Preconditions pass. Re-run with --execute to perform the reload."
    exit 0
fi

# ── Backup, verified before anything is destroyed ────────────────────────────

echo
echo "=== backup ==="
mkdir -p "$BACKUP_DIR" && chmod 755 "$BACKUP_DIR" || exit 2
DUMP="$BACKUP_DIR/market_dividends_$STAMP.dump"

# Redirect as root: pg_dump runs as postgres and cannot write into a
# root-owned directory. That failure has been hit before in this rollout.
sudo -u postgres pg_dump -d "$PROD" -Fc -t market.dividends > "$DUMP" || exit 2
chmod 644 "$DUMP"
ls -lh "$DUMP"

# A dump that cannot be read is not a backup. Checked before the destructive
# step, because afterwards is too late to find out.
TOC=$(sudo -u postgres pg_restore -l "$DUMP" 2>/dev/null | grep -c .)
if [ "${TOC:-0}" -lt 1 ]; then
    echo "REFUSING: the backup at $DUMP is not readable by pg_restore. " >&2
    echo "          Nothing has been modified." >&2
    exit 2
fi
echo "backup verified readable — $TOC TOC entries"

# ── The reload ───────────────────────────────────────────────────────────────

echo
echo "=== load: raw zone -> staging_au.dividends ==="
"$PYBIN" scripts/eodhd/v2/load_to_staging_dividends.py 2>&1 | tail -4
rc=${PIPESTATUS[0]}
[ "$rc" -eq 0 ] || { echo "staging load failed rc=$rc; market.dividends untouched" >&2; exit 1; }

echo
echo "=== transform: staging -> market.dividends (truncate+reload, atomic) ==="
"$PYBIN" scripts/eodhd/v2/transforms/transform_dividends.py 2>&1 | tail -14
rc=${PIPESTATUS[0]}
if [ "$rc" -ne 0 ]; then
    echo >&2
    echo "transform refused or failed (rc=$rc). The truncate is inside its own" >&2
    echo "transaction, so market.dividends is unchanged. Nothing to restore." >&2
    exit 1
fi

# ── Independent verification ─────────────────────────────────────────────────

echo
echo "=== after ==="
sudo -u postgres psql -X -d "$PROD" -c "
SELECT count(*) AS rows, count(DISTINCT asx_code) AS issuers,
       max(ex_date) FILTER (WHERE ex_date <= current_date) AS latest_occurred,
       count(*) FILTER (WHERE ex_date <= current_date
                          AND ex_date >= current_date - 35) AS rows_35d,
       count(DISTINCT asx_code) FILTER (WHERE ex_date <= current_date
                          AND ex_date >= current_date - 35) AS issuers_35d,
       count(*) FILTER (WHERE ex_date > current_date) AS future_announced
  FROM market.dividends;"

echo
echo "=== independent health classification ==="
"$PYBIN" -c "
import sys
import psycopg2
from app.core.db import get_database_url_sync
from compute.engine.daily_compute import fetch_feed_health
c = psycopg2.connect(get_database_url_sync()); cur = c.cursor()
cur.execute('SELECT current_database()'); print('database:', cur.fetchone()[0])
h = fetch_feed_health(cur)
print('healthy :', h.healthy)
print('failure :', h.failure)
print('latest  :', h.latest_ex_date, '| lag:', h.lag_days)
print('breadth :', h.recent_rows, 'rows /', h.recent_issuers, 'issuers')
print('future  :', h.future_announced)
sys.exit(0 if h.healthy else 3)"
health=$?

echo
echo "────────────────────────────────────────────────────────────"
if [ $health -ne 0 ]; then
    echo "FEED IS NOT HEALTHY AFTER THE RELOAD. Do not advance the rollout." >&2
    echo "Restore with:" >&2
    echo "  sudo -u postgres pg_restore -d $PROD -t market.dividends \\" >&2
    echo "      --data-only --clean $DUMP" >&2
    exit 3
fi

echo "RELOAD COMPLETE — market.dividends is healthy on occurred evidence."
echo "backup: $DUMP"
echo
echo "screener.universe still holds dividend metrics derived from the OLD"
echo "table. They are superseded evidence, not validated against this source."
echo "The canonical V2 recompute regenerates them; nothing is patched."
