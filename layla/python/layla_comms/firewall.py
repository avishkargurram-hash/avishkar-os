"""Injection firewall: everything untrusted passes through here before a
model sees it.

This module is one layer of several, and it is deliberately NOT the main
defence. Pattern matching can always be evaded; the real guarantees come
from the structure around it (the model has no tools, output is parsed
against a strict schema, and every side effect is gated in effects.py).
What this layer buys: hidden/invisible text is removed so the model sees
roughly what a human sees, input is size-capped, and obvious attack
attempts raise a flag that makes policy refuse to automate that message.
"""

from __future__ import annotations

import re
import secrets
from html.parser import HTMLParser
from typing import List, Tuple

from .types import CleanMessage, InboundMessage

MAX_BODY = 6000
MAX_SUBJECT = 300
MAX_NAME = 100

_INVISIBLE = dict.fromkeys(
    map(ord, "​‌‍⁠﻿­"
        "‪‫‬‭‮⁦⁧⁨⁩"),
    None,
)
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_VOID = {"br", "hr", "img", "input", "meta", "link", "area", "base", "col", "wbr"}
_BLOCK = {"p", "div", "tr", "li", "br", "h1", "h2", "h3", "h4", "table"}
_HIDDEN_STYLE = re.compile(
    r"display\s*:\s*none|visibility\s*:\s*hidden|font-size\s*:\s*0|opacity\s*:\s*0"
    r"|color\s*:\s*(?:#fff(?:fff)?|white)\b",
    re.I,
)

INJECTION_PATTERNS = {
    "ignore_instructions": r"ignore\s+(?:all\s+|any\s+|the\s+)?(?:previous|prior|above|earlier)\s+(?:instructions?|prompts?|rules)",
    "disregard": r"disregard\s+(?:all\s+|any\s+|the\s+)?(?:previous|prior|above|your)",
    "role_override": r"you\s+are\s+now\s+(?:a|an|the|in)\b|act\s+as\s+(?:a|an|the)\s+(?:system|admin|developer)",
    "system_prompt": r"\bsystem\s+prompt\b|\bdeveloper\s+(?:message|mode)\b",
    "chat_markers": r"<\|im_(?:start|end)\|>|\[/?INST\]|^\s*(?:system|assistant)\s*:",
    "tool_request": r"\b(?:run|execute)\s+(?:the\s+following|this)\s+(?:command|code|script)\b",
    "exfiltration": r"\b(?:forward|send|email)\s+(?:all|every|the\s+entire)\b.{0,60}\b(?:emails?|messages?|inbox|contacts|passwords?)\b",
    "addresses_the_ai": (
        r"\bif\s+you(?:'re|\s+are)\s+(?:an?\s+|the\s+)?(?:ai|a\.i\.|assistant|llm|chatbot|language\s+model)\b"
        r"|\b(?:dear|hey|hello|attention|note\s+to)\s+(?:the\s+)?(?:ai|assistant|llm|chatbot|language\s+model)\b"
        r"|\b(?:ai|assistant|llm|chatbot|language\s+model)s?\s+(?:reading|processing|summari[sz]ing|reviewing|triaging)\s+(?:this|the)\s+(?:email|message|mail)\b"
        r"|\b(?:ai|assistant|llm)\s*(?:agent)?\s*[:,]\s*(?:you\s+(?:must|should|need\s+to)|please)\b"
    ),
    "secret_request": r"\b(?:reveal|print|show|output)\b.{0,30}\b(?:api\s*key|password|secret|token|credentials)\b",
}
_COMPILED = {k: re.compile(v, re.I | re.M | re.S) for k, v in INJECTION_PATTERNS.items()}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: List[str] = []
        self._stack: List[Tuple[str, bool]] = []

    def _hidden(self) -> bool:
        return any(h for _, h in self._stack)

    def handle_starttag(self, tag, attrs):
        if tag in _BLOCK:
            self.out.append("\n")
        if tag in _VOID:
            return
        style = dict(attrs).get("style") or ""
        hidden = tag in ("script", "style", "head", "template") or bool(
            _HIDDEN_STYLE.search(style) or dict(attrs).get("hidden") is not None
        )
        self._stack.append((tag, hidden))

    def handle_endtag(self, tag):
        for i in range(len(self._stack) - 1, -1, -1):
            if self._stack[i][0] == tag:
                del self._stack[i:]
                break

    def handle_data(self, data):
        if not self._hidden():
            self.out.append(data)


def html_to_text(html: str) -> str:
    p = _TextExtractor()
    try:
        p.feed(html)
        p.close()
    except Exception:
        return ""
    return "".join(p.out)


def _normalise(text: str) -> str:
    text = text.translate(_INVISIBLE)
    text = _CONTROL.sub("", text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    return text.strip()


def scan(*texts: str) -> Tuple[str, ...]:
    hits = []
    blob = "\n".join(texts)
    for name, rx in _COMPILED.items():
        if rx.search(blob):
            hits.append(name)
    return tuple(hits)


def clean(msg: InboundMessage) -> CleanMessage:
    """Plain text preferred; HTML is only used when there is no plain part,
    and then with hidden elements removed."""
    raw_body = msg.body_plain.strip() or html_to_text(msg.body_html)
    body = _normalise(raw_body)[:MAX_BODY]
    subject = _normalise(msg.subject)[:MAX_SUBJECT]
    name = _normalise(msg.sender_name)[:MAX_NAME]
    # Scan the pre-truncation text and the raw HTML too: hidden text is
    # stripped from `body`, but the attempt itself is worth flagging.
    hits = scan(subject, name, _normalise(raw_body), _normalise(msg.body_html))
    return CleanMessage(
        msg_id=msg.msg_id,
        sender_email=msg.sender_email.strip().lower(),
        sender_name=name,
        subject=subject,
        body=body,
        injection_hits=hits,
    )


def fence(msg: CleanMessage) -> str:
    """Wrap untrusted content in per-call random delimiters the sender
    cannot predict, so it cannot close the data block early."""
    tag = "UNTRUSTED_" + secrets.token_hex(8)
    return (
        f"<<<{tag}\n"
        f"From: {msg.sender_name} <{msg.sender_email}>\n"
        f"Subject: {msg.subject}\n\n"
        f"{msg.body}\n"
        f"{tag}>>>"
    )
