#!/usr/bin/env bash
#
# The P0-A discovery checkout, kept OUT of the production tree.
#
#     bash backend/scripts/p0a_gate.sh setup     create or refresh it
#     bash backend/scripts/p0a_gate.sh status    where both trees are
#     bash backend/scripts/p0a_gate.sh remove    delete the worktree
#
# Why this exists rather than `git checkout p0a-correctness` in
# /opt/asx-screener:
#
# Production cron is live. The daily pipeline fires at 18:30 AEST and runs
# build_screener_universe.py and composite_score.py from whatever is checked
# out. While the schedulers were frozen a switched tree was harmless; now it
# means a tree left on p0a-correctness would execute the V2 canonical writer
# against PRODUCTION -- writing V2 semantics, sidecars and run attribution
# outside every gate, because someone forgot to switch back.
#
# A rule that depends on remembering to switch back is not a control. So the
# production checkout stays permanently on main and P0-A work happens in a
# separate worktree. The production tree should be boring.
#
# Two things a bare `git worktree add` would leave broken:
#
#   backend/.env is gitignored, so the worktree has no database credential.
#   Symlinked, never copied: one file, one place, no secret in /tmp.
#
#   nothing would stop the worktree being created at the production path, or
#   the production tree being left off main. Both are checked here.

set -u

GATE_DIR=${GATE_DIR:-/tmp/p0a-gate}
GATE_BRANCH=${GATE_BRANCH:-p0a-correctness}
PROD_DIR=${PROD_DIR:-/opt/asx-screener}
PROD_BRANCH=${PROD_BRANCH:-main}

usage() { echo "usage: $0 {setup|status|remove}" >&2; exit 2; }
[ $# -eq 1 ] || usage

if [ ! -d "$PROD_DIR/.git" ]; then
    echo "ERROR: $PROD_DIR is not a git checkout — is this the ASX host?" >&2
    exit 2
fi

# The one thing that must never happen.
case "$(cd -- "$GATE_DIR" 2>/dev/null && pwd || echo "$GATE_DIR")" in
    "$PROD_DIR"|"$PROD_DIR"/*)
        echo "REFUSED: the gate checkout may not live inside $PROD_DIR." >&2
        echo "         That is the failure mode this script exists to remove." >&2
        exit 3 ;;
esac

prod_branch() { git -C "$PROD_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null; }

status() {
    local pb
    pb=$(prod_branch)
    echo "production : $PROD_DIR"
    echo "             branch $pb  $([ "$pb" = "$PROD_BRANCH" ] \
        && echo "ok" || echo "<- NOT $PROD_BRANCH — cron runs this tree")"
    echo "             $(git -C "$PROD_DIR" log --oneline -1 2>/dev/null)"
    echo
    if [ -d "$GATE_DIR/.git" ] || [ -f "$GATE_DIR/.git" ]; then
        echo "gate       : $GATE_DIR"
        echo "             branch $(git -C "$GATE_DIR" rev-parse --abbrev-ref HEAD)"
        echo "             $(git -C "$GATE_DIR" log --oneline -1)"
        echo "             .env $([ -e "$GATE_DIR/backend/.env" ] \
            && echo present || echo "MISSING — scripts cannot reach the database")"
    else
        echo "gate       : not created (run: $0 setup)"
    fi
}

setup() {
    local pb
    pb=$(prod_branch)
    if [ "$pb" != "$PROD_BRANCH" ]; then
        echo "REFUSED: $PROD_DIR is on '$pb', not '$PROD_BRANCH'." >&2
        echo "         Put production back on $PROD_BRANCH first; cron executes" >&2
        echo "         that tree and this script will not paper over it." >&2
        exit 3
    fi

    git -C "$PROD_DIR" fetch --quiet origin

    # Only reset to the remote when the remote ref actually resolves. Without
    # this guard git emits "Use '--' to separate paths from revisions" and
    # leaves the tree at whatever it was, which is the worst of both: a
    # confusing error and an unrefreshed gate.
    sync_to_origin() {
        if git -C "$GATE_DIR" rev-parse --verify --quiet \
               "origin/$GATE_BRANCH" >/dev/null; then
            git -C "$GATE_DIR" reset --hard --quiet "origin/$GATE_BRANCH"
        else
            echo "note: origin/$GATE_BRANCH does not resolve; gate left at" \
                 "its current commit"
        fi
    }

    if [ -d "$GATE_DIR/.git" ] || [ -f "$GATE_DIR/.git" ]; then
        echo "refreshing existing worktree at $GATE_DIR"
        git -C "$GATE_DIR" checkout --quiet "$GATE_BRANCH"
        sync_to_origin
    else
        # Stale metadata first. /tmp is cleared on reboot, so the directory
        # disappearing while git still believes a worktree is registered
        # there is the NORMAL case, not an edge one — and `worktree add` then
        # refuses. Without this the script reported success while creating
        # nothing, which is how the first version of it behaved.
        git -C "$PROD_DIR" worktree prune

        echo "creating worktree at $GATE_DIR on $GATE_BRANCH"
        git -C "$PROD_DIR" worktree add --quiet \
            "$GATE_DIR" "$GATE_BRANCH" 2>/dev/null \
          || git -C "$PROD_DIR" worktree add --quiet \
                --track -b "$GATE_BRANCH" "$GATE_DIR" "origin/$GATE_BRANCH" \
          || { echo "ERROR: could not create the worktree at $GATE_DIR." >&2
               echo "       git worktree list:" >&2
               git -C "$PROD_DIR" worktree list >&2
               exit 4; }
        sync_to_origin
    fi

    # Fail loudly rather than proceed to link a credential into nothing.
    if [ ! -d "$GATE_DIR/backend" ]; then
        echo "ERROR: $GATE_DIR/backend does not exist after setup; the gate" >&2
        echo "       was not created and nothing below would be meaningful." >&2
        exit 4
    fi

    # The credential stays in exactly one place on disk.
    if [ ! -e "$GATE_DIR/backend/.env" ]; then
        ln -s "$PROD_DIR/backend/.env" "$GATE_DIR/backend/.env" \
          || { echo "ERROR: could not link backend/.env" >&2; exit 4; }
        echo "linked backend/.env -> $PROD_DIR/backend/.env"
    fi

    # It must be a LINK, not a copy.
    #
    # `ln -s` does not always produce a symlink: on Git Bash under Windows it
    # copies, and a copy means the production database credential now exists
    # as a second real file under a world-readable /tmp. The whole point of
    # linking was that the secret stays in one place, so a copy is a refusal
    # rather than a warning — and the copy is deleted before exiting.
    if [ ! -L "$GATE_DIR/backend/.env" ]; then
        rm -f "$GATE_DIR/backend/.env"
        echo "REFUSED: backend/.env was COPIED into $GATE_DIR rather than" >&2
        echo "         symlinked. That puts the database credential in a" >&2
        echo "         second location under /tmp. The copy has been deleted." >&2
        echo "         Link it manually and re-run, or use a gate directory" >&2
        echo "         on a filesystem that supports symlinks." >&2
        exit 4
    fi

    echo
    status
    echo
    echo "run discovery from the gate, never from $PROD_DIR:"
    echo "  bash $GATE_DIR/backend/scripts/p0a_discovery.sh preflight"
}

remove() {
    if [ ! -d "$GATE_DIR" ]; then echo "nothing at $GATE_DIR"; exit 0; fi
    rm -f "$GATE_DIR/backend/.env"          # the symlink, never the target
    git -C "$PROD_DIR" worktree remove --force "$GATE_DIR" 2>/dev/null \
        || rm -rf "$GATE_DIR"
    git -C "$PROD_DIR" worktree prune
    echo "removed $GATE_DIR"
}

case "$1" in
    setup)  setup ;;
    status) status ;;
    remove) remove ;;
    *)      usage ;;
esac
