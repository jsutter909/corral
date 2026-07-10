"""Declarative command specs — parse, help, docs, and completions from one model.

Each subcommand declares a :class:`Command` (its arguments, options, prose,
and examples) exactly once. That single declaration is consumed by:

* :func:`parse_args` — the runtime argument parser;
* :func:`render_help` — ``corral <cmd> --help``;
* ``corral.generate.usage_md`` — the ``docs/usage.md`` reference;
* ``corral.generate.zsh`` — the oh-my-zsh ``_corral`` completion and the
  plugin's alias table.

So a new flag added to a spec shows up in the parser, the help text, the
manual, and tab completion without touching anything else.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, Optional, Tuple

from .ui import CorralError

# ---------------------------------------------------------------------------
# Spec model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Example:
    command: str
    note: str = ""  # trailing "# comment" shown next to the example


@dataclass(frozen=True)
class Argument:
    name: str  # "repo" / "branch" / "workspace"
    help: str  # one-liner for --help and the docs table
    required: bool = True
    variadic: bool = False  # last argument only: collects all trailing positionals
    doc: str = ""  # richer prose for docs/usage.md (falls back to help)
    completion: str = ""  # zsh action (e.g. "_directories", "_corral_workspaces")
    value_label: str = ""  # zsh completion description (falls back to name)

    @property
    def dest(self) -> str:
        return self.name.replace("-", "_")

    @property
    def display(self) -> str:
        name = f"{self.name}…" if self.variadic else self.name
        return f"<{name}>" if self.required else f"[{name}]"


@dataclass(frozen=True)
class Option:
    long: str  # "--agent"
    help: str  # one-liner for --help, docs, and zsh [descriptions]
    short: str = ""  # "-a"
    metavar: str = ""  # "<name>"; empty means boolean flag
    optional_value: bool = False  # bare flag -> True; value only via --opt=value
    setting: str = ""  # Settings attr backing the default (e.g. "agent")
    default_doc: str = ""  # documented default when not settings-backed
    choices: Tuple[str, ...] = ()  # completion candidates for the value
    completion: str = ""  # zsh action overriding `choices` (e.g. "_corral_git_refs")
    value_hint: str = ""  # zsh description of the value ("git ref")
    excludes: Tuple[str, ...] = ()  # mutually exclusive option longs (zsh)
    doc: str = ""  # richer prose for docs/usage.md (falls back to help)

    @property
    def dest(self) -> str:
        return self.long.lstrip("-").replace("-", "_")

    @property
    def is_flag(self) -> bool:
        return not self.metavar

    @property
    def names(self) -> Tuple[str, ...]:
        return (self.short, self.long) if self.short else (self.long,)

    @property
    def display(self) -> str:
        joined = ", ".join(self.names)
        if self.optional_value:
            return f"{joined}[={self.metavar}]"
        return f"{joined} {self.metavar}" if self.metavar else joined


@dataclass(frozen=True)
class Command:
    name: str
    summary: str  # one line for `corral help` and the command list
    description: str = ""  # prose paragraphs for --help and usage.md
    aliases: Tuple[str, ...] = ()
    arguments: Tuple[Argument, ...] = ()
    options: Tuple[Option, ...] = ()
    examples: Tuple[Example, ...] = ()
    epilog: str = ""  # extra prose after the options in --help
    shell_alias: str = ""  # omz-plugin alias (e.g. "csp" -> "corral spawn")
    doc: str = ""  # markdown prose for docs/usage.md (falls back to description/epilog)

    @property
    def synopsis(self) -> str:
        parts = [f"corral {self.name}"]
        parts += [a.display for a in self.arguments]
        if self.options:
            parts.append("[options]")
        return " ".join(parts)

    def find_option(self, token: str) -> Optional[Option]:
        for opt in self.options:
            if token in opt.names:
                return opt
        return None


class HelpRequested(Exception):
    """Raised by parse_args when -h/--help is seen; the caller prints help."""


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def parse_args(cmd: Command, argv: Tuple[str, ...], settings) -> Dict[str, object]:
    """Parse argv against a Command spec.

    Returns a dict keyed by dest: flags default to False, valued options
    default to their backing setting (or ""), arguments default to ""
    (variadic arguments to []). Optional-value options default to False,
    become True when given bare, and take a value only as --opt=value.
    Raises CorralError with the same wording the bash CLI used.
    """
    values: Dict[str, object] = {}
    for opt in cmd.options:
        if opt.is_flag or opt.optional_value:
            values[opt.dest] = False
        else:
            values[opt.dest] = getattr(settings, opt.setting) if opt.setting else ""
    for arg in cmd.arguments:
        values[arg.dest] = [] if arg.variadic else ""

    positionals = []
    tokens = list(argv)
    only_positional = False
    while tokens:
        token = tokens.pop(0)
        if only_positional:
            positionals.append(token)
            continue
        if token == "--":
            only_positional = True
            continue
        if token in ("-h", "--help"):
            raise HelpRequested()
        if token.startswith("-") and token != "-":
            name, eq, inline = token.partition("=")
            opt = cmd.find_option(name)
            if opt is None:
                raise CorralError(
                    f"unknown option: {token} (try 'corral {cmd.name} --help')"
                )
            if opt.is_flag:
                if eq:
                    raise CorralError(f"{name} does not take a value")
                values[opt.dest] = True
            elif opt.optional_value:
                # Never consumes the next token — a value must use --opt=value,
                # so a following positional can't be swallowed by mistake.
                values[opt.dest] = inline if eq else True
            elif eq:
                values[opt.dest] = inline
            else:
                if not tokens:
                    raise CorralError(f"{name} needs a value")
                values[opt.dest] = tokens.pop(0)
            continue
        positionals.append(token)

    tail = cmd.arguments[-1] if cmd.arguments and cmd.arguments[-1].variadic else None
    fixed = cmd.arguments[:-1] if tail is not None else cmd.arguments
    if tail is None and len(positionals) > len(cmd.arguments):
        extra = positionals[len(cmd.arguments)]
        raise CorralError(f"unexpected argument: {extra}")
    for arg, value in zip(fixed, positionals):
        values[arg.dest] = value
    if tail is not None:
        values[tail.dest] = positionals[len(fixed):]

    return values


# ---------------------------------------------------------------------------
# Help rendering
# ---------------------------------------------------------------------------


def _option_default(opt: Option, settings) -> str:
    if opt.setting:
        return settings.describe_default(opt.setting)
    return opt.default_doc


def render_help(cmd: Command, settings) -> str:
    from .ui import C  # late import: palette reflects the live terminal

    lines = [f"{C.bold}corral {cmd.name}{C.reset} — {cmd.summary}", ""]
    lines += ["Usage:", f"  {cmd.synopsis}", ""]

    if cmd.arguments:
        lines.append("Arguments:")
        width = max(len(a.display) for a in cmd.arguments) + 2
        for arg in cmd.arguments:
            first, *rest = arg.help.splitlines()
            lines.append(f"  {arg.display:<{width}}{first}")
            lines += [f"  {'':<{width}}{extra}" for extra in rest]
        lines.append("")

    if cmd.options:
        lines.append("Options:")
        width = max(len(o.display) for o in cmd.options) + 2
        for opt in cmd.options:
            first, *rest = opt.help.splitlines()
            default = _option_default(opt, settings)
            if default:
                first = f"{first} (default: {default})"
            lines.append(f"  {opt.display:<{width}}{first}")
            lines += [f"  {'':<{width}}{extra}" for extra in rest]
        lines.append("")

    if cmd.description:
        lines += [cmd.description.strip(), ""]
    if cmd.epilog:
        lines += [cmd.epilog.strip(), ""]

    if cmd.aliases:
        lines += ["Alias: " + ", ".join(f"corral {a}" for a in cmd.aliases), ""]

    if cmd.examples:
        lines.append("Examples:")
        width = max(len(e.command) for e in cmd.examples) + 2
        for ex in cmd.examples:
            if ex.note:
                lines.append(f"  {ex.command:<{width}}# {ex.note}")
            else:
                lines.append(f"  {ex.command}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
