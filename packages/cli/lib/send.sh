# shellcheck shell=bash
# send.sh — type text into an agent's pane, submitting it with Enter.

send_usage() {
  cat <<'EOF'
corral send — send a prompt (or any text) to the agent in a workspace.

Usage:
  corral send <workspace> [--] <text...>

Arguments:
  <workspace>   Workspace id (w4) or label (checkout-fix).
  <text...>     Text to type into the agent pane. Multiple words are joined
                with spaces. Use -- before text that starts with a dash.

Options:
  --no-enter      Type the text without submitting it (no trailing Enter).
  -p, --pane <id>  Send to a specific pane instead of the workspace's agent pane.

The text lands in the workspace's agent pane (the pane corral launched the
agent in). Pair with 'corral wait' to block until the agent goes idle, and
'corral read' to collect its output.

Examples:
  corral send w4 "run the tests and fix any failures"
  corral send checkout-fix --no-enter "draft, not submitted"
  corral send w4 -- "--help"
EOF
}

cmd_send() {
  local enter=1 pane=""
  local positional=()
  while [ $# -gt 0 ]; do
    case "$1" in
      -h|--help)  send_usage; return 0 ;;
      --no-enter) enter=0; shift ;;
      -p|--pane)  pane="${2:?--pane needs a value}"; shift 2 ;;
      --) shift; while [ $# -gt 0 ]; do positional+=("$1"); shift; done ;;
      -*) die "unknown option: $1 (try 'corral send --help')" ;;
      *)  positional+=("$1"); shift ;;
    esac
  done

  local min=2
  [ -n "$pane" ] && min=1
  if [ ${#positional[@]} -lt "$min" ]; then
    send_usage
    die "missing arguments — need a workspace and text (or --pane and text)"
  fi

  require_deps herdr jq
  require_herdr_server

  local text agent="pane"
  if [ -n "$pane" ]; then
    text="${positional[*]}"
  else
    local ws row status
    ws="$(workspace_or_die "${positional[0]}")"
    row="$(agent_pane_for_workspace "$ws")" || die "workspace $ws has no panes"
    IFS=$'\t' read -r pane agent status <<<"$row"
    text="${positional[*]:1}"
  fi

  herdr_do pane send-text "$pane" "$text" >/dev/null
  if [ "$enter" -eq 1 ]; then
    # Give the agent's TUI a beat to ingest the pasted text before submitting;
    # sending Enter in the same instant can race the paste handler.
    sleep 0.2
    herdr_do pane send-keys "$pane" Enter >/dev/null
  fi
  ok "sent to $pane ($agent)"
}
