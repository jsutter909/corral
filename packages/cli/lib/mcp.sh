# shellcheck shell=bash
# mcp.sh — a stdio MCP server so an orchestrator agent can drive corral.
#
# Speaks newline-delimited JSON-RPC 2.0 (the MCP stdio transport) using only
# bash + jq — no extra runtime. Every tool shells back out to the corral CLI,
# so the MCP surface can never drift from the documented command surface.
#
# Register with Claude Code:   claude mcp add corral -- corral mcp

mcp_usage() {
  cat <<'EOF'
corral mcp — run corral as an MCP server over stdio.

Usage:
  corral mcp

Lets an orchestrator agent (e.g. a Claude Code session) spawn, prompt,
watch, and tear down corral agent workspaces as MCP tools:

  corral_spawn   spawn an isolated agent workspace (optionally with a prompt)
  corral_list    list active agent workspaces and their statuses
  corral_send    send a prompt to a running agent
  corral_read    read the recent output of an agent's pane
  corral_wait    block until an agent is idle/blocked or output matches
  corral_close   remove an agent's worktree and close its workspace

Setup (Claude Code):
  claude mcp add corral -- corral mcp

The server is line-oriented stdio; it is meant to be launched by an MCP
client, not interactively.
EOF
}

# --- protocol plumbing -------------------------------------------------------

# Responses are single lines on stdout; everything else must go to stderr.
_mcp_emit() { printf '%s\n' "$1"; }

_mcp_send_result() { # <id-json> <result-json>
  _mcp_emit "$(jq -cn --argjson id "$1" --argjson result "$2" \
    '{jsonrpc: "2.0", id: $id, result: $result}')"
}

_mcp_send_error() { # <id-json> <code> <message>
  _mcp_emit "$(jq -cn --argjson id "$1" --argjson code "$2" --arg msg "$3" \
    '{jsonrpc: "2.0", id: $id, error: {code: $code, message: $msg}}')"
}

# Tool result helper: MCP tool failures are result.isError, not JSON-RPC errors.
_mcp_send_tool_result() { # <id-json> <text> <is-error: true|false>
  _mcp_send_result "$1" "$(jq -cn --arg t "$2" --argjson e "$3" \
    '{content: [{type: "text", text: $t}], isError: $e}')"
}

_mcp_tools() {
  cat <<'EOF'
[
  {
    "name": "corral_spawn",
    "description": "Spawn an isolated coding-agent workspace: a fresh git worktree on its own branch with a coding agent (Claude Code by default) running in it. Pass `prompt` to have the agent start working immediately. If the repo commits a .corral/setup.sh, it runs in the pane before the agent starts (the returned `setup` field says whether one is gating the agent — do not send prompts until it finishes). Returns JSON with the new workspace id, branch, worktree path, and pane ids. Use the workspace id with the other corral tools.",
    "inputSchema": {
      "type": "object",
      "properties": {
        "repo": {"type": "string", "description": "Path inside the git repo to branch from (e.g. ~/dev/app)"},
        "prompt": {"type": "string", "description": "Initial task for the agent to start on immediately"},
        "branch": {"type": "string", "description": "Branch name for the worktree (default: derived from `prompt` when one is given, e.g. agent/fix-tax-rounding, else agent/<repo>-<timestamp>; the returned `branch` field has the final name)"},
        "base": {"type": "string", "description": "Base git ref to branch from (default: current HEAD)"},
        "label": {"type": "string", "description": "Workspace label shown in listings (default: derived from branch)"},
        "agent": {"type": "string", "description": "Agent CLI to launch: claude (default), codex, copilot, droid, opencode, cursor, or none"},
        "model": {"type": "string", "description": "Model for the Claude agent, e.g. opus, sonnet (claude only)"},
        "permission_mode": {"type": "string", "description": "Claude permission mode, e.g. acceptEdits for autonomous work (claude only)"},
        "focus": {"type": "boolean", "description": "Switch the user's herdr focus to the new workspace (default false — don't steal focus)"},
        "no_setup": {"type": "boolean", "description": "Skip the repo's .corral/setup.sh hook (default false — the hook runs when the repo commits one)"}
      },
      "required": ["repo"]
    }
  },
  {
    "name": "corral_list",
    "description": "List active corral agent workspaces as JSON: workspace id, label, repo, branch, agent status (idle/working/blocked), and worktree path.",
    "inputSchema": {"type": "object", "properties": {}}
  },
  {
    "name": "corral_send",
    "description": "Send a prompt (or any text) to the agent running in a workspace. Submits with Enter by default. The agent may take a moment to flip to 'working' — prefer corral_wait with match, or wait for working then idle, before reading results.",
    "inputSchema": {
      "type": "object",
      "properties": {
        "workspace": {"type": "string", "description": "Workspace id (e.g. w4) or label"},
        "text": {"type": "string", "description": "Text to type into the agent"},
        "submit": {"type": "boolean", "description": "Press Enter after typing (default true)"}
      },
      "required": ["workspace", "text"]
    }
  },
  {
    "name": "corral_read",
    "description": "Read the recent terminal output of a workspace's agent pane (plain text, includes scrollback). Use after corral_wait to see what the agent did or what it is asking.",
    "inputSchema": {
      "type": "object",
      "properties": {
        "workspace": {"type": "string", "description": "Workspace id (e.g. w4) or label"},
        "lines": {"type": "integer", "description": "Number of lines to capture (default 120)"}
      },
      "required": ["workspace"]
    }
  },
  {
    "name": "corral_wait",
    "description": "Block until a workspace's agent reaches a status (default idle) or, if `match` is given, until its output contains matching text. Returns the reached condition, or an error on timeout. Statuses: idle (finished/awaiting input), working, blocked (needs human approval), done, unknown.",
    "inputSchema": {
      "type": "object",
      "properties": {
        "workspace": {"type": "string", "description": "Workspace id (e.g. w4) or label"},
        "status": {"type": "string", "enum": ["idle", "working", "blocked", "done", "unknown"], "description": "Agent status to wait for (default idle)"},
        "match": {"type": "string", "description": "Wait for output matching this text instead of a status"},
        "regex": {"type": "boolean", "description": "Treat match as a regular expression (default false)"},
        "timeout_ms": {"type": "integer", "description": "Give up after this many milliseconds (default 300000)"}
      },
      "required": ["workspace"]
    }
  },
  {
    "name": "corral_close",
    "description": "Tear down a corral agent workspace: remove its git worktree and close the workspace. Unmerged branch work stays in git (the branch is kept). Refuses to touch non-corral workspaces.",
    "inputSchema": {
      "type": "object",
      "properties": {
        "workspace": {"type": "string", "description": "Workspace id (e.g. w4) or label"}
      },
      "required": ["workspace"]
    }
  }
]
EOF
}

# --- tool dispatch -----------------------------------------------------------

_mcp_arg() { # <args-json> <key> — prints the value, empty if absent/null
  printf '%s' "$1" | jq -r --arg k "$2" '.[$k] // empty'
}

_mcp_run_tool() { # <id-json> <corral-args...>
  local id="$1"; shift
  local errf out err rc=0
  errf="$(mktemp "${TMPDIR:-/tmp}/corral-mcp.XXXXXX")"
  # </dev/null so a subcommand can never read (and eat) protocol stdin.
  out="$("$CORRAL_BIN_DIR/corral" "$@" </dev/null 2>"$errf")" || rc=$?
  err="$(cat "$errf")"; rm -f "$errf"

  if [ "$rc" -eq 0 ]; then
    local text="${out:-$err}"
    _mcp_send_tool_result "$id" "${text:-ok}" false
  else
    _mcp_send_tool_result "$id" \
      "corral $1 failed (exit $rc)${err:+
$err}${out:+
$out}" true
  fi
}

_mcp_tool_call() { # <id-json> <request-line>
  local id="$1" line="$2" name args
  name="$(printf '%s' "$line" | jq -r '.params.name // empty')"
  args="$(printf '%s' "$line" | jq -c '.params.arguments // {}')"

  local ws
  ws="$(_mcp_arg "$args" workspace)"

  case "$name" in
    corral_spawn)
      local repo prompt branch base label agent model pmode focus
      repo="$(_mcp_arg "$args" repo)"
      if [ -z "$repo" ]; then
        _mcp_send_tool_result "$id" "corral_spawn: 'repo' is required" true
        return 0
      fi
      local tool_cmd=(spawn "$repo")
      branch="$(_mcp_arg "$args" branch)";          [ -n "$branch" ] && tool_cmd+=("$branch")
      tool_cmd+=(--json)
      prompt="$(_mcp_arg "$args" prompt)";          [ -n "$prompt" ] && tool_cmd+=(--prompt "$prompt")
      base="$(_mcp_arg "$args" base)";              [ -n "$base" ]   && tool_cmd+=(--base "$base")
      label="$(_mcp_arg "$args" label)";            [ -n "$label" ]  && tool_cmd+=(--label "$label")
      agent="$(_mcp_arg "$args" agent)";            [ -n "$agent" ]  && tool_cmd+=(--agent "$agent")
      model="$(_mcp_arg "$args" model)";            [ -n "$model" ]  && tool_cmd+=(--model "$model")
      pmode="$(_mcp_arg "$args" permission_mode)";  [ -n "$pmode" ]  && tool_cmd+=(--permission-mode "$pmode")
      focus="$(printf '%s' "$args" | jq -r '.focus == true')"
      [ "$focus" = "true" ] || tool_cmd+=(--no-focus)
      local no_setup
      no_setup="$(printf '%s' "$args" | jq -r '.no_setup == true')"
      [ "$no_setup" = "true" ] && tool_cmd+=(--no-setup)
      _mcp_run_tool "$id" "${tool_cmd[@]}"
      ;;
    corral_list)
      _mcp_run_tool "$id" ls --json
      ;;
    corral_send)
      local text submit
      text="$(_mcp_arg "$args" text)"
      if [ -z "$ws" ] || [ -z "$text" ]; then
        _mcp_send_tool_result "$id" "corral_send: 'workspace' and 'text' are required" true
        return 0
      fi
      submit="$(printf '%s' "$args" | jq -r 'if has("submit") then .submit else true end')"
      local tool_cmd=(send "$ws")
      [ "$submit" = "true" ] || tool_cmd+=(--no-enter)
      tool_cmd+=(-- "$text")
      _mcp_run_tool "$id" "${tool_cmd[@]}"
      ;;
    corral_read)
      if [ -z "$ws" ]; then
        _mcp_send_tool_result "$id" "corral_read: 'workspace' is required" true
        return 0
      fi
      local lines
      lines="$(_mcp_arg "$args" lines)"
      _mcp_run_tool "$id" read "$ws" --lines "${lines:-120}" --source recent
      ;;
    corral_wait)
      if [ -z "$ws" ]; then
        _mcp_send_tool_result "$id" "corral_wait: 'workspace' is required" true
        return 0
      fi
      local match status timeout regex
      match="$(_mcp_arg "$args" match)"
      status="$(_mcp_arg "$args" status)"
      timeout="$(_mcp_arg "$args" timeout_ms)"
      regex="$(printf '%s' "$args" | jq -r '.regex == true')"
      local tool_cmd=(wait "$ws" --timeout "${timeout:-300000}")
      if [ -n "$match" ]; then
        tool_cmd+=(--match "$match")
        [ "$regex" = "true" ] && tool_cmd+=(--regex)
      else
        tool_cmd+=(--status "${status:-idle}")
      fi
      _mcp_run_tool "$id" "${tool_cmd[@]}"
      ;;
    corral_close)
      if [ -z "$ws" ]; then
        _mcp_send_tool_result "$id" "corral_close: 'workspace' is required" true
        return 0
      fi
      _mcp_run_tool "$id" close "$ws" --force
      ;;
    *)
      _mcp_send_error "$id" -32602 "unknown tool: ${name:-<missing name>}"
      ;;
  esac
  return 0
}

# --- request loop ------------------------------------------------------------

_mcp_handle_line() {
  local line="$1"
  if ! printf '%s' "$line" | jq -e . >/dev/null 2>&1; then
    _mcp_send_error null -32700 "parse error: not valid JSON"
    return 0
  fi

  local method has_id id
  method="$(printf '%s' "$line" | jq -r '.method // empty')"
  has_id="$(printf '%s' "$line" | jq -r 'has("id")')"
  id="$(printf '%s' "$line" | jq -c '.id')"

  case "$method" in
    initialize)
      local proto
      proto="$(printf '%s' "$line" | jq -r '.params.protocolVersion // "2025-06-18"')"
      _mcp_send_result "$id" "$(jq -cn --arg pv "$proto" --arg v "$CORRAL_VERSION" \
        '{protocolVersion: $pv, capabilities: {tools: {}},
          serverInfo: {name: "corral", title: "corral — isolated agent workspaces", version: $v}}')"
      ;;
    notifications/*)
      : ;;  # notifications get no response
    ping)
      _mcp_send_result "$id" '{}'
      ;;
    tools/list)
      _mcp_send_result "$id" "$(jq -cn --argjson t "$(_mcp_tools)" '{tools: $t}')"
      ;;
    tools/call)
      _mcp_tool_call "$id" "$line"
      ;;
    *)
      if [ "$has_id" = "true" ]; then
        _mcp_send_error "$id" -32601 "method not found: ${method:-<missing method>}"
      fi
      ;;
  esac
  return 0
}

cmd_mcp() {
  while [ $# -gt 0 ]; do
    case "$1" in
      -h|--help) mcp_usage; return 0 ;;
      *) die "unknown option: $1 (corral mcp takes no arguments; try --help)" ;;
    esac
  done

  require_deps jq
  info "corral mcp server ready (stdio) — register with: claude mcp add corral -- corral mcp"

  local line
  while IFS= read -r line; do
    [ -n "$line" ] || continue
    _mcp_handle_line "$line" || warn "failed to handle request: $line"
  done
}
