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
check "prune --help exits 0"        0 "$CORRAL" prune --help
check "doctor --help exits 0"       0 "$CORRAL" doctor --help
check "help spawn exits 0"          0 "$CORRAL" help spawn
check "unknown command exits 1"     1 "$CORRAL" bogus-command
check "doctor unknown flag exits 1" 1 "$CORRAL" doctor --bogus
check "spawn without repo exits 1"  1 "$CORRAL" spawn
check "spawn --prompt w/o value !=0" 1 "$CORRAL" spawn . --prompt
check "focus without arg exits 1"   1 "$CORRAL" focus

echo "----"
printf '%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
