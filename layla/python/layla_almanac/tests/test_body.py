import json
import socket
import struct
import threading
import time
import urllib.error
import urllib.request

import pytest

from layla_almanac import body as B
from layla_almanac.body import Body, BodyError
from layla_almanac.hub import Hub
from layla_almanac.mqtt import MqttClient, topic_matches
from layla_almanac.server import serve
from layla_almanac.store import AlmanacStore

TOKEN = "a" * 32
TOOL = "b" * 32


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class Pub:
    def __init__(self):
        self.msgs = []

    def __call__(self, topic, payload, retain=False):
        self.msgs.append((topic, payload if isinstance(payload, str) else payload.decode()))
        return True

    def motor(self):
        return [json.loads(p) for t, p in self.msgs if t == B.ROBOT + "/motor/set"]


@pytest.fixture
def rig():
    clock, pub, cfg = Clock(), Pub(), {}
    b = Body(pub, cfg.get, cfg.__setitem__, clock=clock, start_threads=False)
    b.set_link(True)
    return b, pub, clock, cfg


def feed(b, sub, val, root=B.ROBOT):
    b.handle(root + "/" + sub, val.encode())


# ---- directions ---------------------------------------------------------------------------------------------
def test_fw1_swaps_forward_and_backward(rig):
    b, pub, _, _ = rig
    b.drive("forward", 200)
    assert pub.motor()[-1] == {"action": "backward", "speed": 200, "duration_ms": B.BURST_MS}
    b.stop()
    b.drive("backward", 200)
    assert pub.motor()[-1]["action"] == "forward"
    b.drive("left", 200)
    assert pub.motor()[-1]["action"] == "left"


def test_fw2_is_not_swapped_and_override_wins(rig):
    b, pub, _, cfg = rig
    feed(b, "fw", "2")
    b.drive("forward", 180)
    assert pub.motor()[-1]["action"] == "forward"
    b.configure({"invert_fb": True, "invert_lr": True})
    b.stop()
    b.drive("forward", 180)
    b.stop()
    b.drive("left", 180)
    sent = [m["action"] for m in pub.motor() if m["action"] != "stop"]
    assert sent[-2:] == ["backward", "right"]
    assert json.loads(cfg["robot_cfg"]) == {"invert_fb": True, "invert_lr": True}


def test_telemetry_is_reported_in_physical_terms(rig):
    b, _, _, _ = rig
    feed(b, "motor/state", '{"action":"REVERSE","speed":200}')
    assert b.state()["robot"]["motion"] == "forward"      # fw1: firmware REVERSE drives it forwards


# ---- safety -------------------------------------------------------------------------------------------------
def test_held_drive_is_throttled_then_deadman_stops(rig):
    b, pub, clock, _ = rig
    b.drive("left", 200)
    clock.t += 0.1
    b.drive("left", 200)              # refresh inside RESEND_S: not re-published
    assert len(pub.motor()) == 1
    clock.t += B.RESEND_S
    b.drive("left", 200)
    assert len(pub.motor()) == 2
    assert b.deadman_tick() is False
    clock.t += B.DEADMAN_S + 0.05
    assert b.deadman_tick() is True
    assert pub.motor()[-1]["action"] == "stop"
    assert b.deadman_tick() is False   # only once


def test_front_obstacle_refuses_physical_forward_only(rig):
    b, pub, clock, _ = rig
    feed(b, "distance/state", "12.5")
    r = b.drive("forward", 200)
    assert r["ok"] is False and r["blocked"] is True
    assert pub.motor()[-1]["action"] == "stop"
    assert b.drive("backward", 200)["ok"] is True
    clock.t += B.DIST_FRESH_S + 0.1     # stale reading no longer blocks
    assert b.drive("forward", 200)["ok"] is True


def test_held_forward_stops_when_obstacle_appears(rig):
    b, pub, _, _ = rig
    b.drive("forward", 200)
    feed(b, "distance/state", "10")
    assert b.deadman_tick() is True
    assert pub.motor()[-1]["action"] == "stop"


def test_timed_move_runs_and_ends_with_stop():
    pub = Pub()
    b = Body(pub, start_threads=False)
    b.set_link(True)
    r = b.drive("right", 150, seconds=0.5)
    assert r["seconds"] == 0.5
    time.sleep(0.9)
    acts = [m["action"] for m in pub.motor()]
    assert acts[0] == "right" and acts[-1] == "stop"
    assert all(m["duration_ms"] <= B.BURST_MS + 50 for m in pub.motor())


def test_timed_move_is_capped_and_cancelled_by_stop():
    pub = Pub()
    b = Body(pub, start_threads=False)
    b.set_link(True)
    assert b.drive("left", 150, seconds=99)["seconds"] == B.TIMED_MAX_S
    time.sleep(0.2)
    b.stop()
    n = len(pub.motor())
    time.sleep(0.6)
    assert len(pub.motor()) == n          # the timed thread stopped publishing


@pytest.mark.parametrize("action,speed", [("jump", 100), ("forward", 300), ("forward", -1), ("forward", "x"), ("", 1)])
def test_bad_commands_rejected(rig, action, speed):
    b, pub, _, _ = rig
    with pytest.raises(BodyError):
        b.drive(action, speed)
    assert pub.motor() == []


def test_no_link_no_drive(rig):
    b, _, _, _ = rig
    b.set_link(False)
    with pytest.raises(BodyError):
        b.drive("left", 100)


def test_offline_robot_refused_but_stop_always_allowed(rig):
    b, pub, _, _ = rig
    feed(b, "status", "offline")
    with pytest.raises(BodyError, match="offline"):
        b.drive("left", 100)
    assert b.stop()["ok"] and pub.motor()[-1]["action"] == "stop"
    feed(b, "status", "online")
    assert b.drive("left", 100)["ok"]


# ---- AV box -------------------------------------------------------------------------------------------------
def test_box_sensors_switches_and_catalog(rig):
    b, pub, _, _ = rig
    feed(b, "sensor/room_temperature/state", "27.43", B.ESP)
    feed(b, "sensor/room_humidity/state", "nan", B.ESP)
    feed(b, "binary_sensor/pir_motion/state", "ON", B.ESP)
    feed(b, "switch/lamp/state", "OFF", B.ESP)
    feed(b, "ir/catalog", '["tv power", "ac on", 5]', B.ESP)
    feed(b, "ir/request", '{"op":"send"}', B.ESP)          # our own echo is ignored
    s = b.state()["avbox"]
    assert s["sensors"]["room_temperature"]["v"] == 27.43
    assert s["sensors"]["room_humidity"]["v"] is None
    assert s["sensors"]["pir_motion"]["v"] is True
    assert s["switches"]["lamp"]["on"] is False
    assert s["ir_buttons"] == ["ac on", "tv power"]
    assert b.switch("lamp", True)["ok"]
    assert pub.msgs[-1] == (B.ESP + "/switch/lamp/command", "ON")
    with pytest.raises(BodyError):
        b.switch("nope", True)


def test_ir_request_waits_for_brain_answer(rig):
    b, pub, _, _ = rig

    def brain():
        for _ in range(50):
            reqs = [json.loads(p) for t, p in pub.msgs if t == B.ESP + "/ir/request"]
            if reqs:
                r = reqs[-1]
                feed(b, "ir/result", json.dumps({"id": r["id"], "op": r["op"], "name": r["name"], "ok": True,
                                                 "msg": "sent"}), B.ESP)
                return
            time.sleep(0.02)

    threading.Thread(target=brain, daemon=True).start()
    assert b.ir("send", "  TV   Power ") == {"ok": True, "msg": "sent"}
    assert json.loads(pub.msgs[0][1])["name"] == "tv power"
    with pytest.raises(BodyError):
        b.ir("explode", "tv")


# ---- HTTP + auth --------------------------------------------------------------------------------------------
@pytest.fixture
def api(tmp_path):
    pub = Pub()
    hub = Hub(str(tmp_path / "fam.db"))
    body = Body(pub, hub._meta, hub._set_meta, start_threads=False)
    body.set_link(True)
    srv = serve(AlmanacStore(":memory:"), TOKEN, TOOL, port=0, hub=hub, body=body)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}/api/almanac", pub, hub
    srv.shutdown()
    srv.server_close()


def call(url, method="GET", body=None, tok=None):
    h = {"Content-Type": "application/json"}
    if tok:
        h["X-Layla-Secret"] = tok
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None, method=method,
                                 headers=h)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null")


def test_robot_api_owner_only(api):
    base, pub, hub = api
    _, member_tok = hub.add_member("Son", "Member")
    for tok in (None, TOOL, member_tok):
        assert call(base + "/robot/drive", "POST", {"action": "left"}, tok)[0] == 401
        assert call(base + "/body/state", tok=tok)[0] == 401
    assert pub.motor() == []
    code, r = call(base + "/robot/drive", "POST", {"action": "left", "speed": 120}, TOKEN)
    assert code == 200 and r["ok"]
    assert call(base + "/robot/drive", "POST", {"action": "fly"}, TOKEN)[0] == 400
    assert call(base + "/robot/stop", "POST", {}, TOKEN)[1]["ok"]
    code, r = call(base + "/robot/config", "POST", {"invert_fb": False}, TOKEN)
    assert code == 200 and r["config"]["invert_fb_effective"] is False
    code, s = call(base + "/body/state", tok=TOKEN)
    assert code == 200 and s["link"] is True and "robot" in s and "avbox" in s


# ---- the stdlib MQTT client against a tiny in-process broker -----------------------------------------------
def _rd(c, n):
    b = b""
    while len(b) < n:
        x = c.recv(n - len(b))
        if not x:
            raise OSError
        b += x
    return b


def _pkt(c):
    h = _rd(c, 1)[0]
    m, n = 1, 0
    while True:
        x = _rd(c, 1)[0]
        n += (x & 127) * m
        if not x & 128:
            break
        m *= 128
    return h >> 4, _rd(c, n) if n else b""


def test_mqtt_client_subscribes_receives_and_publishes():
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    got = {"subs": [], "pubs": []}

    def broker():
        c, _ = srv.accept()
        while True:
            try:
                t, p = _pkt(c)
            except OSError:
                return
            if t == 1:
                c.sendall(bytes([0x20, 2, 0, 0]))
            elif t == 8:
                tl = struct.unpack("!H", p[2:4])[0]
                got["subs"].append(p[4:4 + tl].decode())
                c.sendall(bytes([0x90, 3]) + p[:2] + b"\x00")
                topic = b"tryvanta/robot/001/status"
                c.sendall(bytes([0x31, 2 + len(topic) + 6]) + struct.pack("!H", len(topic)) + topic + b"online")
            elif t == 3:
                tl = struct.unpack("!H", p[:2])[0]
                got["pubs"].append((p[2:2 + tl].decode(), p[2 + tl:].decode()))
            elif t == 12:
                c.sendall(bytes([0xD0, 0]))

    threading.Thread(target=broker, daemon=True).start()
    seen, links = [], []
    cli = MqttClient("127.0.0.1", srv.getsockname()[1], "t", keepalive=4,
                     on_message=lambda t, p, r: seen.append((t, p.decode(), r)), on_link=links.append)
    cli.subscribe("tryvanta/robot/001/#")
    cli.start()
    for _ in range(100):
        if seen:
            break
        time.sleep(0.02)
    assert links[:1] == [True]
    assert got["subs"] == ["tryvanta/robot/001/#"]
    assert seen == [("tryvanta/robot/001/status", "online", True)]
    assert cli.publish("tryvanta/robot/001/motor/set", '{"action":"stop"}')
    for _ in range(100):
        if got["pubs"]:
            break
        time.sleep(0.02)
    assert got["pubs"] == [("tryvanta/robot/001/motor/set", '{"action":"stop"}')]
    cli.stop()
    srv.close()


def test_topic_matching():
    assert topic_matches("a/#", "a/b/c") and topic_matches("a/+/c", "a/b/c")
    assert not topic_matches("a/+/c", "a/b/d") and not topic_matches("a/b", "a/b/c")


# ---- home (fan / plug / lights / TV through the brain) ------------------------------------------------------
def _answer(b, pub, ok=True, msg="done"):
    def run():
        for _ in range(100):
            reqs = [json.loads(p) for t, p in pub.msgs if t == B.HOME + "/request"]
            if reqs:
                feed(b, "result", json.dumps({"id": reqs[-1]["id"], "ok": ok, "msg": msg}), B.HOME)
                return
            time.sleep(0.02)
    threading.Thread(target=run, daemon=True).start()


def test_home_control_validates_and_relays(rig):
    b, pub, _, _ = rig
    for dev, act in (("oven", "on"), ("fan", "explode"), ("light:garage", "on"), ("tv", "format")):
        with pytest.raises(BodyError):
            b.home_control(dev, act)
    with pytest.raises(BodyError):
        b.home_control("fan", "speed", "fast")
    assert pub.msgs == []
    _answer(b, pub, msg="Fan is now ON at speed 3")
    assert b.home_control("fan", "speed", "3") == {"ok": True, "msg": "Fan is now ON at speed 3"}
    req = json.loads(pub.msgs[-1][1])
    assert (req["op"], req["device"], req["action"], req["value"]) == ("set", "fan", "speed", 3)
    _answer(b, pub, ok=False, msg="module offline")
    assert b.home_control("light:ceiling1", "dim", 40)["ok"] is False
    assert b.state()["home"]["last"]["device"] == "light:ceiling1"


def test_home_state_snapshot_flows_into_state(rig):
    b, _, _, _ = rig
    feed(b, "state", json.dumps({"fan": {"ok": True, "on": True, "speed": 2}, "plug": {"ok": True, "on": False}}), B.HOME)
    h = b.state()["home"]
    assert h["state"]["fan"]["speed"] == 2 and h["age_s"] == 0.0
