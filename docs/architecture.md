# corral — architecture

corral is a thin orchestration layer over [herdr](https://herdr.dev)'s socket
API. It stores no state of its own: herdr is the source of truth for workspaces,
panes, and worktrees, and git is the source of truth for branches. Every corral
command is a short sequence of `herdr` calls plus a little git.

## herdr concepts corral relies on

| herdr concept | Role in corral |
| --- | --- |
| **workspace** | One isolated agent = one workspace. herdr creates a new workspace per worktree. |
| **tab / pane** | The three-pane layout lives in the workspace's first tab. |
| **worktree** | `herdr worktree create` makes a linked git worktree *and* a workspace in a single call. |
| **agent** | herdr detects the agent running in a pane and tracks its status (idle/working/blocked). |

## What `spawn` actually does

```
herdr worktree create --cwd <repo> --branch <b> --label <l> --no-focus
    └─ creates git worktree under ~/.herdr/worktrees/<repo>/<b>
       and a new workspace with one root pane (cwd = worktree)

herdr pane split <root>  --direction right --ratio <r>   # agent | right column
herdr pane split <right> --direction down  --ratio 0.5   # right column -> 2 stacked

herdr pane run <root> "bash .corral/setup.sh && <agent>" # setup (if committed) then agent

herdr workspace focus <workspace>                        # jump to it
```

`--ratio` is the **left** (agent) pane's share of the width, so the default
`0.4` gives the agent 40% and the two terminals 60%.

## The isolation guarantee

Each spawn produces a **linked** git worktree (`is_linked_worktree: true`)
checked out by herdr under `~/.herdr/worktrees/` on its own branch. Corral keys
ownership on **both** properties — linkedness *and* the path prefix
(`CORRAL_WORKTREES_DIR`):

- `ls` shows only corral-owned worktrees.
- `close` and `prune` refuse anything else — your primary repo checkout
  (`is_linked_worktree: false`) and any linked worktree you made by hand
  (outside `~/.herdr/worktrees/`) can never be removed.
- `prune` additionally requires a clean tree and a merged branch before
  deleting; if no base branch can be resolved, the merged check is skipped
  entirely rather than guessed.

## Code map

```
packages/cli/
├── bin/corral               # launcher: symlink-aware, puts src/ on sys.path
└── src/corral/
    ├── app.py               # dispatch, root help, error handling
    ├── cli.py               # Command/Option/Argument spec model + parser + help
    ├── settings.py          # the settings registry + config loading
    ├── herdr.py             # typed client for the herdr socket API
    ├── workspaces.py        # Workspace/Worktree model + the ownership invariant
    ├── agents.py            # agent registry + launch-command construction
    ├── ides.py              # IDE registry + Remote-SSH deep links
    ├── hooks.py             # setup/cleanup hooks; remove_workspace choke point
    ├── naming.py            # branch slugs + prompt-derived branch names
    ├── gitutil.py           # every git call, in one place
    ├── commands/            # one module per subcommand: SPEC + run()
    └── generate/            # renders docs, config example, and the omz plugin

packages/omz-plugin/         # GENERATED zsh layer over the CLI: completion and
                             # ccd/prompt driven by `corral ls --tsv`
```

### The single-source-of-truth registries

Everything user-visible is declared once and rendered everywhere:

- **Command specs** (`commands/*.py`, model in `cli.py`) — each command's
  arguments, options, prose, and examples drive the argument parser,
  `corral <cmd> --help`, `docs/usage.md`, and the `_corral` zsh completion.
- **Settings** (`settings.py`) — each `Setting` declares its env var, default,
  linked flag, and docs; the loader, the settings table in
  `docs/configuration.md`, and `share/config.example.sh` are all derived.
- **Agents / IDEs** (`agents.py`, `ides.py`) — feed spawn/open behavior, docs,
  and completion candidates.

`python -m corral.generate` (via `make generate`) writes the artifacts;
`--check` (in CI and `make check`) fails when they drift.

Runtime pieces worth knowing:

- `Herdr.call(…)` — runs a herdr command and raises on either a non-zero exit
  or an `{"error": …}` response (herdr reports API errors with a zero exit
  code). herdr's stderr passes straight through to the user; only stdout is
  captured.
- `Workspace.is_corral_owned(…)` — the ownership test (linked worktree under
  `CORRAL_WORKTREES_DIR`); the basis of the safety guards in `ls`, `close`,
  and `prune`.
- `hooks.remove_workspace(…)` — the one choke point that destroys a
  workspace, so no removal path can skip the cleanup-before-remove invariant.
- `resolve_workspace(ref, workspaces)` — id-first, then unique label;
  ambiguity is an error, never a guess.
- `ui.confirm(prompt)` — yes/no prompt that reads from `/dev/tty`, so piped
  stdin can never auto-confirm a destructive action.
