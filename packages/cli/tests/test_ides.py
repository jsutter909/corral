"""IDE mapping and Remote-SSH URI construction."""

import unittest

from corral.ides import encode_path, find_ide, remote_uri


class IdeRegistryTests(unittest.TestCase):
    def test_vscode_maps_to_code_cli(self):
        ide = find_ide("vscode")
        self.assertIsNotNone(ide)
        self.assertEqual((ide.cli, ide.scheme, ide.app), ("code", "vscode", "Visual Studio Code"))

    def test_code_is_accepted_for_vscode(self):
        self.assertEqual(find_ide("code").name, "vscode")

    def test_cursor_maps_to_cursor_cli(self):
        ide = find_ide("cursor")
        self.assertEqual((ide.cli, ide.scheme, ide.app), ("cursor", "cursor", "Cursor"))

    def test_unknown_ide_is_rejected(self):
        self.assertIsNone(find_ide("emacs"))


class RemoteUriTests(unittest.TestCase):
    def test_plain_paths_pass_through_unencoded(self):
        path = "/home/jake/.herdr/worktrees/app/agent-fix"
        self.assertEqual(encode_path(path), path)

    def test_uri_hostile_chars_are_percent_encoded(self):
        self.assertEqual(encode_path("/home/j/a b#c?d"), "/home/j/a%20b%23c%3Fd")

    def test_vscode_remote_uri(self):
        self.assertEqual(
            remote_uri(find_ide("vscode"), "devbox", "/home/jake/wt"),
            "vscode://vscode-remote/ssh-remote+devbox/home/jake/wt",
        )

    def test_cursor_remote_uri_encodes_the_path(self):
        self.assertEqual(
            remote_uri(find_ide("cursor"), "devbox", "/home/jake/my wt"),
            "cursor://vscode-remote/ssh-remote+devbox/home/jake/my%20wt",
        )


if __name__ == "__main__":
    unittest.main()
