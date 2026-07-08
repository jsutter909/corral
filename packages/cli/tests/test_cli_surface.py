"""CLI surface smoke tests — exit codes for help/usage/error paths, exercised
through bin/corral in a subprocess (no herdr server needed: these paths all
return before any herdr call). Ported from the old smoke.sh."""

import os
import subprocess
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CORRAL = os.path.join(HERE, os.pardir, "bin", "corral")


def run(*args):
    env = dict(os.environ, CORRAL_CONFIG="/nonexistent/corral-config.sh")
    return subprocess.run(
        [CORRAL, *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )


class ExitCodeTests(unittest.TestCase):
    def assert_exit(self, want, *args):
        proc = run(*args)
        self.assertEqual(
            proc.returncode,
            want,
            msg=f"corral {' '.join(args)} → exit {proc.returncode}, wanted {want}\n"
            f"stderr: {proc.stderr}",
        )
        return proc

    def test_help_paths_exit_zero(self):
        self.assert_exit(0, "help")
        self.assert_exit(0, "version")
        self.assert_exit(0, "-V")
        for cmd in ("spawn", "close", "ls", "focus", "open", "ide", "prune", "doctor"):
            self.assert_exit(0, cmd, "--help")
        self.assert_exit(0, "help", "spawn")

    def test_error_paths_exit_one(self):
        self.assert_exit(1, "bogus-command")
        self.assert_exit(1, "doctor", "--bogus")
        self.assert_exit(1, "spawn")  # missing <repo>
        self.assert_exit(1, "spawn", ".", "--prompt")  # missing value
        self.assert_exit(1, "spawn", ".", "-p")
        self.assert_exit(1, "spawn", ".", "-b")
        self.assert_exit(1, "spawn", ".", "-z")  # unknown short flag
        self.assert_exit(1, "focus")  # missing <workspace>
        self.assert_exit(1, "open", "--ide")  # missing value
        self.assert_exit(1, "open", "--ide", "emacs")  # unknown ide
        self.assert_exit(1, "open", "--bogus")
        self.assert_exit(1, "ls", "extra-arg")  # unexpected positional

    def test_ratio_is_validated_before_any_herdr_call(self):
        proc = self.assert_exit(1, "spawn", ".", "--ratio", "1.5")
        self.assertIn("--ratio must be a number between 0 and 1", proc.stderr)

    def test_version_prints_the_version(self):
        proc = self.assert_exit(0, "version")
        self.assertRegex(proc.stdout, r"^corral \d+\.\d+\.\d+$")

    def test_help_lists_every_command(self):
        proc = self.assert_exit(0, "help")
        for cmd in ("spawn", "ls", "focus", "open", "close", "prune", "doctor"):
            self.assertIn(cmd, proc.stdout)

    def test_alias_help_matches_target(self):
        self.assertEqual(run("ide", "--help").stdout, run("open", "--help").stdout)
        self.assertEqual(run("list", "--help").stdout, run("ls", "--help").stdout)


if __name__ == "__main__":
    unittest.main()
