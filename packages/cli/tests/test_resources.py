"""The shared-resource store: schema, acquire/release atomicity (including a
real cross-connection contention test), range expansion, resources.json sync
semantics, and holder detection."""

import json
import os
import tempfile
import threading
import unittest

from corral.resources import (
    PoolExhausted,
    add_items,
    connect,
    detect_holder,
    expand_items,
    holder_for_worktree,
    list_rows,
    parse_resources_file,
    release,
    release_all,
    release_pool,
    remove_item,
    remove_pool,
    sync_source,
    try_acquire,
)
from corral.ui import CorralError


class StoreCase(unittest.TestCase):
    """Base: a fresh temp-dir database per test."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = os.path.join(self.tmp.name, "state", "resources.db")
        self.conn = connect(self.db)
        self.addCleanup(self.conn.close)

    def states(self, pool=""):
        return {row["name"]: row["state"] for row in list_rows(self.conn, pool=pool)}


class SchemaTests(StoreCase):
    def test_connect_creates_parent_dirs_and_schema(self):
        self.assertTrue(os.path.isfile(self.db))
        version = self.conn.execute("PRAGMA user_version").fetchone()[0]
        self.assertEqual(version, 1)

    def test_newer_schema_is_refused(self):
        self.conn.execute("PRAGMA user_version = 99")
        with self.assertRaisesRegex(CorralError, "newer than this corral"):
            connect(self.db)

    def test_reopening_is_idempotent(self):
        connect(self.db).close()
        connect(self.db).close()


class ExpandItemsTests(unittest.TestCase):
    def test_range_expands_inclusively(self):
        self.assertEqual(expand_items(["3000-3002"]), ["3000", "3001", "3002"])

    def test_plain_tokens_stay_literal(self):
        self.assertEqual(expand_items(["8080", "dev-app-1"]), ["8080", "dev-app-1"])

    def test_backwards_range_is_rejected(self):
        with self.assertRaisesRegex(CorralError, "start exceeds end"):
            expand_items(["9-3"])

    def test_huge_range_is_rejected(self):
        with self.assertRaisesRegex(CorralError, "more than 4096"):
            expand_items(["1-9999"])

    def test_bad_names_are_rejected(self):
        for bad in ("a/b", "a:b", "a b", "", "-x"):
            with self.assertRaises(CorralError):
                expand_items([bad])


class AcquireReleaseTests(StoreCase):
    def setUp(self):
        super().setUp()
        add_items(self.conn, "ports", ["3000", "3001"], "")

    def test_acquires_lowest_free_item(self):
        record = try_acquire(self.conn, "ports", "h1")
        self.assertEqual(record["name"], "3000")
        self.assertEqual(record["holder"], "h1")
        self.assertEqual(try_acquire(self.conn, "ports", "h2")["name"], "3001")

    def test_exhaustion_carries_holder_counts(self):
        try_acquire(self.conn, "ports", "h1")
        try_acquire(self.conn, "ports", "h1")
        with self.assertRaises(PoolExhausted) as caught:
            try_acquire(self.conn, "ports", "h2")
        self.assertEqual(caught.exception.holders, [("h1", 2)])
        self.assertIn("exhausted", str(caught.exception))

    def test_unknown_pool_errors(self):
        with self.assertRaisesRegex(CorralError, "no pool 'nope'"):
            try_acquire(self.conn, "nope", "h1")

    def test_empty_pool_errors(self):
        add_items(self.conn, "empty", [], "")
        with self.assertRaisesRegex(CorralError, "has no items"):
            try_acquire(self.conn, "empty", "h1")

    def test_release_frees_the_item(self):
        try_acquire(self.conn, "ports", "h1")
        release(self.conn, "ports", "3000", "h1", force=False)
        self.assertEqual(self.states()["3000"], "free")

    def test_release_of_a_free_item_errors(self):
        with self.assertRaisesRegex(CorralError, "not checked out"):
            release(self.conn, "ports", "3000", "h1", force=False)

    def test_release_of_someone_elses_item_needs_force(self):
        try_acquire(self.conn, "ports", "h1")
        with self.assertRaisesRegex(CorralError, "held by h1"):
            release(self.conn, "ports", "3000", "h2", force=False)
        release(self.conn, "ports", "3000", "h2", force=True)
        self.assertEqual(self.states()["3000"], "free")

    def test_release_pool_and_release_all(self):
        add_items(self.conn, "apps", ["a1"], "")
        try_acquire(self.conn, "ports", "h1")
        try_acquire(self.conn, "ports", "h2")
        try_acquire(self.conn, "apps", "h1")
        self.assertEqual(release_pool(self.conn, "ports", "h1"), ["3000"])
        self.assertEqual(release_all(self.conn, "h1"), [("apps", "a1")])
        self.assertEqual(release_all(self.conn, "h1"), [])  # idempotent
        self.assertEqual(self.states("ports")["3001"], "held")  # h2 untouched

    def test_data_round_trips_through_acquire(self):
        payload = json.dumps({"api_key": "k1"}, sort_keys=True)
        add_items(self.conn, "apps", ["a1"], payload)
        self.assertEqual(try_acquire(self.conn, "apps", "h1")["data"], payload)

    def test_duplicate_item_errors(self):
        with self.assertRaisesRegex(CorralError, "already exists"):
            add_items(self.conn, "ports", ["3000"], "")

    def test_rm_pool_refuses_held_items_without_force(self):
        try_acquire(self.conn, "ports", "h1")
        with self.assertRaisesRegex(CorralError, "checked-out items"):
            remove_pool(self.conn, "ports", force=False)
        self.assertEqual(remove_pool(self.conn, "ports", force=True), 2)
        self.assertEqual(list_rows(self.conn), [])

    def test_rm_item_refuses_held_without_force(self):
        try_acquire(self.conn, "ports", "h1")
        with self.assertRaisesRegex(CorralError, "held by h1"):
            remove_item(self.conn, "ports", "3000", force=False)
        remove_item(self.conn, "ports", "3001", force=False)
        remove_item(self.conn, "ports", "3000", force=True)
        self.assertEqual(self.states("ports"), {"": "empty"})


class ContentionTests(StoreCase):
    """Separate connections exercise the same file-level BEGIN IMMEDIATE
    locking as separate processes."""

    def test_concurrent_acquire_never_double_books(self):
        add_items(self.conn, "ports", [str(p) for p in range(3000, 3005)], "")
        results, errors = [], []
        barrier = threading.Barrier(16)

        def worker(i):
            conn = connect(self.db)
            try:
                barrier.wait()
                results.append(try_acquire(conn, "ports", f"h{i}")["name"])
            except PoolExhausted:
                errors.append(i)
            finally:
                conn.close()

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(16)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(results), 5, f"acquired: {results}")
        self.assertEqual(len(set(results)), 5, f"double-booked: {results}")
        self.assertEqual(len(errors), 11)

    def test_acquire_release_cycles_end_fully_free(self):
        add_items(self.conn, "ports", ["3000", "3001", "3002"], "")

        def worker(i):
            conn = connect(self.db)
            try:
                for _ in range(5):
                    try:
                        record = try_acquire(conn, "ports", f"h{i}")
                    except PoolExhausted:
                        continue
                    release(conn, "ports", record["name"], f"h{i}", force=False)
            finally:
                conn.close()

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(
            set(self.states("ports").values()), {"free"}, self.states("ports")
        )


class HolderDetectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.wt_dir = os.path.join(self.tmp.name, "worktrees")

    def test_inside_a_worktree_yields_ws_holder(self):
        deep = os.path.join(self.wt_dir, "webapp", "fix-1", "src", "components")
        os.makedirs(deep)
        self.assertEqual(holder_for_worktree(self.wt_dir, deep), "ws:webapp/fix-1")
        self.assertEqual(detect_holder(self.wt_dir, deep), "ws:webapp/fix-1")

    def test_worktree_root_itself_yields_ws_holder(self):
        path = os.path.join(self.wt_dir, "webapp", "fix-1")
        os.makedirs(path)
        self.assertEqual(holder_for_worktree(self.wt_dir, path), "ws:webapp/fix-1")

    def test_repo_level_path_is_not_a_workspace(self):
        path = os.path.join(self.wt_dir, "webapp")
        os.makedirs(path)
        self.assertEqual(holder_for_worktree(self.wt_dir, path), "")

    def test_sibling_prefix_dir_is_not_a_workspace(self):
        evil = self.wt_dir + "-evil"
        deep = os.path.join(evil, "webapp", "fix-1")
        os.makedirs(deep)
        self.assertEqual(holder_for_worktree(self.wt_dir, deep), "")

    def test_outside_falls_back_to_user_host_cwd(self):
        outside = os.path.join(self.tmp.name, "elsewhere")
        os.makedirs(outside)
        holder = detect_holder(self.wt_dir, outside)
        self.assertRegex(holder, r"^[^@]+@[^:]+:/")
        self.assertTrue(holder.endswith(os.path.realpath(outside)))


class ParseResourcesFileTests(unittest.TestCase):
    def test_range_and_list_forms(self):
        pools = parse_resources_file(
            '{"ports": {"range": [3000, 3001]},'
            ' "apps": ["plain", {"name": "a1", "data": {"k": 1}}]}'
        )
        self.assertEqual(pools["ports"], [("3000", ""), ("3001", "")])
        self.assertEqual(pools["apps"], [("plain", ""), ("a1", '{"k": 1}')])

    def test_malformed_json_errors(self):
        with self.assertRaisesRegex(CorralError, "invalid JSON"):
            parse_resources_file("{nope")

    def test_bad_shapes_error(self):
        for text in (
            "[]",
            '{"p": 3}',
            '{"p": {"range": [1]}}',
            '{"p": {"range": ["a", "b"]}}',
            '{"p": [{"data": {}}]}',
            '{"p": ["dup", "dup"]}',
        ):
            with self.assertRaises(CorralError, msg=text):
                parse_resources_file(text)


class SyncTests(StoreCase):
    REPO = "/repos/webapp"

    def sync(self, text, source=REPO):
        return sync_source(self.conn, source, parse_resources_file(text))

    def test_file_pools_are_created_with_file_origin(self):
        summary = self.sync('{"ports": {"range": [3000, 3001]}}')
        self.assertEqual(summary["ports"]["added"], 2)
        rows = list_rows(self.conn, pool="ports")
        self.assertEqual([r["origin"] for r in rows], ["file", "file"])

    def test_resync_is_a_no_op(self):
        text = '{"ports": {"range": [3000, 3001]}}'
        self.sync(text)
        self.assertEqual(self.sync(text), {})

    def test_data_update_keeps_the_lease(self):
        self.sync('{"apps": [{"name": "a1", "data": {"v": 1}}]}')
        try_acquire(self.conn, "apps", "h1")
        summary = self.sync('{"apps": [{"name": "a1", "data": {"v": 2}}]}')
        self.assertEqual(summary["apps"]["updated"], 1)
        row = list_rows(self.conn, pool="apps")[0]
        self.assertEqual((row["state"], row["holder"]), ("held", "h1"))
        self.assertEqual(row["data"], '{"v": 2}')

    def test_removed_free_item_is_deleted(self):
        self.sync('{"ports": {"range": [3000, 3001]}}')
        self.sync('{"ports": {"range": [3000, 3000]}}')
        self.assertEqual(self.states("ports"), {"3000": "free"})

    def test_removed_held_item_is_retired_then_deleted_on_release(self):
        self.sync('{"ports": {"range": [3000, 3001]}}')
        try_acquire(self.conn, "ports", "h1")  # gets 3000
        self.sync('{"ports": {"range": [3001, 3001]}}')
        self.assertEqual(self.states("ports")["3000"], "retired")
        # Never handed out again: the only free item is 3001.
        self.assertEqual(try_acquire(self.conn, "ports", "h2")["name"], "3001")
        # Releasing a retired item removes it for good.
        self.assertTrue(release(self.conn, "ports", "3000", "h1", force=False))
        self.assertNotIn("3000", self.states("ports"))

    def test_re_declaring_a_retired_item_revives_it(self):
        self.sync('{"ports": {"range": [3000, 3000]}}')
        try_acquire(self.conn, "ports", "h1")
        self.sync('{"other": ["x"]}')  # ports gone from file -> 3000 retired
        self.assertEqual(self.states("ports")["3000"], "retired")
        self.sync('{"ports": {"range": [3000, 3000]}, "other": ["x"]}')
        self.assertEqual(self.states("ports")["3000"], "held")

    def test_cli_items_in_a_file_pool_survive_sync(self):
        self.sync('{"ports": {"range": [3000, 3000]}}')
        add_items(self.conn, "ports", ["9999"], "")
        self.sync('{"ports": {"range": [3001, 3001]}}')
        self.assertEqual(self.states("ports"), {"3001": "free", "9999": "free"})

    def test_pool_dropped_from_file_is_deleted_when_empty(self):
        self.sync('{"ports": {"range": [3000, 3001]}}')
        self.sync('{"other": ["x"]}')
        self.assertEqual([r["pool"] for r in list_rows(self.conn)], ["other"])

    def test_cli_pool_name_conflicts(self):
        add_items(self.conn, "ports", ["3000"], "")
        with self.assertRaisesRegex(CorralError, "created via the CLI"):
            self.sync('{"ports": {"range": [3000, 3001]}}')

    def test_cross_repo_pool_name_conflicts(self):
        self.sync('{"ports": {"range": [3000, 3001]}}')
        with self.assertRaisesRegex(CorralError, "another repo"):
            self.sync('{"ports": {"range": [3000, 3001]}}', source="/repos/other")


if __name__ == "__main__":
    unittest.main()
