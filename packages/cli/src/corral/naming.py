"""Branch naming: slugs and prompt-derived names."""

from __future__ import annotations

import re
import shutil
import subprocess

MAX_SLUG_LEN = 40


def branch_slug(text: str) -> str:
    """Turn free-form text into a git-branch-safe slug.

    Lowercase; runs of anything outside [a-z0-9] collapse to single hyphens;
    capped at 40 chars so branch names stay readable (capped *before*
    stripping, so a hyphen landing on the boundary still disappears).
    Returns '' when no usable characters remain.
    """
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower())
    return slug[:MAX_SLUG_LEN].strip("-")


def branch_from_prompt(prompt: str) -> str:
    """Name a branch after the task.

    Asks the claude CLI (print mode, haiku for speed) to summarize the prompt
    into a branch name; whatever comes back is slugged, so a chatty or
    malformed reply can never produce an invalid ref. Falls back to slugging
    the prompt text directly when claude is unavailable or errors. Returns ''
    only if both paths yield nothing (the caller then uses the timestamp
    scheme).
    """
    slug = ""
    if shutil.which("claude"):
        question = (
            "Suggest a short kebab-case git branch name (2-5 words, lowercase "
            "letters, digits and hyphens only, no prefix like feature/) for "
            f"this task: {prompt}\nReply with the branch name only."
        )
        try:
            proc = subprocess.run(
                ["claude", "-p", "--model", "haiku", question],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            if proc.returncode == 0 and proc.stdout:
                slug = branch_slug(proc.stdout.splitlines()[0] if proc.stdout.splitlines() else "")
        except OSError:
            slug = ""
    return slug or branch_slug(prompt)
