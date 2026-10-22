"""Webhook tools called by the ElevenLabs agent. Every answer returned here is either
approved knowledge or a fixed phrase, so the agent never has to invent business facts."""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, List

from .config import Config
from .store import BizStore

PAUSED = ("The owner has paused automated replies. Tell the person: 'Thanks for reaching out - "
          "Avishkar will reply to you personally.' Do not say anything else about the business.")
NOT_STATED = ("That detail is not in the approved information. Tell the person: 'I don't have that detail - "
              "Avishkar will confirm it with you personally.' Do not guess.")
CALLBACK_NOTED = ("Noted. Tell the person: 'Thanks - Avishkar will get back to you personally to confirm the details.' "
                  "Do not promise any time, price or availability.")
RATE_LIMITED = "Too many requests. Tell the person Avishkar will reply personally."

TOPICS = {
    "home": re.compile(r"home|automat|switch|smart|retrofit|tryvanta|light|fan|appliance", re.I),
    "music": re.compile(r"music|piano|keyboard|trinity|class|lesson|grade|exam|academy|learn", re.I),
}
_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def clean(v: Any, n: int = 300) -> str:
    return _CTRL.sub(" ", str(v or "")).strip()[:n]


def digits(v: Any) -> str:
    return re.sub(r"\D", "", str(v or ""))[:20]


def parse_knowledge(text: str) -> Dict[str, Any]:
    """Blocks are blank-line separated. First line is the title; the block that starts with
    'Not stated' is the never-state guard."""
    sections: List[Dict[str, Any]] = []
    guard = ""
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue
        if lines[0].lower().startswith("not stated"):
            guard = " ".join(lines)
            continue
        sections.append({"title": lines[0], "facts": [ln.lstrip("- ").strip() for ln in lines[1:]]})
    return {"sections": sections, "guard": guard}


class Tools:
    def __init__(self, st: BizStore, notifier, cfg: Config, clock: Callable[[], float] = None):
        self.st, self.notifier, self.cfg = st, notifier, cfg
        self.kn = parse_knowledge(cfg.knowledge)

    # ---- helpers --------------------------------------------------------
    def _notify(self, text: str) -> None:
        try:
            self.notifier.send(text)
        except Exception as e:
            self.st.audit("notify_error", {"err": str(e)[:200]})

    def _gate(self, caller: str, tool: str) -> str:
        """Return a refusal message, or '' if the call may proceed."""
        if not self.st.enabled():
            self.st.audit("biz_blocked", {"tool": tool, "why": "disabled"})
            return PAUSED
        now = self.st.clock()
        if (self.st.calls_since(now - 3600, caller) >= self.cfg.per_caller_per_hour
                or self.st.calls_since(now - 3600) >= self.cfg.global_per_hour):
            self.st.audit("biz_blocked", {"tool": tool, "why": "rate"})
            return RATE_LIMITED
        self.st.note_call(caller, tool)
        return ""

    # ---- conversation initiation webhook --------------------------------
    def init_vars(self, d: Dict[str, Any]) -> Dict[str, Any]:
        """Must always return every dynamic variable the agent prompt uses."""
        caller = digits(d.get("caller_id"))
        lead = self.st.get_lead(caller) if caller else {}
        return {"type": "conversation_initiation_client_data", "dynamic_variables": {
            "caller_id": caller or "unknown",
            "owner_name": self.cfg.owner_name,
            "business_name": self.cfg.business_name,
            "is_returning_lead": "yes" if lead else "no",
            "lead_name": lead.get("name") or "unknown",
            "automation_status": "on" if self.st.enabled() else "paused",
        }}

    # ---- tools ----------------------------------------------------------
    def get_offering(self, d: Dict[str, Any]) -> Dict[str, Any]:
        caller = digits(d.get("caller_id"))
        refusal = self._gate(caller, "get_offering")
        if refusal:
            return {"ok": False, "message": refusal}
        topic = clean(d.get("topic"), 120)
        keys = [k for k, rx in TOPICS.items() if rx.search(topic)]
        picked = [s for s in self.kn["sections"]
                  if any((k == "home" and "home" in s["title"].lower()) or
                         (k == "music" and ("music" in s["title"].lower() or "trinity" in s["title"].lower()))
                         for k in keys)]
        if not picked:
            return {"ok": True, "found": False, "message": NOT_STATED,
                    "available_topics": [s["title"] for s in self.kn["sections"]]}
        return {"ok": True, "found": True, "offerings": picked, "never_state": self.kn["guard"],
                "instruction": "State only these facts. For anything else use the not-stated phrase."}

    def capture_lead(self, d: Dict[str, Any]) -> Dict[str, Any]:
        caller = digits(d.get("caller_id"))
        refusal = self._gate(caller, "capture_lead")
        if refusal:
            return {"ok": False, "message": refusal}
        if not caller:
            return {"ok": False, "message": "Missing caller_id."}
        fields = {"name": clean(d.get("name"), 80), "phone": digits(d.get("phone")) or caller,
                  "interest": clean(d.get("interest"), 120), "details": clean(d.get("details"), 400),
                  "preferred_time": clean(d.get("preferred_time"), 120)}
        changed = self.st.upsert_lead(caller, fields)
        self.st.audit("biz_lead", {"caller": caller, "changed": changed})
        if changed:
            lead = self.st.get_lead(caller)
            self._notify(self._lead_text("[Lead]", caller, lead))
        return {"ok": True, "message": CALLBACK_NOTED}

    def request_callback(self, d: Dict[str, Any]) -> Dict[str, Any]:
        caller = digits(d.get("caller_id"))
        refusal = self._gate(caller, "request_callback")
        if refusal:
            return {"ok": False, "message": refusal}
        if not caller:
            return {"ok": False, "message": "Missing caller_id."}
        fields = {"name": clean(d.get("name"), 80), "phone": digits(d.get("phone")) or caller,
                  "interest": clean(d.get("interest"), 120), "details": clean(d.get("details"), 400),
                  "preferred_time": clean(d.get("preferred_time"), 120)}
        changed = self.st.upsert_lead(caller, fields, callback=True)
        self.st.audit("biz_callback", {"caller": caller})
        if changed:
            self._notify(self._lead_text("[Callback requested]", caller, self.st.get_lead(caller)))
        return {"ok": True, "message": CALLBACK_NOTED}

    def escalate(self, d: Dict[str, Any]) -> Dict[str, Any]:
        caller = digits(d.get("caller_id"))
        refusal = self._gate(caller, "escalate_to_owner")
        if refusal:
            return {"ok": False, "message": refusal}
        reason = clean(d.get("reason"), 300) or "no reason given"
        self.st.audit("biz_escalate", {"caller": caller, "reason": reason})
        self._notify(f"[Needs you] WhatsApp Business +{caller or '?'}: {reason}")
        return {"ok": True, "message": "Tell the person: 'Avishkar will reply to you personally.'"}

    @staticmethod
    def _lead_text(tag: str, caller: str, lead: Dict[str, Any]) -> str:
        parts = [f"{tag} WhatsApp Business +{caller}"]
        for label, key in (("Name", "name"), ("Interest", "interest"), ("Details", "details"),
                           ("Preferred time", "preferred_time"), ("Phone", "phone")):
            if lead.get(key):
                parts.append(f"{label}: {lead[key]}")
        return "\n".join(parts)
