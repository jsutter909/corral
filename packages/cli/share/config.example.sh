# corral config — copy to ~/.config/corral/config.sh and edit.
#
#   mkdir -p ~/.config/corral
#   cp "$(dirname "$(readlink -f "$(command -v corral)")")/../share/config.example.sh" \
#      ~/.config/corral/config.sh
#
# This file is sourced by corral as plain bash. Every value can also be set as a
# CORRAL_* environment variable, and any command-line flag overrides both.

# Agent to launch in the left pane. Any herdr-integrated agent works
# (claude, codex, copilot, droid, opencode, cursor, ...). Use "none" for a
# blank shell. Override per-run with: corral spawn <repo> --agent <name>
CORRAL_AGENT=claude

# Agent (left) pane share of the width, 0..1. Higher = wider agent pane.
CORRAL_RATIO=0.6

# Prefix for auto-generated branch names: <prefix>/<repo>-<timestamp>.
CORRAL_BRANCH_PREFIX=agent

# Base ref new worktrees branch from. Empty = current HEAD of the repo.
# e.g. CORRAL_BASE=main
CORRAL_BASE=

# Where herdr checks out corral's worktrees. Corral only ever destroys
# worktrees under this directory (rarely needs changing).
# CORRAL_WORKTREES_DIR="$HOME/.herdr/worktrees"

# Where this config lives (rarely needs changing).
# CORRAL_CONFIG="$HOME/.config/corral/config.sh"
