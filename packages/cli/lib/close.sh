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
    ws="$(resolve_workspace "$ref")" || die "no workspace matching '$ref'"
  else
    ws="$(current_workspace)"
    [ -n "$ws" ] || die "could not determine current workspace; pass one (e.g. corral close w4)"
  fi

  local label wt
  label="$(herdr_do workspace get "$ws" | jq -r '.result.workspace.label // "?"')"
  wt="$(workspace_worktree_path "$ws")"

  # Guard: only worktree-backed workspaces are corral/agent workspaces.
  [ -n "$wt" ] || die "workspace $ws ($label) is not a worktree/agent workspace — refusing to close it"

  if [ "$force" -ne 1 ]; then
    printf 'Remove worktree and close workspace %s%s%s (%s)?\n  %s\n[y/N] ' \
      "$_c_bold" "$ws" "$_c_rst" "$label" "$wt" >&2
    local ans; read -r ans
    case "$ans" in y|Y|yes|YES) ;; *) info "aborted"; return 0 ;; esac
  fi

  herdr_do worktree remove --workspace "$ws" --force >/dev/null
  ok "removed worktree and closed workspace $ws ($label)"
}
