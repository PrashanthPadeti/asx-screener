#!/usr/bin/env bash
#
# Full-suite release gate
# =======================
# Runs EVERY backend/tests/test_*.py at an exact commit, in a disposable
# checkout, against an isolated database, with outbound network blocked.
#
# Why this exists
# ---------------
# The v11.2.22 gate reported "13 suites all passing". There are 81. The
# thirteen were chosen by hand, and `test_refusal_reaches_telemetry_end_to_end`
# was not among them -- it had been failing since v11.2.21, where ASX100 moved
# to EODHD and the test began making a live API call instead of the total
# refusal it asserts about. A gate that picks its own population cannot report
# what it did not look at, which is the same defect the producers had.
#
# So: no suite list. The population is the glob, and the count is reported.
#
# Why the network is blocked
# -----------------------------
# That same test spent production EODHD quota on every run and would have
# passed or failed with the provider's availability. A test that reaches a
# real provider is not testing what it claims. `unshare -n` gives each run a
# network namespace with loopback only, so an unstubbed provider call fails
# loudly here rather than silently succeeding.
#
# Postgres is reached over its unix socket, which a network namespace does not
# affect, so an isolated database still works.
#
# Why it runs the baseline too
# ----------------------------
# A failing suite at the candidate means nothing until you know whether it
# failed before. Attributing pre-existing failures to a candidate -- or a
# candidate's failures to the past -- has happened twice in this work. The
# script runs both commits and diffs the failure sets, so attribution is
# computed rather than argued.
#
# Usage:
#   sudo bash backend/scripts/gate_full_suite.sh <candidate-sha> [baseline-sha]
#
set -uo pipefail

CANDIDATE="${1:?usage: gate_full_suite.sh <candidate-sha> [baseline-sha]}"
BASELINE="${2:-}"

SRC="${SRC:-/opt/asx-screener}"
PY="${PY:-/opt/asx-screener/asx-venv/bin/python}"
WORK="$(mktemp -d /tmp/gate.XXXXXX)"
DB="asx_gate_$$"

cleanup() {
    sudo -u postgres dropdb --if-exists "$DB" >/dev/null 2>&1
    rm -rf "$WORK"
}
trap cleanup EXIT

echo "gate: work=$WORK  db=$DB"

# ── The gate must never be able to write to production ──────────────────────
# The .env below is the real one, so its DATABASE_URL is the production
# database, and a network namespace does not protect it -- loopback is up and
# Postgres is local. The credentials are reused (they work) with the database
# name replaced, and DATABASE_URL is exported so it takes precedence over the
# .env file for pydantic settings.
#
# Never echoed: the URL carries a password.
PROD_URL="$(grep -E '^DATABASE_URL=' "$SRC/backend/.env" 2>/dev/null \
            | head -1 | cut -d= -f2- | tr -d '"'"'"'')"
if [ -z "$PROD_URL" ]; then
    echo "gate: no DATABASE_URL in $SRC/backend/.env -- refusing to run"
    echo "gate: without an explicit override the suite would use the default,"
    echo "gate: which may be production."
    exit 2
fi
DB_OWNER="$(printf '%s' "$PROD_URL" | sed -E 's|^[^:]+://([^:/]+).*|\1|')"
export DATABASE_URL="${PROD_URL%/*}/$DB"

sudo -u postgres createdb -O "$DB_OWNER" "$DB" \
    || { echo "gate: could not create $DB"; exit 2; }
echo "gate: isolated database created, owner=$DB_OWNER"

# Prove the override took, without printing the URL.
case "$DATABASE_URL" in
    *"/$DB") : ;;
    *) echo "gate: DATABASE_URL does not end in the isolated database name"
       exit 2 ;;
esac

# ── Run every suite at one commit ───────────────────────────────────────────
run_at() {
    # Declared separately, not `local a=$1 b=$a`: bash expands every word of
    # the builtin's argument list before the builtin runs, so a later
    # assignment referring to an earlier one reads the CALLER's scope -- and
    # under `set -u` that is an unbound-variable error, not an empty string.
    local sha="$1"
    local label="$2"
    local dir="$WORK/$label"

    git clone -q "$SRC" "$dir" 2>/dev/null || { echo "gate: clone failed"; return 2; }
    git -C "$dir" checkout -q "$sha" 2>/dev/null || {
        echo "gate: $sha not found in $SRC"; return 2; }

    # Symlinked, not copied: the configuration must be identical between the
    # two runs for the comparison to mean anything, and the secret should not
    # be duplicated at rest to achieve that.
    [ -f "$SRC/backend/.env" ] && ln -sf "$SRC/backend/.env" "$dir/backend/.env"

    local resolved
    resolved="$(git -C "$dir" rev-parse HEAD)"
    echo "── $label  $resolved"

    local total=0 passed=0 failed=0
    : > "$WORK/$label.failures"

    for t in "$dir"/backend/tests/test_*.py; do
        total=$((total + 1))
        local name
        name="$(basename "$t")"
        # Loopback up so the unix socket and any localhost binding still work;
        # nothing else is reachable.
        # DATABASE_URL is passed through explicitly so the isolated database
        # wins over the symlinked .env inside the namespace too.
        if unshare -n -- bash -c \
              "ip link set lo up 2>/dev/null; export DATABASE_URL='$DATABASE_URL'; cd '$dir/backend' && '$PY' '$t'" \
              > "$WORK/$label.$name.out" 2>&1; then
            passed=$((passed + 1))
        else
            failed=$((failed + 1))
            echo "$name" >> "$WORK/$label.failures"
            printf '  FAIL  %-55s %s\n' "$name" \
                   "$(tail -n 1 "$WORK/$label.$name.out")"
        fi
    done

    echo "  $label: $total files, $passed passed, $failed failed"
    echo "$total" > "$WORK/$label.total"
}

run_at "$CANDIDATE" candidate || exit 2
[ -n "$BASELINE" ] && { run_at "$BASELINE" baseline || exit 2; }

# ── Attribution ─────────────────────────────────────────────────────────────
echo
echo "════ attribution ════"
if [ -n "$BASELINE" ] && [ -f "$WORK/baseline.failures" ]; then
    sort -o "$WORK/candidate.failures" "$WORK/candidate.failures"
    sort -o "$WORK/baseline.failures"  "$WORK/baseline.failures"

    introduced="$(comm -23 "$WORK/candidate.failures" "$WORK/baseline.failures")"
    preexisting="$(comm -12 "$WORK/candidate.failures" "$WORK/baseline.failures")"
    repaired="$(comm -13 "$WORK/candidate.failures" "$WORK/baseline.failures")"

    echo "INTRODUCED by the candidate (gate blocks on these):"
    [ -n "$introduced" ] && echo "$introduced" | sed 's/^/    /' || echo "    none"
    echo "PRE-EXISTING at the baseline (recorded, not attributed to this work):"
    [ -n "$preexisting" ] && echo "$preexisting" | sed 's/^/    /' || echo "    none"
    echo "REPAIRED by the candidate:"
    [ -n "$repaired" ] && echo "$repaired" | sed 's/^/    /' || echo "    none"

    # Full output for anything the candidate introduced -- the last line of a
    # summary is not a reason.
    if [ -n "$introduced" ]; then
        echo
        echo "════ output of introduced failures ════"
        while read -r n; do
            [ -z "$n" ] && continue
            echo "──── $n"
            cat "$WORK/candidate.$n.out"
        done <<< "$introduced"
    fi

    [ -n "$introduced" ] && exit 1
    exit 0
fi

echo "no baseline given; failures are reported but not attributed"
[ -s "$WORK/candidate.failures" ] && exit 1
exit 0
