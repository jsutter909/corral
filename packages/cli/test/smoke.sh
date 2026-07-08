#!/usr/bin/env bash
# smoke.sh — lightweight checks that exercise the CLI surface without needing a
# running herdr server (help/usage/version paths return before any herdr call).
set -uo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CORRAL="$here/../bin/corral"

pass=0 fail=0
check() { # check <description> <expected-exit> <cmd...>
  local desc="$1" want="$2"; shift 2
  "$@" >/dev/null 2>&1; local got=$?
  if [ "$got" -eq "$want" ]; then
    printf '  ok   %s\n' "$desc"; pass=$((pass + 1))
  else
    printf '  FAIL %s (exit %s, wanted %s)\n' "$desc" "$got" "$want"; fail=$((fail + 1))
  fi
}

echo "corral smoke tests"
check "help exits 0"                0 "$CORRAL" help
check "version exits 0"             0 "$CORRAL" version
check "-V exits 0"                  0 "$CORRAL" -V
check "spawn --help exits 0"        0 "$CORRAL" spawn --help
check "close --help exits 0"        0 "$CORRAL" close --help
check "ls --help exits 0"           0 "$CORRAL" ls --help
check "focus --help exits 0"        0 "$CORRAL" focus --help
check "send --help exits 0"         0 "$CORRAL" send --help
check "read --help exits 0"         0 "$CORRAL" read --help
check "wait --help exits 0"         0 "$CORRAL" wait --help
check "mcp --help exits 0"          0 "$CORRAL" mcp --help
check "prune --help exits 0"        0 "$CORRAL" prune --help
check "doctor --help exits 0"       0 "$CORRAL" doctor --help
check "help spawn exits 0"          0 "$CORRAL" help spawn
check "unknown command exits 1"     1 "$CORRAL" bogus-command
check "doctor unknown flag exits 1" 1 "$CORRAL" doctor --bogus
check "spawn without repo exits 1"  1 "$CORRAL" spawn
check "spawn --prompt w/o value !=0" 1 "$CORRAL" spawn . --prompt
check "spawn -p w/o value !=0"       1 "$CORRAL" spawn . -p
check "spawn -b w/o value !=0"       1 "$CORRAL" spawn . -b
check "spawn unknown short flag !=0" 1 "$CORRAL" spawn . -z
check "focus without arg exits 1"   1 "$CORRAL" focus
check "send without text exits 1"   1 "$CORRAL" send w4
check "send -p w/o value !=0"       1 "$CORRAL" send w4 -p
check "wait bad status exits 1"     1 "$CORRAL" wait w4 --status bogus
check "wait -s bad status exits 1"  1 "$CORRAL" wait w4 -s bogus
check "wait bad timeout exits 1"    1 "$CORRAL" wait w4 --timeout soon
check "wait -t w/o value !=0"       1 "$CORRAL" wait w4 -t
check "read bad source exits 1"     1 "$CORRAL" read w4 --source bogus
check "read -n bad value exits 1"   1 "$CORRAL" read w4 -n soon
check "spawn -j without repo !=0"   1 "$CORRAL" spawn -j
check "mcp unknown flag exits 1"    1 "$CORRAL" mcp --bogus

# --- MCP protocol round-trip (no herdr server needed) ------------------------
# Drive initialize → tools/list → an unknown method through the stdio server
# and assert on the JSON-RPC responses.
mcp_check() { # mcp_check <description> <jq-assertion>
  local desc="$1" assertion="$2"
  if printf '%s' "$mcp_out" | jq -e -s "$assertion" >/dev/null 2>&1; then
    printf '  ok   %s\n' "$desc"; pass=$((pass + 1))
  else
    printf '  FAIL %s\n' "$desc"; fail=$((fail + 1))
  fi
}

mcp_out="$(printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"smoke","version":"0"}}}' \
  '{"jsonrpc":"2.0","method":"notifications/initialized"}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
  '{"jsonrpc":"2.0","id":3,"method":"ping"}' \
  '{"jsonrpc":"2.0","id":4,"method":"no/such-method"}' \
  'not even json' \
  | "$CORRAL" mcp 2>/dev/null)"

mcp_check "mcp initialize returns serverInfo" \
  '.[] | select(.id == 1) | .result.serverInfo.name == "corral"'
mcp_check "mcp initialize echoes protocolVersion" \
  '.[] | select(.id == 1) | .result.protocolVersion == "2025-06-18"'
mcp_check "mcp tools/list includes all six tools" \
  '[.[] | select(.id == 2) | .result.tools[].name] ==
   ["corral_spawn","corral_list","corral_send","corral_read","corral_wait","corral_close"]'
mcp_check "mcp tool schemas declare required fields" \
  '.[] | select(.id == 2) | [.result.tools[] | select(.name == "corral_send")]
   | .[0].inputSchema.required == ["workspace","text"]'
mcp_check "mcp ping returns empty result" \
  '.[] | select(.id == 3) | .result == {}'
mcp_check "mcp unknown method returns -32601" \
  '.[] | select(.id == 4) | .error.code == -32601'
mcp_check "mcp invalid JSON returns parse error" \
  '.[] | select(.id == null and has("error")) | .error.code == -32700'
mcp_check "mcp emits no response to notifications" \
  '[.[] | select(has("id") | not)] | length == 0'

echo "launch-string construction"
lib="$here/../lib"
launch() { bash -c '. "$1/common.sh"; . "$1/spawn.sh"; spawn_launch_cmd "$2" "$3" "$4" "$5" "$6"' _ "$lib" "$@"; }
expect() { # expect <description> <want> <agent> <model> <pmode> <prompt> <setup>
  local desc="$1" want="$2" got; shift 2
  got="$(launch "$@")"
  if [ "$got" = "$want" ]; then
    printf '  ok   %s\n' "$desc"; pass=$((pass + 1))
  else
    printf '  FAIL %s (got "%s", wanted "%s")\n' "$desc" "$got" "$want"; fail=$((fail + 1))
  fi
}
expect "agent only"               'claude'                          claude '' '' '' 0
expect "setup + agent"            'bash .corral/setup.sh && claude' claude '' '' '' 1
expect "setup + claude flags"     'bash .corral/setup.sh && claude --model opus --permission-mode plan' \
                                                                    claude opus plan '' 1
expect "setup, agent none"        'bash .corral/setup.sh'           none   '' '' '' 1
expect "no setup, agent none"     ''                                none   '' '' '' 0
expect "non-claude ignores model" 'bash .corral/setup.sh && codex'  codex  opus '' '' 1
expect "prompt is quoted"         "claude 'fix the tests'"          claude '' '' 'fix the tests' 0
expect "setup + prompt"           "bash .corral/setup.sh && claude 'fix the tests'" \
                                                                    claude '' '' 'fix the tests' 1
expect "prompt quote escaping"    "claude 'it'\\''s broken'"        claude '' '' "it's broken" 0
expect "prompt dropped for none"  'bash .corral/setup.sh'           none   '' '' 'fix the tests' 1

echo "branch naming from prompt"
slug() { bash -c '. "$1/common.sh"; . "$1/spawn.sh"; spawn_branch_slug "$2"' _ "$lib" "$1"; }
expect_slug() { # expect_slug <description> <want> <text>
  local desc="$1" want="$2" got
  got="$(slug "$3")"
  if [ "$got" = "$want" ]; then
    printf '  ok   %s\n' "$desc"; pass=$((pass + 1))
  else
    printf '  FAIL %s (got "%s", wanted "%s")\n' "$desc" "$got" "$want"; fail=$((fail + 1))
  fi
}
expect_slug "slug lowercases + hyphenates" 'fix-the-tax-tests'  'Fix the TAX tests!'
expect_slug "slug collapses separators"    'a-b-c'              '  a -- b // c  '
expect_slug "slug caps length at 40" \
  'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa' \
  'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
expect_slug "slug of symbols is empty"     ''                   '!!! ???'

# spawn_branch_from_prompt with a stubbed `claude` on PATH: reply is used when
# it succeeds, sanitized when chatty, and the prompt slug is the fallback when
# the CLI fails or is absent.
stub="$(mktemp -d)"
name_from() { # name_from <stub-body|-> <prompt>   ("-" = no claude on PATH)
  local body="$1" prompt="$2" path="$stub:/usr/bin:/bin"
  if [ "$body" = "-" ]; then
    rm -f "$stub/claude"   # restricted PATH below hides any real claude too
  else
    printf '%s\n' "$body" >"$stub/claude"; chmod +x "$stub/claude"
  fi
  PATH="$path" bash -c '. "$1/common.sh"; . "$1/spawn.sh"; spawn_branch_from_prompt "$2"' _ "$lib" "$prompt"
}
expect_name() { # expect_name <description> <want> <stub-body|-> <prompt>
  local desc="$1" want="$2" got
  got="$(name_from "$3" "$4")"
  if [ "$got" = "$want" ]; then
    printf '  ok   %s\n' "$desc"; pass=$((pass + 1))
  else
    printf '  FAIL %s (got "%s", wanted "%s")\n' "$desc" "$got" "$want"; fail=$((fail + 1))
  fi
}
expect_name "llm reply names the branch"  'fix-tax-rounding' '#!/bin/sh
echo fix-tax-rounding'                                       'fix the tax tests'
expect_name "chatty reply is sanitized"   'sure-fix-tax'     '#!/bin/sh
echo "Sure! fix/tax"'                                        'fix the tax tests'
expect_name "failing claude falls back"   'fix-the-tax-tests' '#!/bin/sh
exit 1'                                                      'fix the tax tests'
expect_name "no claude falls back"        'fix-the-tax-tests' - 'fix the tax tests'
rm -rf "$stub"

echo "----"
printf '%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
