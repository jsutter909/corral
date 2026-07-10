"""The workspace domain model and corral's ownership invariant.

A corral workspace is a **linked** git worktree that herdr checked out under
the configured worktrees directory. Both properties matter:

* the primary repo checkout is not a linked worktree — never corral's;
* a linked worktree the user made by hand (``git worktree add`` +
  ``herdr worktree open``) lives outside the worktrees dir — not corral's
  to destroy either.

:meth:`Workspace.is_corral_owned` is the single implementation of that test;
``ls``, ``close``, and ``prune`` all go through it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, List, Optional

from .ui import CorralError


@dataclass(frozen=True)
class Worktree:
    checkout_path: str
    is_linked: bool
    repo_name: str

    @classmethod
    def from_payload(cls, payload: Optional[Dict]) -> Optional["Worktree"]:
        if not payload:
            return None
        return cls(
            checkout_path=payload.get("checkout_path") or "",
            is_linked=bool(payload.get("is_linked_worktree", False)),
            repo_name=payload.get("repo_name") or "?",
        )


@dataclass(frozen=True)
class Workspace:
    id: str
    label: str
    agent_status: str
    worktree: Optional[Worktree]

    @classmethod
    def from_payload(cls, payload: Dict) -> "Workspace":
        return cls(
            id=payload.get("workspace_id") or "",
            label=payload.get("label") or "?",
            agent_status=payload.get("agent_status") or "unknown",
            worktree=Worktree.from_payload(payload.get("worktree")),
        )

    def is_corral_owned(self, worktrees_dir: str) -> bool:
        """The ownership invariant: linked worktree AND under worktrees_dir."""
        wt = self.worktree
        if wt is None or not wt.is_linked or not wt.checkout_path:
            return False
        prefix = worktrees_dir.rstrip(os.sep) + os.sep
        return wt.checkout_path.startswith(prefix)

    def owned_worktree_path(self, worktrees_dir: str) -> str:
        """Checkout path for corral-owned workspaces, '' otherwise."""
        if self.is_corral_owned(worktrees_dir):
            return self.worktree.checkout_path  # type: ignore[union-attr]
        return ""


@dataclass(frozen=True)
class WorktreeCreation:
    """What `herdr worktree create`/`open` hands back — the raw materials of a
    workspace. `already_open` is only ever True for `open` (a worktree that
    already had a workspace in this server); `create` always makes a fresh one."""

    workspace_id: str
    root_pane_id: str
    worktree_path: str
    already_open: bool = False


def resolve_workspace(ref: str, workspaces: List[Workspace]) -> Workspace:
    """Resolve a workspace by id or unique label (exact id match wins).

    Raises CorralError with the historical wording on no match / ambiguity.
    """
    by_id = [ws for ws in workspaces if ws.id == ref]
    if by_id:
        return by_id[0]
    by_label = [ws for ws in workspaces if ws.label == ref]
    if len(by_label) == 1:
        return by_label[0]
    if len(by_label) > 1:
        raise CorralError(f"'{ref}' matches multiple workspaces; use the workspace id")
    raise CorralError(f"no workspace matching '{ref}'")
