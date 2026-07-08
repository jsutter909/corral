# corral — command reference

Every command also prints this via `corral <command> --help`.

## `corral spawn <repo> [branch] [options]`

Create an isolated agent workspace in a fresh git worktree.

**Arguments**

| Arg | Meaning |
| --- | --- |
| `<repo>` | Any path inside the git repo to branch from (e.g. `~/dev/app` or `.`). corral resolves it to the repo root. |
| `[branch]` | Branch name for the worktree. Default: `<prefix>/<repo>-<timestamp>`. |

**Options**

| Option | Default | Meaning |
| --- | --- | --- |
| `--agent <name>` | `claude` | Agent to launch in the left pane, or `none` for a blank shell. Any herdr-integrated agent works (`claude`, `codex`, `copilot`, `droid`, `opencode`, `cursor`, …). |
| `--model <name>` | Claude's default | Model for the Claude agent. Applies to the `claude` agent only; ignored (with a warning) for others. |
| `--permission-mode <mode>` | Claude's default | Claude permission/edit mode, e.g. `acceptEdits`, `plan`. `claude` agent only. |
| `--base <ref>` | current HEAD | Base ref the new worktree branches from. |
| `--ratio <0..1>` | `0.4` | Agent (left) pane share of the width. |
| `--label <text>` | branch basename | herdr workspace label. |
| `--no-focus` | (focus) | Create the workspace without switching to it. |

**Examples**

```sh
corral spawn ~/dev/app
corral spawn ~/dev/app feature/checkout
corral spawn . bugfix/tax --base main --agent codex --ratio 0.55
corral spawn ~/dev/app --model opus --permission-mode acceptEdits
corral spawn ~/dev/app --agent none        # just the worktree + terminals
```

## `corral ls [--json]`

List active agent workspaces (corral-owned worktrees only — your primary
checkouts and hand-made worktrees are never listed). Columns: workspace id,
label, git branch, agent status, worktree path. Data rows go to stdout and the
header to stderr, so plain `corral ls` pipes cleanly; `--json` emits an array
for scripting.

```sh
corral ls
corral ls | awk '{print $1}'
corral ls --json | jq -r '.[].branch'
```

## `corral focus <workspace>`

Switch focus to an agent workspace by id (`w4`) or label (`checkout-fix`).
Alias: `corral attach`.

```sh
corral focus checkout-fix
```

## `corral close [workspace] [--force]`

Remove an agent's git worktree and close its workspace. With no argument, closes
the workspace you're currently in. Prompts unless `--force`.

corral refuses to close anything that isn't a corral-created worktree (a linked
worktree under `~/.herdr/worktrees/…`), so it can't destroy your command
workspace, a primary repo checkout, or a worktree you made by hand.

```sh
corral close                 # the workspace you're in
corral close checkout-fix    # by label
corral close w4 --force
```

## `corral prune [options]`

Remove agent workspaces whose work is done. A workspace is prunable **only** when
it is safe to delete:

- its worktree has **no uncommitted changes**, and
- its branch is **fully merged** into the base branch.

This guarantees prune never discards unmerged or uncommitted work.

| Option | Meaning |
| --- | --- |
| `--base <ref>` | Branch to test "merged into" (default: `origin/HEAD`, else `main`, else `master`; if none exist the merged check is skipped rather than guessed). |
| `--idle` | Also prune workspaces with a clean tree whose agent is idle, even if the branch isn't merged. |
| `-n`, `--dry-run` | Show what would be pruned; remove nothing. |
| `-f`, `--force` | Skip the per-workspace confirmation. |

```sh
corral prune --dry-run
corral prune --base main --force
```

## `corral doctor [--no-update]`

Check that corral is healthy and up to date:

1. **Dependencies** — verifies `herdr`, `jq`, and `git` are on `PATH` (each is
   reported individually, with its version and location).
2. **Environment** — reports whether the herdr server is reachable and whether
   a config file exists. Informational only; never fails the doctor.
3. **Update** — fast-forwards the corral installation to the latest `main`
   from its origin remote and reports the new version.

The update step refuses to touch anything that isn't a clean checkout on
`main` — a dev checkout on a feature branch, with local changes, or with a
diverged history is left alone with a note. A non-git install (no `.git`) gets
a pointer to the `install.sh` one-liner instead.

| Option | Meaning |
| --- | --- |
| `--no-update` | Run the checks only; never touch the installation. |

Exits `0` when every required dependency is present and the update succeeded
(or was safely skipped), `1` otherwise.

```sh
corral doctor
corral doctor --no-update
```

## Exit codes

`0` success · `1` usage error or a failed herdr/git operation (the message
explains which).
