#!/usr/bin/env zsh
# completions.zsh — non-interactive tests for the corral oh-my-zsh plugin.
#
# How it works
# ------------
# compadd refuses to run outside the completion subsystem of an interactive
# zsh, so we drive a REAL interactive zsh through a pseudo-terminal
# (zsh/zpty), one fresh single-shot shell per test case:
#
#   1. spawn `zsh -f -i` under zpty with HOME pointed at a temp dir and a
#      stub `corral` on PATH (canned `ls --json` output — no herdr server
#      needed);
#   2. for completion cases, source an init script that puts the plugin dir
#      on fpath, runs a fresh compinit with a throwaway dump, and wraps
#      `compadd` so every candidate is printed as "match<TAB>description"
#      AND still delegated to the real builtin (so _arguments/_describe
#      fallback logic behaves exactly as in production); @@BEGIN@@/@@END@@
#      markers bracket each completion via compprefuncs/comppostfuncs, and
#      ^M is unbound so nothing typed can ever execute;
#   3. write the test's command line plus a literal TAB, read pty output in
#      a non-blocking loop (zpty -r -t + 50ms zselect sleeps) with a hard
#      10s deadline, cut out the marker-delimited block, and compare sorted
#      matches against the expectation;
#   4. function cases (ccd, aliases, corral_prompt_info) instead source
#      corral.plugin.zsh, run a command, and assert on its output.
#
# Run:   zsh packages/omz-plugin/test/completions.zsh
# Exit:  0 all passed; 1 any assertion failed (diff printed); 2 setup error.
# Needs: zsh with zpty/zselect/datetime modules (stock zsh; on CI:
#        `apt-get install -y zsh`), jq, diff. No herdr, no real corral.

emulate -L zsh
setopt no_unset

zmodload zsh/zpty zsh/zselect zsh/datetime || {
  print -u2 'FATAL: zsh modules zpty/zselect/datetime unavailable'
  exit 2
}

typeset -g SELF=${${(%):-%N}:A}
typeset -g PLUGIN_DIR=${SELF:h:h}
typeset -g PTY=corral-comp-test
typeset -gi FAILS=0 CASES=0
typeset -ga ACTUAL
typeset -g RAW=''

[[ -r $PLUGIN_DIR/_corral ]] || {
  print -u2 "FATAL: $PLUGIN_DIR/_corral not found"
  exit 2
}

WORK=$(mktemp -d) || exit 2
trap 'zpty -d $PTY 2>/dev/null; rm -rf -- $WORK' EXIT INT TERM

# --- stub corral binaries -----------------------------------------------------

mkdir -p $WORK/stub-ok $WORK/stub-fail $WORK/wt-a $WORK/wt-b

# Canned workspaces. The second label contains a colon AND a space —
# exercises _describe escaping end to end. Worktree dirs really exist so
# ccd can cd into them.
cat >$WORK/ls.json <<EOF
[
  {"workspace":"w4","label":"checkout-fix","repo":"app","branch":"corral/app-1","status":"busy","worktree":"$WORK/wt-a"},
  {"workspace":"w7","label":"tax: rounding","repo":"app","branch":"bugfix/tax","status":"idle","worktree":"$WORK/wt-b"}
]
EOF

cat >$WORK/stub-ok/corral <<EOF
#!/bin/sh
# Fake corral: canned \`ls --json\`; no herdr server needed.
if [ "\${1:-}" = "ls" ] && [ "\${2:-}" = "--json" ]; then
  cat '$WORK/ls.json'
fi
exit 0
EOF

cat >$WORK/stub-fail/corral <<'EOF'
#!/bin/sh
# Fake corral with no herdr server: dies fast on stderr, like the real one.
echo "error: herdr server is not reachable." >&2
exit 1
EOF

chmod +x $WORK/stub-ok/corral $WORK/stub-fail/corral

# --- init script for the inner shell (completion cases) -----------------------

cat >$WORK/init.zsh <<EOF
path=("\$CORRAL_TEST_STUB" \$path)
fpath=(${(q)PLUGIN_DIR} \$fpath)
EOF
cat >>$WORK/init.zsh <<'EOF'
autoload -Uz compinit
compinit -u -d "$HOME/zcompdump"   # fresh throwaway dump every run

zmodload zsh/zutil
zstyle ':completion:*' completer _complete
zstyle ':completion:*' list-grouped false
zstyle ':completion:*' insert-tab false
zstyle ':completion:*' prefix-needed true   # options only after a typed '-'
zstyle ':completion:*' menu false

# Wrap compadd: print each candidate as "match<TAB>description", then
# delegate to the real builtin so compstate[nmatches] stays truthful and
# _arguments' fallback behaviour matches production exactly.
compadd() {
  local -a _o _a _d
  zparseopts -E O:=_o A:=_a D:=_d
  if (( $#_o || $#_a || $#_d )); then builtin compadd "$@"; return; fi
  local -a _hits _dscr _tmp
  zparseopts -E d:=_tmp
  if (( $#_tmp )); then
    _tmp=${_tmp[2]}
    if [[ $_tmp == \(*\) ]]; then eval "_dscr=${_tmp}"; else _dscr=( "${(@P)_tmp}" ); fi
  fi
  builtin compadd -A _hits -D _dscr "$@"
  local i
  for (( i = 1; i <= $#_hits; i++ )); do
    print -r -- "${_hits[i]}"$'\t'"${_dscr[i]:-}"
  done
  builtin compadd "$@"
}

_harness_begin() { print -r -- '@@BEGIN@@' }
_harness_end()   { print -r -- '@@END@@'; exit 0 }
compprefuncs=( _harness_begin )
comppostfuncs=( _harness_end )

bindkey -e
bindkey '^I' complete-word
bindkey '^M' undefined-key    # nothing typed after this line can ever execute
print -r -- '@@READY@@'
EOF

# --- pty driving ----------------------------------------------------------------

# Read pty output into $REPLY until $1 (literal substring) appears.
# Non-blocking reads + 50ms sleeps + hard 10s deadline: cannot hang.
pty_read_until() {
  local needle=$1 chunk
  local -F deadline=$(( EPOCHREALTIME + 10 ))
  REPLY=''
  while (( EPOCHREALTIME < deadline )); do
    if zpty -r -t $PTY chunk 2>/dev/null; then
      REPLY+=$chunk
      [[ $REPLY == *"$needle"* ]] && return 0
    else
      zpty -t $PTY 2>/dev/null || {              # inner shell exited (expected
        [[ $REPLY == *"$needle"* ]] && return 0  # after @@END@@'s exit)
        return 1
      }
      zselect -t 5   # 50 ms
    fi
  done
  return 1
}

# Run one completion. $1 = stub dir, $2 = line to type before TAB.
# Sets $ACTUAL (sorted match strings) and $RAW (marker-delimited block).
run_completion() {
  local stubdir=$1 input=$2
  ACTUAL=() RAW=''

  zpty $PTY env "CORRAL_TEST_STUB=$stubdir" "HOME=$WORK" TERM=dumb \
    zsh -f -i || return 1
  zpty -w $PTY "source $WORK/init.zsh"
  if ! pty_read_until '@@READY@@'; then
    print -u2 '  harness: inner shell never finished init; output was:'
    print -u2 -r -- "$REPLY"
    zpty -d $PTY 2>/dev/null
    return 1
  fi

  zpty -w -n $PTY "$input"$'\t'
  local ok=0
  pty_read_until '@@END@@' && ok=1
  local out=$REPLY
  zpty -d $PTY 2>/dev/null

  if (( ! ok )); then
    print -u2 '  harness: timed out waiting for completion; output was:'
    print -u2 -r -- "$out"
    return 1
  fi

  out=${out//$'\r'/}
  out=${out#*@@BEGIN@@}
  out=${out%%@@END@@*}
  RAW=$out

  local -a lines=( ${(f)out} )
  local l
  for l in $lines; do
    [[ -n ${l//[[:space:]]/} ]] || continue
    ACTUAL+=( "${l%%$'\t'*}" )
  done
  ACTUAL=( ${(o)ACTUAL} )
  return 0
}

# Run one shell-function case: source the plugin, execute $2, capture output.
# The marker strings are split in the typed line ('@@DO''NE@@') so the echo of
# the input never matches — only the executed print does.
run_shell() {
  local stubdir=$1 cmd=$2
  RAW=''
  zpty $PTY env "PATH=$stubdir:$PATH" "HOME=$WORK" TERM=dumb \
    zsh -f -i || return 1
  zpty -w $PTY "source ${(q)PLUGIN_DIR}/corral.plugin.zsh; print -r -- '@@RE''ADY@@'"
  if ! pty_read_until '@@READY@@'; then
    print -u2 '  harness: plugin never sourced; output was:'
    print -u2 -r -- "$REPLY"
    zpty -d $PTY 2>/dev/null
    return 1
  fi
  zpty -w $PTY "$cmd; print -r -- '@@DO''NE@@'; exit"
  local ok=0
  pty_read_until '@@DONE@@' && ok=1
  RAW=${REPLY//$'\r'/}
  zpty -d $PTY 2>/dev/null
  if (( ! ok )); then
    print -u2 '  harness: timed out running command; output was:'
    print -u2 -r -- "$RAW"
    return 1
  fi
  return 0
}

# --- assertions ------------------------------------------------------------------

# expect_exact <name> <stubdir> <typed-line> <expected match>...
expect_exact() {
  local name=$1 stubdir=$2 input=$3; shift 3
  local -a expected=( "${(@o)@}" )
  (( CASES++ ))
  if ! run_completion $stubdir $input; then
    print -u2 "FAIL  $name (harness error)"
    (( FAILS++ )); return 1
  fi
  if [[ ${(pj:\n:)expected} == ${(pj:\n:)ACTUAL} ]]; then
    print "ok    $name"
  else
    print -u2 "FAIL  $name — completing '${input}<TAB>'"
    print -u2 '      diff (< expected  |  > actual):'
    diff <(print -rl -- $expected) <(print -rl -- $ACTUAL) | sed 's/^/      /' >&2
    (( FAILS++ )); return 1
  fi
}

# expect_none_of <name> <stubdir> <typed-line> <forbidden match>...
expect_none_of() {
  local name=$1 stubdir=$2 input=$3; shift 3
  (( CASES++ ))
  if ! run_completion $stubdir $input; then
    print -u2 "FAIL  $name (harness error)"
    (( FAILS++ )); return 1
  fi
  local bad
  local -a found=()
  for bad in "$@"; do
    (( ${ACTUAL[(Ie)$bad]} )) && found+=( "$bad" )
  done
  if (( $#found )); then
    print -u2 "FAIL  $name — forbidden candidates appeared: $found"
    print -u2 "      full candidate list: $ACTUAL"
    (( FAILS++ )); return 1
  fi
  print "ok    $name"
}

# expect_output <name> <stubdir> <command> <required substring>...
expect_output() {
  local name=$1 stubdir=$2 cmd=$3; shift 3
  (( CASES++ ))
  if ! run_shell $stubdir $cmd; then
    print -u2 "FAIL  $name (harness error)"
    (( FAILS++ )); return 1
  fi
  local needle
  local -a missing=()
  for needle in "$@"; do
    [[ $RAW == *"$needle"* ]] || missing+=( "$needle" )
  done
  if (( $#missing )); then
    print -u2 "FAIL  $name — missing from output: ${(j:, :)missing}"
    print -u2 '      --- captured ---'
    print -u2 -r -- "$RAW"
    (( FAILS++ )); return 1
  fi
  print "ok    $name"
}

# --- completion cases --------------------------------------------------------------

print "== _corral completion tests (zsh $ZSH_VERSION) =="

expect_exact 'corral <TAB> lists all subcommands and aliases' \
  $WORK/stub-ok 'corral ' \
  spawn close ls list focus attach prune clean doctor version help

expect_exact 'corral spawn --<TAB> lists spawn long flags' \
  $WORK/stub-ok 'corral spawn --' \
  --agent --model --permission-mode --prompt --base --ratio --label --no-focus --help

expect_exact 'corral spawn --agent <TAB> lists agents' \
  $WORK/stub-ok 'corral spawn --agent ' \
  claude codex copilot droid opencode cursor none

# Matches are captured in compadd's insertion form, so the label containing a
# space arrives as 'tax:\ rounding' (colon unescaped, space backslashed).
expect_exact 'corral close <TAB> offers workspace ids and labels' \
  $WORK/stub-ok 'corral close ' \
  w4 w7 checkout-fix 'tax:\ rounding'

# Piggyback on the close case's raw capture: descriptions must be present.
(( CASES++ ))
if [[ $RAW == *'corral/app-1 (busy)'* && $RAW == *'bugfix/tax (idle)'* ]]; then
  print 'ok    close candidates carry "branch (status)" descriptions'
else
  print -u2 'FAIL  close candidate descriptions missing; raw block was:'
  print -u2 -r -- "$RAW"
  (( FAILS++ ))
fi

expect_exact 'corral focus <TAB> offers workspaces' \
  $WORK/stub-ok 'corral focus ' \
  w4 w7 checkout-fix 'tax:\ rounding'

expect_exact 'ccd <TAB> offers workspaces' \
  $WORK/stub-ok 'ccd ' \
  w4 w7 checkout-fix 'tax:\ rounding'

expect_exact 'corral ls --<TAB> lists ls flags' \
  $WORK/stub-ok 'corral ls --' \
  --json --help

expect_exact 'corral prune --<TAB> lists prune flags' \
  $WORK/stub-ok 'corral prune --' \
  --base --idle --dry-run --force --help

expect_exact 'corral doctor --<TAB> lists doctor flags' \
  $WORK/stub-ok 'corral doctor --' \
  --no-update --help

expect_exact 'corral help <TAB> completes subcommand names' \
  $WORK/stub-ok 'corral help ' \
  spawn close ls list focus attach prune clean doctor version help

expect_none_of 'corral close <TAB> degrades to empty when corral fails' \
  $WORK/stub-fail 'corral close ' \
  w4 w7 checkout-fix

expect_exact 'static completion still works when corral fails' \
  $WORK/stub-fail 'corral ' \
  spawn close ls list focus attach prune clean doctor version help

# --- plugin function cases ----------------------------------------------------------

print "== corral.plugin.zsh function tests =="

expect_output 'ccd cds into the worktree by label' \
  $WORK/stub-ok 'ccd checkout-fix && print -r -- "went-to:${PWD}:"' \
  "went-to:$WORK/wt-a:"

expect_output 'ccd cds into the worktree by id' \
  $WORK/stub-ok 'ccd w7 && print -r -- "went-to:${PWD}:"' \
  "went-to:$WORK/wt-b:"

expect_output 'ccd rejects an unknown workspace' \
  $WORK/stub-ok 'ccd nope-nothing; print -r -- "rc:$?:"' \
  'no agent workspace matches' 'rc:1:'

expect_output 'corral_prompt_info shows the workspace count' \
  $WORK/stub-ok 'print -r -- "seg=$(corral_prompt_info)."' \
  'seg=🐎 2.'

expect_output 'aliases are defined' \
  $WORK/stub-ok 'print -r -- "a=${aliases[csp]}|${aliases[cls]}|${aliases[ccl]}|${aliases[cfo]}|${aliases[cpr]}|${aliases[cdoc]}"' \
  'a=corral spawn|corral ls|corral close|corral focus|corral prune|corral doctor'

expect_output 'ccd fails cleanly when corral fails' \
  $WORK/stub-fail 'ccd; print -r -- "rc:$?:"' \
  'no active agent workspaces' 'rc:1:'

expect_output 'prompt segment is empty when corral fails' \
  $WORK/stub-fail 'print -r -- "seg=$(corral_prompt_info)."' \
  'seg=.'

# ---------------------------------------------------------------------------

print "== $(( CASES - FAILS ))/$CASES passed =="
(( FAILS == 0 )) || exit 1
exit 0
