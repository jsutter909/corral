<!--
  GENERATED FILE — do not edit by hand.
  Source of truth: packages/cli/src/corral/commands/*.py (each command's SPEC)
  Regenerate with: python -m corral.generate (or: make generate)
-->

# corral — command reference

Every command also prints this via `corral <command> --help`.

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
| `[branch]` | Branch name for the worktree. Default: with `--prompt`, `<prefix>/<name>` where `<name>` is generated from the prompt by the `claude` CLI (falling back to slugged prompt text, with a numeric suffix if the branch already exists); otherwise `<prefix>/<repo>-<timestamp>`. |

**Options**

| Option | Default | Meaning |
| --- | --- | --- |
| `-a`, `--agent` `<name>` | `claude` | Agent to launch in the left pane, or `none` for a blank shell. Any herdr-integrated agent works (`claude`, `codex`, `copilot`, `droid`, `opencode`, `cursor`, …). |
| `-m`, `--model` `<name>` | `` (Claude's default) | Model for the Claude agent. Applies to the `claude` agent only; ignored (with a warning) for others. |
| `-P`, `--permission-mode` `<mode>` | `` (Claude's default) | Claude permission/edit mode, e.g. `acceptEdits`, `plan`. `claude` agent only. |
| `-p`, `--prompt` `<text>` | (none) | Initial prompt handed to the agent on launch, as its first positional argument. Ignored (with a warning) for `--agent none`. When `[branch]` is omitted, the branch is named after the prompt too. |
| `-b`, `--base` `<ref>` | `` (HEAD) | Base ref the new worktree branches from. |
| `-r`, `--ratio` `<0..1>` | `0.4` | Agent (left) pane share of the width. |
| `-l`, `--label` `<text>` | derived from the branch name | herdr workspace label. |
| `--no-focus` | — | Create the workspace without switching to it. |
| `--no-setup` | — | Skip the repo's committed `.corral/setup.sh` (also: `CORRAL_SETUP=0`). |

```sh
corral spawn ~/dev/app
corral spawn ~/dev/app feature/checkout
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
