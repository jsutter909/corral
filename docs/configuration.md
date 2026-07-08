# corral — configuration

corral resolves each setting in this order (later wins):

1. **Built-in defaults** (in `packages/cli/lib/common.sh`)
2. **`~/.config/corral/config.sh`** (or `$XDG_CONFIG_HOME/corral/config.sh`)
3. **`CORRAL_*` environment variables**
4. **Command-line flags**

> The config file is sourced as plain Bash, but corral snapshots your `CORRAL_*`
> environment first and re-applies it after — so values in `config.sh` act as
> your team/personal defaults, while a one-off `CORRAL_RATIO=0.5 corral spawn …`
> or a `--ratio` flag overrides them per run.

## Settings

| Variable | Flag | Default | Meaning |
| --- | --- | --- | --- |
| `CORRAL_AGENT` | `--agent` | `claude` | Agent launched in the left pane, or `none`. |
| `CORRAL_MODEL` | `--model` | `` (Claude's default) | Model for the Claude agent (claude only). |
| `CORRAL_PERMISSION_MODE` | `--permission-mode` | `` (Claude's default) | Claude permission/edit mode, e.g. `acceptEdits`, `plan` (claude only). |
| `CORRAL_RATIO` | `--ratio` | `0.4` | Agent (left) pane width share, `0..1`. |
| `CORRAL_SETUP` | `--no-setup` | `1` | Run a repo's committed `.corral/setup.sh` before the agent (`0` = never). |
| `CORRAL_BRANCH_PREFIX` | — | `agent` | Prefix for auto branch names: `<prefix>/<repo>-<timestamp>`. |
| `CORRAL_BASE` | `--base` | `` (HEAD) | Base ref for new worktrees. |
| `CORRAL_WORKTREES_DIR` | — | `~/.herdr/worktrees` | Where herdr checks out corral's worktrees; corral only ever destroys worktrees under this directory. |
| `CORRAL_CONFIG` | — | `~/.config/corral/config.sh` | Path to the config file itself. |

## Setting it up

```sh
mkdir -p ~/.config/corral
cp "$(dirname "$(readlink -f "$(command -v corral)")")/../share/config.example.sh" \
   ~/.config/corral/config.sh
$EDITOR ~/.config/corral/config.sh
```

Or just create it by hand:

```sh
# ~/.config/corral/config.sh
CORRAL_AGENT=claude
CORRAL_RATIO=0.4
CORRAL_BRANCH_PREFIX=agent
CORRAL_BASE=main
```

## Per-repo configuration: `.corral/`

A repo can commit a `.corral/` directory to customize the workspaces corral
spawns from it. corral reads it from the **new worktree** (i.e. from the base
ref you branch from), never from your primary checkout — so what runs is
exactly what's committed on that ref, and uncommitted local files are ignored.

| File | Status | Meaning |
| --- | --- | --- |
| `.corral/setup.sh` | supported | Environment setup run in the agent pane before the agent: `bash .corral/setup.sh && <agent>`. The agent starts only if it exits 0; on failure the workspace is kept and the error stays visible in the pane. Needs no executable bit. |
| `.corral/config.sh` | reserved | Per-repo spawn defaults (future). |
| `.corral/layout.sh` | reserved | Pane/layout customization (future). |
| `.corral/watch.d/` | reserved | Watch scripts launched in extra panes/tabs (future). |

Unknown files in `.corral/` are ignored today, but treat the directory as a
reserved namespace.

The setup script runs in the pane's own shell with cwd = the worktree and no
extra environment; derive what you need from there (`pwd`,
`git rev-parse --abbrev-ref HEAD`, …). Typical uses: installing dependencies,
copying a `.env` from the primary checkout, `direnv allow`.

Skip it for one run with `corral spawn <repo> --no-setup`, or disable it
globally with `CORRAL_SETUP=0`.

> **Security.** `.corral/setup.sh` is repository-provided code executed with
> your user's privileges the moment you spawn — the same trust decision as
> running a repo's `Makefile`, an npm `postinstall` hook, or a direnv file.
> Review `.corral/` before spawning agents on a repo you don't trust, or skip
> it with `--no-setup` (per run) / `CORRAL_SETUP=0` (globally).

## Team defaults

Because it's just Bash, you can share a config in your repo and have coworkers
source it, e.g. point `CORRAL_CONFIG` at a checked-in file:

```sh
export CORRAL_CONFIG="$HOME/dev/team-dotfiles/corral.sh"
```
