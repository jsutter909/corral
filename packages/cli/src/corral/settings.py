"""The settings registry — corral's single source of truth for configuration.

Every setting is declared once, as a :class:`Setting`. From this registry:

* :meth:`Settings.load` implements the documented precedence
  (built-in defaults < config file < ``CORRAL_*`` environment < CLI flags —
  flags are applied later, by each command's parser);
* ``corral <cmd> --help`` renders live defaults;
* ``python -m corral.generate`` renders the settings table in
  ``docs/configuration.md`` and the whole ``share/config.example.sh``.

Adding a setting here is the entire job — docs and the example config follow
on the next ``make generate``.
"""

from __future__ import annotations

import os
import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Mapping, Optional, Tuple, Union


def _default_config_path(environ: Mapping[str, str]) -> str:
    xdg = environ.get("XDG_CONFIG_HOME") or os.path.join(environ.get("HOME", "~"), ".config")
    return os.path.join(xdg, "corral", "config.sh")


def _default_worktrees_dir(environ: Mapping[str, str]) -> str:
    return os.path.join(environ.get("HOME", "~"), ".herdr", "worktrees")


def _default_resources_db(environ: Mapping[str, str]) -> str:
    xdg = environ.get("XDG_STATE_HOME") or os.path.join(
        environ.get("HOME", "~"), ".local", "state"
    )
    return os.path.join(xdg, "corral", "resources.db")


@dataclass(frozen=True)
class Setting:
    """One configurable value: its identity, default, and documentation."""

    env: str  # CORRAL_* environment variable / config-file key
    attr: str  # attribute name on Settings (settings.agent, …)
    default: Union[str, Callable[[Mapping[str, str]], str]]
    doc: str  # "Meaning" cell in docs/configuration.md (markdown)
    default_doc: str = ""  # "Default" cell; derived from `default` when empty
    empty_means: str = ""  # help-text description of an empty value
    flag: str = ""  # linked CLI flag, e.g. "--agent" (docs table)
    flag_command: str = ""  # command the flag belongs to, e.g. "spawn"
    example: str = ""  # comment block above the config.example.sh entry
    example_value: str = ""  # value shown in the example ("" = the default)
    example_commented: bool = False  # example line ships commented out
    from_file: bool = True  # False: env-only (CORRAL_CONFIG locates the file)

    def resolved_default(self, environ: Mapping[str, str]) -> str:
        if callable(self.default):
            return self.default(environ)
        return self.default

    def describe_default(self, value: str) -> str:
        """Human text for '(default: …)' in --help, given the live value."""
        if value:
            return value
        return self.empty_means or "unset"


SETTINGS: Tuple[Setting, ...] = (
    Setting(
        env="CORRAL_AGENT",
        attr="agent",
        default="claude",
        flag="--agent",
        flag_command="spawn",
        doc="Agent launched in the left pane, or `none`.",
        example=(
            "Agent to launch in the left pane. Any herdr-integrated agent works\n"
            '(claude, codex, copilot, droid, opencode, cursor, ...). Use "none" for a\n'
            "blank shell. Override per-run with: corral spawn <repo> --agent <name>"
        ),
    ),
    Setting(
        env="CORRAL_MODEL",
        attr="model",
        default="",
        default_doc="`` (Claude's default)",
        empty_means="Claude's default",
        flag="--model",
        flag_command="spawn",
        doc="Model for the Claude agent (claude only).",
        example=(
            "Model for the Claude agent (claude only). Empty = Claude's default.\n"
            "Override per-run with: corral spawn <repo> --model <name>"
        ),
        example_commented=True,
    ),
    Setting(
        env="CORRAL_PERMISSION_MODE",
        attr="permission_mode",
        default="",
        default_doc="`` (Claude's default)",
        empty_means="Claude's default",
        flag="--permission-mode",
        flag_command="spawn",
        doc="Claude permission/edit mode, e.g. `acceptEdits`, `plan` (claude only).",
        example=(
            "Claude permission/edit mode (claude only): default, acceptEdits, plan,\n"
            "bypassPermissions. Empty = Claude's default.\n"
            "Override per-run with: corral spawn <repo> --permission-mode <mode>"
        ),
        example_commented=True,
    ),
    Setting(
        env="CORRAL_RATIO",
        attr="ratio",
        default="0.4",
        flag="--ratio",
        flag_command="spawn",
        doc="Agent (left) pane width share, `0..1`.",
        example="Agent (left) pane share of the width, 0..1. Higher = wider agent pane.",
    ),
    Setting(
        env="CORRAL_SETUP",
        attr="setup",
        default="1",
        flag="--no-setup",
        flag_command="spawn",
        doc="Run a repo's committed `.corral/setup.sh` before the agent (`0` = never).",
        example=(
            "Run a repo's committed .corral/setup.sh in the agent pane before the agent\n"
            "starts (chained with &&, so the agent only launches if setup succeeds).\n"
            "Set to 0 to disable. Override per-run with: corral spawn <repo> --no-setup"
        ),
        example_commented=True,
    ),
    Setting(
        env="CORRAL_CLEANUP",
        attr="cleanup",
        default="1",
        flag="--no-cleanup",
        flag_command="close",
        doc=(
            "Run a worktree's `.corral/cleanup.sh` before removing it on close/prune "
            "(`0` = never)."
        ),
        example=(
            "Run a worktree's .corral/cleanup.sh before it is removed on close/prune (the\n"
            "teardown counterpart to setup.sh; runs as the script exists at that moment).\n"
            "If cleanup fails the removal is aborted (worktree kept) unless you pass\n"
            "--force. Set to 0 to disable, or skip per-run with: corral close --no-cleanup"
        ),
        example_commented=True,
    ),
    Setting(
        env="CORRAL_IDE",
        attr="ide",
        default="vscode",
        flag="--ide",
        flag_command="open",
        doc="IDE opened by `corral open`: `vscode` or `cursor`.",
        example=(
            "IDE opened by 'corral open': vscode or cursor.\n"
            "Override per-run with: corral open <workspace> --ide <name>"
        ),
        example_commented=True,
    ),
    Setting(
        env="CORRAL_SSH_HOST",
        attr="ssh_host",
        default="",
        default_doc="`` (this machine's hostname)",
        empty_means="this machine's hostname",
        flag="--host",
        flag_command="open",
        doc=(
            "SSH host in the Remote-SSH links `corral open` prints for remote "
            "(`herdr --remote`) sessions; must match a `Host` entry in your "
            "**local** `~/.ssh/config`."
        ),
        example=(
            "SSH host used in the Remote-SSH links 'corral open' prints when the herdr\n"
            "session is remote (herdr --remote). Must match how YOUR machine reaches this\n"
            "one — a Host entry in your local ~/.ssh/config. Empty = this machine's\n"
            "hostname. Override per-run with: corral open <workspace> --host <host>"
        ),
        example_commented=True,
    ),
    Setting(
        env="CORRAL_BRANCH_PREFIX",
        attr="branch_prefix",
        default="agent",
        doc="Prefix for auto branch names: `<prefix>/<repo>-<timestamp>`.",
        example="Prefix for auto-generated branch names: <prefix>/<repo>-<timestamp>.",
    ),
    Setting(
        env="CORRAL_BASE",
        attr="base",
        default="",
        default_doc="`` (HEAD)",
        empty_means="current HEAD",
        flag="--base",
        flag_command="spawn",
        doc="Base ref for new worktrees.",
        example=(
            "Base ref new worktrees branch from. Empty = current HEAD of the repo.\n"
            "e.g. CORRAL_BASE=main"
        ),
    ),
    Setting(
        env="CORRAL_WORKTREES_DIR",
        attr="worktrees_dir",
        default=_default_worktrees_dir,
        default_doc="`~/.herdr/worktrees`",
        doc=(
            "Where herdr checks out corral's worktrees; corral only ever destroys "
            "worktrees under this directory."
        ),
        example=(
            "Where herdr checks out corral's worktrees. Corral only ever destroys\n"
            "worktrees under this directory (rarely needs changing)."
        ),
        example_value='"$HOME/.herdr/worktrees"',
        example_commented=True,
    ),
    Setting(
        env="CORRAL_RESOURCES_DB",
        attr="resources_db",
        default=_default_resources_db,
        default_doc="`~/.local/state/corral/resources.db`",
        doc=(
            "SQLite database backing `corral resource` pools and leases "
            "(one per machine — all workspaces share it)."
        ),
        example=(
            "Where 'corral resource' keeps its pools and leases. One database per\n"
            "machine — all workspaces share it (rarely needs changing)."
        ),
        example_value='"$HOME/.local/state/corral/resources.db"',
        example_commented=True,
    ),
    Setting(
        env="CORRAL_MONITOR_HOST",
        attr="monitor_host",
        default="127.0.0.1",
        flag="--host",
        flag_command="monitor",
        doc=(
            "Address `corral monitor` binds its web UI to. Defaults to loopback "
            "(local only); set to `0.0.0.0` to expose it on your network."
        ),
        example=(
            "Address 'corral monitor' binds its web UI to. Loopback by default, so the\n"
            "dashboard is reachable only from this machine. Set to 0.0.0.0 to expose it on\n"
            "the network. Override per-run with: corral monitor --host <addr>"
        ),
        example_commented=True,
    ),
    Setting(
        env="CORRAL_MONITOR_PORT",
        attr="monitor_port",
        default="8477",
        flag="--port",
        flag_command="monitor",
        doc="Port `corral monitor` serves its web UI on.",
        example=(
            "Port 'corral monitor' serves its web UI on.\n"
            "Override per-run with: corral monitor --port <port>"
        ),
        example_commented=True,
    ),
    Setting(
        env="CORRAL_CONFIG",
        attr="config_path",
        default=_default_config_path,
        default_doc="`~/.config/corral/config.sh`",
        doc="Path to the config file itself.",
        example="Where this config lives (rarely needs changing).",
        example_value='"$HOME/.config/corral/config.sh"',
        example_commented=True,
        from_file=False,
    ),
)

BY_ENV: Dict[str, Setting] = {s.env: s for s in SETTINGS}
BY_ATTR: Dict[str, Setting] = {s.attr: s for s in SETTINGS}

# Matches the config file's plain-bash assignments: NAME=value / export NAME=value.
_ASSIGNMENT = re.compile(r"^\s*(?:export\s+)?(CORRAL_[A-Z_]+)=(.*)$")


def parse_config_file(text: str, environ: Mapping[str, str]) -> Dict[str, str]:
    """Extract CORRAL_* assignments from a config.sh.

    The file format stays the historical plain-bash one, so existing configs
    keep working — but it is parsed, not sourced: only simple assignments are
    honored (with $VAR / ~ expansion), never arbitrary shell.
    """
    values: Dict[str, str] = {}
    for line in text.splitlines():
        match = _ASSIGNMENT.match(line)
        if not match:
            continue
        name, raw = match.group(1), match.group(2).strip()
        if not raw:
            values[name] = ""
            continue
        try:
            parts = shlex.split(raw, comments=True)
        except ValueError:
            continue  # unbalanced quotes etc. — skip the line, keep the rest
        value = parts[0] if parts else ""
        value = os.path.expanduser(value)
        # expandvars against the same environment the shell would have seen
        value = re.sub(
            r"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?",
            lambda m: environ.get(m.group(1), ""),
            value,
        )
        values[name] = value
    return values


@dataclass
class Settings:
    """Loaded configuration with attribute access per Setting.attr."""

    values: Dict[str, str] = field(default_factory=dict)  # keyed by attr

    def __getattr__(self, name: str) -> str:  # only called for missing attrs
        try:
            return self.__dict__["values"][name]
        except KeyError:
            raise AttributeError(name) from None

    @property
    def setup_enabled(self) -> bool:
        return self.values["setup"] == "1"

    @property
    def cleanup_enabled(self) -> bool:
        return self.values["cleanup"] == "1"

    def describe_default(self, attr: str) -> str:
        """'(default: …)' text for --help, from the live value."""
        return BY_ATTR[attr].describe_default(self.values[attr])

    @classmethod
    def load(cls, environ: Optional[Mapping[str, str]] = None) -> "Settings":
        env = os.environ if environ is None else environ

        values = {s.attr: s.resolved_default(env) for s in SETTINGS}

        config_path = env.get("CORRAL_CONFIG") or values["config_path"]
        values["config_path"] = config_path
        path = Path(config_path)
        if path.is_file():
            try:
                file_values = parse_config_file(path.read_text(encoding="utf-8"), env)
            except OSError:
                file_values = {}
            for setting in SETTINGS:
                if setting.from_file and file_values.get(setting.env):
                    values[setting.attr] = file_values[setting.env]

        # Environment beats the file (flags, applied later, beat both).
        for setting in SETTINGS:
            env_value = env.get(setting.env)
            if env_value:
                values[setting.attr] = env_value

        return cls(values=values)
