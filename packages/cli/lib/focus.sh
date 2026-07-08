# shellcheck shell=bash
# focus.sh — jump focus to an agent workspace by id or label.

focus_usage() {
  cat <<'EOF'
corral focus — switch focus to an agent workspace.

Usage:
  corral focus <workspace>

Arguments:
  <workspace>   Workspace id (w4) or label (checkout-fix).

Alias: corral attach

Example:
  corral focus checkout-fix
EOF
}

cmd_focus() {
  local ref=""
  while [ $# -gt 0 ]; do
    case "$1" in
      -h|--help) focus_usage; return 0 ;;
      -*) die "unknown option: $1 (try 'corral focus --help')" ;;
      *)  ref="$1"; shift ;;
    esac
  done
  [ -n "$ref" ] || { focus_usage; die "missing <workspace> argument"; }

  require_deps herdr jq
  require_herdr_server

  local ws; ws="$(resolve_workspace "$ref")" || die "no workspace matching '$ref'"
  herdr_do workspace focus "$ws" >/dev/null
  ok "focused workspace $ws"
}
