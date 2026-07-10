"""corral end — stop corral's herdr session and release its shared resources."""

from __future__ import annotations

from typing import Dict, List

from .. import gitutil, hooks, resources, ui
from ..cli import Command, Example, Option
from ..herdr import require_deps
from . import Context
from .start import SESSION_NAME

SPEC = Command(
    name="end",
    summary="stop corral's herdr session and release its shared resources.",
    shell_alias="cnd",
    description=(
        "The teardown counterpart to 'corral start'. It stops the persistent\n"
        "'corral' session — killing every agent running in it — and first returns\n"
        "any shared resources (see 'corral resource') still checked out by those\n"
        "worktrees to their pools, so nothing stays leased after the session is gone.\n"
        "\n"
        "Prompts before stopping (agents lose their state) unless --force. The git\n"
        "worktrees themselves are left on disk — only the session is torn down — so a\n"
        "later 'corral start' reopens them. Use 'corral close'/'corral prune' to remove\n"
        "individual worktrees."
    ),
    doc=(
        "Stop corral's persistent **`corral`** session — the teardown counterpart to\n"
        "`corral start` — and release the shared resources its worktrees still hold.\n"
        "\n"
        "Stopping the session kills every agent running in it, so `end` prompts first\n"
        "unless `--force`. Before stopping, it returns any items still checked out by a\n"
        "corral worktree (holder `ws:<repo>/<label>`, see `corral resource`) to their\n"
        "pools — the same auto-release `corral close` does, but for the whole bench at\n"
        "once — so no lease outlives the session. `--no-resources` leaves leases in\n"
        "place.\n"
        "\n"
        "The git worktrees under `CORRAL_WORKTREES_DIR` are left untouched; a later\n"
        "`corral start` reopens them. To remove a worktree, use `corral close` /\n"
        "`corral prune`."
    ),
    epilog=(
        "For a remote session (you ran 'corral start --remote <target>'), the session\n"
        "lives on that machine — run 'corral end' there to stop it. The local\n"
        "monitor-port forward is separate; kill it by hand (pkill -f 'ssh -L <port>',\n"
        "or 'pkill autossh') when you're done with it."
    ),
    options=(
        Option(
            "--force",
            short="-f",
            help="Skip the confirmation prompt",
            doc="Skip the confirmation prompt.",
        ),
        Option(
            "--no-resources",
            help="Don't auto-release shared resources held by the worktrees",
            doc="Don't release the shared resources corral worktrees still hold.",
        ),
        Option(
            "--dry-run",
            help="Print what would be released/stopped; change nothing",
            doc="Print the resources it would release and the session it would stop, without doing it.",
        ),
    ),
    examples=(
        Example("corral end", note="release resources, then stop the corral session (prompts)"),
        Example("corral end --force", note="no prompt"),
        Example("corral end --no-resources", note="stop the session but keep leases"),
        Example("corral end --dry-run", note="show what it would do"),
    ),
)


def _resource_holders(ctx: Context) -> List[str]:
    """Resource holders for every worktree under the worktrees dir."""
    holders = []
    for wt in gitutil.discover_worktrees(ctx.settings.worktrees_dir):
        holder = resources.holder_for_worktree(ctx.settings.worktrees_dir, wt)
        if holder:
            holders.append(holder)
    return holders


def _release_resources(ctx: Context) -> None:
    """Best-effort: return every corral worktree's checked-out shared resources
    to their pools. Reuses the same auto-release path as `corral close`, so it
    never raises and reports what came back."""
    for wt in gitutil.discover_worktrees(ctx.settings.worktrees_dir):
        hooks.release_resources(ctx.settings, wt)


def run(ctx: Context, args: Dict[str, object]) -> int:
    force = bool(args["force"])
    release = not args["no_resources"]
    dry_run = bool(args["dry_run"])

    # --dry-run only prints the plan; a real run needs herdr to stop the session.
    if not dry_run:
        require_deps("herdr")

    running = ctx.herdr.session_running(SESSION_NAME)

    if dry_run:
        if release:
            for holder in _resource_holders(ctx):
                ui.info(f"  corral resource release --all --as {holder}")
        note = "" if running else "   # (not currently running — would be a no-op)"
        ui.info(f"  herdr session stop {SESSION_NAME}{note}")
        return 0

    if running and not force:
        prompt = (
            f"Stop herdr session {ui.C.bold}{SESSION_NAME}{ui.C.reset} "
            "(kills every agent running in it)? [y/N] "
        )
        if not ui.confirm(prompt):
            ui.info("aborted")
            return 0

    # Release before stopping: the leases are keyed by worktree path (pure path
    # math), so this works whether or not the session is up, and clears them
    # even when there's no session left to stop.
    if release:
        _release_resources(ctx)

    if running:
        ctx.herdr.session_stop(SESSION_NAME)
        ui.ok(f"stopped herdr session '{SESSION_NAME}'")
    else:
        ui.info(f"herdr session '{SESSION_NAME}' is not running — nothing to stop")
    return 0
