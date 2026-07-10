"""Per-repo lifecycle hooks (.corral/setup.sh, .corral/cleanup.sh) and the
single choke point for destroying corral workspaces.
"""

from __future__ import annotations

import os
import subprocess

from . import ui
from .herdr import Herdr

SETUP_SCRIPT = os.path.join(".corral", "setup.sh")
CLEANUP_SCRIPT = os.path.join(".corral", "cleanup.sh")


def has_setup_script(worktree: str) -> bool:
    return os.path.isfile(os.path.join(worktree, SETUP_SCRIPT))


def run_cleanup(worktree: str, force: bool, enabled: bool = True) -> bool:
    """Run a worktree's .corral/cleanup.sh before the worktree is removed —
    the counterpart to .corral/setup.sh on spawn.

    Runs cwd'd into the worktree (so the script path stays relative, like
    setup) with stdin closed — a stdin-reading script must not be able to
    swallow anything from the caller. The script executes as it exists in the
    worktree NOW, including changes made during the session (see the security
    note in docs/configuration.md).

    Returns True when it is safe to proceed with removal: no script present,
    cleanup disabled, the script succeeded, or the caller forced past a
    failure. Returns False only when the script failed and force is not set —
    the caller MUST then abort removal (and own the user-facing
    --force/--no-cleanup hint) so a failing teardown is never silently
    discarded.
    """
    if not enabled:
        return True
    if not worktree or not os.path.isfile(os.path.join(worktree, CLEANUP_SCRIPT)):
        return True

    ui.info(f"running {CLEANUP_SCRIPT}")
    try:
        proc = subprocess.run(
            ["bash", CLEANUP_SCRIPT],
            cwd=worktree,
            stdin=subprocess.DEVNULL,
        )
        rc = proc.returncode
    except OSError as exc:
        ui.warn(f"{CLEANUP_SCRIPT} could not run ({exc})")
        rc = 1

    if rc == 0:
        return True
    if force:
        ui.warn(f"{CLEANUP_SCRIPT} failed (exit {rc}) — continuing anyway (--force)")
        return True
    ui.warn(f"{CLEANUP_SCRIPT} failed (exit {rc})")
    return False


def remove_workspace(
    herdr: Herdr,
    workspace_id: str,
    worktree: str,
    force: bool,
    cleanup: bool,
    settings=None,
) -> bool:
    """Run the cleanup hook, then remove a workspace's worktree.

    The single choke point for destroying corral workspaces, so no removal
    path can forget the cleanup-before-remove invariant. cleanup=False skips
    the hook (--no-cleanup); force=True also removes when the hook fails.
    Returns False (nothing removed) when cleanup fails and force is not set.

    When `settings` is given, any shared resources the workspace still holds
    (see `corral resource`) are released after the removal succeeds.
    """
    if cleanup and not run_cleanup(worktree, force):
        return False
    herdr.worktree_remove(workspace_id)
    if settings is not None:
        release_resources(settings, worktree)
    return True


def release_resources(settings, worktree: str) -> None:
    """Best-effort: return the workspace's checked-out shared resources.

    Runs after the worktree is gone, needs only the resources database (no
    herdr, no git), and never raises — a database hiccup must not turn a
    successful close/prune into a failure.
    """
    from . import resources  # late import: sqlite3 only when actually needed

    if not os.path.isfile(settings.resources_db):
        return
    holder = resources.holder_for_worktree(settings.worktrees_dir, worktree)
    if not holder:
        return
    try:
        conn = resources.connect(settings.resources_db)
        try:
            released = resources.release_all(conn, holder)
        finally:
            conn.close()
    except Exception as exc:
        ui.warn(
            f"could not auto-release shared resources ({exc}) — run "
            f"'corral resource release --all --as {holder}' by hand"
        )
        return
    if released:
        names = ", ".join(f"{pool}/{name}" for pool, name in released)
        ui.info(f"released {len(released)} shared resource(s): {names}")
