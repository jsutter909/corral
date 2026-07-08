"""The corral entry point: root help, dispatch, and error handling."""

from __future__ import annotations

import sys
from typing import List, Optional

from . import __version__
from .cli import HelpRequested, parse_args, render_help
from .commands import Context, all_commands, find_command
from .herdr import Herdr
from .settings import Settings
from .ui import C, CorralError


def root_usage(settings: Settings) -> str:
    lines = [
        f"{C.bold}corral{C.reset} — isolated AI-agent workspaces on top of herdr (v{__version__})",
        "",
        "Usage:",
        "  corral <command> [args]",
        "",
        "Commands:",
    ]
    entries = []
    for registered in all_commands():
        spec = registered.spec
        left = f"{spec.name} " + " ".join(a.display for a in spec.arguments)
        entries.append((left.strip(), spec.summary, spec.aliases))
    entries.append(("help [command]", "show help (add a command name for details).", ()))
    entries.append(("version", "print the corral version.", ()))
    width = max(len(left) for left, _, _ in entries) + 3
    for left, summary, aliases in entries:
        text = summary[0].upper() + summary.rstrip(".")[1:]
        if aliases:
            text += f" (alias: {', '.join(aliases)})"
        lines.append(f"  {left:<{width}}{text}")
    lines += [
        "",
        "Run 'corral <command> --help' for command-specific options.",
        "",
        f"Config: {settings.config_path}",
        "Docs:   https://github.com/jsutter909/corral",
    ]
    return "\n".join(lines) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        return _dispatch(args)
    except CorralError as exc:
        print(f"{C.red}error:{C.reset} {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


def _dispatch(args: List[str]) -> int:
    settings = Settings.load()
    command = args.pop(0) if args else "help"

    if command in ("version", "--version", "-V"):
        print(f"corral {__version__}")
        return 0

    if command in ("help", "--help", "-h"):
        if args:
            registered = find_command(args[0])
            if registered is None:
                print(root_usage(settings), end="", file=sys.stderr)
                raise CorralError(f"unknown command: {args[0]}")
            print(render_help(registered.spec, settings), end="")
            return 0
        print(root_usage(settings), end="")
        return 0

    registered = find_command(command)
    if registered is None:
        print(root_usage(settings), end="", file=sys.stderr)
        raise CorralError(f"unknown command: {command}")

    try:
        parsed = parse_args(registered.spec, tuple(args), settings)
    except HelpRequested:
        print(render_help(registered.spec, settings), end="")
        return 0

    ctx = Context(settings=settings, herdr=Herdr())
    return registered.run(ctx, parsed)


if __name__ == "__main__":
    sys.exit(main())
