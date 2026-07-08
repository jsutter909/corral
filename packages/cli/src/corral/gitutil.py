"""Small git helpers — every git call the CLI makes, in one place."""

from __future__ import annotations

import subprocess
from typing import Optional


def _run(args, cwd: Optional[str] = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )


def repo_root(path: str) -> str:
    """Toplevel of the repo containing `path`, or '' when outside a repo."""
    proc = _run(["-C", path, "rev-parse", "--show-toplevel"])
    return proc.stdout.strip() if proc.returncode == 0 else ""


def current_branch(worktree: str) -> str:
    proc = _run(["rev-parse", "--abbrev-ref", "HEAD"], cwd=worktree)
    return proc.stdout.strip() if proc.returncode == 0 else "?"


def branch_exists(repo: str, branch: str) -> bool:
    proc = _run(["show-ref", "--verify", "--quiet", f"refs/heads/{branch}"], cwd=repo)
    return proc.returncode == 0


def ref_exists(worktree: str, ref: str) -> bool:
    proc = _run(["rev-parse", "--verify", "--quiet", ref], cwd=worktree)
    return proc.returncode == 0


def has_uncommitted_changes(worktree: str) -> bool:
    proc = _run(["status", "--porcelain"], cwd=worktree)
    return proc.returncode != 0 or bool(proc.stdout.strip())


def origin_head(worktree: str) -> str:
    """'origin/<default branch>' when origin/HEAD is set, else ''."""
    proc = _run(["symbolic-ref", "--quiet", "refs/remotes/origin/HEAD"], cwd=worktree)
    if proc.returncode != 0:
        return ""
    ref = proc.stdout.strip()
    prefix = "refs/remotes/"
    return ref[len(prefix):] if ref.startswith(prefix) else ""


def is_ancestor(worktree: str, ancestor: str, descendant: str) -> bool:
    proc = _run(["merge-base", "--is-ancestor", ancestor, descendant], cwd=worktree)
    return proc.returncode == 0
