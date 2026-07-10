"""The monitor server: state snapshot (agents joined to held resources),
action dispatch (JSON body -> the real command), and HTTP routing."""

import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest import mock

from corral import monitor, resources
from corral.commands import Context
from corral.settings import Settings
from corral.ui import CorralError
from corral.workspaces import Workspace, Worktree


class FakeHerdr:
    """Just the surface snapshot/focus need, recording focus calls."""

    def __init__(self, workspaces):
        self._workspaces = workspaces
        self.focused = []

    def workspace_list(self):
        return list(self._workspaces)

    def workspace_focus(self, workspace_id):
        self.focused.append(workspace_id)

    def require_server(self):
        pass

    def current_workspace(self):
        return ""


def agent_ws(wid, label, worktree_path):
    return Workspace(
        id=wid,
        label=label,
        agent_status="running",
        worktree=Worktree(checkout_path=worktree_path, is_linked=True, repo_name="app"),
    )


class MonitorTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmp, ignore_errors=True))
        self.wt_dir = os.path.join(self.tmp, "worktrees")
        self.db = os.path.join(self.tmp, "resources.db")
        env = {
            "HOME": self.tmp,
            "CORRAL_CONFIG": "/nonexistent/config.sh",
            "CORRAL_WORKTREES_DIR": self.wt_dir,
            "CORRAL_RESOURCES_DB": self.db,
        }
        self.settings = Settings.load(env)

    def ctx(self, workspaces=()):
        return Context(settings=self.settings, herdr=FakeHerdr(list(workspaces)))

    def wt(self, *parts):
        """A worktree path that actually exists (git calls run with cwd=path)."""
        path = os.path.join(self.wt_dir, *parts)
        os.makedirs(path, exist_ok=True)
        return path

    def seed_pool(self, pool, items, holder_for=None):
        """Create a pool; optionally acquire its first item as `holder_for`."""
        conn = resources.connect(self.db)
        try:
            resources.add_items(conn, pool, items, "")
            if holder_for:
                resources.try_acquire(conn, pool, holder_for)
        finally:
            conn.close()


class SnapshotTests(MonitorTestBase):
    def test_agent_is_joined_to_the_resources_it_holds(self):
        wt = self.wt("app", "feature")
        holder = resources.holder_for_worktree(self.wt_dir, wt)
        self.assertEqual(holder, "ws:app/feature")
        self.seed_pool("ports", ["3000", "3001"], holder_for=holder)

        state = monitor.snapshot(self.ctx([agent_ws("w1", "feature", wt)]))

        self.assertEqual(len(state["agents"]), 1)
        agent = state["agents"][0]
        self.assertEqual(agent["id"], "w1")
        self.assertEqual(agent["holder"], "ws:app/feature")
        held = agent["resources"]
        self.assertEqual([r["name"] for r in held], ["3000"])
        self.assertEqual(held[0]["pool"], "ports")

    def test_resources_held_by_other_agents_are_not_attributed(self):
        wt_a = self.wt("app", "a")
        wt_b = self.wt("app", "b")
        self.seed_pool("ports", ["3000"], holder_for="ws:app/b")

        state = monitor.snapshot(
            self.ctx([agent_ws("w1", "a", wt_a), agent_ws("w2", "b", wt_b)])
        )
        by_id = {a["id"]: a for a in state["agents"]}
        self.assertEqual(by_id["w1"]["resources"], [])
        self.assertEqual([r["name"] for r in by_id["w2"]["resources"]], ["3000"])

    def test_pools_summary_counts_held_and_free(self):
        self.seed_pool("ports", ["3000", "3001", "3002"], holder_for="ws:app/x")
        state = monitor.snapshot(self.ctx())
        pool = next(p for p in state["pools"] if p["name"] == "ports")
        self.assertEqual(pool["total"], 3)
        self.assertEqual(pool["held"], 1)
        self.assertEqual(pool["free"], 2)


class ActionDispatchTests(MonitorTestBase):
    def test_spawn_argv_adds_no_focus_unless_requested(self):
        with mock.patch("corral.commands.spawn.run") as run:
            run.return_value = 0
            monitor.perform(self.ctx(), "spawn", {"repo": "~/dev/app", "agent": "codex"})
            args = run.call_args[0][1]
            self.assertEqual(args["repo"], "~/dev/app")
            self.assertEqual(args["agent"], "codex")
            self.assertTrue(args["no_focus"])

    def test_spawn_argv_keeps_focus_when_requested(self):
        with mock.patch("corral.commands.spawn.run") as run:
            run.return_value = 0
            monitor.perform(self.ctx(), "spawn", {"repo": ".", "focus": True})
            self.assertFalse(run.call_args[0][1]["no_focus"])

    def test_spawn_requires_repo(self):
        with self.assertRaises(CorralError):
            monitor.perform(self.ctx(), "spawn", {})

    def test_close_forces_and_passes_workspace(self):
        with mock.patch("corral.commands.close.run") as run:
            run.return_value = 0
            monitor.perform(self.ctx(), "close", {"workspace": "w4"})
            args = run.call_args[0][1]
            self.assertEqual(args["workspace"], "w4")
            self.assertTrue(args["force"])

    def test_focus_end_to_end(self):
        ctx = self.ctx([agent_ws("w1", "feature", self.wt("app", "feature"))])
        # FakeHerdr stands in for the daemon; the real herdr binary isn't needed
        # (and isn't installed on CI), so stub the dependency check.
        with mock.patch("corral.commands.focus.require_deps"):
            result = monitor.perform(ctx, "focus", {"workspace": "w1"})
        self.assertTrue(result["ok"])
        self.assertEqual(ctx.herdr.focused, ["w1"])

    def test_release_end_to_end(self):
        self.seed_pool("ports", ["3000"], holder_for="ws:app/x")
        monitor.perform(self.ctx(), "release", {"pool": "ports", "item": "3000"})
        conn = resources.connect(self.db)
        try:
            row = next(r for r in resources.list_rows(conn) if r["name"] == "3000")
        finally:
            conn.close()
        self.assertEqual(row["state"], "free")

    def test_unknown_action(self):
        with self.assertRaises(CorralError):
            monitor.perform(self.ctx(), "bogus", {})


class HttpRoutingTests(MonitorTestBase):
    def _serve(self, workspaces=()):
        server = monitor.MonitorServer(("127.0.0.1", 0), self.ctx(workspaces))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server, f"http://127.0.0.1:{server.server_address[1]}"

    def _get(self, url):
        with urllib.request.urlopen(url, timeout=5) as resp:
            return resp.status, json.loads(resp.read())

    def _post(self, url, body):
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def test_index_is_served(self):
        _, base = self._serve()
        with urllib.request.urlopen(base + "/", timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn("text/html", resp.headers["Content-Type"])
            self.assertIn(b"corral monitor", resp.read())

    def test_meta_lists_agents(self):
        _, base = self._serve()
        status, data = self._get(base + "/api/meta")
        self.assertEqual(status, 200)
        self.assertIn("claude", [a["name"] for a in data["agents"]])

    def test_state_reports_agents(self):
        wt = self.wt("app", "feature")
        _, base = self._serve([agent_ws("w1", "feature", wt)])
        status, data = self._get(base + "/api/state")
        self.assertEqual(status, 200)
        self.assertEqual([a["id"] for a in data["agents"]], ["w1"])

    def test_focus_action_over_http(self):
        wt = self.wt("app", "feature")
        server, base = self._serve([agent_ws("w1", "feature", wt)])
        # See test_focus_end_to_end: the handler runs focus.run in this process,
        # so stub the herdr-binary check that CI can't satisfy.
        with mock.patch("corral.commands.focus.require_deps"):
            status, data = self._post(base + "/api/focus", {"workspace": "w1"})
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(server.ctx.herdr.focused, ["w1"])

    def test_bad_action_is_a_client_error(self):
        _, base = self._serve()
        status, data = self._post(base + "/api/nope", {})
        self.assertEqual(status, 400)
        self.assertIn("unknown action", data["error"])

    def test_spawn_without_repo_is_a_client_error(self):
        _, base = self._serve()
        status, data = self._post(base + "/api/spawn", {})
        self.assertEqual(status, 400)
        self.assertIn("repo", data["error"])

    def test_unknown_path_404(self):
        _, base = self._serve()
        status, data = self._post(base + "/nope", {})
        self.assertEqual(status, 404)


if __name__ == "__main__":
    unittest.main()
