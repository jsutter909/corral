"""corral focus — jump focus to an agent workspace by id or label."""

from __future__ import annotations

from typing import Dict

from .. import ui
from ..cli import Argument, Command, Example
from ..herdr import require_deps
from ..ui import CorralError
from ..workspaces import resolve_workspace
from . import Context

SPEC = Command(
    name="focus",
    aliases=("attach",),
    summary="switch focus to an agent workspace.",
    shell_alias="cfo",
    doc="Switch focus to an agent workspace by id (`w4`) or label (`checkout-fix`).",
    arguments=(
        Argument(
            "workspace",
            help="Workspace id (w4) or label (checkout-fix)",
            doc="Workspace id (`w4`) or label (`checkout-fix`).",
            completion="_corral_workspaces",
        ),
    ),
    examples=(Example("corral focus checkout-fix"),),
)


def run(ctx: Context, args: Dict[str, object]) -> int:
    ref = str(args["workspace"])
    if not ref:
        raise CorralError("missing <workspace> argument (try 'corral focus --help')")

    require_deps("herdr")
    ctx.herdr.require_server()

    ws = resolve_workspace(ref, ctx.herdr.workspace_list())
    ctx.herdr.workspace_focus(ws.id)
    ui.ok(f"focused workspace {ws.id}")
    return 0
