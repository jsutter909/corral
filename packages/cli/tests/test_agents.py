"""Launch-string construction — ported one-for-one from the bash smoke tests."""

import unittest

from corral.agents import launch_command, sh_quote


class LaunchCommandTests(unittest.TestCase):
    def test_agent_only(self):
        self.assertEqual(launch_command("claude"), "claude")

    def test_setup_then_agent(self):
        self.assertEqual(
            launch_command("claude", run_setup=True),
            "bash .corral/setup.sh && claude",
        )

    def test_setup_plus_claude_flags(self):
        self.assertEqual(
            launch_command("claude", model="opus", permission_mode="plan", run_setup=True),
            "bash .corral/setup.sh && claude --model opus --permission-mode plan",
        )

    def test_setup_with_agent_none(self):
        self.assertEqual(launch_command("none", run_setup=True), "bash .corral/setup.sh")

    def test_nothing_to_run(self):
        self.assertEqual(launch_command("none"), "")

    def test_non_claude_agent_ignores_model(self):
        self.assertEqual(
            launch_command("codex", model="opus", run_setup=True),
            "bash .corral/setup.sh && codex",
        )

    def test_prompt_is_quoted(self):
        self.assertEqual(
            launch_command("claude", prompt="fix the tests"),
            "claude 'fix the tests'",
        )

    def test_setup_plus_prompt(self):
        self.assertEqual(
            launch_command("claude", prompt="fix the tests", run_setup=True),
            "bash .corral/setup.sh && claude 'fix the tests'",
        )

    def test_prompt_quote_escaping(self):
        self.assertEqual(
            launch_command("claude", prompt="it's broken"),
            "claude 'it'\\''s broken'",
        )

    def test_prompt_dropped_for_agent_none(self):
        self.assertEqual(
            launch_command("none", prompt="fix the tests", run_setup=True),
            "bash .corral/setup.sh",
        )


class ShQuoteTests(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(sh_quote("abc"), "'abc'")

    def test_embedded_single_quote(self):
        self.assertEqual(sh_quote("it's"), "'it'\\''s'")


if __name__ == "__main__":
    unittest.main()
