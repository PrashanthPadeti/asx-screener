#!/usr/bin/env bash
#
# Full-suite release gate
# =======================
# Runs EVERY backend/tests/test_*.py at an exact commit, in a disposable
# checkout, against a disposable database carrying the real schema, with
# outbound network blocked -- then does the same at a baseline commit and
# attributes every failing TEST, not every failing file.
#
# Why this exists
# ---------------
# The v11.2.22 gate reported "13 suites all passing". There are 81. The
# thirteen were chosen by hand, and test_refusal_reaches_telemetry_end_to_end
# was not among them -- failing since v11.2.21, where ASX100 moved to EODHD
# and the test began making a live API call instead of the total refusal it
# asserts about. A gate that picks its own population cannot report what it
# did not look at, which is the defect the producers had.
#
# Four properties, each from a specific way an earlier gate was wrong
# -------------------------------------------------------------------
# 1. NO SUITE LIST. The population is the glob; the file count is reported
#    with the result.
#
# 2. PER-TEST ATTRIBUTION. An earlier version of this script compared sets of
#    FILENAMES. A file failing `test_a` at the candidate and `test_b` at the
#    baseline looked identical in both runs and was classified pre-existing --
#    a file-level verdict blind to which test inside it moved. That is the
#    same aggregation defect this release is about. Failures are now keyed
#    `file::test`.
#
# 3. A REAL SCHEMA. The scratch database was previously created empty, so
#    every DB-dependent suite failed for want of tables at both commits and
#    was reported pre-existing. Neither run exercised them; "it failed before
#    too" was a verdict about an environment, not about the code. The schema
#    now comes from a schema-only dump of production -- read-only, no rows.
#
# 4. INCONCLUSIVE IS NOT PRE-EXISTING. A suite that could not run -- no
#    database, no network, a missing dependency -- is reported INCONCLUSIVE
#    and never counted as a pass or as a pre-existing failure. Blocking the
#    network is what makes an unstubbed provider call fail loudly; it also
#    means tests that genuinely need the network did not run, and the gate
#    must say so rather than quietly absorbing them.
#
# The database is never production: credentials are reused with the database
# name replaced, the override is verified before anything runs, and the URL
# is never echoed.
#
# Usage:
#   sudo bash backend/scripts/gate_full_suite.sh <candidate-sha> [baseline-sha]
#
set -uo pipefail

CANDIDATE="${1:?usage: gate_full_suite.sh <candidate-sha> [baseline-sha]}"
BASELINE="${2:-}"

SRC="${SRC:-/opt/asx-screener}"
PY="${PY:-/opt/asx-screener/asx-venv/bin/python}"
PROD_DB="${PROD_DB:-asx_screener}"
WORK="$(mktemp -d /tmp/gate.XXXXXX)"
DB="asx_gate_$$"

cleanup() {
    sudo -u postgres dropdb --if-exists "$DB" >/dev/null 2>&1
    rm -rf "$WORK"
}
trap cleanup EXIT

echo "gate: work=$WORK  db=$DB"

# ── The gate must never be able to write to production ──────────────────────
# The .env symlinked below is the real one, so its DATABASE_URL is production,
# and a network namespace does not protect it: loopback is up and Postgres is
# local. Credentials are reused with the database name replaced, exported so
# they take precedence over the .env file. Never echoed -- it carries a
# password.
PROD_URL="$(grep -E '^DATABASE_URL=' "$SRC/backend/.env" 2>/dev/null \
            | head -1 | cut -d= -f2- | tr -d '"'"'"'')"
if [ -z "$PROD_URL" ]; then
    echo "gate: no DATABASE_URL in $SRC/backend/.env -- refusing to run"
    exit 2
fi
DB_OWNER="$(printf '%s' "$PROD_URL" | sed -E 's|^[^:]+://([^:/]+).*|\1|')"
export DATABASE_URL="${PROD_URL%/*}/$DB"

# Inside `unshare -n` the namespace gets its OWN loopback, so the host's
# Postgres TCP listener is not reachable at 127.0.0.1:5432 -- `ip link set lo
# up` brings up a fresh, empty loopback, not the host's. A unix socket crosses
# the boundary because it is a filesystem path, which is why psql works there
# and asyncpg did not.
#
# Until the primary-feature contract tests existed, nothing in the suite opened
# an ASYNC connection, so this never surfaced. They failed on their first gate
# run with "Connect call failed ('127.0.0.1', 5432)" -- an environment fault
# reported as nine broken features.
#
# The socket directory is detected rather than assumed.
PGSOCKET_DIR=""
for _d in /var/run/postgresql /run/postgresql /tmp; do
    if ls "$_d"/.s.PGSQL.* >/dev/null 2>&1; then PGSOCKET_DIR="$_d"; break; fi
done
if [ -z "$PGSOCKET_DIR" ]; then
    echo "gate: no postgres unix socket found; tests that open a database"
    echo "gate: connection cannot reach it inside the network namespace."
    echo "gate: refusing to run rather than report that as nine failures."
    exit 2
fi
# user:pass@host[:port]/db  ->  user:pass@/db?host=<socket dir>
DATABASE_URL_NS="$(printf '%s' "$DATABASE_URL" | sed -E 's#@[^/@]*/#@/#')?host=$PGSOCKET_DIR"
export DATABASE_URL_NS

# The SYNC DSN must be isolated too.
#
# Overriding DATABASE_URL alone left DATABASE_URL_SYNC pointing at production
# -- and the .env is SYMLINKED from the real one, so every suite reading the
# sync DSN connected to the live database from inside a gate whose entire
# premise is that it cannot. On 25 Oct 2026 one of them acquired the
# canonical execution lease on production and never released it; a scheduled
# canonical run would have waited 90 minutes and then skipped, silently.
#
# Derived from the same credentials with the database name replaced, exactly
# as DATABASE_URL is, and exported so it takes precedence over the .env.
PROD_SYNC="$(grep -E '^DATABASE_URL_SYNC=' "$SRC/backend/.env" 2>/dev/null \
             | head -1 | cut -d= -f2- | tr -d '"'"'"'')"
if [ -z "$PROD_SYNC" ]; then
    echo "gate: no DATABASE_URL_SYNC in $SRC/backend/.env -- refusing to run"
    echo "gate: suites that use it would reach production unisolated."
    exit 2
fi
export DATABASE_URL_SYNC="${PROD_SYNC%/*}/$DB"
DATABASE_URL_SYNC_NS="$(printf '%s' "$DATABASE_URL_SYNC" \
                        | sed -E 's#@[^/@]*/#@/#')?host=$PGSOCKET_DIR"
export DATABASE_URL_SYNC_NS

# Both must name the isolated database. Checked rather than assumed: a sed
# that silently failed to substitute would send the whole suite at
# production, and the symptom would be a gate that passes while writing to
# the system it certifies.
case "$DATABASE_URL_SYNC" in
    *"/$DB") : ;;
    *) echo "gate: DATABASE_URL_SYNC does not end in the isolated database"
       exit 2 ;;
esac
echo "gate: namespace database URL uses the unix socket at $PGSOCKET_DIR"
case "$DATABASE_URL" in
    *"/$DB") : ;;
    *) echo "gate: DATABASE_URL does not end in the isolated database name"
       exit 2 ;;
esac

sudo -u postgres createdb -O "$DB_OWNER" "$DB" \
    || { echo "gate: could not create $DB"; exit 2; }

# Real schema, no rows. pg_dump --schema-only is read-only on production.
echo "gate: loading schema from $PROD_DB (schema only, read-only)"
if ! sudo -u postgres pg_dump --schema-only --no-owner --no-privileges \
        "$PROD_DB" 2>"$WORK/dump.err" \
        | sudo -u postgres psql -q "$DB" >"$WORK/load.out" 2>&1; then
    echo "gate: schema load reported errors (first lines):"
    head -5 "$WORK/dump.err" "$WORK/load.out" 2>/dev/null
fi
# The dump is restored with --no-owner --no-privileges AS postgres, so every
# schema and table inside ends up owned by postgres with no grants -- while
# the DATABASE is owned by $DB_OWNER. Until the primary-feature contracts
# existed, nothing connected to the scratch database as the APPLICATION
# user: the suites that touched it ran as postgres via psycopg2, so this was
# never exercised.
#
# Their first gate run failed with
#   asyncpg.exceptions.InsufficientPrivilegeError: permission denied for
#   schema screener
# which the gate correctly reported as INCONCLUSIVE rather than as eleven
# broken features.
#
# Grants are generated by a query, not written by hand, so a schema added
# later is covered without anyone remembering. The database is disposable
# and dropped at exit, so granting broadly costs nothing.
echo "gate: granting $DB_OWNER access to the cloned schemas"
sudo -u postgres psql -tAc "SELECT format('GRANT USAGE ON SCHEMA %I TO %I; GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA %I TO %I; GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA %I TO %I;', nspname, '$DB_OWNER', nspname, '$DB_OWNER', nspname, '$DB_OWNER') FROM pg_namespace WHERE nspname NOT LIKE 'pg!_%' ESCAPE '!' AND nspname <> 'information_schema'" "$DB" | sudo -u postgres psql -q "$DB" >>"$WORK/load.out" 2>&1
TABLES="$(sudo -u postgres psql -tAc \
    "SELECT count(*) FROM information_schema.tables WHERE table_schema NOT IN ('pg_catalog','information_schema')" \
    "$DB" 2>/dev/null || echo 0)"
echo "gate: isolated database ready, owner=$DB_OWNER, tables=$TABLES"
if [ "$TABLES" -lt 1 ]; then
    echo "gate: schema is empty -- every DB-dependent suite would be"
    echo "gate: inconclusive. Refusing to report a gate on that."
    exit 2
fi

#: Output markers meaning "this suite could not run", as distinct from "this
#: suite ran and found a defect". Classified INCONCLUSIVE, never pre-existing.
ENV_MARKERS='could not connect|OperationalError|UndefinedTable|ConnectionRefused|Connection refused|Temporary failure in name resolution|nodename nor servname|ModuleNotFoundError|ImportError|getaddrinfo|Network is unreachable|psycopg|asyncpg\.exceptions'

# ── Run every suite at one commit ───────────────────────────────────────────
run_at() {
    # Declared separately, not `local a=$1 b=$a`: bash expands every word of
    # the builtin's argument list before the builtin runs, so a later
    # assignment referring to an earlier one reads the CALLER's scope -- and
    # under `set -u` that is an unbound-variable error.
    local sha="$1"
    local label="$2"
    local dir="$WORK/$label"

    git clone -q "$SRC" "$dir" 2>/dev/null || { echo "gate: clone failed"; return 2; }
    git -C "$dir" checkout -q "$sha" 2>/dev/null || {
        echo "gate: $sha not found in $SRC"; return 2; }

    # Symlinked, not copied: configuration must be identical between the two
    # runs for the comparison to mean anything, and the secret should not be
    # duplicated at rest to achieve that.
    [ -f "$SRC/backend/.env" ] && ln -sf "$SRC/backend/.env" "$dir/backend/.env"

    echo "── $label  $(git -C "$dir" rev-parse HEAD)"

    local files=0 ok=0 bad=0 incon=0
    : > "$WORK/$label.failures"
    : > "$WORK/$label.inconclusive"

    local t name out
    for t in "$dir"/backend/tests/test_*.py; do
        files=$((files + 1))
        name="$(basename "$t")"
        out="$WORK/$label.$name.out"

        # Loopback up so the unix socket and localhost still work; nothing
        # else is reachable. DATABASE_URL re-exported inside the namespace.
        unshare -n -- bash -c \
            "ip link set lo up 2>/dev/null; export DATABASE_URL='$DATABASE_URL_NS'; export DATABASE_URL_SYNC='$DATABASE_URL_SYNC_NS'; cd '$dir/backend' && '$PY' '$t'" \
            > "$out" 2>&1
        local rc=$?

        # A passing suite is a pass, whatever text it printed. Several of
        # these deliberately exercise error paths and name the exceptions
        # they handle, so scanning output before checking the exit status
        # would mark healthy suites inconclusive.
        if [ $rc -eq 0 ]; then
            # Exit 0 is absence of failure, not evidence of execution.
            #
            # Suites here are standalone scripts: `python tests/foo.py` runs
            # an `if __name__ == "__main__"` block that executes the test
            # functions and prints "N/M passed". A file WITHOUT that block
            # defines its functions, runs nothing, and exits 0 -- identical
            # to a file that ran fifty assertions and passed them all.
            #
            # Four files were in exactly that state on 25 Oct 2026, and two
            # of them were the suites certifying the release being gated:
            # test_configuration_builds.py and test_scheduler_ownership.py.
            # The gate reported 101/101 while the behavioural exclusion
            # tests had never run. test_multibagger_contract.py and
            # test_multibagger_score.py had been vacuous far longer.
            #
            # So require the positive signal, and treat its absence as
            # INCONCLUSIVE rather than a pass: a suite that cannot be shown
            # to have run claims nothing either way, which is precisely the
            # state this gate already models for environment faults.
            # Two shapes are accepted, because the suite has two honest
            # conventions:
            #
            #   "N/M passed"             a __main__ runner enumerating tests
            #   "ALL ... CHECKS PASSED"  a script-style suite asserting at
            #                            module level (the multibagger pair)
            #
            # Both prove the file RAN to its end. A file that defines
            # functions and never calls them prints neither.
            if ! grep -qE '^[0-9]+/[0-9]+ passed|ALL [A-Z ]*CHECKS PASSED' "$out"; then
                incon=$((incon + 1))
                echo "$name" >> "$WORK/$label.inconclusive"
                printf '  INCONCL %-50s %s\n' "$name" \
                       "exited 0 without evidence it ran — no test count and no completion marker"
                continue
            fi

            # And the count must be non-zero. A runner that enumerates its
            # tests from globals() and finds none also prints "0/0 passed".
            local ran
            ran="$(grep -oE '^[0-9]+/[0-9]+ passed' "$out" | head -1 \
                   | cut -d/ -f2 | cut -d' ' -f1)"
            if [ -n "$ran" ] && [ "$ran" -eq 0 ]; then
                incon=$((incon + 1))
                echo "$name" >> "$WORK/$label.inconclusive"
                printf '  INCONCL %-50s %s\n' "$name" \
                       "reported 0 tests — the suite has lost its population"
                continue
            fi

            ok=$((ok + 1))
            continue
        fi

        if grep -qE "$ENV_MARKERS" "$out"; then
            incon=$((incon + 1))
            echo "$name" >> "$WORK/$label.inconclusive"
            printf '  INCONCL %-50s %s\n' "$name" \
                   "$(grep -oE "$ENV_MARKERS" "$out" | head -1)"
            continue
        fi

        bad=$((bad + 1))
        # Per TEST, not per file. A suite that failed without printing any
        # PASS/FAIL line never reached its tests; record that as its own id
        # rather than losing it.
        local names
        names="$(grep -oE '^ *(FAIL|ERROR) +[A-Za-z0-9_]+' "$out" \
                 | awk '{print $2}' | sort -u)"
        if [ -z "$names" ]; then
            echo "$name::<suite-did-not-reach-its-tests>" >> "$WORK/$label.failures"
        else
            while read -r tn; do
                [ -n "$tn" ] && echo "$name::$tn" >> "$WORK/$label.failures"
            done <<< "$names"
        fi
        printf '  FAIL    %-50s %s\n' "$name" "$(tail -n 1 "$out")"
    done

    local tests
    tests="$(wc -l < "$WORK/$label.failures")"
    echo "  $label: $files files — $ok passed, $bad failed ($tests tests), $incon inconclusive"
    sort -o "$WORK/$label.failures" "$WORK/$label.failures"
}

run_at "$CANDIDATE" candidate || exit 2
if [ -n "$BASELINE" ]; then
    run_at "$BASELINE" baseline || exit 2
fi

# ── Attribution, per test ───────────────────────────────────────────────────
echo
echo "════ attribution (per test) ════"
if [ -z "$BASELINE" ]; then
    echo "no baseline given; failures are reported but NOT attributed"
    [ -s "$WORK/candidate.failures" ] && exit 1
    exit 0
fi

introduced="$(comm -23 "$WORK/candidate.failures" "$WORK/baseline.failures")"
preexisting="$(comm -12 "$WORK/candidate.failures" "$WORK/baseline.failures")"
repaired_raw="$(comm -13 "$WORK/candidate.failures" "$WORK/baseline.failures")"

# A suite that could not RUN at either commit never enters that commit's
# failure set, so a test inconclusive at the candidate and failing at the
# baseline falls out of `comm -13` looking REPAIRED. It was not repaired; it
# was not executed. Credit for a fix requires the test to have run and
# passed.
#
# Same reasoning in the other direction: inconclusive at the baseline and
# failing at the candidate is not demonstrably INTRODUCED either, because
# there is no baseline observation to have moved from.
cat "$WORK/candidate.inconclusive" "$WORK/baseline.inconclusive" 2>/dev/null \
    | sort -u > "$WORK/blocked.files"

split_by_blocked() {        # stdin -> $1 (verified), $2 (unverifiable)
    : > "$1"; : > "$2"
    while read -r id; do
        [ -z "$id" ] && continue
        if grep -qxF "${id%%::*}" "$WORK/blocked.files"; then
            echo "$id" >> "$2"
        else
            echo "$id" >> "$1"
        fi
    done
}

printf '%s\n' "$repaired_raw" | split_by_blocked "$WORK/repaired" "$WORK/unverif.r"
printf '%s\n' "$introduced"  | split_by_blocked "$WORK/introduced" "$WORK/unverif.i"
repaired="$(cat "$WORK/repaired")"
introduced="$(cat "$WORK/introduced")"
unverifiable="$(cat "$WORK/unverif.r" "$WORK/unverif.i" 2>/dev/null | sort -u)"

show() { [ -n "$2" ] && echo "$2" | sed 's/^/    /' || echo "    none"; }
echo "INTRODUCED by the candidate (gate blocks on these):"; show i "$introduced"
echo "PRE-EXISTING at the baseline:";                       show p "$preexisting"
echo "REPAIRED by the candidate (ran and passed):";         show r "$repaired"
echo "UNVERIFIABLE (blocked at one commit — claims nothing either way):"
show u "$unverifiable"
echo "INCONCLUSIVE suites (could not run; neither pass nor failure):"
show c "$(sort -u "$WORK/candidate.inconclusive" "$WORK/baseline.inconclusive" 2>/dev/null)"

# ── P0: the three features the product exists to provide ────────────────────
# Attribution decides whether a failure is NEW. For most tests that is the
# right question. For the primary surfaces it is not: a screener that is
# broken at both commits is still a screener that is broken, and "PRE-EXISTING"
# would wave it through.
#
# That is not hypothetical. Three failures rode EIGHT releases under that
# label on 24 Oct 2026, one of them warning that a freeze-window run could
# fail. Being correctly classified is not the same as being read.
#
# So these block on their state at the CANDIDATE, regardless of attribution.
P0_PATTERN='test_primary_features_contract'
p0_failures="$(grep -E "^${P0_PATTERN}" "$WORK/candidate.failures" 2>/dev/null || true)"

# A suite that could not RUN is not a suite that passed. The first version of
# this check grepped only the failure list, so when the contract tests were
# blocked by a database they could not reach, P0 printed "all primary-feature
# contracts hold" -- a clean bill of health from a suite that never executed.
# That is the same error the gate's INCONCLUSIVE category exists to prevent,
# committed inside the guard written to prevent it.
p0_inconclusive="$(grep -E "^${P0_PATTERN}" "$WORK/candidate.inconclusive" 2>/dev/null || true)"

# And a suite that produced no result at all is the third way to learn
# nothing: deleted, renamed, or never matched by the glob. The gate writes one
# .out file per suite it EXECUTES, so the presence of that file is the
# evidence -- there is no "passed" list to consult, which the first version of
# this line assumed there was. It referenced $WORK/candidate.passed, a file
# nothing writes, so a clean run would have counted zero and blocked every
# release.
p0_ran=0
for _o in "$WORK"/candidate.*"$P0_PATTERN"*.out; do
    [ -s "$_o" ] && p0_ran=$((p0_ran + 1))
done

echo
echo "════ P0 — primary features (block on state, not attribution) ════"
if [ -n "$p0_failures" ]; then
    echo "$p0_failures" | sed 's/^/    /'
elif [ -n "$p0_inconclusive" ]; then
    echo "    INCONCLUSIVE — the contracts did not run, so they prove nothing:"
    echo "$p0_inconclusive" | sed 's/^/        /'
elif [ "$p0_ran" = "0" ]; then
    echo "    MISSING — no primary-feature suite was executed at all."
else
    echo "    all primary-feature contracts hold"
fi

if [ -n "$p0_inconclusive" ] || [ "$p0_ran" = "0" ]; then
    echo
    echo "════ the PRIMARY FEATURE contracts did not run ════"
    echo "They prove nothing, so this release is not cleared. An environment"
    echo "fault and a broken screener are different problems; neither is a"
    echo "reason to ship."
    for f in $p0_inconclusive; do
        echo "──── $f"
        cat "$WORK/candidate.$f.out" 2>/dev/null | tail -40
    done
    exit 1
fi

if [ -n "$p0_failures" ]; then
    echo
    echo "════ a PRIMARY FEATURE is broken at the candidate ════"
    echo "Stock screening, the market overview or the company pages do not"
    echo "work. This blocks whether or not the baseline was also broken."
    echo "$p0_failures" | cut -d: -f1 | sort -u | while read -r f; do
        [ -z "$f" ] && continue
        echo "──── $f"
        cat "$WORK/candidate.$f.out"
    done
    exit 1
fi

if [ -n "$introduced" ]; then
    echo
    echo "════ output of introduced failures ════"
    # The last line of a summary is not a reason.
    echo "$introduced" | cut -d: -f1 | sort -u | while read -r f; do
        [ -z "$f" ] && continue
        echo "──── $f"
        cat "$WORK/candidate.$f.out"
    done
    exit 1
fi
exit 0
