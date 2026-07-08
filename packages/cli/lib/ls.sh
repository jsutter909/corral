# shellcheck shell=bash
# ls.sh — list active agent (corral-owned worktree) workspaces.

ls_usage() {
  cat <<'EOF'
corral ls — list active agent workspaces.

Usage:
  corral ls [--json]

Options:
  -j, --json   Emit machine-readable JSON instead of a table.

Shows every corral-owned workspace: its id, label, git branch, agent status,
and worktree path. Table rows go to stdout (the header goes to stderr), so
both `corral ls | grep …` and --json are scriptable.
EOF
}

cmd_ls() {
  local as_json=0
  while [ $# -gt 0 ]; do
    case "$1" in
      -h|--help) ls_usage; return 0 ;;
      -j|--json) as_json=1; shift ;;
      -*) die "unknown option: $1 (try 'corral ls --help')" ;;
      *)  die "unexpected argument: $1" ;;
    esac
  done

  require_deps herdr jq git
  require_herdr_server

  local rows
  rows="$(agent_workspace_rows)" || die "could not list agent workspaces"

  if [ -z "$rows" ]; then
    if [ "$as_json" -eq 1 ]; then printf '[]\n'; else
      info "no active agent workspaces (spawn one with 'corral spawn <repo>')"
    fi
    return 0
  fi

  # Append each worktree's git branch to the rows.
  local full="" ws label status repo wt branch
  while IFS=$'\t' read -r ws label status repo wt; do
    [ -n "$ws" ] || continue
    branch="$(git -C "$wt" rev-parse --abbrev-ref HEAD 2>/dev/null || printf '?')"
    full="${full}${ws}"$'\t'"${label}"$'\t'"${repo}"$'\t'"${branch}"$'\t'"${status}"$'\t'"${wt}"$'\n'
  done <<<"$rows"

  if [ "$as_json" -eq 1 ]; then
    printf '%s' "$full" | jq -R -s '
      split("\n") | map(select(length > 0) | split("\t")
        | {workspace: .[0], label: .[1], repo: .[2],
           branch: .[3], status: .[4], worktree: .[5]})'
    return 0
  fi

  # Header on stderr so piped stdout carries only data rows.
  printf '%s%-10s %-20s %-30s %-9s %s%s\n' "$_c_bold" \
    "WORKSPACE" "LABEL" "BRANCH" "STATUS" "WORKTREE" "$_c_rst" >&2
  printf '%s' "$full" | while IFS=$'\t' read -r ws label repo branch status wt; do
    printf '%-10s %-20s %-30s %-9s %s\n' "$ws" "$label" "$branch" "$status" "$wt"
  done
}
