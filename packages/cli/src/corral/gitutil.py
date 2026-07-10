"""Small git helpers — every git call the CLI makes, in one place."""

from __future__ import annotations

import os
import subprocess
from typing import List, Optional


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


def repo_common_root(path: str) -> str:
    """Toplevel of the MAIN checkout of the repo containing `path`, or ''.

    Unlike repo_root, this is the same for every linked worktree of a repo,
    so it can stand in for "the repo" as a stable identity.
    """
    top = repo_root(path)
    if not top:
        return ""
    proc = _run(["rev-parse", "--git-common-dir"], cwd=top)
    if proc.returncode != 0:
        return ""
    common = os.path.realpath(os.path.join(top, proc.stdout.strip()))
    if os.path.basename(common) == ".git":
        return os.path.dirname(common)
    return common  # bare/detached gitdir layouts: still a stable identity


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


def discover_worktrees(worktrees_dir: str) -> List[str]:
    """Every corral worktree checkout under `worktrees_dir`, sorted.

    herdr lays these out as ``<worktrees_dir>/<repo>/<label>/`` — the same
    two-level layout `resources.holder_for_worktree` assumes — and a directory
    is a checkout when it holds a ``.git`` entry (a *file*, for linked
    worktrees). Pure filesystem walk, no git or herdr server needed, so `start`
    can reopen them and `end` can release their resources even when herdr is
    down. Unreadable directories are skipped rather than fatal.
    """
    base = os.path.realpath(worktrees_dir)
    if not os.path.isdir(base):
        return []
    found: List[str] = []
    try:
        repos = sorted(os.listdir(base))
    except OSError:
        return []
    for repo in repos:
        repo_dir = os.path.join(base, repo)
        if not os.path.isdir(repo_dir):
            continue
        try:
            labels = sorted(os.listdir(repo_dir))
        except OSError:
            continue
        for label in labels:
            wt = os.path.join(repo_dir, label)
            if os.path.exists(os.path.join(wt, ".git")):
                found.append(wt)
    return found
