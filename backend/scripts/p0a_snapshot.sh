#!/usr/bin/env bash
#
# Pre-migration snapshot for the P0-A rollout.
#
# Captures what would be needed to reconstruct the current state, taken before
# the first state-changing step. Run it from the backend/ directory:
#
#     bash scripts/p0a_snapshot.sh
#
# It writes to /var/backups/p0a/<UTC timestamp>/ and prints the path. Nothing
# is modified; the script is safe to run more than once.
#
# Why a real dump rather than "we can always recompute":
#
# The recompute is the destructive step, and its failure mode is partial. If it
# stops halfway, screener.universe holds a mixture of old and new rows and the
# old values are the only evidence of what the previous contract produced —
# including the ones P0-A exists to correct, such as CBA's ev_to_ebitda = 0.0.
# "We can recompute it" assumes the recompute works, which is precisely the
# assumption under test.
#
# A custom-format dump is used because it restores selectively: one table can
# be brought back with pg_restore -t without touching the rest.

set -u

ASX_ROOT=${ASX_ROOT:-/opt/asx-screener}
PYBIN=${PYBIN:-$ASX_ROOT/asx-venv/bin/python}
OUT_ROOT=${OUT_ROOT:-/var/backups/p0a}

if [ ! -x "$PYBIN" ]; then
    echo "ERROR: $PYBIN not found — is this the ASX screener host?" >&2
    echo "       hostname: $(hostname)" >&2
    exit 2
fi
if [ ! -f "$ASX_ROOT/backend/.env" ]; then
    echo "ERROR: $ASX_ROOT/backend/.env not found" >&2
    exit 2
fi

set -a; . "$ASX_ROOT/backend/.env"; set +a

DBNAME=$("$PYBIN" -c "
import os, urllib.parse as u
print(u.urlparse(os.environ['DATABASE_URL']).path.lstrip('/'))" 2>/dev/null)
if [ -z "${DBNAME:-}" ]; then
    echo "ERROR: could not read the database name from DATABASE_URL" >&2
    exit 2
fi

STAMP=$(date -u +%Y%m%dT%H%M%SZ)
OUT="$OUT_ROOT/$STAMP"
mkdir -p "$OUT" || exit 2
chmod 700 "$OUT"

PSQL="sudo -u postgres psql -d $DBNAME"

echo "snapshot -> $OUT"
echo

# ── Identity ────────────────────────────────────────────────────────────────
# Which code and which database, recorded together. A snapshot that cannot say
# what it is a snapshot of is an artefact, not evidence.
{
    echo "taken_at_utc:  $STAMP"
    echo "hostname:      $(hostname)"
    echo "database:      $DBNAME"
    echo "app_root:      $ASX_ROOT"
    echo
    echo "--- application revision (deployed tree) ---"
    git -C "$ASX_ROOT" log --oneline -1 2>/dev/null || echo "not a git checkout"
    git -C "$ASX_ROOT" status --short 2>/dev/null | head -20
    echo
    echo "--- server ---"
    $PSQL -tAc "SELECT current_database() || ' | ' || version();" 2>&1
} > "$OUT/identity.txt"
cat "$OUT/identity.txt"

# ── Migration state ─────────────────────────────────────────────────────────
# Whether the P0-A objects already exist, so a re-run after a partial apply is
# interpretable rather than ambiguous.
$PSQL -c "
    SELECT 'column' AS kind,
           table_schema || '.' || table_name || '.' || column_name AS object
      FROM information_schema.columns
     WHERE (table_schema, table_name, column_name) IN (
           ('screener','universe','metric_states'),
           ('screener','universe','compute_run_id'),
           ('market','sector_benchmarks','benchmark_states'),
           ('market','sector_benchmarks','compute_run_id'))
     UNION ALL
    SELECT 'table', table_schema || '.' || table_name
      FROM information_schema.tables
     WHERE table_schema='screener' AND table_name='compute_runs'
     ORDER BY 1, 2;" > "$OUT/migration_state.txt" 2>&1
echo; echo "--- P0-A objects already present ---"; cat "$OUT/migration_state.txt"

# ── Counts and freshness ────────────────────────────────────────────────────
# The numbers a post-recompute comparison is made against. Row counts alone
# would not show a recompute that wrote every row with the same shape and
# different values, so the governed-column populations are included.
$PSQL -x -c "
    SELECT count(*)                     AS universe_rows,
           count(*) FILTER (WHERE status='active') AS active_rows,
           max(universe_built_at)       AS last_built,
           max(price_date)              AS last_price_date,
           count(roe)                   AS roe_n,
           count(ev_to_ebitda)          AS ev_to_ebitda_n,
           count(current_ratio)         AS current_ratio_n,
           count(debt_to_equity)        AS debt_to_equity_n,
           count(grossed_up_yield)      AS grossed_up_yield_n,
           count(composite_score)       AS composite_score_n
      FROM screener.universe;" > "$OUT/counts.txt" 2>&1
$PSQL -x -c "
    SELECT count(*) AS benchmark_rows, max(as_of) AS last_as_of
      FROM market.sector_benchmarks;" >> "$OUT/counts.txt" 2>&1

# The specific values P0-A exists to correct, recorded before they change, so
# the fix can be demonstrated rather than asserted.
$PSQL -c "
    SELECT asx_code, ev_to_ebitda, current_ratio, debt_to_equity,
           grossed_up_yield, franking_pct
      FROM screener.universe
     WHERE asx_code IN ('CBA','NAB','WBC','ANZ','MQG','BHP')
     ORDER BY asx_code;" > "$OUT/before_values.txt" 2>&1

echo; echo "--- counts ---"; cat "$OUT/counts.txt"
echo "--- values P0-A will change ---"; cat "$OUT/before_values.txt"

# ── The dump ────────────────────────────────────────────────────────────────
# screener.compute_runs is included only if it exists, so a first run and a
# re-run after a partial apply both work.
TABLES="-t screener.universe -t market.sector_benchmarks"
if [ "$($PSQL -tAc "SELECT to_regclass('screener.compute_runs') IS NOT NULL;")" = "t" ]; then
    TABLES="$TABLES -t screener.compute_runs"
    echo; echo "compute_runs exists — included in the dump"
fi

echo; echo "dumping $TABLES ..."
# shellcheck disable=SC2086
if sudo -u postgres pg_dump -d "$DBNAME" -Fc $TABLES -f "$OUT/p0a_pre_migration.dump" 2>"$OUT/dump.err"; then
    ls -lh "$OUT/p0a_pre_migration.dump"
else
    echo "ERROR: pg_dump failed — DO NOT PROCEED WITH THE MIGRATION" >&2
    cat "$OUT/dump.err" >&2
    exit 3
fi

# A dump that cannot be listed cannot be restored. Checking now is worth more
# than discovering it during an incident.
if ! sudo -u postgres pg_restore -l "$OUT/p0a_pre_migration.dump" > "$OUT/dump_toc.txt" 2>&1; then
    echo "ERROR: the dump is not readable by pg_restore" >&2
    exit 3
fi

cp migrations/add_metric_states_to_universe.sql \
   migrations/add_benchmark_states_to_sector_benchmarks.sql \
   migrations/rollback_p0a_applicability.sql "$OUT/" 2>/dev/null

echo
echo "=== snapshot complete ==="
echo "path:    $OUT"
echo "restore: sudo -u postgres pg_restore -d $DBNAME -t screener.universe \\"
echo "             --data-only --disable-triggers $OUT/p0a_pre_migration.dump"
echo
echo "Verified: dump written and readable by pg_restore."
echo "The rollback SQL and both migrations are copied alongside it, so the"
echo "snapshot carries the means to undo what follows it."
