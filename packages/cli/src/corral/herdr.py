"""A thin, typed client for the herdr CLI's socket API.

Every herdr invocation goes through :meth:`Herdr.call`, which turns both
non-zero exits and herdr's ``{"error": …}``-with-exit-0 responses into
:class:`CorralError` — no call site can accidentally ignore a failure.
herdr's stderr passes straight through to the user; only stdout (the JSON
payload) is captured.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from typing import Dict, List, Optional, Tuple

from .ui import CorralError
from .workspaces import Workspace, WorktreeCreation


def require_deps(*deps: str) -> None:
    """Friendly first-run failures instead of cryptic 'command not found'."""
    missing = [dep for dep in deps if shutil.which(dep) is None]
    if missing:
        raise CorralError(
            f"missing required command(s): {' '.join(missing)}\n"
            "  corral needs: herdr, git. Install the missing tool(s) and retry.\n"
            "  herdr:  https://herdr.dev"
        )


class Herdr:
    """Wraps the `herdr` executable; all methods raise CorralError on failure."""

    def __init__(self, exe: str = "herdr") -> None:
        self.exe = exe

    # -- plumbing -----------------------------------------------------------

    def call(self, *args: str) -> Dict:
        proc = subprocess.run(
            [self.exe, *args],
            stdout=subprocess.PIPE,
            text=True,
        )
        out = (proc.stdout or "").strip()
        if proc.returncode != 0:
            detail = f": {out}" if out else ""
            raise CorralError(f"herdr {args[0]} failed (exit {proc.returncode}){detail}")
        if not out:
            return {}
        try:
            data = json.loads(out)
        except ValueError:
            raise CorralError(f"herdr {args[0]}: unexpected non-JSON response") from None
        if isinstance(data, dict) and "error" in data:
            err = data["error"] or {}
            msg = err.get("message") or err.get("code") or "unknown error"
            raise CorralError(f"herdr {args[0]}: {msg}")
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _get(data: Dict, path: str):
        """Walk a dotted path, dying loudly when the response shape is off."""
        node = data
        for key in path.split("."):
            if not isinstance(node, dict) or key not in node or node[key] is None:
                raise CorralError(f"unexpected herdr response (missing .{path})")
            node = node[key]
        return node

    # -- server -------------------------------------------------------------

    def server_reachable(self) -> bool:
        try:
            proc = subprocess.run(
                [self.exe, "status", "server"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            return False
        return proc.returncode == 0

    def require_server(self) -> None:
        if not self.server_reachable():
            raise CorralError(
                "herdr server is not reachable.\n"
                "  Start a herdr session first (run 'herdr', or attach with "
                "'herdr --remote <target>')."
            )

    def start_server_detached(self, timeout: float = 10.0) -> None:
        """Start a headless herdr server and wait until it answers.

        Launched in its own session so it outlives this process (which will
        shortly exec the herdr client). Raises CorralError if the server never
        becomes reachable within `timeout` seconds.
        """
        if self.server_reachable():
            return
        try:
            subprocess.Popen(
                [self.exe, "server"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError as exc:
            raise CorralError(f"could not start herdr server: {exc}") from None
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.server_reachable():
                return
            time.sleep(0.2)
        raise CorralError(
            f"herdr server did not come up within {timeout:g}s (try running 'herdr' by hand)"
        )

    # -- workspaces ----------------------------------------------------------

    def workspace_list(self) -> List[Workspace]:
        data = self.call("workspace", "list")
        payload = self._get(data, "result.workspaces")
        return [Workspace.from_payload(item) for item in payload]

    def workspace_get(self, workspace_id: str) -> Workspace:
        data = self.call("workspace", "get", workspace_id)
        return Workspace.from_payload(self._get(data, "result.workspace"))

    def workspace_focus(self, workspace_id: str) -> None:
        self.call("workspace", "focus", workspace_id)

    def workspace_create(self, label: str, cwd: str = "") -> Tuple[str, str]:
        """Create a plain (worktree-less) workspace; return (workspace_id,
        root_pane_id)."""
        args = ["workspace", "create", "--label", label, "--no-focus"]
        if cwd:
            args += ["--cwd", cwd]
        data = self.call(*args)
        return (
            self._get(data, "result.workspace.workspace_id"),
            self._get(data, "result.root_pane.pane_id"),
        )

    def has_workspace_label(self, label: str) -> bool:
        """True if any workspace already carries this label (idempotency check)."""
        return any(ws.label == label for ws in self.workspace_list())

    def current_workspace(self) -> str:
        """Workspace id of the pane invoking corral; '' outside herdr."""
        try:
            proc = subprocess.run(
                [self.exe, "pane", "current", "--current"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            data = json.loads(proc.stdout or "{}")
        except (OSError, ValueError):
            return ""
        if proc.returncode != 0 or not isinstance(data, dict):
            return ""
        return ((data.get("result") or {}).get("pane") or {}).get("workspace_id") or ""

    # -- worktrees -----------------------------------------------------------

    def worktree_create(
        self, cwd: str, branch: str, label: str, base: str = ""
    ) -> WorktreeCreation:
        args = [
            "worktree", "create",
            "--cwd", cwd,
            "--branch", branch,
            "--label", label,
            "--no-focus",
        ]
        if base:
            args += ["--base", base]
        data = self.call(*args)
        return WorktreeCreation(
            workspace_id=self._get(data, "result.workspace.workspace_id"),
            root_pane_id=self._get(data, "result.root_pane.pane_id"),
            worktree_path=self._get(data, "result.worktree.path"),
        )

    def worktree_remove(self, workspace_id: str) -> None:
        self.call("worktree", "remove", "--workspace", workspace_id, "--force")

    def worktree_remove_quiet(self, workspace_id: str) -> None:
        """Best-effort removal for rollback paths; never raises."""
        try:
            subprocess.run(
                [self.exe, "worktree", "remove", "--workspace", workspace_id, "--force"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            pass

    # -- panes ----------------------------------------------------------------

    def pane_split(self, pane_id: str, direction: str, ratio: str) -> str:
        data = self.call(
            "pane", "split", pane_id,
            "--direction", direction,
            "--ratio", str(ratio),
            "--no-focus",
        )
        return self._get(data, "result.pane.pane_id")

    def pane_run(self, pane_id: str, command: str) -> None:
        self.call("pane", "run", pane_id, command)
