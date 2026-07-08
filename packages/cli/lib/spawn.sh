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
  -a, --agent <name>    Agent to launch in the left pane, or "none" for a blank shell
                    (default: $CORRAL_AGENT). Any herdr-integrated agent works:
                    claude, codex, copilot, droid, opencode, cursor, ...
  -m, --model <name>    Model for the Claude agent (default: ${CORRAL_MODEL:-Claude default}).
                    claude agent only.
  -P, --permission-mode <mode>
                    Claude permission/edit mode, e.g. acceptEdits, plan
                    (default: ${CORRAL_PERMISSION_MODE:-Claude default}). claude agent only.
  -p, --prompt <text>   Initial prompt to hand the agent on launch. Passed as the
                    agent's first positional argument (ignored for --agent none).
  -b, --base <ref>      Base ref to branch the worktree from (default: current HEAD)
  -r, --ratio <0..1>    Agent (left) pane share of width (default: $CORRAL_RATIO)
  -l, --label <text>    Workspace label (default: derived from the branch name)
  --no-focus        Create the workspace without switching focus to it
  --no-setup        Skip the repo's .corral/setup.sh (also: CORRAL_SETUP=0)

If the repo commits a .corral/setup.sh, spawn runs it in the agent pane first
(bash .corral/setup.sh && <agent>) — the agent only starts once setup succeeds.

Examples:
  corral spawn ~/dev/app
  corral spawn ~/dev/app feature/checkout
  corral spawn . bugfix/tax --base main --agent codex --ratio 0.55
  corral spawn ~/dev/app --prompt "fix the failing tax tests"
EOF
}

# EXIT trap while spawn is mid-flight: if anything failed after the worktree
# was created, roll the partial workspace back so no orphan is left behind.
_spawn_cleanup() {
  local rc=$?
  if [ "$rc" -ne 0 ] && [ -n "${_spawn_partial_ws:-}" ]; then
    warn "spawn failed — removing partially created workspace ${_spawn_partial_ws}"
    herdr worktree remove --workspace "$_spawn_partial_ws" --force >/dev/null 2>&1 || true
  fi
}

# Compose the command string for the agent pane: the repo's setup script
# chained (&&) before the agent, so the agent only starts if setup succeeds.
# The pane's cwd is the worktree, so the script path stays relative. A prompt
# becomes the agent's first positional argument, shell-quoted so spaces and
# metacharacters survive herdr running the command string.
# Usage: spawn_launch_cmd <agent> <model> <permission_mode> <prompt> <setup 0|1>
# Prints the command; prints nothing when there is nothing to run.
spawn_launch_cmd() {
  local agent="$1" model="$2" permission_mode="$3" prompt="$4" setup="$5"
  local launch=""
  if [ "$agent" != "none" ] && [ -n "$agent" ]; then
    launch="$agent"
    if [ "$agent" = "claude" ]; then
      [ -n "$model" ]           && launch="$launch --model $model"
      [ -n "$permission_mode" ] && launch="$launch --permission-mode $permission_mode"
    fi
    [ -n "$prompt" ] && launch="$launch $(shell_quote "$prompt")"
  fi
  if [ "$setup" = "1" ]; then
    if [ -n "$launch" ]; then
      launch="bash .corral/setup.sh && $launch"
    else
      launch="bash .corral/setup.sh"
    fi
  fi
  printf '%s' "$launch"
}

cmd_spawn() {
  local repo_arg="" branch="" base="$CORRAL_BASE" ratio="$CORRAL_RATIO"
  local agent="$CORRAL_AGENT" label="" focus=1 setup="$CORRAL_SETUP"
  local model="$CORRAL_MODEL" permission_mode="$CORRAL_PERMISSION_MODE"
  local prompt=""

  # First non-flag positional is the repo, second is the branch.
  local positional=()
  while [ $# -gt 0 ]; do
    case "$1" in
      -h|--help) spawn_usage; return 0 ;;
      -a|--agent)   agent="${2:?--agent needs a value}"; shift 2 ;;
      -m|--model)   model="${2:?--model needs a value}"; shift 2 ;;
      -P|--permission-mode) permission_mode="${2:?--permission-mode needs a value}"; shift 2 ;;
      -p|--prompt)  prompt="${2?--prompt needs a value}"; shift 2 ;;
      -b|--base)    base="${2:?--base needs a value}"; shift 2 ;;
      -r|--ratio)   ratio="${2:?--ratio needs a value}"; shift 2 ;;
      -l|--label)   label="${2:?--label needs a value}"; shift 2 ;;
      --no-focus) focus=0; shift ;;
      --no-setup) setup=0; shift ;;
      --) shift; while [ $# -gt 0 ]; do positional+=("$1"); shift; done ;;
      -*) die "unknown option: $1 (try 'corral spawn --help')" ;;
      *)  positional+=("$1"); shift ;;
    esac
  done
  repo_arg="${positional[0]:-}"
  branch="${positional[1]:-}"
  [ -n "$repo_arg" ] || { spawn_usage; die "missing <repo> argument"; }

  # Validate --ratio before any herdr call so a typo can't half-build a workspace.
  local ratio_re='^(0(\.[0-9]+)?|1(\.0+)?|\.[0-9]+)$'
  [[ "$ratio" =~ $ratio_re ]] || die "--ratio must be a number between 0 and 1 (got '$ratio')"

  require_deps herdr jq git
  require_herdr_server

  # Resolve to the repo root so the worktree anchors correctly.
  local repo
  repo="$(git -C "$repo_arg" rev-parse --show-toplevel 2>/dev/null)" \
    || die "'$repo_arg' is not inside a git repository"
  local name; name="$(basename "$repo")"

  # Default branch: timestamp + pid so parallel spawns in the same second
  # still get distinct names.
  if [ -z "$branch" ]; then
    branch="${CORRAL_BRANCH_PREFIX}/${name}-$(date +%Y%m%d-%H%M%S)-$$"
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

  # Any failure past this point must not leave a half-built workspace behind.
  _spawn_partial_ws="$ws"
  trap _spawn_cleanup EXIT

  # 2) Split the root pane: agent on the left, right column takes (1 - ratio).
  local split_resp rtop rbot
  split_resp="$(herdr_do pane split "$left" --direction right --ratio "$ratio" --no-focus)"
  rtop="$(json_get "$split_resp" '.result.pane.pane_id')"

  # 3) Split the right column horizontally into two stacked terminals.
  split_resp="$(herdr_do pane split "$rtop" --direction down --ratio 0.5 --no-focus)"
  rbot="$(json_get "$split_resp" '.result.pane.pane_id')"

  # 4) Launch in the left pane. If the repo ships a .corral/setup.sh (present
  #    in the fresh worktree because it's checked out from the base ref), chain
  #    it before the agent: the agent only starts once setup succeeds, and a
  #    failure stays visible in the pane (the workspace is kept, no rollback).
  local run_setup=0
  if [ "$setup" = "1" ] && [ -f "$wt/.corral/setup.sh" ]; then
    run_setup=1
  fi

  # --model, --permission-mode, and --prompt only make sense for an agent;
  # warn (rather than silently pass unknown flags) when they'd be dropped.
  if [ "$agent" != "claude" ] && [ "$agent" != "none" ] && [ -n "$agent" ] \
     && { [ -n "$model" ] || [ -n "$permission_mode" ]; }; then
    warn "--model/--permission-mode only apply to the claude agent; ignoring for '$agent'"
  fi
  if { [ "$agent" = "none" ] || [ -z "$agent" ]; } && [ -n "$prompt" ]; then
    warn "--prompt has no effect with --agent none; ignoring"
  fi

  local launch
  launch="$(spawn_launch_cmd "$agent" "$model" "$permission_mode" "$prompt" "$run_setup")"
  if [ -n "$launch" ]; then
    herdr_do pane run "$left" "$launch" >/dev/null
  fi

  # 5) Focus the new workspace (lands on the left/agent pane).
  [ "$focus" -eq 1 ] && herdr_do workspace focus "$ws" >/dev/null

  # Success — disarm the cleanup trap.
  _spawn_partial_ws=""
  trap - EXIT

  ok "agent workspace ${_c_bold}${ws}${_c_rst} (${label})"
  printf '    repo     %s\n'  "$repo"     >&2
  printf '    branch   %s\n'  "$branch"   >&2
  printf '    worktree %s\n'  "$wt"       >&2
  printf '    agent    %s\n'  "$agent"    >&2
  if [ "$run_setup" -eq 1 ]; then
    printf '    setup    .corral/setup.sh\n' >&2
  fi
  if [ "$agent" = "claude" ]; then
    [ -n "$model" ]           && printf '    model    %s\n' "$model"           >&2
    [ -n "$permission_mode" ] && printf '    mode     %s\n' "$permission_mode" >&2
  fi
  [ -n "$prompt" ] && [ "$agent" != "none" ] && printf '    prompt   %s\n' "$prompt" >&2
  printf '    panes    agent=%s  term-top=%s  term-bottom=%s\n' "$left" "$rtop" "$rbot" >&2
  printf '\n  Tear down when finished:  %scorral close %s%s\n' "$_c_dim" "$ws" "$_c_rst" >&2
}
