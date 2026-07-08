"""The IDE registry for `corral open`, plus Remote-SSH deep links.

Declared once; consumed by the open command, the docs, and the generated
zsh completion.
"""

from __future__ import annotations

import urllib.parse
from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class IDE:
    name: str  # canonical config/flag value
    cli: str  # shell command that opens a folder
    scheme: str  # URI scheme registered for Remote-SSH deep links
    app: str  # display name (also the macOS `open -a` target)
    aliases: Tuple[str, ...] = ()

    @property
    def all_names(self) -> Tuple[str, ...]:
        return (self.name, *self.aliases)


IDES: Tuple[IDE, ...] = (
    IDE("vscode", cli="code", scheme="vscode", app="Visual Studio Code", aliases=("code",)),
    IDE("cursor", cli="cursor", scheme="cursor", app="Cursor"),
)


def find_ide(name: str) -> Optional[IDE]:
    for ide in IDES:
        if name in ide.all_names:
            return ide
    return None


def encode_path(path: str) -> str:
    """Percent-encode a filesystem path for a vscode-remote URI, keeping '/'."""
    return urllib.parse.quote(path, safe="/")


def remote_uri(ide: IDE, host: str, path: str) -> str:
    """The Remote-SSH deep link VS Code and Cursor register for their scheme:
    <scheme>://vscode-remote/ssh-remote+<host><absolute path>
    """
    return f"{ide.scheme}://vscode-remote/ssh-remote+{host}{encode_path(path)}"
