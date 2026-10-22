"""Home control bridge for the Almanac app (Bedroom & Appliances screen).

The Almanac server cannot reach the cloud devices itself (tokens live in the brain), so it asks over the VM-local MQTT
broker and this plugin answers using the brain's EXISTING, read-back-verified device code:
  fan    -> control_bedroom_fan / tuya_fan fan_status       (Tuya cloud)
  plug   -> control_plug / _plug_read                       (Wipro 16A, Tuya cloud)
  lights -> control_switchboard_relay / layla_evolviot      (Evolviot 5-channel module)
  tv     -> tv_control (laptop ADB bridge; no state read-back, the bridge's ack is the truth)

Topics (127.0.0.1:51883, never exposed):
  layla/home/request  {id, op:"get"|"set", device, action, value}
  layla/home/result   {id, ok, msg}
  layla/home/state    retained snapshot (refreshed on "get" and after every successful "set"; cached 4 s)

No LLM tools here; Layla's voice already has these devices. Kill switch: LAYLA_HOME_BRIDGE=0. Never raises.
"""
import json
import os
import threading
import time

from layla_plugin_util import flag

TOOLS, NAMES, KEYWORDS = [], set(), ()
HOST, PORT = os.environ.get("ESP_MQTT_HOST", "127.0.0.1"), int(os.environ.get("ESP_MQTT_PORT", "51883"))
PREFIX = "layla/home"
CACHE_S = 4.0
LIGHT_ROLES = {"switch1": "bulb", "switch2": "tube", "switch3": "ceiling1", "switch4": "ceiling2", "switch5": "general"}
TV_KEYS = {"power_on": "wake", "power_off": "sleep", "power": "power", "mute": "mute", "volume_up": "volume_up",
           "volume_down": "volume_down", "play": "play", "pause": "pause", "play_pause": "play_pause", "next": "next",
           "previous": "previous", "home": "home", "back": "back"}

_D = {}
_client = None
_snap = {"ts": 0}
_snap_lock = threading.Lock()
_refresh_lock = threading.Lock()


def init(**deps):
    _D.update(deps)
    if flag("LAYLA_HOME_BRIDGE"):
        threading.Thread(target=_run, name="home-bridge", daemon=True).start()


def _run():
    global _client
    try:
        import paho.mqtt.client as mqtt
        c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="layla-home-bridge")

        def _on_connect(cl, u, f, rc, p=None):
            cl.subscribe([(PREFIX + "/request", 1), (PREFIX + "/event", 0)])

        def _on_message(cl, u, msg):
            raw = msg.payload.decode("utf-8", "replace")
            if msg.topic == PREFIX + "/event":        # the Almanac presence automation acted: tell the owner quietly
                try:
                    push = _D.get("push")
                    if push:
                        push({"type": "notify", "text": str(json.loads(raw).get("text", ""))[:240], "tone": "calm"})
                except Exception:  # noqa: BLE001
                    pass
                return
            threading.Thread(target=_serve, args=(raw,), daemon=True).start()

        c.on_connect = _on_connect
        c.on_message = _on_message
        c.reconnect_delay_set(2, 60)
        c.connect_async(HOST, PORT, 30)
        _client = c
        c.loop_forever(retry_first_connection=True)
    except Exception as e:  # noqa: BLE001
        print(f"[home] mqtt thread stopped: {type(e).__name__}", flush=True)


def _pub(topic, obj, retain=False):
    if _client is not None:
        try:
            _client.publish(topic, json.dumps(obj, separators=(",", ":")), qos=1, retain=retain)
        except Exception:  # noqa: BLE001
            pass


# ---- reading state --------------------------------------------------------------------------------------------
def _fan():
    try:
        r = _D["fan_status"]()
        o = r.get("output") or {}
        if r.get("status") != "success" or not isinstance(o, dict):
            err = str(r.get("error") or "fan unreachable")
            return {"ok": False, "offline": "OFFLINE" in err, "err": err[:160]}
        sp = o.get("speed")
        return {"ok": True, "on": bool(o.get("on")), "speed": int(sp) if isinstance(sp, (int, float)) else None}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "err": type(e).__name__}


def _plug():
    try:
        d = _D["plug_read"]()
        if d is None:
            return {"ok": False, "err": "plug unreachable"}
        return {"ok": True, "on": bool(d.get("switch_1")), "power_w": round((d.get("cur_power") or 0) / 10.0, 1),
                "voltage": round((d.get("cur_voltage") or 0) / 10.0)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "err": type(e).__name__}


def _lights():
    ev = _D.get("ev")
    if ev is None:
        return {"ok": False, "err": "Evolviot module not loaded"}
    try:
        chans, states = ev._channels(), ev._states()
        items = []
        for c in chans:
            s = states.get(c["entity"]) or {}
            items.append({"key": c["key"], "role": LIGHT_ROLES.get(c["key"]), "name": c["name"] or c["key"],
                          "on": bool(ev._is_on(s)), "level": ev._level(s), "available": bool(s.get("available")),
                          "dimmable": c["key"] in getattr(ev, "DIMMABLE", set())})
        return {"ok": True, "items": items}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "err": str(e)[:120]}


def refresh(force=False):
    with _refresh_lock:
        if not force and time.time() - _snap.get("ts", 0) < CACHE_S:
            return dict(_snap)
        snap = {"ts": time.time(), "fan": _fan(), "plug": _plug(), "lights": _lights(),
                "tv": {"ok": True, "note": "TV state is not readable; commands are confirmed by the home laptop bridge"}}
        with _snap_lock:
            _snap.clear()
            _snap.update(snap)
        _pub(PREFIX + "/state", snap, retain=True)
        return snap


# ---- commands -------------------------------------------------------------------------------------------------
def _light_key(name):
    ev = _D.get("ev")
    for c in (ev._channels() if ev else []):
        if c["key"] == name or LIGHT_ROLES.get(c["key"]) == name:
            return c["key"]
    return None


def _do(device, action, value):
    ex = _D["execute_tool"]
    if device == "fan":
        if action == "speed":
            v = int(value)
            if not 1 <= v <= 5:
                return {"status": "error", "error": "fan speed is 1-5"}
            return ex("control_bedroom_fan", {"action": "on", "speed": v})
        if action in ("on", "off", "toggle"):
            return ex("control_bedroom_fan", {"action": action})
    elif device == "plug":
        if action in ("on", "off", "toggle"):
            return ex("control_plug", {"action": action})
    elif device.startswith("light:"):
        key = _light_key(device.split(":", 1)[1])
        if not key:
            return {"status": "error", "error": "unknown light"}
        args = {"relay": key, "action": action}
        if action == "dim":
            v = int(value)
            if not 1 <= v <= 100:
                return {"status": "error", "error": "brightness is 1-100"}
            args = {"relay": key, "action": "on", "brightness": v}
        elif action not in ("on", "off", "toggle"):
            return {"status": "error", "error": "light action must be on, off, toggle or dim"}
        return ex("control_switchboard_relay", args)
    elif device == "tv":
        key = TV_KEYS.get(action)
        if not key:
            return {"status": "error", "error": "unknown TV action"}
        return _D["tv_control"]({"key": key})
    return {"status": "error", "error": f"unknown device/action {device}/{action}"}


def _serve(raw):
    try:
        d = json.loads(raw)
        rid = str(d.get("id", ""))[:32]
        op, device, action = str(d.get("op", "")), str(d.get("device", "")), str(d.get("action", ""))
    except Exception:  # noqa: BLE001
        return
    if op == "get":
        refresh(force=bool(d.get("force")))
        _pub(PREFIX + "/result", {"id": rid, "ok": True, "msg": "refreshed"})
        return
    if op != "set":
        _pub(PREFIX + "/result", {"id": rid, "ok": False, "msg": "unknown op"})
        return
    try:
        r = _do(device, action, d.get("value"))
    except Exception as e:  # noqa: BLE001
        r = {"status": "error", "error": f"{type(e).__name__}: {e}"}
    ok = r.get("status") == "success"
    out = r.get("output")
    msg = (out if isinstance(out, str) else json.dumps(out)) if ok else str(r.get("error") or "failed")
    _pub(PREFIX + "/result", {"id": rid, "ok": ok, "msg": str(msg)[:300]})
    if device != "tv":
        refresh(force=True)
