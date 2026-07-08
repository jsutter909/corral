# shellcheck shell=bash
# common.sh — shared helpers for the corral CLI.
# Sourced by bin/corral before dispatching to a subcommand.

CORRAL_VERSION="0.1.0"

# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------
if [ -t 2 ]; then
  _c_red=$'\033[31m'; _c_grn=$'\033[32m'; _c_ylw=$'\033[33m'
  _c_dim=$'\033[2m';  _c_bold=$'\033[1m'; _c_rst=$'\033[0m'
else
  _c_red=; _c_grn=; _c_ylw=; _c_dim=; _c_bold=; _c_rst=
fi

log()   { printf '%s\n' "$*" >&2; }
info()  { printf '%s%s%s\n' "$_c_dim" "$*" "$_c_rst" >&2; }
ok()    { printf '%s✔%s %s\n' "$_c_grn" "$_c_rst" "$*" >&2; }
warn()  { printf '%s!%s %s\n' "$_c_ylw" "$_c_rst" "$*" >&2; }
die()   { printf '%serror:%s %s\n' "$_c_red" "$_c_rst" "$*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Dependency check — friendly first-run failures instead of cryptic errors.
# ---------------------------------------------------------------------------
require_deps() {
  local missing=()
  local dep
  for dep in "$@"; do
    command -v "$dep" >/dev/null 2>&1 || missing+=("$dep")
  done
  if [ ${#missing[@]} -gt 0 ]; then
    die "missing required command(s): ${missing[*]}
  corral needs: herdr, jq, git. Install the missing tool(s) and retry.
  herdr:  https://herdr.dev"
  fi
}

# Ensure we're talking to a running herdr server (spawn/close/ls all need it).
require_herdr_server() {
  if ! herdr status server >/dev/null 2>&1; then
    die "herdr server is not reachable.
  Start a herdr session first (run 'herdr', or attach with 'herdr --remote <target>')."
  fi
}

# ---------------------------------------------------------------------------
# Config — defaults, then ~/.config/corral/config.sh, then CORRAL_* env, then flags.
# ---------------------------------------------------------------------------
load_config() {
  # Built-in defaults.
  : "${CORRAL_AGENT:=claude}"           # agent to launch in the left pane (or "none")
  : "${CORRAL_RATIO:=0.6}"              # left (agent) pane share of width, 0..1
  : "${CORRAL_BRANCH_PREFIX:=agent}"    # prefix for auto-generated branch names
  : "${CORRAL_BASE:=}"                  # base ref for new worktrees ("" = current HEAD)
  : "${CORRAL_CONFIG:=${XDG_CONFIG_HOME:-$HOME/.config}/corral/config.sh}"

  # User config file can set/override any CORRAL_* value. Env vars set before the
  # file win only if the file guards with := ; to let the file take precedence we
  # source it, then re-apply nothing. Flags (parsed later) always win.
  if [ -f "$CORRAL_CONFIG" ]; then
    # shellcheck disable=SC1090
    . "$CORRAL_CONFIG"
  fi
}

# ---------------------------------------------------------------------------
# herdr / JSON helpers
# ---------------------------------------------------------------------------

# Run a herdr command, capture stdout, and fail loudly on an API error object.
# Usage: out="$(herdr_do worktree create --cwd "$repo" ...)"
herdr_do() {
  local out rc
  out="$(herdr "$@" 2>&1)"; rc=$?
  if [ $rc -ne 0 ]; then
    die "herdr $1 failed (exit $rc): $out"
  fi
  # herdr reports API-level failures as {"error":{...}} with a zero exit.
  if printf '%s' "$out" | jq -e 'has("error")' >/dev/null 2>&1; then
    local msg
    msg="$(printf '%s' "$out" | jq -r '.error.message // .error.code // "unknown error"')"
    die "herdr $1: $msg"
  fi
  printf '%s' "$out"
}

# Extract a jq path from a JSON blob, dying if the value is null/empty.
# Usage: id="$(json_get "$out" '.result.workspace.workspace_id')"
json_get() {
  local blob="$1" path="$2" val
  val="$(printf '%s' "$blob" | jq -r "$path // empty")"
  [ -n "$val" ] || die "unexpected herdr response (missing $path)"
  printf '%s' "$val"
}

# The workspace id of the pane invoking corral (empty if not inside herdr).
current_workspace() {
  herdr pane current --current 2>/dev/null \
    | jq -r '.result.pane.workspace_id // empty' 2>/dev/null
}

# Resolve a workspace by id (w4) or by label (checkout-fix). Prints the id.
resolve_workspace() {
  local ref="$1"
  [ -n "$ref" ] || return 1
  local list; list="$(herdr_do workspace list)"
  # Exact id match first, then unique label match.
  local byid; byid="$(printf '%s' "$list" \
    | jq -r --arg r "$ref" '.result.workspaces[] | select(.workspace_id==$r) | .workspace_id')"
  if [ -n "$byid" ]; then printf '%s' "$byid"; return 0; fi
  local bylabel; bylabel="$(printf '%s' "$list" \
    | jq -r --arg r "$ref" '.result.workspaces[] | select(.label==$r) | .workspace_id')"
  local n; n="$(printf '%s\n' "$bylabel" | grep -c .)"
  if [ "$n" -eq 1 ]; then printf '%s' "$bylabel"; return 0; fi
  if [ "$n" -gt 1 ]; then die "'$ref' matches multiple workspaces; use the workspace id"; fi
  return 1
}

# Is this a corral/agent workspace? Only *linked* worktrees qualify — the
# primary repo checkout (is_linked_worktree=false) must never be touched by
# close/prune. Prints the worktree checkout path, or nothing.
workspace_worktree_path() {
  local ws="$1"
  herdr_do workspace get "$ws" \
    | jq -r '.result.workspace.worktree | select(.is_linked_worktree==true) | .checkout_path // empty'
}

# Same, but takes an already-fetched `workspace get` blob (avoids a second call).
worktree_path_from_info() {
  printf '%s' "$1" \
    | jq -r '.result.workspace.worktree | select(.is_linked_worktree==true) | .checkout_path // empty'
}
