# shellcheck shell=bash
# read.sh — capture the output visible in an agent's pane.

read_usage() {
  cat <<'EOF'
corral read — print the recent output of the agent in a workspace.

Usage:
  corral read <workspace> [options]

Arguments:
  <workspace>   Workspace id (w4) or label (checkout-fix).
                Defaults to the workspace you're currently in.

Options:
  -n, --lines <n>    Number of lines to capture (default: the visible screen).
  -s, --source <src> visible | recent | recent-unwrapped (default: visible).
                     "recent" includes scrollback above the visible screen.
  --ansi             Keep ANSI colors/styles instead of plain text.
  -p, --pane <id>    Read a specific pane instead of the workspace's agent pane.

Output goes to stdout, so it pipes cleanly:
  corral read w4 --lines 200 --source recent | tail -40
EOF
}

cmd_read() {
  local ref="" lines="" source="" ansi=0 pane=""
  while [ $# -gt 0 ]; do
    case "$1" in
      -h|--help) read_usage; return 0 ;;
      -n|--lines)  lines="${2:?--lines needs a value}"; shift 2 ;;
      -s|--source) source="${2:?--source needs a value}"; shift 2 ;;
      --ansi)      ansi=1; shift ;;
      -p|--pane)   pane="${2:?--pane needs a value}"; shift 2 ;;
      -*) die "unknown option: $1 (try 'corral read --help')" ;;
      *)  [ -z "$ref" ] || die "unexpected argument: $1"; ref="$1"; shift ;;
    esac
  done

  case "$source" in ""|visible|recent|recent-unwrapped) : ;;
    *) die "--source must be visible, recent, or recent-unwrapped (got '$source')" ;;
  esac
  [ -z "$lines" ] || [[ "$lines" =~ ^[0-9]+$ ]] || die "--lines must be a number (got '$lines')"

  require_deps herdr jq
  require_herdr_server

  if [ -z "$pane" ]; then
    local ws row agent status
    ws="$(workspace_or_die "$ref")"
    row="$(agent_pane_for_workspace "$ws")" || die "workspace $ws has no panes"
    IFS=$'\t' read -r pane agent status <<<"$row"
  fi

  local args=(pane read "$pane")
  [ -n "$source" ] && args+=(--source "$source")
  [ "$ansi" -eq 1 ] && args+=(--ansi)

  local out
  if [ -n "$lines" ]; then
    # herdr's --lines window counts the blank rows below the cursor, so a
    # sparsely filled pane can come back empty. Fetch the whole buffer
    # (herdr clamps the window to what exists), drop trailing blank lines,
    # and take the last N locally instead.
    out="$(herdr_do "${args[@]}" --lines 100000)"
    out="$(printf '%s\n' "$out" \
      | awk 'NF {last = NR} {l[NR] = $0} END {for (i = 1; i <= last; i++) print l[i]}' \
      | tail -n "$lines")"
  else
    out="$(herdr_do "${args[@]}")"
  fi
  printf '%s\n' "$out"
}
