"""Settings precedence (defaults < config file < environment) and parsing."""

import os
import tempfile
import unittest

from corral.settings import Settings, parse_config_file


class ParseConfigFileTests(unittest.TestCase):
    def test_plain_assignments(self):
        values = parse_config_file("CORRAL_AGENT=codex\nCORRAL_RATIO=0.5\n", {})
        self.assertEqual(values["CORRAL_AGENT"], "codex")
        self.assertEqual(values["CORRAL_RATIO"], "0.5")

    def test_export_quotes_and_comments(self):
        text = (
            "# a comment\n"
            'export CORRAL_BASE="main"\n'
            "CORRAL_BRANCH_PREFIX='bot'   # trailing comment\n"
        )
        values = parse_config_file(text, {})
        self.assertEqual(values["CORRAL_BASE"], "main")
        self.assertEqual(values["CORRAL_BRANCH_PREFIX"], "bot")

    def test_home_expansion(self):
        values = parse_config_file(
            'CORRAL_WORKTREES_DIR="$HOME/.herdr/worktrees"\n', {"HOME": "/home/t"}
        )
        self.assertEqual(values["CORRAL_WORKTREES_DIR"], "/home/t/.herdr/worktrees")

    def test_arbitrary_shell_is_ignored(self):
        values = parse_config_file('if true; then\n  echo hi\nfi\nCORRAL_AGENT=x\n', {})
        self.assertEqual(list(values), ["CORRAL_AGENT"])


class SettingsLoadTests(unittest.TestCase):
    def _load(self, config_text=None, extra_env=None):
        env = {"HOME": "/home/t"}
        if config_text is not None:
            tmp = tempfile.NamedTemporaryFile(
                "w", suffix=".sh", delete=False, encoding="utf-8"
            )
            tmp.write(config_text)
            tmp.close()
            self.addCleanup(os.unlink, tmp.name)
            env["CORRAL_CONFIG"] = tmp.name
        env.update(extra_env or {})
        return Settings.load(env)

    def test_builtin_defaults(self):
        settings = self._load()
        self.assertEqual(settings.agent, "claude")
        self.assertEqual(settings.ratio, "0.4")
        self.assertEqual(settings.branch_prefix, "agent")
        self.assertEqual(settings.worktrees_dir, "/home/t/.herdr/worktrees")
        self.assertTrue(settings.setup_enabled)
        self.assertTrue(settings.cleanup_enabled)

    def test_config_file_overrides_defaults(self):
        settings = self._load("CORRAL_AGENT=codex\nCORRAL_SETUP=0\n")
        self.assertEqual(settings.agent, "codex")
        self.assertFalse(settings.setup_enabled)

    def test_environment_beats_config_file(self):
        settings = self._load(
            "CORRAL_AGENT=codex\n", extra_env={"CORRAL_AGENT": "droid"}
        )
        self.assertEqual(settings.agent, "droid")

    def test_missing_config_file_is_fine(self):
        settings = self._load(extra_env={"CORRAL_CONFIG": "/nonexistent/config.sh"})
        self.assertEqual(settings.agent, "claude")
        self.assertEqual(settings.config_path, "/nonexistent/config.sh")

    def test_describe_default_reports_live_value_or_empty_meaning(self):
        settings = self._load()
        self.assertEqual(settings.describe_default("agent"), "claude")
        self.assertEqual(settings.describe_default("model"), "Claude's default")
        self.assertEqual(settings.describe_default("base"), "current HEAD")


if __name__ == "__main__":
    unittest.main()
