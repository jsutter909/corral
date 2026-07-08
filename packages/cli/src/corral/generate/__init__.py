"""Artifact generation — docs, config example, and the oh-my-zsh plugin.

Everything corral used to maintain by hand alongside the code is now
**rendered from the registries** (command specs, settings, agents, IDEs)
and checked in:

* ``docs/usage.md`` — the command reference
* ``docs/configuration.md`` — the configuration guide
* ``packages/cli/share/config.example.sh`` — the example config
* ``packages/omz-plugin/_corral`` — zsh tab completion
* ``packages/omz-plugin/corral.plugin.zsh`` — aliases, ccd, prompt segment

Run ``python -m corral.generate`` (or ``make generate``) after changing a
spec; ``--check`` verifies the checked-in artifacts are fresh (CI runs it).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Tuple

from ..paths import REPO_ROOT

MANAGED_BY = "python -m corral.generate (or: make generate)"


def generated_header(comment: str, source: str) -> str:
    """A do-not-edit banner. `comment` is the line prefix ('#' or 'md')."""
    lines = (
        "GENERATED FILE — do not edit by hand.",
        f"Source of truth: {source}",
        f"Regenerate with: {MANAGED_BY}",
    )
    if comment == "md":
        return "<!--\n" + "".join(f"  {line}\n" for line in lines) + "-->\n"
    return "".join(f"{comment} {line}\n" for line in lines)


@dataclass(frozen=True)
class Artifact:
    path: str  # repo-root relative
    render: Callable[[], str]


def artifacts() -> Tuple[Artifact, ...]:
    from . import config_example, configuration_md, usage_md, zsh

    return (
        Artifact("docs/usage.md", usage_md.render),
        Artifact("docs/configuration.md", configuration_md.render),
        Artifact("packages/cli/share/config.example.sh", config_example.render),
        Artifact("packages/omz-plugin/_corral", zsh.render_completion),
        Artifact("packages/omz-plugin/corral.plugin.zsh", zsh.render_plugin),
    )


def write_all() -> None:
    for artifact in artifacts():
        target = REPO_ROOT / artifact.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(artifact.render(), encoding="utf-8")
        print(f"wrote {artifact.path}")


def check_all() -> bool:
    """True when every checked-in artifact matches its rendered content."""
    fresh = True
    for artifact in artifacts():
        target = REPO_ROOT / artifact.path
        expected = artifact.render()
        actual = target.read_text(encoding="utf-8") if target.is_file() else None
        if actual == expected:
            print(f"ok    {artifact.path}")
        else:
            state = "stale" if actual is not None else "missing"
            print(f"{state.upper():<5} {artifact.path}")
            fresh = False
    return fresh
