"""corral open — open the configured IDE (VS Code or Cursor) in a worktree."""

from __future__ import annotations

import os
import platform
import shutil
import socket
import subprocess
from typing import Dict

from .. import ui
from ..agents import sh_quote
from ..cli import Argument, Command, Example, Option
from ..herdr import require_deps
from ..ides import IDES, find_ide, remote_uri
from ..ui import CorralError
from . import Context, resolve_ref_or_current

SPEC = Command(
    name="open",
    aliases=("ide",),
    summary="open your IDE in an agent workspace's worktree.",
    shell_alias="cop",
    description=(
        "corral resolves the workspace's worktree checkout path via herdr (it\n"
        "never guesses from the label), so the IDE always opens the exact folder\n"
        "the agent is working in. Any worktree-backed workspace can be opened,\n"
        "not just corral-created ones."
    ),
    epilog=(
        "When the herdr session is remote — you attached with 'herdr --remote',\n"
        "so corral runs on the server but your IDE runs on your local machine —\n"
        "corral can't launch the IDE from here. Instead it prints a\n"
        "<ide>://vscode-remote/… deep link (clickable in most terminals) plus\n"
        "the equivalent 'code --remote' command to run locally; both open the\n"
        "worktree over Remote-SSH. The link's host must match how YOUR machine\n"
        "reaches this one (a Host entry in your local ~/.ssh/config); set\n"
        "CORRAL_SSH_HOST or --host when the hostname isn't it."
    ),
    doc=(
        "Open your IDE in an agent workspace's worktree. With no argument, opens the\n"
        "worktree of the workspace you're currently in.\n"
        "\n"
        "corral asks herdr for the workspace's worktree checkout path (it never guesses\n"
        "from the label), so the IDE always opens the exact folder the agent is working\n"
        "in. Any worktree-backed workspace can be opened, not just corral-created ones.\n"
        "\n"
        "**Local herdr session** — the IDE runs on the same machine — corral launches it\n"
        "directly (`code <worktree>` / `cursor <worktree>`, falling back to\n"
        "`open -a` on macOS when the shell command isn't installed).\n"
        "\n"
        "**Remote herdr session** (`herdr --remote`) — corral runs on the server but\n"
        "your IDE runs on your local machine, so it can't be launched from the server.\n"
        "corral detects this (an SSH environment or an attached `herdr --remote` client\n"
        "bridge) and instead prints a `vscode://vscode-remote/ssh-remote+<host><path>`\n"
        "deep link — clickable in most terminals — plus the equivalent\n"
        "`code --remote ssh-remote+<host> <path>` command to run locally. Both open the\n"
        "worktree over the IDE's Remote-SSH support. The `<host>` must be how **your**\n"
        "machine reaches the server (a `Host` entry in your local `~/.ssh/config`); when\n"
        "the server's hostname isn't that, set `CORRAL_SSH_HOST` or pass `--host`.\n"
        "Use `--ssh`/`--no-ssh` when the auto-detection guesses wrong."
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
            "--ide",
            short="-i",
            metavar="<name>",
            setting="ide",
            help="IDE to open: " + " or ".join(ide.name for ide in IDES),
            doc=(
                "IDE to open: "
                + " or ".join(f"`{ide.name}`" for ide in IDES)
                + " (config: `CORRAL_IDE`)."
            ),
            choices=tuple(ide.name for ide in IDES),
            value_hint="ide",
        ),
        Option(
            "--ssh",
            help=(
                "Force Remote-SSH mode (print a link that opens the IDE on\n"
                "your local machine over SSH)"
            ),
            doc="Force Remote-SSH mode.",
            default_doc="auto",
            excludes=("--no-ssh",),
        ),
        Option(
            "--no-ssh",
            help="Force local mode (launch the IDE on this machine)",
            doc="Force local mode.",
            default_doc="auto",
            excludes=("--ssh",),
        ),
        Option(
            "--host",
            metavar="<host>",
            setting="ssh_host",
            help="SSH host to use in the Remote-SSH link",
            doc=(
                "SSH host used in the Remote-SSH link (config: `CORRAL_SSH_HOST`)."
            ),
            completion="_hosts",
            value_hint="host",
        ),
    ),
    examples=(
        Example("corral open", note="open the worktree you're in"),
        Example("corral open checkout-fix", note="open by label"),
        Example("corral open w4 --ide cursor"),
        Example("corral open w4 --host devbox", note='remote link via ssh host alias "devbox"'),
    ),
)


def session_is_remote() -> bool:
    """Is this herdr session remote (IDE UI not on this machine)?

    True when corral itself runs over SSH, or when a 'herdr --remote' client
    bridge is attached to the local server. Overridable with --ssh/--no-ssh.
    """
    if os.environ.get("SSH_CONNECTION") or os.environ.get("SSH_CLIENT") or os.environ.get("SSH_TTY"):
        return True
    try:
        proc = subprocess.run(
            ["pgrep", "-f", "herdr remote-client-bridge"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return proc.returncode == 0
    except OSError:
        return False


def run(ctx: Context, args: Dict[str, object]) -> int:
    ref = str(args["workspace"])
    ide_name = str(args["ide"])
    host = str(args["host"])
    if args["ssh"] and args["no_ssh"]:
        raise CorralError("--ssh and --no-ssh are mutually exclusive")
    mode = "ssh" if args["ssh"] else "local" if args["no_ssh"] else "auto"

    ide = find_ide(ide_name)
    if ide is None:
        names = " or ".join(i.name for i in IDES)
        raise CorralError(
            f"unknown IDE '{ide_name}' — use {names} (CORRAL_IDE or --ide)"
        )

    require_deps("herdr")
    ctx.herdr.require_server()

    ws_id = resolve_ref_or_current(ctx, ref, example="corral open w4")
    ws = ctx.herdr.workspace_get(ws_id)

    # Any worktree-backed workspace may be opened (unlike close, this is
    # harmless), but the path must come from herdr — never guessed — so the
    # IDE opens the exact checkout the agent works in.
    wt = ws.worktree.checkout_path if ws.worktree else ""
    if not wt:
        raise CorralError(f"workspace {ws.id} ({ws.label}) has no git worktree attached")
    if not os.path.isdir(wt):
        raise CorralError(f"worktree path {wt} no longer exists")

    if mode == "auto":
        mode = "ssh" if session_is_remote() else "local"

    if mode == "local":
        if shutil.which(ide.cli):
            proc = subprocess.run([ide.cli, wt])
            if proc.returncode != 0:
                raise CorralError(f"'{ide.cli} {wt}' failed")
        elif platform.system() == "Darwin" and shutil.which("open"):
            proc = subprocess.run(["open", "-a", ide.app, wt])
            if proc.returncode != 0:
                raise CorralError(f"could not open {ide.app}")
        else:
            raise CorralError(
                f"the '{ide.cli}' command is not on PATH — install the {ide.app} "
                "shell command, or use --ssh for a Remote-SSH link"
            )
        ui.ok(f"opened {wt} in {ide.app}")
        return 0

    # Remote: corral runs on the herdr server; the IDE runs on the user's
    # machine, so it can't be launched from here. Print a deep link (stdout,
    # clickable in most terminals) and the CLI equivalent to run locally.
    if not host:
        host = socket.gethostname()
    ui.info(f"herdr session is remote — open this worktree from your machine ({ide.app} over SSH):")
    print(remote_uri(ide, host, wt))
    ui.info(f"or run locally:  {ide.cli} --remote ssh-remote+{host} {sh_quote(wt)}")
    ui.info(
        f"(host '{host}' must match a Host entry in your local ~/.ssh/config — "
        "set CORRAL_SSH_HOST or --host if not)"
    )
    return 0
