# packages/

corral is a monorepo so that the CLI and the tooling that grows around it live
and version together.

| Package | Status | What it is |
| --- | --- | --- |
| [`cli/`](cli/) | ✅ shipping | The `corral` command — spawn and manage isolated agent workspaces. |
| `omz-plugin/` | 🅿️ planned | An oh-my-zsh plugin: completions, aliases, and a prompt segment showing active corral workspaces. |
| _future tooling_ | 💭 ideas | Shell completions (bash/fish), a status-bar helper, richer `ls`/dashboard views. |

## Conventions for new packages

- One self-contained directory under `packages/`.
- Its own `README.md` describing what it is and how to install it.
- No cross-package imports at runtime beyond the documented CLI surface — each
  package should be installable on its own.
- Keep runtime dependencies minimal (the CLI needs only `herdr`, `git`, `jq`).
