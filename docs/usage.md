<!--
  GENERATED FILE — do not edit by hand.
  Source of truth: packages/cli/src/corral/commands/*.py (each command's SPEC)
  Regenerate with: python -m corral.generate (or: make generate)
-->

# corral — command reference

Every command also prints this via `corral <command> --help`.

## `corral start [options]`

Bring up corral's herdr session and drop you into it, with `corral monitor`
already running in a `monitor` workspace (idempotent — a second `start` reuses
it). corral keeps its own persistent **`corral`** session, separate from your
default herdr session: `herdr --session corral` starts it if needed and
attaches the existing one otherwise, so `start` always lands on the same
session and the monitor survives disconnects.

**Agents per worktree.** On a *fresh* session `start` also opens an agent
workspace (the same agent-left / two-terminals layout as `spawn`, using your
configured `CORRAL_AGENT`/`CORRAL_MODEL`) for every existing worktree under
`CORRAL_WORKTREES_DIR` — one command rebuilds your whole bench. When the
session is merely reconnected to, no agents are opened (they are already
running). `--no-agents` skips opening them even on a fresh start.

**Local** (no target) — corral session + monitor here, then
`herdr --session corral`.

**Remote** (`--remote <target>` or `CORRAL_REMOTE`, same syntax as
`herdr --remote`) — corral bootstraps the target over SSH first:

1. installs corral there if it's missing (the `install.sh` one-liner);
2. copies this machine's config across, with `CORRAL_REMOTE` stripped so the
   remote doesn't point at a further host;
3. starts the corral session + monitor on the remote (`corral start --no-attach`);
4. forwards the monitor port back so the dashboard is reachable at
   `http://localhost:<port>` locally — via `autossh` when it's installed, so the
   tunnel auto-reconnects across sleep/roaming (plain `ssh` with keepalives
   otherwise);
5. attaches with `herdr --remote <target> --session corral`.

Each step past the attach has a `--no-*` opt-out. `--no-attach` does the setup
for **this** machine and stops before attaching (it's also how corral seeds the
remote). `--dry-run` prints every command it would run — install, copy, seed,
forward, attach — without touching anything, which is the safe way to inspect
the remote path.

**Options**

| Option | Default | Meaning |
| --- | --- | --- |
| `-r`, `--remote` `<target>` | `` (local — this machine) | SSH target to attach to (same syntax as `herdr --remote`). |
| `--no-attach` | — | Set up this machine's server + monitor without attaching the herdr client. |
| `--no-monitor` | — | Skip starting `corral monitor`. |
| `--no-agents` | — | Don't open an agent workspace for each existing worktree when the corral session is started fresh. (Reconnecting to an already-running session never opens agents, with or without this flag.) |
| `--no-install` | — | Remote only: skip installing corral on the target. |
| `--no-config-copy` | — | Remote only: skip copying this machine's config to the target. |
| `--no-forward` | — | Remote only: skip the `ssh -L` monitor-port forward. |
| `--dry-run` | — | Print every command `start` would run (including the attach) without executing. |

```sh
corral start                             # local herdr + monitor + an agent per worktree, then attach
corral start --remote devbox             # bootstrap + attach devbox over SSH
corral start --no-agents                 # don't reopen agents for existing worktrees
corral start --no-attach                 # just bring up the server + monitor
corral start --remote devbox --dry-run   # show what it would do
```

## `corral end [options]`

Stop corral's persistent **`corral`** session — the teardown counterpart to
`corral start` — and release the shared resources its worktrees still hold.

Stopping the session kills every agent running in it, so `end` prompts first
unless `--force`. Before stopping, it returns any items still checked out by a
corral worktree (holder `ws:<repo>/<label>`, see `corral resource`) to their
pools — the same auto-release `corral close` does, but for the whole bench at
once — so no lease outlives the session. `--no-resources` leaves leases in
place.

The git worktrees under `CORRAL_WORKTREES_DIR` are left untouched; a later
`corral start` reopens them. To remove a worktree, use `corral close` /
`corral prune`.

**Options**

| Option | Default | Meaning |
| --- | --- | --- |
| `-f`, `--force` | — | Skip the confirmation prompt. |
| `--no-resources` | — | Don't release the shared resources corral worktrees still hold. |
| `--dry-run` | — | Print the resources it would release and the session it would stop, without doing it. |

```sh
corral end                  # release resources, then stop the corral session (prompts)
corral end --force          # no prompt
corral end --no-resources   # stop the session but keep leases
corral end --dry-run        # show what it would do
```

## `corral spawn <repo> [branch] [options]`

Create an isolated agent workspace in a fresh git worktree.

If the repo commits a `.corral/setup.sh`, spawn chains it before the agent in
the agent pane (`bash .corral/setup.sh && <agent>`): the agent only starts once
setup succeeds, and a failure stays visible in the pane. See
[per-repo configuration](configuration.md#per-repo-configuration-corral).

**Arguments**

| Arg | Meaning |
| --- | --- |
| `<repo>` | Any path inside the git repo to branch from (e.g. `~/dev/app` or `.`). corral resolves it to the repo root. |
| `[branch]` | Branch for the worktree. A new name is created; a branch that already exists — locally, or only on a remote (`origin/feature/x`, or just `feature/x`) — is checked out into the worktree instead (handy for an open PR), and a remote branch gets a local tracking branch of the same name. spawn fetches first, so a freshly pushed branch resolves by bare name without the `origin/` prefix. The worktree and its workspace label are named after the branch. Default: with `--prompt`, `<prefix>/<name>` where `<name>` is generated from the prompt by the `claude` CLI (falling back to slugged prompt text, with a numeric suffix if the branch already exists); otherwise `<prefix>/<repo>-<timestamp>`. |

**Options**

| Option | Default | Meaning |
| --- | --- | --- |
| `-a`, `--agent` `<name>` | `claude` | Agent to launch in the left pane, or `none` for a blank shell. Any herdr-integrated agent works (`claude`, `codex`, `copilot`, `droid`, `opencode`, `cursor`, …). |
| `-m`, `--model` `<name>` | `` (Claude's default) | Model for the Claude agent. Applies to the `claude` agent only; ignored (with a warning) for others. |
| `-P`, `--permission-mode` `<mode>` | `` (Claude's default) | Claude permission/edit mode, e.g. `acceptEdits`, `plan`. `claude` agent only. |
| `-p`, `--prompt` `<text>` | (none) | Initial prompt handed to the agent on launch, as its first positional argument. Ignored (with a warning) for `--agent none`. When `[branch]` is omitted, the branch is named after the prompt too. |
| `-b`, `--base` `<ref>` | `` (HEAD) | Base ref a new branch is created from. Ignored when `[branch]` names a branch that already exists (local or remote). |
| `-r`, `--ratio` `<0..1>` | `0.4` | Agent (left) pane share of the width. |
| `-l`, `--label` `<text>` | derived from the branch name | herdr workspace label. |
| `--no-focus` | — | Create the workspace without switching to it. |
| `--no-setup` | — | Skip the repo's committed `.corral/setup.sh` (also: `CORRAL_SETUP=0`). |

```sh
corral spawn ~/dev/app
corral spawn ~/dev/app feature/checkout
corral spawn ~/dev/app origin/feature/checkout                      # check out an existing (PR) branch
corral spawn . bugfix/tax --base main --agent codex --ratio 0.55
corral spawn ~/dev/app --model opus --permission-mode acceptEdits
corral spawn ~/dev/app --prompt "fix the failing tax tests"         # branch: e.g. agent/fix-failing-tax-tests
corral spawn ~/dev/app --agent none                                 # just the worktree + terminals
```

## `corral ls [options]`

List active agent workspaces (corral-owned worktrees only — your primary
checkouts and hand-made worktrees are never listed). Columns: workspace id,
label, git branch, agent status, worktree path. Data rows go to stdout and the
header to stderr, so plain `corral ls` pipes cleanly; `--json` emits an array
and `--tsv` tab-separated rows for scripting (the oh-my-zsh plugin is built on
`--tsv`).

Alias: `corral list`.

**Options**

| Option | Default | Meaning |
| --- | --- | --- |
| `-j`, `--json` | — | Emit a JSON array instead of a table. |
| `--tsv` | — | Emit one tab-separated row per workspace — the format the oh-my-zsh plugin consumes. Columns: workspace, label, repo, branch, status, worktree. |

```sh
corral ls
corral ls | awk '{print $1}'
corral ls --json | python3 -c 'import json,sys; print(len(json.load(sys.stdin)))'
```

## `corral focus <workspace>`

Switch focus to an agent workspace by id (`w4`) or label (`checkout-fix`).

Alias: `corral attach`.

**Arguments**

| Arg | Meaning |
| --- | --- |
| `<workspace>` | Workspace id (`w4`) or label (`checkout-fix`). |

```sh
corral focus checkout-fix
```

## `corral open [workspace] [options]`

Open your IDE in an agent workspace's worktree. With no argument, opens the
worktree of the workspace you're currently in.

corral asks herdr for the workspace's worktree checkout path (it never guesses
from the label), so the IDE always opens the exact folder the agent is working
in. Any worktree-backed workspace can be opened, not just corral-created ones.

**Local herdr session** — the IDE runs on the same machine — corral launches it
directly (`code <worktree>` / `cursor <worktree>`, falling back to
`open -a` on macOS when the shell command isn't installed).

**Remote herdr session** (`herdr --remote`) — corral runs on the server but
your IDE runs on your local machine, so it can't be launched from the server.
corral detects this (an SSH environment or an attached `herdr --remote` client
bridge) and instead prints a `vscode://vscode-remote/ssh-remote+<host><path>`
deep link — clickable in most terminals — plus the equivalent
`code --remote ssh-remote+<host> <path>` command to run locally. Both open the
worktree over the IDE's Remote-SSH support. The `<host>` must be how **your**
machine reaches the server (a `Host` entry in your local `~/.ssh/config`); when
the server's hostname isn't that, set `CORRAL_SSH_HOST` or pass `--host`.
Use `--ssh`/`--no-ssh` when the auto-detection guesses wrong.

Alias: `corral ide`.

**Arguments**

| Arg | Meaning |
| --- | --- |
| `[workspace]` | Workspace id (`w4`) or label (`checkout-fix`). Defaults to the workspace you're currently in. |

**Options**

| Option | Default | Meaning |
| --- | --- | --- |
| `-i`, `--ide` `<name>` | `vscode` | IDE to open: `vscode` or `cursor` (config: `CORRAL_IDE`). |
| `--ssh` | auto | Force Remote-SSH mode. |
| `--no-ssh` | auto | Force local mode. |
| `--host` `<host>` | `` (this machine's hostname) | SSH host used in the Remote-SSH link (config: `CORRAL_SSH_HOST`). |

```sh
corral open                    # open the worktree you're in
corral open checkout-fix       # open by label
corral open w4 --ide cursor
corral open w4 --host devbox   # remote link via ssh host alias "devbox"
```

## `corral close [workspace] [options]`

Remove an agent's git worktree and close its workspace. With no argument,
closes the workspace you're currently in. Prompts unless `--force`.

corral refuses to close anything that isn't a corral-created worktree (a linked
worktree under `~/.herdr/worktrees/…`), so it can't destroy your command
workspace, a primary repo checkout, or a worktree you made by hand.

If the worktree contains a `.corral/cleanup.sh`, corral runs it there before
removing it. If cleanup fails, close aborts and leaves the worktree intact;
`--force` removes it anyway (re-running the script) and `--no-cleanup` skips
the script entirely. See
[per-repo configuration](configuration.md#per-repo-configuration-corral).

**Arguments**

| Arg | Meaning |
| --- | --- |
| `[workspace]` | Workspace id (`w4`) or label (`checkout-fix`). Defaults to the workspace you're currently in. |

**Options**

| Option | Default | Meaning |
| --- | --- | --- |
| `-f`, `--force` | — | Skip the confirmation prompt, and close even if the worktree's `.corral/cleanup.sh` fails (the script still runs). |
| `--no-cleanup` | — | Do not run `.corral/cleanup.sh` (also: `CORRAL_CLEANUP=0`). |

```sh
corral close                # close the workspace you're in (prompts)
corral close checkout-fix   # close by label
corral close w4 --force
```

## `corral prune [options]`

Remove agent workspaces whose work is done. A workspace is prunable **only**
when it is safe to delete:

- its worktree has **no uncommitted changes**, and
- its branch is **fully merged** into the base branch.

This guarantees prune never discards unmerged or uncommitted work.

If a workspace's worktree contains a `.corral/cleanup.sh`, corral runs it there
before removing the worktree; a workspace whose cleanup fails is skipped
(worktree kept) unless `--force` is given.

Alias: `corral clean`.

**Options**

| Option | Default | Meaning |
| --- | --- | --- |
| `-b`, `--base` `<ref>` | the repo's origin/HEAD, else main, else master; if none of those exist the merged check is skipped entirely | Branch to test "merged into" (default: `origin/HEAD`, else `main`, else `master`; if none exist the merged check is skipped rather than guessed). |
| `-i`, `--idle` | — | Also prune workspaces with a clean tree whose agent is idle, even if the branch isn't merged. |
| `-n`, `--dry-run` | — | Show what would be pruned; remove nothing. |
| `-f`, `--force` | — | Skip the per-workspace confirmation, and prune even if a workspace's `.corral/cleanup.sh` fails. |
| `--no-cleanup` | — | Do not run `.corral/cleanup.sh` before removing worktrees. |

```sh
corral prune --dry-run
corral prune --base main --force
```

## `corral resource <action> [target] [items…] [options]`

Check shared resources in and out of named pools — dev-server ports, Shopify
dev-app credentials, anything scarce that concurrent agent workspaces must not
grab twice. State lives in one machine-wide SQLite database
(`CORRAL_RESOURCES_DB`); every checkout is a single database transaction, so
two agents can never acquire the same item.

| Action | Meaning |
| --- | --- |
| `acquire` | check out one free item from a pool |
| `release` | return checked-out items to their pool |
| `add` | create a pool or add items to one |
| `rm` | remove a pool or a single item |
| `ls` | list pools, items, and holders |
| `sync` | sync this repo's .corral/resources.json into the database |

`acquire` prints the item name on stdout (`PORT=$(corral resource acquire
ports)`); `--json` adds the item's attached data payload (for example Shopify
app credentials). When the pool is exhausted it fails and lists the holders;
`--wait` polls until an item frees up instead.

**Holders.** Run inside a corral worktree, acquire records the workspace
(`ws:<repo>/<label>`) as the holder — so a `.corral/setup.sh` can reserve
resources at spawn time — and `corral close`/`corral prune` automatically
release everything that workspace still holds. Outside a worktree the holder
is `user@host:<cwd>`; `--as` overrides it either way.

**Per-repo pools.** A repo can commit a `.corral/resources.json` declaring
pools; corral syncs it into the database on `acquire`/`ls`/`sync`:

```json
{
  "shopify-dev-apps": [
    {"name": "dev-app-1", "data": {"api_key": "…", "url": "…"}},
    {"name": "dev-app-2", "data": {"api_key": "…"}}
  ],
  "ports": {"range": [3000, 3009]}
}
```

The file is declarative for the pools it names: new items are added, changed
`data` is updated in place (leases untouched), and items dropped from the file
are deleted when free — or retired when currently held, so they are never
handed out again and disappear once released. Items added to the same pool via
the CLI are left alone. See
[per-repo configuration](configuration.md#per-repo-configuration-corral).

Alias: `corral res`.

**Arguments**

| Arg | Meaning |
| --- | --- |
| `<action>` | One of: acquire, release, add, rm, ls, sync |
| `[target]` | Pool name, or `<pool>/<item>` for `release` and `rm`. |
| `[items…]` | Items to add (`add` only); `N-M` expands to an inclusive port range. |

**Options**

| Option | Default | Meaning |
| --- | --- | --- |
| `-j`, `--json` | — | Emit machine-readable JSON, including item `data` (`acquire`, `ls`). |
| `--tsv` | — | Emit one tab-separated row per item (`ls`). Columns: pool, name, state, holder, acquired_at — the format the zsh completion consumes. |
| `--as` `<holder>` | (none) | Act as this holder tag (default: the enclosing corral workspace as `ws:<repo>/<label>`, else `user@host:<cwd>`). |
| `-w`, `--wait` `<seconds>` | (none) | `acquire` only: poll every 2s until an item frees up instead of failing. Bare `--wait` waits forever; `--wait=30` gives up after 30 seconds. |
| `--data` `<json>` | (none) | `add` only: a JSON payload attached to each added item, returned by `acquire --json` and `ls --json`. |
| `--all` | — | `release` only: return everything the holder has checked out. |
| `--mine` | — | `ls` only: only items checked out by this workspace/holder. |
| `-f`, `--force` | — | Release an item held by someone else; `rm` a pool with held items. |

```sh
corral resource add ports 3000-3009
corral resource acquire ports                               # prints e.g. 3001
corral resource acquire shopify-dev-apps --json --wait=60
corral resource release ports/3001
corral resource release --all                               # return everything this workspace holds
corral resource ls --mine
```

## `corral monitor [options]`

Serve a local web dashboard for the agent fleet. It lists every corral-owned
workspace joined to the resources it currently holds, plus every resource pool,
and refreshes itself as things change. Buttons on the page spawn, focus, and
close agents and release held resource items — each routed through the same
command the CLI runs, so the web UI and the terminal share one implementation.

The server is stdlib-only (no extra install) and binds to `127.0.0.1` by
default — reachable only from this machine. Set `--host 0.0.0.0` (or
`CORRAL_MONITOR_HOST`) to expose it on your network. Runs until interrupted
with Ctrl-C.

Alias: `corral ui`.

**Options**

| Option | Default | Meaning |
| --- | --- | --- |
| `-p`, `--port` `<port>` | `8477` | TCP port to serve the web UI on. |
| `--host` `<addr>` | `127.0.0.1` | Address to bind to (`127.0.0.1` = local only; `0.0.0.0` = exposed). |

```sh
corral monitor                  # http://127.0.0.1:8477
corral monitor --port 9000
corral monitor --host 0.0.0.0   # reachable on your network
```

## `corral doctor [options]`

Check that corral is healthy and up to date:

1. **Dependencies** — verifies `herdr` and `git` are on `PATH` (each is
   reported individually, with its version and location).
2. **Environment** — reports the Python in use, whether the herdr server is
   reachable, and whether a config file exists. Informational only; never
   fails the doctor.
3. **Update** — fast-forwards the corral installation to the latest `main`
   from its origin remote and reports the new version.

The update step refuses to touch anything that isn't a clean checkout on
`main` — a dev checkout on a feature branch, with local changes, or with a
diverged history is left alone with a note. A non-git install (no `.git`) gets
a pointer to the `install.sh` one-liner instead.

Exits `0` when every required dependency is present and the update succeeded
(or was safely skipped), `1` otherwise.

**Options**

| Option | Default | Meaning |
| --- | --- | --- |
| `--no-update` | — | Run the checks only; never touch the installation. |

```sh
corral doctor
corral doctor --no-update
```

## Exit codes

`0` success · `1` usage error or a failed herdr/git operation (the message
explains which).
