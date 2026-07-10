"""End-to-end tests for `corral resource` shared-resource checkout.

Simulates the real workflow of a simple web app whose dev servers each need one
port, with exactly two ports in the pool. A scratch git repo ("webapp") declares
`.corral/resources.json` and a `.corral/setup.sh` that reserves a port at spawn
time; herdr-style worktrees are laid out under CORRAL_WORKTREES_DIR so the pure
path-math holder detection tags each lease with `ws:webapp/<label>`.

Most cases drive the real CLI through bin/corral in a subprocess (hermetic: a
temp resources DB, an isolated CORRAL_CONFIG, and a temp worktrees root). The
auto-release-on-close path is exercised in-process via corral.hooks with a fake
herdr stub, since no herdr server is available.

Run: cd packages/cli && python3 -m unittest tests.test_e2e_resources -v
"""

import contextlib
import io
import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest

# tests/__init__.py puts packages/cli/src on sys.path, so `corral` imports work.
from corral import hooks, resources
from corral.settings import Settings

HERE = os.path.dirname(os.path.abspath(__file__))
CORRAL = os.path.join(HERE, os.pardir, "bin", "corral")

# --tsv column order emitted by `corral resource ls` (kept in sync with
# corral.commands.resource.COLUMNS).
COLUMNS = ("pool", "name", "state", "holder", "acquired_at")

RESOURCES_JSON = '{"ports": {"range": [3000, 3001]}}\n'

SETUP_SH = """#!/usr/bin/env bash
# What a real repo's .corral/setup.sh would do at spawn time: reserve one dev
# port for this workspace before the agent starts.
set -e
PORT=$(corral resource acquire ports)
echo "$PORT" > .dev-port
"""

SERVER_PY = "# trivial app; would serve on $DEV_PORT but never actually runs\n"

# git that ignores the developer's global/system config, so the suite is
# hermetic regardless of the host's git setup.
GIT_ENV = dict(
    os.environ,
    GIT_CONFIG_GLOBAL=os.devnull,
    GIT_CONFIG_SYSTEM=os.devnull,
    GIT_TERMINAL_PROMPT="0",
)


def run_git(cwd, *args):
    proc = subprocess.run(
        ["git", *args],
        cwd=cwd,
        env=GIT_ENV,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed (exit {proc.returncode}): {proc.stderr}"
        )
    return proc


class ResourceE2E(unittest.TestCase):
    """Shared scratch repo + worktrees (once), a fresh DB per test."""

    @classmethod
    def setUpClass(cls):
        # A temp worktrees root (realpath'd so it matches holder detection) that
        # is separate from the main clone — the main clone must never look like a
        # corral worktree.
        cls.wt_dir = os.path.realpath(tempfile.mkdtemp(prefix="corral-wt-"))
        cls.repo = os.path.realpath(tempfile.mkdtemp(prefix="corral-repo-"))
        # A plain non-git dir: querying `ls` from here means no auto-sync runs,
        # so read-only inspection never mutates the DB.
        cls.neutral = os.path.realpath(tempfile.mkdtemp(prefix="corral-neutral-"))
        cls.addClassCleanup(shutil.rmtree, cls.wt_dir, ignore_errors=True)
        cls.addClassCleanup(shutil.rmtree, cls.repo, ignore_errors=True)
        cls.addClassCleanup(shutil.rmtree, cls.neutral, ignore_errors=True)

        run_git(cls.repo, "init", "-q")
        run_git(cls.repo, "config", "user.email", "webapp@example.com")
        run_git(cls.repo, "config", "user.name", "Web App")
        os.makedirs(os.path.join(cls.repo, ".corral"))
        cls._write(os.path.join(cls.repo, "server.py"), SERVER_PY)
        cls._write(os.path.join(cls.repo, ".corral", "resources.json"), RESOURCES_JSON)
        setup = os.path.join(cls.repo, ".corral", "setup.sh")
        cls._write(setup, SETUP_SH)
        os.chmod(setup, 0o755)
        run_git(cls.repo, "add", "-A")
        run_git(cls.repo, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "init webapp")

        # Herdr-style worktrees: <wt_dir>/webapp/<label>, each a real checkout.
        cls.worktrees = {}
        for label in ("wt1", "wt2", "wt3"):
            path = os.path.join(cls.wt_dir, "webapp", label)
            run_git(cls.repo, "worktree", "add", "-q", path, "-b", label)
            cls.worktrees[label] = path

    @staticmethod
    def _write(path, text):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)

    def setUp(self):
        # A fresh database per test so no lease state leaks between methods.
        dbdir = tempfile.mkdtemp(prefix="corral-db-")
        self.addCleanup(shutil.rmtree, dbdir, ignore_errors=True)
        self.db = os.path.join(dbdir, "resources.db")

    # -- helpers ------------------------------------------------------------

    def env(self):
        return dict(
            os.environ,
            CORRAL_CONFIG="/nonexistent/corral-config.sh",
            CORRAL_WORKTREES_DIR=self.wt_dir,
            CORRAL_RESOURCES_DB=self.db,
            # Put bin/ on PATH so setup.sh's bare `corral` resolves.
            PATH=os.path.dirname(CORRAL) + os.pathsep + os.environ.get("PATH", ""),
        )

    def run_corral(self, *args, cwd):
        return subprocess.run(
            [CORRAL, *args],
            cwd=cwd,
            env=self.env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    def run_setup(self, label):
        """Run the repo's .corral/setup.sh in a worktree, like spawn does."""
        return subprocess.run(
            ["bash", ".corral/setup.sh"],
            cwd=self.worktrees[label],
            env=self.env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    def acquire(self, label):
        """Acquire one port from a worktree; return the port string."""
        proc = self.run_corral("resource", "acquire", "ports", cwd=self.worktrees[label])
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        return proc.stdout.strip()

    def dev_port(self, label):
        with open(os.path.join(self.worktrees[label], ".dev-port"), encoding="utf-8") as fh:
            return fh.read().strip()

    def leases(self):
        """All items as {name: row}, read via `ls --tsv` from a non-repo cwd
        (so no auto-sync fires and the read is side-effect free)."""
        proc = self.run_corral("resource", "ls", "--tsv", cwd=self.neutral)
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        return self._parse(proc.stdout)

    def settings(self):
        return Settings(values={"resources_db": self.db, "worktrees_dir": self.wt_dir})

    # -- tests --------------------------------------------------------------

    def test_single_worktree_startup(self):
        """setup.sh reserves a port; the lease is tagged to the workspace, and
        the resources.json auto-sync happened with no manual `add`."""
        proc = self.run_setup("wt1")
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        port = self.dev_port("wt1")
        self.assertIn(port, {"3000", "3001"})

        rows = self.leases()
        self.assertIn(port, rows)
        self.assertEqual(rows[port]["state"], "held")
        self.assertEqual(rows[port]["holder"], "ws:webapp/wt1")
        # Both declared ports exist (auto-sync from setup.sh's acquire).
        self.assertEqual(set(rows), {"3000", "3001"})

    def test_two_worktrees_get_distinct_ports(self):
        proc1 = self.run_setup("wt1")
        self.assertEqual(proc1.returncode, 0, msg=proc1.stderr)
        proc2 = self.run_setup("wt2")
        self.assertEqual(proc2.returncode, 0, msg=proc2.stderr)
        port1, port2 = self.dev_port("wt1"), self.dev_port("wt2")
        self.assertNotEqual(port1, port2)
        self.assertEqual({port1, port2}, {"3000", "3001"})

        rows = self.leases()
        self.assertEqual(rows[port1]["holder"], "ws:webapp/wt1")
        self.assertEqual(rows[port2]["holder"], "ws:webapp/wt2")
        self.assertEqual(rows[port1]["state"], "held")
        self.assertEqual(rows[port2]["state"], "held")

    def test_pool_exhausted_blocks_third(self):
        # Worktrees are shared across tests; clear any stale .dev-port so the
        # "no port written" assertion reflects only this run.
        stale = os.path.join(self.worktrees["wt3"], ".dev-port")
        if os.path.exists(stale):
            os.remove(stale)
        self.assertEqual(self.run_setup("wt1").returncode, 0)
        self.assertEqual(self.run_setup("wt2").returncode, 0)
        proc = self.run_setup("wt3")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("exhausted", proc.stderr)
        # holders are listed so an operator can see who to chase.
        self.assertIn("ws:webapp/wt1", proc.stderr)
        self.assertIn("ws:webapp/wt2", proc.stderr)
        # The agent would not have started: no port file was written.
        self.assertFalse(os.path.exists(os.path.join(self.worktrees["wt3"], ".dev-port")))

    def test_free_on_close_returns_port(self):
        port1 = self.acquire("wt1")
        port2 = self.acquire("wt2")
        self.assertNotEqual(port1, port2)

        fake = FakeHerdr()
        with contextlib.redirect_stderr(io.StringIO()):
            ok = hooks.remove_workspace(
                fake, "w1", self.worktrees["wt1"],
                force=True, cleanup=False, settings=self.settings(),
            )
        self.assertTrue(ok)
        self.assertEqual(fake.removed, ["w1"])

        rows = self.leases()
        self.assertEqual(rows[port1]["state"], "free")
        self.assertEqual(rows[port1]["holder"], "")
        self.assertEqual(rows[port2]["state"], "held")  # wt2 untouched

        # The freed port is now available to a newly started worktree.
        proc = self.run_setup("wt3")
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        self.assertEqual(self.dev_port("wt3"), port1)

    def test_close_with_nothing_held_is_a_noop(self):
        port2 = self.acquire("wt2")  # DB has state, but wt1 holds nothing

        fake = FakeHerdr()
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            ok = hooks.remove_workspace(
                fake, "w9", self.worktrees["wt1"],
                force=True, cleanup=False, settings=self.settings(),
            )
        self.assertTrue(ok)
        self.assertEqual(fake.removed, ["w9"])
        self.assertNotIn("released", buf.getvalue())  # no resource messages

        rows = self.leases()  # DB untouched: wt2's lease survives
        self.assertEqual(rows[port2]["state"], "held")
        self.assertEqual(rows[port2]["holder"], "ws:webapp/wt2")

    def test_wait_acquires_when_a_port_is_freed(self):
        port1 = self.acquire("wt1")
        port2 = self.acquire("wt2")
        self.assertEqual({port1, port2}, {"3000", "3001"})

        waiter = subprocess.Popen(
            [CORRAL, "resource", "acquire", "ports", "--wait=20"],
            cwd=self.worktrees["wt3"],
            env=self.env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.addCleanup(lambda: waiter.poll() is None and waiter.kill())

        time.sleep(1.0)
        self.assertIsNone(waiter.poll(), "waiter should still be blocked")

        rel = self.run_corral("resource", "release", f"ports/{port1}", cwd=self.worktrees["wt1"])
        self.assertEqual(rel.returncode, 0, msg=rel.stderr)

        out, err = waiter.communicate(timeout=15)
        self.assertEqual(waiter.returncode, 0, msg=err)
        self.assertEqual(out.strip(), port1)  # the freed port

        # Both ports held again (wt3 took the freed one); --wait=1 gives up ~1s.
        start = time.monotonic()
        gave = self.run_corral("resource", "acquire", "ports", "--wait=1", cwd=self.worktrees["wt1"])
        elapsed = time.monotonic() - start
        self.assertEqual(gave.returncode, 1)
        self.assertIn("gave up", gave.stderr)
        self.assertLess(elapsed, 12, "should give up promptly, not wait forever")

    def test_explicit_release_returns_the_resource(self):
        port = self.acquire("wt1")
        rel = self.run_corral("resource", "release", f"ports/{port}", cwd=self.worktrees["wt1"])
        self.assertEqual(rel.returncode, 0, msg=rel.stderr)

        rows = self.leases()
        self.assertEqual(rows[port]["state"], "free")
        self.assertEqual(rows[port]["holder"], "")

    def test_resources_json_edit_propagates(self):
        wt1 = self.worktrees["wt1"]
        rjson = os.path.join(wt1, ".corral", "resources.json")
        try:
            held = self.acquire("wt1")  # holds one port (3000); the other is free
            free = "3001" if held == "3000" else "3000"

            # Shrink the checked-in file to a disjoint single port (uncommitted).
            self._write(rjson, '{"ports": {"range": [4000, 4000]}}\n')
            proc = self.run_corral("resource", "ls", "--tsv", cwd=wt1)
            self.assertEqual(proc.returncode, 0, msg=proc.stderr)
            rows = self._parse(proc.stdout)
            # Held-but-removed port is retired (never handed out, kept for its holder).
            self.assertEqual(rows[held]["state"], "retired")
            self.assertEqual(rows[held]["holder"], "ws:webapp/wt1")
            # Free removed port disappears; the newly declared one shows up free.
            self.assertNotIn(free, rows)
            self.assertIn("4000", rows)
            self.assertEqual(rows["4000"]["state"], "free")

            # Restore the file; the retired lease comes back and 4000 vanishes.
            self._write(rjson, RESOURCES_JSON)
            proc = self.run_corral("resource", "ls", "--tsv", cwd=wt1)
            self.assertEqual(proc.returncode, 0, msg=proc.stderr)
            rows = self._parse(proc.stdout)
            self.assertEqual(rows[held]["state"], "held")  # retired cleared
            self.assertEqual(rows[held]["holder"], "ws:webapp/wt1")
            self.assertIn(free, rows)
            self.assertNotIn("4000", rows)
        finally:
            self._write(rjson, RESOURCES_JSON)

    @staticmethod
    def _parse(tsv):
        rows = {}
        for line in tsv.splitlines():
            if not line:
                continue
            parts = line.split("\t")
            parts += [""] * (len(COLUMNS) - len(parts))
            row = dict(zip(COLUMNS, parts))
            rows[row["name"]] = row
        return rows


class FakeHerdr:
    """Records worktree removals; the only method remove_workspace calls."""

    def __init__(self):
        self.removed = []

    def worktree_remove(self, workspace_id):
        self.removed.append(workspace_id)


if __name__ == "__main__":
    unittest.main()
