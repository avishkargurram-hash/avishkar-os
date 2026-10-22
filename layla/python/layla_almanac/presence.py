"""Presence automation: when the room has really been empty for a while, switch the lights and fan off; optionally put
back exactly what it switched off when the owner returns.

Safety rules (every one of them must hold before anything is switched off):
  * disabled by default -- the owner turns it on;
  * the AV box is online and reporting (fresh readings) and the LD2410C radar is part of those readings;
  * radar AND PIR both say "nobody" continuously for `empty_min` minutes (a sleeping person still shows on the radar);
  * the radar has actually seen the owner in the last SEEN_WITHIN_S (proof the sensor can see the room);
  * not snoozed;
  * fires once per absence: after it acts it is disarmed until the room is occupied again, so a light the owner
    switches on remotely is never switched off again behind their back.
Only devices that are currently ON are touched. Plug, TV and appliances are never touched.
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from .body import Body, BodyError, LIGHTS

TICK_S = 15.0
SEEN_WITHIN_S = 12 * 3600
FRESH_S = 120.0
HOME_STALE_S = 90.0
EMPTY_MIN_RANGE = (3, 180)
EVENTS_KEEP = 20
LIGHT_LABEL = {"bulb": "bulb", "tube": "tube light", "ceiling1": "ceiling light 1", "ceiling2": "ceiling light 2",
               "general": "general switch"}


class Presence:
    def __init__(self, body: Body, publish: Callable[[str, Any, bool], bool], cfg_get: Callable[[str], str],
                 cfg_set: Callable[[str, str], None], clock: Callable[[], float] = time.time,
                 start_thread: bool = True):
        self.body, self._pub, self._cfg_get, self._cfg_set, self._now = body, publish, cfg_get, cfg_set, clock
        self._lock = threading.RLock()
        raw: Dict[str, Any] = {}
        try:
            raw = json.loads(cfg_get("presence_cfg") or "{}")
        except Exception:
            pass
        self.cfg = {
            "enabled": bool(raw.get("enabled", False)),
            "empty_min": self._clamp_min(raw.get("empty_min", 10)),
            "restore": bool(raw.get("restore", False)),
            "lights": [r for r in raw.get("lights", list(LIGHTS)) if r in LIGHTS],
            "fan": bool(raw.get("fan", True)),
            "snooze_until": float(raw.get("snooze_until", 0) or 0),
        }
        self.state = "unknown"          # present | empty | unknown
        self.since = self._now()
        self.armed = True
        self.last_present = 0.0         # last time the radar/PIR saw somebody
        self.turned_off: List[str] = []  # what we switched off during the current absence
        self.events: List[Dict[str, Any]] = []
        self._acting = False
        if start_thread:
            threading.Thread(target=self._loop, name="presence", daemon=True).start()

    # ---- config ---------------------------------------------------------------------------------------------
    @staticmethod
    def _clamp_min(v: Any) -> int:
        try:
            return max(EMPTY_MIN_RANGE[0], min(EMPTY_MIN_RANGE[1], int(v)))
        except (TypeError, ValueError):
            return 10

    def _save(self) -> None:
        self._cfg_set("presence_cfg", json.dumps(self.cfg))

    def configure(self, d: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            if "enabled" in d:
                if not isinstance(d["enabled"], bool):
                    raise BodyError("enabled must be true or false")
                self.cfg["enabled"] = d["enabled"]
                if d["enabled"]:
                    self.armed = True
            if "empty_min" in d:
                try:
                    int(d["empty_min"])
                except (TypeError, ValueError):
                    raise BodyError("empty_min must be a number of minutes")
                self.cfg["empty_min"] = self._clamp_min(d["empty_min"])
            if "restore" in d:
                if not isinstance(d["restore"], bool):
                    raise BodyError("restore must be true or false")
                self.cfg["restore"] = d["restore"]
            if "fan" in d:
                if not isinstance(d["fan"], bool):
                    raise BodyError("fan must be true or false")
                self.cfg["fan"] = d["fan"]
            if "lights" in d:
                if not isinstance(d["lights"], list) or any(r not in LIGHTS for r in d["lights"]):
                    raise BodyError("lights must be a list of: " + ", ".join(LIGHTS))
                self.cfg["lights"] = list(dict.fromkeys(d["lights"]))
            self._save()
        self.body._changed()
        return self.status()

    def snooze(self, minutes: Any) -> Dict[str, Any]:
        try:
            m = max(0, min(24 * 60, int(minutes)))
        except (TypeError, ValueError):
            raise BodyError("minutes must be a number")
        with self._lock:
            self.cfg["snooze_until"] = self._now() + m * 60 if m else 0
            self._save()
        self.body._changed()
        return self.status()

    # ---- reading the room -----------------------------------------------------------------------------------
    def _read(self) -> Dict[str, Any]:
        """(present, usable) from the AV box. usable=False means: do not trust it, do not act."""
        b = self.body
        now = self._now()
        with b._lock:
            box = b.box
            online = box["online"] is True
            fresh = bool(box["seen_at"]) and now - box["seen_at"] <= FRESH_S
            rad = box["sensors"].get("radar_presence")
            pir = box["sensors"].get("pir_motion")
        usable = b.link and online and fresh and rad is not None and rad["v"] is not None
        present = bool(rad and rad["v"]) or bool(pir and pir["v"])
        return {"usable": usable, "present": present}

    def status(self) -> Dict[str, Any]:
        now = self._now()
        with self._lock:
            sn = max(0, int(self.cfg["snooze_until"] - now))
            return {"enabled": self.cfg["enabled"], "empty_min": self.cfg["empty_min"], "restore": self.cfg["restore"],
                    "lights": list(self.cfg["lights"]), "fan": self.cfg["fan"], "snooze_s": sn,
                    "state": self.state, "since_s": int(now - self.since), "armed": self.armed,
                    "would_act_in_s": self._eta(now), "events": list(self.events[-5:])}

    def _eta(self, now: float) -> Optional[int]:
        if not self.cfg["enabled"] or self.state != "empty" or not self.armed:
            return None
        return max(0, int(self.cfg["empty_min"] * 60 - (now - self.since)))

    # ---- the loop -------------------------------------------------------------------------------------------
    def _loop(self) -> None:
        while True:
            time.sleep(TICK_S)
            try:
                self.tick()
            except Exception:
                pass

    def tick(self) -> Optional[str]:
        """One evaluation. Returns what it did ("off", "restore") or None. Public so tests can drive it."""
        now = self._now()
        r = self._read()
        with self._lock:
            if not r["usable"]:
                if self.state != "unknown":
                    self.state, self.since = "unknown", now
                return None
            new = "present" if r["present"] else "empty"
            if new != self.state:
                prev = self.state
                self.state, self.since = new, now
                back: List[str] = []
                if new == "present":
                    self.last_present = now
                    self.armed = True
                    if self.cfg["restore"] and prev == "empty":
                        back = list(self.turned_off)
                    self.turned_off = []
                self.body._changed()
                if back:
                    return self._restore(back)
            if new == "present":
                self.last_present = now
                return None
            if not (self.cfg["enabled"] and self.armed and not self._acting):
                return None
            if now < self.cfg["snooze_until"]:
                return None
            if now - self.since < self.cfg["empty_min"] * 60:
                return None
            if not self.last_present or now - self.last_present > SEEN_WITHIN_S:
                return None            # the radar has not seen anybody lately: cannot tell "empty" from "blind"
            self.armed = False
            self._acting = True
        threading.Thread(target=self._switch_off, daemon=True).start()
        return "off"

    # ---- acting ---------------------------------------------------------------------------------------------
    def _on_devices(self) -> List[str]:
        """Devices that are currently on, from a fresh snapshot of the brain's device read-back."""
        h = self.body.home
        if not h["state"] or self._now() - h["at"] > HOME_STALE_S:
            try:
                self.body.home_refresh(force=True)
            except BodyError:
                pass
        st = (self.body.home["state"] or {})
        out: List[str] = []
        lights = st.get("lights") or {}
        if lights.get("ok"):
            for it in lights.get("items", []):
                if it.get("role") in self.cfg["lights"] and it.get("on") and it.get("available"):
                    out.append("light:" + it["role"])
        fan = st.get("fan") or {}
        if self.cfg["fan"] and fan.get("ok") and fan.get("on"):
            out.append("fan")
        return out

    def _event(self, text: str, done: List[str], failed: List[str]) -> None:
        ev = {"at": self._now(), "text": text, "done": done, "failed": failed}
        with self._lock:
            self.events.append(ev)
            del self.events[:-EVENTS_KEEP]
        self._pub("layla/home/event", json.dumps({"text": text}), False)
        self.body._changed()

    def _switch_off(self) -> None:
        try:
            targets = self._on_devices()
            done, failed = [], []
            for dev in targets:
                try:
                    r = self.body.home_control(dev, "off")
                except BodyError:
                    r = {"ok": False}
                (done if r.get("ok") else failed).append(dev)
            with self._lock:
                self.turned_off = list(done)
            if not targets:
                self._event("Room empty %d min: everything I manage was already off." % self.cfg["empty_min"], [], [])
                return
            nice = [LIGHT_LABEL.get(d[6:], d) if d.startswith("light:") else "fan" for d in done]
            text = "Room empty for %d min, so I switched off: %s." % (self.cfg["empty_min"], ", ".join(nice) or "nothing")
            if failed:
                text += " Could not switch off: " + ", ".join(LIGHT_LABEL.get(d[6:], d) if d.startswith("light:") else d
                                                             for d in failed) + "."
            self._event(text, done, failed)
        finally:
            with self._lock:
                self._acting = False

    def _restore(self, devs: List[str]) -> str:
        def run() -> None:
            done, failed = [], []
            for dev in devs:
                try:
                    r = self.body.home_control(dev, "on")
                except BodyError:
                    r = {"ok": False}
                (done if r.get("ok") else failed).append(dev)
            nice = [LIGHT_LABEL.get(d[6:], d) if d.startswith("light:") else "fan" for d in done]
            if done or failed:
                self._event("Welcome back: switched on %s." % (", ".join(nice) or "nothing"), done, failed)

        threading.Thread(target=run, daemon=True).start()
        return "restore"
