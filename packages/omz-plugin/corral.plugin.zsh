# GENERATED FILE — do not edit by hand.
# Source of truth: packages/cli/src/corral/generate/zsh.py (+ the command specs)
# Regenerate with: python -m corral.generate (or: make generate)
#
# corral oh-my-zsh plugin — aliases, ccd, and a prompt segment.
# Tab completion comes from the _corral file next to this one (oh-my-zsh puts
# the plugin directory on fpath before compinit, so it loads automatically).

# Bail quietly if corral isn't installed yet.
(( $+commands[corral] )) || return 0

# Zsh Plugin Standard $0 handling: resolve this file's path however we were
# loaded (sourced, autoloaded, symlinked plugin dir, ...).
0="${${ZERO:-${0:#$ZSH_ARGZERO}}:-${(%):-%N}}"
0="${${(M)0:#/*}:-$PWD/$0}"

# Completion wiring. Under oh-my-zsh this is a no-op: omz adds the plugin
# directory to fpath BEFORE running compinit, so compinit discovers _corral
# via its #compdef line. The fallbacks cover other plugin managers and
# manual `source` use.
if (( ! ${fpath[(I)${0:h}]} )); then
  fpath=("${0:h}" $fpath)
fi
if (( $+functions[compdef] )) && ! (( $+functions[_corral] )); then
  autoload -Uz _corral
  compdef _corral corral ccd
fi

# ---------------------------------------------------------------------------
# Aliases — rendered from the command registry (each command's shell_alias).
# Only defined when the name isn't already a command/alias/function, so the
# plugin never shadows something you have.
# ---------------------------------------------------------------------------
() {
  local name target
  for name target in \
      csp 'corral spawn' \
      cls 'corral ls' \
      cfo 'corral focus' \
      cop 'corral open' \
      ccl 'corral close' \
      cpr 'corral prune' \
      crs 'corral resource' \
      cdoc 'corral doctor'; do
    (( $+commands[$name] || $+aliases[$name] || $+functions[$name] )) \
      || alias "$name"="$target"
  done
}

# ---------------------------------------------------------------------------
# ccd [workspace] — cd this shell into an agent's worktree.
# With no argument and exactly one active workspace, goes there; otherwise
# resolves the argument as a workspace id or label. Tab-completes via _corral.
# Built on `corral ls --tsv`: workspace, label, repo, branch, status, worktree.
# ---------------------------------------------------------------------------
ccd() {
  local rows
  rows="$(command corral ls --tsv 2>/dev/null)"
  if [[ -z "$rows" ]]; then
    print -u2 "ccd: no active agent workspaces (is the herdr server running?)"
    return 1
  fi

  local line
  local -a fields matches
  if [[ -z "${1-}" ]]; then
    matches=(${(f)rows})
    if (( $#matches > 1 )); then
      print -u2 "ccd: which workspace? one of:"
      for line in $matches; do
        fields=("${(@ps:\t:)line}")
        print -u2 "  ${(r:6:)fields[1]} ${fields[2]}"
      done
      return 1
    fi
  else
    for line in ${(f)rows}; do
      fields=("${(@ps:\t:)line}")
      if [[ "$fields[1]" == "$1" || "$fields[2]" == "$1" ]]; then
        matches+=("$line")
      fi
    done
    if (( $#matches == 0 )); then
      print -u2 "ccd: no agent workspace matches '$1' (see 'corral ls')"
      return 1
    fi
    if (( $#matches > 1 )); then
      print -u2 "ccd: '$1' is ambiguous — matches ${#matches} workspaces (use the id)"
      return 1
    fi
  fi

  fields=("${(@ps:\t:)matches[1]}")
  cd -- "$fields[6]"
}

# ---------------------------------------------------------------------------
# corral_prompt_info — active agent-workspace count for your prompt, in the
# style of git_prompt_info. Prints nothing when there are no workspaces (or no
# herdr server), so it stays invisible until you're actually herding agents.
#
#   RPROMPT='$(corral_prompt_info)'
#
# Note: this runs `corral ls` (one herdr socket call) on every prompt render.
# ---------------------------------------------------------------------------
: "${ZSH_THEME_CORRAL_PREFIX="🐎 "}"
: "${ZSH_THEME_CORRAL_SUFFIX=""}"

corral_prompt_info() {
  local -a rows
  rows=( ${(f)"$(command corral ls --tsv 2>/dev/null)"} )
  rows=( ${rows:#} )
  (( $#rows )) || return 0
  print -rn -- "${ZSH_THEME_CORRAL_PREFIX}${#rows}${ZSH_THEME_CORRAL_SUFFIX}"
}
