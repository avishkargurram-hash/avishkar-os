"""Owner commands for the Business channel: /biz on|off|status|leads. Reached via the
layla_wa Telegram controller, which owns the single getUpdates poller for the bot."""

from __future__ import annotations

from typing import Optional

from .store import BizStore

HELP = "/biz on - enable the Business agent tools\n/biz off - pause them immediately\n/biz status\n/biz leads"


def handle_command(st: BizStore, text: str) -> Optional[str]:
    t = text.strip()
    if not (t == "/biz" or t.startswith("/biz ") or t.startswith("/biz@")):
        return None
    parts = t.split(None, 1)
    cmd = (parts[1].strip().split()[0].lower() if len(parts) > 1 and parts[1].strip() else "")
    if cmd == "off":
        st.set_enabled(False)
        return ("Business agent tools are OFF. The ElevenLabs agent will tell people you'll reply personally. "
                "To stop it entirely also turn off 'Enable messaging' in the ElevenLabs WhatsApp account settings.")
    if cmd == "on":
        st.set_enabled(True)
        return "Business agent tools are ON."
    if cmd == "status":
        return f"Business agent tools: {'ON' if st.enabled() else 'OFF'}\nLeads captured: {len(st.recent_leads(1000))}"
    if cmd == "leads":
        rows = st.recent_leads(8)
        if not rows:
            return "No leads yet."
        return "\n".join(f"+{r['caller']} | {r['name'] or '-'} | {r['interest'] or '-'}"
                         f"{' | CALLBACK' if r['callback'] else ''}" for r in rows)
    return HELP
