"""corral spawn — create an isolated agent workspace in a fresh git worktree."""

from __future__ import annotations

import datetime
import os
import re
import sys
from typing import Dict

from .. import gitutil, hooks, ui
from ..agents import AGENTS, CLAUDE_MODELS, CLAUDE_PERMISSION_MODES, NONE, find_agent, launch_command
from ..cli import Argument, Command, Example, Option
from ..herdr import require_deps
from ..naming import branch_from_prompt
from ..ui import CorralError
from . import Context

LAYOUT = """\
Layout (one herdr workspace per agent):
  +----------------+-------------+
  |                | terminal    |   left  : the agent (Claude Code by default),
  |   agent pane   +-------------+           full height
  |                | terminal    |   right : two terminals stacked, both cwd'd
  +----------------+-------------+           into the worktree"""

SPEC = Command(
    name="spawn",
    summary="launch an isolated agent workspace in a fresh git worktree.",
    shell_alias="csp",
    description=LAYOUT,
    epilog=(
        "If the repo commits a .corral/setup.sh, spawn runs it in the agent pane\n"
        "first (bash .corral/setup.sh && <agent>) — the agent only starts once\n"
        "setup succeeds."
    ),
    doc=(
        "Create an isolated agent workspace in a fresh git worktree.\n"
        "\n"
        "If the repo commits a `.corral/setup.sh`, spawn chains it before the agent in\n"
        "the agent pane (`bash .corral/setup.sh && <agent>`): the agent only starts once\n"
        "setup succeeds, and a failure stays visible in the pane. See\n"
        "[per-repo configuration](configuration.md#per-repo-configuration-corral)."
    ),
    arguments=(
        Argument(
            "repo",
            help="Path inside the git repo to branch from (e.g. ~/dev/app or .)",
            doc=(
                "Any path inside the git repo to branch from (e.g. `~/dev/app` or "
                "`.`). corral resolves it to the repo root."
            ),
            completion="_directories",
            value_label="repository directory",
        ),
        Argument(
            "branch",
            required=False,
            help=(
                "Branch name for the worktree\n"
                "(default: with --prompt, <prefix>/<name> where <name> is\n"
                "generated from the prompt by the claude CLI, slugged\n"
                "prompt text as fallback; otherwise <prefix>/<repo>-<timestamp>)"
            ),
            doc=(
                "Branch name for the worktree. Default: with `--prompt`, "
                "`<prefix>/<name>` where `<name>` is generated from the prompt by "
                "the `claude` CLI (falling back to slugged prompt text, with a "
                "numeric suffix if the branch already exists); otherwise "
                "`<prefix>/<repo>-<timestamp>`."
            ),
            completion="_corral_new_branch",
            value_label="new branch name",
        ),
    ),
    options=(
        Option(
            "--agent",
            short="-a",
            metavar="<name>",
            setting="agent",
            help='Agent to launch in the left pane, or "none" for a blank shell',
            doc=(
                "Agent to launch in the left pane, or `none` for a blank shell. "
                "Any herdr-integrated agent works ("
                + ", ".join(f"`{a.name}`" for a in AGENTS if a.name != NONE)
                + ", …)."
            ),
            completion="_corral_agents",
            value_hint="agent",
        ),
        Option(
            "--model",
            short="-m",
            metavar="<name>",
            setting="model",
            help="Model for the Claude agent. claude agent only",
            doc=(
                "Model for the Claude agent. Applies to the `claude` agent only; "
                "ignored (with a warning) for others."
            ),
            choices=CLAUDE_MODELS,
            value_hint="model",
        ),
        Option(
            "--permission-mode",
            short="-P",
            metavar="<mode>",
            setting="permission_mode",
            help="Claude permission/edit mode, e.g. acceptEdits, plan. claude agent only",
            doc="Claude permission/edit mode, e.g. `acceptEdits`, `plan`. `claude` agent only.",
            choices=CLAUDE_PERMISSION_MODES,
            value_hint="mode",
        ),
        Option(
            "--prompt",
            short="-p",
            metavar="<text>",
            help=(
                "Initial prompt to hand the agent on launch\n"
                "(passed as the agent's first positional argument, ignored for\n"
                "--agent none; when [branch] is omitted, the branch is named\n"
                "after the prompt too)"
            ),
            doc=(
                "Initial prompt handed to the agent on launch, as its first "
                "positional argument. Ignored (with a warning) for `--agent none`. "
                "When `[branch]` is omitted, the branch is named after the prompt too."
            ),
            value_hint="prompt",
        ),
        Option(
            "--base",
            short="-b",
            metavar="<ref>",
            setting="base",
            help="Base ref to branch the worktree from",
            doc="Base ref the new worktree branches from.",
            completion="_corral_git_refs",
            value_hint="git ref",
        ),
        Option(
            "--ratio",
            short="-r",
            metavar="<0..1>",
            setting="ratio",
            help="Agent (left) pane share of width",
            doc="Agent (left) pane share of the width.",
            value_hint="ratio (0..1)",
        ),
        Option(
            "--label",
            short="-l",
            metavar="<text>",
            help="Workspace label",
            default_doc="derived from the branch name",
            doc="herdr workspace label.",
            value_hint="label",
        ),
        Option(
            "--no-focus",
            help="Create the workspace without switching focus to it",
            doc="Create the workspace without switching to it.",
        ),
        Option(
            "--no-setup",
            help="Skip the repo's .corral/setup.sh (also: CORRAL_SETUP=0)",
            doc="Skip the repo's committed `.corral/setup.sh` (also: `CORRAL_SETUP=0`).",
        ),
    ),
    examples=(
        Example("corral spawn ~/dev/app"),
        Example("corral spawn ~/dev/app feature/checkout"),
        Example("corral spawn . bugfix/tax --base main --agent codex --ratio 0.55"),
        Example("corral spawn ~/dev/app --model opus --permission-mode acceptEdits"),
        Example(
            'corral spawn ~/dev/app --prompt "fix the failing tax tests"',
            note="branch: e.g. agent/fix-failing-tax-tests",
        ),
        Example("corral spawn ~/dev/app --agent none", note="just the worktree + terminals"),
    ),
)

_RATIO_RE = re.compile(r"^(0(\.[0-9]+)?|1(\.0+)?|\.[0-9]+)$")


def _default_branch(ctx: Context, repo: str, prompt: str) -> str:
    """Branch name when none was given: prompt-derived, else timestamped."""
    prefix = ctx.settings.branch_prefix
    slug = ""
    if prompt:
        ui.info("naming the branch from the prompt…")
        slug = branch_from_prompt(prompt)
    if slug:
        branch = f"{prefix}/{slug}"
        if gitutil.branch_exists(repo, branch):
            n = 2
            while gitutil.branch_exists(repo, f"{branch}-{n}"):
                n += 1
            branch = f"{branch}-{n}"
        return branch
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{prefix}/{os.path.basename(repo)}-{stamp}-{os.getpid()}"


def run(ctx: Context, args: Dict[str, object]) -> int:
    repo_arg = str(args["repo"])
    branch = str(args["branch"])
    agent = str(args["agent"])
    model = str(args["model"])
    permission_mode = str(args["permission_mode"])
    prompt = str(args["prompt"])
    base = str(args["base"])
    ratio = str(args["ratio"])
    label = str(args["label"])
    focus = not args["no_focus"]
    setup = ctx.settings.setup_enabled and not args["no_setup"]

    if not repo_arg:
        raise CorralError("missing <repo> argument (try 'corral spawn --help')")

    # Validate --ratio before any herdr call so a typo can't half-build a workspace.
    if not _RATIO_RE.match(ratio):
        raise CorralError(f"--ratio must be a number between 0 and 1 (got '{ratio}')")

    require_deps("herdr", "git")
    ctx.herdr.require_server()

    # Resolve to the repo root so the worktree anchors correctly.
    repo = gitutil.repo_root(repo_arg)
    if not repo:
        raise CorralError(f"'{repo_arg}' is not inside a git repository")

    # Default branch: named after the task when a prompt was given, otherwise
    # timestamp + pid so parallel spawns in the same second still get distinct
    # names. Prompt-derived names get a numeric suffix if the branch exists.
    if not branch:
        branch = _default_branch(ctx, repo, prompt)
    if not label:
        label = os.path.basename(branch)

    # 1) Create the git worktree + a fresh, isolated workspace.
    created = ctx.herdr.worktree_create(cwd=repo, branch=branch, label=label, base=base)
    ws, left, wt = created.workspace_id, created.root_pane_id, created.worktree_path

    # Any failure past this point must not leave a half-built workspace behind:
    # roll the partial workspace back. The cleanup hook runs best-effort first
    # (forced) — setup.sh may already have started in the pane and created
    # external resources, and once the worktree is gone its cleanup.sh is gone
    # with it — but a cleanup failure must never block the rollback itself.
    try:
        # 2) Split the root pane: agent left, right column takes (1 - ratio).
        right_top = ctx.herdr.pane_split(left, direction="right", ratio=ratio)
        # 3) Split the right column into two stacked terminals.
        right_bottom = ctx.herdr.pane_split(right_top, direction="down", ratio="0.5")

        # 4) Launch in the left pane. If the repo ships a .corral/setup.sh
        #    (present in the fresh worktree because it's checked out from the
        #    base ref), chain it before the agent: the agent only starts once
        #    setup succeeds, and a failure stays visible in the pane.
        run_setup = setup and hooks.has_setup_script(wt)

        # --model/--permission-mode/--prompt only make sense for an agent that
        # takes them; warn (rather than silently drop) when they'd be ignored.
        spec = find_agent(agent)
        takes_claude_flags = spec is not None and spec.takes_model
        if agent not in (NONE, "") and not takes_claude_flags and (model or permission_mode):
            ui.warn(
                "--model/--permission-mode only apply to the claude agent; "
                f"ignoring for '{agent}'"
            )
        if agent in (NONE, "") and prompt:
            ui.warn("--prompt has no effect with --agent none; ignoring")

        launch = launch_command(agent, model, permission_mode, prompt, run_setup)
        if launch:
            ctx.herdr.pane_run(left, launch)

        # 5) Focus the new workspace (lands on the left/agent pane).
        if focus:
            ctx.herdr.workspace_focus(ws)
    except BaseException:
        ui.warn(f"spawn failed — removing partially created workspace {ws}")
        try:
            hooks.run_cleanup(wt, force=True)
        except Exception:
            pass
        ctx.herdr.worktree_remove_quiet(ws)
        raise

    ui.ok(f"agent workspace {ui.C.bold}{ws}{ui.C.reset} ({label})")
    summary = [
        f"    repo     {repo}",
        f"    branch   {branch}",
        f"    worktree {wt}",
        f"    agent    {agent}",
    ]
    if run_setup:
        summary.append("    setup    .corral/setup.sh")
    if takes_claude_flags:
        if model:
            summary.append(f"    model    {model}")
        if permission_mode:
            summary.append(f"    mode     {permission_mode}")
    if prompt and agent not in (NONE, ""):
        summary.append(f"    prompt   {prompt}")
    summary.append(f"    panes    agent={left}  term-top={right_top}  term-bottom={right_bottom}")
    summary.append("")
    summary.append(f"  Tear down when finished:  {ui.C.dim}corral close {ws}{ui.C.reset}")
    print("\n".join(summary), file=sys.stderr)
    return 0
