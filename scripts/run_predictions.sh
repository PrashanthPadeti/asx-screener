#!/bin/bash
#
# Nightly price-prediction trigger.
#
# The admin password used to be a literal on the login line below. This file is
# tracked in a PUBLIC repository, so that credential was published from the
# moment it was committed and had to be treated as compromised, not merely
# tidied away. It was rotated on 17 Sep 2026; what follows is the shape that
# stops it happening again.
#
# Two rules this now keeps:
#
#   the credential lives in backend/.env, like every other secret, and is
#   read at run time -- never in source, never in this repository
#
#   it is passed to curl on STDIN, not in argv. `-d '{"password":"..."}'`
#   puts the secret in the process table, where any user on the box can read
#   it with ps, and in this script's own shell history when run by hand
#
# Requires ADMIN_EMAIL and ADMIN_PASSWORD in backend/.env.

set -uo pipefail

LOG=${PREDICTIONS_LOG:-/var/log/asx-predictions.log}
ENV_FILE=${ASX_ENV_FILE:-/opt/asx-screener/backend/.env}
API=${ASX_API:-http://localhost:8000}

log() { echo "$(date -Is)  $*" >> "$LOG"; }

log "--- run_predictions start ---"

if [ ! -r "$ENV_FILE" ]; then
    log "ERROR: cannot read $ENV_FILE — no credentials, not attempting login"
    exit 1
fi

set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a

# Named explicitly rather than defaulted. A missing credential must stop the
# script, not send an empty password to the login endpoint and log a confusing
# authentication failure.
if [ -z "${ADMIN_EMAIL:-}" ] || [ -z "${ADMIN_PASSWORD:-}" ]; then
    log "ERROR: ADMIN_EMAIL or ADMIN_PASSWORD missing from $ENV_FILE"
    exit 1
fi

# ── Step 1: a fresh admin token ──────────────────────────────────────────────
# The body goes through stdin via `-d @-`, so the password never appears in the
# process table.
TOKEN=$(
    printf '{"email":"%s","password":"%s"}' "$ADMIN_EMAIL" "$ADMIN_PASSWORD" \
    | curl -s --max-time 30 -X POST "$API/api/v1/auth/login" \
           -H "Content-Type: application/json" -d @- \
    | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" \
      2>/dev/null
)

if [ -z "$TOKEN" ]; then
    log "ERROR: could not obtain admin token for $ADMIN_EMAIL (check the"
    log "       credential in $ENV_FILE — it was rotated on 17 Sep 2026)"
    exit 1
fi

# ── Step 2: trigger predictions ──────────────────────────────────────────────
# The HTTP status decides the verdict, not the shape of the body.
#
# My first version failed on any response containing "detail", which made
# 409 "Today's predictions already ran" an ERROR. That is an idempotency
# reply, not a failure: the work is done and re-running would change nothing.
# A predicate that reports success as failure trains whoever reads the log to
# ignore it, which is worse than having no check.
RESPONSE=$(curl -s --max-time 600 -w '\n%{http_code}' -X POST \
    "$API/api/v1/predictions/trigger?top_n=1000" \
    -H "Authorization: Bearer $TOKEN")
STATUS=${RESPONSE##*$'\n'}
BODY=${RESPONSE%$'\n'*}

log "HTTP $STATUS: $BODY"

case "$STATUS" in
    2??)
        log "--- run_predictions done (triggered) ---"
        exit 0
        ;;
    409)
        # Already ran today. Nothing to do, and nothing wrong.
        log "--- run_predictions done (already ran today; no action) ---"
        exit 0
        ;;
    *)
        log "ERROR: prediction trigger failed with HTTP ${STATUS:-no response}"
        exit 1
        ;;
esac

