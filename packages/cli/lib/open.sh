# shellcheck shell=bash
# open.sh — open the configured IDE (VS Code or Cursor) in a workspace's worktree.

open_usage() {
  local host_default="${CORRAL_SSH_HOST:-$(hostname)}"
  cat <<EOF
corral open — open your IDE in an agent workspace's worktree.

Usage:
  corral open [workspace] [options]

Arguments:
  [workspace]   Workspace id (w4) or label (checkout-fix).
                Defaults to the workspace you're currently in.

Options:
  -i, --ide <name>   IDE to open: vscode or cursor (default: $CORRAL_IDE)
  --ssh              Force Remote-SSH mode: print a link that opens the IDE on
                     your local machine over SSH
  --no-ssh           Force local mode: launch the IDE on this machine
  --host <host>      SSH host to use in the Remote-SSH link (default: $host_default)

Alias: corral ide

corral resolves the workspace's worktree checkout path via herdr, so the IDE
always opens the exact folder the agent is working in.

When the herdr session is remote — you attached with 'herdr --remote', so
corral runs on the server but your IDE runs on your local machine — corral
can't launch the IDE from here. Instead it prints a <ide>://vscode-remote/…
deep link (clickable in most terminals) plus the equivalent 'code --remote'
command to run locally; both open the worktree over Remote-SSH. The link's
host must match how YOUR machine reaches this one (a Host entry in your local
~/.ssh/config); set CORRAL_SSH_HOST or --host when the hostname isn't it.

Examples:
  corral open                    # open the worktree you're in
  corral open checkout-fix       # open by label
  corral open w4 --ide cursor
  corral open w4 --host devbox   # remote link via ssh host alias "devbox"
EOF
}

# Map an IDE name (config/flag value) to its CLI command, URI scheme, and
# display name, tab-separated. Exits nonzero on an unknown name.
# Usage: ide_fields <vscode|code|cursor>
ide_fields() {
  case "$1" in
    vscode|code) printf 'code\tvscode\tVisual Studio Code' ;;
    cursor)      printf 'cursor\tcursor\tCursor' ;;
    *) return 1 ;;
  esac
}

# Percent-encode a filesystem path for use in a vscode-remote URI, keeping
# "/" so the path stays a path. LC_ALL=C makes ${s:i:1} iterate bytes, which
# percent-encodes multibyte UTF-8 characters byte-by-byte as URIs require.
ide_encode_path() {
  local LC_ALL=C s="$1" out="" c i
  for ((i = 0; i < ${#s}; i++)); do
    c="${s:$i:1}"
    case "$c" in
      [a-zA-Z0-9/._~-]) out+="$c" ;;
      *) out+="$(printf '%%%02X' "'$c")" ;;
    esac
  done
  printf '%s' "$out"
}

# The Remote-SSH deep link VS Code and Cursor register for their URI scheme:
# <scheme>://vscode-remote/ssh-remote+<host><absolute path>
# Usage: ide_remote_uri <scheme> <host> <path>
ide_remote_uri() {
  printf '%s://vscode-remote/ssh-remote+%s%s' "$1" "$2" "$(ide_encode_path "$3")"
}

# Is this herdr session remote (IDE UI not on this machine)? True when corral
# itself runs over SSH, or when a 'herdr --remote' client bridge is attached
# to the local server. Overridable with --ssh/--no-ssh.
ide_session_is_remote() {
  [ -n "${SSH_CONNECTION-}${SSH_CLIENT-}${SSH_TTY-}" ] && return 0
  pgrep -f 'herdr remote-client-bridge' >/dev/null 2>&1
}

cmd_open() {
  local ref="" ide="$CORRAL_IDE" mode="auto" host="$CORRAL_SSH_HOST"
  while [ $# -gt 0 ]; do
    case "$1" in
      -h|--help) open_usage; return 0 ;;
      -i|--ide)  ide="${2:?--ide needs a value}"; shift 2 ;;
      --ssh)     mode="ssh"; shift ;;
      --no-ssh)  mode="local"; shift ;;
      --host)    host="${2:?--host needs a value}"; shift 2 ;;
      -*) die "unknown option: $1 (try 'corral open --help')" ;;
      *)  ref="$1"; shift ;;
    esac
  done

  local fields cli scheme app
  fields="$(ide_fields "$ide")" \
    || die "unknown IDE '$ide' — use vscode or cursor (CORRAL_IDE or --ide)"
  IFS=$'\t' read -r cli scheme app <<<"$fields"

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
    [ -n "$ws" ] || die "could not determine current workspace; pass one (e.g. corral open w4)"
  fi

  # Any worktree-backed workspace may be opened (unlike close, this is
  # harmless), but the path must come from herdr — never guessed — so the IDE
  # opens the exact checkout the agent works in.
  local wsinfo label wt
  wsinfo="$(herdr_do workspace get "$ws")"
  label="$(printf '%s' "$wsinfo" | jq -r '.result.workspace.label // "?"')"
  wt="$(printf '%s' "$wsinfo" | jq -r '.result.workspace.worktree.checkout_path // empty')"
  [ -n "$wt" ] || die "workspace $ws ($label) has no git worktree attached"
  [ -d "$wt" ] || die "worktree path $wt no longer exists"

  if [ "$mode" = "auto" ]; then
    if ide_session_is_remote; then mode="ssh"; else mode="local"; fi
  fi

  if [ "$mode" = "local" ]; then
    if command -v "$cli" >/dev/null 2>&1; then
      "$cli" "$wt" || die "'$cli $wt' failed"
    elif [ "$(uname -s)" = "Darwin" ] && command -v open >/dev/null 2>&1; then
      open -a "$app" "$wt" || die "could not open $app"
    else
      die "the '$cli' command is not on PATH — install the $app shell command, or use --ssh for a Remote-SSH link"
    fi
    ok "opened $wt in $app"
    return 0
  fi

  # Remote: corral runs on the herdr server; the IDE runs on the user's
  # machine, so it can't be launched from here. Print a deep link (stdout,
  # clickable in most terminals) and the CLI equivalent to run locally.
  [ -n "$host" ] || host="$(hostname)"
  info "herdr session is remote — open this worktree from your machine ($app over SSH):"
  printf '%s\n' "$(ide_remote_uri "$scheme" "$host" "$wt")"
  info "or run locally:  $cli --remote ssh-remote+$host $(shell_quote "$wt")"
  info "(host '$host' must match a Host entry in your local ~/.ssh/config — set CORRAL_SSH_HOST or --host if not)"
}
