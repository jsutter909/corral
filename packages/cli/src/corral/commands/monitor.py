"""corral monitor — a local web dashboard for the agent fleet."""

from __future__ import annotations

from typing import Dict

from ..cli import Command, Example, Option
from ..herdr import require_deps
from ..ui import CorralError
from . import Context

SPEC = Command(
    name="monitor",
    aliases=("ui",),
    summary="serve a local web UI to monitor and manage agent workspaces.",
    shell_alias="cmon",
    description=(
        "Opens a small web dashboard (no dependencies — pure stdlib) that lists\n"
        "every corral-owned workspace, the resources each one holds, and every\n"
        "resource pool, refreshing itself as agents come and go. From the page\n"
        "you can spawn a new agent, focus one, close one, and release a held\n"
        "resource — the same operations as the CLI, wired to the same commands.\n"
        "\n"
        "Binds to loopback by default, so the dashboard is reachable only from\n"
        "this machine; set --host 0.0.0.0 (or CORRAL_MONITOR_HOST) to expose it."
    ),
    doc=(
        "Serve a local web dashboard for the agent fleet. It lists every corral-owned\n"
        "workspace joined to the resources it currently holds, plus every resource pool,\n"
        "and refreshes itself as things change. Buttons on the page spawn, focus, and\n"
        "close agents and release held resource items — each routed through the same\n"
        "command the CLI runs, so the web UI and the terminal share one implementation.\n"
        "\n"
        "The server is stdlib-only (no extra install) and binds to `127.0.0.1` by\n"
        "default — reachable only from this machine. Set `--host 0.0.0.0` (or\n"
        "`CORRAL_MONITOR_HOST`) to expose it on your network. Runs until interrupted\n"
        "with Ctrl-C."
    ),
    options=(
        Option(
            "--port",
            short="-p",
            metavar="<port>",
            setting="monitor_port",
            help="Port to serve the web UI on",
            doc="TCP port to serve the web UI on.",
            value_hint="port",
        ),
        Option(
            "--host",
            metavar="<addr>",
            setting="monitor_host",
            help="Address to bind to (127.0.0.1 = local only; 0.0.0.0 = network)",
            doc="Address to bind to (`127.0.0.1` = local only; `0.0.0.0` = exposed).",
            value_hint="address",
        ),
    ),
    examples=(
        Example("corral monitor", note="http://127.0.0.1:8477"),
        Example("corral monitor --port 9000"),
        Example("corral monitor --host 0.0.0.0", note="reachable on your network"),
    ),
)


def run(ctx: Context, args: Dict[str, object]) -> int:
    from .. import monitor  # lazy: pulls in http.server only when actually serving

    host = str(args["host"])
    port_raw = str(args["port"])
    try:
        port = int(port_raw)
    except ValueError:
        raise CorralError(f"--port must be a number (got '{port_raw}')") from None
    if not 1 <= port <= 65535:
        raise CorralError(f"--port must be between 1 and 65535 (got {port})")

    require_deps("herdr", "git")
    ctx.herdr.require_server()

    monitor.serve(ctx, host, port)
    return 0
