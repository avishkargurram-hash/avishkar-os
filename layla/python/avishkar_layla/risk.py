"""Risk classification. See CONTRACT.md SS4.

A real, pattern-based classifier -- deterministic and auditable, not a
model call. The same honestly-scoped-heuristic discipline every Chief
Domain Agent's own tools use (e.g. medical-healthcare's flag_urgency).
"""

from __future__ import annotations

import re

from .types import RISK_HIGH, RISK_LOW, RISK_MEDIUM

_HIGH_RISK_PATTERNS = re.compile(
    r"\b(wire transfer|financial transaction|sign(ing)? (a |the )?contract|"
    r"legal commitment|force push|drop table|delete (the )?production|"
    r"production deploy|deploy to production|delete .*(repository|database)|"
    r"revoke access|change security|rotate (all )?credentials|terminate employee)\b",
    re.IGNORECASE,
)
_MEDIUM_RISK_PATTERNS = re.compile(
    r"\b(send (an? )?email|create (a |the )?calendar event|schedule (a |the )?meeting|"
    r"update project|modify (project )?metadata|post to slack|send a message)\b",
    re.IGNORECASE,
)


def classify_risk(action_description: str, action_kind: str = "") -> str:
    """Classifies an action LOW/MEDIUM/HIGH from its description. See
    Part XIII's worked examples -- these patterns are drawn directly
    from them, not invented independently.
    """
    text = f"{action_description} {action_kind}"
    if _HIGH_RISK_PATTERNS.search(text):
        return RISK_HIGH
    if _MEDIUM_RISK_PATTERNS.search(text):
        return RISK_MEDIUM
    return RISK_LOW
