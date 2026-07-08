"""corral ls — list active agent (corral-owned worktree) workspaces."""

from __future__ import annotations

import json
import sys
from typing import Dict, List

from .. import gitutil, ui
from ..cli import Command, Example, Option
from ..herdr import require_deps
from ..ui import CorralError
from . import Context, owned_workspaces

# Column order for --json objects, --tsv rows, and (minus repo) the table.
COLUMNS = ("workspace", "label", "repo", "branch", "status", "worktree")

SPEC = Command(
    name="ls",
    aliases=("list",),
    summary="list active agent workspaces.",
    shell_alias="cls",
    description=(
        "Shows every corral-owned workspace: its id, label, git branch, agent\n"
        "status, and worktree path (your primary checkouts and hand-made\n"
        "worktrees are never listed). Table rows go to stdout (the header goes\n"
        "to stderr), so `corral ls | grep …`, --json, and --tsv are all\n"
        "scriptable."
    ),
    doc=(
        "List active agent workspaces (corral-owned worktrees only — your primary\n"
        "checkouts and hand-made worktrees are never listed). Columns: workspace id,\n"
        "label, git branch, agent status, worktree path. Data rows go to stdout and the\n"
        "header to stderr, so plain `corral ls` pipes cleanly; `--json` emits an array\n"
        "and `--tsv` tab-separated rows for scripting (the oh-my-zsh plugin is built on\n"
        "`--tsv`)."
    ),
    options=(
        Option(
            "--json",
            short="-j",
            help="Emit machine-readable JSON instead of a table",
            doc="Emit a JSON array instead of a table.",
            excludes=("--tsv",),
        ),
        Option(
            "--tsv",
            help="Emit tab-separated rows (workspace, label, repo, branch, status, worktree)",
            doc=(
                "Emit one tab-separated row per workspace — the format the "
                "oh-my-zsh plugin consumes. Columns: "
                + ", ".join(COLUMNS)
                + "."
            ),
            excludes=("--json",),
        ),
    ),
    examples=(
        Example("corral ls"),
        Example("corral ls | awk '{print $1}'"),
        Example("corral ls --json | python3 -c 'import json,sys; print(len(json.load(sys.stdin)))'"),
    ),
)


def rows(ctx: Context) -> List[Dict[str, str]]:
    """One dict per corral-owned workspace, with its live git branch."""
    result = []
    for ws in owned_workspaces(ctx):
        wt = ws.owned_worktree_path(ctx.settings.worktrees_dir)
        result.append(
            {
                "workspace": ws.id,
                "label": ws.label,
                "repo": ws.worktree.repo_name if ws.worktree else "?",
                "branch": gitutil.current_branch(wt),
                "status": ws.agent_status,
                "worktree": wt,
            }
        )
    return result


def run(ctx: Context, args: Dict[str, object]) -> int:
    if args["json"] and args["tsv"]:
        raise CorralError("--json and --tsv are mutually exclusive")

    require_deps("herdr", "git")
    ctx.herdr.require_server()

    listing = rows(ctx)

    if args["json"]:
        print(json.dumps(listing, indent=1 if listing else None))
        return 0
    if args["tsv"]:
        for row in listing:
            print("\t".join(row[col] for col in COLUMNS))
        return 0

    if not listing:
        ui.info("no active agent workspaces (spawn one with 'corral spawn <repo>')")
        return 0

    # Header on stderr so piped stdout carries only data rows.
    header = f"{'WORKSPACE':<10} {'LABEL':<20} {'BRANCH':<30} {'STATUS':<9} WORKTREE"
    print(f"{ui.C.bold}{header}{ui.C.reset}", file=sys.stderr)
    for row in listing:
        print(
            f"{row['workspace']:<10} {row['label']:<20} {row['branch']:<30} "
            f"{row['status']:<9} {row['worktree']}"
        )
    return 0
