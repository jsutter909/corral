"""Unit tests for the pure SSH command builders in corral.remote.

These need no network — they assert the exact argv / shell strings corral would
run, plus the CORRAL_REMOTE-stripping that keeps a copied config from pointing a
remote at a further host."""

import unittest

from corral import remote


class BuilderTests(unittest.TestCase):
    def test_ssh_args(self):
        self.assertEqual(remote.ssh_args("devbox", "echo", "hi"), ["ssh", "devbox", "echo", "hi"])

    def test_login_shell_wraps_in_bash_lc(self):
        self.assertEqual(
            remote.login_shell("user@host", "corral start --no-attach"),
            ["ssh", "user@host", "bash", "-lc", "corral start --no-attach"],
        )

    def test_install_command_is_conditional(self):
        cmd = remote.install_command()
        self.assertTrue(cmd.startswith("command -v corral >/dev/null 2>&1 || curl -fsSL "))
        self.assertIn(remote.INSTALL_URL, cmd)
        self.assertTrue(cmd.endswith("| bash"))

    def test_copy_config_command_makes_dir_then_writes(self):
        self.assertEqual(
            remote.copy_config_command(),
            'mkdir -p "$HOME/.config/corral" && cat > "$HOME/.config/corral/config.sh"',
        )

    def test_forward_args_plain_ssh(self):
        argv = remote.forward_args("devbox", 8477, use_autossh=False)
        self.assertEqual(argv[0], "ssh")
        self.assertIn("-L", argv)
        self.assertIn("8477:127.0.0.1:8477", argv)
        self.assertIn("ServerAliveInterval=15", argv)
        self.assertEqual(argv[-1], "devbox")

    def test_forward_args_autossh_autoreconnects(self):
        argv = remote.forward_args("devbox", 8477, use_autossh=True)
        self.assertEqual(argv[:3], ["autossh", "-M", "0"])
        self.assertIn("8477:127.0.0.1:8477", argv)
        self.assertIn("ServerAliveInterval=15", argv)
        self.assertEqual(argv[-1], "devbox")

    def test_seed_command(self):
        self.assertEqual(remote.seed_command(), "corral start --no-attach")


class FilterConfigTests(unittest.TestCase):
    def test_strips_corral_remote_assignment(self):
        text = "CORRAL_AGENT=claude\nCORRAL_REMOTE=devbox\nCORRAL_RATIO=0.4\n"
        out = remote.filter_config(text)
        self.assertNotIn("CORRAL_REMOTE", out)
        self.assertIn("CORRAL_AGENT=claude", out)
        self.assertIn("CORRAL_RATIO=0.4", out)

    def test_strips_export_and_indented_forms(self):
        text = "export CORRAL_REMOTE=devbox\n  CORRAL_REMOTE=other\nCORRAL_AGENT=claude\n"
        out = remote.filter_config(text)
        self.assertNotIn("CORRAL_REMOTE", out)
        self.assertIn("CORRAL_AGENT=claude", out)

    def test_keeps_unrelated_lines_and_trailing_newline(self):
        text = "# a comment\nCORRAL_AGENT=claude\n"
        self.assertEqual(remote.filter_config(text), text)

    def test_leaves_config_without_remote_untouched(self):
        text = "CORRAL_AGENT=claude\nCORRAL_MONITOR_PORT=9000\n"
        self.assertEqual(remote.filter_config(text), text)


class DryRunRunnerTests(unittest.TestCase):
    """Runners with dry_run=True must print and never shell out."""

    def setUp(self):
        self.calls = []
        self._orig = remote.subprocess.run
        remote.subprocess.run = lambda *a, **k: self.calls.append((a, k))
        self.addCleanup(lambda: setattr(remote.subprocess, "run", self._orig))

    def test_runners_do_not_execute_on_dry_run(self):
        self.assertTrue(remote.install_remote("devbox", dry_run=True))
        self.assertTrue(remote.copy_config_remote("devbox", "CORRAL_AGENT=claude\n", dry_run=True))
        self.assertTrue(remote.seed_monitor_remote("devbox", dry_run=True))
        self.assertTrue(remote.forward_port("devbox", 8477, dry_run=True))
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
