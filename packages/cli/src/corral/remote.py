"""SSH plumbing for ``corral start --remote``.

The command *builders* here are pure — they return argv lists / shell strings
and touch nothing — so the remote bootstrap can be unit-tested without a box to
ssh into. The *runners* wrap them in :mod:`subprocess`, are best-effort (they
warn rather than abort, matching what the user opted into), and honor
``dry_run`` by printing the command instead of executing it.
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
from typing import Dict, List, Optional

from . import ui

# SSH keepalives so a dropped connection (laptop sleep, network change) is
# noticed within ~45s instead of hanging, and the forward fails loudly rather
# than silently binding nothing.
KEEPALIVE_OPTS = [
    "-o", "ServerAliveInterval=15",
    "-o", "ServerAliveCountMax=3",
    "-o", "ExitOnForwardFailure=yes",
]

# The one-liner documented in install.sh / README, run over ssh when the remote
# has no corral yet. `command -v` short-circuits so an existing install is left
# alone. `|` binds tighter than `||`, so this is `check || (curl | bash)`.
INSTALL_URL = "https://raw.githubusercontent.com/jsutter909/corral/main/install.sh"

# Where the copied config lands on the remote (its login-shell $HOME). Matches
# corral's own default config location.
REMOTE_CONFIG_DIR = "$HOME/.config/corral"
REMOTE_CONFIG_PATH = "$HOME/.config/corral/config.sh"

# What corral runs on the remote to bring up its server + monitor without
# attaching a client there. --no-attach never recurses into remote prep, and
# the copied config has CORRAL_REMOTE stripped, so this resolves to a local seed.
SEED_ARGS = ("corral", "start", "--no-attach")

_REMOTE_ASSIGNMENT = re.compile(r"^\s*(?:export\s+)?CORRAL_REMOTE=")


# ---------------------------------------------------------------------------
# Pure command builders
# ---------------------------------------------------------------------------


def ssh_args(target: str, *cmd: str) -> List[str]:
    """`ssh <target> <cmd...>` as an argv list."""
    return ["ssh", target, *cmd]


def login_shell(target: str, script: str) -> List[str]:
    """Run `script` on the remote through a login shell, so ~/.local/bin (where
    install.sh puts corral/herdr) is on PATH."""
    return ssh_args(target, "bash", "-lc", script)


def install_command() -> str:
    """Shell script: install corral on the remote only if it isn't already."""
    return f"command -v corral >/dev/null 2>&1 || curl -fsSL {INSTALL_URL} | bash"


def copy_config_command(remote_path: str = REMOTE_CONFIG_PATH) -> str:
    """Shell script: create the config dir and write stdin to `remote_path`."""
    return f'mkdir -p "{REMOTE_CONFIG_DIR}" && cat > "{remote_path}"'


def seed_command() -> str:
    """Shell script that seeds the remote server + monitor (no client attach)."""
    return " ".join(SEED_ARGS)


def forward_args(target: str, port: int, use_autossh: bool = False) -> List[str]:
    """Background-forward the monitor port so the remote dashboard is reachable
    at localhost:<port>.

    With autossh (`use_autossh`) the tunnel auto-reconnects across network drops
    and laptop sleep; `-M 0` tells autossh to lean on the ssh keepalives above
    for liveness rather than its own monitoring port. Plain ssh is the fallback
    when autossh isn't installed (keepalives only — no auto-reconnect)."""
    spec = f"{port}:127.0.0.1:{port}"
    if use_autossh:
        return ["autossh", "-M", "0", "-f", "-N", *KEEPALIVE_OPTS, "-L", spec, target]
    return ["ssh", "-f", "-N", *KEEPALIVE_OPTS, "-L", spec, target]


def filter_config(text: str) -> str:
    """Drop any CORRAL_REMOTE assignment from a config before copying it to the
    remote — the remote is the endpoint and must not point at a further host."""
    kept = [line for line in text.splitlines() if not _REMOTE_ASSIGNMENT.match(line)]
    result = "\n".join(kept)
    if text.endswith("\n") and result:
        result += "\n"
    return result


# ---------------------------------------------------------------------------
# Runners (best-effort; honor dry_run)
# ---------------------------------------------------------------------------


def _show(argv: List[str], note: str = "") -> None:
    suffix = f"  # {note}" if note else ""
    ui.info(f"  {' '.join(shlex.quote(a) for a in argv)}{suffix}")


def install_remote(target: str, dry_run: bool = False) -> bool:
    """Install corral on the remote if missing. Warns (returns False) on failure."""
    argv = login_shell(target, install_command())
    if dry_run:
        _show(argv, "install corral if missing")
        return True
    if not _run(argv):
        ui.warn("could not install corral on the remote (install it there by hand)")
        return False
    return True


def copy_config_remote(target: str, config_text: str, dry_run: bool = False) -> bool:
    """Copy the (CORRAL_REMOTE-stripped) local config to the remote."""
    argv = login_shell(target, copy_config_command())
    if dry_run:
        _show(argv, f"copy config to {REMOTE_CONFIG_PATH} (CORRAL_REMOTE stripped)")
        return True
    if not _run(argv, input_text=filter_config(config_text)):
        ui.warn("could not copy config to the remote")
        return False
    return True


def seed_monitor_remote(target: str, dry_run: bool = False) -> bool:
    """Bring up the remote herdr server + monitor pane (no client attach)."""
    argv = login_shell(target, seed_command())
    if dry_run:
        _show(argv, "start remote server + monitor")
        return True
    if not _run(argv):
        ui.warn("could not start the monitor on the remote")
        return False
    return True


def forward_port(target: str, port: int, dry_run: bool = False) -> bool:
    """Background-forward the monitor port from the remote to localhost, with
    auto-reconnect via autossh when it's installed."""
    use_autossh = shutil.which("autossh") is not None
    argv = forward_args(target, port, use_autossh)
    how = "auto-reconnect via autossh" if use_autossh else "ssh keepalive, no auto-reconnect"
    if dry_run:
        _show(argv, f"forward monitor port -> http://localhost:{port} ({how})")
        return True
    # AUTOSSH_GATETIME=0 lets autossh keep retrying even if the first connection
    # fails fast — the seamless-across-sleep behavior we want.
    env = dict(os.environ, AUTOSSH_GATETIME="0") if use_autossh else None
    if not _run(argv, env=env):
        ui.warn(
            f"could not forward the monitor port (is localhost:{port} already forwarded?)"
        )
        return False
    if not use_autossh:
        ui.info(
            "  install 'autossh' for a monitor forward that auto-reconnects "
            "after sleep/roaming"
        )
    return True


def _run(argv: List[str], input_text: Optional[str] = None, env: Optional[Dict[str, str]] = None) -> bool:
    """Run argv, streaming its stderr through; True on exit 0."""
    try:
        proc = subprocess.run(argv, input=input_text, text=True, env=env)
    except OSError:
        return False
    return proc.returncode == 0
