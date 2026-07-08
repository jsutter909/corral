"""Generated artifacts: checked-in copies must be fresh, and every artifact
must carry the do-not-edit banner. This is the invariant that lets the docs
and the omz plugin be code-generated instead of hand-maintained."""

import shutil
import subprocess
import unittest

from corral.generate import artifacts, check_all
from corral.paths import REPO_ROOT


class FreshnessTests(unittest.TestCase):
    def test_checked_in_artifacts_match_the_registries(self):
        self.assertTrue(
            check_all(),
            msg="generated artifacts are stale — run: make generate",
        )

    def test_every_artifact_declares_it_is_generated(self):
        for artifact in artifacts():
            content = artifact.render()
            self.assertIn("GENERATED FILE", content, msg=artifact.path)

    def test_completion_keeps_its_compdef_first_line(self):
        for artifact in artifacts():
            if artifact.path.endswith("_corral"):
                first = artifact.render().splitlines()[0]
                self.assertEqual(first, "#compdef corral ccd")


class ZshSyntaxTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("zsh"), "zsh not installed")
    def test_generated_zsh_parses(self):
        for name in ("_corral", "corral.plugin.zsh"):
            path = REPO_ROOT / "packages" / "omz-plugin" / name
            proc = subprocess.run(
                ["zsh", "-n", str(path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            self.assertEqual(proc.returncode, 0, msg=f"{name}: {proc.stdout}")


if __name__ == "__main__":
    unittest.main()
