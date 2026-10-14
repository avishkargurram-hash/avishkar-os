"""Layla ESP -- the owner's ESPHome sensor box (DHT22, LDR, PIR, IR obstacle sensors, OLED) over MQTT.

The ESP publishes through ESPHome's `mqtt:` component with topic_prefix `layla/esp1`:
    layla/esp1/status                          online | offline   (ESPHome birth/will)
    layla/esp1/sensor/<id>/state               number
    layla/esp1/binary_sensor/<id>/state        ON | OFF
and listens on  layla/esp1/display/text       (shown on the OLED).
This plugin subscribes on the broker's internal plaintext listener (127.0.0.1:51883, VM-only), keeps the latest
values in memory and exposes read tools plus an OLED message tool. Read-mostly, nothing here controls mains power.
Kill switch: ESP_BOX=0. Never raises into the caller.
"""
import os
import threading
import time

from layla_plugin_util import S, flag, tool

PREFIX = os.environ.get("ESP_PREFIX", "layla/esp1")
HOST, PORT = os.environ.get("ESP_MQTT_HOST", "127.0.0.1"), int(os.environ.get("ESP_MQTT_PORT", "51883"))
STALE_S = 120                     # a sensor older than this is "not reporting"
LABELS = {"room_temperature": "temperature", "room_humidity": "humidity", "ldr_light_level": "light",
          "pir_motion": "motion", "ir_obstacle_detection": "ir_obstacle", "ir_module_detection": "ir_module"}

_D = {}
_vals = {}                        # id -> {"v": value, "at": ts, "since": ts of last change}
_state = {"online": None, "at": 0, "motion_at": 0}
_client = None
_nan = {}                          # id -> ts of last NaN reading

TOOLS = [
    tool("esp_status",
         "Read the owner's ESP32 sensor box: room temperature, humidity, light level, motion (PIR), IR obstacle "
         "sensors and whether the box is online. Use for 'room temperature?', 'is anyone moving?', 'is it dark?'.",
         {}, []),
    tool("esp_display", "Show a short text message on the ESP32 box's small OLED screen (max 40 characters).",
         {"text": S}, ["text"]),
]
NAMES = {"esp_status", "esp_display"}
KEYWORDS = ("room temperature", "room temp", "humidity", "how hot", "how cold", "is it dark", "light level",
            "motion sensor", "pir", "esp32", "sensor box", "sensors", "oled", "small screen", "show on the screen")


def init(**deps):
    _D.update(deps)
    if flag("ESP_BOX"):
        threading.Thread(target=_run, daemon=True).start()


def _run():
    global _client
    try:
        import paho.mqtt.client as mqtt
        c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="layla-esp-plugin")
        c.on_connect = lambda cl, u, f, rc, p=None: cl.subscribe(PREFIX + "/#")
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
        parts = t.split("/")
        if len(parts) == 3 and parts[2] == "state":
            kind, sid = parts[0], parts[1]
            if kind == "sensor":
                try:
                    v = float(val)
                except ValueError:
                    return
                if v != v:                # NaN: the sensor is attached but failing (e.g. DHT22 'Communication failed')
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
        return "The ESP sensor box is switched off."
    if not _vals:
        return "I haven't heard from the ESP sensor box yet (no readings received)."
    bits = []
    t, h, l = _get("room_temperature"), _get("room_humidity"), _get("ldr_light_level")
    if t:
        bits.append(f"temperature {t['v']:.1f} C")
    if h:
        bits.append(f"humidity {h['v']:.0f}%")
    if l:
        # raw ADC volts at 12 dB attenuation (0-~3.1 V). Which end is "dark" depends on the LDR wiring: calibrate.
        bits.append(f"light sensor {l['v']:.2f} V (raw; scale not calibrated yet)")
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
        return "The ESP sensor box has gone quiet (no fresh readings in the last 2 minutes)."
    box = {True: "online", False: "offline", None: "status unknown"}[_state["online"]]
    return f"ESP sensor box ({box}): " + "; ".join(bits) + "."


def call(name, args):
    try:
        args = args or {}
        if name == "esp_status":
            return {"status": "success", "output": summary()}
        if name == "esp_display":
            if not flag("ESP_BOX") or _client is None:
                return {"status": "error", "error": "ESP box link is off"}
            text = "".join(ch for ch in str(args.get("text", "")) if ch.isprintable())[:40].strip()
            if not text:
                return {"status": "error", "error": "no text"}
            _client.publish(PREFIX + "/display/text", text, qos=0, retain=False)
            return {"status": "success", "output": f"Sent to the ESP screen: {text}"}
        return {"status": "error", "error": f"unknown tool {name}"}
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "error": f"{type(e).__name__}: {e}"}
