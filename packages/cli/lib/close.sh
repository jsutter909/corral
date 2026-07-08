# shellcheck shell=bash
# close.sh — tear down an agent workspace (remove worktree + close workspace).

close_usage() {
  cat <<'EOF'
corral close — remove an agent's git worktree and close its workspace.

Usage:
  corral close [workspace] [options]

Arguments:
  [workspace]   Workspace id (w4) or label (checkout-fix).
                Defaults to the workspace you're currently in.

Options:
  -f, --force   Skip the confirmation prompt.

Guard: corral refuses to close a workspace that is not worktree-backed, so it
can never destroy your command/control workspace.

Examples:
  corral close                 # close the workspace you're in (prompts)
  corral close checkout-fix    # close by label
  corral close w4 --force
EOF
}

cmd_close() {
  local ref="" force=0
  while [ $# -gt 0 ]; do
    case "$1" in
      -h|--help)  close_usage; return 0 ;;
      -f|--force) force=1; shift ;;
      -*) die "unknown option: $1 (try 'corral close --help')" ;;
      *)  ref="$1"; shift ;;
    esac
  done

  require_deps herdr jq
  require_herdr_server

  local ws
  if [ -n "$ref" ]; then
    local list rc=0
    list="$(herdr_do workspace list)"
    ws="$(resolve_workspace "$ref" "$list")" || rc=$?
    [ "$rc" -ne 2 ] || die "'$ref' matches multiple workspaces; use the workspace id"
    [ -n "$ws" ] || die "no workspace matching '$ref'"
  else
    ws="$(current_workspace)"
    [ -n "$ws" ] || die "could not determine current workspace; pass one (e.g. corral close w4)"
  fi

  local wsinfo label wt
  wsinfo="$(herdr_do workspace get "$ws")"
  label="$(printf '%s' "$wsinfo" | jq -r '.result.workspace.label // "?"')"
  wt="$(worktree_path_from_info "$wsinfo")"

  # Guard: only corral-owned worktree workspaces may be destroyed.
  [ -n "$wt" ] || die "workspace $ws ($label) is not a corral-managed worktree workspace — refusing to close it"

  if [ "$force" -ne 1 ]; then
    local prompt
    prompt="$(printf 'Remove worktree and close workspace %s%s%s (%s)?\n  %s\n[y/N] ' \
      "$_c_bold" "$ws" "$_c_rst" "$label" "$wt")"
    confirm "$prompt" || { info "aborted"; return 0; }
  fi

  herdr_do worktree remove --workspace "$ws" --force >/dev/null
  ok "removed worktree and closed workspace $ws ($label)"
}
