# corral — oh-my-zsh plugin

Zsh niceties for the [corral CLI](../cli/): tab completion for every command,
short aliases, a `ccd` helper that cd's into an agent's worktree, and an
optional prompt segment showing how many agents you're herding.

## What you get

**Tab completion** for all commands, flags, and — where it matters — live
values:

```text
corral <TAB>                 # spawn / close / ls / focus / prune / doctor / …
corral spawn --<TAB>         # --agent --model --prompt --base --ratio --label --no-focus (short: -a -m -p -b -r -l)
corral spawn --agent <TAB>   # claude codex copilot droid opencode cursor none
corral spawn --base <TAB>    # branches of the repo you're in
corral close <TAB>           # live workspace ids AND labels, with branch + status
corral focus <TAB>           # same
```

Workspace completion is fetched live from `corral ls --json`, so it always
matches reality; when the herdr server isn't running it quietly completes
nothing.

**Aliases** (each is skipped if the name is already taken on your system):

| Alias | Expands to |
| --- | --- |
| `csp` | `corral spawn` |
| `cls` | `corral ls` |
| `ccl` | `corral close` |
| `cfo` | `corral focus` |
| `cpr` | `corral prune` |
| `cdoc` | `corral doctor` |

**`ccd [workspace]`** — cd into an agent's worktree by id or label (with tab
completion). This is a shell function, so it moves *your current shell* —
something the corral binary itself can't do:

```sh
ccd checkout-fix     # cd ~/.herdr/worktrees/app/agent-checkout-fix…
ccd                  # with exactly one active workspace: go there
```

**`corral_prompt_info`** — a prompt segment in the style of oh-my-zsh's
`git_prompt_info`. Prints `🐎 3` when three agent workspaces are active,
nothing when there are none. Not enabled automatically — add it yourself:

```sh
# ~/.zshrc, after oh-my-zsh loads
setopt prompt_subst
RPROMPT='$(corral_prompt_info)'
```

Customize with `ZSH_THEME_CORRAL_PREFIX` / `ZSH_THEME_CORRAL_SUFFIX`.
Heads-up: it runs one `corral ls` (a herdr socket call) per prompt render.

## Install

### oh-my-zsh

```sh
# 1. Link this directory in as a custom plugin named "corral"
#    (install.sh puts the repo at ~/.local/share/corral)
ln -s ~/.local/share/corral/packages/omz-plugin \
      "${ZSH_CUSTOM:-$HOME/.oh-my-zsh/custom}/plugins/corral"

# 2. Add corral to the plugins list in ~/.zshrc
#      plugins=(git corral)

# 3. Reload
exec zsh
```

If you cloned the repo yourself (e.g. `~/dev/corral`), link that path instead:

```sh
ln -s ~/dev/corral/packages/omz-plugin \
      "${ZSH_CUSTOM:-$HOME/.oh-my-zsh/custom}/plugins/corral"
```

If completions don't appear, your compinit dump is stale — rebuild it:

```sh
rm -f ~/.zcompdump* "${ZSH_COMPDUMP:-}" && exec zsh
```

### plain zsh (no oh-my-zsh)

```sh
# ~/.zshrc — before compinit runs
fpath=(~/dev/corral/packages/omz-plugin $fpath)
autoload -Uz compinit && compinit
source ~/dev/corral/packages/omz-plugin/corral.plugin.zsh
```

## Files

```
omz-plugin/
├── corral.plugin.zsh    # aliases, ccd, corral_prompt_info
├── _corral              # completion (#compdef corral ccd)
└── test/
    └── completions.zsh  # pty-driven completion tests (no herdr needed)
```

Run the tests with `zsh test/completions.zsh` (or `make test` at the repo
root). They drive a real interactive zsh in a pseudo-terminal against a stubbed
`corral`, so no herdr server is required.
