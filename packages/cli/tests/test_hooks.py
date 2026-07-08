"""The .corral/cleanup.sh teardown hook."""

import os
import tempfile
import unittest

from corral.hooks import run_cleanup


class RunCleanupTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.wt = self._tmp.name
        self.addCleanup(self._tmp.cleanup)

    def _write_script(self, body):
        os.makedirs(os.path.join(self.wt, ".corral"), exist_ok=True)
        with open(os.path.join(self.wt, ".corral", "cleanup.sh"), "w") as fh:
            fh.write(body)

    def test_no_script_proceeds(self):
        self.assertTrue(run_cleanup(self.wt, force=False))

    def test_success_proceeds(self):
        self._write_script("exit 0\n")
        self.assertTrue(run_cleanup(self.wt, force=False))

    def test_failure_aborts(self):
        self._write_script("exit 3\n")
        self.assertFalse(run_cleanup(self.wt, force=False))

    def test_failure_plus_force_proceeds(self):
        self._write_script("exit 3\n")
        self.assertTrue(run_cleanup(self.wt, force=True))

    def test_disabled_proceeds_despite_failure(self):
        self._write_script("exit 3\n")
        self.assertTrue(run_cleanup(self.wt, force=False, enabled=False))

    def test_script_runs_with_stdin_closed(self):
        # A stdin-slurping cleanup (cat, ssh, read) must not be able to hang
        # or swallow the caller's input: stdin is /dev/null, so `read` fails.
        self._write_script("read -r line && exit 1; exit 0\n")
        self.assertTrue(run_cleanup(self.wt, force=False))

    def test_script_runs_in_the_worktree(self):
        self._write_script('[ "$(pwd -P)" = "$(cd . && pwd -P)" ] && touch ran-here\n')
        self.assertTrue(run_cleanup(self.wt, force=False))
        self.assertTrue(os.path.exists(os.path.join(self.wt, "ran-here")))


if __name__ == "__main__":
    unittest.main()
