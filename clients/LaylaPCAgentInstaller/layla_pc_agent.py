"""Layla-PC-Agent -- the Windows-side companion for PC Access, Tiers 1-2 only
(browser + application launch). Connects OUTBOUND to the same secured broker
the ESP32 home box uses -- no inbound port ever opens on this machine, exactly
the pattern already proven for home control.

Topics (device_id below):
    cmd    tryvanta/pc/<device_id>/cmd/open_url    payload = a URL
    cmd    tryvanta/pc/<device_id>/cmd/open_app    payload = a friendly app name
    result tryvanta/pc/<device_id>/result          {"cmd":...,"arg":...,"status":...,"detail":...}
    status tryvanta/pc/<device_id>/status           online|offline (retained, LWT)

Tier 3 (screenshot, mouse/keyboard) now exists in layla_pc_cu.py, gated by the
approval UI that this note asked for: owner Allow per session (and per risky
step) in Layla, a visible STOP banner here, corner fail-safe, local off file.
    cmd    tryvanta/pc/<device_id>/cmd/cu           JSON {"req","op","session","args"}
    result tryvanta/pc/<device_id>/cu/<req>         JSON reply
Tier 4 (shell exec, installs) is still deliberately NOT implemented.
"""
import os
import shutil
import subprocess
import sys
import webbrowser

import certifi
import paho.mqtt.client as mqtt

DEVICE_ID = "pc-001"
HOST = "layla.tryvanta.in"
PORT = 8883
USER = "pcagent"
PASS = "PCAGENT_MQTT_5583_Xv2q"
BASE = f"tryvanta/pc/{DEVICE_ID}"

# Tier 3 (screen control) lives in its own module so Tiers 1-2 keep working
# even if pyautogui/tkinter can't load on some machine.
try:
    import layla_pc_cu as _cu_mod
    _cu_err = ""
except Exception as _e:  # noqa: BLE001
    _cu_mod, _cu_err = None, f"{type(_e).__name__}: {_e}"

# Friendly name -> how to actually launch it on Windows. Resolved lazily so a
# missing app just fails that one command, not the whole agent.
def _start(cmd_str: str):
    subprocess.Popen(f'start "" {cmd_str}', shell=True)

APP_LAUNCHERS = {
    "notepad": lambda: _start("notepad.exe"),
    "explorer": lambda: _start("explorer.exe"),
    "file explorer": lambda: _start("explorer.exe"),
    "calculator": lambda: _start("calc.exe"),
    "chrome": lambda: _start("chrome") if shutil.which("chrome") else _start(
        r'"C:\Program Files\Google\Chrome\Application\chrome.exe"'),
    "edge": lambda: _start("msedge"),
    "vscode": lambda: _start("code") if shutil.which("code") else _start("Code.exe"),
    "vs code": lambda: _start("code") if shutil.which("code") else _start("Code.exe"),
    "spotify": lambda: _start("spotify:"),
    "word": lambda: _start("winword"),
    "excel": lambda: _start("excel"),
    "task manager": lambda: _start("taskmgr"),
    "settings": lambda: _start("ms-settings:"),
}


def handle_open_url(url: str):
    url = url.strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        return {"status": "error", "detail": "only http(s) URLs are allowed"}
    webbrowser.open(url)
    return {"status": "success", "detail": f"opened {url} in the default browser"}


def handle_open_app(name: str):
    key = name.strip().lower()
    fn = APP_LAUNCHERS.get(key)
    if fn is None:
        return {"status": "error", "detail": f"'{name}' isn't in the known app list yet: {sorted(APP_LAUNCHERS)}"}
    try:
        fn()
        return {"status": "success", "detail": f"launched {name}"}
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "detail": str(e)}


# Screenpipe activity memory
try:
    import screenpipe_recorder as _sp_mod
except Exception as _e:
    _sp_mod = None


def on_connect(client, userdata, flags, rc, props=None):
    print(f"[layla-pc-agent] connected to {HOST}:{PORT} as {DEVICE_ID}", flush=True)
    client.subscribe(f"{BASE}/cmd/+", qos=1)
    client.publish(f"{BASE}/status", "online", retain=True, qos=1)


def on_message(client, userdata, msg):
    action = msg.topic.rsplit("/", 1)[-1]
    arg = msg.payload.decode("utf-8", errors="replace")
    import json
    import threading

    if action == "cu":
        def _cu():
            try:
                cmd = json.loads(arg)
            except Exception:
                return
            if _cu_mod is None:
                reply = {"ok": False, "error": f"screen control unavailable on this PC: {_cu_err}"}
            else:
                reply = _cu_mod.handle(cmd)
            client.publish(f"{BASE}/cu/{cmd.get('req', 'x')}", json.dumps(reply), qos=1)
            print(f"[layla-pc-agent] cu {cmd.get('op')} -> ok={reply.get('ok')}")
        threading.Thread(target=_cu, daemon=True).start()
        return

    print(f"[layla-pc-agent] cmd={action} arg={arg!r}")
    if action == "open_url":
        result = handle_open_url(arg)
    elif action == "open_app":
        result = handle_open_app(arg)
    elif action in ("query_activity", "query_pc_activity"):
        try:
            params = json.loads(arg) if arg.strip().startswith("{") else {"query": arg}
        except Exception:
            params = {"query": arg}
        if _sp_mod is None:
            result = {"status": "error", "error": "Screenpipe activity recorder unavailable"}
        else:
            result = _sp_mod.query_activity(params.get("query"), float(params.get("hours", 24)))
    elif action == "list_windows":
        if _cu_mod is None:
            result = {"status": "error", "error": "Desktop control unavailable"}
        else:
            result = _cu_mod.list_windows()
    elif action == "screenshot":
        if _cu_mod is None:
            result = {"status": "error", "error": "Desktop control unavailable"}
        else:
            result = _cu_mod.get_screenshot()
    elif action == "control_desktop":
        try:
            cmd = json.loads(arg) if isinstance(arg, str) and arg.strip().startswith("{") else {"op": "list_windows"}
        except Exception as e:
            cmd = {"op": "unknown", "error": str(e)}
        if _cu_mod is None:
            result = {"status": "error", "error": "Desktop control unavailable"}
        else:
            result = _cu_mod.handle(cmd)
    else:
        result = {"status": "error", "detail": f"unknown command '{action}'"}

    result.update({"cmd": action, "arg": arg})
    client.publish(f"{BASE}/result", json.dumps(result), qos=1)
    print(f"[layla-pc-agent] -> {result.get('status') or result.get('ok')}")


def main():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"layla-pc-agent-{DEVICE_ID}")
    client.username_pw_set(USER, PASS)
    client.tls_set(ca_certs=certifi.where())
    client.will_set(f"{BASE}/status", "offline", retain=True, qos=1)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(HOST, PORT, keepalive=30)
    print(f"[layla-pc-agent] starting -- device_id={DEVICE_ID}, apps known: {sorted(APP_LAUNCHERS)}")

    # Start background activity monitor
    if _sp_mod is not None:
        try:
            monitor = _sp_mod.ActivityMonitorThread(poll_interval=10.0)
            monitor.start()
        except Exception as e:
            print(f"[layla-pc-agent] failed to start activity monitor: {e}")

    client.loop_forever()


if __name__ == "__main__":
    main()
