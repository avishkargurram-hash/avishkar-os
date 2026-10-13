"""Orchestrator -- the 11th, coordinating seat in ADR-0007's locked
Chief Domain Agent roster (called "Executive Orchestrator" in the
Execution Mode phase list; ADR-0012 confirms this is a cosmetic rename
of the same locked seat, not a new one).

Unlike the 10 domain agents, the Orchestrator is not itself built from
an AgentBlueprint running its own reasoning loop -- it composes the
real avishkar_agent.Orchestrator (built in Phase 3) over instances of
all 10 domain agents. There is deliberately no blueprint.json here:
AgentBlueprint describes a single reasoning agent's mission/tools/
guardrails, and the Orchestrator has none of those itself -- it only
knows about registered ChiefDomainAgent instances and named strategies
(ARCHITECTURE.md SS1). See README.md SS1 for why this isn't an
oversight.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, Optional

from avishkar_agent import ChiefDomainAgent, Orchestrator
from avishkar_router import Router

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_AGENT_PACKAGE_DIRS = (
    "agents/software-ai-engineering/python",
    "agents/medical-healthcare/python",
    "agents/legal-compliance/python",
    "agents/startup-business-product/python",
    "agents/education-knowledge/python",
    "agents/research-intelligence/python",
    "agents/finance-economics/python",
    "agents/government-public-policy/python",
    "agents/human-development-psychology/python",
    "agents/creative-media/python",
)


def _ensure_domain_agent_packages_importable() -> None:
    """Each domain agent's package (e.g. `medical_healthcare_agent`) is
    a standalone top-level module named after its folder, not a
    sub-package of this one -- consistent with how every other agent's
    own examples/tests already add their single package to sys.path.
    Composing all 10 means adding all 10 directories, done once, here,
    rather than duplicated in every caller.
    """
    for rel in _AGENT_PACKAGE_DIRS:
        path = str(_ROOT / rel)
        if path not in sys.path:
            sys.path.insert(0, path)


def build_all_domain_agents(router: Router, *, model_override: Optional[str] = None) -> Dict[str, ChiefDomainAgent]:
    """Builds a fresh instance of all 10 domain agents, each with its
    own real integration (memory backend, knowledge base, guardrails,
    quality gates) exactly as documented in its own README. Returns a
    dict keyed by agent name for direct access alongside the
    Orchestrator itself.
    """
    _ensure_domain_agent_packages_importable()

    from creative_media_agent import build_creative_media_agent
    from education_knowledge_agent import build_education_knowledge_agent
    from finance_economics_agent import build_finance_economics_agent
    from government_public_policy_agent import build_government_public_policy_agent
    from human_development_psychology_agent import build_human_development_psychology_agent
    from legal_compliance_agent import build_legal_compliance_agent
    from medical_healthcare_agent import build_medical_healthcare_agent
    from research_intelligence_agent import build_research_intelligence_agent
    from software_ai_engineering_agent import build_software_ai_engineering_agent
    from startup_business_product_agent import build_startup_business_product_agent

    agents = (
        build_software_ai_engineering_agent(router, model_override=model_override),
        build_medical_healthcare_agent(router, model_override=model_override),
        build_legal_compliance_agent(router, model_override=model_override),
        build_startup_business_product_agent(router, model_override=model_override),
        build_education_knowledge_agent(router, model_override=model_override),
        build_research_intelligence_agent(router, model_override=model_override),
        build_finance_economics_agent(router, model_override=model_override),
        build_government_public_policy_agent(router, model_override=model_override),
        build_human_development_psychology_agent(router, model_override=model_override),
        build_creative_media_agent(router, model_override=model_override),
    )
    return {agent.name: agent for agent in agents}


def build_executive_orchestrator(router: Router, *, model_override: Optional[str] = None) -> Orchestrator:
    """Constructs the real avishkar_agent.Orchestrator (Phase 3) over
    all 10 domain agents. This is the entire "Orchestrator" Chief
    Domain Agent -- composition, not a new reasoning engine.
    """
    domain_agents = build_all_domain_agents(router, model_override=model_override)
    return Orchestrator(agents=tuple(domain_agents.values()))
