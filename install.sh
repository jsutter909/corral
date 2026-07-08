#!/usr/bin/env bash
# install.sh — install corral.
#
# Remote (from anywhere):
#   curl -fsSL https://raw.githubusercontent.com/YOURNAME/corral/main/install.sh | bash
#
# Local (from a checkout):
#   ./install.sh
#
# Environment overrides:
#   CORRAL_REPO   git URL to clone           (default: https://github.com/YOURNAME/corral.git)
#   CORRAL_REF    branch/tag to install      (default: main)
#   CORRAL_HOME   where corral lives         (default: ~/.local/share/corral)
#   CORRAL_BIN    dir to symlink `corral`    (default: ~/.local/bin)
set -euo pipefail

REPO="${CORRAL_REPO:-https://github.com/YOURNAME/corral.git}"
REF="${CORRAL_REF:-main}"
HOME_DIR="${CORRAL_HOME:-${XDG_DATA_HOME:-$HOME/.local/share}/corral}"
BIN_DIR="${CORRAL_BIN:-$HOME/.local/bin}"

red=$'\033[31m'; grn=$'\033[32m'; ylw=$'\033[33m'; dim=$'\033[2m'; rst=$'\033[0m'
say()  { printf '%s\n' "$*"; }
ok()   { printf '%s✔%s %s\n' "$grn" "$rst" "$*"; }
warn() { printf '%s!%s %s\n' "$ylw" "$rst" "$*"; }
die()  { printf '%serror:%s %s\n' "$red" "$rst" "$*" >&2; exit 1; }

# --- Locate the source tree: local checkout if we're in one, else clone. ------
src=""
self="${BASH_SOURCE[0]:-}"
if [ -n "$self" ] && [ -f "$self" ]; then
  here="$(cd "$(dirname "$self")" && pwd)"
  [ -f "$here/packages/cli/bin/corral" ] && src="$here"
fi

if [ -z "$src" ]; then
  command -v git >/dev/null || die "git is required to install corral"
  if [ -d "$HOME_DIR/.git" ]; then
    say "${dim}updating existing checkout in $HOME_DIR${rst}"
    git -C "$HOME_DIR" fetch --quiet origin "$REF"
    git -C "$HOME_DIR" checkout --quiet "$REF"
    git -C "$HOME_DIR" pull --quiet --ff-only origin "$REF"
  else
    say "${dim}cloning $REPO -> $HOME_DIR${rst}"
    git clone --quiet --branch "$REF" "$REPO" "$HOME_DIR"
  fi
  src="$HOME_DIR"
fi

# --- Symlink the launcher into PATH. ------------------------------------------
mkdir -p "$BIN_DIR"
ln -sf "$src/packages/cli/bin/corral" "$BIN_DIR/corral"
chmod +x "$src/packages/cli/bin/corral"
ok "corral installed to $BIN_DIR/corral"

# --- Dependency + PATH advice. ------------------------------------------------
missing=()
for dep in herdr jq git; do command -v "$dep" >/dev/null 2>&1 || missing+=("$dep"); done
if [ ${#missing[@]} -gt 0 ]; then
  warn "missing runtime dependencies: ${missing[*]}"
  say  "  corral needs herdr, jq, and git on your PATH. See https://herdr.dev"
fi

case ":$PATH:" in
  *":$BIN_DIR:"*) : ;;
  *) warn "$BIN_DIR is not on your PATH — add this to your shell rc:"
     say  "    export PATH=\"$BIN_DIR:\$PATH\"" ;;
esac

say ""
ok "done — run: ${grn}corral help${rst}"
