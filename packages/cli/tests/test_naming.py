"""Branch slugs and prompt-derived branch names (with a stubbed claude CLI)."""

import os
import stat
import tempfile
import unittest
from unittest import mock

from corral.naming import branch_from_prompt, branch_slug


class BranchSlugTests(unittest.TestCase):
    def test_lowercases_and_hyphenates(self):
        self.assertEqual(branch_slug("Fix the TAX tests!"), "fix-the-tax-tests")

    def test_collapses_separators(self):
        self.assertEqual(branch_slug("  a -- b // c  "), "a-b-c")

    def test_caps_length_at_40(self):
        self.assertEqual(branch_slug("a" * 50), "a" * 40)

    def test_symbols_only_is_empty(self):
        self.assertEqual(branch_slug("!!! ???"), "")


class BranchFromPromptTests(unittest.TestCase):
    """spawn_branch_from_prompt semantics: the claude reply names the branch
    when the CLI succeeds, is sanitized when chatty, and the slugged prompt is
    the fallback when the CLI fails or is absent."""

    def _with_stub(self, body, prompt):
        with tempfile.TemporaryDirectory() as stub:
            if body is not None:
                path = os.path.join(stub, "claude")
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(body)
                os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)
            restricted = f"{stub}:/usr/bin:/bin"
            with mock.patch.dict(os.environ, {"PATH": restricted}):
                return branch_from_prompt(prompt)

    def test_llm_reply_names_the_branch(self):
        got = self._with_stub("#!/bin/sh\necho fix-tax-rounding\n", "fix the tax tests")
        self.assertEqual(got, "fix-tax-rounding")

    def test_chatty_reply_is_sanitized(self):
        got = self._with_stub('#!/bin/sh\necho "Sure! fix/tax"\n', "fix the tax tests")
        self.assertEqual(got, "sure-fix-tax")

    def test_failing_claude_falls_back_to_prompt_slug(self):
        got = self._with_stub("#!/bin/sh\nexit 1\n", "fix the tax tests")
        self.assertEqual(got, "fix-the-tax-tests")

    def test_no_claude_falls_back_to_prompt_slug(self):
        got = self._with_stub(None, "fix the tax tests")
        self.assertEqual(got, "fix-the-tax-tests")


if __name__ == "__main__":
    unittest.main()
