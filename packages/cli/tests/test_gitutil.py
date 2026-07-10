"""Git helpers that back 'spawn from an existing branch' — exercised against
real throwaway repos so the behavior tracks git's, not a mock's."""

import os
import subprocess
import tempfile
import unittest

from corral import gitutil


def _git(repo, *args):
    subprocess.run(
        ["git", "-C", repo, *args],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


class RemoteRefTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = self._tmp.name
        # A "remote" repo with a couple of branches, and a clone of it.
        self.remote = os.path.join(root, "remote")
        self.repo = os.path.join(root, "clone")
        _git(root, "init", "--quiet", "--bare", "remote")
        work = os.path.join(root, "work")
        _git(root, "clone", "--quiet", self.remote, "work")
        _git(work, "config", "user.email", "t@example.com")
        _git(work, "config", "user.name", "t")
        _git(work, "commit", "--quiet", "--allow-empty", "-m", "init")
        _git(work, "branch", "feature/x")
        _git(work, "push", "--quiet", "origin", "HEAD:main", "feature/x")
        _git(root, "clone", "--quiet", self.remote, "clone")

    def tearDown(self):
        self._tmp.cleanup()

    def test_plain_name_resolves_to_origin_ref(self):
        self.assertEqual(gitutil.remote_ref(self.repo, "feature/x"), "origin/feature/x")

    def test_already_qualified_name_passes_through(self):
        self.assertEqual(
            gitutil.remote_ref(self.repo, "origin/feature/x"), "origin/feature/x"
        )

    def test_unknown_branch_returns_empty(self):
        self.assertEqual(gitutil.remote_ref(self.repo, "nope"), "")

    def test_local_only_branch_is_not_a_remote_ref(self):
        _git(self.repo, "branch", "local-only", "origin/feature/x")
        self.assertEqual(gitutil.remote_ref(self.repo, "local-only"), "")

    def test_remotes_lists_origin(self):
        self.assertEqual(gitutil.remotes(self.repo), ["origin"])


class FetchBranchTests(unittest.TestCase):
    """fetch_branch populates the remote-tracking ref for a branch pushed to
    the remote *after* the clone, so a bare name resolves without a manual
    fetch. Exercised against real repos."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = self._tmp.name
        self.remote = os.path.join(root, "remote")
        self.work = os.path.join(root, "work")
        self.repo = os.path.join(root, "clone")
        _git(root, "init", "--quiet", "--bare", "remote")
        _git(root, "clone", "--quiet", self.remote, "work")
        _git(self.work, "config", "user.email", "t@example.com")
        _git(self.work, "config", "user.name", "t")
        _git(self.work, "commit", "--quiet", "--allow-empty", "-m", "init")
        _git(self.work, "push", "--quiet", "origin", "HEAD:main")
        _git(root, "clone", "--quiet", self.remote, "clone")
        # A branch pushed to the remote only AFTER the clone — unknown locally.
        _git(self.work, "branch", "feature/pr-42")
        _git(self.work, "push", "--quiet", "origin", "feature/pr-42")

    def tearDown(self):
        self._tmp.cleanup()

    def test_unfetched_branch_is_not_visible_until_fetch(self):
        self.assertEqual(gitutil.remote_ref(self.repo, "feature/pr-42"), "")
        self.assertEqual(gitutil.fetch_branch(self.repo, "feature/pr-42"), "origin/feature/pr-42")
        self.assertEqual(gitutil.remote_ref(self.repo, "feature/pr-42"), "origin/feature/pr-42")

    def test_qualified_name_fetches_and_resolves(self):
        self.assertEqual(
            gitutil.fetch_branch(self.repo, "origin/feature/pr-42"), "origin/feature/pr-42"
        )

    def test_nonexistent_branch_returns_empty(self):
        self.assertEqual(gitutil.fetch_branch(self.repo, "nope"), "")


if __name__ == "__main__":
    unittest.main()
