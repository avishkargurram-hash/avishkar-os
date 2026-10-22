"""Run: python -m layla_wa  (env: WA_DB, WA_TOKEN, WA_PORT, LLM_*, TELEGRAM_*, WA_DIR)."""

import os
import sys

from layla_comms.llm import openai_compatible
from layla_comms.notify import ConsoleNotifier, TelegramNotifier

from .config import Config
from .engine import Engine
from .server import serve
from .store import WaStore
from .telegram import Controller


def main() -> int:
    e = os.environ
    token = e.get("WA_TOKEN", "")
    if len(token) < 24:
        print("WA_TOKEN must be set to a long random string", file=sys.stderr)
        return 2
    st = WaStore(e.get("WA_DB", "wa.db"))
    tg_token, chat = e.get("TELEGRAM_BOT_TOKEN"), e.get("TELEGRAM_CHAT_ID")
    notifier = TelegramNotifier(tg_token, chat) if tg_token and chat else ConsoleNotifier()
    complete = openai_compatible(e["LLM_BASE_URL"], e["LLM_API_KEY"], e["LLM_MODEL"])
    engine = Engine(st, complete, notifier, Config.from_env())
    if tg_token and chat:
        fwd = {}
        if e.get("BIZ_ADMIN_URL") and e.get("BIZ_ADMIN_TOKEN"):
            fwd["/biz"] = (e["BIZ_ADMIN_URL"], e["BIZ_ADMIN_TOKEN"])
        if e.get("FIN_ADMIN_URL") and e.get("FIN_ADMIN_TOKEN"):
            fwd["/fin"] = (e["FIN_ADMIN_URL"], e["FIN_ADMIN_TOKEN"])
        Controller(st, tg_token, chat, forwards=fwd).start()
    srv = serve(engine, token, e.get("WA_HOST", "127.0.0.1"), int(e.get("WA_PORT", "8120")))
    print(f"layla_wa listening on {srv.server_address}; auto-reply {'ON' if st.enabled() else 'OFF'}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
