"""Render docs/usage.md — the command reference — from the command specs."""

from __future__ import annotations

from typing import List

from ..cli import Command, Option
from ..commands import all_commands
from ..settings import BY_ATTR
from . import generated_header


def _doc_default(opt: Option) -> str:
    if opt.setting:
        setting = BY_ATTR[opt.setting]
        if setting.default_doc:
            return setting.default_doc
        default = setting.default
        return f"`{default}`" if isinstance(default, str) and default else "(none)"
    return opt.default_doc or ("—" if opt.is_flag else "(none)")


def _md_cell(text: str) -> str:
    return " ".join(text.split()).replace("|", "\\|")


def _command_section(cmd: Command) -> List[str]:
    lines = [f"## `{cmd.synopsis.replace('corral ', 'corral ', 1)}`", ""]

    prose = cmd.doc or cmd.description or cmd.summary
    lines += [prose.strip(), ""]

    if cmd.aliases:
        alias_text = ", ".join(f"`corral {a}`" for a in cmd.aliases)
        lines += [f"Alias: {alias_text}.", ""]

    if cmd.arguments:
        lines += ["**Arguments**", "", "| Arg | Meaning |", "| --- | --- |"]
        for arg in cmd.arguments:
            meaning = _md_cell(arg.doc or arg.help)
            lines.append(f"| `{arg.display}` | {meaning} |")
        lines.append("")

    if cmd.options:
        lines += [
            "**Options**",
            "",
            "| Option | Default | Meaning |",
            "| --- | --- | --- |",
        ]
        for opt in cmd.options:
            names = ", ".join(f"`{n}`" for n in opt.names)
            if opt.metavar:
                names += f" `{opt.metavar}`"
            meaning = _md_cell(opt.doc or opt.help)
            lines.append(f"| {names} | {_doc_default(opt)} | {meaning} |")
        lines.append("")

    if cmd.examples:
        lines.append("```sh")
        width = max(len(e.command) for e in cmd.examples) + 3
        for example in cmd.examples:
            if example.note:
                lines.append(f"{example.command:<{width}}# {example.note}")
            else:
                lines.append(example.command)
        lines += ["```", ""]

    return lines


def render() -> str:
    lines = [
        generated_header("md", "packages/cli/src/corral/commands/*.py (each command's SPEC)").rstrip(),
        "",
        "# corral — command reference",
        "",
        "Every command also prints this via `corral <command> --help`.",
        "",
    ]
    for registered in all_commands():
        lines += _command_section(registered.spec)

    lines += [
        "## Exit codes",
        "",
        "`0` success · `1` usage error or a failed herdr/git operation (the message",
        "explains which).",
    ]
    return "\n".join(lines).rstrip() + "\n"
