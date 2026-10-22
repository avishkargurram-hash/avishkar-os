"""Run: python -m layla_fin  (env: FIN_DB, FIN_ADMIN_TOKEN, FIN_PORT, ELEVENLABS_API_KEY, FIN_DIGEST_HOUR, TELEGRAM_*)."""

import os
import sys

from layla_comms.notify import ConsoleNotifier, TelegramNotifier

from .admin import handle_command
from .monitor import Monitor, MonitorThread
from .server import serve
from .store import FinStore


def main() -> int:
    e = os.environ
    admin_token = e.get("FIN_ADMIN_TOKEN", "")
    if len(admin_token) < 24:
        print("FIN_ADMIN_TOKEN must be a long random string", file=sys.stderr)
        return 2
    st = FinStore(e.get("FIN_DB", "fin.db"))
    tg, chat = e.get("TELEGRAM_BOT_TOKEN"), e.get("TELEGRAM_CHAT_ID")
    notifier = TelegramNotifier(tg, chat) if tg and chat else ConsoleNotifier()
    mon = Monitor(st, notifier, e.get("ELEVENLABS_API_KEY", ""), int(e.get("FIN_DIGEST_HOUR", "9")))
    MonitorThread(mon, int(e.get("FIN_INTERVAL_S", "900"))).start()
    srv = serve(lambda text: handle_command(st, text, mon), admin_token, e.get("FIN_HOST", "127.0.0.1"),
                int(e.get("FIN_PORT", "8140")))
    print(f"layla_fin admin on {srv.server_address}; elevenlabs poll {'ON' if mon.key else 'OFF'}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
