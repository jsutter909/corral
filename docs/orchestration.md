# Orchestrating corral agents

corral agents are ordinary interactive sessions (Claude Code by default), each
in its own worktree and herdr workspace. As of `corral send`/`read`/`wait` and
`corral mcp`, they are also **drivable by a parent orchestrator agent**: one
Claude Code session that farms work out to corral agents, watches them, and
collects the results — while you can still pop into any worker's pane and take
over by hand at any time.

Two ways to wire it up, same underlying commands:

| Layer | Best for |
| --- | --- |
| **CLI** (`corral spawn/send/wait/read/close`) | shell scripts, cron, CI, or an agent that already has a shell tool |
| **MCP** (`corral mcp`) | giving an orchestrator agent first-class, schema-described tools |

## The control loop

Everything reduces to five verbs:

```sh
# 1. Spawn a worker on its own branch, already working on a task.
out="$(corral spawn ~/dev/app --prompt "fix issue #42: the checkout tax bug" \
        --permission-mode acceptEdits --no-focus --json)"
ws="$(jq -r .workspace <<<"$out")"

# 2. Block until it finishes (or needs a human).
corral wait "$ws" --status working --timeout 15000   # it picked the task up
corral wait "$ws" --status idle    --timeout 600000  # it stopped

# 3. See what it did / what it's asking.
corral read "$ws" --lines 200 --source recent

# 4. Steer it with a follow-up.
corral send "$ws" "also add a regression test for that"

# 5. Tear down when the branch is pushed/merged.
corral close "$ws" --force        # or: corral prune
```

`corral ls --json` gives the fleet view (workspace, label, branch, agent
status, worktree path) for fan-in loops:

```sh
corral ls --json | jq -r '.[] | select(.status == "blocked") | .workspace'
```

Statuses come from herdr's agent detection: `working` (busy), `idle`
(finished or awaiting input), `blocked` (waiting on a permission prompt or a
question — usually worth a `corral read` and a human decision).

## MCP: the orchestrator's tool belt

`corral mcp` runs a stdio MCP server (pure bash + jq, like the rest of
corral). Register it once:

```sh
claude mcp add corral -- corral mcp
```

Then any Claude Code session can orchestrate:

| Tool | Wraps |
| --- | --- |
| `corral_spawn` | `corral spawn --json` (defaults to `--no-focus` so workers don't steal your screen; pass `focus: true` to override) |
| `corral_list` | `corral ls --json` |
| `corral_send` | `corral send` |
| `corral_read` | `corral read --source recent` |
| `corral_wait` | `corral wait` (default timeout 5 min) |
| `corral_close` | `corral close --force` |

A typical orchestrator prompt then just works:

> Spawn three corral agents on ~/dev/app — one per failing test suite in this
> list — wait for them to go idle, read each one's output, and summarize which
> fixes are ready to merge.

Every tool shells back out to the corral CLI, so the MCP surface can never
drift from the documented command behavior (including all the ownership
guards — an orchestrator can't close a workspace corral doesn't own).

## Patterns and caveats

- **Give workers autonomy.** An orchestrated worker can't click permission
  prompts. Spawn with `permission_mode: "acceptEdits"` (or your policy of
  choice) or workers will sit `blocked` waiting for a human.
- **Setup hooks run first.** If the repo commits a
  [`.corral/setup.sh`](configuration.md#per-repo-configuration-corral), the
  agent pane runs it *before* the agent starts — `corral send` during that
  window types into the setup script, not the agent. `spawn --json` reports
  `"setup": true` when a hook is gating the agent; wait for the agent to
  reach `working`/`idle` (or pass `--no-setup`) before sending follow-ups.
  `spawn --prompt` is unaffected — it's part of the launch command itself.
- **The send→wait race.** `wait --status idle` returns immediately if the
  agent hasn't flipped to `working` yet. After a `send`, either wait for
  `working` with a short timeout first, or wait on `--match` for a sentinel
  you asked the agent to print (e.g. "reply DONE when finished").
- **Humans can co-drive.** Workers are normal interactive panes — `corral
  focus w4` and type. The orchestrator sees whatever state results; nothing
  desyncs, because herdr is the single source of truth.
- **Results flow through git.** Each worker is on its own branch in its own
  worktree. The natural fan-in is `git`: have workers commit (or push and open
  PRs), then `corral prune` sweeps merged, clean workspaces.
- **One wait at a time.** `corral mcp` handles requests sequentially, so a
  long `corral_wait` blocks other corral tool calls in that session. Prefer
  bounded timeouts and re-polling with `corral_list` when juggling many
  workers.
