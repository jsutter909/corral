# GENERATED FILE — do not edit by hand.
# Source of truth: packages/cli/src/corral/settings.py
# Regenerate with: python -m corral.generate (or: make generate)

# corral config — copy to ~/.config/corral/config.sh and edit.
#
#   mkdir -p ~/.config/corral
#   cp "$(dirname "$(readlink -f "$(command -v corral)")")/../share/config.example.sh" \
#      ~/.config/corral/config.sh
#
# corral parses this file for plain CORRAL_* assignments (quotes and $HOME/~
# expansion supported; arbitrary shell is ignored). Every value can also be
# set as a CORRAL_* environment variable, and any command-line flag overrides
# both.

# Agent to launch in the left pane. Any herdr-integrated agent works
# (claude, codex, copilot, droid, opencode, cursor, ...). Use "none" for a
# blank shell. Override per-run with: corral spawn <repo> --agent <name>
CORRAL_AGENT=claude

# Model for the Claude agent (claude only). Empty = Claude's default.
# Override per-run with: corral spawn <repo> --model <name>
# CORRAL_MODEL=

# Claude permission/edit mode (claude only): default, acceptEdits, plan,
# bypassPermissions. Empty = Claude's default.
# Override per-run with: corral spawn <repo> --permission-mode <mode>
# CORRAL_PERMISSION_MODE=

# Agent (left) pane share of the width, 0..1. Higher = wider agent pane.
CORRAL_RATIO=0.4

# Run a repo's committed .corral/setup.sh in the agent pane before the agent
# starts (chained with &&, so the agent only launches if setup succeeds).
# Set to 0 to disable. Override per-run with: corral spawn <repo> --no-setup
# CORRAL_SETUP=1

# Run a worktree's .corral/cleanup.sh before it is removed on close/prune (the
# teardown counterpart to setup.sh; runs as the script exists at that moment).
# If cleanup fails the removal is aborted (worktree kept) unless you pass
# --force. Set to 0 to disable, or skip per-run with: corral close --no-cleanup
# CORRAL_CLEANUP=1

# IDE opened by 'corral open': vscode or cursor.
# Override per-run with: corral open <workspace> --ide <name>
# CORRAL_IDE=vscode

# SSH host used in the Remote-SSH links 'corral open' prints when the herdr
# session is remote (herdr --remote). Must match how YOUR machine reaches this
# one — a Host entry in your local ~/.ssh/config. Empty = this machine's
# hostname. Override per-run with: corral open <workspace> --host <host>
# CORRAL_SSH_HOST=

# Prefix for auto-generated branch names: <prefix>/<repo>-<timestamp>.
CORRAL_BRANCH_PREFIX=agent

# Base ref new worktrees branch from. Empty = current HEAD of the repo.
# e.g. CORRAL_BASE=main
CORRAL_BASE=

# Where herdr checks out corral's worktrees. Corral only ever destroys
# worktrees under this directory (rarely needs changing).
# CORRAL_WORKTREES_DIR="$HOME/.herdr/worktrees"

# Where 'corral resource' keeps its pools and leases. One database per
# machine — all workspaces share it (rarely needs changing).
# CORRAL_RESOURCES_DB="$HOME/.local/state/corral/resources.db"

# Address 'corral monitor' binds its web UI to. Loopback by default, so the
# dashboard is reachable only from this machine. Set to 0.0.0.0 to expose it on
# the network. Override per-run with: corral monitor --host <addr>
# CORRAL_MONITOR_HOST=127.0.0.1

# Port 'corral monitor' serves its web UI on.
# Override per-run with: corral monitor --port <port>
# CORRAL_MONITOR_PORT=8477

# Where this config lives (rarely needs changing).
# CORRAL_CONFIG="$HOME/.config/corral/config.sh"
