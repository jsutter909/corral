"""corral doctor — check corral's dependencies and update to the latest main."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from typing import Dict

from .. import __version__, gitutil, ui
from ..cli import Command, Example, Option
from ..paths import REPO_ROOT
from ..ui import CorralError
from . import Context

RUNTIME_DEPS = ("herdr", "git")

SPEC = Command(
    name="doctor",
    summary="check that corral is healthy and up to date.",
    shell_alias="cdoc",
    description=(
        "Verifies the runtime dependencies (herdr, git) are installed, reports\n"
        "on the herdr server and config file, then fast-forwards the corral\n"
        "installation to the latest main from its origin remote.\n"
        "\n"
        "The update step only ever fast-forwards a clean checkout that is on\n"
        "main; a dev checkout (other branch, or local changes) is left alone\n"
        "with a note."
    ),
    doc=(
        "Check that corral is healthy and up to date:\n"
        "\n"
        "1. **Dependencies** — verifies `herdr` and `git` are on `PATH` (each is\n"
        "   reported individually, with its version and location).\n"
        "2. **Environment** — reports the Python in use, whether the herdr server is\n"
        "   reachable, and whether a config file exists. Informational only; never\n"
        "   fails the doctor.\n"
        "3. **Update** — fast-forwards the corral installation to the latest `main`\n"
        "   from its origin remote and reports the new version.\n"
        "\n"
        "The update step refuses to touch anything that isn't a clean checkout on\n"
        "`main` — a dev checkout on a feature branch, with local changes, or with a\n"
        "diverged history is left alone with a note. A non-git install (no `.git`) gets\n"
        "a pointer to the `install.sh` one-liner instead.\n"
        "\n"
        "Exits `0` when every required dependency is present and the update succeeded\n"
        "(or was safely skipped), `1` otherwise."
    ),
    epilog=(
        "Exit status: 0 when every required dependency is present and the update\n"
        "step succeeded (or was safely skipped), 1 otherwise."
    ),
    options=(
        Option(
            "--no-update",
            help="Run the checks only; never touch the installation",
            doc="Run the checks only; never touch the installation.",
        ),
    ),
    examples=(
        Example("corral doctor"),
        Example("corral doctor --no-update"),
    ),
)


def _version_of(dep: str) -> str:
    """First line of `<dep> --version`, or '' — purely cosmetic."""
    try:
        proc = subprocess.run(
            [dep, "--version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except OSError:
        return ""
    lines = (proc.stdout or "").splitlines()
    return lines[0] if lines else ""


def _installed_version(root: str) -> str:
    """Version string of the checkout at `root` as it exists on disk (after a
    pull this differs from the one this process imported)."""
    init = os.path.join(root, "packages", "cli", "src", "corral", "__init__.py")
    try:
        with open(init, encoding="utf-8") as fh:
            match = re.search(r'^__version__ = "([^"]+)"', fh.read(), re.MULTILINE)
    except OSError:
        return ""
    return match.group(1) if match else ""


def _git(root: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", root, *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )


def _update(root: str) -> bool:
    """Fast-forward the corral checkout at `root` to origin/main.

    Prints its findings; returns False only on a real failure (fetch/pull
    error), True when up to date, updated, or safely skipped.
    """
    if _git(root, "rev-parse", "--git-dir").returncode != 0:
        ui.warn(f"install at {root} is not a git checkout — cannot self-update")
        ui.info(
            "  reinstall with: curl -fsSL "
            "https://raw.githubusercontent.com/jsutter909/corral/main/install.sh | bash"
        )
        return True

    branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() or "?"
    if branch != "main":
        ui.warn(f"skipping update: checkout is on '{branch}', not main (dev checkout?)")
        return True
    status = _git(root, "status", "--porcelain")
    if status.stdout.strip():
        ui.warn(f"skipping update: checkout at {root} has local changes")
        return True

    ui.info("fetching origin main")
    if _git(root, "fetch", "--quiet", "origin", "main").returncode != 0:
        ui.warn("could not fetch origin main (offline? no remote?)")
        return False

    short_head = _git(root, "rev-parse", "--short", "HEAD").stdout.strip()
    if gitutil.is_ancestor(root, "origin/main", "HEAD"):
        ui.ok(f"corral is up to date (v{__version__}, {short_head})")
        return True
    if not gitutil.is_ancestor(root, "HEAD", "origin/main"):
        ui.warn("skipping update: local main has diverged from origin/main")
        return True

    if _git(root, "pull", "--quiet", "--ff-only", "origin", "main").returncode != 0:
        ui.warn("fast-forward to origin/main failed")
        return False

    new_head = _git(root, "rev-parse", "--short", "HEAD").stdout.strip()
    new_version = _installed_version(root) or "?"
    ui.ok(f"updated corral to latest main (v{new_version}, {new_head})")
    return True


def run(ctx: Context, args: Dict[str, object]) -> int:
    failed = False

    # --- required dependencies (unlike require_deps, report every one) ------
    ui.info("dependencies")
    for dep in RUNTIME_DEPS:
        path = shutil.which(dep)
        if path:
            version = _version_of(dep)
            suffix = f" ({version})" if version else ""
            ui.ok(f"{dep} — {path}{suffix}")
        else:
            ui.warn(f"{dep} — not found on PATH")
            failed = True
    if failed:
        ui.info("  corral needs herdr and git. herdr: https://herdr.dev")

    # --- environment (informational; never fails the doctor) ----------------
    ui.info("environment")
    ui.ok(f"python — {sys.executable} ({sys.version.split()[0]})")
    if shutil.which("herdr"):
        if ctx.herdr.server_reachable():
            ui.ok("herdr server is reachable")
        else:
            ui.warn("herdr server is not reachable (spawn/ls/close need one running)")
    config = ctx.settings.config_path
    if os.path.isfile(config):
        ui.ok(f"config: {config}")
    else:
        ui.info(f"  no config file at {config} (defaults in effect — that's fine)")

    # --- self-update to the latest main --------------------------------------
    if not args["no_update"]:
        ui.info("update")
        if shutil.which("git"):
            if not _update(str(REPO_ROOT)):
                failed = True
        else:
            ui.warn("skipping update: git is not installed")

    if failed:
        raise CorralError("doctor found problems (see above)")
    ui.ok("corral is healthy")
    return 0
