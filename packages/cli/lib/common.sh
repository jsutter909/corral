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

info()  { printf '%s%s%s\n' "$_c_dim" "$*" "$_c_rst" >&2; }
ok()    { printf '%s✔%s %s\n' "$_c_grn" "$_c_rst" "$*" >&2; }
warn()  { printf '%s!%s %s\n' "$_c_ylw" "$_c_rst" "$*" >&2; }
die()   { printf '%serror:%s %s\n' "$_c_red" "$_c_rst" "$*" >&2; exit 1; }

# Ask a yes/no question on the terminal. Returns 0 on yes, 1 on anything else.
# Reads from /dev/tty (not stdin) so piped input can never auto-confirm a
# destructive action; without a terminal it refuses instead of hanging/dying.
confirm() {
  local prompt="$1" ans
  printf '%s' "$prompt" >&2
  if ! read -r ans 2>/dev/null </dev/tty; then
    printf '\n' >&2
    die "no terminal available for confirmation — use --force to skip the prompt"
  fi
  case "$ans" in y|Y|yes|YES) return 0 ;; *) return 1 ;; esac
}

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
# Config — precedence, later wins: defaults < config file < CORRAL_* env < flags.
# ---------------------------------------------------------------------------
load_config() {
  : "${CORRAL_CONFIG:=${XDG_CONFIG_HOME:-$HOME/.config}/corral/config.sh}"

  # The config file uses plain assignments, so it would clobber environment
  # variables. Snapshot the env first and re-apply it after sourcing, keeping
  # the documented precedence: env beats file, flags (parsed later) beat both.
  local env_agent="${CORRAL_AGENT-}" env_ratio="${CORRAL_RATIO-}"
  local env_prefix="${CORRAL_BRANCH_PREFIX-}" env_base="${CORRAL_BASE-}"
  local env_worktrees="${CORRAL_WORKTREES_DIR-}"
  local env_model="${CORRAL_MODEL-}" env_permission_mode="${CORRAL_PERMISSION_MODE-}"

  if [ -f "$CORRAL_CONFIG" ]; then
    # shellcheck disable=SC1090
    . "$CORRAL_CONFIG"
  fi

  if [ -n "$env_agent" ];     then CORRAL_AGENT="$env_agent"; fi
  if [ -n "$env_ratio" ];     then CORRAL_RATIO="$env_ratio"; fi
  if [ -n "$env_prefix" ];    then CORRAL_BRANCH_PREFIX="$env_prefix"; fi
  if [ -n "$env_base" ];      then CORRAL_BASE="$env_base"; fi
  if [ -n "$env_worktrees" ]; then CORRAL_WORKTREES_DIR="$env_worktrees"; fi
  if [ -n "$env_model" ];           then CORRAL_MODEL="$env_model"; fi
  if [ -n "$env_permission_mode" ]; then CORRAL_PERMISSION_MODE="$env_permission_mode"; fi

  # Built-in defaults for anything still unset.
  : "${CORRAL_AGENT:=claude}"           # agent to launch in the left pane (or "none")
  : "${CORRAL_RATIO:=0.4}"              # left (agent) pane share of width, 0..1
  : "${CORRAL_BRANCH_PREFIX:=agent}"    # prefix for auto-generated branch names
  : "${CORRAL_BASE:=}"                  # base ref for new worktrees ("" = current HEAD)
  : "${CORRAL_WORKTREES_DIR:=$HOME/.herdr/worktrees}"  # where herdr checks out corral's worktrees
  : "${CORRAL_MODEL:=}"                 # model for the claude agent ("" = Claude's default)
  : "${CORRAL_PERMISSION_MODE:=}"       # claude permission/edit mode ("" = Claude's default)
}

# ---------------------------------------------------------------------------
# herdr / JSON helpers
# ---------------------------------------------------------------------------

# Run a herdr command, capture stdout, and fail loudly on error. herdr's stderr
# passes straight through to the user (capturing it would corrupt the JSON on
# stdout). The `|| rc=$?` keeps errexit from killing the assignment before the
# die branch can report what failed.
# Usage: out="$(herdr_do worktree create --cwd "$repo" ...)"
herdr_do() {
  local out rc=0
  out="$(herdr "$@")" || rc=$?
  if [ "$rc" -ne 0 ]; then
    die "herdr $1 failed (exit $rc)${out:+: $out}"
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

# Single-quote a string for safe reuse in a shell command line. herdr runs the
# `pane run` command string through a shell, so any value we splice in (e.g. a
# free-form --prompt) must be quoted or spaces/metacharacters would break it.
# Wraps in single quotes and escapes embedded single quotes the POSIX way.
shell_quote() {
  printf "'%s'" "${1//\'/\'\\\'\'}"
}

# The workspace id of the pane invoking corral (empty if not inside herdr).
# Always returns 0 so callers can test the output rather than the status.
current_workspace() {
  herdr pane current --current 2>/dev/null \
    | jq -r '.result.pane.workspace_id // empty' 2>/dev/null \
    || true
}

# Resolve a workspace by id (w4) or unique label from a `workspace list` blob
# (exact id match wins over labels). Prints the id.
# Returns: 0 resolved, 1 no match, 2 ambiguous label.
# Takes the blob as an argument so herdr failures die in the caller, not in a
# swallowed subshell.
resolve_workspace() {
  local ref="$1" list="$2" out
  out="$(printf '%s' "$list" | jq -r --arg r "$ref" '
    .result.workspaces as $w
    | [$w[] | select(.workspace_id == $r) | .workspace_id] as $byid
    | [$w[] | select(.label == $r)        | .workspace_id] as $bylabel
    | if ($byid | length) > 0 then $byid[0]
      elif ($bylabel | length) == 1 then $bylabel[0]
      elif ($bylabel | length) > 1 then "AMBIGUOUS"
      else empty end')"
  case "$out" in
    "")        return 1 ;;
    AMBIGUOUS) return 2 ;;
    *)         printf '%s' "$out" ;;
  esac
}

# ---------------------------------------------------------------------------
# Ownership — which workspaces are corral's to touch?
# A corral workspace is a *linked* git worktree that herdr checked out under
# $CORRAL_WORKTREES_DIR. The path check matters: a linked worktree the user
# made by hand (git worktree add + herdr worktree open) is NOT corral's to
# destroy, and the primary repo checkout (is_linked_worktree=false) never is.
# NOTE: agent_workspace_rows applies the same two tests in jq — keep in sync.
# ---------------------------------------------------------------------------

# Print the worktree checkout path from a `workspace get` blob, but only for
# corral-owned workspaces; prints nothing otherwise.
worktree_path_from_info() {
  local wt
  wt="$(printf '%s' "$1" \
    | jq -r '.result.workspace.worktree | select(.is_linked_worktree==true) | .checkout_path // empty')"
  case "$wt" in
    "$CORRAL_WORKTREES_DIR"/*) printf '%s' "$wt" ;;
    *) : ;;
  esac
}

# Emit one TSV row per corral-owned workspace: id, label, status, repo, path.
# Single `workspace list` call — the response already embeds the worktree
# object, so no per-workspace lookups are needed.
agent_workspace_rows() {
  local list
  list="$(herdr_do workspace list)" || return 1
  printf '%s' "$list" | jq -r --arg dir "$CORRAL_WORKTREES_DIR/" '
    .result.workspaces[]
    | select((.worktree.is_linked_worktree // false) == true)
    | select(.worktree.checkout_path | startswith($dir))
    | [.workspace_id, (.label // "?"), (.agent_status // "unknown"),
       (.worktree.repo_name // "?"), .worktree.checkout_path]
    | @tsv'
}
