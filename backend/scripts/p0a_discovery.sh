#!/usr/bin/env bash
#
# Targeted V2 discovery rebuild — the changed pipeline, against a database it
# cannot publish from
# =====================================================================
# A discovery run with publication disabled. It answers **do the changed
# contracts compose?** It does not answer "does the whole production sequence
# compose?" — that is a later, production-shaped rehearsal, immediately before
# the real canonical recompute, and it is a different gate.
#
# The name matters and is used throughout: this is a TARGETED V2 DISCOVERY
# REBUILD, not a full canonical rebuild. Technical, weekly, monthly and period
# products are cloned and held constant, deliberately, so that every
# difference observed is attributable to the code that changed rather than to
# unrelated recomputation. The consequence is that a result from this run must
# never later be described as proving full same-run coherence, and the
# evidence bundle prints the recomputed/held-constant manifest so that claim
# cannot be made by accident.
#
# Why a separate DATABASE and not a scratch SCHEMA. Every write path is
# hardcoded to schema-qualified names, so a scratch schema means threading a
# schema parameter through three scripts — and a parameter that can be set to
# screener_scratch can be set back to screener. The isolation would rest on a
# flag. A separate database needs no code change at all.
#
# Isolation, stated exactly:
#   - the scratch data lives in a database no configured DATABASE_URL names
#   - this script refuses to target the production database by name
#   - the connection is asked which database it reached, immediately before
#     EVERY stage, not once at startup
#   - a production sentinel is captured before the run and compared after, so
#     a stage that escaped the redirect is detected even if every check above
#     passed
# Optionally (see `role`), a dedicated scratch role that cannot CONNECT to
# production turns the refusal into a database-enforced property. Running the
# stages as `postgres` is deliberately NOT offered: raising privilege to
# improve isolation is a worse trade than the differing database name already
# provides.
#
# Usage:
#   p0a_discovery.sh clone      create + load the scratch database
#   p0a_discovery.sh verify     counts, hypertable shape, restore errors
#   p0a_discovery.sh role       report on (and create) a scratch-only role
#   p0a_discovery.sh preflight  the acceptance boundary, + sentinel capture
#   p0a_discovery.sh run        the canonical driver, scratch only
#   p0a_discovery.sh sentinel   re-compare the production sentinel
#   p0a_discovery.sh evidence   the evidence bundle
#   p0a_discovery.sh all        clone, verify, preflight, run, sentinel, evidence

set -u

HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
BACKEND=$(cd -- "$HERE/.." && pwd)
cd "$BACKEND" || { echo "ERROR: cannot enter $BACKEND" >&2; exit 2; }

ASX_ROOT=${ASX_ROOT:-/opt/asx-screener}
PYBIN=${PYBIN:-$ASX_ROOT/asx-venv/bin/python}
SCRATCH=${SCRATCH_DB:-asx_screener_scratch}
WORKDIR=${WORKDIR:-/var/backups/p0a/discovery}
ALLOWLIST="$HERE/p0a_restore_allowlist.txt"
RESTORE_LOG="$WORKDIR/restore.err"
SENTINEL="$WORKDIR/production_sentinel.txt"
#: Written only when preflight passes, and read by `run`. The sentinel file is
#: written either way -- capturing production's state is useful even on a
#: failed preflight -- so its existence cannot stand for acceptance.
PREFLIGHT_OK="$WORKDIR/preflight.ok"

#: Read by no pipeline stage — derived from the code, not assumed. Between
#: them 1.7GB of the 7.4GB database.
EXCLUDE=(-T staging_au.eod_prices -T market.price_predictions)

#: The hypertables in the pipeline's dependency set. Row counts alone cannot
#: tell a faithful restore from one with the right number of rows and the
#: wrong temporal or key shape, or one that lost its Timescale identity.
HYPERTABLES=(market.daily_prices market.daily_metrics market.computed_metrics)

[ -x "$PYBIN" ] || { echo "ERROR: $PYBIN not found — wrong host?" >&2; exit 2; }
[ -f "$BACKEND/.env" ] || { echo "ERROR: $BACKEND/.env not found" >&2; exit 2; }

set -a; . "$BACKEND/.env"; set +a

PROD=$("$PYBIN" -c "
import os, urllib.parse as u
print(u.urlparse(os.environ['DATABASE_URL']).path.lstrip('/'))" 2>/dev/null)
[ -n "${PROD:-}" ] || { echo "ERROR: cannot read database name from DATABASE_URL" >&2; exit 2; }

if [ "$SCRATCH" = "$PROD" ]; then
    echo "REFUSING: scratch database resolves to production ($PROD)." >&2
    exit 2
fi

PSQL_PROD="sudo -u postgres psql -X -tA -d $PROD"
PSQL_SCRATCH="sudo -u postgres psql -X -tA -d $SCRATCH"

scratch_url() {
    "$PYBIN" - "$1" "$SCRATCH" <<'PY'
import sys, urllib.parse as u
parsed = u.urlparse(sys.argv[1])
print(u.urlunparse(parsed._replace(path="/" + sys.argv[2])))
PY
}

#: Ask the connection which database it reached, through the same resolver the
#: stages use. Printed before every stage, because the whole history of P0-A
#: says a runtime observation beats an assumption about inheritance.
observed_db() {
    DATABASE_URL_SYNC="$1" "$PYBIN" -c "
import psycopg2
from app.core.db import get_database_url_sync
c = psycopg2.connect(get_database_url_sync())
cur = c.cursor(); cur.execute('SELECT current_database()')
print(cur.fetchone()[0])" 2>&1 | tail -1
}

echo "run type:   TARGETED V2 DISCOVERY REBUILD (publication disabled)"
echo "host:       $(hostname)"
echo "production: $PROD  (read-only here, never written)"
echo "scratch:    $SCRATCH"
echo "revision:   $(git log --oneline -1 2>/dev/null || echo 'not a checkout')"
echo

# ── clone ─────────────────────────────────────────────────────────────────────

do_clone() {
    echo "=== clone ==="
    if [ "$($PSQL_PROD -c "SELECT 1 FROM pg_database WHERE datname='$SCRATCH';")" = "1" ]; then
        echo "ERROR: $SCRATCH already exists." >&2
        echo "       Drop it deliberately before recloning:" >&2
        echo "         sudo -u postgres dropdb $SCRATCH" >&2
        echo "       Not dropped automatically: a rerun that silently discards" >&2
        echo "       the previous run's evidence is how a finding disappears." >&2
        return 2
    fi

    mkdir -p "$WORKDIR" && chmod 755 "$WORKDIR" || return 2
    local dump="$WORKDIR/discovery_$(date -u +%Y%m%dT%H%M%SZ).dump"

    local owner
    owner=$($PSQL_PROD -c \
        "SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname='$PROD';")
    echo "owner: $owner"

    sudo -u postgres createdb -O "$owner" "$SCRATCH" || return 2
    sudo -u postgres psql -X -q -d "$SCRATCH" -c \
        "CREATE EXTENSION IF NOT EXISTS timescaledb;" || return 2

    # Without the pre/post wrapper the clone looks populated while its chunk
    # structure is wrong — which would read as data findings and poison the
    # entire run.
    sudo -u postgres psql -X -q -d "$SCRATCH" -c \
        "SELECT timescaledb_pre_restore();" || return 2

    # Redirect as root rather than -f: pg_dump runs as postgres and cannot
    # write into a root-owned directory. That failure has been hit before.
    echo "dumping $PROD (excluding eod_prices, price_predictions)…"
    sudo -u postgres pg_dump -d "$PROD" -Fc "${EXCLUDE[@]}" > "$dump" || return 2
    chmod 644 "$dump"
    ls -lh "$dump"

    echo "restoring into $SCRATCH… (single-threaded — see note)"
    # stderr is kept, not discarded. It is the only record of an index,
    # constraint, function or Timescale metadata object that failed while
    # every table row arrived — the class of failure row counts cannot see.
    #
    # NOT parallel. -j reorders the restore, and _timescaledb_catalog tables
    # carry foreign keys between them: dimension -> hypertable,
    # dimension_slice -> chunk, compression_chunk_size -> chunk. A parallel
    # restore loaded the children first and every one of those COPYs failed,
    # which left all three hypertables as plain tables with zero chunks --
    # while every user-table row count matched exactly. That is the whole
    # reason restore stderr is not allowed to be ignored.
    sudo -u postgres pg_restore -d "$SCRATCH" "$dump" 2> "$RESTORE_LOG"
    local restore_rc=$?
    chmod 644 "$RESTORE_LOG" 2>/dev/null
    echo "pg_restore exit: $restore_rc  (stderr -> $RESTORE_LOG)"

    # Fatal regardless of anything else. A failed post-restore leaves
    # Timescale in its restoring state, and every later reading of that
    # database is of an object in a mode it should not be in.
    echo "running timescaledb_post_restore()…"
    local post
    post=$(sudo -u postgres psql -X -tA -d "$SCRATCH" \
             -c "SELECT timescaledb_post_restore();" 2>&1)
    if [ "$post" != "t" ]; then
        echo "FATAL: timescaledb_post_restore() did not return true: $post" >&2
        echo "       Row counts are irrelevant to this. The clone is unusable." >&2
        return 2
    fi
    echo "timescaledb_post_restore: t"

    sudo -u postgres psql -X -q -d "$SCRATCH" -c \
        "REVOKE CONNECT ON DATABASE $SCRATCH FROM PUBLIC;" || return 2
    sudo -u postgres psql -X -q -d "$SCRATCH" -c \
        "COMMENT ON DATABASE $SCRATCH IS
         'Targeted V2 discovery rebuild. Publication disabled: no application
          connection string names this database. Not authoritative, not backed
          up, safe to drop.';" || return 2

    echo "clone complete — acceptance is decided by 'verify', not by this step"
}

# ── verify ────────────────────────────────────────────────────────────────────

check_restore_errors() {
    echo "--- restore output"
    if [ ! -f "$RESTORE_LOG" ]; then
        echo "  no restore log at $RESTORE_LOG — clone not run here?" >&2
        return 1
    fi

    # Everything that looks like a failure, minus exactly what has been
    # allowlisted. An empty allowlist means every such line is unrecognised,
    # which is the correct starting state: a message is benign only once
    # somebody has looked at it and said so.
    local unrecognised
    unrecognised=$("$PYBIN" - "$RESTORE_LOG" "$ALLOWLIST" <<'PY'
import pathlib, sys

log = pathlib.Path(sys.argv[1]).read_text(errors="replace").splitlines()
allow = []
p = pathlib.Path(sys.argv[2])
if p.exists():
    allow = [ln.strip() for ln in p.read_text().splitlines()
             if ln.strip() and not ln.lstrip().startswith("#")]

SUSPECT = ("error", "fatal", "could not", "does not exist",
           "already exists", "permission denied", "warning")
out = []
for line in log:
    low = line.lower()
    if not any(token in low for token in SUSPECT):
        continue
    if any(entry in line for entry in allow):
        continue
    out.append(line)

for line in out:
    print(line)
sys.exit(1 if out else 0)
PY
)
    local rc=$?
    if [ $rc -eq 0 ]; then
        echo "  no unrecognised restore errors"
        return 0
    fi
    echo "  UNRECOGNISED RESTORE OUTPUT:" >&2
    echo "$unrecognised" | sed 's/^/    /' >&2
    echo "" >&2
    echo "  Row counts cannot see an index, constraint, function or Timescale" >&2
    echo "  metadata object that failed. Read these, and if any is genuinely" >&2
    echo "  harmless add its exact text to:" >&2
    echo "    $ALLOWLIST" >&2
    return 1
}

do_verify() {
    echo "=== verify ==="
    local bad=0

    check_restore_errors || bad=1

    echo
    echo "--- dependency table counts"
    "$PYBIN" - "$PROD" "$SCRATCH" <<'PY' || bad=1
import subprocess, sys

prod, scratch = sys.argv[1], sys.argv[2]

CRITICAL = [
    "financials.annual_pnl", "financials.annual_balance_sheet",
    "financials.annual_cashflow", "financials.earnings_quarterly",
    "market.companies", "market.companies_current", "market.daily_prices",
    "market.dividends", "market.yearly_metrics", "market.computed_metrics",
    "market.daily_metrics", "market.valuation_snapshot",
    "market.halfyearly_metrics", "market.weekly_metrics",
    "market.short_positions", "market.analyst_ratings",
    "staging_au.shares_stats", "staging_au.company_profile",
    "screener.universe", "market.sector_benchmarks",
]

def q(db, sql):
    """Value, or (None, reason). A bare None hid why market.daily_prices could
    not be counted -- which was the single most diagnostic fact available."""
    r = subprocess.run(["sudo", "-u", "postgres", "psql", "-X", "-tA",
                        "-d", db, "-c", sql], capture_output=True, text=True)
    if r.returncode == 0:
        return r.stdout.strip(), None
    reason = " ".join(r.stderr.split())[:160] or f"exit {r.returncode}"
    return None, reason

bad = False
for table in CRITICAL:
    (a, ea) = q(prod, f"SELECT count(*) FROM {table};")
    (b, eb) = q(scratch, f"SELECT count(*) FROM {table};")
    if a is None or b is None:
        print(f"  {table:38} UNREADABLE")
        if ea:
            print(f"    prod:    {ea}")
        if eb:
            print(f"    scratch: {eb}")
        bad = True
        continue
    same = a == b
    bad = bad or not same
    print(f"  {table:38} prod={int(a):>9,}  scratch={int(b):>9,}  "
          f"{'ok' if same else 'MISMATCH'}")

sys.exit(1 if bad else 0)
PY

    echo
    echo "--- hypertable shape and Timescale identity"
    # Not a checksum. The purpose is to catch a restore with the right number
    # of rows and the wrong temporal or key shape, or one that came back as a
    # plain table having lost its Timescale identity entirely.
    "$PYBIN" - "$PROD" "$SCRATCH" "${HYPERTABLES[@]}" <<'PY' || bad=1
import subprocess, sys

prod, scratch = sys.argv[1], sys.argv[2]
tables = sys.argv[3:]

def q(db, sql):
    r = subprocess.run(["sudo", "-u", "postgres", "psql", "-X", "-tA", "-F", "|",
                        "-d", db, "-c", sql], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None

def shape(db, schema, name):
    ident = q(db, f"""
        SELECT count(*) FROM timescaledb_information.hypertables
         WHERE hypertable_schema='{schema}' AND hypertable_name='{name}';""")
    chunks = q(db, f"""
        SELECT count(*) FROM timescaledb_information.chunks
         WHERE hypertable_schema='{schema}' AND hypertable_name='{name}';""")
    # The time column comes from Timescale's own metadata rather than being
    # guessed from a column name that might differ per table.
    tcol = q(db, f"""
        SELECT column_name FROM timescaledb_information.dimensions
         WHERE hypertable_schema='{schema}' AND hypertable_name='{name}'
         ORDER BY dimension_number LIMIT 1;""")
    bounds = key = None
    if tcol:
        bounds = q(db, f"SELECT min({tcol})||' .. '||max({tcol}) FROM {schema}.{name};")
    has_code = q(db, f"""
        SELECT count(*) FROM information_schema.columns
         WHERE table_schema='{schema}' AND table_name='{name}'
           AND column_name='asx_code';""")
    if has_code == "1":
        key = q(db, f"SELECT count(DISTINCT asx_code) FROM {schema}.{name};")
    return {"hypertable": ident, "chunks": chunks, "time_col": tcol,
            "bounds": bounds, "distinct_asx_code": key}

bad = False
for table in tables:
    schema, name = table.split(".", 1)
    a, b = shape(prod, schema, name), shape(scratch, schema, name)
    print(f"  {table}")
    if b["hypertable"] != "1":
        print(f"    NOT A HYPERTABLE IN SCRATCH (prod={a['hypertable']}, "
              f"scratch={b['hypertable']}) — Timescale identity lost")
        bad = True
    for field in ("hypertable", "chunks", "time_col", "bounds", "distinct_asx_code"):
        same = a[field] == b[field]
        bad = bad or not same
        mark = "ok" if same else "MISMATCH"
        print(f"    {field:18} prod={str(a[field]):<34} scratch={str(b[field]):<34} {mark}")

sys.exit(1 if bad else 0)
PY

    echo
    if [ $bad -eq 0 ]; then
        echo "CLONE ACCEPTED — data verified and no unrecognised restore error"
    else
        echo "CLONE NOT ACCEPTED — do not run" >&2
    fi
    return $bad
}

# ── role ──────────────────────────────────────────────────────────────────────

do_role() {
    echo "=== scratch-only role ==="
    # The cleanest extra guard is a role that CANNOT connect to production,
    # which turns "the harness refuses" into a database-enforced property.
    # Whether that is cheap depends on one fact about production, so it is
    # measured rather than assumed.
    local pub
    pub=$($PSQL_PROD -c "
        SELECT CASE WHEN datacl IS NULL THEN 'implicit-public'
                    WHEN array_to_string(datacl,',') LIKE '%=Tc/%' THEN 'public-connect'
                    ELSE 'restricted' END
          FROM pg_database WHERE datname='$PROD';")
    echo "  production CONNECT for PUBLIC: $pub"

    if [ "$pub" != "restricted" ]; then
        echo
        echo "  A scratch-only role CANNOT be delivered as a real guarantee here."
        echo "  PUBLIC holds CONNECT on $PROD, so any role — including a new"
        echo "  scratch one — can reach production. Making it real requires"
        echo "  REVOKE CONNECT ON DATABASE $PROD FROM PUBLIC, which is a"
        echo "  production permission change during a freeze, and would break"
        echo "  any role that reaches production through PUBLIC rather than"
        echo "  through its own grant."
        echo
        echo "  Not doing that now. Creating the role anyway would produce a"
        echo "  guard that looks database-enforced and is not, which is worse"
        echo "  than the honest position: isolation currently rests on the"
        echo "  differing database name, the pre-stage identity observation,"
        echo "  and the production sentinel."
        return 0
    fi

    echo "  PUBLIC has no CONNECT on production, so the role is a real guard."
    echo "  Create it with a password you supply, then re-run with"
    echo "  SCRATCH_ROLE_URL set to its connection string:"
    echo
    echo "    sudo -u postgres createuser --login --pwprompt asx_scratch"
    echo "    sudo -u postgres psql -d $SCRATCH \\"
    echo "      -c 'GRANT CONNECT ON DATABASE $SCRATCH TO asx_scratch;' \\"
    echo "      -c 'GRANT ALL ON ALL TABLES IN SCHEMA screener, market, financials, staging_au TO asx_scratch;'"
    echo
    echo "  Not created automatically: it needs a password, and a password"
    echo "  this script invented would have to be stored somewhere."
}

# ── preflight (the acceptance boundary) + sentinel ────────────────────────────

capture_sentinel() {
    $PSQL_PROD -F '|' -c "
        SELECT 'universe_rows',        count(*)::text FROM screener.universe
        UNION ALL SELECT 'universe_active',     count(*)::text FROM screener.universe WHERE status='active'
        UNION ALL SELECT 'universe_built_at',   coalesce(max(universe_built_at)::text,'-') FROM screener.universe
        UNION ALL SELECT 'universe_with_run',   count(compute_run_id)::text FROM screener.universe
        UNION ALL SELECT 'universe_sidecars',   count(metric_states)::text FROM screener.universe
        UNION ALL SELECT 'compute_runs_rows',   count(*)::text FROM screener.compute_runs
        UNION ALL SELECT 'benchmark_rows',      count(*)::text FROM market.sector_benchmarks
        UNION ALL SELECT 'yearly_metrics_rows', count(*)::text FROM market.yearly_metrics
        UNION ALL SELECT 'computed_metrics_rows', count(*)::text FROM market.computed_metrics
        UNION ALL SELECT 'fixture_rows_md5',    md5(string_agg(t,'|' ORDER BY t))
                    FROM (SELECT asx_code||':'||coalesce(ev_to_ebitda::text,'-')
                                 ||':'||coalesce(current_ratio::text,'-')
                                 ||':'||coalesce(debt_to_equity::text,'-')
                                 ||':'||coalesce(grossed_up_yield::text,'-') AS t
                            FROM screener.universe
                           WHERE asx_code IN ('ANZ','BHP','CBA','MQG','NAB','WBC')) f
        ORDER BY 1;"
}

do_preflight() {
    echo "=== preflight: acceptance boundary ==="
    local bad=0

    # 1. Writers still frozen — both authorities, by observation.
    local cron_live
    cron_live=$(crontab -l 2>/dev/null | grep -cE '^[^#[:space:]]')
    echo "  cron live entries:        $cron_live  $([ "$cron_live" -eq 0 ] && echo ok || echo 'NOT FROZEN')"
    [ "$cron_live" -eq 0 ] || bad=1

    local health
    health=$(curl -s --max-time 5 http://127.0.0.1:8000/health 2>/dev/null)
    local frozen jobs
    # The keys are nested under "schedulers", not at the top level:
    #   {"status":"ok",...,"schedulers":{"frozen":true,"jobs":0}}
    #
    # Read flat, both came back None and preflight reported NOT FROZEN while
    # the freeze was fully in force. A check that cannot read its input
    # reported the very condition it exists to detect -- and because it fails
    # closed, it looked like diligence. Failing closed is right; failing
    # closed for a reason that is not true is a false alarm that trains an
    # operator to run anyway, which is exactly what happened.
    #
    # Both shapes are accepted so an older build does not re-break this, and
    # an unreadable response still yields the literal "unreadable" rather than
    # a value that could pass a comparison.
    read -r frozen jobs <<EOF
$(printf '%s' "$health" | "$PYBIN" -c "
import json, sys
try:
    payload = json.load(sys.stdin)
except Exception:
    print('unreadable unreadable'); raise SystemExit
sched = payload.get('schedulers') or {}
print(sched.get('frozen', payload.get('frozen', 'absent')),
      sched.get('jobs', payload.get('jobs', 'absent')))" 2>/dev/null)
EOF
    echo "  in-process frozen:        $frozen"
    echo "  in-process jobs:          $jobs"
    if [ "$frozen" != "True" ] || [ "$jobs" != "0" ]; then
        echo "    NOT FROZEN — the scratch run must not share the window with a" >&2
        echo "    production writer, or a production change during the run is" >&2
        echo "    unattributable." >&2
        bad=1
    fi

    # 2. Scratch reachable and correctly identified through the real resolver.
    local url_sync reached
    url_sync=$(scratch_url "$DATABASE_URL_SYNC") || return 2
    reached=$(observed_db "$url_sync")
    echo "  resolver reaches:         $reached  $([ "$reached" = "$SCRATCH" ] && echo ok || echo WRONG)"
    [ "$reached" = "$SCRATCH" ] || bad=1

    # 3. Production sentinel. Writers are frozen, so production must be stable
    #    on these observables for the duration. Detection, not prevention —
    #    but cheap and highly diagnostic if a stage escapes the redirect.
    mkdir -p "$WORKDIR" && chmod 755 "$WORKDIR"
    capture_sentinel > "$SENTINEL" || return 2
    echo "  production sentinel:      captured -> $SENTINEL"
    sed 's/^/    /' "$SENTINEL"

    echo
    rm -f "$PREFLIGHT_OK"
    if [ $bad -eq 0 ]; then
        {
            git rev-parse HEAD 2>/dev/null || echo unknown
            date -u +%FT%TZ
        } > "$PREFLIGHT_OK"
        echo "PREFLIGHT PASSED — the acceptance boundary holds"
    else
        echo "PREFLIGHT FAILED — do not run" >&2
    fi
    return $bad
}

do_sentinel() {
    echo "=== production sentinel: re-compare ==="
    if [ ! -f "$SENTINEL" ]; then
        echo "ERROR: no sentinel at $SENTINEL — preflight was not run" >&2
        return 2
    fi
    local now="$WORKDIR/production_sentinel.after.txt"
    capture_sentinel > "$now" || return 2
    if diff -u "$SENTINEL" "$now" > /tmp/sentinel.diff 2>&1; then
        echo "  production unchanged across the run — no stage escaped the redirect"
        return 0
    fi
    echo "  PRODUCTION CHANGED DURING THE SCRATCH RUN:" >&2
    sed 's/^/    /' /tmp/sentinel.diff >&2
    echo "" >&2
    echo "  Writers are frozen, so nothing should have moved. This is evidence" >&2
    echo "  that a stage reached production. Treat the run's output as void." >&2
    return 1
}

# ── run ───────────────────────────────────────────────────────────────────────

do_run() {
    echo "=== run: the canonical driver against $SCRATCH ==="

    # The acceptance boundary is a gate, not advice.
    #
    # discovery-2 was started after preflight reported FAILED, because nothing
    # required it to have passed. The freeze check is the whole reason
    # preflight exists: a production writer active during the run makes any
    # production change unattributable, and the sentinel comparison afterwards
    # would then be measuring two things at once.
    if [ ! -f "$PREFLIGHT_OK" ]; then
        echo "REFUSING: no passing preflight. Run:" >&2
        echo "  $0 preflight" >&2
        return 2
    fi
    local marked current
    marked=$(head -1 "$PREFLIGHT_OK")
    current=$(git rev-parse HEAD 2>/dev/null)
    if [ -n "$current" ] && [ "$marked" != "$current" ]; then
        echo "REFUSING: preflight passed at $marked, the tree is now $current." >&2
        echo "          Re-run preflight against the code that will execute." >&2
        return 2
    fi
    echo "preflight: passed at $(tail -1 "$PREFLIGHT_OK") for $marked"

    echo "RECOMPUTED: computed_metrics, yearly_metrics, universe, factor scores,"
    echo "            sector_benchmarks"
    echo "HELD CONSTANT (cloned): daily_metrics, weekly, monthly, quarterly,"
    echo "            halfyearly, period_metrics, prices, dividends, financials"
    echo

    # Delegates to p0a_canonical_run.py rather than driving the stages itself.
    #
    # This used to invoke the five scripts directly with no run id, which is
    # precisely the second lifecycle the driver exists to prevent: a path that
    # computes everything and produces no attributable run, beside one that
    # does. Two ways to execute the pipeline is how an alternate publication
    # route grows back, and the resolver cannot tell them apart once rows
    # exist. The discovery run must exercise the SAME lifecycle production
    # will use, or it is not evidence about production.
    #
    # The driver owns ordering, stage requirements, the health precondition
    # and finalisation. Everything here does is point it at scratch and prove
    # it went there.
    local url_sync url_async reached
    url_sync=$(scratch_url "$DATABASE_URL_SYNC") || return 2
    url_async=$(scratch_url "$DATABASE_URL") || return 2

    reached=$(observed_db "$url_sync")
    echo "driver will run against: $reached"
    if [ "$reached" != "$SCRATCH" ]; then
        echo "REFUSING: resolver reached '$reached', not '$SCRATCH'." >&2
        return 2
    fi

    # Exported, not per-command: the driver spawns each stage as a subprocess
    # and they inherit this environment. The driver re-checks the database
    # identity before every stage regardless.
    DATABASE_URL_SYNC="$url_sync" DATABASE_URL="$url_async"         "$PYBIN" scripts/p0a_canonical_run.py --execute
    local rc=$?

    if [ $rc -ne 0 ]; then
        echo >&2
        echo "The canonical run did not publish (rc=$rc). Its run row and any" >&2
        echo "stage evidence remain in $SCRATCH as forensics; no finalisation" >&2
        echo "exists, so no resolver would select it. Read the stage evidence:" >&2
        echo "  SELECT stage_name, status, expected_count, written_count," >&2
        echo "         missing_count, extra_count, details" >&2
        echo "    FROM screener.compute_run_stages ORDER BY run_id, stage_name;" >&2
        return $rc
    fi
    echo
    echo "canonical run published"
}

# ── evidence ──────────────────────────────────────────────────────────────────

do_evidence() {
    echo "=== evidence bundle ==="
    local url_sync
    url_sync=$(scratch_url "$DATABASE_URL_SYNC") || return 2
    DISCOVERY_REV="$(git log --oneline -1 2>/dev/null)" \
        DATABASE_URL_SYNC="$url_sync" "$PYBIN" scripts/p0a_discovery_evidence.py
}

# ── dispatch ──────────────────────────────────────────────────────────────────

case "${1:-all}" in
    clone)     do_clone ;;
    verify)    do_verify ;;
    role)      do_role ;;
    preflight) do_preflight ;;
    run)       do_run ;;
    sentinel)  do_sentinel ;;
    evidence)  do_evidence ;;
    all)       do_clone && do_verify && do_preflight && do_run \
                        && do_sentinel && do_evidence ;;
    *) echo "usage: $0 {clone|verify|role|preflight|run|sentinel|evidence|all}" >&2
       exit 2 ;;
esac
rc=$?

echo
echo "p0a_discovery ${1:-all}: $([ $rc -eq 0 ] && echo PASS || echo FAIL) (rc=$rc)"
exit $rc
