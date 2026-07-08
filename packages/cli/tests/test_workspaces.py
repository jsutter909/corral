"""Workspace resolution and the ownership invariant."""

import unittest

from corral.ui import CorralError
from corral.workspaces import Workspace, Worktree, resolve_workspace

WT_DIR = "/home/t/.herdr/worktrees"


def ws(id, label, path=None, linked=True):
    worktree = None
    if path is not None:
        worktree = Worktree(checkout_path=path, is_linked=linked, repo_name="app")
    return Workspace(id=id, label=label, agent_status="idle", worktree=worktree)


class OwnershipTests(unittest.TestCase):
    def test_linked_worktree_under_dir_is_owned(self):
        self.assertTrue(ws("w1", "a", f"{WT_DIR}/app/x").is_corral_owned(WT_DIR))

    def test_primary_checkout_is_never_owned(self):
        # is_linked_worktree=false — the user's main clone.
        self.assertFalse(
            ws("w1", "a", f"{WT_DIR}/app/x", linked=False).is_corral_owned(WT_DIR)
        )

    def test_hand_made_worktree_outside_dir_is_not_owned(self):
        self.assertFalse(ws("w1", "a", "/home/t/dev/app-wt").is_corral_owned(WT_DIR))

    def test_prefix_match_is_path_aware(self):
        # /home/t/.herdr/worktrees-evil must not satisfy the prefix test.
        self.assertFalse(ws("w1", "a", f"{WT_DIR}-evil/x").is_corral_owned(WT_DIR))

    def test_workspace_without_worktree_is_not_owned(self):
        self.assertFalse(ws("w1", "a").is_corral_owned(WT_DIR))


class ResolveTests(unittest.TestCase):
    def setUp(self):
        self.workspaces = [
            ws("w4", "checkout-fix", f"{WT_DIR}/app/a"),
            ws("w7", "tax", f"{WT_DIR}/app/b"),
            ws("w9", "tax", f"{WT_DIR}/app/c"),
        ]

    def test_resolves_by_id(self):
        self.assertEqual(resolve_workspace("w4", self.workspaces).id, "w4")

    def test_resolves_by_unique_label(self):
        self.assertEqual(resolve_workspace("checkout-fix", self.workspaces).id, "w4")

    def test_exact_id_match_beats_labels(self):
        workspaces = self.workspaces + [ws("checkout-fix", "other", f"{WT_DIR}/x")]
        self.assertEqual(resolve_workspace("checkout-fix", workspaces).id, "checkout-fix")

    def test_ambiguous_label_raises(self):
        with self.assertRaisesRegex(CorralError, "matches multiple workspaces"):
            resolve_workspace("tax", self.workspaces)

    def test_no_match_raises(self):
        with self.assertRaisesRegex(CorralError, "no workspace matching"):
            resolve_workspace("nope", self.workspaces)


if __name__ == "__main__":
    unittest.main()
