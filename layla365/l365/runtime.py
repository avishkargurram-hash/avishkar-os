"""The 24/7 runner: ONE process hosting all nine agents.

Today it keeps heartbeats, enforces approved actions, and exposes a local
health endpoint. Per-agent evaluators (what each agent watches for) plug in
later through l365/plugins/<agent>.py with a tick(agent) function.
"""
import http.server
import importlib
import json
import signal
import threading
import time
import traceback

from . import config, db
from .agent import Agent
from . import executors  # noqa: F401  (registers executors)
from . import taskloop

TICK_SECONDS = 30
HEALTH_PORT = 8090


class Runner:
    def __init__(self):
        self.cfg = config.load()
        self.agents = {n: Agent(n, c) for n, c in self.cfg["agents"].items()}
        self.core = db.connect("core")
        self.stop = threading.Event()
        self.last_tick = None
        self.last_error = None

    def q(self, sql, args=None, fetch=False):
        with self.core.cursor() as cur:
            cur.execute(sql, args)
            return cur.fetchall() if fetch else None

    def ensure_state(self):
        for name, c in self.cfg["agents"].items():
            self.q("INSERT INTO core.agent_state(agent, mode) VALUES (%s,%s) ON CONFLICT DO NOTHING",
                   (name, c.get("mode", "shadow")))

    def heartbeat(self, component, info=None):
        self.q("INSERT INTO core.heartbeat(component, ts, info) VALUES (%s, now(), %s) "
               "ON CONFLICT (component) DO UPDATE SET ts=now(), info=EXCLUDED.info",
               (component, db.Json(info or {})))

    def process_approvals(self):
        # expire stale
        self.q("UPDATE core.approvals SET status='expired' WHERE status='pending' AND expires_at < now()")
        self.q("UPDATE core.actions a SET status='rejected', reason='approval expired/rejected' "
               "FROM core.approvals p WHERE a.approval_id=p.id AND a.status='pending_approval' "
               "AND p.status IN ('rejected','expired')")
        rows = self.q(
            "SELECT a.id, a.agent, a.kind, a.params FROM core.actions a "
            "JOIN core.approvals p ON p.id=a.approval_id "
            "WHERE a.status='pending_approval' AND p.status='approved'", fetch=True)
        for aid, agent_name, kind, params in rows:
            agent = self.agents.get(agent_name)
            if agent is None or not agent.state()["enabled"]:
                self.q("UPDATE core.actions SET status='blocked', reason='agent disabled at execution time' WHERE id=%s", (aid,))
                continue
            status, result = agent.run_executor(kind, params or {})
            self.q("UPDATE core.actions SET status=%s, result=%s, reason=%s WHERE id=%s",
                   (status, db.Json(result), "executed after human approval", aid))

    def tick(self):
        try:  # re-send reports/results that were queued while Layla was unreachable
            from . import gateway
            if gateway.outbox_size():
                gateway.flush_outbox()
        except Exception as e:  # noqa: BLE001
            self.last_error = f"outbox: {type(e).__name__}: {e}"
        for name, agent in self.agents.items():
            try:
                st = agent.state()
                self.heartbeat(f"agent:{name}", {"enabled": st["enabled"], "mode": st["mode"]})
                if not st["enabled"]:
                    continue
                try:
                    mod = importlib.import_module(f"l365.plugins.{name}")
                except ModuleNotFoundError:
                    mod = None
                if mod and hasattr(mod, "tick"):
                    mod.tick(agent)
                taskloop.step(agent)
            except Exception as e:  # noqa: BLE001  one agent never stops the others
                self.last_error = f"{name}: {type(e).__name__}: {e}"
                traceback.print_exc()
        self.process_approvals()
        try:  # Naina's approved code changes -> branch + pull request
            from . import github_flow
            github_flow.tick()
        except Exception as e:  # noqa: BLE001
            self.last_error = f"github_flow: {type(e).__name__}: {e}"
        try:  # owner's Telegram window: read his taps/commands, send the hourly digest
            from . import telegram
            telegram.poll()
            now = time.time()
            if now - getattr(self, "_last_digest", 0) >= 3600:
                telegram.send_digest()
                self._last_digest = now
        except Exception as e:  # noqa: BLE001
            self.last_error = f"telegram: {type(e).__name__}: {e}"
        self.last_tick = time.time()
        self.heartbeat("runner", {"agents": len(self.agents), "last_error": self.last_error})

    def snapshot(self):
        rows = self.q("SELECT agent, enabled, mode FROM core.agent_state ORDER BY agent", fetch=True)
        return {"alive": True, "last_tick": self.last_tick, "last_error": self.last_error,
                "agents": [{"agent": a, "enabled": e, "mode": m} for a, e, m in rows]}

    def serve_health(self):
        runner = self

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):  # noqa: N802
                if self.path in ("/health", "/agents"):
                    body = json.dumps(runner.snapshot()).encode()
                    self.send_response(200)
                else:
                    body = b'{"error":"not found"}'
                    self.send_response(404)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        srv = http.server.ThreadingHTTPServer(("127.0.0.1", HEALTH_PORT), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        return srv

    def run(self):
        self.ensure_state()
        self.serve_health()
        signal.signal(signal.SIGTERM, lambda *a: self.stop.set())
        signal.signal(signal.SIGINT, lambda *a: self.stop.set())
        print(f"[l365] runner up: {len(self.agents)} agents, tick {TICK_SECONDS}s", flush=True)
        while not self.stop.is_set():
            try:
                self.tick()
            except Exception:  # noqa: BLE001
                traceback.print_exc()
                try:
                    self.core = db.connect("core")
                except Exception:  # noqa: BLE001
                    pass
            self.stop.wait(TICK_SECONDS)
        print("[l365] runner stopped", flush=True)
