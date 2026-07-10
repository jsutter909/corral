"""The `corral monitor` web UI — a local dashboard for the agent fleet.

A single stdlib :mod:`http.server` (no dependencies, matching the rest of
corral) that serves a small single-page app plus a JSON API:

* ``GET  /``            — the dashboard page (HTML/CSS/JS, all inlined below)
* ``GET  /api/meta``    — static choices for the spawn form (agents, models, …)
* ``GET  /api/state``   — a live snapshot: every corral-owned workspace joined
                          to the resources it currently holds, plus every pool
* ``POST /api/spawn``   — launch a new agent workspace
* ``POST /api/focus``   — switch the herdr session's focus to a workspace
* ``POST /api/close``   — tear a workspace down (worktree removed)
* ``POST /api/release`` — return a held resource item to its pool

The write endpoints don't reinvent anything: each turns its JSON body into the
same argv a shell user would type and runs it through the very command the CLI
uses (:func:`corral.cli.parse_args` + the command's ``run``), so the web UI and
the terminal share one implementation and one set of validations.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict, List, Tuple

from . import gitutil, resources, ui
from .agents import AGENTS, CLAUDE_MODELS, CLAUDE_PERMISSION_MODES
from .cli import parse_args
from .commands import Context, owned_workspaces
from .ui import CorralError


# ---------------------------------------------------------------------------
# State snapshot — agents joined to the resources they hold
# ---------------------------------------------------------------------------


def snapshot(ctx: Context) -> Dict[str, object]:
    """A JSON-ready view of the fleet: agents (each with the resources it
    holds) and every resource pool with its items.

    The join key is the holder tag: a resource acquired from inside a corral
    worktree is recorded against ``ws:<repo>/<label>`` (see
    :func:`resources.holder_for_worktree`), and the same tag is derived here
    from each workspace's worktree path — no extra herdr calls needed.
    """
    wt_dir = ctx.settings.worktrees_dir

    conn = resources.connect(ctx.settings.resources_db)
    try:
        rows = resources.list_rows(conn)
    finally:
        conn.close()

    held_by: Dict[str, List[Dict[str, str]]] = {}
    for row in rows:
        if row["holder"]:
            held_by.setdefault(row["holder"], []).append(row)

    agents = []
    for ws in owned_workspaces(ctx):
        wt = ws.owned_worktree_path(wt_dir)
        holder = resources.holder_for_worktree(wt_dir, wt) if wt else ""
        held = held_by.get(holder, []) if holder else []
        agents.append(
            {
                "id": ws.id,
                "label": ws.label,
                "repo": ws.worktree.repo_name if ws.worktree else "?",
                "branch": gitutil.current_branch(wt) if wt else "?",
                "status": ws.agent_status,
                "worktree": wt,
                "holder": holder,
                "resources": [
                    {
                        "pool": r["pool"],
                        "name": r["name"],
                        "acquired_at": r["acquired_at"],
                        "data": _decode(r["data"]),
                    }
                    for r in held
                ],
            }
        )

    pools = _pools(rows)
    return {"agents": agents, "pools": pools}


def _decode(data: str):
    try:
        return json.loads(data) if data else None
    except ValueError:
        return None


def _pools(rows: List[Dict[str, str]]) -> List[Dict[str, object]]:
    """Group the flat item rows into per-pool summaries for the UI."""
    order: List[str] = []
    by_pool: Dict[str, List[Dict[str, str]]] = {}
    for row in rows:
        pool = row["pool"]
        if pool not in by_pool:
            by_pool[pool] = []
            order.append(pool)
        by_pool[pool].append(row)

    result = []
    for pool in order:
        items = [r for r in by_pool[pool] if r["state"] != "empty"]
        held = sum(1 for r in items if r["state"] == "held")
        result.append(
            {
                "name": pool,
                "total": len(items),
                "held": held,
                "free": sum(1 for r in items if r["state"] == "free"),
                "items": [
                    {
                        "name": r["name"],
                        "state": r["state"],
                        "holder": r["holder"],
                        "acquired_at": r["acquired_at"],
                        "data": _decode(r["data"]),
                    }
                    for r in items
                ],
            }
        )
    return result


def meta() -> Dict[str, object]:
    """Static choices the spawn form needs — straight from the registries."""
    return {
        "agents": [{"name": a.name, "summary": a.summary} for a in AGENTS],
        "models": list(CLAUDE_MODELS),
        "permission_modes": list(CLAUDE_PERMISSION_MODES),
    }


# ---------------------------------------------------------------------------
# Actions — a JSON body becomes argv for the real command
# ---------------------------------------------------------------------------


def _str(payload: Dict[str, object], key: str) -> str:
    value = payload.get(key)
    return str(value).strip() if value is not None else ""


def _require(payload: Dict[str, object], key: str, action: str) -> str:
    value = _str(payload, key)
    if not value:
        raise CorralError(f"{action} needs '{key}'")
    return value


def _spawn_argv(payload: Dict[str, object]) -> List[str]:
    argv: List[str] = [_require(payload, "repo", "spawn")]
    branch = _str(payload, "branch")
    if branch:
        argv.append(branch)
    for flag, key in (
        ("--agent", "agent"),
        ("--model", "model"),
        ("--permission-mode", "permission_mode"),
        ("--prompt", "prompt"),
        ("--base", "base"),
        ("--ratio", "ratio"),
        ("--label", "label"),
    ):
        value = _str(payload, key)
        if value:
            argv += [flag, value]
    if payload.get("no_setup"):
        argv.append("--no-setup")
    # Spawning from a browser shouldn't yank the herdr session's focus unless
    # the user asked for it (the CLI focuses by default).
    if not payload.get("focus"):
        argv.append("--no-focus")
    return argv


def _release_argv(payload: Dict[str, object]) -> List[str]:
    pool = _require(payload, "pool", "release")
    item = _require(payload, "item", "release")
    # --force: the UI releases on the holder's behalf, not as the server's own
    # user, so skip the "held by someone else" guard.
    return ["release", f"{pool}/{item}", "--force"]


def perform(ctx: Context, action: str, payload: Dict[str, object]) -> Dict[str, object]:
    """Dispatch a write action by running the corresponding corral command."""
    from .commands import close, focus, resource, spawn

    if action == "spawn":
        module, argv = spawn, _spawn_argv(payload)
    elif action == "focus":
        module, argv = focus, [_require(payload, "workspace", "focus")]
    elif action == "close":
        module, argv = close, [_require(payload, "workspace", "close"), "--force"]
    elif action == "release":
        module, argv = resource, _release_argv(payload)
    else:
        raise CorralError(f"unknown action '{action}'")

    parsed = parse_args(module.SPEC, tuple(argv), ctx.settings)
    module.run(ctx, parsed)
    return {"ok": True, "action": action}


# ---------------------------------------------------------------------------
# HTTP server
# ---------------------------------------------------------------------------


class _Handler(BaseHTTPRequestHandler):
    server_version = "corral-monitor"

    # Routing -------------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler API)
        path = self.path.split("?", 1)[0]
        if path == "/":
            self._send(200, INDEX_HTML.encode("utf-8"), "text/html; charset=utf-8")
            return
        if path == "/api/meta":
            self._json(200, meta())
            return
        if path == "/api/state":
            self._guarded(lambda: snapshot(self._ctx()))
            return
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if not path.startswith("/api/"):
            self._json(404, {"error": "not found"})
            return
        action = path[len("/api/"):].strip("/")
        payload = self._body()
        if payload is None:
            return  # _body already answered with a 400
        self._guarded(lambda: perform(self._ctx(), action, payload))

    # Helpers -------------------------------------------------------------

    def _ctx(self) -> Context:
        return self.server.ctx  # type: ignore[attr-defined]

    def _body(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            payload = json.loads(raw or b"{}")
        except ValueError:
            self._json(400, {"error": "invalid JSON body"})
            return None
        if not isinstance(payload, dict):
            self._json(400, {"error": "JSON body must be an object"})
            return None
        return payload

    def _guarded(self, work) -> None:
        """Run `work`, mapping CorralError -> 400 and anything else -> 500."""
        try:
            self._json(200, work())
        except CorralError as exc:
            self._json(400, {"error": str(exc)})
        except Exception as exc:  # keep the server alive on unexpected faults
            self._json(500, {"error": f"{type(exc).__name__}: {exc}"})

    def _json(self, code: int, obj) -> None:
        self._send(code, json.dumps(obj).encode("utf-8"), "application/json")

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            pass  # client navigated away mid-response — nothing to do

    def log_message(self, fmt: str, *args) -> None:
        # Keep the terminal quiet; only requests to unknown paths are worth a peep.
        return


class MonitorServer(ThreadingHTTPServer):
    """Threaded so a slow spawn (several herdr calls) can't block polling."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: Tuple[str, int], ctx: Context) -> None:
        super().__init__(address, _Handler)
        self.ctx = ctx


def serve(ctx: Context, host: str, port: int) -> None:
    """Bind and serve the dashboard until interrupted (Ctrl-C)."""
    try:
        server = MonitorServer((host, port), ctx)
    except OSError as exc:
        raise CorralError(
            f"could not listen on {host}:{port} ({exc}) — "
            "is another monitor already running? try --port"
        ) from None

    shown = "localhost" if host in ("127.0.0.1", "0.0.0.0", "") else host
    ui.ok(f"corral monitor on {ui.C.bold}http://{shown}:{port}{ui.C.reset}")
    if host == "0.0.0.0":
        ui.warn("bound to 0.0.0.0 — reachable from your network, not just this machine")
    ui.info("press Ctrl-C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        ui.info("stopping monitor")
    finally:
        server.server_close()


# ---------------------------------------------------------------------------
# The dashboard (single self-contained page)
# ---------------------------------------------------------------------------

INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>corral monitor</title>
<style>
:root {
  --bg: #f6f7f9; --panel: #fff; --border: #e3e6ea; --text: #1c2024;
  --muted: #6b7280; --accent: #7c5cff; --accent-fg: #fff;
  --ok: #1a7f4b; --ok-bg: #e6f6ec; --warn: #9a6700; --warn-bg: #fff4d6;
  --danger: #c0392b; --danger-bg: #fdecea; --chip: #eef0f3;
  --shadow: 0 1px 2px rgba(0,0,0,.06), 0 4px 12px rgba(0,0,0,.04);
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0f1115; --panel: #171a21; --border: #262b34; --text: #e6e8eb;
    --muted: #8b93a1; --accent: #9d86ff; --accent-fg: #16121f;
    --ok: #4ade80; --ok-bg: #14301f; --warn: #f5c65b; --warn-bg: #33280c;
    --danger: #ff6b5e; --danger-bg: #3a1512; --chip: #222834;
    --shadow: none;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--text);
  font: 14px/1.5 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
}
a { color: var(--accent); }
header {
  position: sticky; top: 0; z-index: 5; background: var(--panel);
  border-bottom: 1px solid var(--border); padding: 14px 20px;
  display: flex; align-items: center; gap: 14px; flex-wrap: wrap;
}
header h1 { font-size: 16px; margin: 0; font-weight: 650; letter-spacing: .2px; }
header .sub { color: var(--muted); font-size: 12px; }
header .spacer { flex: 1; }
.dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%;
  background: var(--muted); margin-right: 6px; vertical-align: middle; }
.dot.live { background: var(--ok); }
.dot.err { background: var(--danger); }
main { padding: 20px; max-width: 1100px; margin: 0 auto; }
section { margin-bottom: 28px; }
section > h2 {
  font-size: 12px; text-transform: uppercase; letter-spacing: .08em;
  color: var(--muted); margin: 0 0 12px; font-weight: 600;
}
button {
  font: inherit; cursor: pointer; border: 1px solid var(--border);
  background: var(--panel); color: var(--text); border-radius: 8px;
  padding: 7px 12px; transition: filter .12s, border-color .12s;
}
button:hover { filter: brightness(1.05); border-color: var(--accent); }
button.primary { background: var(--accent); color: var(--accent-fg); border-color: transparent; font-weight: 600; }
button.danger { color: var(--danger); }
button.small { padding: 4px 9px; font-size: 12px; border-radius: 6px; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 14px; }
.card {
  background: var(--panel); border: 1px solid var(--border); border-radius: 12px;
  padding: 16px; box-shadow: var(--shadow);
}
.card .row1 { display: flex; align-items: baseline; gap: 8px; }
.card .label { font-weight: 650; font-size: 15px; }
.card .id { color: var(--muted); font-size: 12px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.card .meta { color: var(--muted); font-size: 12.5px; margin-top: 4px; word-break: break-all; }
.card .meta b { color: var(--text); font-weight: 500; }
.badge {
  display: inline-block; font-size: 11px; padding: 2px 8px; border-radius: 999px;
  background: var(--chip); color: var(--muted); font-weight: 600; letter-spacing: .02em;
}
.badge.running, .badge.busy, .badge.working { background: var(--ok-bg); color: var(--ok); }
.badge.idle, .badge.waiting { background: var(--warn-bg); color: var(--warn); }
.card .actions { margin-top: 14px; display: flex; gap: 8px; }
.res { margin-top: 12px; padding-top: 12px; border-top: 1px dashed var(--border); }
.res .h { font-size: 11px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); margin-bottom: 6px; }
.chips { display: flex; flex-wrap: wrap; gap: 6px; }
.chip {
  font-size: 12px; background: var(--chip); border-radius: 6px; padding: 3px 8px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}
.chip.none { color: var(--muted); font-family: inherit; background: transparent; padding: 0; }
table { width: 100%; border-collapse: collapse; }
.card.pool { padding: 0; overflow: hidden; }
.card.pool .phead {
  display: flex; align-items: center; gap: 8px; padding: 12px 16px;
  border-bottom: 1px solid var(--border);
}
.card.pool .pname { font-weight: 650; }
.card.pool table td { padding: 7px 16px; border-bottom: 1px solid var(--border); font-size: 13px; }
.card.pool table tr:last-child td { border-bottom: none; }
.card.pool .iname { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.state { font-size: 11px; font-weight: 600; }
.state.free { color: var(--ok); }
.state.held { color: var(--warn); }
.state.retired { color: var(--muted); }
.holder { color: var(--muted); font-size: 12px; word-break: break-all; }
.empty { color: var(--muted); padding: 24px; text-align: center; border: 1px dashed var(--border); border-radius: 12px; }
.banner { background: var(--danger-bg); color: var(--danger); padding: 10px 14px; border-radius: 8px; margin-bottom: 16px; display: none; }
.banner.show { display: block; }
/* modal */
.overlay { position: fixed; inset: 0; background: rgba(0,0,0,.45); display: none; align-items: flex-start; justify-content: center; padding: 40px 16px; z-index: 20; }
.overlay.show { display: flex; }
.modal { background: var(--panel); border: 1px solid var(--border); border-radius: 14px; padding: 22px; width: 480px; max-width: 100%; box-shadow: var(--shadow); }
.modal h3 { margin: 0 0 16px; font-size: 16px; }
.field { margin-bottom: 12px; }
.field label { display: block; font-size: 12px; color: var(--muted); margin-bottom: 4px; }
.field input, .field select {
  width: 100%; font: inherit; padding: 8px 10px; border: 1px solid var(--border);
  border-radius: 8px; background: var(--bg); color: var(--text);
}
.field.check { display: flex; align-items: center; gap: 8px; }
.field.check input { width: auto; }
.field.check label { margin: 0; }
.two { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.modal .foot { display: flex; justify-content: flex-end; gap: 8px; margin-top: 18px; }
.hint { font-size: 11.5px; color: var(--muted); margin-top: 4px; }
</style>
</head>
<body>
<header>
  <h1>🐎 corral monitor</h1>
  <span class="sub"><span id="dot" class="dot"></span><span id="status">connecting…</span></span>
  <span class="spacer"></span>
  <button class="primary" id="spawnBtn">+ Spawn agent</button>
  <button id="refreshBtn">Refresh</button>
</header>
<main>
  <div id="banner" class="banner"></div>

  <section>
    <h2>Agents <span id="agentCount" class="sub"></span></h2>
    <div id="agents" class="grid"></div>
    <div id="agentsEmpty" class="empty" style="display:none">
      No active agent workspaces. Spawn one to get started.
    </div>
  </section>

  <section>
    <h2>Resource pools <span id="poolCount" class="sub"></span></h2>
    <div id="pools" class="grid"></div>
    <div id="poolsEmpty" class="empty" style="display:none">No resource pools.</div>
  </section>
</main>

<div class="overlay" id="overlay">
  <div class="modal">
    <h3>Spawn agent</h3>
    <div class="field">
      <label>Repository path *</label>
      <input id="f_repo" placeholder="~/dev/app or /path/to/repo" autocomplete="off">
      <div class="hint">Any path inside the git repo to branch from.</div>
    </div>
    <div class="field">
      <label>Branch (optional)</label>
      <input id="f_branch" placeholder="auto: from prompt, else <prefix>/<repo>-<timestamp>" autocomplete="off">
    </div>
    <div class="two">
      <div class="field">
        <label>Agent</label>
        <select id="f_agent"></select>
      </div>
      <div class="field">
        <label>Base ref (optional)</label>
        <input id="f_base" placeholder="default: HEAD" autocomplete="off">
      </div>
    </div>
    <div class="two">
      <div class="field">
        <label>Model (claude only)</label>
        <select id="f_model"></select>
      </div>
      <div class="field">
        <label>Permission mode (claude only)</label>
        <select id="f_permission_mode"></select>
      </div>
    </div>
    <div class="field">
      <label>Opening prompt (optional)</label>
      <input id="f_prompt" placeholder="e.g. fix the failing tax tests" autocomplete="off">
    </div>
    <div class="field check">
      <input type="checkbox" id="f_focus">
      <label for="f_focus">Switch the herdr session's focus to the new agent</label>
    </div>
    <div class="field check">
      <input type="checkbox" id="f_no_setup">
      <label for="f_no_setup">Skip the repo's .corral/setup.sh</label>
    </div>
    <div class="foot">
      <button id="cancelBtn">Cancel</button>
      <button class="primary" id="submitBtn">Spawn</button>
    </div>
  </div>
</div>

<script>
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, c =>
  ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

let META = { agents: [], models: [], permission_modes: [] };
let refreshing = false;

function showBanner(msg) {
  const b = $("banner");
  b.textContent = msg;
  b.classList.add("show");
}
function clearBanner() { $("banner").classList.remove("show"); }

function setStatus(ok, text) {
  $("dot").className = "dot " + (ok ? "live" : "err");
  $("status").textContent = text;
}

async function api(path, opts) {
  const res = await fetch(path, opts);
  let data = {};
  try { data = await res.json(); } catch (e) {}
  if (!res.ok) throw new Error(data.error || ("HTTP " + res.status));
  return data;
}

function agentCard(a) {
  const res = a.resources.length
    ? `<div class="chips">${a.resources.map(r =>
        `<span class="chip" title="${esc(r.acquired_at)}">${esc(r.pool)}/${esc(r.name)}</span>`).join("")}</div>`
    : `<span class="chip none">none held</span>`;
  const st = esc(a.status).toLowerCase();
  return `<div class="card">
    <div class="row1">
      <span class="label">${esc(a.label)}</span>
      <span class="id">${esc(a.id)}</span>
      <span style="flex:1"></span>
      <span class="badge ${st}">${esc(a.status)}</span>
    </div>
    <div class="meta"><b>${esc(a.repo)}</b> · ${esc(a.branch)}</div>
    <div class="meta">${esc(a.worktree)}</div>
    <div class="res">
      <div class="h">Resources</div>
      ${res}
    </div>
    <div class="actions">
      <button class="small" data-act="focus" data-ws="${esc(a.id)}">Focus</button>
      <button class="small danger" data-act="close" data-ws="${esc(a.id)}" data-label="${esc(a.label)}">Close</button>
    </div>
  </div>`;
}

function poolCard(p) {
  const rows = p.items.map(it => {
    const rel = it.state === "held"
      ? `<button class="small" data-act="release" data-pool="${esc(p.name)}" data-item="${esc(it.name)}">Release</button>`
      : "";
    return `<tr>
      <td class="iname">${esc(it.name)}</td>
      <td><span class="state ${esc(it.state)}">${esc(it.state)}</span></td>
      <td class="holder">${esc(it.holder)}</td>
      <td style="text-align:right">${rel}</td>
    </tr>`;
  }).join("");
  return `<div class="card pool">
    <div class="phead">
      <span class="pname">${esc(p.name)}</span>
      <span class="badge">${p.held}/${p.total} held</span>
    </div>
    <table><tbody>${rows || `<tr><td class="holder" style="padding:14px 16px">empty pool</td></tr>`}</tbody></table>
  </div>`;
}

function render(state) {
  const agents = state.agents || [];
  const pools = state.pools || [];
  $("agents").innerHTML = agents.map(agentCard).join("");
  $("agentsEmpty").style.display = agents.length ? "none" : "block";
  $("agentCount").textContent = agents.length ? `(${agents.length})` : "";
  $("pools").innerHTML = pools.map(poolCard).join("");
  $("poolsEmpty").style.display = pools.length ? "none" : "block";
  $("poolCount").textContent = pools.length ? `(${pools.length})` : "";
}

async function refresh() {
  if (refreshing) return;
  refreshing = true;
  try {
    const state = await api("/api/state");
    render(state);
    clearBanner();
    setStatus(true, "live · " + new Date().toLocaleTimeString());
  } catch (e) {
    setStatus(false, "error");
    showBanner("Could not load state: " + e.message);
  } finally {
    refreshing = false;
  }
}

async function act(payload) {
  try {
    await api("/api/" + payload.action, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload.body || {}),
    });
    clearBanner();
    await refresh();
  } catch (e) {
    showBanner(payload.action + " failed: " + e.message);
  }
}

document.addEventListener("click", (ev) => {
  const btn = ev.target.closest("button[data-act]");
  if (!btn) return;
  const act_ = btn.dataset.act;
  if (act_ === "focus") {
    act({ action: "focus", body: { workspace: btn.dataset.ws } });
  } else if (act_ === "close") {
    if (confirm(`Close workspace ${btn.dataset.label} (${btn.dataset.ws})?\nIts worktree will be removed.`))
      act({ action: "close", body: { workspace: btn.dataset.ws } });
  } else if (act_ === "release") {
    act({ action: "release", body: { pool: btn.dataset.pool, item: btn.dataset.item } });
  }
});

// Spawn modal
function fillSelect(sel, values, extra) {
  sel.innerHTML = (extra ? [extra] : []).concat(values.map(v =>
    typeof v === "string" ? { value: v, text: v } : v))
    .map(o => `<option value="${esc(o.value)}">${esc(o.text)}</option>`).join("");
}
function openModal() {
  fillSelect($("f_agent"), META.agents.map(a => ({ value: a.name, text: a.name + " — " + a.summary })));
  fillSelect($("f_model"), META.models, { value: "", text: "default" });
  fillSelect($("f_permission_mode"), META.permission_modes, { value: "", text: "default" });
  $("overlay").classList.add("show");
  $("f_repo").focus();
}
function closeModal() { $("overlay").classList.remove("show"); }

async function submitSpawn() {
  const body = {
    repo: $("f_repo").value.trim(),
    branch: $("f_branch").value.trim(),
    agent: $("f_agent").value,
    model: $("f_model").value,
    permission_mode: $("f_permission_mode").value,
    prompt: $("f_prompt").value.trim(),
    base: $("f_base").value.trim(),
    focus: $("f_focus").checked,
    no_setup: $("f_no_setup").checked,
  };
  if (!body.repo) { $("f_repo").focus(); return; }
  const btn = $("submitBtn");
  btn.disabled = true; btn.textContent = "Spawning…";
  try {
    await api("/api/spawn", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    closeModal();
    ["f_repo","f_branch","f_prompt","f_base"].forEach(id => $(id).value = "");
    clearBanner();
    await refresh();
  } catch (e) {
    showBanner("spawn failed: " + e.message);
  } finally {
    btn.disabled = false; btn.textContent = "Spawn";
  }
}

$("spawnBtn").onclick = openModal;
$("cancelBtn").onclick = closeModal;
$("submitBtn").onclick = submitSpawn;
$("refreshBtn").onclick = refresh;
$("overlay").addEventListener("click", (e) => { if (e.target === $("overlay")) closeModal(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeModal(); });

(async function init() {
  try { META = await api("/api/meta"); } catch (e) {}
  await refresh();
  setInterval(refresh, 4000);
})();
</script>
</body>
</html>
"""
