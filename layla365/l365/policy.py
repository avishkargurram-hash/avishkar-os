"""Action policy: which tier applies to an action kind.

Tiers: A1 auto+logged | A2 auto within caps | A3 needs human approval | A4 never.
The agent registry (agents.yaml) sets a base tier; HARD_RULES can only make it
STRICTER, so an edit to agents.yaml can never silently unlock money or external
sends. Unknown kinds default to A3.
"""

ORDER = {"A1": 1, "A2": 2, "A3": 3, "A4": 4}

# (kind prefix, minimum tier) -- enforced at the action layer for EVERY agent.
# Owner decision 2026-10-12: "nothing is gated beyond payments". Everything else (deploys, deletes,
# device locks...) runs autonomously inside its per-day caps. Messages to outside people stay gated
# only because no executor exists for them yet (the WhatsApp phone agent has its own tap-to-allow).
HARD_RULES = [
    ("money.", "A3"),            # any money movement or order: human confirms
    ("comm.external.", "A3"),
]

DEFAULT_UNKNOWN = "A3"


def effective_tier(agent_actions: dict, kind: str) -> str:
    tier = agent_actions.get(kind, DEFAULT_UNKNOWN)
    for prefix, minimum in HARD_RULES:
        if kind.startswith(prefix) and ORDER[minimum] > ORDER[tier]:
            tier = minimum
    return tier
