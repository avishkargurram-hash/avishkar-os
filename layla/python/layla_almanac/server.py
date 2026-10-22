"""HTTP API. Bound to loopback; nginx exposes /api/almanac/ over TLS.

  POST /api/almanac/sync                    X-Layla-Secret: <ALMANAC_TOKEN>      merge pushed records, return changes
  GET  /api/almanac/state?since=<rev>       X-Layla-Secret: <ALMANAC_TOKEN>      records changed since rev (0 = everything)
  POST /api/almanac/tool/get_almanac_state  X-Layla-Secret|Bearer <ALMANAC_TOOL_TOKEN>   read-only summary for Layla
  GET  /api/almanac/ping                    no auth, no data

Family Connect + clipboard (need the Hub; owner = app token, member = a token the owner issued):
  GET  /api/almanac/family/state?since=     owner|member   shared records + members/presence
  POST /api/almanac/family/sync             owner|member   merge fshop:/fev: records
  POST /api/almanac/family/presence         owner|member   {status, note}
  POST /api/almanac/family/members          owner          {name, role} -> {id, token} (token shown once)
  POST /api/almanac/family/members/revoke   owner          {id}
  GET  /api/almanac/clip                    owner          recent clipboard items
  POST /api/almanac/clip                    owner          {text, device}
  POST /api/almanac/clip/clear              owner
  GET  /api/almanac/ws                      WebSocket; first frame {"t":"auth","token":...} (never in the URL)

The app token and the tool token are different on purpose: the app token ships inside an app, the tool
token only ever lives in Layla's agent config, and it can read a summary but never write."""

from __future__ import annotations

import hmac
import json
import select
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from . import ws
from .body import Body, BodyError
from .hub import Conn, Hub
from .store import AlmanacStore, ValidationError
from .summary import build_summary

MAX_BODY = 2 * 1024 * 1024
BASE = "/api/almanac"
WS_AUTH_WAIT = 10
WS_IDLE_PING = 25
WS_DEAD_AFTER = 90
WS_MSGS_PER_10S = 60
WS_ROBOT_PER_10S = 250   # joystick frames have their own, larger budget (~10 Hz while a stick is held)


def _eq(got: str, want: str) -> bool:
    return bool(want) and hmac.compare_digest(got.encode(), want.encode())


def make_handler(st: AlmanacStore, token: str, tool_token: str, hub: Optional[Hub] = None,
                 body: Optional[Body] = None):
    class H(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        _body_consumed = False

        def log_message(self, *a):
            pass

        def _send(self, code: int, obj: Optional[Dict[str, Any]] = None) -> None:
            body = b"" if obj is None else json.dumps(obj, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Layla-Secret")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Max-Age", "86400")
            self.send_header("Cache-Control", "no-store")
            if self.command == "POST" and not self._body_consumed:
                self.close_connection = True
                self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)

        def _app_authed(self) -> bool:
            return _eq(self.headers.get("X-Layla-Secret", ""), token)

        def _tool_authed(self) -> bool:
            got = self.headers.get("X-Layla-Secret", "")
            if not got:
                auth = self.headers.get("Authorization", "")
                got = auth[7:] if auth.startswith("Bearer ") else ""
            return _eq(got, tool_token)

        def _json_body(self) -> Optional[Dict[str, Any]]:
            """None means unusable; an empty body is an empty object."""
            try:
                n = int(self.headers.get("Content-Length", "0"))
                if n < 0:
                    return None
                if n > MAX_BODY:
                    if n <= 4 * MAX_BODY:  # drain so the client sees our answer, not a reset
                        left = n
                        while left > 0:
                            chunk = self.rfile.read(min(65536, left))
                            if not chunk:
                                break
                            left -= len(chunk)
                        self._body_consumed = True
                    return None
                raw = self.rfile.read(n)
                self._body_consumed = True
                d = json.loads(raw or b"{}")
                return d if isinstance(d, dict) else None
            except Exception:
                return None

        def _who(self) -> Optional[Dict[str, Any]]:
            """owner (app token) or an active family member; None if neither."""
            got = self.headers.get("X-Layla-Secret", "")
            if _eq(got, token):
                return {"id": "owner", "role": "owner", "name": (hub._meta("owner_name") if hub else "") or "Owner"}
            m = hub.auth_member(got) if hub else None
            return {**m, "role": "member"} if m else None

        def do_OPTIONS(self):
            self._send(204)

        def do_GET(self):
            u = urlparse(self.path)
            path = u.path.rstrip("/")
            if path == f"{BASE}/ping":
                return self._send(200, {"ok": True})
            if hub and path == f"{BASE}/ws":
                return self._ws()
            if hub and path == f"{BASE}/family/state":
                who = self._who()
                if not who:
                    return self._send(401, {"error": "unauthorized"})
                try:
                    since = max(0, int(parse_qs(u.query).get("since", ["0"])[0]))
                except ValueError:
                    return self._send(400, {"error": "bad since"})
                hub.touch(who["id"])
                recs, tombs, rev = hub.family.changes_since(since)
                return self._send(200, {"ok": True, "rev": rev, "records": recs, "tombstones": tombs,
                                        "members": hub.members_public(), "me": {k: who[k] for k in ("id", "name", "role")},
                                        "server_time": hub.family._now_ms()})
            if hub and path == f"{BASE}/clip":
                if not self._app_authed():
                    return self._send(401, {"error": "unauthorized"})
                return self._send(200, {"ok": True, "items": hub.clip_list()})
            if path == f"{BASE}/state":
                if not self._app_authed():
                    return self._send(401, {"error": "unauthorized"})
                try:
                    since = max(0, int(parse_qs(u.query).get("since", ["0"])[0]))
                except ValueError:
                    return self._send(400, {"error": "bad since"})
                recs, tombs, rev = st.changes_since(since)
                return self._send(200, {"ok": True, "rev": rev, "records": recs, "tombstones": tombs,
                                        "templates": st.templates(), "server_time": st._now_ms()})
            if path == f"{BASE}/tool/get_almanac_state":
                return self._tool({})
            if body is not None and path == f"{BASE}/body/state":
                if not self._app_authed():
                    return self._send(401, {"error": "unauthorized"})
                return self._send(200, {"ok": True, **body.state()})
            self._send(404, {"error": "not found"})

        def do_POST(self):
            path = urlparse(self.path).path.rstrip("/")
            if path == f"{BASE}/sync":
                if not self._app_authed():
                    return self._send(401, {"error": "unauthorized"})
                d = self._json_body()
                if d is None:
                    return self._send(400, {"error": "bad request"})
                recs, tombs = d.get("records", {}), d.get("tombstones", {})
                if not isinstance(recs, dict) or not isinstance(tombs, dict):
                    return self._send(400, {"error": "records and tombstones must be objects"})
                try:
                    since = max(0, int(d.get("since") or 0))
                    applied = st.merge(recs, tombs, d.get("templates"), str(d.get("device") or ""))
                except (ValidationError, ValueError, TypeError) as e:
                    return self._send(400, {"error": str(e)[:120]})
                changes, ctombs, rev = st.changes_since(since)
                return self._send(200, {"ok": True, "applied": applied, "rev": rev, "records": changes,
                                        "tombstones": ctombs, "templates": st.templates(),
                                        "server_time": st._now_ms()})
            if path == f"{BASE}/tool/get_almanac_state":
                d = self._json_body()
                return self._tool(d if d is not None else {})
            if hub and (path.startswith(f"{BASE}/family/") or path.startswith(f"{BASE}/clip")):
                return self._hub_post(path)
            if body is not None and (path.startswith(f"{BASE}/robot/") or path.startswith(f"{BASE}/avbox/")
                                     or path.startswith(f"{BASE}/home/") or path.startswith(f"{BASE}/presence/")):
                return self._body_post(path)
            self._send(404, {"error": "not found"})

        def _body_post(self, path: str) -> None:
            """Owner only: the robot and the AV box are never reachable with a family-member token."""
            if not self._app_authed():
                return self._send(401, {"error": "unauthorized"})
            d = self._json_body()
            if d is None:
                return self._send(400, {"error": "bad request"})
            try:
                if path == f"{BASE}/robot/drive":
                    r = body.drive(d.get("action"), d.get("speed", 200), d.get("seconds"))
                elif path == f"{BASE}/robot/stop":
                    r = body.stop()
                elif path == f"{BASE}/robot/config":
                    r = {"ok": True, "config": body.configure(d)}
                elif path == f"{BASE}/avbox/ir":
                    r = body.ir(d.get("op"), d.get("name"), wait=d.get("wait", True) is not False)
                elif path == f"{BASE}/avbox/display":
                    r = body.display(d.get("text"))
                elif path == f"{BASE}/avbox/switch":
                    r = body.switch(d.get("id"), d.get("on"))
                elif path == f"{BASE}/presence/config" and body.presence is not None:
                    r = {"ok": True, "presence": body.presence.configure(d)}
                elif path == f"{BASE}/presence/snooze" and body.presence is not None:
                    r = {"ok": True, "presence": body.presence.snooze(d.get("minutes"))}
                elif path == f"{BASE}/home/control":
                    r = body.home_control(d.get("device"), d.get("action"), d.get("value"))
                elif path == f"{BASE}/home/refresh":
                    r = body.home_refresh(bool(d.get("force")))
                else:
                    return self._send(404, {"error": "not found"})
            except BodyError as e:
                return self._send(400, {"ok": False, "error": str(e)[:160]})
            return self._send(200, r)

        def _hub_post(self, path: str) -> None:
            who = self._who()
            if not who:
                return self._send(401, {"error": "unauthorized"})
            owner = who["role"] == "owner"
            d = self._json_body()
            if d is None:
                return self._send(400, {"error": "bad request"})
            try:
                if path == f"{BASE}/family/sync":
                    recs, tombs = d.get("records", {}), d.get("tombstones", {})
                    if not isinstance(recs, dict) or not isinstance(tombs, dict):
                        return self._send(400, {"error": "records and tombstones must be objects"})
                    since = max(0, int(d.get("since") or 0))
                    applied = hub.family.merge(recs, tombs, None, who["id"])
                    hub.touch(who["id"])
                    changes, ctombs, rev = hub.family.changes_since(since)
                    if applied:
                        hub.broadcast({"t": "fam", "what": "data", "rev": rev})
                    return self._send(200, {"ok": True, "applied": applied, "rev": rev, "records": changes,
                                            "tombstones": ctombs, "server_time": hub.family._now_ms()})
                if path == f"{BASE}/family/presence":
                    hub.set_presence(who["id"], str(d.get("status") or ""), str(d.get("note") or ""),
                                     str(d.get("name") or "") if owner else "")
                    hub.broadcast({"t": "fam", "what": "presence"})
                    return self._send(200, {"ok": True, "members": hub.members_public()})
                if not owner:
                    return self._send(403, {"error": "owner only"})
                if path == f"{BASE}/family/members":
                    mid, tok = hub.add_member(str(d.get("name") or ""), str(d.get("role") or "Member"))
                    hub.broadcast({"t": "fam", "what": "presence"})
                    return self._send(200, {"ok": True, "id": mid, "token": tok, "members": hub.members_public()})
                if path == f"{BASE}/family/members/revoke":
                    ok = hub.revoke(str(d.get("id") or ""))
                    hub.broadcast({"t": "fam", "what": "presence"})
                    return self._send(200 if ok else 404, {"ok": ok, "members": hub.members_public()})
                if path == f"{BASE}/clip":
                    item = hub.clip_add(d.get("text"), d.get("device"))
                    hub.broadcast({"t": "clip", "item": item}, owner_only=True)
                    return self._send(200, {"ok": True, "item": item})
                if path == f"{BASE}/clip/clear":
                    hub.clip_clear()
                    hub.broadcast({"t": "clips", "items": []}, owner_only=True)
                    return self._send(200, {"ok": True})
            except (ValidationError, ValueError, TypeError) as e:
                return self._send(400, {"error": str(e)[:120]})
            self._send(404, {"error": "not found"})

        # ---- WebSocket ---------------------------------------------------------------------------------------
        def _ws_identity(self, tok: Any) -> Optional[Tuple[str, str]]:
            if not isinstance(tok, str):
                return None
            if _eq(tok, token):
                return "owner", "owner"
            m = hub.auth_member(tok)
            return ("member", m["id"]) if m else None

        def _ws(self) -> None:
            key = self.headers.get("Sec-WebSocket-Key", "")
            if (self.headers.get("Upgrade", "").lower() != "websocket"
                    or "upgrade" not in self.headers.get("Connection", "").lower()
                    or not key or self.headers.get("Sec-WebSocket-Version") != "13"):
                return self._send(400, {"error": "websocket upgrade required"})
            sock = self.connection
            self.send_response_only(101, "Switching Protocols")
            self.send_header("Upgrade", "websocket")
            self.send_header("Connection", "Upgrade")
            self.send_header("Sec-WebSocket-Accept", ws.accept_key(key))
            self.end_headers()
            self.close_connection = True
            sock.settimeout(5)  # bounds sends only; reads are gated by select()
            buf, frag = bytearray(), bytearray()
            conn: Optional[Conn] = None
            started = last_rx = time.time()
            window_start, window_n, robot_n = time.time(), 0, 0
            try:
                while True:
                    ready, _, _ = select.select([sock], [], [], WS_IDLE_PING)
                    now = time.time()
                    if ready:
                        data = sock.recv(65536)
                        if not data:
                            break
                        buf += data
                        last_rx = now
                    else:
                        if conn is None and now - started > WS_AUTH_WAIT:
                            sock.sendall(ws.close_frame(4408))
                            break
                        if now - last_rx > WS_DEAD_AFTER:
                            break
                        sock.sendall(ws.encode_frame(ws.OP_PING))
                    while True:
                        fr = ws.decode_frame(buf)
                        if fr is None:
                            break
                        fin, op, payload = fr
                        if op == ws.OP_CLOSE:
                            sock.sendall(ws.close_frame(1000))
                            return
                        if op == ws.OP_PING:
                            sock.sendall(ws.encode_frame(ws.OP_PONG, payload))
                            continue
                        if op == ws.OP_PONG:
                            continue
                        if op in (ws.OP_TEXT, ws.OP_BIN):
                            frag = bytearray(payload)
                        elif op == ws.OP_CONT:
                            frag += payload
                            if len(frag) > ws.MAX_PAYLOAD:
                                raise ws.ProtocolError(1009, "message too large")
                        if not fin:
                            continue
                        try:
                            msg = json.loads(bytes(frag).decode())
                        except Exception:
                            msg = None
                        frag = bytearray()
                        if now - window_start > 10:
                            window_start, window_n, robot_n = now, 0, 0
                        is_robot = isinstance(msg, dict) and str(msg.get("t", "")).startswith("robot.")
                        if is_robot:
                            robot_n += 1
                        else:
                            window_n += 1
                        if window_n > WS_MSGS_PER_10S or robot_n > WS_ROBOT_PER_10S:
                            if body is not None and is_robot:
                                body.stop()
                            sock.sendall(ws.close_frame(4429))
                            return
                        if not isinstance(msg, dict):
                            continue
                        if conn is None:
                            ident = self._ws_identity(msg.get("token")) if msg.get("t") == "auth" else None
                            if not ident:
                                sock.sendall(ws.close_frame(4401))
                                return
                            conn = Conn(sock, *ident)
                            if not hub.register(conn):
                                sock.sendall(ws.close_frame(1013))
                                return
                            hub.touch(conn.member_id)
                            hello = {"t": "hello", "role": conn.role, "id": conn.member_id,
                                     "members": hub.members_public()}
                            if conn.role == "owner":
                                hello["clips"] = hub.clip_list()
                                if body is not None:
                                    hello["body"] = body.state()
                            conn.send(hello)
                            hub.broadcast({"t": "fam", "what": "presence"}, skip=conn)
                            continue
                        self._ws_msg(conn, msg)
            except (ws.ProtocolError, OSError) as e:
                try:
                    sock.sendall(ws.close_frame(e.code if isinstance(e, ws.ProtocolError) else 1006))
                except OSError:
                    pass
            finally:
                if conn is not None:
                    if body is not None and getattr(conn, "drove", False):
                        body.stop()          # the controller vanished: never leave the robot running
                    conn.closed = True
                    hub.unregister(conn)
                    hub.touch(conn.member_id)
                    hub.broadcast({"t": "fam", "what": "presence"})

        def _ws_msg(self, conn: Conn, msg: Dict[str, Any]) -> None:
            t = msg.get("t")
            try:
                if t == "ping":
                    conn.send({"t": "pong"})
                elif t == "clip" and conn.role == "owner":
                    item = hub.clip_add(msg.get("text"), msg.get("device"))
                    conn.send({"t": "clip_ack", "item": item})
                    hub.broadcast({"t": "clip", "item": item}, owner_only=True, skip=conn)
                elif t == "presence":
                    hub.set_presence(conn.member_id, str(msg.get("status") or ""), str(msg.get("note") or ""))
                    hub.broadcast({"t": "fam", "what": "presence"})
                elif body is not None and conn.role == "owner" and t in ("robot.drive", "robot.stop", "body.get"):
                    if t == "robot.drive":
                        conn.drove = True
                        r = body.drive(msg.get("a"), msg.get("s", 200))
                        if not r.get("ok"):
                            conn.send({"t": "robot.err", "msg": r.get("msg") or "drive failed"})
                    elif t == "robot.stop":
                        body.stop()
                    else:
                        conn.send({"t": "body", **body.state()})
            except BodyError as e:
                conn.send({"t": "robot.err", "msg": str(e)[:120]})
            except ValidationError as e:
                conn.send({"t": "err", "msg": str(e)[:120]})

        def _tool(self, d: Dict[str, Any]) -> None:
            if not self._tool_authed():
                return self._send(401, {"error": "unauthorized"})
            try:
                self._send(200, build_summary(st, str(d.get("date") or "")))
            except Exception:
                self._send(500, {"ok": False, "message": "Almanac summary failed. Tell the owner."})

    return H


class _Server(ThreadingHTTPServer):
    daemon_threads = True  # WebSocket handler threads must not block shutdown
    request_queue_size = 128  # stdlib default of 5 resets bursts of parallel connections


def serve(st: AlmanacStore, token: str, tool_token: str, host: str = "127.0.0.1", port: int = 8150,
          hub: Optional[Hub] = None, body: Optional[Body] = None):
    return _Server((host, port), make_handler(st, token, tool_token, hub, body))
