# Contributing to corral

Thanks for helping out! corral is small and Bash-only — easy to hack on.

## Setup

```sh
git clone https://github.com/jsutter909/corral.git
cd corral
make link     # symlink the working tree's `corral` onto your PATH
```

Now edits to `packages/cli/**` take effect immediately (the symlink points at
your checkout).

## Before you push

```sh
make check    # runs shellcheck (if installed) + smoke tests
```

- **Lint:** install [`shellcheck`](https://www.shellcheck.net/)
  (`brew install shellcheck` / `apt install shellcheck`). CI runs it.
- **Tests:** `packages/cli/test/smoke.sh` exercises the CLI surface without a
  herdr server. If you add a command, add a `--help` smoke check for it.

## Conventions

- One subcommand per file in `packages/cli/lib/`, exposing `cmd_<name>` and a
  `<name>_usage` function. Wire it into `bin/corral`'s dispatcher.
- Put anything reusable (herdr calls, JSON parsing, guards) in `common.sh`.
- Always go through `herdr_do` for herdr calls — it turns API errors into clear
  failures.
- Preserve the safety guards: destructive actions must operate on **linked**
  worktrees only, never a primary checkout.
- 2-space indent, `set -euo pipefail` in the entry point, keep messages on stderr
  so stdout stays pipeable.

## Commits & PRs

- Small, focused commits with imperative subject lines ("add prune --idle").
- Describe user-facing changes in the PR body; update `docs/` when behavior
  changes.
