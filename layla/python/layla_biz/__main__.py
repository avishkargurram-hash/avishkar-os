"""Run: python -m layla_biz  (env: BIZ_DB, BIZ_TOKEN, BIZ_ADMIN_TOKEN, BIZ_PORT, BIZ_DIR, TELEGRAM_*)."""

import os
import sys

from layla_comms.notify import ConsoleNotifier, TelegramNotifier

from .admin import handle_command
from .config import Config
from .server import serve
from .store import BizStore
from .tools import Tools


def main() -> int:
    e = os.environ
    token, admin_token = e.get("BIZ_TOKEN", ""), e.get("BIZ_ADMIN_TOKEN", "")
    if len(token) < 24 or len(admin_token) < 24 or token == admin_token:
        print("BIZ_TOKEN and BIZ_ADMIN_TOKEN must be distinct long random strings", file=sys.stderr)
        return 2
    st = BizStore(e.get("BIZ_DB", "biz.db"))
    tg, chat = e.get("TELEGRAM_BOT_TOKEN"), e.get("TELEGRAM_CHAT_ID")
    notifier = TelegramNotifier(tg, chat) if tg and chat else ConsoleNotifier()
    tools = Tools(st, notifier, Config.from_env())
    srv = serve(tools, token, e.get("BIZ_HOST", "127.0.0.1"), int(e.get("BIZ_PORT", "8130")),
                admin_token, lambda text: handle_command(st, text))
    print(f"layla_biz listening on {srv.server_address}; tools {'ON' if st.enabled() else 'OFF'}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
