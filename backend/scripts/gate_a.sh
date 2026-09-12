#!/usr/bin/env bash
#
# Gate A runner — unit suite, containment gate, then schema evidence.
#
# Lives in the repo rather than being pasted, because a long heredoc through a
# wrapped console has twice produced a corrupted or wrong-tree run.
#
# Run it from anywhere: it anchors on its own location, not on the caller's
# working directory. It used to require being run from backend/, and invoked
# from the repo root it reported "can't open file 'tests/test_*.py'" and
# "can't open file 'scripts/gate_a.py'" — a gate whose result depends on where
# you were standing when you ran it is not a gate.
#
# Note the subshell and pipefail: a bare `... | tee log` returns tee's status,
# so a failing gate would report success. The subshell also keeps pipefail out
# of the calling shell, and avoids `exit`, which would end an interactive
# session rather than the run.
#
#     ( set -o pipefail; bash /opt/asx-screener/backend/scripts/gate_a.sh \
#       2>&1 | tee /tmp/gate.log ); echo "EXIT=$?"
#
# The evidence queries always run, even when the gate fails, because what the
# storage schema holds is what decides the post-migration work either way.
# Exits with the gate's status so it is executable truth, not a report.

set -u

# Anchor on the script, then work from backend/. Every relative path below —
# tests/, scripts/, and the import root for `compute.engine` — is relative to
# this and to nothing else.
HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
BACKEND=$(cd -- "$HERE/.." && pwd)
cd "$BACKEND" || { echo "ERROR: cannot enter $BACKEND" >&2; exit 2; }

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

# An unmatched glob expands to itself, so `for t in tests/test_*.py` would run
# python on the literal string and the suite's verdict would rest on that
# happening to be an error. Zero tests found is a harness failure and has to
# say so: a suite that runs nothing must never be able to report PASS.
shopt -s nullglob
TESTS=(tests/test_*.py)
shopt -u nullglob
if [ ${#TESTS[@]} -eq 0 ]; then
    echo "ERROR: no tests matched tests/test_*.py under $BACKEND" >&2
    exit 2
fi
echo "(${#TESTS[@]} test files)"

for t in "${TESTS[@]}"; do
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
echo "=== is every governed field ScreenerRow promises actually fetched? ==="
# The other direction of the same boundary, and the one that bites hardest.
#
# A governed field that ScreenerRow advertises and a SELECT omits does not
# come back blank inside a validated contract: project_row raises
# MissingProjectedColumn, because the projector cannot tell "the company has
# no value" from "the application never asked for one" and must not guess.
# So an omission here is a 500 on every row of every governed response.
#
# Checked for each model version, not just the latest, because the failure
# arrives precisely when a version widens the governed set: six horizon CAGRs
# (ebitda/fcf/bvps x 3y/5y) sat in the field catalogue and in no SELECT on any
# surface for as long as they were ungoverned, and became fatal the moment V2
# governed them. Reading the SELECTs by eye is how they stayed missed.
"$PYBIN" - <<'PY' || exit_fetch=1
import ast, pathlib, re, sys

from app.schemas.screener import ScreenerRow
from compute.engine.metric_states import GOVERNED_METRICS
from compute.engine.universe_writer import column_for

SURFACES = ("build_screener_sql", "batch_screener", "query_screener")

src = pathlib.Path("app/api/v1/routes/screener.py").read_text(encoding="utf-8")
tree = ast.parse(src)
fields = set(ScreenerRow.model_fields)

bodies = {}
for node in ast.walk(tree):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        if node.name in SURFACES:
            bodies[node.name] = ast.get_source_segment(src, node) or ""

missing_any = False
for version in sorted(GOVERNED_METRICS):
    promised = sorted({column_for(m) for m in GOVERNED_METRICS[version]} & fields)
    for surface in SURFACES:
        body = bodies.get(surface)
        if body is None:
            print(f"  {version:18} {surface:20} SURFACE NOT FOUND")
            missing_any = True
            continue
        gaps = [c for c in promised
                if not re.search(rf"\bu\.{c}\b", body)]
        status = "ok" if not gaps else f"MISSING {gaps}"
        print(f"  {version:18} {surface:20} "
              f"{len(promised) - len(gaps):3}/{len(promised):<3} {status}")
        if gaps:
            missing_any = True

sys.exit(1 if missing_any else 0)
PY
exit_fetch=${exit_fetch:-0}

echo
echo "unit suite:     $([ $suite_failed -eq 0 ] && echo PASS || echo FAIL)"
echo "promised/fetch: $([ "$exit_fetch" -eq 0 ] && echo PASS || echo FAIL)"
echo "gate A exit:    $gate"

# Every check that can fail contributes to the status, or the ones that do not
# are decoration. The gate used to exit on $gate alone, so the unit suite could
# report FAIL in the body while the command returned 0 — which is the shape of
# failure this script exists to remove.
rc=$gate
[ $suite_failed -eq 0 ] || rc=1
[ "$exit_fetch" -eq 0 ] || rc=1
exit $rc
