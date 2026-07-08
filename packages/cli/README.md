# @corral/cli

The `corral` command — isolated AI-agent workspaces on top of
[herdr](https://herdr.dev). This is the package installed by the repo's
top-level `install.sh`.

- **Language:** Python 3.9+ (stdlib only — no dependencies, no build step)
- **Runtime deps:** `herdr`, `git`
- **Entry point:** [`bin/corral`](bin/corral) — puts `src/` on `sys.path` and
  runs the `corral` package

See the [top-level README](../../README.md) for install and usage, and
[`docs/`](../../docs) for the full reference, configuration, and architecture.

## Layout

```
bin/corral                # launcher (symlinked onto PATH as `corral`)
src/corral/
├── app.py                # dispatch + root help
├── cli.py                # declarative Command/Option/Argument specs + parser
├── settings.py           # settings registry + config loading
├── herdr.py              # typed herdr client
├── workspaces.py         # workspace model + ownership invariant
├── agents.py  ides.py    # agent / IDE registries
├── hooks.py              # .corral/setup.sh + cleanup.sh lifecycle
├── commands/             # one module per subcommand (SPEC + run)
└── generate/             # renders docs, config example, and the omz plugin
share/config.example.sh   # GENERATED from the settings registry
tests/                    # unittest suite; runs without a herdr server
pyproject.toml            # optional `pip install` metadata
```

The specs and registries are the single source of truth: `--help`, the parser,
`docs/usage.md`, `docs/configuration.md`, `share/config.example.sh`, and the
oh-my-zsh plugin are all rendered from them (`make generate` at the repo root;
CI verifies freshness).

## Local development

From the repo root:

```sh
make link       # symlink this bin/corral onto your PATH
make generate   # re-render generated artifacts after changing a spec
make test       # python unit tests + zsh completion tests
make check      # lint + freshness + tests
```
