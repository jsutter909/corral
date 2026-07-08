# 🐎 corral

> Isolated AI-agent workspaces, one command at a time — built on [herdr](https://herdr.dev).

`corral` turns your herdr session into a control center for parallel coding agents.
Point it at a repo and it spins up a fully isolated **git worktree** in its own
**herdr workspace**, laid out for hands-on agent work:

```
+------------------+-------------+
|                  |  terminal   |   left  : your agent (Claude Code by default),
|   agent (claude) +-------------+           full height
|                  |  terminal   |   right : two terminals, both cwd'd into the
+------------------+-------------+           worktree
```

Run several at once — each agent gets its own branch, its own files, and its own
window. Nothing steps on anything else. When an agent's done, one command tears
the whole thing down.

## Requirements

- [`herdr`](https://herdr.dev) — the terminal workspace manager corral drives
- `git`
- `jq`

corral is pure Bash, so there's nothing to compile.

## Install

```sh
curl -fsSL https://raw.githubusercontent.com/jsutter909/corral/main/install.sh | bash
```

This clones corral to `~/.local/share/corral` and symlinks `corral` into
`~/.local/bin`. Make sure that's on your `PATH`. To update later, re-run the same
line (or `git -C ~/.local/share/corral pull`).

<details>
<summary>Install from a clone instead</summary>

```sh
git clone https://github.com/jsutter909/corral.git
cd corral
make install      # or: make link  (symlink the working tree for development)
```
</details>

## Quickstart

```sh
# From your "command" pane in herdr:
corral spawn ~/dev/app                      # new worktree + workspace, launches claude
corral spawn ~/dev/app feature/checkout     # name the branch
corral spawn ~/dev/app --agent codex        # use a different agent
corral spawn ~/dev/app --base main          # branch from a specific ref

corral ls                                   # see what's running
corral focus checkout                        # jump to an agent by label or id
corral close                                 # tear down the workspace you're in
corral prune                                 # remove merged + clean agent workspaces
```

## Commands

| Command | What it does |
| --- | --- |
| `corral spawn <repo> [branch]` | Create an isolated worktree + workspace and launch an agent. |
| `corral ls [--json]` | List active agent workspaces (id, label, branch, status, path). |
| `corral focus <workspace>` | Switch focus to an agent by id or label (alias: `attach`). |
| `corral close [workspace]` | Remove an agent's worktree and close its workspace. |
| `corral prune` | Remove agent workspaces that are merged **and** have a clean tree. |
| `corral help [command]` | Help, optionally for a specific command. |

Every command has `--help`. Full reference: [`docs/usage.md`](docs/usage.md).

### Safety

corral only ever touches worktrees it created: **linked** git worktrees under
`~/.herdr/worktrees/…`. It will **refuse** to `close` or `prune` your primary
repo checkout or a worktree you made by hand. `prune` never removes a workspace
with uncommitted changes, and only considers unmerged branches when you
explicitly pass `--idle`.

## Configuration

Defaults live in `~/.config/corral/config.sh`; `CORRAL_*` env vars and CLI flags
override them.

```sh
# ~/.config/corral/config.sh
CORRAL_AGENT=claude          # or codex, copilot, droid, opencode, cursor, none
CORRAL_MODEL=                # model for the claude agent ("" = Claude's default)
CORRAL_PERMISSION_MODE=      # claude edit mode: acceptEdits, plan, … (claude only)
CORRAL_RATIO=0.4             # agent pane width share, 0..1
CORRAL_BRANCH_PREFIX=agent   # <prefix>/<repo>-<timestamp>
CORRAL_BASE=main             # base ref for new worktrees ("" = current HEAD)
```

See [`docs/configuration.md`](docs/configuration.md) and
[`packages/cli/share/config.example.sh`](packages/cli/share/config.example.sh).

## oh-my-zsh plugin

Tab completion for every command (including live workspace ids/labels), short
aliases, `ccd` to hop your shell into an agent's worktree, and an optional
`corral_prompt_info` prompt segment:

```sh
ln -s ~/.local/share/corral/packages/omz-plugin \
      "${ZSH_CUSTOM:-$HOME/.oh-my-zsh/custom}/plugins/corral"
# then add corral to plugins=(...) in ~/.zshrc and restart your shell
```

Full details (including plain-zsh install): [`packages/omz-plugin/README.md`](packages/omz-plugin/README.md).

## How it works

`corral spawn` is a thin, well-tested wrapper over herdr's socket API:

1. `herdr worktree create` — makes the git worktree **and** a fresh, isolated
   workspace in one call.
2. `herdr pane split` (×2) — carves the agent pane on the left and two stacked
   terminals on the right.
3. `herdr pane run` — launches your agent in the left pane.

Details and the herdr concepts involved: [`docs/architecture.md`](docs/architecture.md).

## Monorepo layout

```
corral/
├── packages/
│   ├── cli/            # the corral CLI (this is what installs today)
│   │   ├── bin/corral  # dispatcher
│   │   ├── lib/        # one file per subcommand + common helpers
│   │   ├── share/      # config.example.sh
│   │   └── test/       # smoke tests
│   └── omz-plugin/     # oh-my-zsh plugin: completions, aliases, ccd, prompt
├── docs/               # usage, configuration, architecture
├── install.sh          # curl-able installer
└── Makefile            # install / link / lint / test
```

The repo is a monorepo on purpose — tooling grows alongside the CLI under
`packages/`. See [`packages/README.md`](packages/README.md) for the plan.

## Development

```sh
make link     # symlink the working tree's launcher into ~/.local/bin
make test     # smoke tests + zsh completion tests (no herdr server needed)
make lint     # shellcheck + zsh -n (if installed)
make check    # lint + test
```

Contributions welcome — see [`CONTRIBUTING.md`](CONTRIBUTING.md).

## License

[MIT](LICENSE).
