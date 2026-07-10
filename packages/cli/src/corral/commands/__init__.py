"""Subcommand registry and shared runtime context.

Each command module exposes a `SPEC` (the declarative :class:`corral.cli.Command`)
and a `run(ctx, args)` function. Registering the module here wires it into the
dispatcher, `corral help`, docs generation, and zsh completion all at once.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

from ..cli import Command
from ..herdr import Herdr
from ..settings import Settings
from ..ui import CorralError
from ..workspaces import Workspace, resolve_workspace


@dataclass
class Context:
    settings: Settings
    herdr: Herdr


@dataclass(frozen=True)
class Registered:
    spec: Command
    run: Callable[[Context, Dict[str, object]], int]


def _registry() -> Tuple[Registered, ...]:
    # Imported lazily so command modules can import from this package freely.
    from . import (
        close,
        doctor,
        focus,
        ls,
        monitor,
        open as open_cmd,
        prune,
        resource,
        spawn,
    )

    return (
        Registered(spawn.SPEC, spawn.run),
        Registered(ls.SPEC, ls.run),
        Registered(focus.SPEC, focus.run),
        Registered(open_cmd.SPEC, open_cmd.run),
        Registered(close.SPEC, close.run),
        Registered(prune.SPEC, prune.run),
        Registered(resource.SPEC, resource.run),
        Registered(monitor.SPEC, monitor.run),
        Registered(doctor.SPEC, doctor.run),
    )


_cache: Optional[Tuple[Registered, ...]] = None


def all_commands() -> Tuple[Registered, ...]:
    global _cache
    if _cache is None:
        _cache = _registry()
    return _cache


def find_command(name: str) -> Optional[Registered]:
    for registered in all_commands():
        if name == registered.spec.name or name in registered.spec.aliases:
            return registered
    return None


# ---------------------------------------------------------------------------
# Helpers shared by several commands
# ---------------------------------------------------------------------------


def owned_workspaces(ctx: Context) -> List[Workspace]:
    """Every corral-owned workspace — a single `workspace list` call, filtered
    through the ownership invariant."""
    return [
        ws
        for ws in ctx.herdr.workspace_list()
        if ws.is_corral_owned(ctx.settings.worktrees_dir)
    ]


def resolve_ref_or_current(ctx: Context, ref: str, example: str) -> str:
    """Workspace id for an explicit ref, or the invoking pane's workspace."""
    if ref:
        return resolve_workspace(ref, ctx.herdr.workspace_list()).id
    current = ctx.herdr.current_workspace()
    if not current:
        raise CorralError(
            f"could not determine current workspace; pass one (e.g. {example})"
        )
    return current
