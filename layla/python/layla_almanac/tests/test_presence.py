import json
import threading
import time

import pytest

from layla_almanac import body as B
from layla_almanac.body import Body, BodyError
from layla_almanac.presence import Presence, SEEN_WITHIN_S


class Clock:
    def __init__(self):
        self.t = 100000.0

    def __call__(self):
        return self.t


class Rig:
    def __init__(self, **cfg0):
        self.clock, self.msgs, self.cfg = Clock(), [], {}
        self.cfg["presence_cfg"] = json.dumps(cfg0) if cfg0 else ""
        self.body = Body(lambda t, p, r=False: self.msgs.append((t, p)) or True, self.cfg.get, self.cfg.__setitem__,
                         clock=self.clock, start_threads=False)
        self.body.set_link(True)
        self.p = Presence(self.body, lambda t, p, r=False: self.msgs.append((t, p)) or True, self.cfg.get,
                          self.cfg.__setitem__, clock=self.clock, start_thread=False)
        self.box("status", "online")
        self.set(radar=True, pir=False)
        self.home(lights_on=("bulb", "ceiling1"), fan=True)
        self.answers = []
        self.stop = False
        threading.Thread(target=self._brain, daemon=True).start()

    def box(self, sub, val):
        self.body.handle(B.ESP + "/" + sub, val.encode())

    def set(self, radar=None, pir=None):
        if radar is not None:
            self.box("binary_sensor/radar_presence/state", "ON" if radar else "OFF")
        if pir is not None:
            self.box("binary_sensor/pir_motion/state", "ON" if pir else "OFF")
        self.box("sensor/room_temperature/state", "29.0")       # keeps the box "fresh"

    def home(self, lights_on=(), fan=False):
        items = [{"key": "switch%d" % (i + 1), "role": r, "on": r in lights_on, "available": True, "dimmable": False}
                 for i, r in enumerate(B.LIGHTS)]
        self.body.handle(B.HOME + "/state", json.dumps({"fan": {"ok": True, "on": fan, "speed": 3},
                                                        "lights": {"ok": True, "items": items}}).encode())

    def _brain(self):                      # answers every home/request like the brain would
        seen = 0
        while not self.stop:
            reqs = [json.loads(p) for t, p in self.msgs if t == B.HOME + "/request"]
            while seen < len(reqs):
                r = reqs[seen]
                seen += 1
                if r.get("op") == "set":
                    self.answers.append((r["device"], r["action"]))
                self.body.handle(B.HOME + "/result", json.dumps({"id": r["id"], "ok": True, "msg": "ok"}).encode())
            time.sleep(0.01)

    def run(self, minutes):
        self.clock.t += minutes * 60
        self.set()                         # fresh box reading
        return self.p.tick()

    def settle(self):
        for _ in range(100):
            if not self.p._acting:
                break
            time.sleep(0.02)
        time.sleep(0.05)


@pytest.fixture
def rig():
    r = Rig()
    yield r
    r.stop = True


def go_empty(r, minutes_present=1):
    r.p.tick()
    r.set(radar=False, pir=False)
    r.p.tick()


def test_disabled_by_default_never_acts(rig):
    go_empty(rig)
    assert rig.run(60) is None and rig.answers == []


def test_switches_off_lights_and_fan_after_empty_minutes(rig):
    rig.p.configure({"enabled": True, "empty_min": 10})
    go_empty(rig)
    assert rig.run(9) is None
    assert rig.run(2) == "off"
    rig.settle()
    assert sorted(rig.answers) == [("fan", "off"), ("light:bulb", "off"), ("light:ceiling1", "off")]
    assert rig.p.status()["events"][-1]["done"]
    assert any(t == "layla/home/event" for t, _ in rig.msgs)


def test_only_once_per_absence_and_rearms_on_return(rig):
    rig.p.configure({"enabled": True, "empty_min": 5})
    go_empty(rig)
    rig.run(6); rig.settle()
    n = len(rig.answers)
    assert rig.run(30) is None and len(rig.answers) == n          # does not nag
    rig.set(radar=True)
    rig.p.tick()
    assert rig.p.armed is True


def test_pir_motion_alone_keeps_room_occupied(rig):
    rig.p.configure({"enabled": True, "empty_min": 5})
    rig.set(radar=False, pir=True)
    rig.p.tick()
    assert rig.run(30) is None and rig.answers == []


def test_stale_or_offline_box_never_acts(rig):
    rig.p.configure({"enabled": True, "empty_min": 5})
    go_empty(rig)
    rig.clock.t += 600                       # no fresh reading for 10 min
    assert rig.p.tick() is None
    rig.box("status", "offline")
    assert rig.run(30) is None and rig.answers == []


def test_never_seen_recently_means_blind_not_empty(rig):
    rig.p.configure({"enabled": True, "empty_min": 5})
    rig.set(radar=False, pir=False)          # radar has never seen anyone since start
    rig.p.tick()
    assert rig.run(20) is None and rig.answers == []
    rig2 = Rig()
    rig2.p.configure({"enabled": True, "empty_min": 5})
    go_empty(rig2)
    rig2.clock.t += SEEN_WITHIN_S + 10
    assert rig2.run(30) is None
    rig.stop = rig2.stop = True


def test_snooze_blocks_then_expires(rig):
    rig.p.configure({"enabled": True, "empty_min": 5})
    rig.p.snooze(30)
    go_empty(rig)
    assert rig.run(10) is None
    assert rig.run(25) == "off"
    rig.settle()


def test_only_touches_devices_that_are_on_and_selected(rig):
    rig.p.configure({"enabled": True, "empty_min": 5, "lights": ["bulb", "tube"], "fan": False})
    go_empty(rig)
    assert rig.run(6) == "off"
    rig.settle()
    assert rig.answers == [("light:bulb", "off")]


def test_restore_puts_back_exactly_what_it_turned_off(rig):
    rig.p.configure({"enabled": True, "empty_min": 5, "restore": True})
    go_empty(rig)
    rig.run(6); rig.settle()
    rig.answers.clear()
    rig.set(radar=True)
    assert rig.p.tick() == "restore"
    time.sleep(0.3)
    assert sorted(rig.answers) == [("fan", "on"), ("light:bulb", "on"), ("light:ceiling1", "on")]


def test_no_restore_by_default(rig):
    rig.p.configure({"enabled": True, "empty_min": 5})
    go_empty(rig)
    rig.run(6); rig.settle()
    rig.answers.clear()
    rig.set(radar=True)
    assert rig.p.tick() is None and rig.answers == []


def test_config_validation_and_persistence(rig):
    with pytest.raises(BodyError):
        rig.p.configure({"enabled": "yes"})
    with pytest.raises(BodyError):
        rig.p.configure({"lights": ["garage"]})
    st = rig.p.configure({"empty_min": 1})
    assert st["empty_min"] == 3                                # clamped
    rig.p.configure({"enabled": True, "empty_min": 20, "fan": False})
    p2 = Presence(rig.body, lambda *a, **k: True, rig.cfg.get, rig.cfg.__setitem__, clock=rig.clock, start_thread=False)
    assert p2.cfg["enabled"] and p2.cfg["empty_min"] == 20 and p2.cfg["fan"] is False


def test_status_is_in_body_state(rig):
    rig.body.presence = rig.p
    s = rig.body.state()
    assert s["presence"]["enabled"] is False and "state" in s["presence"]
