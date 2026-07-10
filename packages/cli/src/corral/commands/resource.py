"""corral resource — check shared resources in and out of machine-wide pools."""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Dict, List, Tuple

from .. import gitutil, resources, ui
from ..cli import Argument, Command, Example, Option
from ..ui import CorralError
from . import Context

# Action names + one-liners; also renders the zsh _corral_resource_actions helper.
ACTIONS: Tuple[Tuple[str, str], ...] = (
    ("acquire", "check out one free item from a pool"),
    ("release", "return checked-out items to their pool"),
    ("add", "create a pool or add items to one"),
    ("rm", "remove a pool or a single item"),
    ("ls", "list pools, items, and holders"),
    ("sync", "sync this repo's .corral/resources.json into the database"),
)

_POLL_SECONDS = 2.0

# Column order for --tsv rows (the zsh completion consumes this).
COLUMNS = ("pool", "name", "state", "holder", "acquired_at")

SPEC = Command(
    name="resource",
    aliases=("res",),
    summary="check shared resources (ports, credentials, …) in and out of pools.",
    shell_alias="crs",
    description=(
        "Actions:\n"
        "  acquire <pool>         check out one free item; prints its name\n"
        "  release <pool>/<item>  return an item (or: release <pool>, release --all)\n"
        "  add <pool> <items…>    create/extend a pool (N-M expands to a port range)\n"
        "  rm <pool>[/<item>]     remove a pool or a single item\n"
        "  ls [pool]              list pools, items, holders\n"
        "  sync                   sync this repo's .corral/resources.json\n"
        "\n"
        "Pools and leases live in one machine-wide SQLite database\n"
        "(CORRAL_RESOURCES_DB), so concurrent agent workspaces can never check\n"
        "out the same item twice. Inside a corral worktree the holder defaults\n"
        "to the workspace (ws:<repo>/<label>) — acquire from .corral/setup.sh to\n"
        "reserve resources at spawn — and 'corral close'/'corral prune' release\n"
        "a workspace's items automatically. A repo can also declare pools in a\n"
        "committed .corral/resources.json, synced in on acquire/ls/sync."
    ),
    doc=(
        "Check shared resources in and out of named pools — dev-server ports, Shopify\n"
        "dev-app credentials, anything scarce that concurrent agent workspaces must not\n"
        "grab twice. State lives in one machine-wide SQLite database\n"
        "(`CORRAL_RESOURCES_DB`); every checkout is a single database transaction, so\n"
        "two agents can never acquire the same item.\n"
        "\n"
        "| Action | Meaning |\n"
        "| --- | --- |\n"
        + "\n".join(f"| `{name}` | {summary} |" for name, summary in ACTIONS)
        + "\n"
        "\n"
        "`acquire` prints the item name on stdout (`PORT=$(corral resource acquire\n"
        "ports)`); `--json` adds the item's attached data payload (for example Shopify\n"
        "app credentials). When the pool is exhausted it fails and lists the holders;\n"
        "`--wait` polls until an item frees up instead.\n"
        "\n"
        "**Holders.** Run inside a corral worktree, acquire records the workspace\n"
        "(`ws:<repo>/<label>`) as the holder — so a `.corral/setup.sh` can reserve\n"
        "resources at spawn time — and `corral close`/`corral prune` automatically\n"
        "release everything that workspace still holds. Outside a worktree the holder\n"
        "is `user@host:<cwd>`; `--as` overrides it either way.\n"
        "\n"
        "**Per-repo pools.** A repo can commit a `.corral/resources.json` declaring\n"
        "pools; corral syncs it into the database on `acquire`/`ls`/`sync`:\n"
        "\n"
        "```json\n"
        "{\n"
        '  "shopify-dev-apps": [\n'
        '    {"name": "dev-app-1", "data": {"api_key": "…", "url": "…"}},\n'
        '    {"name": "dev-app-2", "data": {"api_key": "…"}}\n'
        "  ],\n"
        '  "ports": {"range": [3000, 3009]}\n'
        "}\n"
        "```\n"
        "\n"
        "The file is declarative for the pools it names: new items are added, changed\n"
        "`data` is updated in place (leases untouched), and items dropped from the file\n"
        "are deleted when free — or retired when currently held, so they are never\n"
        "handed out again and disappear once released. Items added to the same pool via\n"
        "the CLI are left alone. See\n"
        "[per-repo configuration](configuration.md#per-repo-configuration-corral)."
    ),
    arguments=(
        Argument(
            "action",
            help="One of: " + ", ".join(name for name, _ in ACTIONS),
            completion="_corral_resource_actions",
            value_label="resource action",
        ),
        Argument(
            "target",
            required=False,
            help="Pool name, or <pool>/<item> for release and rm",
            doc="Pool name, or `<pool>/<item>` for `release` and `rm`.",
            completion="_corral_resource_targets",
            value_label="pool[/item]",
        ),
        Argument(
            "items",
            required=False,
            variadic=True,
            help="Items to add (add only); N-M expands to a port range",
            doc="Items to add (`add` only); `N-M` expands to an inclusive port range.",
            value_label="item name",
        ),
    ),
    options=(
        Option(
            "--json",
            short="-j",
            help="Emit machine-readable JSON (acquire, ls)",
            doc="Emit machine-readable JSON, including item `data` (`acquire`, `ls`).",
            excludes=("--tsv",),
        ),
        Option(
            "--tsv",
            help="Emit tab-separated rows: " + ", ".join(COLUMNS) + " (ls)",
            doc=(
                "Emit one tab-separated row per item (`ls`). Columns: "
                + ", ".join(COLUMNS)
                + " — the format the zsh completion consumes."
            ),
            excludes=("--json",),
        ),
        Option(
            "--as",
            metavar="<holder>",
            help=(
                "Act as this holder\n"
                "(default: the enclosing corral workspace, else user@host:cwd)"
            ),
            doc=(
                "Act as this holder tag (default: the enclosing corral workspace as "
                "`ws:<repo>/<label>`, else `user@host:<cwd>`)."
            ),
            value_hint="holder",
        ),
        Option(
            "--wait",
            short="-w",
            metavar="<seconds>",
            optional_value=True,
            help=(
                "acquire: poll until an item frees up instead of failing\n"
                "(bare --wait waits forever; --wait=30 gives up after 30s)"
            ),
            doc=(
                "`acquire` only: poll every 2s until an item frees up instead of "
                "failing. Bare `--wait` waits forever; `--wait=30` gives up "
                "after 30 seconds."
            ),
        ),
        Option(
            "--data",
            metavar="<json>",
            help="add: JSON payload attached to each added item (shown by acquire --json)",
            doc=(
                "`add` only: a JSON payload attached to each added item, returned "
                "by `acquire --json` and `ls --json`."
            ),
            value_hint="json",
        ),
        Option(
            "--all",
            help="release: return everything the holder has checked out",
            doc="`release` only: return everything the holder has checked out.",
        ),
        Option(
            "--mine",
            help="ls: only items checked out by this workspace/holder",
            doc="`ls` only: only items checked out by this workspace/holder.",
        ),
        Option(
            "--force",
            short="-f",
            help="Release an item held by someone else; rm a pool with held items",
            doc="Release an item held by someone else; `rm` a pool with held items.",
        ),
    ),
    examples=(
        Example("corral resource add ports 3000-3009"),
        Example("corral resource acquire ports", note="prints e.g. 3001"),
        Example("corral resource acquire shopify-dev-apps --json --wait=60"),
        Example("corral resource release ports/3001"),
        Example("corral resource release --all", note="return everything this workspace holds"),
        Example("corral resource ls --mine"),
    ),
)


def _split_target(target: str) -> Tuple[str, str]:
    """'ports' -> ('ports', ''); 'ports/3001' -> ('ports', '3001')."""
    pool, _, item = target.partition("/")
    if not pool or (item and "/" in item):
        raise CorralError(f"bad target '{target}' (expected <pool> or <pool>/<item>)")
    return pool, item


def _require_target(args: Dict[str, object], action: str, what: str) -> str:
    target = str(args["target"])
    if not target:
        raise CorralError(f"{action} needs a {what} (corral resource {action} <{what}>)")
    return target


def _holder(ctx: Context, args: Dict[str, object]) -> str:
    return str(args["as"]) or resources.detect_holder(
        ctx.settings.worktrees_dir, os.getcwd()
    )


def _auto_sync(conn) -> None:
    """Best-effort sync of the enclosing repo's resources.json (acquire/ls).

    Warns and proceeds on any problem — a broken file must not brick
    acquire/ls; only the explicit `sync` action hard-errors.
    """
    root = gitutil.repo_root(os.getcwd())
    if not root:
        return
    try:
        # Source = the main checkout, so every worktree of a repo counts as
        # the same declarer of its pools.
        resources.sync_file(conn, root, gitutil.repo_common_root(os.getcwd()))
    except CorralError as exc:
        ui.warn(f"skipping {resources.RESOURCES_FILE} sync ({exc})")


def _decoded(record: Dict[str, str]) -> Dict[str, object]:
    out: Dict[str, object] = dict(record)
    out["data"] = json.loads(record["data"]) if record["data"] else None
    return out


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------


def _acquire(ctx: Context, db, args: Dict[str, object]) -> int:
    pool, item = _split_target(_require_target(args, "acquire", "pool"))
    if item:
        raise CorralError(f"acquire takes a pool, not an item (try 'corral resource acquire {pool}')")
    holder = _holder(ctx, args)
    deadline = _wait_deadline(args["wait"])
    conn = db()
    _auto_sync(conn)

    announced = False
    while True:
        try:
            record = resources.try_acquire(conn, pool, holder)
            break
        except resources.PoolExhausted as exc:
            if deadline is None:
                raise
            if not announced:
                held = ", ".join(f"{h} ×{n}" for h, n in exc.holders)
                ui.info(
                    f"pool '{pool}' exhausted — waiting for a free item "
                    f"(held by: {held}; Ctrl-C to stop)"
                )
                announced = True
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise CorralError(
                    f"gave up waiting for pool '{pool}' after "
                    f"{args['wait']}s (held by: "
                    + ", ".join(f"{h} ×{n}" for h, n in exc.holders)
                    + ")"
                ) from None
            time.sleep(min(_POLL_SECONDS, remaining))

    if args["json"]:
        print(json.dumps(_decoded(record), indent=1))
    else:
        print(record["name"])
    ui.ok(f"acquired {pool}/{record['name']} (holder: {holder})")
    return 0


def _wait_deadline(wait: object):
    """--wait value -> None (fail fast), inf (forever), or a monotonic deadline."""
    if wait is False:
        return None
    if wait is True:
        return float("inf")
    try:
        seconds = float(str(wait))
    except ValueError:
        raise CorralError(f"--wait needs a number of seconds (got '{wait}')") from None
    if seconds <= 0:
        raise CorralError("--wait needs a positive number of seconds")
    return time.monotonic() + seconds


def _release(ctx: Context, db, args: Dict[str, object]) -> int:
    holder = _holder(ctx, args)
    if args["all"]:
        if args["target"]:
            raise CorralError("release --all takes no target")
        released = resources.release_all(db(), holder)
        if not released:
            ui.info(f"nothing checked out by {holder}")
            return 0
        names = ", ".join(f"{pool}/{name}" for pool, name in released)
        ui.ok(f"released {len(released)} item(s): {names}")
        return 0

    pool, item = _split_target(_require_target(args, "release", "pool[/item]"))
    if item:
        retired = resources.release(db(), pool, item, holder, bool(args["force"]))
        note = f" (retired — removed from {resources.RESOURCES_FILE})" if retired else ""
        ui.ok(f"released {pool}/{item}{note}")
        return 0
    names = resources.release_pool(db(), pool, holder)
    if not names:
        ui.info(f"nothing in pool '{pool}' checked out by {holder}")
        return 0
    ui.ok(f"released {len(names)} item(s) from '{pool}': {', '.join(names)}")
    return 0


def _add(ctx: Context, db, args: Dict[str, object]) -> int:
    pool, item = _split_target(_require_target(args, "add", "pool"))
    if item:
        raise CorralError(
            f"add takes a pool and item names (try 'corral resource add {pool} {item}')"
        )
    data = ""
    if args["data"]:
        try:
            data = json.dumps(json.loads(str(args["data"])), sort_keys=True)
        except ValueError as exc:
            raise CorralError(f"--data is not valid JSON: {exc}") from None
    names = resources.expand_items(list(args["items"]))
    resources.add_items(db(), pool, names, data)
    if names:
        ui.ok(f"added {len(names)} item(s) to pool '{pool}'")
    else:
        ui.ok(f"created pool '{pool}' (add items with 'corral resource add {pool} <items…>')")
    return 0


def _rm(ctx: Context, db, args: Dict[str, object]) -> int:
    pool, item = _split_target(_require_target(args, "rm", "pool[/item]"))
    force = bool(args["force"])
    if item:
        resources.remove_item(db(), pool, item, force)
        ui.ok(f"removed {pool}/{item}")
    else:
        count = resources.remove_pool(db(), pool, force)
        ui.ok(f"removed pool '{pool}' ({count} item(s))")
    return 0


def _ls(ctx: Context, db, args: Dict[str, object]) -> int:
    pool, item = _split_target(str(args["target"])) if args["target"] else ("", "")
    if item:
        raise CorralError("ls takes a pool name, not an item")
    conn = db()
    _auto_sync(conn)
    holder = _holder(ctx, args) if args["mine"] else ""
    listing = resources.list_rows(conn, pool=pool, holder=holder)

    if args["json"]:
        print(json.dumps([_decoded(row) for row in listing], indent=1 if listing else None))
        return 0
    if args["tsv"]:
        for row in listing:
            if row["state"] != "empty":
                print("\t".join(row[col] for col in COLUMNS))
        return 0

    if not listing:
        ui.info("no resource pools (create one with 'corral resource add <pool> <items…>')")
        return 0

    # Header on stderr so piped stdout carries only data rows (like corral ls).
    header = f"{'POOL':<20} {'ITEM':<20} {'STATE':<8} {'HOLDER':<36} ACQUIRED"
    print(f"{ui.C.bold}{header}{ui.C.reset}", file=sys.stderr)
    for row in listing:
        if row["state"] == "empty":
            print(f"{row['pool']:<20} {ui.C.dim}(empty){ui.C.reset}")
            continue
        print(
            f"{row['pool']:<20} {row['name']:<20} {row['state']:<8} "
            f"{row['holder']:<36} {row['acquired_at']}"
        )
    return 0


def _sync(ctx: Context, db, args: Dict[str, object]) -> int:
    if args["target"]:
        raise CorralError("sync takes no target (it syncs this repo's resources file)")
    root = gitutil.repo_root(os.getcwd())
    if not root:
        raise CorralError("not inside a git repo — nothing to sync")
    path = os.path.join(root, resources.RESOURCES_FILE)
    if not os.path.isfile(path):
        raise CorralError(f"no {resources.RESOURCES_FILE} in {root}")
    summary = resources.sync_file(db(), root, gitutil.repo_common_root(os.getcwd()))
    if not summary:
        ui.info(f"{resources.RESOURCES_FILE} already in sync")
        return 0
    for pool, stats in sorted(summary.items()):
        changes = ", ".join(
            f"{count} {what}" for what, count in stats.items() if count
        )
        ui.ok(f"synced pool '{pool}' ({changes})")
    return 0


_HANDLERS = {
    "acquire": _acquire,
    "release": _release,
    "add": _add,
    "rm": _rm,
    "ls": _ls,
    "sync": _sync,
}


def run(ctx: Context, args: Dict[str, object]) -> int:
    action = str(args["action"])
    known = ", ".join(name for name, _ in ACTIONS)
    if not action:
        raise CorralError(f"missing action (expected one of: {known})")
    handler = _HANDLERS.get(action)
    if handler is None:
        raise CorralError(f"unknown action '{action}' (expected one of: {known})")
    if args["json"] and args["tsv"]:
        raise CorralError("--json and --tsv are mutually exclusive")
    if action != "add" and args["items"]:
        raise CorralError(f"unexpected argument: {args['items'][0]}")

    # Lazy: each handler validates its arguments before first touching the
    # database, so usage errors never depend on a writable CORRAL_RESOURCES_DB.
    opened = []

    def db():
        if not opened:
            opened.append(resources.connect(ctx.settings.resources_db))
        return opened[0]

    try:
        return handler(ctx, db, args)
    finally:
        if opened:
            opened[0].close()
