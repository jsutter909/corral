# shellcheck shell=bash
# ls.sh — list active agent (worktree-backed) workspaces.

ls_usage() {
  cat <<'EOF'
corral ls — list active agent workspaces.

Usage:
  corral ls [--json]

Options:
  --json   Emit machine-readable JSON instead of a table.

Shows every worktree-backed workspace: its id, label, git branch, agent status,
and worktree path.
EOF
}

# Emit one JSON object per agent workspace to stdout.
_ls_collect() {
  local list; list="$(herdr_do workspace list)"
  local ids; ids="$(printf '%s' "$list" | jq -r '.result.workspaces[].workspace_id')"
  local ws
  for ws in $ids; do
    local info wt
    info="$(herdr_do workspace get "$ws")"
    wt="$(worktree_path_from_info "$info")"
    [ -n "$wt" ] || continue   # skip command/control + primary-checkout workspaces
    local label status repo branch
    label="$(printf '%s'  "$info" | jq -r '.result.workspace.label // "?"')"
    status="$(printf '%s' "$info" | jq -r '.result.workspace.agent_status // "unknown"')"
    repo="$(printf '%s'   "$info" | jq -r '.result.workspace.worktree.repo_name // "?"')"
    branch="$(git -C "$wt" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "?")"
    jq -n --arg ws "$ws" --arg label "$label" --arg branch "$branch" \
          --arg status "$status" --arg repo "$repo" --arg wt "$wt" \
      '{workspace:$ws, label:$label, repo:$repo, branch:$branch, status:$status, worktree:$wt}'
  done
}

cmd_ls() {
  local as_json=0
  while [ $# -gt 0 ]; do
    case "$1" in
      -h|--help) ls_usage; return 0 ;;
      --json) as_json=1; shift ;;
      -*) die "unknown option: $1 (try 'corral ls --help')" ;;
      *)  die "unexpected argument: $1" ;;
    esac
  done

  require_deps herdr jq git
  require_herdr_server

  local rows; rows="$(_ls_collect)"

  if [ "$as_json" -eq 1 ]; then
    printf '%s' "$rows" | jq -s '.'
    return 0
  fi

  if [ -z "$rows" ]; then
    info "no active agent workspaces (spawn one with 'corral spawn <repo>')"
    return 0
  fi

  # Aligned table. Header to stderr so stdout stays parseable if piped.
  {
    printf '%s%-10s %-20s %-30s %-9s %s%s\n' "$_c_bold" \
      "WORKSPACE" "LABEL" "BRANCH" "STATUS" "WORKTREE" "$_c_rst"
    printf '%s' "$rows" | jq -r \
      '"\(.workspace)\t\(.label)\t\(.branch)\t\(.status)\t\(.worktree)"' \
    | while IFS=$'\t' read -r ws label branch status wt; do
        printf '%-10s %-20s %-30s %-9s %s\n' "$ws" "$label" "$branch" "$status" "$wt"
      done
  } >&2
}
