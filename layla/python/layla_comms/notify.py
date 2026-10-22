"""Owner notification channel. Telegram bot if configured, else stdout."""

from __future__ import annotations

import json
import urllib.request


class ConsoleNotifier:
    def send(self, text: str) -> None:
        print(text)


class TelegramNotifier:
    def __init__(self, token: str, chat_id: str):
        self._url = f"https://api.telegram.org/bot{token}/sendMessage"
        self._chat = chat_id

    def send(self, text: str) -> None:
        body = json.dumps({"chat_id": self._chat, "text": text[:4000]}).encode()
        req = urllib.request.Request(self._url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            if r.status != 200:
                raise RuntimeError(f"telegram status {r.status}")
