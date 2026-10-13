import base64
import datetime as dt
import json
import os
import socket
import struct
import threading
import time
import urllib.error
import urllib.request

import pytest

from layla_almanac import ws
from layla_almanac.hub import Hub
from layla_almanac.server import serve
from layla_almanac.store import AlmanacStore, ValidationError
from layla_almanac.summary import build_summary

TOKEN = "a" * 32
TOOL = "b" * 32
NOW = dt.datetime(2026, 10, 7, 9, 0, tzinfo=dt.timezone.utc)  # Wednesday, ISO week 41
TODAY = "2026-10-07"


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


@pytest.fixture
def clock():
    return Clock(NOW.timestamp())


@pytest.fixture
def store(clock):
    return AlmanacStore(":memory:", clock=clock)


@pytest.fixture
def hub(clock):
    return Hub(":memory:", clock=clock)


@pytest.fixture
def api(store, hub):
    srv = serve(store, TOKEN, TOOL, port=0, hub=hub)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    yield f"http://127.0.0.1:{port}/api/almanac", port
    srv.shutdown()
    srv.server_close()


def call(url, method="GET", body=None, secret=None):
    h = {"X-Layla-Secret": secret} if secret else {}
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read()
        return e.code, (json.loads(raw) if raw else None)


def ms(clock, d=0):
    return int((clock.t + d) * 1000)


def cipher(ct="QUJD"):
    return {"v": 1, "iv": "AAAAAAAAAAAAAAAA", "ct": ct}


# ---- store: new key prefixes ----------------------------------------------------------------------------------
def test_new_module_prefixes_roundtrip(store, clock):
    recs = {
        "prj:p1": {"u": ms(clock), "v": {"name": "Spine rehab", "tasks": [], "milestones": []}},
        "chk:c1": {"u": ms(clock), "v": {"tier": "daily", "title": "Morning", "items": []}},
        "shop:s1": {"u": ms(clock), "v": {"name": "Milk"}},
        "exp:e1": {"u": ms(clock), "v": {"amt": 10, "type": "out"}},
        "alm:a1": {"u": ms(clock), "v": {"time": "06:30", "on": True}},
        "vh:h1": {"u": ms(clock), "v": cipher()},
        "vd:d1": {"u": ms(clock), "v": cipher()},
        "vp:k1": {"u": ms(clock), "v": cipher()},
    }
    assert store.merge(recs, {}) == 8
    assert store.get("prj:p1")["name"] == "Spine rehab"


def test_vault_records_must_look_like_ciphertext(store, clock):
    for bad in ({"title": "plain", "password": "hunter2"},  # plaintext
                {"v": 1, "iv": "AAAA", "ct": "not base64!!"},
                {"v": 2, "iv": "AAAA", "ct": "QUJD"},
                {"v": 1, "iv": "AAAA", "ct": "QUJD", "extra": "leak"},
                {"v": 1, "iv": "", "ct": "QUJD"}):
        with pytest.raises(ValidationError):
            store.merge({"vp:x": {"u": ms(clock), "v": bad}}, {})
    assert store.get("vp:x") is None


def test_vmeta_validation(store, clock):
    ok = {"salt": "c2FsdHNhbHRzYWx0c2E=", "ver": "dmVyaWZ5dmVyaWZ5", "iter": 310000}
    assert store.merge({"vmeta": {"u": ms(clock), "v": ok}}, {}) == 1
    for bad in ({**ok, "iter": 10}, {**ok, "iter": 10 ** 9}, {**ok, "salt": "!!"}, {"salt": "x"}, [1]):
        with pytest.raises(ValidationError):
            store.merge({"vmeta": {"u": ms(clock, 5), "v": bad}}, {})


def test_family_keys_not_accepted_in_personal_store(store, clock):
    with pytest.raises(ValidationError):
        store.merge({"fshop:x": {"u": ms(clock), "v": {"name": "Milk"}}}, {})


def test_oversized_vault_record_rejected(store, clock):
    with pytest.raises(ValidationError):
        store.merge({"vd:big": {"u": ms(clock), "v": cipher("A" * 600_000)}}, {})


# ---- summary: aggregates only ---------------------------------------------------------------------------------
def test_summary_includes_modules_and_excludes_private_data(store, clock):
    k = ms(clock)
    store.merge({
        "prj:p1": {"u": k, "v": {"name": "Muziclly", "status": "active", "due": "2026-12-01", "desc": "SECRET-DESC",
                                 "milestones": [{"id": "m1", "title": "Beta", "done": False, "due": "2026-11-01"},
                                                {"id": "m2", "title": "Alpha", "done": True}],
                                 "tasks": [{"id": "t1", "title": "x", "done": True}, {"id": "t2", "title": "y"}]}},
        "chk:c1": {"u": k, "v": {"tier": "weekly", "title": "Weekly review",
                                 "items": [{"id": "i1", "t": "Plan"}, {"id": "i2", "t": "Invoice"}],
                                 "done": {"2026-W41": ["i1"], "2026-W40": ["i2"]}}},
        "shop:s1": {"u": k, "v": {"name": "Milk", "qty": "2"}},
        "shop:s2": {"u": k, "v": {"name": "Eggs", "done": True}},
        "exp:e1": {"u": k, "v": {"type": "out", "amt": 500, "cat": "food", "note": "SECRET-NOTE", "date": TODAY}},
        "exp:e2": {"u": k, "v": {"type": "in", "amt": 2000, "cat": "salary", "date": "2026-10-01"}},
        "exp:e3": {"u": k, "v": {"type": "out", "amt": 999, "cat": "old", "date": "2026-09-30"}},
        "alm:a1": {"u": k, "v": {"label": "Wake", "time": "06:30", "days": [1, 2], "on": True}},
        "alm:a2": {"u": k, "v": {"label": "Off", "time": "07:00", "on": False}},
        "vp:k1": {"u": k, "v": cipher()},
        "vmeta": {"u": k, "v": {"salt": "c2FsdHNhbHRzYWx0c2E=", "ver": "dmVyaWZ5dmVyaWZ5", "iter": 310000}},
    }, {})
    out = build_summary(st=store, date=TODAY)
    assert out["projects"][0]["name"] == "Muziclly"
    assert out["projects"][0]["tasks_open"] == 1 and out["projects"][0]["next_milestone"] == "Beta"
    ck = out["checklists"][0]
    assert ck["done"] == 1 and ck["total"] == 2 and ck["left"] == ["Invoice"]
    assert out["shopping"] == {"open_count": 1, "items": ["Milk x2"]}
    cf = out["cashflow_this_month"]
    assert cf["income"] == 2000 and cf["spent"] == 500 and cf["net"] == 1500
    assert [a["label"] for a in out["alarms"]] == ["Wake"]
    blob = json.dumps(out)
    for leak in ("SECRET-DESC", "SECRET-NOTE", "vp:k1", "AAAAAAAAAAAAAAAA", "salt"):
        assert leak not in blob


def test_summary_survives_malformed_module_records(store, clock):
    store.merge({"prj:p1": {"u": ms(clock), "v": {"tasks": "nope", "milestones": [1, 2]}},
                 "exp:e1": {"u": ms(clock), "v": {"amt": "lots", "date": 5}},
                 "chk:c1": {"u": ms(clock), "v": {"items": None, "done": []}}}, {})
    assert build_summary(store, TODAY)["ok"] is True


# ---- family connect over REST ---------------------------------------------------------------------------------
def test_member_isolation(api, store, clock):
    base, _ = api
    s, d = call(f"{base}/family/members", "POST", {"name": "Priya", "role": "Wife"}, TOKEN)
    assert s == 200 and d["id"].startswith("m")
    mt = d["token"]
    store.merge({"note:n1": {"u": ms(clock), "v": {"title": "personal"}}}, {})
    # a member token never opens the owner's personal data, sync, clipboard or admin
    assert call(f"{base}/state", secret=mt)[0] == 401
    assert call(f"{base}/sync", "POST", {"records": {}, "tombstones": {}}, mt)[0] == 401
    assert call(f"{base}/clip", secret=mt)[0] == 401
    assert call(f"{base}/clip", "POST", {"text": "x"}, mt)[0] == 403
    assert call(f"{base}/clip/clear", "POST", {}, mt)[0] == 403
    assert call(f"{base}/tool/get_almanac_state", "POST", {}, mt)[0] == 401
    assert call(f"{base}/family/members", "POST", {"name": "Evil", "role": "Son"}, mt)[0] == 403
    assert call(f"{base}/family/members/revoke", "POST", {"id": "owner"}, mt)[0] == 403
    # but the family space works
    s, d = call(f"{base}/family/state", secret=mt)
    assert s == 200 and d["me"]["name"] == "Priya" and d["me"]["role"] == "member"
    assert call(f"{base}/family/state", secret="wrong")[0] == 401
    # the tool token is not an owner token either
    assert call(f"{base}/family/state", secret=TOOL)[0] == 401


def test_family_shared_records_and_member_cannot_write_personal_keys(api, clock):
    base, _ = api
    _, d = call(f"{base}/family/members", "POST", {"name": "Aarav", "role": "Son"}, TOKEN)
    mt = d["token"]
    rec = {"fshop:f1": {"u": ms(clock), "v": {"name": "Bread"}}}
    s, d = call(f"{base}/family/sync", "POST", {"records": rec, "tombstones": {}}, mt)
    assert s == 200 and d["applied"] == 1
    s, d = call(f"{base}/family/state", secret=TOKEN)
    assert d["records"]["fshop:f1"]["v"]["name"] == "Bread"
    bad = {"shop:x": {"u": ms(clock), "v": {"name": "personal"}}}
    assert call(f"{base}/family/sync", "POST", {"records": bad, "tombstones": {}}, mt)[0] == 400
    ev = {"fev:e1": {"u": ms(clock, 1), "v": {"title": "Dinner", "date": TODAY}}}
    assert call(f"{base}/family/sync", "POST", {"records": ev, "tombstones": {}}, TOKEN)[0] == 200
    s, d = call(f"{base}/family/state?since=0", secret=mt)
    assert set(d["records"]) == {"fshop:f1", "fev:e1"}


def test_revoke_blocks_member(api):
    base, _ = api
    _, d = call(f"{base}/family/members", "POST", {"name": "Priya", "role": "Wife"}, TOKEN)
    mt, mid = d["token"], d["id"]
    assert call(f"{base}/family/state", secret=mt)[0] == 200
    assert call(f"{base}/family/members/revoke", "POST", {"id": mid}, TOKEN)[0] == 200
    assert call(f"{base}/family/state", secret=mt)[0] == 401


def test_presence_and_member_limits(api):
    base, _ = api
    _, d = call(f"{base}/family/members", "POST", {"name": "Priya", "role": "Wife"}, TOKEN)
    mt = d["token"]
    assert call(f"{base}/family/presence", "POST", {"status": "home", "note": "cooking"}, mt)[0] == 200
    assert call(f"{base}/family/presence", "POST", {"status": "teleporting"}, mt)[0] == 400
    s, d = call(f"{base}/family/state", secret=TOKEN)
    me = [m for m in d["members"] if m["name"] == "Priya"][0]
    assert me["status"] == "home" and me["note"] == "cooking"
    assert call(f"{base}/family/members", "POST", {"name": "", "role": "Wife"}, TOKEN)[0] == 400
    assert call(f"{base}/family/members", "POST", {"name": "X", "role": "Wi<fe>"}, TOKEN)[0] == 400


def test_token_stored_hashed(hub):
    mid, tok = hub.add_member("Priya", "Wife")
    rows = hub._db.execute("SELECT token_hash FROM members").fetchall()
    assert tok not in rows[0][0] and len(rows[0][0]) == 64
    assert hub.auth_member(tok)["id"] == mid and hub.auth_member(tok + "x") is None


# ---- clipboard over REST --------------------------------------------------------------------------------------
def test_clip_rest_ring_ttl_and_limits(api, hub, clock):
    base, _ = api
    assert call(f"{base}/clip")[0] == 401
    for i in range(35):
        assert call(f"{base}/clip", "POST", {"text": f"item {i}", "device": "pc"}, TOKEN)[0] == 200
    s, d = call(f"{base}/clip", secret=TOKEN)
    assert len(d["items"]) == 30 and d["items"][0]["text"] == "item 34"
    call(f"{base}/clip", "POST", {"text": "item 34"}, TOKEN)  # consecutive duplicate collapses
    assert len(call(f"{base}/clip", secret=TOKEN)[1]["items"]) == 30
    assert call(f"{base}/clip", "POST", {"text": ""}, TOKEN)[0] == 400
    assert call(f"{base}/clip", "POST", {"text": "x" * 70000}, TOKEN)[0] == 400
    clock.t += 25 * 3600
    assert call(f"{base}/clip", secret=TOKEN)[1]["items"] == []
    call(f"{base}/clip", "POST", {"text": "a"}, TOKEN)
    assert call(f"{base}/clip/clear", "POST", {}, TOKEN)[0] == 200
    assert call(f"{base}/clip", secret=TOKEN)[1]["items"] == []


def test_clip_never_touches_disk_or_state(api, hub, store):
    base, _ = api
    call(f"{base}/clip", "POST", {"text": "super-secret-password"}, TOKEN)
    assert "super-secret-password" not in json.dumps(call(f"{base}/state", secret=TOKEN)[1])
    assert "super-secret-password" not in json.dumps(build_summary(store, TODAY))
    dump = "\n".join(hub._db.iterdump()) + "\n".join(hub.family._db.iterdump())
    assert "super-secret-password" not in dump


# ---- WebSocket ------------------------------------------------------------------------------------------------
class WS:
    def __init__(self, port, path="/api/almanac/ws"):
        self.s = socket.create_connection(("127.0.0.1", port), timeout=5)
        key = base64.b64encode(os.urandom(16)).decode()
        self.s.sendall((f"GET {path} HTTP/1.1\r\nHost: x\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                        f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = self.s.recv(4096)
            if not chunk:
                break
            buf += chunk
        head, _, rest = buf.partition(b"\r\n\r\n")
        self.status = int(head.split()[1])
        self.accept_ok = ws.accept_key(key).encode() in head
        self.buf = bytearray(rest)

    def send(self, obj, op=ws.OP_TEXT, raw=None):
        payload = raw if raw is not None else json.dumps(obj).encode()
        mask = os.urandom(4)
        n = len(payload)
        head = bytes([0x80 | op])
        head += bytes([0x80 | n]) if n < 126 else bytes([0x80 | 126]) + struct.pack(">H", n)
        self.s.sendall(head + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))

    def send_unmasked(self, payload=b"hi"):
        self.s.sendall(bytes([0x81, len(payload)]) + payload)

    def recv(self, timeout=3):
        self.s.settimeout(timeout)
        while True:
            # server frames are unmasked: parse manually
            if len(self.buf) >= 2:
                n, pos = self.buf[1] & 0x7F, 2
                if n == 126 and len(self.buf) >= 4:
                    n, pos = struct.unpack(">H", bytes(self.buf[2:4]))[0], 4
                if (n < 126 or pos == 4) and len(self.buf) >= pos + n:
                    op = self.buf[0] & 0x0F
                    data = bytes(self.buf[pos:pos + n])
                    del self.buf[:pos + n]
                    if op == ws.OP_CLOSE:
                        return {"closed": struct.unpack(">H", data[:2])[0]}
                    if op == ws.OP_PING:
                        continue
                    return json.loads(data)
            chunk = self.s.recv(65536)
            if not chunk:
                return {"closed": None}
            self.buf += chunk

    def recv_type(self, *types, tries=15):
        for _ in range(tries):
            m = self.recv()
            if m.get("t") in types or "closed" in m:
                return m
        raise AssertionError(f"never saw {types}")

    def auth(self, token):
        self.send({"t": "auth", "token": token})
        return self.recv()

    def close(self):
        try:
            self.s.close()
        except OSError:
            pass


def test_ws_frame_codec_roundtrip():
    assert ws.accept_key("dGhlIHNhbXBsZSBub25jZQ==") == "s3pPLMBiTxaQ9kYGzzhZRbK+xOo="  # RFC 6455 section 1.3
    big = os.urandom(70000)
    f = ws.encode_frame(ws.OP_BIN, big)
    assert f[1] == 127 and f[10:] == big
    mask = b"\x01\x02\x03\x04"
    masked = bytes(b ^ mask[i % 4] for i, b in enumerate(b"hello"))
    buf = bytearray(bytes([0x81, 0x85]) + mask + masked)
    assert ws.decode_frame(buf) == (True, ws.OP_TEXT, b"hello") and not buf
    partial = bytearray(bytes([0x81, 0x85]) + mask + masked[:2])
    assert ws.decode_frame(partial) is None  # needs more bytes, nothing consumed
    with pytest.raises(ws.ProtocolError):
        ws.decode_frame(bytearray([0x81, 0x02, 0x68, 0x69]))  # unmasked client frame


def test_ws_requires_upgrade_and_auth(api):
    base, port = api
    assert call(f"{base}/ws")[0] == 400
    c = WS(port)
    assert c.status == 101 and c.accept_ok
    assert c.auth("nope") == {"closed": 4401}
    c.close()
    c = WS(port)  # first frame must be auth
    c.send({"t": "clip", "text": "sneak"})
    assert c.recv() == {"closed": 4401}
    c.close()
    c = WS(port)
    c.send_unmasked()
    assert c.recv()["closed"] == 1002
    c.close()


def test_ws_clipboard_between_two_owner_devices_and_member_excluded(api, hub):
    base, port = api
    _, d = call(f"{base}/family/members", "POST", {"name": "Priya", "role": "Wife"}, TOKEN)
    mt = d["token"]
    pc, phone, wife = WS(port), WS(port), WS(port)
    h1, h2, h3 = pc.auth(TOKEN), phone.auth(TOKEN), wife.auth(mt)
    assert h1["t"] == "hello" and h1["role"] == "owner" and "clips" in h1
    assert h3["role"] == "member" and "clips" not in h3
    pc.send({"t": "clip", "text": "https://example.com/a", "device": "PC"})
    ack = pc.recv_type("clip_ack")
    assert ack["t"] == "clip_ack" and ack["item"]["text"] == "https://example.com/a"
    got = phone.recv_type("clip")
    assert got["t"] == "clip" and got["item"]["text"] == "https://example.com/a" and got["item"]["device"] == "PC"
    # the member's socket only ever hears family/presence traffic, never the clipboard
    wife.s.settimeout(0.5)
    seen = []
    try:
        while True:
            seen.append(wife.recv(0.5))
    except (socket.timeout, TimeoutError):
        pass
    assert all(m.get("t") == "fam" for m in seen)
    # and a member's clip message is ignored
    wife.send({"t": "clip", "text": "member-clip"})
    time.sleep(0.3)
    assert all(c["text"] != "member-clip" for c in hub.clip_list())
    # a late joiner gets history in hello
    late = WS(port)
    assert late.auth(TOKEN)["clips"][0]["text"] == "https://example.com/a"
    for c in (pc, phone, wife, late):
        c.close()


def test_ws_family_push_and_revoke_drops_socket(api):
    base, port = api
    _, d = call(f"{base}/family/members", "POST", {"name": "Priya", "role": "Wife"}, TOKEN)
    mt, mid = d["token"], d["id"]
    owner, wife = WS(port), WS(port)
    owner.auth(TOKEN)
    wife.auth(mt)
    # drain presence chatter
    def next_fam(c, what):
        for _ in range(10):
            m = c.recv()
            if m.get("t") == "fam" and m.get("what") == what:
                return m
        raise AssertionError("no push")
    wife.send({"t": "presence", "status": "home", "note": "back"})
    assert next_fam(owner, "presence")
    call(f"{base}/family/sync", "POST", {"records": {"fshop:f1": {"u": int(time.time() * 1000), "v": {"name": "Rice"}}},
                                         "tombstones": {}}, TOKEN)
    assert next_fam(wife, "data")["rev"] >= 1
    call(f"{base}/family/members/revoke", "POST", {"id": mid}, TOKEN)
    closed = None
    for _ in range(10):
        m = wife.recv()
        if "closed" in m:
            closed = m["closed"]
            break
    assert closed in (4403, None)
    owner.close()
    wife.close()
