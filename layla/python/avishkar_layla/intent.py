"""IntentInterpreter. See CONTRACT.md SS13.

A real, pattern-based classifier -- the same honestly-scoped-heuristic
discipline as risk.classify_risk, not a model call.
"""

from __future__ import annotations

import dataclasses
import re

_QUESTION_PATTERN = re.compile(r"\?\s*$|^(what|why|how|when|where|who|is|are|can|could|should)\b", re.IGNORECASE)
_COMMAND_PATTERN = re.compile(r"^(please\s+)?(delete|deploy|send|create|update|remove|execute|run|cancel)\b", re.IGNORECASE)
_URGENT_PATTERN = re.compile(r"\b(urgent|asap|immediately|right away|critical|emergency)\b", re.IGNORECASE)
_HIGH_URGENCY_PATTERN = re.compile(r"\b(today|soon|quickly|as soon as possible)\b", re.IGNORECASE)
_ACTION_VERBS = re.compile(
    r"\b(build|create|send|deploy|update|schedule|delegate|research|delete|remove|fix|review|draft)\b",
    re.IGNORECASE,
)


@dataclasses.dataclass(frozen=True)
class Intent:
    category: str  # "question" | "command" | "request" | "information"
    urgency: str  # "low" | "normal" | "high" | "urgent"
    requires_action: bool


class IntentInterpreter:
    def interpret(self, text: str) -> Intent:
        stripped = text.strip()

        if _COMMAND_PATTERN.search(stripped):
            category = "command"
        elif _QUESTION_PATTERN.search(stripped):
            category = "question"
        elif _ACTION_VERBS.search(stripped):
            category = "request"
        else:
            category = "information"

        if _URGENT_PATTERN.search(stripped):
            urgency = "urgent"
        elif _HIGH_URGENCY_PATTERN.search(stripped):
            urgency = "high"
        elif category == "question":
            urgency = "low"
        else:
            urgency = "normal"

        requires_action = category in ("command", "request")

        return Intent(category=category, urgency=urgency, requires_action=requires_action)
