# shellcheck shell=bash
# wait.sh — block until an agent reaches a status or its output matches text.

wait_usage() {
  cat <<'EOF'
corral wait — block until a workspace's agent reaches a status (or prints
matching output). Exits 0 when the condition is met, non-zero on timeout.

Usage:
  corral wait <workspace> [options]

Arguments:
  <workspace>   Workspace id (w4) or label (checkout-fix).
                Defaults to the workspace you're currently in.

Options:
  -s, --status <s>    idle | working | blocked | done | unknown (default: idle).
  -m, --match <text>  Wait for output matching <text> instead of a status.
  --regex             Treat --match as a regular expression.
  -t, --timeout <ms>  Give up after this many milliseconds (default: 300000).
  -p, --pane <id>     Watch a specific pane instead of the workspace's agent pane.

Note: a status wait returns as soon as the agent is *currently* in that
status. Right after 'corral send', the agent may still report idle for a
moment — wait for "working" first, or use --match, when that matters:
  corral send w4 "fix the failing test" && corral wait w4 --status working \
    --timeout 15000 ; corral wait w4 --status idle --timeout 600000

Examples:
  corral wait w4                          # until the agent goes idle
  corral wait w4 --status blocked         # until it needs human input
  corral wait w4 --match "All tests passed" --timeout 120000
EOF
}

cmd_wait() {
  local ref="" status="idle" match="" regex=0 timeout="300000" pane=""
  local status_set=0
  while [ $# -gt 0 ]; do
    case "$1" in
      -h|--help) wait_usage; return 0 ;;
      -s|--status)  status="${2:?--status needs a value}"; status_set=1; shift 2 ;;
      -m|--match)   match="${2:?--match needs a value}"; shift 2 ;;
      --regex)      regex=1; shift ;;
      -t|--timeout) timeout="${2:?--timeout needs a value}"; shift 2 ;;
      -p|--pane)    pane="${2:?--pane needs a value}"; shift 2 ;;
      -*) die "unknown option: $1 (try 'corral wait --help')" ;;
      *)  [ -z "$ref" ] || die "unexpected argument: $1"; ref="$1"; shift ;;
    esac
  done

  [ "$status_set" -eq 1 ] && [ -n "$match" ] \
    && die "--status and --match are mutually exclusive"
  case "$status" in idle|working|blocked|done|unknown) : ;;
    *) die "--status must be idle, working, blocked, done, or unknown (got '$status')" ;;
  esac
  [[ "$timeout" =~ ^[0-9]+$ ]] || die "--timeout must be milliseconds (got '$timeout')"

  require_deps herdr jq
  require_herdr_server

  if [ -z "$pane" ]; then
    local ws row agent astatus
    ws="$(workspace_or_die "$ref")"
    row="$(agent_pane_for_workspace "$ws")" || die "workspace $ws has no panes"
    IFS=$'\t' read -r pane agent astatus <<<"$row"
  fi

  if [ -n "$match" ]; then
    local args=(wait output "$pane" --match "$match" --source recent --timeout "$timeout")
    [ "$regex" -eq 1 ] && args+=(--regex)
    herdr_do "${args[@]}" >/dev/null
    printf 'matched\n'
  else
    herdr_do wait agent-status "$pane" --status "$status" --timeout "$timeout" >/dev/null
    printf '%s\n' "$status"
  fi
}
