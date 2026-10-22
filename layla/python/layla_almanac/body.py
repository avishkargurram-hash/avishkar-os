"""Layla's body, as seen from the Almanac server: the GR robot and the AV sensor box.

Both live on the VM-local MQTT broker. This module owns the robot's safety rules so that every caller -- the
Almanac joystick (WebSocket), the HTTP API and Layla's voice plugin (which calls the HTTP API) -- drives the robot
exactly the same way.

Directions here are always PHYSICAL ("forward" = the way the robot's face points). The current GR wiring makes
firmware v1's FORWARD drive the robot backwards, so v1 gets the forward/backward pair swapped automatically; a
firmware that publishes `<robot>/fw` >= 2 has that fixed at the source. The owner can override either axis.

Safety layers (each one alone is enough to stop the robot):
  1. every MQTT command carries a short duration_ms -- the firmware stops by itself when it runs out;
  2. a dead-man here: a held (joystick) drive that is not refreshed within DEADMAN_S is stopped explicitly;
  3. timed (voice) moves are capped at TIMED_MAX_S and cancelled by any new command or stop;
  4. physical-forward is refused when a fresh distance reading says something is closer than FRONT_STOP_CM.

The AV box: ESPHome publishes `<esp>/sensor|binary_sensor|switch/<id>/state`. Learned IR codes stay owned by
Layla's brain plugin (layla_esp); this module asks it to send/learn/forget over `<esp>/ir/request` and reads
the button catalogue it retains on `<esp>/ir/catalog`.
"""

from __future__ import annotations

import json
import re
import secrets
import threading
import time
from typing import Any, Callable, Dict, List, Optional

ROBOT = "tryvanta/robot/001"
ESP = "layla/esp1"
HOME = "layla/home"

BURST_MS = 600          # each command keeps the motors running this long unless refreshed
RESEND_S = 0.25         # a held direction is re-published at most this often
DEADMAN_S = 0.6         # a held drive not refreshed within this is stopped
TIMED_MAX_S = 5.0       # longest single timed (voice) move
FRONT_STOP_CM = 20.0
DIST_FRESH_S = 1.5
NOTIFY_MIN_S = 0.15     # coalesce telemetry pushes
IR_WAIT_S = 4.0
IR_LEARN_WAIT_S = 30.0
HOME_WAIT_S = 20.0
TV_WAIT_S = 40.0          # the brain waits up to 35 s for the laptop TV bridge

ACTIONS = ("forward", "backward", "left", "right")
_FLIP_FB = {"forward": "backward", "backward": "forward", "left": "left", "right": "right"}
_FLIP_LR = {"left": "right", "right": "left", "forward": "forward", "backward": "backward"}
_RAW_TO_PHYS = {"FORWARD": "forward", "REVERSE": "backward", "LEFT": "left", "RIGHT": "right", "STOPPED": "stopped"}
_ID_OK = re.compile(r"^[a-z0-9_]{1,48}$")
_NAME_OK = re.compile(r"^[a-z0-9 ._-]{1,40}$")
HOME_ACTIONS = {
    "fan": {"on", "off", "toggle", "speed"},
    "plug": {"on", "off", "toggle"},
    "tv": {"power_on", "power_off", "power", "mute", "volume_up", "volume_down", "play", "pause", "play_pause",
           "next", "previous", "home", "back"},
}
LIGHTS = ("bulb", "tube", "ceiling1", "ceiling2", "general")


class BodyError(ValueError):
    pass


class Body:
    def __init__(self, publish: Callable[[str, Any, bool], bool], cfg_get: Callable[[str], str] = lambda k: "",
                 cfg_set: Callable[[str, str], None] = lambda k, v: None,
                 on_change: Optional[Callable[[Dict[str, Any]], None]] = None, clock: Callable[[], float] = time.time,
                 start_threads: bool = True):
        self._pub, self._cfg_get, self._cfg_set, self._on_change, self._now = publish, cfg_get, cfg_set, on_change, clock
        self._lock = threading.RLock()
        self.link = False
        self.robot: Dict[str, Any] = {"online": None, "fw": 1, "raw_action": "STOPPED", "raw_speed": 0, "obstacle": None,
                                      "pir": None, "distance_cm": None, "distance_at": 0.0, "seen_at": 0.0}
        self.box: Dict[str, Any] = {"online": None, "seen_at": 0.0, "sensors": {}, "switches": {}, "ir": [],
                                    "ir_catalog_at": 0.0, "last_ir": None}
        self._hold: Optional[Dict[str, Any]] = None     # {"action", "speed", "last_cmd", "last_pub"}
        self._timed_gen = 0
        self._ir_wait: Dict[str, Dict[str, Any]] = {}
        self.home: Dict[str, Any] = {"state": None, "at": 0.0, "last": None}
        self.presence = None          # set by __main__ (presence.Presence); kept out of the body lock on purpose
        self._notify_at = 0.0
        self._notify_pending = False
        cfg = {}
        try:
            cfg = json.loads(self._cfg_get("robot_cfg") or "{}")
        except Exception:
            pass
        self.cfg = {"invert_fb": cfg.get("invert_fb"), "invert_lr": bool(cfg.get("invert_lr", False))}
        if start_threads:
            threading.Thread(target=self._deadman_loop, name="robot-deadman", daemon=True).start()

    # ---- MQTT side ------------------------------------------------------------------------------------------
    def set_link(self, up: bool) -> None:
        with self._lock:
            self.link = up
            if not up:
                self._hold = None
        self._changed()

    def handle(self, topic: str, payload: bytes, retained: bool = False) -> None:
        val = payload.decode("utf-8", "replace").strip()
        now = self._now()
        if topic.startswith(ROBOT + "/"):
            self._robot_msg(topic[len(ROBOT) + 1:], val, now)
        elif topic.startswith(ESP + "/"):
            self._box_msg(topic[len(ESP) + 1:], val, now)
        elif topic.startswith(HOME + "/"):
            self._home_msg(topic[len(HOME) + 1:], val, now)

    def _robot_msg(self, t: str, val: str, now: float) -> None:
        r = self.robot
        with self._lock:
            if t == "status":
                r["online"] = val.lower() == "online"
            elif t == "fw":
                try:
                    r["fw"] = int(float(val))
                except ValueError:
                    return
            elif t == "motor/state":
                try:
                    d = json.loads(val)
                    r["raw_action"], r["raw_speed"] = str(d.get("action", "STOPPED")).upper(), int(d.get("speed", 0))
                except Exception:
                    return
            elif t == "obstacle/state":
                r["obstacle"] = val == "blocked"
            elif t == "pir/state":
                r["pir"] = val == "motion"
            elif t == "distance/state":
                try:
                    cm = float(val)
                except ValueError:
                    return
                r["distance_cm"], r["distance_at"] = (cm if 0 < cm < 600 else None), now
            elif t == "motor/set":
                return          # our own (or another controller's) commands: not telemetry
            else:
                return
            if t != "status":
                r["seen_at"] = now
        self._changed()

    def _box_msg(self, t: str, val: str, now: float) -> None:
        b = self.box
        with self._lock:
            if t == "status":
                b["online"] = val.lower() == "online"
            elif t == "ir/catalog":
                try:
                    names = json.loads(val)
                    b["ir"] = sorted(str(n) for n in names if isinstance(n, str))[:64]
                    b["ir_catalog_at"] = now
                except Exception:
                    return
            elif t == "ir/result":
                try:
                    d = json.loads(val)
                except Exception:
                    return
                w = self._ir_wait.get(str(d.get("id", "")))
                if w is not None:
                    w["result"] = d
                    w["ev"].set()
                b["last_ir"] = {"op": d.get("op"), "name": d.get("name"), "ok": bool(d.get("ok")),
                                "msg": str(d.get("msg", ""))[:200], "at": now}
            else:
                parts = t.split("/")
                if len(parts) != 3 or parts[2] != "state" or not _ID_OK.match(parts[1]):
                    return
                kind, sid = parts[0], parts[1]
                if kind == "sensor":
                    try:
                        v = float(val)
                    except ValueError:
                        return
                    b["sensors"][sid] = {"v": None if v != v else round(v, 2), "at": now}
                elif kind == "binary_sensor":
                    b["sensors"][sid] = {"v": val.upper() == "ON", "at": now}
                elif kind == "switch":
                    b["switches"][sid] = {"on": val.upper() == "ON", "at": now}
                else:
                    return
                b["seen_at"] = now
        self._changed()

    def _home_msg(self, t: str, val: str, now: float) -> None:
        try:
            d = json.loads(val)
        except Exception:
            return
        if not isinstance(d, dict):
            return
        with self._lock:
            if t == "state":
                self.home["state"], self.home["at"] = d, now
            elif t == "result":
                w = self._ir_wait.get(str(d.get("id", "")))
                if w is not None:
                    w["result"] = d
                    w["ev"].set()
                return
            else:
                return
        self._changed()

    # ---- robot control --------------------------------------------------------------------------------------
    def _invert_fb(self) -> bool:
        v = self.cfg.get("invert_fb")
        return bool(v) if v is not None else int(self.robot.get("fw") or 1) < 2

    def _to_fw(self, phys: str) -> str:
        a = _FLIP_FB[phys] if self._invert_fb() else phys
        return _FLIP_LR[a] if self.cfg.get("invert_lr") else a

    def _front_blocked(self) -> bool:
        r = self.robot
        d = r.get("distance_cm")
        return d is not None and self._now() - r.get("distance_at", 0) <= DIST_FRESH_S and d < FRONT_STOP_CM

    def _send(self, phys: str, speed: int, ms: int) -> bool:
        fw = self._to_fw(phys)
        msg = json.dumps({"action": fw, "speed": int(speed), "duration_ms": int(ms)}, separators=(",", ":"))
        return bool(self._pub(ROBOT + "/motor/set", msg, False))

    @staticmethod
    def _check(action: str, speed: Any) -> int:
        if action not in ACTIONS:
            raise BodyError("action must be one of " + ", ".join(ACTIONS))
        try:
            s = int(speed)
        except (TypeError, ValueError):
            raise BodyError("speed must be 0..255")
        if not 0 <= s <= 255:
            raise BodyError("speed must be 0..255")
        return s

    def drive(self, action: str, speed: Any = 200, seconds: Any = None) -> Dict[str, Any]:
        """Held drive (seconds=None: keep calling to keep moving) or a timed move (seconds given, voice)."""
        action = str(action or "").strip().lower()
        s = self._check(action, speed)
        if not self.link:
            raise BodyError("robot link is down (broker unreachable)")
        if self.robot.get("online") is False:
            raise BodyError("the robot is offline (switched off or not on WiFi)")
        if action == "forward" and self._front_blocked():
            self.stop()
            return {"ok": False, "blocked": True, "msg": f"something is closer than {FRONT_STOP_CM:.0f} cm in front"}
        if seconds is None:
            now = self._now()
            with self._lock:
                self._timed_gen += 1                     # a joystick takes over from any timed move
                h = self._hold
                fresh = h is None or h["action"] != action or abs(h["speed"] - s) >= 24 or now - h["last_pub"] >= RESEND_S
                if h is None or h["action"] != action:
                    h = self._hold = {"action": action, "speed": s, "last_cmd": now, "last_pub": 0.0}
                h["last_cmd"], h["speed"] = now, s
                if fresh:
                    h["last_pub"] = now
            ok = self._send(action, s, BURST_MS) if fresh else True
            return {"ok": ok, "action": action, "speed": s}
        try:
            secs = float(seconds)
        except (TypeError, ValueError):
            raise BodyError("seconds must be a number")
        secs = max(0.2, min(TIMED_MAX_S, secs))
        with self._lock:
            self._hold = None
            self._timed_gen += 1
            gen = self._timed_gen
        threading.Thread(target=self._timed, args=(gen, action, s, secs), name="robot-timed", daemon=True).start()
        return {"ok": True, "action": action, "speed": s, "seconds": secs}

    def _timed(self, gen: int, action: str, speed: int, secs: float) -> None:
        end = self._now() + secs
        while True:
            with self._lock:
                if gen != self._timed_gen:
                    return
            left = end - self._now()
            if left <= 0:
                break
            if action == "forward" and self._front_blocked():
                break
            self._send(action, speed, int(min(BURST_MS, left * 1000) + 50))
            time.sleep(min(0.35, max(0.05, left)))
        with self._lock:
            if gen != self._timed_gen:
                return
        self._publish_stop()

    def stop(self) -> Dict[str, Any]:
        with self._lock:
            self._hold = None
            self._timed_gen += 1
        ok = self._publish_stop()
        return {"ok": ok}

    def _publish_stop(self) -> bool:
        msg = json.dumps({"action": "stop", "speed": 0, "duration_ms": 1}, separators=(",", ":"))
        a = self._pub(ROBOT + "/motor/set", msg, False)
        return bool(a)

    def _deadman_loop(self) -> None:
        while True:
            time.sleep(0.1)
            try:
                self.deadman_tick()
            except Exception:
                pass

    def deadman_tick(self) -> bool:
        with self._lock:
            h = self._hold
            if h is None:
                return False
            expired = self._now() - h["last_cmd"] > DEADMAN_S
            blocked = h["action"] == "forward" and self._front_blocked()
            if not (expired or blocked):
                return False
            self._hold = None
        self._publish_stop()
        return True

    def configure(self, d: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            if "invert_fb" in d:
                v = d["invert_fb"]
                if v is not None and not isinstance(v, bool):
                    raise BodyError("invert_fb must be true, false or null (auto)")
                self.cfg["invert_fb"] = v
            if "invert_lr" in d:
                if not isinstance(d["invert_lr"], bool):
                    raise BodyError("invert_lr must be true or false")
                self.cfg["invert_lr"] = d["invert_lr"]
            self._cfg_set("robot_cfg", json.dumps(self.cfg))
        self._changed()
        return self.state()["robot"]["config"]

    # ---- AV box control -------------------------------------------------------------------------------------
    def ir(self, op: str, name: str, wait: bool = True) -> Dict[str, Any]:
        op = str(op or "").lower()
        name = re.sub(r"\s+", " ", str(name or "").strip().lower())
        if op not in ("send", "learn", "forget"):
            raise BodyError("op must be send, learn or forget")
        if not _NAME_OK.match(name):
            raise BodyError("button name: 1-40 letters, digits, spaces, . _ -")
        if not self.link:
            raise BodyError("AV box link is down (broker unreachable)")
        rid = secrets.token_hex(6)
        w = {"ev": threading.Event(), "result": None}
        with self._lock:
            self._ir_wait[rid] = w
        try:
            self._pub(ESP + "/ir/request", json.dumps({"id": rid, "op": op, "name": name}), False)
            if not wait:
                return {"ok": True, "pending": True, "id": rid}
            w["ev"].wait(IR_LEARN_WAIT_S if op == "learn" else IR_WAIT_S)
            r = w["result"]
            if r is None:
                return {"ok": False, "msg": "Layla's AV box service did not answer (is the brain running?)"}
            return {"ok": bool(r.get("ok")), "msg": str(r.get("msg", ""))[:300]}
        finally:
            with self._lock:
                self._ir_wait.pop(rid, None)

    def _ask(self, topic: str, req: Dict[str, Any], wait_s: float) -> Dict[str, Any]:
        rid = secrets.token_hex(6)
        w = {"ev": threading.Event(), "result": None}
        with self._lock:
            self._ir_wait[rid] = w
        try:
            self._pub(topic, json.dumps(dict(req, id=rid)), False)
            w["ev"].wait(wait_s)
            return w["result"] or {"ok": False, "msg": "Layla's home service did not answer in time (is the brain running?)"}
        finally:
            with self._lock:
                self._ir_wait.pop(rid, None)

    def home_control(self, device: str, action: str, value: Any = None) -> Dict[str, Any]:
        device, action = str(device or "").lower(), str(action or "").lower()
        if device.startswith("light:"):
            if device[6:] not in LIGHTS or action not in ("on", "off", "toggle", "dim"):
                raise BodyError("unknown light or action")
        elif action not in HOME_ACTIONS.get(device, ()):
            raise BodyError("unknown device or action")
        if action in ("speed", "dim"):
            try:
                value = int(value)
            except (TypeError, ValueError):
                raise BodyError("value must be a number")
        if not self.link:
            raise BodyError("home link is down (broker unreachable)")
        r = self._ask(HOME + "/request", {"op": "set", "device": device, "action": action, "value": value},
                      TV_WAIT_S if device == "tv" else HOME_WAIT_S)
        out = {"ok": bool(r.get("ok")), "msg": str(r.get("msg", ""))[:300]}
        with self._lock:
            self.home["last"] = dict(out, device=device, action=action, at=self._now())
        self._changed()
        return out

    def home_refresh(self, force: bool = False) -> Dict[str, Any]:
        if not self.link:
            raise BodyError("home link is down (broker unreachable)")
        r = self._ask(HOME + "/request", {"op": "get", "force": bool(force)}, HOME_WAIT_S)
        return {"ok": bool(r.get("ok")), "msg": str(r.get("msg", ""))[:200]}

    def display(self, text: str) -> Dict[str, Any]:
        t = "".join(ch for ch in str(text or "") if ch.isprintable())[:40].strip()
        if not t:
            raise BodyError("no text")
        return {"ok": bool(self._pub(ESP + "/display/text", t, False))}

    def switch(self, sid: str, on: Any) -> Dict[str, Any]:
        sid = str(sid or "")
        if not _ID_OK.match(sid) or sid not in self.box["switches"]:
            raise BodyError("unknown switch")
        if not isinstance(on, bool):
            raise BodyError("on must be true or false")
        return {"ok": bool(self._pub(ESP + "/switch/" + sid + "/command", "ON" if on else "OFF", False))}

    # ---- state ----------------------------------------------------------------------------------------------
    def state(self) -> Dict[str, Any]:
        s = self._state()
        pr = self.presence
        if pr is not None:           # outside self._lock: Presence takes its own lock and then ours
            s["presence"] = pr.status()
        return s

    def _state(self) -> Dict[str, Any]:
        now = self._now()
        with self._lock:
            r, b = self.robot, self.box
            raw = r["raw_action"]
            phys = _RAW_TO_PHYS.get(raw, raw.lower())
            if phys in ("forward", "backward") and self._invert_fb():
                phys = _FLIP_FB[phys]
            if phys in ("left", "right") and self.cfg.get("invert_lr"):
                phys = _FLIP_LR[phys]
            dist = r["distance_cm"] if now - r["distance_at"] <= DIST_FRESH_S * 2 else None
            sensors = {k: {"v": v["v"], "age_s": round(now - v["at"], 1)} for k, v in b["sensors"].items()}
            switches = {k: {"on": v["on"], "age_s": round(now - v["at"], 1)} for k, v in b["switches"].items()}
            return {
                "link": self.link,
                "robot": {"online": r["online"], "fw": r["fw"], "motion": phys, "speed": r["raw_speed"],
                          "distance_cm": dist, "front_blocked": self._front_blocked(),
                          "ir_obstacle": r["obstacle"], "pir": r["pir"],
                          "holding": self._hold["action"] if self._hold else None,
                          "config": {"invert_fb": self.cfg.get("invert_fb"), "invert_lr": bool(self.cfg.get("invert_lr")),
                                     "invert_fb_effective": self._invert_fb()}},
                "avbox": {"online": b["online"], "seen_s": round(now - b["seen_at"], 1) if b["seen_at"] else None,
                          "sensors": sensors, "switches": switches, "ir_buttons": list(b["ir"]),
                          "last_ir": dict(b["last_ir"]) if b["last_ir"] else None},
                "home": {"state": self.home["state"], "age_s": round(now - self.home["at"], 1) if self.home["at"] else None,
                         "last": dict(self.home["last"]) if self.home["last"] else None},
            }

    def _changed(self) -> None:
        if self._on_change is None:
            return
        now = self._now()
        with self._lock:
            if self._notify_pending:
                return
            wait = NOTIFY_MIN_S - (now - self._notify_at)
            if wait > 0:
                self._notify_pending = True
                threading.Timer(wait, self._flush).start()
                return
            self._notify_at = now
        self._emit()

    def _flush(self) -> None:
        with self._lock:
            self._notify_pending = False
            self._notify_at = self._now()
        self._emit()

    def _emit(self) -> None:
        try:
            self._on_change(self.state())
        except Exception:
            pass


def subscriptions() -> List[str]:
    return [ROBOT + "/#", ESP + "/#", HOME + "/state", HOME + "/result"]
