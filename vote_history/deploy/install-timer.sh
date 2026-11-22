#!/usr/bin/env bash
# Install the weekly vote-parser baseline check as a user systemd timer.
#
# Idempotent: run it again after editing either unit file and it reinstalls and restarts
# cleanly. It copies rather than symlinks, because systemd reads these at daemon-reload and
# a unit file living in a git worktree would change under it on a branch switch.
#
#   vote_history/deploy/install-timer.sh            # install and enable
#   vote_history/deploy/install-timer.sh --check     # report state, change nothing
#   vote_history/deploy/install-timer.sh --uninstall # stop, disable, remove

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
UNIT_DIR="$HOME/.config/systemd/user"
NAME="vote-baseline-check"

case "${1:-}" in
    --check)
        systemctl --user list-timers "$NAME.timer" --all --no-pager || true
        echo
        systemctl --user status "$NAME.service" --no-pager -n 20 || true
        echo
        echo "alert state:"
        "${HOME}/.local/bin/job-alert" list 2>/dev/null || echo "  job-alert not installed"
        exit 0 ;;
    --uninstall)
        systemctl --user disable --now "$NAME.timer" 2>/dev/null || true
        rm -f "$UNIT_DIR/$NAME.timer" "$UNIT_DIR/$NAME.service"
        systemctl --user daemon-reload
        echo "removed $NAME"
        exit 0 ;;
    "") : ;;
    *) echo "usage: $0 [--check | --uninstall]" >&2; exit 2 ;;
esac

# Refuse rather than install something that cannot work. A timer that runs weekly and
# delivers nowhere is the problem this replaced.
if [ ! -x "$HOME/.local/bin/job-alert" ] && [ ! -x "$HOME/vault/claude-brain/tools/job-alert" ]; then
    echo "ERROR: job-alert is not installed, so a failure would reach nobody." >&2
    echo "  ln -sf ~/vault/claude-brain/tools/job-alert ~/.local/bin/job-alert" >&2
    exit 1
fi

if [ ! -x "$REPO/.venv/bin/python3" ]; then
    echo "WARNING: $REPO/.venv is missing. parse_votes.py needs pdfplumber:" >&2
    echo "  /usr/bin/python3 -m venv $REPO/.venv" >&2
    echo "  $REPO/.venv/bin/pip install -r $HERE/requirements.txt" >&2
    echo "Installing the timer anyway: the first run will raise an exit-2 alert saying this." >&2
fi

chmod +x "$REPO/vote_history/scripts/baseline-watch"

mkdir -p "$UNIT_DIR"
cp "$HERE/$NAME.service" "$HERE/$NAME.timer" "$UNIT_DIR/"
systemctl --user daemon-reload
systemctl --user enable --now "$NAME.timer"

echo "installed:"
systemctl --user list-timers "$NAME.timer" --all --no-pager
echo
echo "Run it once now without waiting for the timer:"
echo "  systemctl --user start $NAME.service && journalctl --user -u $NAME.service -n 20 --no-pager"
