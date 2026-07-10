"""gitutil.discover_worktrees — the filesystem walk `start`/`end` build on."""

import os
import tempfile
import unittest

from corral import gitutil


def touch_worktree(base, repo, label):
    """Create <base>/<repo>/<label> with a .git file (a linked worktree)."""
    wt = os.path.join(base, repo, label)
    os.makedirs(wt)
    with open(os.path.join(wt, ".git"), "w", encoding="utf-8") as fh:
        fh.write("gitdir: /somewhere\n")
    # discover_worktrees realpath's its base, so compare against realpath too
    # (temp dirs can sit under a symlink, e.g. macOS /tmp -> /private/tmp).
    return os.path.realpath(wt)


class DiscoverWorktreesTests(unittest.TestCase):
    def test_missing_dir_is_empty(self):
        self.assertEqual(gitutil.discover_worktrees("/no/such/dir"), [])

    def test_finds_two_level_layout_sorted(self):
        with tempfile.TemporaryDirectory() as base:
            b = touch_worktree(base, "app", "feature-b")
            a = touch_worktree(base, "app", "feature-a")
            c = touch_worktree(base, "lib", "fix")
            self.assertEqual(gitutil.discover_worktrees(base), [a, b, c])

    def test_ignores_dirs_without_git(self):
        with tempfile.TemporaryDirectory() as base:
            wt = touch_worktree(base, "app", "real")
            os.makedirs(os.path.join(base, "app", "leftover-empty"))
            os.makedirs(os.path.join(base, "stray-top-level"))
            self.assertEqual(gitutil.discover_worktrees(base), [wt])

    def test_git_may_be_a_file_or_dir(self):
        # Linked worktrees have a .git *file*; a primary-style .git *dir* counts too.
        with tempfile.TemporaryDirectory() as base:
            wt = os.path.join(base, "app", "primary")
            os.makedirs(os.path.join(wt, ".git"))
            self.assertEqual(gitutil.discover_worktrees(base), [os.path.realpath(wt)])

    def test_file_where_dir_expected_is_skipped(self):
        with tempfile.TemporaryDirectory() as base:
            # A stray file at the repo level must not crash the walk.
            with open(os.path.join(base, "notes.txt"), "w", encoding="utf-8") as fh:
                fh.write("x")
            wt = touch_worktree(base, "app", "real")
            self.assertEqual(gitutil.discover_worktrees(base), [wt])


if __name__ == "__main__":
    unittest.main()
