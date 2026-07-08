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
| `--base <ref>` | current HEAD | Base ref the new worktree branches from. |
| `--ratio <0..1>` | `0.6` | Agent (left) pane share of the width. |
| `--label <text>` | branch basename | herdr workspace label. |
| `--no-focus` | (focus) | Create the workspace without switching to it. |

**Examples**

```sh
corral spawn ~/dev/app
corral spawn ~/dev/app feature/checkout
corral spawn . bugfix/tax --base main --agent codex --ratio 0.55
corral spawn ~/dev/app --agent none        # just the worktree + terminals
```

## `corral ls [--json]`

List active agent workspaces (linked worktrees only — your primary checkouts are
never listed). Columns: workspace id, label, git branch, agent status, worktree
path. `--json` emits an array for scripting.

```sh
corral ls
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

corral refuses to close anything that isn't a linked (corral-created) worktree,
so it can't destroy your command workspace or a primary repo checkout.

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
| `--base <ref>` | Branch to test "merged into" (default: `origin/HEAD`, else `main`, else `master`). |
| `--idle` | Also prune workspaces with a clean tree whose agent is idle, even if the branch isn't merged. |
| `-n`, `--dry-run` | Show what would be pruned; remove nothing. |
| `-f`, `--force` | Skip the per-workspace confirmation. |

```sh
corral prune --dry-run
corral prune --base main --force
```

## Exit codes

`0` success · `1` usage error or a failed herdr/git operation (the message
explains which).
