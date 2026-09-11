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
    echo "--- scheduler state in the service log ---"
    journalctl -u "$SERVICE" --no-pager -n 200 2>/dev/null \
        | grep -E "SCHEDULERS FROZEN|Schedulers started" | tail -2 \
        || echo "(no scheduler line found)"
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

    echo
    echo "restarting $SERVICE so the scheduler restarts with no jobs ..."
    systemctl restart "$SERVICE"
    sleep 6
    echo
    status
    echo
    echo "Confirm the log says SCHEDULERS FROZEN before proceeding. If it says"
    echo "'Schedulers started', the deployed code predates the freeze switch —"
    echo "deploy it first."
}

thaw() {
    if cron_frozen; then
        crontab -l 2>/dev/null | sed -E "s|^$MARKER ||" | crontab -
        echo "cron restored ($(crontab -l | grep -cE '^[^#[:space:]]') live entries)"
    else
        echo "cron was not frozen by this script — untouched"
    fi

    if env_frozen; then
        # Remove only the lines this script added.
        sed -i -E '/^[[:space:]]*SCHEDULERS_ENABLED[[:space:]]*=/d; /^# rollout freeze, added /d' \
            "$ENV_FILE"
        echo "SCHEDULERS_ENABLED removed from $ENV_FILE"
    else
        echo "SCHEDULERS_ENABLED was not set — untouched"
    fi

    echo
    echo "restarting $SERVICE ..."
    systemctl restart "$SERVICE"
    sleep 6
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
