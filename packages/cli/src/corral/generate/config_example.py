"""Render share/config.example.sh from the settings registry."""

from __future__ import annotations

from ..settings import SETTINGS, Setting
from . import generated_header

_PREAMBLE = """\
# corral config — copy to ~/.config/corral/config.sh and edit.
#
#   mkdir -p ~/.config/corral
#   cp "$(dirname "$(readlink -f "$(command -v corral)")")/../share/config.example.sh" \\
#      ~/.config/corral/config.sh
#
# corral parses this file for plain CORRAL_* assignments (quotes and $HOME/~
# expansion supported; arbitrary shell is ignored). Every value can also be
# set as a CORRAL_* environment variable, and any command-line flag overrides
# both.
"""


def _entry(setting: Setting) -> str:
    lines = [f"# {line}" if line else "#" for line in setting.example.splitlines()]
    if setting.example_value:
        value = setting.example_value
    elif isinstance(setting.default, str):
        value = setting.default
    else:  # dynamic default — the example must spell out a literal
        value = ""
    assignment = f"{setting.env}={value}"
    if setting.example_commented:
        assignment = f"# {assignment}"
    lines.append(assignment)
    return "\n".join(lines)


def render() -> str:
    blocks = [
        generated_header("#", "packages/cli/src/corral/settings.py").rstrip(),
        _PREAMBLE.rstrip(),
    ]
    blocks += [_entry(setting) for setting in SETTINGS]
    return "\n\n".join(blocks) + "\n"
