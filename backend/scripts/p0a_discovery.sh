#!/usr/bin/env bash
#
# P0-A discovery run — the V2 pipeline against a scratch database
# ===============================================================
# A discovery run, with publication disabled. It answers "what does V2
# actually produce" without any of it becoming servable, and it must stay
# incapable of becoming authoritative by construction rather than by care.
#
# Why a separate DATABASE and not a scratch SCHEMA. Every write path in the
# pipeline is hardcoded to schema-qualified names -- screener.universe,
# market.yearly_metrics, market.computed_metrics -- so a scratch schema means
# threading a schema parameter through three scripts, and a parameter that can
# be set to screener_scratch can be set back to screener. The isolation would
# rest on a flag. A separate database needs no code change at all, and the only
# way its contents reach a customer is editing the application's connection
# string, which is the same action as pointing production at anything else.
#
# What that guarantee is and is not: the scratch data lives in a database the
# application's configured DATABASE_URL does not name. This script refuses to
# target the production database, and verifies by observation -- it asks the
# connection which database it actually reached -- rather than trusting that
# an exported variable took effect.
#
# Stage order is the weekly pipeline's, not invented here:
#   daily_compute -> yearly_compute -> build_screener_universe
#   -> composite_score -> sector_benchmarks
# Steps the V2 change does not touch (technical, weekly, monthly, period,
# pros_cons) are deliberately NOT rerun: their production outputs are cloned
# and read as-is, which keeps the discovery run comparable to production
# instead of mixing in unrelated recomputation.
#
# Usage:
#   p0a_discovery.sh clone      create + load the scratch database
#   p0a_discovery.sh verify     row counts scratch vs production
#   p0a_discovery.sh run        the five stages, scratch only
#   p0a_discovery.sh evidence   the evidence bundle
#   p0a_discovery.sh all        all four, stopping on the first failure
#
#   ( set -o pipefail; backend/scripts/p0a_discovery.sh all 2>&1 \
#     | tee /tmp/discovery.log ); echo "EXIT=$?"

set -u

HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
BACKEND=$(cd -- "$HERE/.." && pwd)
cd "$BACKEND" || { echo "ERROR: cannot enter $BACKEND" >&2; exit 2; }

ASX_ROOT=${ASX_ROOT:-/opt/asx-screener}
PYBIN=${PYBIN:-$ASX_ROOT/asx-venv/bin/python}
SCRATCH=${SCRATCH_DB:-asx_screener_scratch}
WORKDIR=${WORKDIR:-/var/backups/p0a/discovery}

#: Read by no pipeline stage (derived from the code, not assumed), and between
#: them 1.7GB of the 7.4GB database. Excluded so the clone is 5.3GB.
EXCLUDE=(-T staging_au.eod_prices -T market.price_predictions)

[ -x "$PYBIN" ] || { echo "ERROR: $PYBIN not found — wrong host?" >&2; exit 2; }
[ -f "$BACKEND/.env" ] || { echo "ERROR: $BACKEND/.env not found" >&2; exit 2; }

set -a; . "$BACKEND/.env"; set +a

PROD=$("$PYBIN" -c "
import os, urllib.parse as u
print(u.urlparse(os.environ['DATABASE_URL']).path.lstrip('/'))" 2>/dev/null)
[ -n "${PROD:-}" ] || { echo "ERROR: cannot read database name from DATABASE_URL" >&2; exit 2; }

# The one guard that matters. Everything else in this script is convenience.
if [ "$SCRATCH" = "$PROD" ]; then
    echo "REFUSING: scratch database resolves to production ($PROD)." >&2
    exit 2
fi

# The scratch URL: production's, with the database name replaced. Built by
# parsing rather than by string substitution, so a password that happens to
# contain the database name cannot corrupt it.
scratch_url() {
    "$PYBIN" - "$1" "$SCRATCH" <<'PY'
import sys, urllib.parse as u
parsed = u.urlparse(sys.argv[1])
print(u.urlunparse(parsed._replace(path="/" + sys.argv[2])))
PY
}

echo "host:       $(hostname)"
echo "production: $PROD  (read-only here, never written)"
echo "scratch:    $SCRATCH"
echo "revision:   $(git log --oneline -1 2>/dev/null || echo 'not a checkout')"
echo

# ── clone ─────────────────────────────────────────────────────────────────────

do_clone() {
    echo "=== clone ==="
    if [ "$(sudo -u postgres psql -tAc \
            "SELECT 1 FROM pg_database WHERE datname='$SCRATCH';")" = "1" ]; then
        echo "ERROR: $SCRATCH already exists." >&2
        echo "       Drop it deliberately before recloning:" >&2
        echo "         sudo -u postgres dropdb $SCRATCH" >&2
        echo "       Not dropped automatically: a rerun that silently discards" >&2
        echo "       the previous run's evidence is how a finding disappears." >&2
        return 2
    fi

    mkdir -p "$WORKDIR" && chmod 755 "$WORKDIR" || return 2
    local dump="$WORKDIR/discovery_$(date -u +%Y%m%dT%H%M%SZ).dump"

    # Same owner as production, so the restored grants land on a role that can
    # actually hold them and the scratch permission structure mirrors the real
    # one rather than being flattened to postgres.
    local owner
    owner=$(sudo -u postgres psql -tAc \
        "SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname='$PROD';")
    echo "owner: $owner"

    sudo -u postgres createdb -O "$owner" "$SCRATCH" || return 2

    # TimescaleDB: three hypertables are in the pipeline's dependency set
    # (market.daily_metrics, market.daily_prices, market.computed_metrics).
    # Restoring them without the pre/post wrapper produces a database that
    # looks populated while its chunk structure is wrong -- which would read
    # as data findings and poison the entire run.
    sudo -u postgres psql -q -d "$SCRATCH" -c \
        "CREATE EXTENSION IF NOT EXISTS timescaledb;" || return 2
    sudo -u postgres psql -q -d "$SCRATCH" -c "SELECT timescaledb_pre_restore();" || return 2

    # Redirect as root rather than -f: pg_dump runs as postgres and cannot
    # write into a root-owned directory. That failure has been hit before.
    echo "dumping $PROD (excluding eod_prices, price_predictions)…"
    sudo -u postgres pg_dump -d "$PROD" -Fc "${EXCLUDE[@]}" > "$dump" || return 2
    chmod 644 "$dump"
    ls -lh "$dump"

    echo "restoring into $SCRATCH…"
    # pg_restore's exit status is non-zero for warnings as well as errors, so
    # it is reported but not treated as fatal on its own -- the row-count
    # verification below is what decides whether the clone is usable.
    sudo -u postgres pg_restore -d "$SCRATCH" -j2 "$dump"
    echo "pg_restore exit: $? (verification below is the real test)"

    sudo -u postgres psql -q -d "$SCRATCH" -c "SELECT timescaledb_post_restore();" || return 2

    # PUBLIC keeps CONNECT on a new database by default. The application role
    # must retain it -- the stages run as that role -- so this removes only the
    # blanket grant, not the one the run needs.
    sudo -u postgres psql -q -d "$SCRATCH" -c \
        "REVOKE CONNECT ON DATABASE $SCRATCH FROM PUBLIC;" || return 2

    sudo -u postgres psql -q -d "$SCRATCH" -c \
        "COMMENT ON DATABASE $SCRATCH IS
         'P0-A discovery run. Publication disabled: no application connection
          string names this database. Not authoritative, not backed up, safe
          to drop.';" || return 2

    echo "clone complete"
}

# ── verify ────────────────────────────────────────────────────────────────────

do_verify() {
    echo "=== verify: row counts, scratch vs production ==="
    # A short table in the scratch clone does not announce itself. It produces
    # a company with no financials, which the discovery run reports as reduced
    # coverage -- indistinguishable from a real V2 withdrawal, and far more
    # damaging than a failed clone, because it is believed.
    "$PYBIN" - "$PROD" "$SCRATCH" <<'PY'
import subprocess, sys

prod, scratch = sys.argv[1], sys.argv[2]

def counts(db):
    sql = """
    SELECT n.nspname||'.'||c.relname, c.reltuples::bigint
      FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE c.relkind = 'r'
       AND n.nspname IN ('screener','market','financials','staging_au')
     ORDER BY 1;"""
    out = subprocess.run(["sudo", "-u", "postgres", "psql", "-tAF", "\t",
                          "-d", db, "-c", sql],
                         capture_output=True, text=True, check=True).stdout
    return {line.split("\t")[0]: int(line.split("\t")[1])
            for line in out.strip().splitlines() if "\t" in line}

# Exact counts, not reltuples estimates, for the tables the run actually reads.
# reltuples is fine for spotting a table that failed to restore at all; it is
# not fine for deciding the clone is faithful.
CRITICAL = [
    "financials.annual_pnl", "financials.annual_balance_sheet",
    "financials.annual_cashflow", "financials.earnings_quarterly",
    "market.companies", "market.companies_current", "market.daily_prices",
    "market.dividends", "market.yearly_metrics", "market.computed_metrics",
    "market.daily_metrics", "market.valuation_snapshot",
    "market.halfyearly_metrics", "market.weekly_metrics",
    "market.short_positions", "market.analyst_ratings",
    "staging_au.shares_stats", "staging_au.company_profile",
    "screener.universe",
]

def exact(db, table):
    out = subprocess.run(["sudo", "-u", "postgres", "psql", "-tA",
                          "-d", db, "-c", f"SELECT count(*) FROM {table};"],
                         capture_output=True, text=True)
    return int(out.stdout.strip()) if out.returncode == 0 else None

p, s = counts(prod), counts(scratch)
missing = sorted(set(p) - set(s))
if missing:
    print(f"  TABLES ABSENT FROM SCRATCH: {missing}")

bad = False
for table in CRITICAL:
    a, b = exact(prod, table), exact(scratch, table)
    if a is None or b is None:
        print(f"  {table:38} UNREADABLE prod={a} scratch={b}")
        bad = True
        continue
    # screener.universe is expected to differ after the run; before it, equal.
    flag = "ok" if a == b else "MISMATCH"
    if a != b:
        bad = True
    print(f"  {table:38} prod={a:>9}  scratch={b:>9}  {flag}")

if missing:
    bad = True
print("\nclone faithful" if not bad else "\nCLONE NOT FAITHFUL — do not run")
sys.exit(1 if bad else 0)
PY
}

# ── run ───────────────────────────────────────────────────────────────────────

do_run() {
    echo "=== run: five stages against $SCRATCH ==="

    local url_sync url_async
    url_sync=$(scratch_url "$DATABASE_URL_SYNC") || return 2
    url_async=$(scratch_url "$DATABASE_URL") || return 2

    # load_dotenv() defaults to override=False, so an exported variable beats
    # .env. That is the mechanism -- but it is a property of a library default,
    # so it is verified rather than assumed, through the same resolver the
    # stages use, before a single row is written.
    local reached
    reached=$(DATABASE_URL_SYNC="$url_sync" DATABASE_URL="$url_async" "$PYBIN" -c "
import psycopg2
from app.core.db import get_database_url_sync
conn = psycopg2.connect(get_database_url_sync())
cur = conn.cursor(); cur.execute('SELECT current_database()')
print(cur.fetchone()[0])" 2>&1 | tail -1)

    echo "stages will write to: $reached"
    if [ "$reached" != "$SCRATCH" ]; then
        echo "REFUSING: the resolver reached '$reached', not '$SCRATCH'." >&2
        echo "          .env is winning over the environment. Nothing has run." >&2
        return 2
    fi

    local -a STAGES=(
        "compute/engine/daily_compute.py"
        "compute/engine/yearly_compute.py"
        "scripts/eodhd/v2/build_screener_universe.py"
        "compute/engine/composite_score.py"
        "compute/engine/sector_benchmarks.py"
    )

    for stage in "${STAGES[@]}"; do
        echo
        echo "--- $stage"
        local t0=$SECONDS
        if DATABASE_URL_SYNC="$url_sync" DATABASE_URL="$url_async" \
               "$PYBIN" "$stage"; then
            echo "--- $stage OK ($((SECONDS - t0))s)"
        else
            local rc=$?
            echo "--- $stage FAILED rc=$rc after $((SECONDS - t0))s" >&2
            echo "    Stopping: later stages read what this one writes, so" >&2
            echo "    continuing would produce evidence about a partial run." >&2
            return $rc
        fi
    done
    echo
    echo "all stages complete"
}

# ── evidence ──────────────────────────────────────────────────────────────────

do_evidence() {
    echo "=== evidence bundle ==="
    local url_sync
    url_sync=$(scratch_url "$DATABASE_URL_SYNC") || return 2
    DATABASE_URL_SYNC="$url_sync" "$PYBIN" scripts/p0a_discovery_evidence.py
}

# ── dispatch ──────────────────────────────────────────────────────────────────

case "${1:-all}" in
    clone)    do_clone ;;
    verify)   do_verify ;;
    run)      do_run ;;
    evidence) do_evidence ;;
    all)      do_clone && do_verify && do_run && do_evidence ;;
    *)        echo "usage: $0 {clone|verify|run|evidence|all}" >&2; exit 2 ;;
esac
rc=$?

echo
echo "p0a_discovery ${1:-all}: $([ $rc -eq 0 ] && echo PASS || echo FAIL) (rc=$rc)"
exit $rc
