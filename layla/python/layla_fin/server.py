"""Loopback-only admin endpoint for the Telegram controller. No public routes: nginx never proxies it."""

from __future__ import annotations

import hmac
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Optional

MAX_BODY = 16 * 1024


def serve(admin: Callable[[str], Optional[str]], admin_token: str, host: str = "127.0.0.1",
          port: int = 8140) -> ThreadingHTTPServer:
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, obj):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            ok = (self.path.split("?")[0].rstrip("/") == "/admin/cmd"
                  and self.client_address[0] in ("127.0.0.1", "::1")
                  and hmac.compare_digest(self.headers.get("Authorization", "").encode(),
                                          f"Bearer {admin_token}".encode()))
            if not ok:
                return self._send(401, {"error": "unauthorized"})
            try:
                n = int(self.headers.get("Content-Length", "0"))
                d = json.loads(self.rfile.read(n) if 0 < n <= MAX_BODY else b"{}")
                text = str(d.get("text", "")) if isinstance(d, dict) else ""
            except Exception:
                return self._send(400, {"error": "bad request"})
            self._send(200, {"reply": admin(text)})

    return ThreadingHTTPServer((host, port), H)
