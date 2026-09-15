#!/usr/bin/env bash
#
# Freeze and thaw the writers for the P0-A rollout window.
#
#     bash scripts/p0a_freeze.sh status
#     bash scripts/p0a_freeze.sh freeze
#     bash scripts/p0a_freeze.sh thaw
#
# There are two independent schedulers on this host and both must be stopped.
# Stopping one is the failure mode this script exists to prevent:
#
#   cron          7 jobs. daily_pipeline, weekly_refresh, weekly_pipeline and
#                 top5_strategy all read or write screener.universe.
#   APScheduler   18 jobs registered in app/main.py, inside the asx-backend
#                 process. market_snapshot, anomaly_detect, anomaly_alerts,
#                 short_positions and top5_strategy touch the same tables.
#
# The API keeps serving throughout. Freezing is not a maintenance outage — it
# stops computation, not traffic.
#
# The anomaly alert worker is NOT controlled here, and this script used to
# claim otherwise. The header said it was "excluded from thaw deliberately"
# while thaw() restored every scheduler and printed a reminder asking a human
# to stop the job before the next 20:35 run. A comment is not an exclusion and
# a reminder is not a control -- and neither would help anyone who restarted
# the service by some other route.
#
# The exclusion is now executable and lives with the job: app/main.py declines
# to register anomaly_alerts unless ANOMALY_ALERTS_ENABLED is on, and
# send_anomaly_alerts refuses to send even if called directly. Default off.
# Turning it on is a release decision with its own gate, not a side effect of
# thawing. `status` below reports the real state rather than asserting one.

set -u

ASX_ROOT=${ASX_ROOT:-/opt/asx-screener}
STATE_DIR=${STATE_DIR:-/var/backups/p0a/freeze}
ENV_FILE="$ASX_ROOT/backend/.env"
SERVICE=${SERVICE:-asx-backend}
PYBIN=${PYBIN:-$ASX_ROOT/asx-venv/bin/python}
# The unit writes StandardOutput and StandardError here rather than to
# journald. Useful for tracebacks on a failed start, but NOT a source of
# scheduler state: uvicorn configures its own loggers and app/main.py's
# logger.info lines never reach it.
LOGFILE=${LOGFILE:-$ASX_ROOT/logs/backend.log}
HEALTH_URL=${HEALTH_URL:-http://127.0.0.1:8000/health}
MARKER="# P0A-FREEZE"

usage() { echo "usage: $0 {status|freeze|thaw}" >&2; exit 2; }
[ $# -eq 1 ] || usage

if [ ! -f "$ENV_FILE" ]; then
    echo "ERROR: $ENV_FILE not found — is this the ASX screener host?" >&2
    echo "       hostname: $(hostname)" >&2
    exit 2
fi

cron_frozen() { crontab -l 2>/dev/null | grep -q "^$MARKER"; }
env_frozen()  { grep -qiE '^[[:space:]]*SCHEDULERS_ENABLED[[:space:]]*=[[:space:]]*(0|false|no|off)' "$ENV_FILE"; }

status() {
    echo "host:        $(hostname)"
    echo "cron:        $(cron_frozen && echo FROZEN || echo active) "\
         "($(crontab -l 2>/dev/null | grep -cE '^[^#[:space:]]') live entries)"
    # What was asked for. Deliberately labelled as such: the earlier version
    # printed this as "scheduler: FROZEN" and was reporting a freeze that had
    # not happened, because the app could not start to honour it.
    echo "env flag:    $(env_frozen && echo set || echo unset)"
    echo "service:     $(systemctl is-active "$SERVICE" 2>/dev/null)"
    echo
    echo "--- jobs in flight ---"
    pgrep -af 'daily_pipeline|weekly_refresh|weekly_pipeline|top5_strategy|daily_compute|sector_bench|anomaly_detect|anomaly_alert|build_screener_universe' \
        || echo "none"
    echo
    echo "--- what the running process actually holds ---"
    local jobs flag
    jobs=$(scheduler_jobs); flag=$(scheduler_frozen_flag)
    case "${jobs:-}" in
        "")   echo "scheduler: unknown (health endpoint unreachable)" ;;
        null) echo "scheduler: null (deployed code predates this field)" ;;
        0)    if [ "$flag" = "true" ]; then
                  echo "scheduler: 0 jobs, frozen=true  <- frozen, verified in the process"
              else
                  echo "scheduler: 0 jobs but frozen=$flag  <- BROKEN, not frozen"
              fi ;;
        *)    echo "scheduler: $jobs jobs, frozen=$flag  <- NOT frozen" ;;
    esac

    # Read from the running process, not from .env: what matters is what the
    # service loaded, and an .env edit without a restart would report a
    # control that is not in force.
    local alerts
    alerts=$(anomaly_alerts_flag)
    case "${alerts:-}" in
        "")     echo "anomaly alerts: unknown (health endpoint unreachable)" ;;
        null)   echo "anomaly alerts: null (deployed code predates this field)" ;;
        false)  echo "anomaly alerts: DISABLED  <- outbound email path is closed" ;;
        true)   echo "anomaly alerts: ENABLED   <- emails WILL be sent at 20:35" ;;
        *)      echo "anomaly alerts: $alerts" ;;
    esac
}

# Whether the running process will send outbound anomaly alerts. Independent
# of freeze state by design: thawing restores schedulers, and this must not
# come back with them.
anomaly_alerts_flag() {
    curl -fsS --max-time 10 "$HEALTH_URL" 2>/dev/null \
        | sed -nE 's/.*"anomaly_alerts"[[:space:]]*:[[:space:]]*(true|false|null).*/\1/p'
}

# How many jobs the RUNNING scheduler holds. Ground truth from the process
# rather than from a log line: uvicorn configures its own loggers, so none of
# app/main.py's logger.info output reaches logs/backend.log. A whole-file grep
# for "Schedulers started" returns zero, which means a freeze verified by log
# line could never succeed — it would revert on every attempt.
scheduler_jobs() {
    curl -fsS --max-time 10 "$HEALTH_URL" 2>/dev/null \
        | sed -nE 's/.*"jobs"[[:space:]]*:[[:space:]]*([0-9]+|null).*/\1/p'
}

# The flag the running process attributes its state to. Checked alongside the
# job count because the two prove different things: the count proves the
# operational effect, the flag proves the effect came from this maintenance
# control rather than from job registration having failed for some other
# reason. A scheduler holding 0 jobs with frozen=false is broken, not frozen.
scheduler_frozen_flag() {
    curl -fsS --max-time 10 "$HEALTH_URL" 2>/dev/null \
        | sed -nE 's/.*"frozen"[[:space:]]*:[[:space:]]*(true|false|null).*/\1/p'
}

# Whether the app can still construct its Settings. pydantic-settings forbids
# extras, so an undeclared key in .env raises at import and uvicorn cannot load
# the app at all — a total outage, not a quiet fallback. Checked before any
# restart, because a config edit that cannot start is not something to discover
# from systemd's restart counter.
settings_load() {
    (cd "$ASX_ROOT/backend" && "$PYBIN" -c \
        "from app.core.config import get_settings; get_settings()" 2>&1)
}

# Three independent conditions, because each can pass while another fails:
#   active     systemd is happy
#   healthy    the app answers, rather than being mid-crash-loop with
#              is-active momentarily true
#   jobs       the running scheduler holds the number this state requires.
#              0 is proof the freeze reached the process, not proof a config
#              file says it should have.
verify_running() {
    local want="$1"
    sleep 8
    [ "$(systemctl is-active "$SERVICE")" = "active" ] || return 1
    curl -fsS --max-time 10 "$HEALTH_URL" >/dev/null 2>&1 || return 3

    local jobs flag
    jobs=$(scheduler_jobs); flag=$(scheduler_frozen_flag)
    case "$want" in
        FROZEN) [ "$jobs" = "0" ] && [ "$flag" = "true" ] || return 2 ;;
        ACTIVE) [ -n "$jobs" ] && [ "$jobs" != "0" ] && [ "$jobs" != "null" ] \
                    && [ "$flag" = "false" ] || return 2 ;;
    esac
    return 0
}

restore_env() {
    sed -i -E '/^[[:space:]]*SCHEDULERS_ENABLED[[:space:]]*=/d; /^# rollout freeze, added /d' \
        "$ENV_FILE"
}

freeze() {
    mkdir -p "$STATE_DIR" && chmod 700 "$STATE_DIR"
    local stamp; stamp=$(date -u +%Y%m%dT%H%M%SZ)

    # Baseline: can the app load its configuration as things stand? If not,
    # something is already wrong and this is not the moment to change more.
    # Without it a pre-existing fault would be discovered after the .env edit
    # and blamed on the freeze.
    if ! err=$(settings_load); then
        echo "ERROR: settings do not load BEFORE any change — aborting." >&2
        echo "$err" | tail -5 >&2
        exit 3
    fi

    # Record before changing. A freeze that cannot be undone exactly is not a
    # freeze, it is a schedule rewrite.
    if cron_frozen; then
        echo "cron already frozen — leaving the existing backup intact"
    else
        crontab -l > "$STATE_DIR/crontab.$stamp.bak" 2>/dev/null
        cp "$STATE_DIR/crontab.$stamp.bak" "$STATE_DIR/crontab.current.bak"
        echo "cron backed up -> $STATE_DIR/crontab.$stamp.bak"

        # Comment every live entry and mark it, so thaw can identify exactly
        # what this script disabled and leave anything else alone.
        crontab -l 2>/dev/null \
            | sed -E "s|^([^#[:space:]].*)$|$MARKER \1|" \
            | crontab -
        echo "cron: $(crontab -l | grep -c "^$MARKER") entries disabled"
    fi

    if env_frozen; then
        echo "SCHEDULERS_ENABLED already off"
    else
        cp "$ENV_FILE" "$STATE_DIR/env.$stamp.bak"
        printf '\n%s rollout freeze, added %s\nSCHEDULERS_ENABLED=false\n' \
            "#" "$stamp" >> "$ENV_FILE"
        echo "SCHEDULERS_ENABLED=false appended to $ENV_FILE"
    fi

    # The check that matters: settings must still load with the key present.
    # Writing SCHEDULERS_ENABLED into .env without the matching field in
    # config.py took the API down for eight minutes on 11 Sep 2026 — the
    # variable did not fall back to a default, it failed Settings()
    # construction at import, so uvicorn could not load the app at all. This
    # turns that outage into an aborted freeze with the service untouched.
    echo
    echo "checking the app can still load its settings ..."
    if ! err=$(settings_load); then
        echo "ERROR: settings will not load with SCHEDULERS_ENABLED set — reverting." >&2
        echo "$err" | tail -5 >&2
        restore_env
        echo "ENV REVERTED. The service was NOT restarted and is untouched." >&2
        exit 3
    fi

    echo
    echo "restarting $SERVICE so the scheduler restarts with no jobs ..."
    systemctl restart "$SERVICE"

    verify_running FROZEN
    case $? in
        0) echo "verified: service active, health OK, 0 jobs, frozen=true" ;;
        3) echo "ERROR: $SERVICE is active but $HEALTH_URL does not answer." >&2
           echo "       Reverting .env and restarting." >&2
           restore_env
           systemctl restart "$SERVICE"; sleep 8
           echo "state after revert: $(systemctl is-active "$SERVICE")" >&2
           tail -20 "$LOGFILE" >&2
           exit 3 ;;
        1) echo "ERROR: $SERVICE did not come back — reverting .env." >&2
           restore_env
           systemctl restart "$SERVICE"; sleep 8
           echo "state after revert: $(systemctl is-active "$SERVICE")" >&2
           tail -20 "$LOGFILE" >&2
           exit 3 ;;
        2) echo "ERROR: this startup did not log SCHEDULERS FROZEN." >&2
           echo "       The deployed code predates the freeze switch, so cron" >&2
           echo "       is stopped and the in-process scheduler is NOT." >&2
           echo "       Reverting .env; deploy the switch, then freeze again." >&2
           restore_env
           systemctl restart "$SERVICE"; sleep 8
           exit 3 ;;
    esac

    echo
    status
}

thaw() {
    if cron_frozen; then
        crontab -l 2>/dev/null | sed -E "s|^$MARKER ||" | crontab -
        echo "cron restored ($(crontab -l | grep -cE '^[^#[:space:]]') live entries)"
    else
        echo "cron was not frozen by this script — untouched"
    fi

    if env_frozen; then
        restore_env
        echo "SCHEDULERS_ENABLED removed from $ENV_FILE"
    else
        echo "SCHEDULERS_ENABLED was not set — untouched"
    fi

    echo
    echo "restarting $SERVICE ..."
    systemctl restart "$SERVICE"
    if ! verify_running ACTIVE; then
        echo "ERROR: $SERVICE did not come back after thaw." >&2
        tail -20 "$LOGFILE" >&2
        exit 3
    fi
    echo "verified: service active"
    echo
    status
    echo
    echo "Outbound anomaly alerts are governed by ANOMALY_ALERTS_ENABLED, not"
    echo "by this script. The line above reports their real state. Detection"
    echo "still runs and records flags either way; only the email path is gated."
}

case "$1" in
    status) status ;;
    freeze) freeze ;;
    thaw)   thaw ;;
    *)      usage ;;
esac
