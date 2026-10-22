"""Layla's robot body (Layla GR): drive it by voice ("Layla, come forward", "turn left", "stop").

All driving goes through the Almanac server's /robot API on this VM (layla_almanac/body.py), the same path the
Almanac joystick uses, so voice and joystick share one set of safety rules: short self-expiring motor bursts, a
dead-man, a 5 s cap per move, and a front-obstacle stop. Directions are PHYSICAL (forward = where her face points);
the server handles the GR's swapped motor wiring.

Token: the Almanac owner token from /opt/layla-almanac/almanac.env (read once, never logged).
Kill switch: LAYLA_ROBOT=0 in /opt/layla/.env. Never raises into the caller.
"""
import json
import urllib.error
import urllib.request

from layla_plugin_util import S, flag, tool

BASE = "http://127.0.0.1:8150/api/almanac"
ENV_FILE = "/opt/layla-almanac/almanac.env"
_D = {"tok": None}

TOOLS = [
    tool("robot_move",
         "Drive Layla's own robot body (the GR car she lives in) for a few seconds. direction: forward, backward, "
         "left (turn left on the spot), right (turn right). seconds: 0.3-5 (default 1.5). speed: 90-255 "
         "(default 110, gentle). Use for 'come forward', 'go back', 'turn left', 'move a bit', 'drive towards me'. "
         "It stops by itself; something close in front blocks forward.",
         {"direction": {"type": "string", "enum": ["forward", "backward", "left", "right"]},
          "seconds": {"type": "number"}, "speed": {"type": "integer"}}, ["direction"]),
    tool("robot_stop", "Stop Layla's robot body immediately. Use for 'stop', 'halt', 'wait', 'don't move'.", {}, []),
    tool("robot_status",
         "Check Layla's robot body: is it online, is it moving, distance to whatever is in front, motion sensor.",
         {}, []),
]
NAMES = {"robot_move", "robot_stop", "robot_status"}
KEYWORDS = ("robot", "your body", "the car", "gr ", "layla gr", "drive", "come forward", "come here", "move forward",
            "go forward", "go back", "move back", "reverse", "turn left", "turn right", "spin", "stop moving",
            "halt", "come to me", "move a bit")


def init(**deps):
    try:
        for line in open(ENV_FILE, encoding="utf-8"):
            line = line.strip()
            if line.startswith("ALMANAC_TOKEN="):
                _D["tok"] = line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception as e:  # noqa: BLE001
        print(f"[robot] almanac token unavailable: {type(e).__name__}", flush=True)


def _req(method, path, body=None, timeout=8):
    if not _D["tok"]:
        raise RuntimeError("Almanac owner token not configured")
    r = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body is not None else None,
                               method=method, headers={"Content-Type": "application/json", "User-Agent": "layla/1.0",
                                                       "X-Layla-Secret": _D["tok"]})
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read())
        except Exception:  # noqa: BLE001
            return {"ok": False, "error": f"HTTP {e.code}"}


def status_text():
    s = _req("GET", "/body/state")
    r = s.get("robot") or {}
    if not s.get("link"):
        return "I can't reach my body's message broker right now."
    if not r.get("online"):
        return "My robot body (GR) is offline -- it's switched off or not on WiFi."
    bits = [f"moving {r['motion']}" if r.get("motion") not in (None, "stopped") else "standing still"]
    if r.get("distance_cm") is not None:
        bits.append(f"{r['distance_cm']:.0f} cm of space in front")
    if r.get("front_blocked"):
        bits.append("something is too close in front, so I won't drive forward")
    if r.get("pir") is not None:
        bits.append("motion sensor sees movement" if r["pir"] else "no movement around me")
    return "My robot body is online: " + ", ".join(bits) + "."


def call(name, args):
    try:
        if not flag("LAYLA_ROBOT"):
            return {"status": "error", "error": "robot control is switched off (LAYLA_ROBOT=0)"}
        args = args or {}
        if name == "robot_stop":
            r = _req("POST", "/robot/stop", {})
            return {"status": "success" if r.get("ok") else "error",
                    "output": "Stopped." if r.get("ok") else "", "error": r.get("error", "")}
        if name == "robot_status":
            return {"status": "success", "output": status_text()}
        if name == "robot_move":
            d = str(args.get("direction", "")).lower().strip()
            try:
                secs = float(args.get("seconds") or 1.5)
            except (TypeError, ValueError):
                secs = 1.5
            try:
                speed = int(args.get("speed") or 110)
            except (TypeError, ValueError):
                speed = 110
            speed = max(90, min(255, speed))
            r = _req("POST", "/robot/drive", {"action": d, "speed": speed, "seconds": secs})
            if r.get("ok"):
                return {"status": "success",
                        "output": f"Moving {d} for {r.get('seconds', secs):.1f} s (it stops on its own)."}
            return {"status": "error", "error": r.get("msg") or r.get("error") or "the robot didn't accept that"}
        return {"status": "error", "error": f"unknown tool {name}"}
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "error": f"{type(e).__name__}: {e}"}
