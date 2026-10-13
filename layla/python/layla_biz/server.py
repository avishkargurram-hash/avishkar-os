"""HTTP API for ElevenLabs webhook tools. Bound to localhost; nginx exposes /biz/ over TLS.
Every request needs the shared secret as `Authorization: Bearer <secret>` or `X-Layla-Secret`.
/admin/cmd is for the local Telegram controller only (loopback + admin token); nginx never proxies it."""

from __future__ import annotations

import hmac
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, Optional

from .tools import Tools

MAX_BODY = 32 * 1024


def make_handler(tools: Tools, secret: str, admin_token: str = "",
                 admin: Optional[Callable[[str], Optional[str]]] = None):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _authed(self) -> bool:
            got = self.headers.get("Authorization", "") or ("Bearer " + self.headers.get("X-Layla-Secret", ""))
            return hmac.compare_digest(got.encode(), f"Bearer {secret}".encode())

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
                return self._send(200, {"ok": True, "enabled": tools.st.enabled()})
            self._send(404, {"error": "not found"})

        def do_POST(self):
            path = self.path.split("?")[0].rstrip("/")
            if path == "/admin/cmd":
                return self._admin()
            if not self._authed():
                return self._send(401, {"error": "unauthorized"})
            d = self._body()
            if d is None:
                return self._send(400, {"error": "bad request"})
            name = path.rsplit("/", 1)[-1]
            routes = {"init": tools.init_vars, "get_offering": tools.get_offering,
                      "capture_lead": tools.capture_lead, "request_callback": tools.request_callback,
                      "escalate_to_owner": tools.escalate}
            fn = routes.get(name)
            if fn is None:
                return self._send(404, {"error": "not found"})
            try:
                return self._send(200, fn(d))
            except Exception as e:
                tools.st.audit("server_error", {"path": name, "err": str(e)[:200]})
                if name == "init":
                    return self._send(200, tools.init_vars({}))
                return self._send(500, {"ok": False, "message": "Tell the person Avishkar will reply personally."})

        def _body(self) -> Optional[Dict[str, Any]]:
            try:
                n = int(self.headers.get("Content-Length", "0"))
                if n > MAX_BODY:
                    return None
                d = json.loads(self.rfile.read(n) or b"{}")
                return d if isinstance(d, dict) else None
            except Exception:
                return None

        def _admin(self):
            ok = (admin is not None and admin_token and self.client_address[0] in ("127.0.0.1", "::1")
                  and hmac.compare_digest(self.headers.get("Authorization", "").encode(),
                                          f"Bearer {admin_token}".encode()))
            if not ok:
                return self._send(401, {"error": "unauthorized"})
            d = self._body()
            if d is None:
                return self._send(400, {"error": "bad request"})
            self._send(200, {"reply": admin(str(d.get("text", "")))})

    return H


def serve(tools: Tools, secret: str, host: str = "127.0.0.1", port: int = 8130,
          admin_token: str = "", admin=None) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), make_handler(tools, secret, admin_token, admin))
