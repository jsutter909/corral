"""The agent registry and launch-command construction.

Agents are declared once here; the registry feeds ``spawn --agent`` docs,
the zsh completion (name + description), and the launch-command builder.
Adding an agent below is all it takes for it to appear everywhere on the
next ``make generate``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

NONE = "none"


@dataclass(frozen=True)
class Agent:
    name: str
    summary: str  # completion description / docs
    takes_model: bool = False  # honors `corral spawn --model`
    takes_permission_mode: bool = False  # honors `corral spawn --permission-mode`


AGENTS: Tuple[Agent, ...] = (
    Agent("claude", "Claude Code (default)", takes_model=True, takes_permission_mode=True),
    Agent("codex", "OpenAI Codex CLI"),
    Agent("copilot", "GitHub Copilot CLI"),
    Agent("droid", "Factory Droid"),
    Agent("opencode", "opencode"),
    Agent("cursor", "Cursor CLI"),
    Agent(NONE, "no agent — blank shell in the left pane"),
)

# Values completed for spawn --model / --permission-mode (claude only).
CLAUDE_MODELS: Tuple[str, ...] = ("opus", "sonnet", "haiku")
CLAUDE_PERMISSION_MODES: Tuple[str, ...] = (
    "acceptEdits",
    "plan",
    "bypassPermissions",
    "default",
)


def find_agent(name: str) -> Optional[Agent]:
    for agent in AGENTS:
        if agent.name == name:
            return agent
    return None


def sh_quote(value: str) -> str:
    """Single-quote a string for the shell herdr runs `pane run` through.

    POSIX style: wrap in single quotes, escape embedded single quotes.
    """
    return "'" + value.replace("'", "'\\''") + "'"


def launch_command(
    agent: str,
    model: str = "",
    permission_mode: str = "",
    prompt: str = "",
    run_setup: bool = False,
) -> str:
    """Compose the agent pane's command string.

    The repo's setup script is chained (&&) before the agent, so the agent
    only starts if setup succeeds. A prompt becomes the agent's first
    positional argument, quoted so spaces and metacharacters survive herdr
    running the command through a shell. Model/permission-mode apply to
    agents that declare support (claude). Returns '' when there is nothing
    to run.
    """
    launch = ""
    if agent and agent != NONE:
        launch = agent
        spec = find_agent(agent)
        if spec is not None and spec.takes_model and model:
            launch += f" --model {model}"
        if spec is not None and spec.takes_permission_mode and permission_mode:
            launch += f" --permission-mode {permission_mode}"
        if prompt:
            launch += f" {sh_quote(prompt)}"
    if run_setup:
        launch = f"bash .corral/setup.sh && {launch}" if launch else "bash .corral/setup.sh"
    return launch
