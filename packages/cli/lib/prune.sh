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
  -b, --base <ref>
                 Branch to test "merged into" against
                 (default: the repo's origin/HEAD, else main, else master;
                 if none of those exist the merged check is skipped entirely).
  -i, --idle     Also prune workspaces with a clean worktree whose agent is
                 idle, even if the branch is not merged (still requires a clean
                 tree; use with care).
  -n, --dry-run  Show what would be pruned without removing anything.
  -f, --force    Skip the per-workspace confirmation prompt, and prune a
                 workspace even if its .corral/cleanup.sh fails (the script
                 still runs).
  --no-cleanup   Do not run .corral/cleanup.sh (also: CORRAL_CLEANUP=0).

If a workspace's worktree contains a .corral/cleanup.sh, corral runs it there
before removing the worktree. If cleanup fails, that workspace is skipped
(worktree kept) unless --force is given.

Examples:
  corral prune --dry-run
  corral prune --base main --force
EOF
}

# Print the base branch ref to test merges against for a given worktree.
# Returns 1 when no base can be resolved — the caller MUST then skip the
# merged check (there is no ref that can safely stand in for one; in
# particular HEAD must never be used, since HEAD is its own ancestor and
# would make every branch look merged).
_prune_base_for() {
  local wt="$1" base="$2"
  if [ -n "$base" ]; then printf '%s' "$base"; return 0; fi
  local ref
  if ref="$(git -C "$wt" symbolic-ref --quiet refs/remotes/origin/HEAD 2>/dev/null)"; then
    printf '%s' "${ref#refs/remotes/}"; return 0
  fi
  local b
  for b in main master; do
    if git -C "$wt" rev-parse --verify --quiet "$b" >/dev/null; then printf '%s' "$b"; return 0; fi
  done
  return 1
}

cmd_prune() {
  local base="" idle=0 dry=0 force=0 cleanup=1
  while [ $# -gt 0 ]; do
    case "$1" in
      -h|--help)   prune_usage; return 0 ;;
      -b|--base)   base="${2:?--base needs a value}"; shift 2 ;;
      -i|--idle)   idle=1; shift ;;
      -n|--dry-run) dry=1; shift ;;
      -f|--force)  force=1; shift ;;
      --no-cleanup) cleanup=0; shift ;;
      -*) die "unknown option: $1 (try 'corral prune --help')" ;;
      *)  die "unexpected argument: $1" ;;
    esac
  done

  require_deps herdr jq git
  require_herdr_server

  local rows
  rows="$(agent_workspace_rows)" || die "could not list agent workspaces"

  local pruned=0 considered=0
  local ws label status repo wt
  while IFS=$'\t' read -r ws label status repo wt; do
    [ -n "$ws" ] || continue
    considered=$((considered + 1))

    # Never touch a worktree with uncommitted changes.
    if [ -n "$(git -C "$wt" status --porcelain 2>/dev/null)" ]; then
      continue
    fi

    local reason="" tgt
    if tgt="$(_prune_base_for "$wt" "$base")" \
       && git -C "$wt" merge-base --is-ancestor HEAD "$tgt" 2>/dev/null; then
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
      local prompt
      prompt="$(printf 'Prune %s%s%s (%s) — %s? [y/N] ' \
        "$_c_bold" "$ws" "$_c_rst" "$label" "$reason")"
      confirm "$prompt" || continue
    fi

    if ! remove_workspace "$ws" "$wt" "$force" "$cleanup"; then
      warn "skipping $ws ($label) — cleanup failed (--force to prune anyway, --no-cleanup to skip the script)"
      continue
    fi
    ok "pruned $ws ($label) — $reason"
    pruned=$((pruned + 1))
  done <<<"$rows"

  if [ "$pruned" -eq 0 ]; then
    info "nothing to prune ($considered agent workspace(s) checked)"
  elif [ "$dry" -eq 1 ]; then
    info "$pruned of $considered workspace(s) would be pruned"
  fi
}
