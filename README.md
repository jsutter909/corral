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
- `python3` (3.9+, stdlib only — no packages to install)

corral runs straight from a checkout; there's nothing to compile and nothing
to `pip install`.

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
corral start                                # bring up herdr + monitor + an agent per worktree, then attach
corral start --remote devbox                # same, but on a remote machine over SSH
corral start --no-agents                    # don't reopen agents for existing worktrees

# From your "command" pane in herdr:
corral spawn ~/dev/app                      # new worktree + workspace, launches claude
corral spawn ~/dev/app feature/checkout     # name the branch
corral spawn ~/dev/app --agent codex        # use a different agent
corral spawn ~/dev/app --base main          # branch from a specific ref
corral spawn ~/dev/app --prompt "fix tests" # hand the agent an opening prompt

corral ls                                   # see what's running
corral monitor                               # web dashboard at http://127.0.0.1:8477
corral focus checkout                        # jump to an agent by label or id
corral open checkout                         # open the worktree in VS Code/Cursor
corral close                                 # tear down the workspace you're in
corral prune                                 # remove merged + clean agent workspaces
corral doctor                                # check deps + update to the latest main
corral end                                   # stop the corral session + release its resources
```

## Commands

| Command | What it does |
| --- | --- |
| `corral start` | Start a herdr session (local, or remote over SSH) with `corral monitor` running and — on a fresh session — an agent workspace reopened for every existing worktree, then attach the herdr TUI. |
| `corral spawn <repo> [branch]` | Create an isolated worktree + workspace and launch an agent. |
| `corral ls [--json]` | List active agent workspaces (id, label, branch, status, path). |
| `corral monitor` | Serve a local web dashboard to monitor agents + resources and manage them (spawn/focus/close/release). |
| `corral focus <workspace>` | Switch focus to an agent by id or label (alias: `attach`). |
| `corral open [workspace]` | Open your IDE (VS Code or Cursor) in an agent's worktree — via Remote-SSH links when the herdr session is remote (alias: `ide`). |
| `corral close [workspace]` | Remove an agent's worktree and close its workspace. |
| `corral prune` | Remove agent workspaces that are merged **and** have a clean tree. |
| `corral doctor` | Check dependencies and update corral to the latest `main`. |
| `corral end` | Stop the persistent `corral` session (the teardown counterpart to `start`) and release the shared resources its worktrees still hold. |
| `corral help [command]` | Help, optionally for a specific command. |

Every command has `--help`. Full reference: [`docs/usage.md`](docs/usage.md).

### Safety

corral only ever touches worktrees it created: **linked** git worktrees under
`~/.herdr/worktrees/…`. It will **refuse** to `close` or `prune` your primary
repo checkout or a worktree you made by hand. `prune` never removes a workspace
with uncommitted changes, and only considers unmerged branches when you
explicitly pass `--idle`.

## Configuration

Defaults live in `~/.config/corral/config.sh` (parsed for plain `CORRAL_*`
assignments — existing configs keep working); `CORRAL_*` env vars and CLI
flags override them.

```sh
# ~/.config/corral/config.sh
CORRAL_AGENT=claude          # or codex, copilot, droid, opencode, cursor, none
CORRAL_MODEL=                # model for the claude agent ("" = Claude's default)
CORRAL_PERMISSION_MODE=      # claude edit mode: acceptEdits, plan, … (claude only)
CORRAL_IDE=vscode            # IDE for 'corral open': vscode or cursor
CORRAL_RATIO=0.4             # agent pane width share, 0..1
CORRAL_BRANCH_PREFIX=agent   # <prefix>/<repo>-<timestamp>
CORRAL_BASE=main             # base ref for new worktrees ("" = current HEAD)
```

A repo can also commit a `.corral/setup.sh` to prepare each workspace (install
deps, copy a `.env`, …) — spawn runs it in the agent pane and only starts the
agent once it succeeds — and a `.corral/cleanup.sh` to tear it down: corral runs
it in the worktree before `close`/`prune` removes it, and aborts the removal if
it fails (override with `--force`, or skip the script with `--no-cleanup`).

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
│   ├── cli/                # the corral CLI (Python, stdlib only)
│   │   ├── bin/corral      # launcher (symlinked onto PATH)
│   │   ├── src/corral/     # the package: commands, registries, herdr client
│   │   │   └── generate/   # renders the generated artifacts below
│   │   ├── share/          # config.example.sh (generated)
│   │   └── tests/          # unit + CLI-surface tests
│   └── omz-plugin/         # oh-my-zsh plugin (generated): completions, aliases, ccd, prompt
├── docs/                   # usage + configuration (generated), architecture
├── install.sh              # curl-able installer
└── Makefile                # install / link / generate / lint / test
```

The repo is a monorepo on purpose — tooling grows alongside the CLI under
`packages/`. See [`packages/README.md`](packages/README.md) for the plan.

### Generated, not hand-maintained

corral's command specs, settings, agents, and IDEs are each declared once, as
Python registries. The command reference (`docs/usage.md`), the configuration
guide (`docs/configuration.md`), the example config, and the entire oh-my-zsh
plugin (`_corral` completions + `corral.plugin.zsh`) are **rendered from those
registries** and checked in. Add a flag or an agent in one place, run
`make generate`, and the parser, `--help`, docs, and tab completion all update
together — CI fails if they drift.

## Development

```sh
make link       # symlink the working tree's launcher into ~/.local/bin
make generate   # re-render docs + omz plugin from the registries
make test       # python unit tests + zsh completion tests (no herdr server needed)
make lint       # byte-compile, shellcheck install.sh, zsh -n the plugin
make check      # lint + generated-artifact freshness + test
```

Contributions welcome — see [`CONTRIBUTING.md`](CONTRIBUTING.md).

## License

[MIT](LICENSE).
