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
# What this does NOT do: the anomaly alert worker stays frozen after the
# rollout. It is excluded from `thaw` deliberately and comes back only through
# its own detector/re-detection sequence. Its daily crash is currently the
# only thing preventing defect-derived alerts from reaching inboxes, and a
# thaw that "restores everything" would undo that by accident.

set -u

ASX_ROOT=${ASX_ROOT:-/opt/asx-screener}
STATE_DIR=${STATE_DIR:-/var/backups/p0a/freeze}
ENV_FILE="$ASX_ROOT/backend/.env"
SERVICE=${SERVICE:-asx-backend}
PYBIN=${PYBIN:-$ASX_ROOT/asx-venv/bin/python}
# The unit writes StandardOutput and StandardError to this file rather than to
# journald, so this is where the scheduler line actually lands. Looking in
# journalctl reported "no scheduler line found" while the answer sat here.
LOGFILE=${LOGFILE:-$ASX_ROOT/logs/backend.log}
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
    echo "scheduler:   $(env_frozen && echo FROZEN || echo active)"
    echo "service:     $(systemctl is-active "$SERVICE" 2>/dev/null)"
    echo
    echo "--- jobs in flight ---"
    pgrep -af 'daily_pipeline|weekly_refresh|weekly_pipeline|top5_strategy|daily_compute|sector_bench|anomaly_detect|anomaly_alert|build_screener_universe' \
        || echo "none"
    echo
    echo "--- what the process actually did (last startup) ---"
    # The unit writes StandardOutput to a file, not journald, so journalctl
    # shows only systemd's own lines. Looking there reported "no scheduler
    # line found" while the answer sat in backend.log.
    grep -hE "SCHEDULERS FROZEN|Schedulers started" "$LOGFILE" 2>/dev/null \
        | tail -2 || echo "(no scheduler line in $LOGFILE)"
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

# Did the service actually come back, and did it do what was asked? Both, since
# a running service that ignored the freeze is the dangerous case: it looks
# fine and keeps writing.
verify_running() {
    local want="$1"           # FROZEN | ACTIVE
    sleep 8
    if [ "$(systemctl is-active "$SERVICE")" != "active" ]; then
        return 1
    fi
    if [ "$want" = "FROZEN" ]; then
        tail -50 "$LOGFILE" 2>/dev/null | grep -q "SCHEDULERS FROZEN" || return 2
    fi
    return 0
}

restore_env() {
    sed -i -E '/^[[:space:]]*SCHEDULERS_ENABLED[[:space:]]*=/d; /^# rollout freeze, added /d' \
        "$ENV_FILE"
}

freeze() {
    mkdir -p "$STATE_DIR" && chmod 700 "$STATE_DIR"
    local stamp; stamp=$(date -u +%Y%m%dT%H%M%SZ)

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

    # Prove the app can still load its configuration BEFORE restarting it.
    # Writing SCHEDULERS_ENABLED into .env without the matching field in
    # config.py took the API down for eight minutes on 11 Sep 2026 — the
    # variable did not fall back to a default, it failed Settings()
    # construction at import. This check turns that into an aborted freeze.
    echo
    echo "checking the app can still load its settings ..."
    if ! err=$(settings_load); then
        echo "ERROR: settings will not load with this .env — reverting." >&2
        echo "$err" | tail -5 >&2
        restore_env
        echo "ENV REVERTED. The service was NOT restarted and is untouched." >&2
        exit 3
    fi
    echo "settings load cleanly."

    echo
    echo "restarting $SERVICE so the scheduler restarts with no jobs ..."
    systemctl restart "$SERVICE"

    verify_running FROZEN
    case $? in
        0) echo "verified: service active and SCHEDULERS FROZEN in the log" ;;
        1) echo "ERROR: $SERVICE did not come back — reverting .env." >&2
           restore_env
           systemctl restart "$SERVICE"; sleep 8
           echo "state after revert: $(systemctl is-active "$SERVICE")" >&2
           tail -20 "$LOGFILE" >&2
           exit 3 ;;
        2) echo "ERROR: service is running but the log does not say FROZEN." >&2
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
    echo "REMINDER: the anomaly alert worker is now scheduled again. If its"
    echo "detector/re-detection sequence is not complete, stop it before the"
    echo "next 8:35pm run."
}

case "$1" in
    status) status ;;
    freeze) freeze ;;
    thaw)   thaw ;;
    *)      usage ;;
esac
