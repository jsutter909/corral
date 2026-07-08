"""Repo-relative paths, resolved from this package's own location.

The CLI is run straight from a checkout (bin/corral inserts src/ onto
sys.path), so the monorepo root is always a fixed number of levels up from
this file: packages/cli/src/corral/paths.py.
"""

from __future__ import annotations

from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent  # …/packages/cli/src/corral
CLI_DIR = PACKAGE_DIR.parents[1]  # …/packages/cli
REPO_ROOT = PACKAGE_DIR.parents[3]  # the corral checkout
