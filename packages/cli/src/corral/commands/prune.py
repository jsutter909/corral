"""corral prune — remove finished/stale agent workspaces safely."""

from __future__ import annotations

from typing import Dict

from .. import gitutil, hooks, ui
from ..cli import Command, Example, Option
from ..herdr import require_deps
from . import Context, owned_workspaces

SPEC = Command(
    name="prune",
    aliases=("clean",),
    summary="remove agent workspaces whose work is done.",
    shell_alias="cpr",
    description=(
        "By default a workspace is prunable only when it is SAFE to delete:\n"
        "  * its worktree has no uncommitted changes, AND\n"
        "  * its branch is fully merged into the base branch.\n"
        "This guarantees prune never throws away unmerged or uncommitted work."
    ),
    doc=(
        "Remove agent workspaces whose work is done. A workspace is prunable **only**\n"
        "when it is safe to delete:\n"
        "\n"
        "- its worktree has **no uncommitted changes**, and\n"
        "- its branch is **fully merged** into the base branch.\n"
        "\n"
        "This guarantees prune never discards unmerged or uncommitted work.\n"
        "\n"
        "If a workspace's worktree contains a `.corral/cleanup.sh`, corral runs it there\n"
        "before removing the worktree; a workspace whose cleanup fails is skipped\n"
        "(worktree kept) unless `--force` is given."
    ),
    epilog=(
        "If a workspace's worktree contains a .corral/cleanup.sh, corral runs it\n"
        "there before removing the worktree. If cleanup fails, that workspace is\n"
        "skipped (worktree kept) unless --force is given."
    ),
    options=(
        Option(
            "--base",
            short="-b",
            metavar="<ref>",
            help='Branch to test "merged into" against',
            default_doc=(
                "the repo's origin/HEAD, else main, else master; if none of those "
                "exist the merged check is skipped entirely"
            ),
            doc=(
                'Branch to test "merged into" (default: `origin/HEAD`, else `main`, '
                "else `master`; if none exist the merged check is skipped rather "
                "than guessed)."
            ),
            completion="_corral_git_refs",
            value_hint="git ref",
        ),
        Option(
            "--idle",
            short="-i",
            help=(
                "Also prune idle workspaces with a clean tree\n"
                "(even if the branch is not merged — still requires a clean\n"
                "worktree; use with care)"
            ),
            doc=(
                "Also prune workspaces with a clean tree whose agent is idle, even "
                "if the branch isn't merged."
            ),
        ),
        Option(
            "--dry-run",
            short="-n",
            help="Show what would be pruned without removing anything",
            doc="Show what would be pruned; remove nothing.",
        ),
        Option(
            "--force",
            short="-f",
            help=(
                "Skip the per-workspace confirmation prompt; prune even if\n"
                ".corral/cleanup.sh fails (the script still runs)"
            ),
            doc=(
                "Skip the per-workspace confirmation, and prune even if a "
                "workspace's `.corral/cleanup.sh` fails."
            ),
        ),
        Option(
            "--no-cleanup",
            help="Do not run .corral/cleanup.sh (also: CORRAL_CLEANUP=0)",
            doc="Do not run `.corral/cleanup.sh` before removing worktrees.",
        ),
    ),
    examples=(
        Example("corral prune --dry-run"),
        Example("corral prune --base main --force"),
    ),
)


def _base_for(worktree: str, base: str) -> str:
    """The base ref to test merges against for a given worktree, or ''.

    '' means no base could be resolved — the caller MUST then skip the merged
    check (there is no ref that can safely stand in for one; in particular
    HEAD must never be used, since HEAD is its own ancestor and would make
    every branch look merged).
    """
    if base:
        return base
    ref = gitutil.origin_head(worktree)
    if ref:
        return ref
    for candidate in ("main", "master"):
        if gitutil.ref_exists(worktree, candidate):
            return candidate
    return ""


def run(ctx: Context, args: Dict[str, object]) -> int:
    base = str(args["base"])
    idle = bool(args["idle"])
    dry = bool(args["dry_run"])
    force = bool(args["force"])
    cleanup = ctx.settings.cleanup_enabled and not args["no_cleanup"]

    require_deps("herdr", "git")
    ctx.herdr.require_server()

    pruned = 0
    considered = 0
    for ws in owned_workspaces(ctx):
        wt = ws.owned_worktree_path(ctx.settings.worktrees_dir)
        considered += 1

        # Never touch a worktree with uncommitted changes.
        if gitutil.has_uncommitted_changes(wt):
            continue

        target = _base_for(wt, base)
        if target and gitutil.is_ancestor(wt, "HEAD", target):
            reason = f"merged into {target}"
        elif idle and ws.agent_status == "idle":
            reason = "idle, clean tree"
        else:
            continue

        if dry:
            ui.info(f"would prune {ws.id} ({ws.label}) — {reason}")
            pruned += 1
            continue

        if not force:
            prompt = f"Prune {ui.C.bold}{ws.id}{ui.C.reset} ({ws.label}) — {reason}? [y/N] "
            if not ui.confirm(prompt):
                continue

        if not hooks.remove_workspace(ctx.herdr, ws.id, wt, force=force, cleanup=cleanup):
            ui.warn(
                f"skipping {ws.id} ({ws.label}) — cleanup failed "
                "(--force to prune anyway, --no-cleanup to skip the script)"
            )
            continue
        ui.ok(f"pruned {ws.id} ({ws.label}) — {reason}")
        pruned += 1

    if pruned == 0:
        ui.info(f"nothing to prune ({considered} agent workspace(s) checked)")
    elif dry:
        ui.info(f"{pruned} of {considered} workspace(s) would be pruned")
    return 0
