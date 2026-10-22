"""Layla ESP -- the owner's "AV Box": an ESPHome sensor + IR hub (DHT22, LDR, PIR, IR obstacle
sensors, SSD1306 OLED, and -- once the firmware below is flashed -- an IR receiver/blaster) over MQTT.

The ESP publishes through ESPHome's `mqtt:` component with topic_prefix `layla/esp1`:
    layla/esp1/status                          online | offline   (ESPHome birth/will)
    layla/esp1/sensor/<id>/state               number
    layla/esp1/binary_sensor/<id>/state        ON | OFF
    layla/esp1/ir/received                     a captured IR code  (NEW -- needs the remote_receiver
                                               publish in the firmware; see IR_FIRMWARE_NOTE)
and listens on:
    layla/esp1/display/text                    shown on the OLED
    layla/esp1/ir/transmit                     an IR code to blast (NEW -- needs remote_transmitter)

This plugin subscribes on the broker's internal plaintext listener (127.0.0.1:51883, VM-only), keeps the
latest values in memory, records a small rolling history (the foundation for routine prediction), watches
the box's liveness and tells the owner GENTLY if it drops (the box is on weak WiFi in a temporary home, so
a drop is expected, not an incident), and learns/replays IR codes. Read-mostly for mains; nothing here
controls the switchboard. Kill switch: ESP_BOX=0. Never raises into the caller.

IR_FIRMWARE_NOTE: the live box decodes IR (remote.pronto logs) but has no clean receive topic and no
transmitter. To make learn+replay real, add to the box YAML and OTA-flash (from a laptop on the box's WiFi):

    # NOTE: GPIO23 was the "IR Module Detection" binary_sensor -- DELETE that block, GPIO23 is now the TX LED.
    remote_receiver:
      id: ir_rx
      pin: {number: GPIO27, inverted: true, mode: {input: true, pullup: true}}   # RX = GPIO27 (TSOP/VS1838 OUT)
      dump: pronto
      on_pronto:
        - mqtt.publish: {topic: layla/esp1/ir/received, payload: !lambda 'return x.data;'}

    remote_transmitter:
      id: ir_tx
      pin: GPIO23            # TX = GPIO23 (IR LED via the transistor)
      carrier_duty_percent: 50%

    mqtt:
      on_message:
        - topic: layla/esp1/ir/transmit
          then:
            - remote_transmitter.transmit_pronto: {data: !lambda 'return x;'}

Until that is flashed, ir_learn reports "no code received" and ir_send reports the blaster isn't ready.
"""
import json
import os
import threading
import time
from collections import deque

from layla_plugin_util import S, flag, tool

PREFIX = os.environ.get("ESP_PREFIX", "layla/esp1")
HOST, PORT = os.environ.get("ESP_MQTT_HOST", "127.0.0.1"), int(os.environ.get("ESP_MQTT_PORT", "51883"))
STALE_S = 120                     # a sensor older than this is "not reporting"
OFFLINE_GRACE_S = 900             # box silent this long -> consider it dropped (weak WiFi here; be patient)
RENOTIFY_S = 6 * 3600             # don't nag about the same outage more than once per 6 h
HISTORY_MAX = 1500                # rolling samples kept in memory
PERSIST_S = 300                   # persist history to long-term memory this often
IR_LEARN_WINDOW_S = 25            # how long ir_learn waits for a button press
IR_MIN_LEN = 60                   # pronto codes shorter than this are ambient IR noise, not a button press
IR_CONFIDENT_LEN = 120            # a code this long is clearly a real press -> stop waiting early
MEM_HIST_KEY, MEM_IR_KEY = "esp:history", "esp:ir_codes"

LABELS = {"room_temperature": "temperature", "room_humidity": "humidity", "ldr_light_level": "light",
          "pir_motion": "motion", "ir_obstacle_detection": "ir_obstacle", "ir_module_detection": "ir_module"}

_D = {}
_vals = {}                        # id -> {"v": value, "at": ts, "since": ts of last change}
_state = {"online": None, "at": 0, "motion_at": 0}
_client = None
_nan = {}                          # id -> ts of last NaN reading
_hist = deque(maxlen=HISTORY_MAX)  # (ts, temp, humidity, light, motion_bool)
_last_persist = 0
# self-heal bookkeeping
_heal = {"notified_at": 0, "down_since": 0, "was_down": False}
# IR capture bookkeeping
_ir = {"pending_name": None, "pending_until": 0, "last_code": None, "last_at": 0, "candidates": []}
_ir_lock = threading.Lock()

TOOLS = [
    tool("esp_status",
         "Read the owner's AV sensor box: room temperature, humidity, light level, motion (PIR), IR obstacle "
         "sensors and whether the box is online. Use for 'room temperature?', 'is anyone moving?', 'is it dark?', "
         "'what's the room like?', 'get room state'.",
         {}, []),
    tool("get_room_state",
         "Alias of esp_status: the current state of the room from the AV sensor box (temperature, humidity, "
         "light, motion, box online/offline).",
         {}, []),
    tool("esp_history",
         "Summarise the room's recent sensor history and simple patterns from the AV box: temperature trend, "
         "how much motion lately, and roughly when the room is usually active. Use for 'how has the room been', "
         "'temperature trend', 'when am I usually active', 'has there been movement today'.",
         {}, []),
    tool("esp_display", "Show a short text message on the AV box's small OLED screen (max 40 characters).",
         {"text": S}, ["text"]),
    tool("ir_learn",
         "Learn an IR remote button: name it, then point the remote at the AV box and press the button once. "
         "Use for 'learn my AC power button', 'remember this TV remote button as volume up'.",
         {"name": S}, ["name"]),
    tool("ir_send",
         "Replay a previously learned IR code to control a device (AC, TV, ...). Use for 'turn on the AC', "
         "'press TV power', after the button was learned with ir_learn.",
         {"name": S}, ["name"]),
    tool("ir_list", "List the IR remote buttons the AV box has already learned.", {}, []),
    tool("ir_forget", "Forget a previously learned IR button by name.", {"name": S}, ["name"]),
]
NAMES = {"esp_status", "get_room_state", "esp_history", "esp_display", "ir_learn", "ir_send", "ir_list", "ir_forget"}
KEYWORDS = ("room temperature", "room temp", "humidity", "how hot", "how cold", "is it dark", "light level",
            "motion sensor", "pir", "esp32", "av box", "sensor box", "sensors", "room state", "oled",
            "small screen", "show on the screen", "temperature trend", "room history", "when am i usually",
            "learn the remote", "ir remote", "ac remote", "tv remote", "turn on the ac", "turn off the ac",
            "press power", "learn this button", "blast ir")


# -- memory helpers (guarded; the plugin works without persistence) ----------
def _mem():
    return _D.get("memory")


def _recall(key, default):
    m = _mem()
    try:
        if m is not None:
            v = m.recall("long_term", key)
            return v if v is not None else default
    except Exception:  # noqa: BLE001
        pass
    return default


def _remember(key, val):
    m = _mem()
    try:
        if m is not None:
            m.remember("long_term", key, val)
    except Exception:  # noqa: BLE001
        pass


def _notify(text, tone="calm"):
    push = _D.get("push")
    if callable(push):
        try:
            push({"type": "notify", "text": text, "tone": tone})
            return True
        except Exception:  # noqa: BLE001
            pass
    return False


def init(**deps):
    _D.update(deps)
    # warm-start the rolling history from memory so trends survive a brain restart
    for s in (_recall(MEM_HIST_KEY, []) or [])[-HISTORY_MAX:]:
        try:
            _hist.append(tuple(s))
        except Exception:  # noqa: BLE001
            pass
    if flag("ESP_BOX"):
        threading.Thread(target=_run, daemon=True).start()
        threading.Thread(target=_healer, daemon=True).start()


def _run():
    global _client
    try:
        import paho.mqtt.client as mqtt
        c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="layla-esp-plugin")
        def _on_connect(cl, u, f, rc, p=None):
            cl.subscribe(PREFIX + "/#")
            _publish_catalog(cl)
        c.on_connect = _on_connect
        c.on_message = _on_message
        c.reconnect_delay_set(2, 60)
        c.connect_async(HOST, PORT, 30)
        _client = c
        c.loop_forever(retry_first_connection=True)
    except Exception as e:  # noqa: BLE001
        print(f"[esp] mqtt thread stopped: {type(e).__name__}", flush=True)


def _on_message(_c, _u, msg):
    try:
        t = msg.topic[len(PREFIX) + 1:]
        val = msg.payload.decode("utf-8", "replace").strip()
        now = time.time()
        if t == "status":
            _state.update(online=(val.lower() == "online"), at=now)
            return
        if t == "ir/request":                  # the Almanac app asking us to send / learn / forget a button
            threading.Thread(target=_serve_ir_request, args=(val,), daemon=True).start()
            return
        if t == "ir/received":                 # a captured IR code from the (flashed) receiver
            if val:
                with _ir_lock:
                    _ir["last_code"], _ir["last_at"] = val, now
                    # collect real (long) codes during a learn window; short ones are ambient IR noise
                    if _ir["pending_name"] and now <= _ir["pending_until"] and len(val) >= IR_MIN_LEN:
                        _ir["candidates"].append(val)
            return
        parts = t.split("/")
        if len(parts) == 3 and parts[2] == "state":
            kind, sid = parts[0], parts[1]
            if kind == "sensor":
                try:
                    v = float(val)
                except ValueError:
                    return
                if v != v:                # NaN: sensor attached but failing (DHT22 'Communication failed')
                    _vals.pop(sid, None)
                    _nan[sid] = now
                    return
                _nan.pop(sid, None)
            elif kind == "binary_sensor":
                v = val.upper() == "ON"
            else:
                return
            old = _vals.get(sid)
            _vals[sid] = {"v": v, "at": now, "since": now if (old is None or old["v"] != v) else old["since"]}
            if sid == "pir_motion" and v is True:
                _state["motion_at"] = now
            _record_history(now)
    except Exception:  # noqa: BLE001
        pass


# -- predictive foundation: rolling history ----------------------------------
def _record_history(now):
    """Append a compact sample and periodically persist. Cheap: one tuple + an occasional memory write."""
    global _last_persist
    t = _vals.get("room_temperature"); h = _vals.get("room_humidity")
    l = _vals.get("ldr_light_level"); m = _vals.get("pir_motion")
    sample = (round(now), round(t["v"], 1) if t else None, round(h["v"]) if h else None,
              round(l["v"], 2) if l else None, bool(m["v"]) if m else None)
    # sample at most every ~30 s to keep the ring spanning a useful window
    if _hist and now - _hist[-1][0] < 30:
        return
    _hist.append(sample)
    if now - _last_persist >= PERSIST_S:
        _remember(MEM_HIST_KEY, list(_hist))
        _last_persist = now


def _history_summary():
    if not _hist:
        return "I haven't recorded any room history yet."
    now = time.time()
    hr = [s for s in _hist if now - s[0] <= 3600]
    temps = [s[1] for s in _hist if s[1] is not None]
    bits = []
    if temps:
        recent = [s[1] for s in hr if s[1] is not None]
        if len(temps) >= 3 and recent:
            delta = recent[-1] - temps[max(0, len(temps) - min(len(temps), 120))]
            trend = "rising" if delta > 0.3 else "falling" if delta < -0.3 else "steady"
            bits.append(f"temperature is {trend} (now {recent[-1]:.1f} C)")
    motions = sum(1 for s in hr if s[4] is True)
    if hr:
        bits.append(f"{motions} motion event(s) in the last hour")
    # rough "usually active" hours from all history (local server time)
    active_hours = {}
    for s in _hist:
        if s[4] is True:
            hrn = time.localtime(s[0]).tm_hour
            active_hours[hrn] = active_hours.get(hrn, 0) + 1
    if active_hours:
        top = sorted(active_hours, key=active_hours.get, reverse=True)[:3]
        bits.append("usually most active around " + ", ".join(f"{h}:00" for h in sorted(top)))
    span_h = (now - _hist[0][0]) / 3600.0
    return (f"Room history over ~{span_h:.1f} h ({len(_hist)} samples): " + "; ".join(bits) + "."
            if bits else "Room history is still building up.")


# -- self-healing: gentle, weak-WiFi-aware -----------------------------------
def _healer():
    """Watch the box's liveness. A drop here is expected (weak WiFi, temporary home), so alert once,
    softly, after a long grace, and never nag. Recovery clears silently."""
    while True:
        try:
            time.sleep(60)
            if not flag("ESP_BOX"):
                continue
            now = time.time()
            last = max([_state["at"]] + [r["at"] for r in _vals.values()] or [0])
            down = (last == 0) or (now - last > OFFLINE_GRACE_S) or (_state["online"] is False)
            if down:
                if not _heal["was_down"]:
                    _heal["was_down"] = True
                    _heal["down_since"] = last or now
                if now - _heal["notified_at"] >= RENOTIFY_S:
                    mins = int((now - (_heal["down_since"] or now)) / 60)
                    _notify(f"Heads up: the AV sensor box has been quiet for about {mins} min -- most likely the "
                            f"weak WiFi here, not a fault. I'll keep listening and let you know when it's back.",
                            "calm")
                    _heal["notified_at"] = now
            elif _heal["was_down"]:
                _heal["was_down"] = False
                down_min = int((now - (_heal["down_since"] or now)) / 60)
                if down_min >= 5:
                    _notify(f"The AV box is back online (was away ~{down_min} min).", "warm")
                _heal["down_since"] = 0
        except Exception:  # noqa: BLE001
            pass


def _get(sid):
    r = _vals.get(sid)
    return r if r and time.time() - r["at"] <= STALE_S else None


def _ago(ts):
    s = int(time.time() - ts)
    return "just now" if s < 60 else (f"{s // 60} min ago" if s < 3600 else f"{s // 3600} h ago")


def summary():
    if not flag("ESP_BOX"):
        return "The AV sensor box is switched off."
    if not _vals:
        return "I haven't heard from the AV sensor box yet (no readings received)."
    bits = []
    t, h, l = _get("room_temperature"), _get("room_humidity"), _get("ldr_light_level")
    if t:
        bits.append(f"temperature {t['v']:.1f} C")
    if h:
        bits.append(f"humidity {h['v']:.0f}%")
    if l:
        bits.append(f"light sensor {l['v']:.2f} V (raw; scale not calibrated yet)")
    # LD2410C mmWave: sees people sitting still, unlike the PIR. Binary states are only published on change,
    # so trust the last value while the box itself is online instead of calling it stale after STALE_S.
    rp = _vals.get("radar_presence") if _state["online"] else None
    if rp:
        if rp["v"]:
            d = _get("radar_detection_distance")
            mv = _vals.get("radar_moving_target")
            where = f" about {d['v'] / 100:.1f} m from the box" if d and d["v"] and d["v"] > 0 else ""
            bits.append(f"radar: someone is in the room ({'moving' if mv and mv['v'] else 'still'}){where}")
        else:
            bits.append(f"radar: nobody in the room (empty since {_ago(rp['since'])})")
    m = _get("pir_motion")
    if m:
        bits.append("motion detected now" if m["v"] else
                    ("no motion right now" + (f", last seen {_ago(_state['motion_at'])}" if _state["motion_at"] else "")))
    for sid, label in (("ir_obstacle_detection", "IR obstacle sensor"), ("ir_module_detection", "IR module")):
        r = _get(sid)
        if r:
            bits.append(f"{label}: {'blocked' if r['v'] else 'clear'}")
    for sid, label in (("room_temperature", "temperature"), ("room_humidity", "humidity")):
        if sid in _nan and not _get(sid) and time.time() - _nan[sid] <= STALE_S:
            bits.append(f"the {label} sensor (DHT22) is not giving a valid reading, probably a wiring fault")
    if not bits:
        return "The AV sensor box has gone quiet (no fresh readings in the last 2 minutes)."
    box = {True: "online", False: "offline", None: "status unknown"}[_state["online"]]
    return f"AV sensor box ({box}): " + "; ".join(bits) + "."


# -- IR genie ----------------------------------------------------------------
def _ir_learn(name):
    name = (name or "").strip().lower()
    if not name:
        return {"status": "error", "error": "give the button a name, e.g. 'ac power'"}
    if not flag("ESP_BOX") or _client is None:
        return {"status": "error", "error": "AV box link is off"}
    with _ir_lock:
        _ir["pending_name"] = name
        _ir["pending_until"] = time.time() + IR_LEARN_WINDOW_S
        _ir["candidates"] = []
    # wait for a real (long) code; stop early once we clearly have a button press
    deadline = time.time() + IR_LEARN_WINDOW_S
    while time.time() < deadline:
        time.sleep(0.4)
        with _ir_lock:
            if any(len(c) >= IR_CONFIDENT_LEN for c in _ir["candidates"]):
                break
    with _ir_lock:
        _ir["pending_name"] = None
        cands = list(_ir["candidates"])
        _ir["candidates"] = []
    if not cands:
        return {"status": "error",
                "error": (f"Only ambient IR noise (or nothing) came through in {IR_LEARN_WINDOW_S}s -- no real "
                          "button press. Point the remote right at the box's receiver and press firmly once.")}
    best = max(cands, key=len)                 # the real remote code is the longest; noise is short
    codes = dict(_recall(MEM_IR_KEY, {}) or {})
    codes[name] = {"code": best, "learned_at": time.time(), "len": len(best)}
    _remember(MEM_IR_KEY, codes)
    _publish_catalog()
    _notify(f"Learned the IR button '{name}'.", "warm")
    return {"status": "success",
            "output": f"Learned '{name}' ({len(best)}-char code). You can now say: send {name}."}


def _publish_catalog(cl=None):
    """Retain the learned button NAMES (never the codes) so the Almanac app can list them."""
    cl = cl or _client
    if cl is None:
        return
    try:
        names = sorted((_recall(MEM_IR_KEY, {}) or {}).keys())
        cl.publish(PREFIX + "/ir/catalog", json.dumps(names), qos=1, retain=True)
    except Exception:  # noqa: BLE001
        pass


def _serve_ir_request(raw):
    """Almanac -> `ir/request` {id, op, name}; answer on `ir/result`. Only VM-local clients reach this broker."""
    try:
        d = json.loads(raw)
        rid, op, name = str(d.get("id", ""))[:32], str(d.get("op", "")), str(d.get("name", ""))
    except Exception:  # noqa: BLE001
        return
    if op == "send":
        r = _ir_send(name)
    elif op == "learn":
        r = _ir_learn(name)
    elif op == "forget":
        r = call("ir_forget", {"name": name})
    else:
        r = {"status": "error", "error": "unknown op"}
    ok = r.get("status") == "success"
    if _client is not None:
        try:
            _client.publish(PREFIX + "/ir/result", json.dumps(
                {"id": rid, "op": op, "name": name, "ok": ok, "msg": r.get("output") or r.get("error") or ""}),
                qos=1, retain=False)
        except Exception:  # noqa: BLE001
            pass


def _ir_send(name):
    name = (name or "").strip().lower()
    codes = dict(_recall(MEM_IR_KEY, {}) or {})
    if name not in codes:
        return {"status": "error", "error": f"I haven't learned '{name}'. Known: {', '.join(codes) or 'none'}."}
    if not flag("ESP_BOX") or _client is None:
        return {"status": "error", "error": "AV box link is off"}
    _client.publish(PREFIX + "/ir/transmit", codes[name]["code"], qos=1, retain=False)
    return {"status": "success",
            "output": (f"Sent the '{name}' IR code. (If the device didn't respond, the box needs a "
                       "remote_transmitter + IR LED flashed -- see IR_FIRMWARE_NOTE.)")}


def call(name, args):
    try:
        args = args or {}
        if name in ("esp_status", "get_room_state"):
            return {"status": "success", "output": summary()}
        if name == "esp_history":
            return {"status": "success", "output": _history_summary()}
        if name == "esp_display":
            if not flag("ESP_BOX") or _client is None:
                return {"status": "error", "error": "AV box link is off"}
            text = "".join(ch for ch in str(args.get("text", "")) if ch.isprintable())[:40].strip()
            if not text:
                return {"status": "error", "error": "no text"}
            _client.publish(PREFIX + "/display/text", text, qos=0, retain=False)
            return {"status": "success", "output": f"Sent to the AV box screen: {text}"}
        if name == "ir_learn":
            return _ir_learn(args.get("name"))
        if name == "ir_send":
            return _ir_send(args.get("name"))
        if name == "ir_list":
            codes = _recall(MEM_IR_KEY, {}) or {}
            return {"status": "success",
                    "output": ("Learned IR buttons: " + ", ".join(sorted(codes))) if codes
                              else "No IR buttons learned yet. Use ir_learn to teach one."}
        if name == "ir_forget":
            nm = (args.get("name") or "").strip().lower()
            codes = dict(_recall(MEM_IR_KEY, {}) or {})
            if nm in codes:
                codes.pop(nm)
                _remember(MEM_IR_KEY, codes)
                _publish_catalog()
                return {"status": "success", "output": f"Forgot the IR button '{nm}'."}
            return {"status": "error", "error": f"No learned button named '{nm}'."}
        return {"status": "error", "error": f"unknown tool {name}"}
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "error": f"{type(e).__name__}: {e}"}
