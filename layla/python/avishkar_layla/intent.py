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
    r"\b(build|create|send|deploy|update|schedule|delegate|research|delete|remove|fix|review|draft"
    r"|remind|alarm|message|search|open|launch|turn on|turn off|look up|check status"
    r"|take (a )?(picture|photo))\b",
    re.IGNORECASE,
)
# "call" and "dial" are deliberately NOT in _ACTION_VERBS (2026-09-07): no
# real capability exists anywhere in this stack for either -- confirmed
# directly in PhoneAgentAdapter's own source, which documents "no SMS, no
# call, no location, no contacts" as a deliberate privacy scope, not an
# unwired capability. Before this fix, "call"/"dial" matched here, forcing
# requires_action=True, which sent ordinary sentences ("call me sir",
# "don't call me sir, use my name") toward Planner/CapabilityResolver
# instead of conversation -- CapabilityResolver's own domain vocabulary
# doesn't mention "call"/"dial" either, so the result was never a
# successful action, only a dead-end REQUIRES_HUMAN that a real, working
# capability would have earned honestly. Removing them lets these phrases
# reach the conversational path instead, where the vastly more common
# real-world sense of "call" ("call me sir" = a form of address, not a
# phone request) is actually handled -- and if a user genuinely asks
# Layla to place a call, she can now say so honestly in conversation
# instead of surfacing a cryptic internal error. If real phone-dialing is
# ever built (a real Android capability, not a text fix), "call"/"dial"
# belong back here as part of that same change, not before.


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
