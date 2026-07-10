"""corral close — tear down an agent workspace (remove worktree + close it)."""

from __future__ import annotations

from typing import Dict

from .. import hooks, ui
from ..cli import Argument, Command, Example, Option
from ..herdr import require_deps
from ..ui import CorralError
from . import Context, resolve_ref_or_current

SPEC = Command(
    name="close",
    summary="remove an agent's git worktree and close its workspace.",
    shell_alias="ccl",
    description=(
        "If the worktree contains a .corral/cleanup.sh, corral runs it there\n"
        "before removing the worktree. If cleanup fails, close aborts and leaves\n"
        "the worktree intact; --force removes it anyway (re-running the script),\n"
        "--no-cleanup removes it without running the script at all.\n"
        "\n"
        "Guard: corral refuses to close a workspace that is not a corral-managed\n"
        "worktree, so it can never destroy your command/control workspace, a\n"
        "primary repo checkout, or a worktree you made by hand."
    ),
    doc=(
        "Remove an agent's git worktree and close its workspace. With no argument,\n"
        "closes the workspace you're currently in. Prompts unless `--force`.\n"
        "\n"
        "corral refuses to close anything that isn't a corral-created worktree (a linked\n"
        "worktree under `~/.herdr/worktrees/…`), so it can't destroy your command\n"
        "workspace, a primary repo checkout, or a worktree you made by hand.\n"
        "\n"
        "If the worktree contains a `.corral/cleanup.sh`, corral runs it there before\n"
        "removing it. If cleanup fails, close aborts and leaves the worktree intact;\n"
        "`--force` removes it anyway (re-running the script) and `--no-cleanup` skips\n"
        "the script entirely. See\n"
        "[per-repo configuration](configuration.md#per-repo-configuration-corral)."
    ),
    arguments=(
        Argument(
            "workspace",
            required=False,
            help=(
                "Workspace id (w4) or label (checkout-fix).\n"
                "Defaults to the workspace you're currently in"
            ),
            doc=(
                "Workspace id (`w4`) or label (`checkout-fix`). Defaults to the "
                "workspace you're currently in."
            ),
            completion="_corral_workspaces",
        ),
    ),
    options=(
        Option(
            "--force",
            short="-f",
            help=(
                "Skip the confirmation prompt; close even if .corral/cleanup.sh fails\n"
                "(the script still runs)"
            ),
            doc=(
                "Skip the confirmation prompt, and close even if the worktree's "
                "`.corral/cleanup.sh` fails (the script still runs)."
            ),
        ),
        Option(
            "--no-cleanup",
            help="Do not run .corral/cleanup.sh (also: CORRAL_CLEANUP=0)",
            doc="Do not run `.corral/cleanup.sh` (also: `CORRAL_CLEANUP=0`).",
        ),
    ),
    examples=(
        Example("corral close", note="close the workspace you're in (prompts)"),
        Example("corral close checkout-fix", note="close by label"),
        Example("corral close w4 --force"),
    ),
)


def run(ctx: Context, args: Dict[str, object]) -> int:
    ref = str(args["workspace"])
    force = bool(args["force"])
    cleanup = ctx.settings.cleanup_enabled and not args["no_cleanup"]

    require_deps("herdr")
    ctx.herdr.require_server()

    ws_id = resolve_ref_or_current(ctx, ref, example="corral close w4")
    ws = ctx.herdr.workspace_get(ws_id)
    wt = ws.owned_worktree_path(ctx.settings.worktrees_dir)

    # Guard: only corral-owned worktree workspaces may be destroyed.
    if not wt:
        raise CorralError(
            f"workspace {ws.id} ({ws.label}) is not a corral-managed worktree "
            "workspace — refusing to close it"
        )

    if not force:
        prompt = (
            f"Remove worktree and close workspace {ui.C.bold}{ws.id}{ui.C.reset} "
            f"({ws.label})?\n  {wt}\n[y/N] "
        )
        if not ui.confirm(prompt):
            ui.info("aborted")
            return 0

    if not hooks.remove_workspace(
        ctx.herdr, ws.id, wt, force=force, cleanup=cleanup, settings=ctx.settings
    ):
        raise CorralError(
            f"cleanup failed for {ws.id} ({ws.label}) — worktree left intact "
            "(--force to remove anyway, --no-cleanup to skip the script)"
        )
    ui.ok(f"removed worktree and closed workspace {ws.id} ({ws.label})")
    return 0
