"""corral resource end-to-end through bin/corral — happy path, JSON output,
holder override, exhaustion, and --wait, against a temp database (no herdr
server needed: resource never talks to herdr)."""

import json
import os
import subprocess
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CORRAL = os.path.join(HERE, os.pardir, "bin", "corral")


class ResourceCommandTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = os.path.join(self.tmp.name, "resources.db")
        # cwd outside any git repo so no .corral/resources.json auto-syncs in.
        self.cwd = os.path.join(self.tmp.name, "cwd")
        os.makedirs(self.cwd)

    def corral(self, *args, cwd=None):
        env = dict(
            os.environ,
            CORRAL_CONFIG="/nonexistent/corral-config.sh",
            CORRAL_RESOURCES_DB=self.db,
            CORRAL_WORKTREES_DIR=os.path.join(self.tmp.name, "worktrees"),
        )
        return subprocess.run(
            [CORRAL, "resource", *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            cwd=cwd or self.cwd,
        )

    def ok(self, *args, **kwargs):
        proc = self.corral(*args, **kwargs)
        self.assertEqual(
            proc.returncode, 0,
            msg=f"corral resource {' '.join(args)} failed\nstderr: {proc.stderr}",
        )
        return proc

    def fail(self, *args, **kwargs):
        proc = self.corral(*args, **kwargs)
        self.assertEqual(
            proc.returncode, 1,
            msg=f"corral resource {' '.join(args)} unexpectedly exited "
            f"{proc.returncode}\nstderr: {proc.stderr}",
        )
        return proc

    def test_add_acquire_ls_release_rm_happy_path(self):
        self.ok("add", "ports", "3000-3001")
        proc = self.ok("acquire", "ports", "--as", "h1")
        self.assertEqual(proc.stdout.strip(), "3000")

        rows = [
            line.split("\t")
            for line in self.ok("ls", "--tsv").stdout.strip().splitlines()
        ]
        self.assertEqual(rows[0][:4], ["ports", "3000", "held", "h1"])
        self.assertEqual(rows[1][:4], ["ports", "3001", "free", ""])

        self.ok("release", "ports/3000", "--as", "h1")
        rows = self.ok("ls", "--tsv").stdout
        self.assertNotIn("held", rows)
        self.ok("rm", "ports")
        self.assertEqual(self.ok("ls", "--tsv").stdout.strip(), "")

    def test_acquire_json_carries_data(self):
        self.ok("add", "apps", "a1", "--data", '{"api_key": "k1"}')
        record = json.loads(self.ok("acquire", "apps", "--json", "--as", "h1").stdout)
        self.assertEqual(record["name"], "a1")
        self.assertEqual(record["data"], {"api_key": "k1"})
        self.assertEqual(record["holder"], "h1")

    def test_default_holder_is_user_host_cwd_outside_worktrees(self):
        self.ok("add", "ports", "3000")
        self.ok("acquire", "ports")
        holder = self.ok("ls", "--tsv").stdout.strip().split("\t")[3]
        self.assertRegex(holder, r"^[^@]+@[^:]+:/")

    def test_worktree_cwd_records_ws_holder(self):
        worktree = os.path.join(self.tmp.name, "worktrees", "webapp", "fix-1")
        os.makedirs(worktree)
        self.ok("add", "ports", "3000")
        self.ok("acquire", "ports", cwd=worktree)
        holder = self.ok("ls", "--tsv").stdout.strip().split("\t")[3]
        self.assertEqual(holder, "ws:webapp/fix-1")

    def test_exhaustion_fails_fast_with_holders(self):
        self.ok("add", "ports", "3000")
        self.ok("acquire", "ports", "--as", "h1")
        proc = self.fail("acquire", "ports", "--as", "h2")
        self.assertIn("exhausted", proc.stderr)
        self.assertIn("h1", proc.stderr)

    def test_wait_gives_up_after_the_deadline(self):
        self.ok("add", "ports", "3000")
        self.ok("acquire", "ports", "--as", "h1")
        start = time.monotonic()
        proc = self.fail("acquire", "ports", "--as", "h2", "--wait=1")
        elapsed = time.monotonic() - start
        self.assertIn("gave up waiting", proc.stderr)
        self.assertGreaterEqual(elapsed, 0.9)
        self.assertLess(elapsed, 10)

    def test_wait_picks_up_a_freed_item(self):
        self.ok("add", "ports", "3000")
        self.ok("acquire", "ports", "--as", "h1")
        env = dict(
            os.environ,
            CORRAL_CONFIG="/nonexistent/corral-config.sh",
            CORRAL_RESOURCES_DB=self.db,
        )
        waiter = subprocess.Popen(
            [CORRAL, "resource", "acquire", "ports", "--as", "h2", "--wait=15"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            cwd=self.cwd,
        )
        time.sleep(1.0)
        self.ok("release", "ports/3000", "--as", "h1")
        stdout, stderr = waiter.communicate(timeout=15)
        self.assertEqual(waiter.returncode, 0, stderr)
        self.assertEqual(stdout.strip(), "3000")

    def test_release_all_returns_everything_the_holder_has(self):
        self.ok("add", "ports", "3000-3001")
        self.ok("add", "apps", "a1")
        self.ok("acquire", "ports", "--as", "h1")
        self.ok("acquire", "apps", "--as", "h1")
        self.ok("acquire", "ports", "--as", "h2")
        self.ok("release", "--all", "--as", "h1")
        held = [
            line.split("\t")
            for line in self.ok("ls", "--tsv").stdout.strip().splitlines()
            if "\theld\t" in line
        ]
        self.assertEqual([(r[0], r[1], r[3]) for r in held], [("ports", "3001", "h2")])

    def test_sync_from_a_repo_resources_file(self):
        repo = os.path.join(self.tmp.name, "webapp")
        os.makedirs(os.path.join(repo, ".corral"))
        subprocess.run(["git", "init", "-q", repo], check=True)
        with open(os.path.join(repo, ".corral", "resources.json"), "w") as fh:
            fh.write('{"ports": {"range": [3000, 3001]}}')

        self.ok("sync", cwd=repo)
        # Auto-sync also happens on acquire from inside the repo.
        proc = self.ok("acquire", "ports", cwd=repo)
        self.assertEqual(proc.stdout.strip(), "3000")
        # From outside the repo the pool is still there (machine-wide DB).
        self.assertIn("ports\t3001\tfree", self.ok("ls", "--tsv").stdout)

    def test_worktrees_of_one_repo_share_the_pool_source(self):
        # Two linked worktrees of the same repo must not fight over pool
        # ownership: the source is keyed to the main checkout.
        repo = os.path.join(self.tmp.name, "webapp")
        os.makedirs(os.path.join(repo, ".corral"))
        with open(os.path.join(repo, ".corral", "resources.json"), "w") as fh:
            fh.write('{"ports": {"range": [3000, 3001]}}')
        git_env = dict(
            os.environ,
            GIT_CONFIG_GLOBAL="/dev/null",
            GIT_CONFIG_SYSTEM="/dev/null",
            GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
            GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t",
        )
        def git(*args, cwd=repo):
            subprocess.run(
                ["git", *args], cwd=cwd, check=True, env=git_env,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        git("init", "-q")
        git("add", "-A")
        git("commit", "-qm", "init")
        wt1 = os.path.join(self.tmp.name, "wt1")
        wt2 = os.path.join(self.tmp.name, "wt2")
        git("worktree", "add", "-q", wt1, "-b", "b1")
        git("worktree", "add", "-q", wt2, "-b", "b2")

        first = self.ok("acquire", "ports", "--as", "h1", cwd=wt1)
        second = self.ok("acquire", "ports", "--as", "h2", cwd=wt2)
        self.assertNotIn("skipping", second.stderr)  # no cross-repo conflict
        self.assertEqual(
            {first.stdout.strip(), second.stdout.strip()}, {"3000", "3001"}
        )

    def test_sync_outside_a_repo_errors(self):
        proc = self.fail("sync")
        self.assertIn("not inside a git repo", proc.stderr)


if __name__ == "__main__":
    unittest.main()
