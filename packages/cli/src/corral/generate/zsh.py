"""Render the oh-my-zsh plugin from the registries.

* ``_corral`` — tab completion. Flags, exclusions, value candidates, and the
  agent/command lists all come from the command specs and the agent registry.
* ``corral.plugin.zsh`` — the alias table comes from each command's
  ``shell_alias``; ccd and the prompt segment are templates built on
  ``corral ls --tsv`` (no jq needed).
"""

from __future__ import annotations

from typing import List

from ..agents import AGENTS
from ..cli import Argument, Command, Option
from ..commands import all_commands
from . import generated_header

_SOURCE = "packages/cli/src/corral/generate/zsh.py (+ the command specs)"


def _zq(text: str) -> str:
    """Escape for interpolation inside a zsh single-quoted string."""
    return text.replace("'", "'\\''")


def _first_line(text: str) -> str:
    return text.splitlines()[0].rstrip(",.")


# ---------------------------------------------------------------------------
# _corral (completion)
# ---------------------------------------------------------------------------


def _option_spec(opt: Option) -> str:
    desc = _zq(_first_line(opt.help))
    value = ""
    if not opt.is_flag:
        hint = _zq(opt.value_hint or opt.metavar.strip("<>"))
        if opt.completion:
            action = opt.completion
        elif opt.choices:
            action = "(" + " ".join(opt.choices) + ")"
        else:
            action = ""
        value = f":{hint}:{action}"
    if opt.short:
        group = " ".join((*opt.excludes, opt.short, opt.long))
        return f"'({group})'{{{opt.short},{opt.long}}}'[{desc}]{value}'"
    if opt.excludes:
        group = " ".join(opt.excludes)
        return f"'({group}){opt.long}[{desc}]{value}'"
    return f"'{opt.long}[{desc}]{value}'"


def _argument_spec(position: int, arg: Argument) -> str:
    label = _zq(arg.value_label or arg.name)
    colon = ":" if arg.required else "::"
    return f"'{position}{colon}{label}:{arg.completion}'"


def _command_case(spec: Command) -> List[str]:
    lines = [f"        {spec.name})", "          _arguments -S \\"]
    specs = [f"'(- *)'{{-h,--help}}'[show {spec.name} help]'"]
    specs += [_option_spec(opt) for opt in spec.options]
    specs += [_argument_spec(i + 1, arg) for i, arg in enumerate(spec.arguments)]
    lines += [f"            {s} \\" for s in specs]
    lines += ["            && ret=0", "          ;;"]
    return lines


def _agents_fn() -> str:
    entries = "\n".join(
        f"    '{_zq(agent.name)}:{_zq(agent.summary)}'" for agent in AGENTS
    )
    return f"""\
# Agents accepted by `corral spawn --agent` — rendered from the agent
# registry (corral.agents.AGENTS); any herdr-integrated agent also works.
_corral_agents() {{
  local -a agents=(
{entries}
  )
  _describe -t agents 'agent' agents
}}"""


def _commands_fn() -> str:
    entries = []
    for registered in all_commands():
        spec = registered.spec
        entries.append(f"    '{spec.name}:{_zq(spec.summary.rstrip('.'))}'")
        for alias in spec.aliases:
            entries.append(
                f"    '{alias}:{_zq(spec.summary.rstrip('.'))} (alias for {spec.name})'"
            )
    body = "\n".join(entries)
    return f"""\
_corral_commands() {{
  local -a cmds=(
{body}
    'version:print the corral version'
    'help:show help (add a command name for details)'
  )
  _describe -t commands 'corral command' cmds
}}"""


_STATIC_HELPERS = """\
# Git refs for --base. Pragmatic choice: complete refs of the repo containing
# the spawn <repo> positional when it has been typed and is a directory,
# otherwise the current directory's repo. Silently no matches outside a repo.
# ($line is visible here via dynamic scope from the calling _arguments.)
_corral_git_refs() {
  local dir=${line[1]:-.}
  [[ -d $dir ]] || dir=.
  local -a refs
  refs=( ${(f)"$(command git -C $dir for-each-ref \\
    --format='%(refname:short)' refs/heads refs/remotes refs/tags 2>/dev/null)"} )
  refs=( ${refs:#(*/|)HEAD} )
  (( $#refs )) || return 1
  _wanted refs expl 'git ref' compadd -a refs
}

_corral_new_branch() {
  _message 'new branch name (default: <prefix>/<repo>-<timestamp>)'
}

# Active workspaces from `corral ls --tsv` (columns: workspace, label, repo,
# branch, status, worktree), offered as both ids and labels, described as
# "label — branch (status)".
#
# * One `corral ls` call per completion invocation; deliberately NOT cached
#   via _store_cache/zcompcache — workspaces churn constantly and a stale
#   cache is worse than a ~25ms subprocess.
# * Degrades silently to "no matches" when the herdr server is down: corral
#   exits nonzero fast (local check), so no timeout wrapper is needed.
# * Colons in labels are escaped for _describe, which splits each pair on the
#   first unescaped colon.
_corral_workspaces() {
  local -a rows pairs parts
  rows=( ${(f)"$(command corral ls --tsv 2>/dev/null)"} )

  local row ws label branch wstatus   # NB: "status" is read-only in zsh
  for row in $rows; do
    parts=( "${(@ps:\\t:)row}" )
    ws=$parts[1] label=$parts[2] branch=$parts[4] wstatus=$parts[5]
    [[ -n $ws ]] || continue
    pairs+=( "${ws//:/\\\\:}:${label} — ${branch} (${wstatus})" )
    if [[ -n $label && $label != $ws ]]; then
      pairs+=( "${label//:/\\\\:}:${ws} — ${branch} (${wstatus})" )
    fi
  done

  (( $#pairs )) || return 1
  _describe -t workspaces 'workspace (id or label)' pairs
}"""


def render_completion() -> str:
    lines = [
        "#compdef corral ccd",
        generated_header("#", _SOURCE).rstrip(),
        "#",
        "# Completion for corral — isolated AI-agent workspaces on top of herdr.",
        "# Lives at the plugin root: oh-my-zsh puts the plugin directory itself on",
        "# fpath before running compinit, so this file is picked up automatically.",
        "# Also completes ccd (from corral.plugin.zsh), which takes one workspace.",
        "",
        "# --- value helpers ----------------------------------------------------------",
        "",
        _agents_fn(),
        "",
        _STATIC_HELPERS,
        "",
        "# --- subcommands -------------------------------------------------------------",
        "",
        _commands_fn(),
        "",
        "# --- main dispatcher ----------------------------------------------------------",
        "",
        "_corral() {",
        "  # ccd (plugin function) takes a single workspace argument.",
        "  if [[ $service == ccd ]]; then",
        "    _arguments '1:workspace:_corral_workspaces'",
        "    return",
        "  fi",
        "",
        '  local curcontext="$curcontext" state state_descr line ret=1',
        "  typeset -A opt_args",
        "",
        "  _arguments -C \\",
        "    '(- *)'{-h,--help}'[show help]' \\",
        "    '(- *)'{-V,--version}'[print the corral version]' \\",
        "    '1: :->command' \\",
        "    '*:: :->args' && ret=0",
        "",
        "  case $state in",
        "    command)",
        "      _corral_commands && ret=0",
        "      ;;",
        "    args)",
        "      local cmd=${line[1]}",
        "      case $cmd in            # aliases share their target's completion",
    ]
    alias_map = [
        (alias, registered.spec.name)
        for registered in all_commands()
        for alias in registered.spec.aliases
    ]
    width = max(len(alias) for alias, _ in alias_map) + 1
    for alias, target in alias_map:
        lines.append(f"        {alias + ')':<{width + 1}} cmd={target} ;;")
    lines += [
        "      esac",
        '      curcontext="${curcontext%:*:*}:corral-${cmd}:"',
        "      case $cmd in",
    ]
    for registered in all_commands():
        lines += _command_case(registered.spec)
    lines += [
        "        help)",
        "          _arguments '1::command:_corral_commands' && ret=0",
        "          ;;",
        "        version)",
        "          _message 'no more arguments'",
        "          ;;",
        "      esac",
        "      ;;",
        "  esac",
        "",
        "  return ret",
        "}",
        "",
        '_corral "$@"',
    ]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# corral.plugin.zsh
# ---------------------------------------------------------------------------


def _alias_rows() -> str:
    pairs = [
        (spec.shell_alias, f"corral {spec.name}")
        for spec in (r.spec for r in all_commands())
        if spec.shell_alias
    ]
    body = " \\\n".join(f"      {name} '{target}'" for name, target in pairs)
    return body


def render_plugin() -> str:
    return f"""\
{generated_header("#", _SOURCE).rstrip()}
#
# corral oh-my-zsh plugin — aliases, ccd, and a prompt segment.
# Tab completion comes from the _corral file next to this one (oh-my-zsh puts
# the plugin directory on fpath before compinit, so it loads automatically).

# Bail quietly if corral isn't installed yet.
(( $+commands[corral] )) || return 0

# Zsh Plugin Standard $0 handling: resolve this file's path however we were
# loaded (sourced, autoloaded, symlinked plugin dir, ...).
0="${{${{ZERO:-${{0:#$ZSH_ARGZERO}}}}:-${{(%):-%N}}}}"
0="${{${{(M)0:#/*}}:-$PWD/$0}}"

# Completion wiring. Under oh-my-zsh this is a no-op: omz adds the plugin
# directory to fpath BEFORE running compinit, so compinit discovers _corral
# via its #compdef line. The fallbacks cover other plugin managers and
# manual `source` use.
if (( ! ${{fpath[(I)${{0:h}}]}} )); then
  fpath=("${{0:h}}" $fpath)
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
() {{
  local name target
  for name target in \\
{_alias_rows()}; do
    (( $+commands[$name] || $+aliases[$name] || $+functions[$name] )) \\
      || alias "$name"="$target"
  done
}}

# ---------------------------------------------------------------------------
# ccd [workspace] — cd this shell into an agent's worktree.
# With no argument and exactly one active workspace, goes there; otherwise
# resolves the argument as a workspace id or label. Tab-completes via _corral.
# Built on `corral ls --tsv`: workspace, label, repo, branch, status, worktree.
# ---------------------------------------------------------------------------
ccd() {{
  local rows
  rows="$(command corral ls --tsv 2>/dev/null)"
  if [[ -z "$rows" ]]; then
    print -u2 "ccd: no active agent workspaces (is the herdr server running?)"
    return 1
  fi

  local line
  local -a fields matches
  if [[ -z "${{1-}}" ]]; then
    matches=(${{(f)rows}})
    if (( $#matches > 1 )); then
      print -u2 "ccd: which workspace? one of:"
      for line in $matches; do
        fields=("${{(@ps:\\t:)line}}")
        print -u2 "  ${{(r:6:)fields[1]}} ${{fields[2]}}"
      done
      return 1
    fi
  else
    for line in ${{(f)rows}}; do
      fields=("${{(@ps:\\t:)line}}")
      if [[ "$fields[1]" == "$1" || "$fields[2]" == "$1" ]]; then
        matches+=("$line")
      fi
    done
    if (( $#matches == 0 )); then
      print -u2 "ccd: no agent workspace matches '$1' (see 'corral ls')"
      return 1
    fi
    if (( $#matches > 1 )); then
      print -u2 "ccd: '$1' is ambiguous — matches ${{#matches}} workspaces (use the id)"
      return 1
    fi
  fi

  fields=("${{(@ps:\\t:)matches[1]}}")
  cd -- "$fields[6]"
}}

# ---------------------------------------------------------------------------
# corral_prompt_info — active agent-workspace count for your prompt, in the
# style of git_prompt_info. Prints nothing when there are no workspaces (or no
# herdr server), so it stays invisible until you're actually herding agents.
#
#   RPROMPT='$(corral_prompt_info)'
#
# Note: this runs `corral ls` (one herdr socket call) on every prompt render.
# ---------------------------------------------------------------------------
: "${{ZSH_THEME_CORRAL_PREFIX="🐎 "}}"
: "${{ZSH_THEME_CORRAL_SUFFIX=""}}"

corral_prompt_info() {{
  local -a rows
  rows=( ${{(f)"$(command corral ls --tsv 2>/dev/null)"}} )
  rows=( ${{rows:#}} )
  (( $#rows )) || return 0
  print -rn -- "${{ZSH_THEME_CORRAL_PREFIX}}${{#rows}}${{ZSH_THEME_CORRAL_SUFFIX}}"
}}
"""
