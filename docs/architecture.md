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

herdr pane run <root> <agent>                            # launch the agent

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
├── bin/corral        # arg dispatch; resolves lib/ via symlink-aware path
└── lib/
    ├── common.sh     # logging, dep checks, config load, herdr/JSON helpers, guards
    ├── spawn.sh      # cmd_spawn
    ├── close.sh      # cmd_close
    ├── ls.sh         # cmd_ls
    ├── focus.sh      # cmd_focus
    └── prune.sh      # cmd_prune

packages/omz-plugin/  # zsh layer over the CLI: completion driven by
                      # `corral ls --json`, aliases, ccd, prompt segment
```

Helpers worth knowing in `common.sh`:

- `herdr_do …` — runs a herdr command and dies on either a non-zero exit or an
  `{"error": …}` response (herdr reports API errors with a zero exit code).
  herdr's stderr passes straight through to the user; only stdout is captured.
- `json_get <blob> <jq-path>` — extract a field or die if missing.
- `worktree_path_from_info` / `agent_workspace_rows` — apply the ownership test
  (linked worktree under `CORRAL_WORKTREES_DIR`); the basis of the safety
  guards. `agent_workspace_rows` builds the whole listing from a single
  `workspace list` call.
- `resolve_workspace <id-or-label> <list-blob>` — resolve from an
  already-fetched workspace list (returns 1 for no match, 2 for an ambiguous
  label) so herdr failures surface in the caller, not a swallowed subshell.
- `confirm <prompt>` — yes/no prompt that reads from `/dev/tty`, so piped stdin
  can never auto-confirm a destructive action.
