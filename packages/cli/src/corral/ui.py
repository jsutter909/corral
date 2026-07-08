"""Terminal output helpers.

All human-facing messages go to stderr so stdout stays pipeable (the ls table
rows and `open`'s Remote-SSH link are the only things corral prints to stdout).
Colors are enabled only when stderr is a terminal, matching the original CLI.
"""

from __future__ import annotations

import sys


class CorralError(Exception):
    """A user-facing failure: printed as `error: <message>` and exits 1."""


class _Palette:
    def __init__(self, enabled: bool) -> None:
        self.red = "\033[31m" if enabled else ""
        self.green = "\033[32m" if enabled else ""
        self.yellow = "\033[33m" if enabled else ""
        self.dim = "\033[2m" if enabled else ""
        self.bold = "\033[1m" if enabled else ""
        self.reset = "\033[0m" if enabled else ""


C = _Palette(sys.stderr.isatty())


def info(msg: str) -> None:
    print(f"{C.dim}{msg}{C.reset}", file=sys.stderr)


def ok(msg: str) -> None:
    print(f"{C.green}✔{C.reset} {msg}", file=sys.stderr)


def warn(msg: str) -> None:
    print(f"{C.yellow}!{C.reset} {msg}", file=sys.stderr)


def die(msg: str) -> "CorralError":
    """Convenience for `raise die(...)` call sites."""
    return CorralError(msg)


def confirm(prompt: str) -> bool:
    """Ask a yes/no question on the controlling terminal.

    Reads from /dev/tty (not stdin) so piped input can never auto-confirm a
    destructive action; without a terminal it refuses instead of hanging.
    """
    sys.stderr.write(prompt)
    sys.stderr.flush()
    try:
        with open("/dev/tty", "r", encoding="utf-8", errors="replace") as tty:
            answer = tty.readline()
            if answer == "":
                raise OSError("EOF on /dev/tty")
    except OSError:
        sys.stderr.write("\n")
        raise CorralError(
            "no terminal available for confirmation — use --force to skip the prompt"
        ) from None
    return answer.strip() in ("y", "Y", "yes", "YES")
