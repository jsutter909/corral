"""corral start — bring up a herdr session (local or remote) with the monitor."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict

from .. import remote, ui
from ..agents import sh_quote
from ..cli import Command, Example, Option
from ..herdr import require_deps
from ..ui import CorralError
from . import Context

# The workspace corral parks `corral monitor` in. Reused across runs so `start`
# is idempotent — a second start won't stack a second monitor.
MONITOR_LABEL = "monitor"

SPEC = Command(
    name="start",
    summary="start a herdr session (local or remote) with the monitor running.",
    shell_alias="cst",
    description=(
        "One command to bring up a herdr session and land you in it. corral makes\n"
        "sure a herdr server is running, parks 'corral monitor' in its own\n"
        "workspace so the dashboard is always up, then attaches the herdr TUI\n"
        "(this process is replaced by herdr).\n"
        "\n"
        "With a remote target — from --remote or CORRAL_REMOTE, same syntax as\n"
        "'herdr --remote' — corral first bootstraps the other machine over SSH:\n"
        "installs corral there if missing, copies this config across (minus\n"
        "CORRAL_REMOTE), starts the monitor on the remote, and forwards its port\n"
        "back with 'ssh -L' so the dashboard is reachable at http://localhost:<port>\n"
        "here. Then it attaches with 'herdr --remote <target>'."
    ),
    doc=(
        "Bring up a herdr session and drop you into it, with `corral monitor` already\n"
        "running in its own `monitor` workspace (idempotent — a second `start` reuses\n"
        "it). corral starts a herdr server if one isn't reachable, then replaces itself\n"
        "with the herdr client (`exec herdr`).\n"
        "\n"
        "**Local** (no target) — server + monitor here, then `herdr`.\n"
        "\n"
        "**Remote** (`--remote <target>` or `CORRAL_REMOTE`, same syntax as\n"
        "`herdr --remote`) — corral bootstraps the target over SSH first:\n"
        "\n"
        "1. installs corral there if it's missing (the `install.sh` one-liner);\n"
        "2. copies this machine's config across, with `CORRAL_REMOTE` stripped so the\n"
        "   remote doesn't point at a further host;\n"
        "3. starts the herdr server + monitor on the remote (`corral start --no-attach`);\n"
        "4. forwards the monitor port back with `ssh -L`, so the dashboard is reachable\n"
        "   at `http://localhost:<port>` locally;\n"
        "5. attaches with `herdr --remote <target>`.\n"
        "\n"
        "Each step past the attach has a `--no-*` opt-out. `--no-attach` does the setup\n"
        "for **this** machine and stops before attaching (it's also how corral seeds the\n"
        "remote). `--dry-run` prints every command it would run — install, copy, seed,\n"
        "forward, attach — without touching anything, which is the safe way to inspect\n"
        "the remote path."
    ),
    epilog=(
        "The 'ssh -L' port forward daemonizes itself and keeps running after herdr\n"
        "exits; kill it by hand (e.g. pkill -f 'ssh -L <port>') when you're done."
    ),
    options=(
        Option(
            "--remote",
            short="-r",
            metavar="<target>",
            setting="remote",
            help="SSH target to attach to (same as herdr --remote); empty = local",
            doc="SSH target to attach to (same syntax as `herdr --remote`).",
            completion="_hosts",
            value_hint="ssh target",
        ),
        Option(
            "--no-attach",
            help=(
                "Set up this machine's server + monitor, but don't attach the TUI\n"
                "(never does remote bootstrapping)"
            ),
            doc="Set up this machine's server + monitor without attaching the herdr client.",
        ),
        Option(
            "--no-monitor",
            help="Don't start corral monitor",
            doc="Skip starting `corral monitor`.",
        ),
        Option(
            "--no-install",
            help="Remote: don't try to install corral on the target",
            doc="Remote only: skip installing corral on the target.",
        ),
        Option(
            "--no-config-copy",
            help="Remote: don't copy this config to the target",
            doc="Remote only: skip copying this machine's config to the target.",
        ),
        Option(
            "--no-forward",
            help="Remote: don't forward the monitor port with ssh -L",
            doc="Remote only: skip the `ssh -L` monitor-port forward.",
        ),
        Option(
            "--dry-run",
            help="Print the commands that would run; change nothing",
            doc="Print every command `start` would run (including the attach) without executing.",
        ),
    ),
    examples=(
        Example("corral start", note="local herdr + monitor, then attach"),
        Example("corral start --remote devbox", note="bootstrap + attach devbox over SSH"),
        Example("corral start --no-attach", note="just bring up the server + monitor"),
        Example("corral start --remote devbox --dry-run", note="show what it would do"),
    ),
)


def _monitor_port(ctx: Context) -> int:
    raw = str(ctx.settings.monitor_port)
    try:
        port = int(raw)
    except ValueError:
        raise CorralError(f"CORRAL_MONITOR_PORT must be a number (got '{raw}')") from None
    if not 1 <= port <= 65535:
        raise CorralError(f"CORRAL_MONITOR_PORT must be between 1 and 65535 (got {port})")
    return port


def _attach(*herdr_args: str) -> None:
    """Replace this process with the herdr client (does not return)."""
    os.execvp("herdr", ["herdr", *herdr_args])


def _seed_monitor(ctx: Context, dry_run: bool) -> None:
    """Ensure `corral monitor` is running in its own workspace on this machine."""
    host = str(ctx.settings.monitor_host)
    port = _monitor_port(ctx)
    launch = f"corral monitor --host {sh_quote(host)} --port {sh_quote(str(port))}"
    if dry_run:
        ui.info(f"  herdr workspace create --label {MONITOR_LABEL}")
        ui.info(f"  herdr pane run <root> {launch}")
        return
    if ctx.herdr.has_workspace_label(MONITOR_LABEL):
        ui.info(f"monitor already running (workspace '{MONITOR_LABEL}')")
        return
    _ws, pane = ctx.herdr.workspace_create(MONITOR_LABEL)
    ctx.herdr.pane_run(pane, launch)
    ui.ok(f"monitor on {ui.C.bold}http://{host}:{port}{ui.C.reset} (workspace '{MONITOR_LABEL}')")


def _ensure_server(ctx: Context, dry_run: bool) -> None:
    if dry_run:
        ui.info("  herdr server  # only if one isn't already running")
        return
    ctx.herdr.start_server_detached()


def _seed_local(ctx: Context, no_monitor: bool, dry_run: bool) -> None:
    _ensure_server(ctx, dry_run)
    if not no_monitor:
        _seed_monitor(ctx, dry_run)


def _start_local(ctx: Context, no_monitor: bool, dry_run: bool) -> int:
    _seed_local(ctx, no_monitor, dry_run)
    if dry_run:
        ui.info("  exec herdr")
        return 0
    ui.info("attaching herdr session…")
    _attach()
    return 0  # unreachable after exec


def _start_remote(
    ctx: Context,
    target: str,
    no_monitor: bool,
    no_install: bool,
    no_config_copy: bool,
    no_forward: bool,
    dry_run: bool,
) -> int:
    ui.info(f"bootstrapping remote herdr session on {ui.C.bold}{target}{ui.C.reset}…")

    if not no_install:
        remote.install_remote(target, dry_run)

    if not no_config_copy:
        config_path = str(ctx.settings.config_path)
        if os.path.isfile(config_path):
            try:
                text = Path(config_path).read_text(encoding="utf-8")
            except OSError:
                text = ""
                ui.warn(f"could not read local config {config_path}; skipping copy")
            if text:
                remote.copy_config_remote(target, text, dry_run)
        else:
            ui.info(f"  no local config at {config_path} — nothing to copy")

    if not no_monitor:
        remote.seed_monitor_remote(target, dry_run)

    if not no_forward:
        remote.forward_port(target, _monitor_port(ctx), dry_run)

    if dry_run:
        ui.info(f"  exec herdr --remote {target}")
        return 0
    ui.info(f"attaching herdr --remote {target}…")
    _attach("--remote", target)
    return 0  # unreachable after exec


def run(ctx: Context, args: Dict[str, object]) -> int:
    target = str(args["remote"]).strip()
    no_attach = bool(args["no_attach"])
    no_monitor = bool(args["no_monitor"])
    no_install = bool(args["no_install"])
    no_config_copy = bool(args["no_config_copy"])
    no_forward = bool(args["no_forward"])
    dry_run = bool(args["dry_run"])

    # --dry-run only prints the plan, so it needs nothing installed; a real run
    # will exec herdr, so require it (and git, matching the other commands).
    if not dry_run:
        require_deps("herdr", "git")

    # --no-attach only ever sets up THIS machine (never remote bootstrapping),
    # so the copied-config-with-CORRAL_REMOTE-stripped invocation corral runs on
    # the remote can't recurse back out over SSH.
    if no_attach:
        _seed_local(ctx, no_monitor, dry_run)
        return 0

    if not target:
        return _start_local(ctx, no_monitor, dry_run)
    return _start_remote(
        ctx, target, no_monitor, no_install, no_config_copy, no_forward, dry_run
    )
