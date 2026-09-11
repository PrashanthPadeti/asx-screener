#!/usr/bin/env bash
#
# Gate A runner — unit suite, containment gate, then schema evidence.
#
# Lives in the repo rather than being pasted, because a long heredoc through a
# wrapped console has twice produced a corrupted or wrong-tree run. Run it from
# the backend/ directory of a checkout at the commit you intend to prove:
#
#     cd /tmp/p0a-gate/backend && bash scripts/gate_a.sh 2>&1 | tee /tmp/gate.log
#
# The evidence queries always run, even when the gate fails, because what the
# storage schema holds is what decides the post-migration work either way.
# Exits with the gate's status so it is executable truth, not a report.

set -u

ASX_ROOT=${ASX_ROOT:-/opt/asx-screener}
PYBIN=${PYBIN:-$ASX_ROOT/asx-venv/bin/python}

# This gate is specific to the ASX screener. It has been pointed at the wrong
# host once; failing here is cheaper than a confusing run somewhere else.
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

# psql as the postgres superuser connects to the "postgres" database by
# default, where screener.universe does not exist — which reports every column
# as absent rather than saying it looked in the wrong place. Take the database
# name from the same DATABASE_URL the app uses.
DBNAME=$("$PYBIN" -c "
import os, urllib.parse as u
print(u.urlparse(os.environ['DATABASE_URL']).path.lstrip('/'))" 2>/dev/null)
if [ -z "${DBNAME:-}" ]; then
    echo "ERROR: could not read the database name from DATABASE_URL" >&2
    exit 2
fi

PSQL="sudo -u postgres psql -d $DBNAME"

# Identity of both things under test, printed before anything is proven. A
# previous run reported every governed column as absent because psql had
# connected to the default "postgres" database; the evidence looked like a
# storage contract mismatch rather than a harness fault. Naming the database
# the connection actually reached makes that failure self-announcing.
IDENT=$($PSQL -tAc "SELECT current_database() || ' @ ' ||
                           coalesce(host(inet_server_addr()), 'local socket') ||
                           ':' || coalesce(inet_server_port()::text, '-');" 2>&1)

echo "HOST:                $(hostname)"
echo "DATABASE UNDER TEST: $IDENT"
echo "HEAD UNDER TEST:     $(git log --oneline -1 2>/dev/null || echo 'not a checkout')"

# Schema existence is a prerequisite, not a finding. Continuing without it
# yields empty evidence that reads as "these columns do not exist" when the
# truth is that nothing was looked at.
if [ "$($PSQL -tAc "SELECT to_regclass('screener.universe') IS NOT NULL;" 2>/dev/null)" != "t" ]; then
    echo "ERROR: screener.universe not visible in $DBNAME — aborting rather" >&2
    echo "       than reporting misleading empty evidence." >&2
    exit 2
fi

echo
echo "=== unit suite ==="
suite_failed=0
for t in tests/test_*.py; do
    printf '%-48s' "$(basename "$t")"
    if "$PYBIN" "$t" >/tmp/gate-unit.log 2>&1; then
        tail -1 /tmp/gate-unit.log
    else
        suite_failed=1
        echo "FAIL"
        grep -E "^  (FAIL|ERROR)" /tmp/gate-unit.log || tail -8 /tmp/gate-unit.log
    fi
done

echo
echo "=== GATE A: pre-migration containment ==="
"$PYBIN" scripts/gate_a.py
gate=$?

#: The governed fields ScreenerRow advertises that no endpoint currently
#: selects. Gate A found them arriving null with no cause.
SUSPECT="('net_debt_to_ebitda'),('working_capital'),('interest_coverage'),
         ('asset_turnover'),('roic'),('composite_score'),('value_score'),
         ('quality_score'),('growth_score'),('momentum_score'),('income_score')"

echo
echo "=== do the unselected governed columns exist? ==="
# Reported per column, so an absent one says ABSENT rather than simply not
# appearing in a list. Silence and absence must not look the same in evidence
# that decides whether the fix is a SELECT, a migration, or a writer change.
$PSQL -c "
    SELECT v.name,
           CASE WHEN c.column_name IS NULL THEN 'ABSENT' ELSE 'present' END
               AS status
      FROM (VALUES $SUSPECT) AS v(name)
      LEFT JOIN information_schema.columns c
             ON c.table_schema = 'screener'
            AND c.table_name   = 'universe'
            AND c.column_name  = v.name
     ORDER BY 2, 1;"

echo
echo "=== populated? (active rows) ==="
# Built from the columns that actually exist. Naming them literally would make
# one absent column error the whole query out, losing the counts for the ten
# that are there — and "exists but never written" is the distinction Gate B
# depends on.
COUNTS=$($PSQL -tAc "
    SELECT string_agg(format('count(%I) AS %I', c.column_name, c.column_name),
                      ', ' ORDER BY c.column_name)
      FROM (VALUES $SUSPECT) AS v(name)
      JOIN information_schema.columns c
             ON c.table_schema = 'screener'
            AND c.table_name   = 'universe'
            AND c.column_name  = v.name;")

if [ -n "${COUNTS:-}" ]; then
    $PSQL -x -c \
        "SELECT count(*) AS rows, $COUNTS
           FROM screener.universe WHERE status='active';"
else
    echo "none of the suspect columns exist on screener.universe"
fi

echo "=== governed metrics not exposed on ScreenerRow ==="
"$PYBIN" - <<'PY'
from compute.engine.metric_states import GOVERNED_METRICS, LATEST_MODEL_VERSION
from compute.engine.universe_writer import column_for
from app.schemas.screener import ScreenerRow

columns = {column_for(m) for m in GOVERNED_METRICS[LATEST_MODEL_VERSION]}
print(sorted(columns - set(ScreenerRow.model_fields)))
PY

echo
echo "unit suite:  $([ $suite_failed -eq 0 ] && echo PASS || echo FAIL)"
echo "gate A exit: $gate"
exit $gate
