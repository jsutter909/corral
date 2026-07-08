# corral — configuration

corral resolves each setting in this order (later wins):

1. **Built-in defaults** (in `packages/cli/lib/common.sh`)
2. **`~/.config/corral/config.sh`** (or `$XDG_CONFIG_HOME/corral/config.sh`)
3. **`CORRAL_*` environment variables**
4. **Command-line flags**

> The config file is sourced as plain Bash, but corral snapshots your `CORRAL_*`
> environment first and re-applies it after — so values in `config.sh` act as
> your team/personal defaults, while a one-off `CORRAL_RATIO=0.5 corral spawn …`
> or a `--ratio` flag overrides them per run.

## Settings

| Variable | Flag | Default | Meaning |
| --- | --- | --- | --- |
| `CORRAL_AGENT` | `--agent` | `claude` | Agent launched in the left pane, or `none`. |
| `CORRAL_RATIO` | `--ratio` | `0.4` | Agent (left) pane width share, `0..1`. |
| `CORRAL_BRANCH_PREFIX` | — | `agent` | Prefix for auto branch names: `<prefix>/<repo>-<timestamp>`. |
| `CORRAL_BASE` | `--base` | `` (HEAD) | Base ref for new worktrees. |
| `CORRAL_WORKTREES_DIR` | — | `~/.herdr/worktrees` | Where herdr checks out corral's worktrees; corral only ever destroys worktrees under this directory. |
| `CORRAL_CONFIG` | — | `~/.config/corral/config.sh` | Path to the config file itself. |

## Setting it up

```sh
mkdir -p ~/.config/corral
cp "$(dirname "$(readlink -f "$(command -v corral)")")/../share/config.example.sh" \
   ~/.config/corral/config.sh
$EDITOR ~/.config/corral/config.sh
```

Or just create it by hand:

```sh
# ~/.config/corral/config.sh
CORRAL_AGENT=claude
CORRAL_RATIO=0.4
CORRAL_BRANCH_PREFIX=agent
CORRAL_BASE=main
```

## Team defaults

Because it's just Bash, you can share a config in your repo and have coworkers
source it, e.g. point `CORRAL_CONFIG` at a checked-in file:

```sh
export CORRAL_CONFIG="$HOME/dev/team-dotfiles/corral.sh"
```
