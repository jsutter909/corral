<!--
  GENERATED FILE — do not edit by hand.
  Source of truth: packages/cli/src/corral/settings.py (+ this module's prose)
  Regenerate with: python -m corral.generate (or: make generate)
-->

# corral — configuration

corral resolves each setting in this order (later wins):

1. **Built-in defaults** (in `packages/cli/src/corral/settings.py`)
2. **`~/.config/corral/config.sh`** (or `$XDG_CONFIG_HOME/corral/config.sh`)
3. **`CORRAL_*` environment variables**
4. **Command-line flags**

> The config file keeps its historical shell syntax (`CORRAL_AGENT=claude`,
> quotes and `$HOME`/`~` expansion supported), so existing configs keep
> working — but corral **parses** it rather than sourcing it: only plain
> `CORRAL_*` assignments are honored, never arbitrary shell. Values in
> `config.sh` act as your team/personal defaults, while a one-off
> `CORRAL_RATIO=0.5 corral spawn …` or a `--ratio` flag overrides them per run.

## Settings

| Variable | Flag | Default | Meaning |
| --- | --- | --- | --- |
| `CORRAL_AGENT` | `--agent` | `claude` | Agent launched in the left pane, or `none`. |
| `CORRAL_MODEL` | `--model` | `` (Claude's default) | Model for the Claude agent (claude only). |
| `CORRAL_PERMISSION_MODE` | `--permission-mode` | `` (Claude's default) | Claude permission/edit mode, e.g. `acceptEdits`, `plan` (claude only). |
| `CORRAL_RATIO` | `--ratio` | `0.4` | Agent (left) pane width share, `0..1`. |
| `CORRAL_SETUP` | `--no-setup` | `1` | Run a repo's committed `.corral/setup.sh` before the agent (`0` = never). |
| `CORRAL_CLEANUP` | `--no-cleanup` | `1` | Run a worktree's `.corral/cleanup.sh` before removing it on close/prune (`0` = never). |
| `CORRAL_IDE` | `--ide` | `vscode` | IDE opened by `corral open`: `vscode` or `cursor`. |
| `CORRAL_SSH_HOST` | `--host` | `` (this machine's hostname) | SSH host in the Remote-SSH links `corral open` prints for remote (`herdr --remote`) sessions; must match a `Host` entry in your **local** `~/.ssh/config`. |
| `CORRAL_REMOTE` | `--remote` | `` (local — this machine) | SSH target `corral start` attaches to, same syntax as `herdr --remote` (a `Host` alias in your `~/.ssh/config`, or `user@host`). Empty runs herdr on this machine. |
| `CORRAL_BRANCH_PREFIX` | — | `agent` | Prefix for auto branch names: `<prefix>/<repo>-<timestamp>`. |
| `CORRAL_BASE` | `--base` | `` (HEAD) | Base ref for new worktrees. |
| `CORRAL_WORKTREES_DIR` | — | `~/.herdr/worktrees` | Where herdr checks out corral's worktrees; corral only ever destroys worktrees under this directory. |
| `CORRAL_RESOURCES_DB` | — | `~/.local/state/corral/resources.db` | SQLite database backing `corral resource` pools and leases (one per machine — all workspaces share it). |
| `CORRAL_MONITOR_HOST` | `--host` | `127.0.0.1` | Address `corral monitor` binds its web UI to. Defaults to loopback (local only); set to `0.0.0.0` to expose it on your network. |
| `CORRAL_MONITOR_PORT` | `--port` | `8477` | Port `corral monitor` serves its web UI on. |
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
spawns from it. At spawn time corral reads it from the **new worktree** (i.e.
from the base ref you branch from), never from your primary checkout — so what
runs at spawn is exactly what's committed on that ref. The exception is
`.corral/cleanup.sh`, which runs at **close/prune time** and executes as it
exists in the worktree at that moment — including changes made during the
session (see the security note below).

| File | Status | Meaning |
| --- | --- | --- |
| `.corral/setup.sh` | supported | Environment setup run in the agent pane before the agent: `bash .corral/setup.sh && <agent>`. The agent starts only if it exits 0; on failure the workspace is kept and the error stays visible in the pane. Needs no executable bit. |
| `.corral/cleanup.sh` | supported | Teardown run in the worktree (`bash .corral/cleanup.sh`, stdin closed) before it is removed on close/prune, as the script exists at that moment. If it exits non-zero the removal is aborted and the worktree kept; `--force` removes anyway, `--no-cleanup` skips the script. Needs no executable bit. |
| `.corral/resources.json` | supported | Shared resource pools (dev ports, app credentials, …) synced into the machine-wide database by `corral resource` — see [usage.md](usage.md#corral-resource). |
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

`.corral/resources.json` declares shared resource pools the repo's workspaces
draw from (see [`corral resource`](usage.md#corral-resource) for the format
and sync semantics). To reserve a resource for every workspace at spawn time,
acquire it in `setup.sh` — the holder is detected from the worktree path, and
`corral close`/`corral prune` return whatever the workspace still holds:

```sh
# .corral/setup.sh
PORT=$(corral resource acquire ports --wait=60) || exit 1
echo "DEV_PORT=$PORT" >> .env
```

`.corral/cleanup.sh` is the teardown counterpart: it runs in the worktree
(cwd = the worktree, stdin closed) right before `corral close`/`corral prune`
removes it — tear down anything `setup.sh` created outside the worktree
(containers, tunnels, cloud resources, scratch directories). If it exits
non-zero the removal is **aborted** and the worktree kept, so a failed
teardown never silently loses cleanup work. From there: `--force` removes
anyway (note it runs the script again, so keep cleanup idempotent),
`--no-cleanup` removes without running the script at all, and
`CORRAL_CLEANUP=0` disables cleanup globally. Spawn's rollback (when spawn
fails partway) also runs cleanup best-effort before removing the partial
worktree.

> **Security.** `.corral/setup.sh` and `.corral/cleanup.sh` are
> repository-provided code executed with your user's privileges — the same
> trust decision as running a repo's `Makefile`, an npm `postinstall` hook, or
> a direnv file. Setup runs what's committed on the ref you spawn from;
> cleanup runs whatever `.corral/cleanup.sh` the worktree contains at
> close/prune time — **including changes an agent made during the session**.
> Review it before closing a workspace you don't trust, or skip execution with
> `--no-setup` / `--no-cleanup` (per run) or `CORRAL_SETUP=0` /
> `CORRAL_CLEANUP=0` (globally).

## Team defaults

You can share a config in your repo and have coworkers point `CORRAL_CONFIG`
at the checked-in file:

```sh
export CORRAL_CONFIG="$HOME/dev/team-dotfiles/corral.sh"
```
