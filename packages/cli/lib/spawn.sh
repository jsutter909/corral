# shellcheck shell=bash
# spawn.sh — create an isolated agent workspace in a fresh git worktree.

spawn_usage() {
  cat <<EOF
corral spawn — launch an isolated agent workspace in a fresh git worktree.

Usage:
  corral spawn <repo> [branch] [options]

Layout (one herdr workspace per agent):
  +----------------+-------------+
  |                | terminal    |   left  : the agent (Claude Code by default),
  |   agent pane   +-------------+           full height
  |                | terminal    |   right : two terminals stacked, both cwd'd
  +----------------+-------------+           into the worktree

Arguments:
  <repo>            Path inside the git repo to branch from (e.g. ~/dev/app or .)
  [branch]          Branch name for the worktree
                    (default: <prefix>/<repo>-<timestamp>)

Options:
  --agent <name>    Agent to launch in the left pane, or "none" for a blank shell
                    (default: $CORRAL_AGENT). Any herdr-integrated agent works:
                    claude, codex, copilot, droid, opencode, cursor, ...
  --base <ref>      Base ref to branch the worktree from (default: current HEAD)
  --ratio <0..1>    Agent (left) pane share of width (default: $CORRAL_RATIO)
  --label <text>    Workspace label (default: derived from the branch name)
  --no-focus        Create the workspace without switching focus to it

Examples:
  corral spawn ~/dev/app
  corral spawn ~/dev/app feature/checkout
  corral spawn . bugfix/tax --base main --agent codex --ratio 0.55
EOF
}

cmd_spawn() {
  local repo_arg="" branch="" base="$CORRAL_BASE" ratio="$CORRAL_RATIO"
  local agent="$CORRAL_AGENT" label="" focus=1

  # First non-flag positional is the repo, second is the branch.
  local positional=()
  while [ $# -gt 0 ]; do
    case "$1" in
      -h|--help) spawn_usage; return 0 ;;
      --agent)   agent="${2:?--agent needs a value}"; shift 2 ;;
      --base)    base="${2:?--base needs a value}"; shift 2 ;;
      --ratio)   ratio="${2:?--ratio needs a value}"; shift 2 ;;
      --label)   label="${2:?--label needs a value}"; shift 2 ;;
      --no-focus) focus=0; shift ;;
      --) shift; while [ $# -gt 0 ]; do positional+=("$1"); shift; done ;;
      -*) die "unknown option: $1 (try 'corral spawn --help')" ;;
      *)  positional+=("$1"); shift ;;
    esac
  done
  repo_arg="${positional[0]:-}"
  branch="${positional[1]:-}"
  [ -n "$repo_arg" ] || { spawn_usage; die "missing <repo> argument"; }

  require_deps herdr jq git
  require_herdr_server

  # Resolve to the repo root so the worktree anchors correctly.
  local repo
  repo="$(git -C "$repo_arg" rev-parse --show-toplevel 2>/dev/null)" \
    || die "'$repo_arg' is not inside a git repository"
  local name; name="$(basename "$repo")"

  # Default branch: unique + timestamped so parallel agents never collide.
  if [ -z "$branch" ]; then
    branch="${CORRAL_BRANCH_PREFIX}/${name}-$(date +%Y%m%d-%H%M%S)"
  fi
  [ -n "$label" ] || label="$(basename "$branch")"

  # 1) Create the git worktree + a fresh, isolated workspace.
  local create_args=(worktree create --cwd "$repo" --branch "$branch" --label "$label" --no-focus)
  [ -n "$base" ] && create_args+=(--base "$base")
  local resp; resp="$(herdr_do "${create_args[@]}")"

  local ws left wt
  ws="$(json_get "$resp" '.result.workspace.workspace_id')"
  left="$(json_get "$resp" '.result.root_pane.pane_id')"
  wt="$(json_get "$resp" '.result.worktree.path')"

  # 2) Split the root pane: agent on the left, right column takes (1 - ratio).
  local rtop rbot
  rtop="$(json_get "$(herdr_do pane split "$left" --direction right --ratio "$ratio" --no-focus)" \
          '.result.pane.pane_id')"

  # 3) Split the right column horizontally into two stacked terminals.
  rbot="$(json_get "$(herdr_do pane split "$rtop" --direction down --ratio 0.5 --no-focus)" \
          '.result.pane.pane_id')"

  # 4) Launch the agent in the left pane (unless "none").
  if [ "$agent" != "none" ] && [ -n "$agent" ]; then
    herdr_do pane run "$left" "$agent" >/dev/null
  fi

  # 5) Focus the new workspace (lands on the left/agent pane).
  [ "$focus" -eq 1 ] && herdr_do workspace focus "$ws" >/dev/null

  ok "agent workspace ${_c_bold}${ws}${_c_rst} (${label})"
  printf '    repo     %s\n'  "$repo"     >&2
  printf '    branch   %s\n'  "$branch"   >&2
  printf '    worktree %s\n'  "$wt"       >&2
  printf '    agent    %s\n'  "$agent"    >&2
  printf '    panes    agent=%s  term-top=%s  term-bottom=%s\n' "$left" "$rtop" "$rbot" >&2
  printf '\n  Tear down when finished:  %scorral close %s%s\n' "$_c_dim" "$ws" "$_c_rst" >&2
}
