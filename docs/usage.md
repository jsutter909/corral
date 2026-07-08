# corral — command reference

Every command also prints this via `corral <command> --help`.

## `corral spawn <repo> [branch] [options]`

Create an isolated agent workspace in a fresh git worktree.

**Arguments**

| Arg | Meaning |
| --- | --- |
| `<repo>` | Any path inside the git repo to branch from (e.g. `~/dev/app` or `.`). corral resolves it to the repo root. |
| `[branch]` | Branch name for the worktree. Default: with `--prompt`, `<prefix>/<name>` where `<name>` is generated from the prompt by the `claude` CLI (falling back to slugged prompt text, with a numeric suffix if the branch already exists); otherwise `<prefix>/<repo>-<timestamp>`. |

**Options**

| Option | Default | Meaning |
| --- | --- | --- |
| `-a, --agent <name>` | `claude` | Agent to launch in the left pane, or `none` for a blank shell. Any herdr-integrated agent works (`claude`, `codex`, `copilot`, `droid`, `opencode`, `cursor`, …). |
| `-m, --model <name>` | Claude's default | Model for the Claude agent. Applies to the `claude` agent only; ignored (with a warning) for others. |
| `-P, --permission-mode <mode>` | Claude's default | Claude permission/edit mode, e.g. `acceptEdits`, `plan`. `claude` agent only. |
| `-p, --prompt <text>` | (none) | Initial prompt handed to the agent on launch, as its first positional argument. Ignored (with a warning) for `--agent none`. When `[branch]` is omitted, the branch is named after the prompt too. |
| `-b, --base <ref>` | current HEAD | Base ref the new worktree branches from. |
| `-r, --ratio <0..1>` | `0.4` | Agent (left) pane share of the width. |
| `-l, --label <text>` | branch basename | herdr workspace label. |
| `--no-focus` | (focus) | Create the workspace without switching to it. |
| `--no-setup` | (run if present) | Skip the repo's committed `.corral/setup.sh`. |
| `-j, --json` | (off) | Emit a machine-readable spawn result on stdout: workspace id, label, repo, branch, worktree path, pane ids, and whether a setup script gates the agent. The human summary still goes to stderr. |

If the repo commits a `.corral/setup.sh`, spawn chains it before the agent in
the agent pane (`bash .corral/setup.sh && <agent>`): the agent only starts once
setup succeeds, and a failure stays visible in the pane. See
[per-repo configuration](configuration.md#per-repo-configuration-corral).

**Examples**

```sh
corral spawn ~/dev/app
corral spawn ~/dev/app feature/checkout
corral spawn . bugfix/tax --base main --agent codex --ratio 0.55
corral spawn ~/dev/app --model opus --permission-mode acceptEdits
corral spawn ~/dev/app --prompt "fix the failing tax tests"   # branch: e.g. agent/fix-failing-tax-tests
corral spawn ~/dev/app --agent none        # just the worktree + terminals
corral spawn ~/dev/app --prompt "fix issue #42" --no-focus --json
```

## `corral ls [-j|--json]`

List active agent workspaces (corral-owned worktrees only — your primary
checkouts and hand-made worktrees are never listed). Columns: workspace id,
label, git branch, agent status, worktree path. Data rows go to stdout and the
header to stderr, so plain `corral ls` pipes cleanly; `-j`/`--json` emits an
array for scripting.

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

## `corral send <workspace> [--] <text...>`

Send a prompt (or any text) to the agent running in a workspace. The text is
typed into the workspace's agent pane and submitted with Enter.

| Option | Meaning |
| --- | --- |
| `--no-enter` | Type the text without submitting it. |
| `-p, --pane <id>` | Send to a specific pane instead of the workspace's agent pane. |

Use `--` before text that starts with a dash.

```sh
corral send w4 "run the tests and fix any failures"
corral send checkout-fix --no-enter "draft, not submitted"
```

## `corral read <workspace> [options]`

Print the recent output of a workspace's agent pane to stdout (plain text by
default, so it pipes cleanly).

| Option | Meaning |
| --- | --- |
| `-n, --lines <n>` | Number of lines to capture (default: the visible screen). |
| `-s, --source <src>` | `visible`, `recent` (includes scrollback), or `recent-unwrapped`. |
| `--ansi` | Keep ANSI colors/styles. |
| `-p, --pane <id>` | Read a specific pane instead of the workspace's agent pane. |

```sh
corral read w4 --lines 200 --source recent | tail -40
```

## `corral wait <workspace> [options]`

Block until a workspace's agent reaches a status (default: `idle`), or until
its output matches text. Exits `0` when the condition is met, non-zero on
timeout — so it chains cleanly in scripts.

| Option | Meaning |
| --- | --- |
| `-s, --status <s>` | `idle`, `working`, `blocked`, `done`, or `unknown` (default `idle`). |
| `-m, --match <text>` | Wait for output matching `<text>` instead of a status. |
| `--regex` | Treat `--match` as a regular expression. |
| `-t, --timeout <ms>` | Give up after this many milliseconds (default `300000`). |
| `-p, --pane <id>` | Watch a specific pane instead of the workspace's agent pane. |

A status wait returns as soon as the agent is *currently* in that status —
right after `corral send`, the agent can still be `idle` for a beat. When that
matters, wait for `working` first (short timeout), then `idle`:

```sh
corral send w4 "fix the failing test"
corral wait w4 --status working --timeout 15000
corral wait w4 --status idle --timeout 600000
corral read w4 --lines 100
```

## `corral mcp`

Run corral as an [MCP](https://modelcontextprotocol.io) server over stdio, so
an orchestrator agent (e.g. a Claude Code session) can spawn, prompt, watch,
and tear down corral agents as first-class tools: `corral_spawn`,
`corral_list`, `corral_send`, `corral_read`, `corral_wait`, `corral_close`.

```sh
claude mcp add corral -- corral mcp
```

See [`docs/orchestration.md`](orchestration.md) for the full orchestrator
workflow.

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
| `-b`, `--base <ref>` | Branch to test "merged into" (default: `origin/HEAD`, else `main`, else `master`; if none exist the merged check is skipped rather than guessed). |
| `-i`, `--idle` | Also prune workspaces with a clean tree whose agent is idle, even if the branch isn't merged. |
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
