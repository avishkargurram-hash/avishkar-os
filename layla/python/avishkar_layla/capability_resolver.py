"""CapabilityResolver -- inspection-before-dispatch matching. See
CONTRACT.md SS5.

Applies the same matching policy avishkar_agent.Orchestrator._match_one
uses internally (exact agent name, else domain substring) but as a
small, standalone, real matcher a Planner can call *before* committing
to a PlanStep -- Orchestrator itself only exposes agent names via
list_agents(), not domains, so this works from an explicit mapping the
caller already has (the same ChiefDomainAgent instances used to build
the Orchestrator).
"""

from __future__ import annotations

import re
from typing import Mapping, Tuple

_WORD_PATTERN = re.compile(r"[a-z0-9]+")


def _words(text: str) -> Tuple[str, ...]:
    return tuple(_WORD_PATTERN.findall(text.lower()))


class CapabilityResolver:
    def __init__(self, agent_domains: Mapping[str, str]) -> None:
        self._agent_domains = dict(agent_domains)

    @property
    def known_capabilities(self) -> Tuple[str, ...]:
        return tuple(self._agent_domains.keys())

    def infer_relevant(self, text: str) -> Tuple[str, ...]:
        """Which known agent names are plausibly relevant to free text --
        real whole-word overlap between `text` and each agent's own
        name/domain words, not a model call. A real, honestly-scoped
        heuristic (same discipline as every other keyword classifier in
        this platform, e.g. medical-healthcare's flag_urgency) -- see
        README.md Limitations for its ceiling: it will miss a relevant
        agent whose domain words don't literally appear in the text.

        Matching is whole-word (via a tokenized set), not substring --
        a substring check would let short tokens like "ai" (from
        "software-ai-engineering") false-positive-match inside an
        unrelated word like "domain"; caught by this module's own test
        suite, not asserted away.
        """
        text_words = set(_words(text))
        matches = []
        for name, domain in self._agent_domains.items():
            name_words = set(_words(name))
            domain_words = {w for w in _words(domain) if len(w) > 3}
            if name_words & text_words or domain_words & text_words:
                matches.append(name)
        return tuple(matches)

    def match(self, required_capability: str) -> Tuple[str, ...]:
        normalized = required_capability.lower().replace("-", " ")
        if normalized in {name.lower().replace("-", " ") for name in self._agent_domains}:
            # Exact name match (post-normalization) wins outright, same
            # precedence Orchestrator._match_one gives it.
            for name in self._agent_domains:
                if name.lower().replace("-", " ") == normalized:
                    return (name,)
        return tuple(
            name for name, domain in self._agent_domains.items()
            if normalized in domain.lower()
        )
