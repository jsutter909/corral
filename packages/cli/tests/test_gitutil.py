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


if __name__ == "__main__":
    unittest.main()
