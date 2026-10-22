"""HTTP API the phone talks to. Bound to localhost; nginx exposes /wa/ over TLS.
Every request needs the device bearer token."""

from __future__ import annotations

import hmac
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict

from .engine import Engine, Incoming

MAX_BODY = 64 * 1024


def make_handler(engine: Engine, token: str):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):  # keep tokens/messages out of stderr logs
            pass

        def _authed(self) -> bool:
            got = self.headers.get("Authorization", "")
            return hmac.compare_digest(got.encode(), f"Bearer {token}".encode())

        def _send(self, code: int, obj: Dict[str, Any]) -> None:
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if not self._authed():
                return self._send(401, {"error": "unauthorized"})
            if self.path.rstrip("/").endswith("/ping"):
                return self._send(200, {"ok": True, "enabled": engine.st.enabled()})
            if self.path.rstrip("/").endswith("/status"):         # for the owner's Almanac app
                now = engine.st.clock()
                return self._send(200, {"ok": True, "enabled": engine.st.enabled(), "groups": engine.st.groups(),
                                        "muted": engine.st.muted(),
                                        "sent_24h": engine.st.count_replies_since(now - 86400),
                                        "recent": engine.st.recent_activity(8)})
            self._send(404, {"error": "not found"})

        def do_POST(self):
            if not self._authed():
                return self._send(401, {"error": "unauthorized"})
            try:
                n = int(self.headers.get("Content-Length", "0"))
                if n > MAX_BODY:
                    return self._send(413, {"error": "too large"})
                d = json.loads(self.rfile.read(n) or b"{}")
                if not isinstance(d, dict):
                    raise ValueError("body must be an object")
            except Exception:
                return self._send(400, {"error": "bad request"})
            p = self.path.rstrip("/").rsplit("/", 1)[-1]
            try:
                if p == "message":
                    return self._send(200, engine.handle(Incoming.from_json(d)))
                if p == "commit":
                    return self._send(200, engine.commit(str(d.get("id", ""))))
                if p == "ack":
                    return self._send(200, engine.ack(str(d.get("id", "")), bool(d.get("ok")),
                                                      str(d.get("error", ""))))
                if p == "cancel":
                    return self._send(200, engine.cancel(str(d.get("id", ""))))
                if p == "power":                                    # the app's kill switch (same as Telegram /wa on|off)
                    on = d.get("on")
                    if not isinstance(on, bool):
                        return self._send(400, {"error": "on must be true or false"})
                    engine.st.set_enabled(on)
                    engine.st.audit("wa_power", {"on": on, "via": "app"})
                    return self._send(200, {"ok": True, "enabled": engine.st.enabled()})
            except Exception as e:
                engine.st.audit("server_error", {"path": p, "err": str(e)[:200]})
                return self._send(500, {"error": "internal", "action": "none"})
            self._send(404, {"error": "not found"})

    return H


def serve(engine: Engine, token: str, host: str = "127.0.0.1", port: int = 8120) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), make_handler(engine, token))
