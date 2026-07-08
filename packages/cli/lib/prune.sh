# shellcheck shell=bash
# prune.sh — remove finished/stale agent workspaces safely.

prune_usage() {
  cat <<'EOF'
corral prune — remove agent workspaces whose work is done.

By default a workspace is prunable only when it is SAFE to delete:
  * its worktree has no uncommitted changes, AND
  * its branch is fully merged into the base branch.
This guarantees prune never throws away unmerged or uncommitted work.

Usage:
  corral prune [options]

Options:
  --base <ref>   Branch to test "merged into" against
                 (default: the repo's origin/HEAD, else main, else master).
  --idle         Also prune workspaces with a clean worktree whose agent is
                 idle, even if the branch is not merged (still requires a clean
                 tree; use with care).
  -n, --dry-run  Show what would be pruned without removing anything.
  -f, --force    Skip the per-workspace confirmation prompt.

Examples:
  corral prune --dry-run
  corral prune --base main --force
EOF
}

# Print the base branch ref to test merges against for a given worktree.
_prune_base_for() {
  local wt="$1" base="$2"
  if [ -n "$base" ]; then printf '%s' "$base"; return; fi
  local ref
  ref="$(git -C "$wt" symbolic-ref --quiet refs/remotes/origin/HEAD 2>/dev/null)" \
    && { printf '%s' "${ref#refs/remotes/}"; return; }
  local b
  for b in main master; do
    if git -C "$wt" rev-parse --verify --quiet "$b" >/dev/null; then printf '%s' "$b"; return; fi
  done
  printf '%s' "HEAD"   # fallback: nothing will look "merged" beyond itself
}

cmd_prune() {
  local base="" idle=0 dry=0 force=0
  while [ $# -gt 0 ]; do
    case "$1" in
      -h|--help)   prune_usage; return 0 ;;
      --base)      base="${2:?--base needs a value}"; shift 2 ;;
      --idle)      idle=1; shift ;;
      -n|--dry-run) dry=1; shift ;;
      -f|--force)  force=1; shift ;;
      -*) die "unknown option: $1 (try 'corral prune --help')" ;;
      *)  die "unexpected argument: $1" ;;
    esac
  done

  require_deps herdr jq git
  require_herdr_server

  local list ids ws pruned=0 considered=0
  list="$(herdr_do workspace list)"
  ids="$(printf '%s' "$list" | jq -r '.result.workspaces[].workspace_id')"

  for ws in $ids; do
    local info wt
    info="$(herdr_do workspace get "$ws")"
    wt="$(worktree_path_from_info "$info")"   # linked worktrees only — never the primary checkout
    [ -n "$wt" ] || continue
    considered=$((considered + 1))

    local label status
    label="$(printf '%s'  "$info" | jq -r '.result.workspace.label // "?"')"
    status="$(printf '%s' "$info" | jq -r '.result.workspace.agent_status // "unknown"')"

    # Never touch a worktree with uncommitted changes.
    if [ -n "$(git -C "$wt" status --porcelain 2>/dev/null)" ]; then
      continue
    fi

    local reason=""
    local tgt; tgt="$(_prune_base_for "$wt" "$base")"
    if git -C "$wt" merge-base --is-ancestor HEAD "$tgt" 2>/dev/null; then
      reason="merged into $tgt"
    elif [ "$idle" -eq 1 ] && [ "$status" = "idle" ]; then
      reason="idle, clean tree"
    else
      continue
    fi

    if [ "$dry" -eq 1 ]; then
      info "would prune $ws ($label) — $reason"
      pruned=$((pruned + 1))
      continue
    fi

    if [ "$force" -ne 1 ]; then
      printf 'Prune %s%s%s (%s) — %s? [y/N] ' \
        "$_c_bold" "$ws" "$_c_rst" "$label" "$reason" >&2
      local ans; read -r ans
      case "$ans" in y|Y|yes|YES) ;; *) continue ;; esac
    fi

    herdr_do worktree remove --workspace "$ws" --force >/dev/null
    ok "pruned $ws ($label) — $reason"
    pruned=$((pruned + 1))
  done

  if [ "$pruned" -eq 0 ]; then
    info "nothing to prune ($considered agent workspace(s) checked)"
  elif [ "$dry" -eq 1 ]; then
    info "$pruned of $considered workspace(s) would be pruned"
  fi
}
