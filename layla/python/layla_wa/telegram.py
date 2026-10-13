"""Telegram control channel: /wa on|off|status, group and mute management.
Only the owner's chat id is obeyed; every other sender is ignored."""

from __future__ import annotations

import json
import threading
import time
import urllib.parse
import urllib.request
from typing import Callable, List, Optional, Tuple

from .store import WaStore

HELP = ("/wa on - start auto-replies\n/wa off - stop immediately\n/wa status\n"
        "/wa group add|remove <group name>, /wa group list\n"
        "/wa mute|unmute <contact name>, /wa muted")


def handle_command(st: WaStore, text: str) -> Optional[str]:
    """Return the reply text for a /wa command, or None if it is not one."""
    t = text.strip()
    if not (t == "/wa" or t.startswith("/wa ") or t.startswith("/wa@")):
        return None
    parts = t.split(None, 1)
    rest = parts[1].strip() if len(parts) > 1 else ""
    cmd, _, arg = rest.partition(" ")
    cmd, arg = cmd.lower(), arg.strip()
    if cmd == "off":
        st.set_enabled(False)
        return "WhatsApp auto-reply is OFF. Queued replies will be blocked too."
    if cmd == "on":
        st.set_enabled(True)
        return "WhatsApp auto-reply is ON."
    if cmd == "status":
        return (f"WhatsApp auto-reply: {'ON' if st.enabled() else 'OFF'}\n"
                f"Groups: {', '.join(st.groups()) or 'none'}\nMuted: {', '.join(st.muted()) or 'none'}")
    if cmd == "group":
        sub, _, name = arg.partition(" ")
        sub, name = sub.lower(), name.strip()
        if sub == "list":
            return "Allowed groups: " + (", ".join(st.groups()) or "none")
        if sub == "add" and name:
            st.add_group(name)
            return f"Group added: {name.lower()}"
        if sub == "remove" and name:
            return f"Group removed: {name.lower()}" if st.remove_group(name) else "That group was not in the list."
        return "Usage: /wa group add|remove <name> | /wa group list"
    if cmd == "mute" and arg:
        st.mute(arg)
        return f"Muted: {arg.lower()}"
    if cmd == "unmute" and arg:
        return f"Unmuted: {arg.lower()}" if st.unmute(arg) else "That name was not muted."
    if cmd == "muted":
        return "Muted: " + (", ".join(st.muted()) or "none")
    return HELP


def forward_command(url: str, token: str, text: str) -> str:
    """Relay an owner command to a sibling service's loopback admin endpoint."""
    req = urllib.request.Request(url, data=json.dumps({"text": text}).encode(),
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read()).get("reply") or "(no reply)"
    except Exception as e:
        return f"That service is not reachable: {str(e)[:80]}"


class Controller(threading.Thread):
    """forwards: {"/biz": (admin_url, admin_token)} - one Telegram poller serves every Layla service."""

    def __init__(self, st: WaStore, token: str, owner_chat: str,
                 http: Optional[Callable[[str], dict]] = None,
                 forwards: Optional[dict] = None,
                 forwarder: Callable[[str, str, str], str] = forward_command):
        super().__init__(daemon=True)
        self.st, self.token, self.owner = st, token, str(owner_chat)
        self._http = http or self._real_http
        self.forwards = forwards or {}
        self._forwarder = forwarder
        self.stop_flag = threading.Event()

    def _route(self, text: str) -> Optional[str]:
        reply = handle_command(self.st, text)
        if reply is not None:
            return reply
        first = text.strip().split(None, 1)[0].split("@")[0] if text.strip() else ""
        if first in self.forwards:
            url, tok = self.forwards[first]
            return self._forwarder(url, tok, text)
        return None

    def _real_http(self, url: str) -> dict:
        with urllib.request.urlopen(url, timeout=40) as r:
            return json.loads(r.read())

    def _api(self, method: str, **params) -> dict:
        q = urllib.parse.urlencode(params)
        return self._http(f"https://api.telegram.org/bot{self.token}/{method}?{q}")

    def poll_once(self) -> int:
        off = int(self.st.get_setting("tg:offset", "0") or 0)
        data = self._api("getUpdates", offset=off, timeout=25)
        done = 0
        for u in data.get("result", []):
            self.st.set_setting("tg:offset", str(u["update_id"] + 1))
            m = u.get("message") or {}
            if str((m.get("chat") or {}).get("id", "")) != self.owner:
                continue
            reply = self._route(m.get("text") or "")
            if reply:
                self._api("sendMessage", chat_id=self.owner, text=reply[:4000])
                done += 1
        return done

    def run(self) -> None:
        backoff = 2
        while not self.stop_flag.is_set():
            try:
                self.poll_once()
                backoff = 2
            except Exception as e:
                self.st.audit("tg_poll_error", {"err": str(e)[:200]})
                self.stop_flag.wait(backoff)
                backoff = min(backoff * 2, 60)
