# Contributing to corral

Thanks for helping out! corral is a small, dependency-free Python CLI — easy
to hack on (Python 3.9+, stdlib only).

## Setup

```sh
git clone https://github.com/jsutter909/corral.git
cd corral
make link     # symlink the working tree's `corral` onto your PATH
```

Now edits to `packages/cli/**` take effect immediately (the symlink points at
your checkout; `bin/corral` runs the package straight from `src/`).

## The golden rule: specs are the source of truth

Commands, flags, settings, agents, and IDEs are declared once, in the
registries under `packages/cli/src/corral/` (`commands/*.py`, `settings.py`,
`agents.py`, `ides.py`). The docs (`docs/usage.md`, `docs/configuration.md`),
the example config, and the whole oh-my-zsh plugin are **generated** from
them:

```sh
make generate   # after changing any spec or registry
```

Never edit a file with a `GENERATED FILE` banner by hand — CI runs
`make check-generated` and fails when artifacts drift.

## Before you push

```sh
make check    # lint + generated-artifact freshness + tests
```

- **Tests:** `packages/cli/tests/` runs without a herdr server
  (`python3 -m unittest discover -s tests -t .` from `packages/cli`). The zsh
  completion tests drive a real interactive zsh in a pty. If you add a
  command or flag, the CLI-surface and completion tests usually need one new
  expectation each.
- **Lint:** [`shellcheck`](https://www.shellcheck.net/) covers `install.sh`;
  `zsh -n` covers the generated plugin; the Python package is byte-compiled.

## Conventions

- One subcommand per module in `packages/cli/src/corral/commands/`, exposing a
  `SPEC` (declarative `Command`) and `run(ctx, args)`. Register it in
  `commands/__init__.py` — the dispatcher, help, docs, and completion follow.
- Always go through `Herdr.call` (or its typed wrappers) for herdr calls — it
  turns API errors into clear failures.
- Preserve the safety guards: destructive actions must go through
  `Workspace.is_corral_owned` and `hooks.remove_workspace`, and must operate
  on **linked** worktrees only, never a primary checkout.
- Keep messages on stderr so stdout stays pipeable.

## Commits & PRs

- Small, focused commits with imperative subject lines ("add prune --idle").
- Describe user-facing changes in the PR body; `docs/` regenerates via
  `make generate` when specs change — commit the result.
