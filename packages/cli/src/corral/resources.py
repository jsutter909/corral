"""The shared-resource store — pools, items, and leases in one SQLite file.

`corral resource` lets concurrent agent workspaces check scarce dev resources
(ports, Shopify dev-app configs, …) in and out of named pools. All state lives
in a single machine-wide SQLite database (settings.resources_db); SQLite's
file locking is the locking story: every mutation runs inside a
``BEGIN IMMEDIATE`` transaction, so "find a free item and mark it held" is
atomic across processes and contenders queue on the connection's busy timeout.

Everything here is a plain function over a connection (or a db path), with no
herdr and no CLI knowledge — the `resource` command and the close/prune
auto-release both call in from outside.
"""

from __future__ import annotations

import contextlib
import getpass
import json
import os
import re
import socket
import sqlite3
from datetime import datetime, timezone
from typing import Dict, Iterator, List, Optional, Tuple

from .ui import CorralError

SCHEMA_VERSION = 1

# Individual statements: executed one by one inside the migration transaction
# (sqlite3.executescript would implicitly commit and break it).
_SCHEMA = (
    """
    CREATE TABLE pools (
        name   TEXT PRIMARY KEY,
        origin TEXT NOT NULL DEFAULT 'cli',     -- 'cli' | 'file'
        source TEXT NOT NULL DEFAULT ''         -- repo root declaring a file pool
    )
    """,
    """
    CREATE TABLE items (
        pool        TEXT NOT NULL,
        name        TEXT NOT NULL,
        data        TEXT NOT NULL DEFAULT '',   -- JSON text; '' = none
        origin      TEXT NOT NULL DEFAULT 'cli',
        retired     INTEGER NOT NULL DEFAULT 0, -- removed from its file while held
        holder      TEXT NOT NULL DEFAULT '',   -- '' = free
        acquired_at TEXT NOT NULL DEFAULT '',   -- UTC ISO-8601
        PRIMARY KEY (pool, name),
        FOREIGN KEY (pool) REFERENCES pools(name) ON DELETE CASCADE
    )
    """,
)

# Pool and item names travel through pool/item addressing, TSV output, and
# zsh completion, so keep them boring: no slashes, colons, or whitespace.
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

_RANGE = re.compile(r"^(\d+)-(\d+)$")
_MAX_RANGE = 4096

RESOURCES_FILE = os.path.join(".corral", "resources.json")


class PoolExhausted(CorralError):
    """Every item in the pool is checked out; carries who holds what."""

    def __init__(self, pool: str, holders: List[Tuple[str, int]]):
        self.pool = pool
        self.holders = holders
        total = sum(count for _, count in holders)
        held = ", ".join(f"{holder} ×{count}" for holder, count in holders)
        super().__init__(f"pool '{pool}' exhausted ({total} held: {held})")


# ---------------------------------------------------------------------------
# Connection / schema
# ---------------------------------------------------------------------------


def connect(db_path: str) -> sqlite3.Connection:
    """Open (creating if needed) the resources database.

    isolation_level=None puts sqlite3 in autocommit so the explicit
    ``BEGIN IMMEDIATE`` in :func:`tx` is the only transaction control;
    timeout=5.0 makes contending processes queue on the write lock.
    """
    try:
        parent = os.path.dirname(db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        conn = sqlite3.connect(db_path, timeout=5.0, isolation_level=None)
    except (OSError, sqlite3.Error) as exc:
        raise CorralError(
            f"could not open resources db {db_path} ({exc}) — "
            "set CORRAL_RESOURCES_DB to a writable path"
        ) from None
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    _migrate(conn, db_path)
    return conn


def _migrate(conn: sqlite3.Connection, db_path: str) -> None:
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version == SCHEMA_VERSION:
        return
    if version > SCHEMA_VERSION:
        raise CorralError(
            f"resources db {db_path} has schema version {version}, newer than "
            f"this corral understands ({SCHEMA_VERSION}) — upgrade corral"
        )
    with tx(conn):
        for statement in _SCHEMA:
            conn.execute(statement)
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


@contextlib.contextmanager
def tx(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """One write transaction: takes the cross-process write lock up front."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Names, ranges, holders
# ---------------------------------------------------------------------------


def validate_name(kind: str, name: str) -> str:
    if not _NAME.match(name):
        raise CorralError(
            f"invalid {kind} name '{name}' (use letters, digits, '.', '_', '-')"
        )
    return name


def expand_items(tokens: List[str]) -> List[str]:
    """Item names from CLI tokens; N-M expands to an inclusive port range."""
    names: List[str] = []
    for token in tokens:
        match = _RANGE.match(token)
        if not match:
            names.append(validate_name("item", token))
            continue
        start, end = int(match.group(1)), int(match.group(2))
        if start > end:
            raise CorralError(f"bad range '{token}' (start exceeds end)")
        if end - start + 1 > _MAX_RANGE:
            raise CorralError(f"range '{token}' expands to more than {_MAX_RANGE} items")
        names.extend(str(port) for port in range(start, end + 1))
    return names


def holder_for_worktree(worktrees_dir: str, path: str) -> str:
    """'ws:<repo>/<label>' when `path` is inside a corral worktree, else ''.

    Pure path math against herdr's <worktrees_dir>/<repo>/<label> layout — no
    herdr server needed, so acquire works from a setup.sh and auto-release
    works even when herdr is half-dead.
    """
    base = os.path.realpath(worktrees_dir)
    real = os.path.realpath(path)
    if not real.startswith(base + os.sep):
        return ""
    parts = real[len(base) + 1:].split(os.sep)
    if len(parts) < 2 or not parts[0] or not parts[1]:
        return ""
    return f"ws:{parts[0]}/{parts[1]}"


def detect_holder(worktrees_dir: str, cwd: str) -> str:
    """The default holder tag: the enclosing workspace, else user@host:cwd."""
    holder = holder_for_worktree(worktrees_dir, cwd)
    if holder:
        return holder
    try:
        user = getpass.getuser()
    except OSError:
        user = "unknown"
    return f"{user}@{socket.gethostname()}:{os.path.realpath(cwd)}"


# ---------------------------------------------------------------------------
# Pools and items (CLI-driven)
# ---------------------------------------------------------------------------


def _pool_row(conn: sqlite3.Connection, pool: str) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM pools WHERE name = ?", (pool,)).fetchone()


def _require_pool(conn: sqlite3.Connection, pool: str) -> sqlite3.Row:
    row = _pool_row(conn, pool)
    if row is None:
        raise CorralError(
            f"no pool '{pool}' (create one with 'corral resource add {pool} <items…>')"
        )
    return row


def add_items(conn: sqlite3.Connection, pool: str, names: List[str], data: str) -> int:
    """Create the pool if needed and add items (origin 'cli'). Returns the
    number added; duplicate names are an error naming the first one."""
    validate_name("pool", pool)
    with tx(conn):
        conn.execute(
            "INSERT OR IGNORE INTO pools (name, origin, source) VALUES (?, 'cli', '')",
            (pool,),
        )
        for name in names:
            dup = conn.execute(
                "SELECT 1 FROM items WHERE pool = ? AND name = ?", (pool, name)
            ).fetchone()
            if dup:
                raise CorralError(f"item '{pool}/{name}' already exists")
            conn.execute(
                "INSERT INTO items (pool, name, data, origin) VALUES (?, ?, ?, 'cli')",
                (pool, name, data),
            )
    return len(names)


def remove_pool(conn: sqlite3.Connection, pool: str, force: bool) -> int:
    """Drop a pool and its items. Refuses while items are held unless force."""
    with tx(conn):
        _require_pool(conn, pool)
        held = conn.execute(
            "SELECT name, holder FROM items WHERE pool = ? AND holder != '' ORDER BY name",
            (pool,),
        ).fetchall()
        if held and not force:
            what = ", ".join(f"{row['name']} (held by {row['holder']})" for row in held)
            raise CorralError(
                f"pool '{pool}' has checked-out items: {what} — release them "
                "first or pass --force"
            )
        count = conn.execute(
            "SELECT COUNT(*) FROM items WHERE pool = ?", (pool,)
        ).fetchone()[0]
        conn.execute("DELETE FROM items WHERE pool = ?", (pool,))
        conn.execute("DELETE FROM pools WHERE name = ?", (pool,))
    return count


def remove_item(conn: sqlite3.Connection, pool: str, name: str, force: bool) -> None:
    with tx(conn):
        _require_pool(conn, pool)
        row = conn.execute(
            "SELECT holder FROM items WHERE pool = ? AND name = ?", (pool, name)
        ).fetchone()
        if row is None:
            raise CorralError(f"no item '{pool}/{name}'")
        if row["holder"] and not force:
            raise CorralError(
                f"item '{pool}/{name}' is held by {row['holder']} — release it "
                "first or pass --force"
            )
        conn.execute("DELETE FROM items WHERE pool = ? AND name = ?", (pool, name))


# ---------------------------------------------------------------------------
# Acquire / release
# ---------------------------------------------------------------------------


def try_acquire(conn: sqlite3.Connection, pool: str, holder: str) -> Dict[str, str]:
    """Check out the first free item of a pool, atomically.

    Raises CorralError when the pool is missing/empty and PoolExhausted (with
    per-holder counts) when everything is checked out.
    """
    with tx(conn):
        _require_pool(conn, pool)
        row = conn.execute(
            "SELECT name, data FROM items WHERE pool = ? AND holder = '' "
            "AND retired = 0 ORDER BY name LIMIT 1",
            (pool,),
        ).fetchone()
        if row is None:
            holders = conn.execute(
                "SELECT holder, COUNT(*) AS n FROM items WHERE pool = ? "
                "AND holder != '' GROUP BY holder ORDER BY n DESC, holder",
                (pool,),
            ).fetchall()
            if not holders:
                raise CorralError(
                    f"pool '{pool}' has no items "
                    f"(add some with 'corral resource add {pool} <items…>')"
                )
            raise PoolExhausted(pool, [(h["holder"], h["n"]) for h in holders])
        acquired_at = _now()
        conn.execute(
            "UPDATE items SET holder = ?, acquired_at = ? WHERE pool = ? AND name = ?",
            (holder, acquired_at, pool, row["name"]),
        )
    return {
        "pool": pool,
        "name": row["name"],
        "data": row["data"],
        "holder": holder,
        "acquired_at": acquired_at,
    }


def _free_item(conn: sqlite3.Connection, pool: str, name: str, retired: int) -> bool:
    """Return one held item to the pool (inside a tx). Retired items — removed
    from their resources.json while held — are deleted instead of freed.
    Returns True when the row was retired."""
    if retired:
        conn.execute("DELETE FROM items WHERE pool = ? AND name = ?", (pool, name))
        return True
    conn.execute(
        "UPDATE items SET holder = '', acquired_at = '' WHERE pool = ? AND name = ?",
        (pool, name),
    )
    return False


def release(
    conn: sqlite3.Connection, pool: str, name: str, holder: str, force: bool
) -> bool:
    """Release one item; True when it was retired (removed, not freed)."""
    with tx(conn):
        _require_pool(conn, pool)
        row = conn.execute(
            "SELECT holder, retired FROM items WHERE pool = ? AND name = ?",
            (pool, name),
        ).fetchone()
        if row is None:
            raise CorralError(f"no item '{pool}/{name}'")
        if not row["holder"]:
            raise CorralError(f"item '{pool}/{name}' is not checked out")
        if row["holder"] != holder and not force:
            raise CorralError(
                f"item '{pool}/{name}' is held by {row['holder']}, not you "
                f"({holder}) — pass --force to release it anyway"
            )
        return _free_item(conn, pool, name, row["retired"])


def release_pool(conn: sqlite3.Connection, pool: str, holder: str) -> List[str]:
    """Release everything `holder` has checked out of one pool."""
    with tx(conn):
        _require_pool(conn, pool)
        rows = conn.execute(
            "SELECT name, retired FROM items WHERE pool = ? AND holder = ? ORDER BY name",
            (pool, holder),
        ).fetchall()
        for row in rows:
            _free_item(conn, pool, row["name"], row["retired"])
    return [row["name"] for row in rows]


def release_all(conn: sqlite3.Connection, holder: str) -> List[Tuple[str, str]]:
    """Release everything `holder` has checked out, across all pools."""
    with tx(conn):
        rows = conn.execute(
            "SELECT pool, name, retired FROM items WHERE holder = ? ORDER BY pool, name",
            (holder,),
        ).fetchall()
        for row in rows:
            _free_item(conn, row["pool"], row["name"], row["retired"])
    return [(row["pool"], row["name"]) for row in rows]


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------


def list_rows(
    conn: sqlite3.Connection, pool: str = "", holder: str = ""
) -> List[Dict[str, str]]:
    """One dict per item (state: free/held/retired), plus empty pools."""
    if pool:
        _require_pool(conn, pool)
    result = []
    query = (
        "SELECT p.name AS pool, i.name, i.data, i.origin, i.retired, i.holder, "
        "i.acquired_at FROM pools p LEFT JOIN items i ON i.pool = p.name "
    )
    where, params = [], []
    if pool:
        where.append("p.name = ?")
        params.append(pool)
    if where:
        query += "WHERE " + " AND ".join(where) + " "
    query += "ORDER BY p.name, i.name"
    for row in conn.execute(query, params):
        if row["name"] is None:  # empty pool, kept visible
            if holder:
                continue
            result.append(
                {
                    "pool": row["pool"], "name": "", "state": "empty",
                    "holder": "", "acquired_at": "", "data": "", "origin": "",
                }
            )
            continue
        if holder and row["holder"] != holder:
            continue
        state = "retired" if row["retired"] else ("held" if row["holder"] else "free")
        result.append(
            {
                "pool": row["pool"],
                "name": row["name"],
                "state": state,
                "holder": row["holder"],
                "acquired_at": row["acquired_at"],
                "data": row["data"],
                "origin": row["origin"],
            }
        )
    return result


# ---------------------------------------------------------------------------
# .corral/resources.json
# ---------------------------------------------------------------------------


def parse_resources_file(text: str) -> Dict[str, List[Tuple[str, str]]]:
    """Parse a .corral/resources.json into {pool: [(item, data_json), …]}.

    Two pool forms:
      "ports": {"range": [3000, 3009]}
      "apps":  ["name", {"name": "dev-app-1", "data": {…}}, …]
    """
    try:
        raw = json.loads(text)
    except ValueError as exc:
        raise CorralError(f"invalid JSON in {RESOURCES_FILE}: {exc}") from None
    if not isinstance(raw, dict):
        raise CorralError(f"{RESOURCES_FILE} must be a JSON object of pools")

    pools: Dict[str, List[Tuple[str, str]]] = {}
    for pool, spec in raw.items():
        validate_name("pool", str(pool))
        items: List[Tuple[str, str]] = []
        if isinstance(spec, dict):
            bounds = spec.get("range")
            if (
                not isinstance(bounds, list) or len(bounds) != 2
                or not all(isinstance(b, int) for b in bounds)
            ):
                raise CorralError(
                    f"pool '{pool}' in {RESOURCES_FILE}: expected "
                    '{"range": [start, end]}'
                )
            items = [(name, "") for name in expand_items([f"{bounds[0]}-{bounds[1]}"])]
        elif isinstance(spec, list):
            for entry in spec:
                if isinstance(entry, str):
                    items.append((validate_name("item", entry), ""))
                elif isinstance(entry, dict) and isinstance(entry.get("name"), str):
                    name = validate_name("item", entry["name"])
                    data = entry.get("data")
                    items.append(
                        (name, json.dumps(data, sort_keys=True) if data is not None else "")
                    )
                else:
                    raise CorralError(
                        f"pool '{pool}' in {RESOURCES_FILE}: each item must be "
                        'a name or {"name": …, "data": …}'
                    )
        else:
            raise CorralError(
                f"pool '{pool}' in {RESOURCES_FILE}: expected an item list or "
                '{"range": [start, end]}'
            )
        seen = set()
        for name, _ in items:
            if name in seen:
                raise CorralError(
                    f"pool '{pool}' in {RESOURCES_FILE}: duplicate item '{name}'"
                )
            seen.add(name)
        pools[pool] = items
    return pools


def sync_source(
    conn: sqlite3.Connection, source: str, pools: Dict[str, List[Tuple[str, str]]]
) -> Dict[str, Dict[str, int]]:
    """Make the DB's file-origin pools for `source` match its resources.json.

    Declarative per (pool, source): file items are inserted/updated (data
    changes never touch a lease); file-origin items dropped from the file are
    deleted when free and retired when held (never handed out again, deleted
    on release); cli-origin items in the same pool are left alone. A pool name
    owned by the CLI or by a different repo's file is a conflict.
    """
    summary: Dict[str, Dict[str, int]] = {}
    with tx(conn):
        for pool in pools:
            row = _pool_row(conn, pool)
            if row is None:
                continue
            if row["origin"] == "cli":
                raise CorralError(
                    f"pool '{pool}' already exists (created via the CLI) — "
                    f"'corral resource rm {pool}' it or rename the pool in "
                    f"{RESOURCES_FILE}"
                )
            if row["source"] != source:
                raise CorralError(
                    f"pool '{pool}' is declared by another repo "
                    f"({row['source']}) — rename it in {RESOURCES_FILE}"
                )
        known = [
            row["name"]
            for row in conn.execute(
                "SELECT name FROM pools WHERE origin = 'file' AND source = ?", (source,)
            )
        ]
        for pool in sorted(set(known) | set(pools)):
            declared = dict(pools.get(pool, []))
            stats = {"added": 0, "updated": 0, "removed": 0, "retired": 0}
            if declared and _pool_row(conn, pool) is None:
                conn.execute(
                    "INSERT INTO pools (name, origin, source) VALUES (?, 'file', ?)",
                    (pool, source),
                )
            existing = {
                row["name"]: row
                for row in conn.execute(
                    "SELECT name, data, origin, retired, holder FROM items "
                    "WHERE pool = ?",
                    (pool,),
                )
            }
            for name, data in declared.items():
                row = existing.get(name)
                if row is None:
                    conn.execute(
                        "INSERT INTO items (pool, name, data, origin) "
                        "VALUES (?, ?, ?, 'file')",
                        (pool, name, data),
                    )
                    stats["added"] += 1
                elif row["data"] != data or row["retired"] or row["origin"] != "file":
                    # Re-declaring a retired item un-retires it; a data change
                    # updates in place without touching the lease.
                    conn.execute(
                        "UPDATE items SET data = ?, origin = 'file', retired = 0 "
                        "WHERE pool = ? AND name = ?",
                        (data, pool, name),
                    )
                    stats["updated"] += 1
            for name, row in existing.items():
                if row["origin"] != "file" or name in declared:
                    continue
                if row["holder"]:
                    if not row["retired"]:
                        conn.execute(
                            "UPDATE items SET retired = 1 WHERE pool = ? AND name = ?",
                            (pool, name),
                        )
                        stats["retired"] += 1
                else:
                    conn.execute(
                        "DELETE FROM items WHERE pool = ? AND name = ?", (pool, name)
                    )
                    stats["removed"] += 1
            if pool not in pools:
                left = conn.execute(
                    "SELECT COUNT(*) FROM items WHERE pool = ?", (pool,)
                ).fetchone()[0]
                if left == 0:
                    conn.execute("DELETE FROM pools WHERE name = ?", (pool,))
            if any(stats.values()):
                summary[pool] = stats
    return summary


def sync_file(
    conn: sqlite3.Connection, repo_root: str, source: str = ""
) -> Dict[str, Dict[str, int]]:
    """Sync a repo's .corral/resources.json; {} when the repo has none.

    `source` is the identity the pools are recorded under — pass the repo's
    main-checkout path (gitutil.repo_common_root) so every linked worktree of
    one repo counts as the same declarer; defaults to repo_root itself.
    """
    path = os.path.join(repo_root, RESOURCES_FILE)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
    except FileNotFoundError:
        return {}
    except OSError as exc:
        raise CorralError(f"could not read {path}: {exc}") from None
    return sync_source(conn, source or repo_root, parse_resources_file(text))
