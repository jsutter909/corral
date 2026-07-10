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


def remotes(repo: str) -> List[str]:
    """Configured remote names (e.g. ['origin']); empty outside a repo."""
    proc = _run(["-C", repo, "remote"])
    return proc.stdout.split() if proc.returncode == 0 else []


def remote_ref(repo: str, branch: str) -> str:
    """Resolve `branch` to a unique remote-tracking ref, or '' when there is
    none (or it's ambiguous across remotes).

    Accepts both a plain branch name — looked up across every remote,
    preferring ``origin`` when more than one carries it — and a name already
    qualified with its remote (``origin/feature/x``). The return value is a
    ref like ``origin/feature/x`` suitable for use as a `git worktree` base.
    """
    rems = remotes(repo)
    # Already qualified as <remote>/<name>? (handles slashed branch names too)
    for r in rems:
        prefix = f"{r}/"
        if branch.startswith(prefix) and _remote_ref_exists(repo, r, branch[len(prefix):]):
            return branch
    # Plain name: collect the remotes that carry it, preferring origin.
    matches = [r for r in rems if _remote_ref_exists(repo, r, branch)]
    if not matches:
        return ""
    if "origin" in matches:
        return f"origin/{branch}"
    if len(matches) == 1:
        return f"{matches[0]}/{branch}"
    return ""  # ambiguous across remotes — don't guess


def _remote_ref_exists(repo: str, remote: str, branch: str) -> bool:
    proc = _run(
        ["-C", repo, "show-ref", "--verify", "--quiet", f"refs/remotes/{remote}/{branch}"]
    )
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
