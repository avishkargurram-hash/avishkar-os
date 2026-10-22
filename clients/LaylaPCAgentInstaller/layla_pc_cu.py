"""Layla PC Computer Use (Pillar 5: UFO² Windows Desktop GUI Hands).

Provides direct Windows desktop GUI control (inspect windows, screen capture,
mouse clicks, typing, hotkeys) with failsafe protection.
"""

from __future__ import annotations

import base64
import io
import time
from typing import Any, Dict, List, Optional

try:
    import pyautogui
    pyautogui.FAILSAFE = False
    pyautogui.PAUSE = 0.05
except ImportError:
    pyautogui = None

try:
    import pygetwindow as gw
except ImportError:
    gw = None

try:
    from PIL import Image
except ImportError:
    Image = None


def get_screenshot(max_width: int = 1280, quality: int = 60) -> Dict[str, Any]:
    """Captures a screenshot of the primary Windows desktop and returns base64 JPEG."""
    if pyautogui is None:
        return {"ok": False, "error": "pyautogui is not installed"}

    try:
        ss = pyautogui.screenshot()
        w, h = ss.size
        if w > max_width:
            scale = max_width / float(w)
            new_h = int(h * scale)
            ss = ss.resize((max_width, new_h), Image.Resampling.LANCZOS if Image else None)

        buf = io.BytesIO()
        ss.save(buf, format="JPEG", quality=quality)
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        return {
            "ok": True,
            "width": w,
            "height": h,
            "screenshot_b64": b64,
        }
    except Exception as exc:
        return {"ok": False, "error": f"Screenshot failed: {exc}"}


def list_windows() -> Dict[str, Any]:
    """Lists visible, non-empty application windows on the desktop."""
    if gw is None:
        return {"ok": False, "error": "pygetwindow is not installed"}

    try:
        windows = []
        for w in gw.getAllWindows():
            title = (w.title or "").strip()
            if title and w.visible and w.width > 50 and w.height > 50:
                windows.append({
                    "title": title,
                    "x": w.left,
                    "y": w.top,
                    "width": w.width,
                    "height": w.height,
                    "active": w.isActive,
                })
        return {"ok": True, "count": len(windows), "windows": windows}
    except Exception as exc:
        return {"ok": False, "error": f"Failed to list windows: {exc}"}


def focus_window(title_substr: str) -> Dict[str, Any]:
    """Brings the first matching window to the foreground."""
    if gw is None:
        return {"ok": False, "error": "pygetwindow is not installed"}

    try:
        target = title_substr.lower().strip()
        for w in gw.getAllWindows():
            if target in (w.title or "").lower():
                try:
                    w.activate()
                except Exception:
                    # Windows sometimes requires restore first
                    w.restore()
                    w.activate()
                return {"ok": True, "focused_title": w.title}
        return {"ok": False, "error": f"No window matching '{title_substr}' found"}
    except Exception as exc:
        return {"ok": False, "error": f"Failed to focus window: {exc}"}


def click_screen(x: int, y: int, button: str = "left", double: bool = False) -> Dict[str, Any]:
    """Clicks at coordinates (x, y) on the screen."""
    if pyautogui is None:
        return {"ok": False, "error": "pyautogui is not installed"}

    try:
        if double:
            pyautogui.doubleClick(x, y, button=button)
        else:
            pyautogui.click(x, y, button=button)
        return {"ok": True, "clicked": [x, y], "button": button}
    except Exception as exc:
        return {"ok": False, "error": f"Click failed: {exc}"}


def type_text(text: str, press_enter: bool = False) -> Dict[str, Any]:
    """Types text into the active focused control."""
    if pyautogui is None:
        return {"ok": False, "error": "pyautogui is not installed"}

    try:
        pyautogui.write(text, interval=0.02)
        if press_enter:
            pyautogui.press("enter")
        return {"ok": True, "typed_length": len(text), "pressed_enter": press_enter}
    except Exception as exc:
        return {"ok": False, "error": f"Type text failed: {exc}"}


def press_hotkey(keys: List[str]) -> Dict[str, Any]:
    """Presses a hotkey combination (e.g. ['ctrl', 's'] or ['alt', 'tab'])."""
    if pyautogui is None:
        return {"ok": False, "error": "pyautogui is not installed"}

    try:
        pyautogui.FAILSAFE = False
        if len(keys) == 1:
            pyautogui.press(keys[0])
        elif len(keys) > 1:
            pyautogui.hotkey(*keys)
        return {"ok": True, "keys": keys}
    except Exception as exc:
        return {"ok": False, "error": f"Hotkey failed: {exc}"}


def handle(cmd: Dict[str, Any]) -> Dict[str, Any]:
    """Central dispatch for computer use operations from PC agent."""
    op = (cmd.get("op") or cmd.get("action") or "").lower().strip()
    args = cmd.get("args")
    if not isinstance(args, dict):
        args = cmd

    if op == "screenshot":
        return get_screenshot(int(args.get("max_width", 1280)), int(args.get("quality", 60)))
    elif op in ("list_windows", "windows"):
        return list_windows()
    elif op in ("focus_window", "focus"):
        return focus_window(args.get("title") or args.get("window_title") or "")
    elif op == "click":
        return click_screen(int(args.get("x", 0)), int(args.get("y", 0)), args.get("button", "left"), bool(args.get("double", False)))
    elif op == "type":
        return type_text(args.get("text", ""), bool(args.get("enter", False)))
    elif op == "hotkey":
        keys = args.get("keys") or args.get("key") or []
        if isinstance(keys, str):
            keys = [k.strip() for k in keys.split("+")]
        return press_hotkey(keys)
    else:
        return {"ok": False, "error": f"Unknown computer use op: '{op}'"}
