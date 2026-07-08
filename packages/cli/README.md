# @corral/cli

The `corral` command — isolated AI-agent workspaces on top of
[herdr](https://herdr.dev). This is the package installed by the repo's
top-level `install.sh`.

- **Language:** Bash (no build step)
- **Runtime deps:** `herdr`, `git`, `jq`
- **Entry point:** [`bin/corral`](bin/corral) — dispatches to `lib/<command>.sh`

See the [top-level README](../../README.md) for install and usage, and
[`docs/`](../../docs) for the full reference, configuration, and architecture.

## Layout

```
bin/corral            # dispatcher (symlinked onto PATH as `corral`)
lib/common.sh         # logging, dep checks, config, herdr/JSON helpers, guards
lib/{spawn,close,ls,focus,prune}.sh
share/config.example.sh
test/smoke.sh         # runs without a herdr server
```

## Local development

From the repo root:

```sh
make link     # symlink this bin/corral onto your PATH
make test     # smoke tests
make lint     # shellcheck (if installed)
```
