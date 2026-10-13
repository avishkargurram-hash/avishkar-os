"""Research & Intelligence -- domain module for the research-intelligence
Chief Domain Agent (renamed from "Science" in the Execution Mode phase
list per ADR-0012 -- the same locked ADR-0007 roster seat).

Wires blueprint.json to real tools, guardrails, and quality gates.
avishkar_agent itself never changes to support this agent.
"""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path
from typing import Optional, Tuple

from avishkar_agent import (
    AgentBlueprint,
    ChiefDomainAgent,
    Guardrail,
    MCPToolRef,
    QualityGate,
    Tool,
    ToolRegistry,
)
from avishkar_agent.thinking import DEFAULT_THINKING_MODELS
from avishkar_evaluation import EvalCase, EvalSuite, make_quality_gate, weighted_keyword_scorer
from avishkar_knowledge import KnowledgeBase, as_tool
from avishkar_memory import build_memory_policy
from avishkar_router import Router
from avishkar_security import make_secret_scanning_guardrail

_BLUEPRINT_PATH = Path(__file__).resolve().parent.parent / "blueprint.json"

# --- Tools ---------------------------------------------------------------

_HIGH_RELIABILITY_PATTERN = re.compile(r"\b(peer-reviewed|randomized controlled trial|meta-analysis|primary source)\b", re.IGNORECASE)
_LOW_RELIABILITY_PATTERN = re.compile(r"\b(blog post|opinion piece|anonymous forum|unverified)\b", re.IGNORECASE)

_HEDGE_PATTERN = re.compile(r"\b(may|might|suggests?|preliminary|appears to|likely|possibly)\b", re.IGNORECASE)
_DEFINITIVE_PATTERN = re.compile(r"\b(proves?|definitively|certainly|without question)\b", re.IGNORECASE)


def _assess_source_reliability(source_description: str) -> str:
    """Keyword heuristic: 'high' | 'low' | 'medium'. A cheap signal, not
    a real citation-quality analysis. See README.md Limitations.
    """
    if _HIGH_RELIABILITY_PATTERN.search(source_description):
        return "high"
    if _LOW_RELIABILITY_PATTERN.search(source_description):
        return "low"
    return "medium"


def _extract_confidence_level(text: str) -> str:
    """'tentative' if hedge language is present, 'definitive' if
    unqualified certainty language is present (and no hedge), else
    'unstated'.
    """
    has_hedge = bool(_HEDGE_PATTERN.search(text))
    has_definitive = bool(_DEFINITIVE_PATTERN.search(text))
    if has_hedge:
        return "tentative"
    if has_definitive:
        return "definitive"
    return "unstated"


def _build_knowledge_base() -> KnowledgeBase:
    kb = KnowledgeBase()
    kb.ingest(
        "scientific-method-principles",
        "A finding is only as strong as its evidence: prefer "
        "reproducible, peer-reviewed results, state confidence "
        "explicitly, and distinguish correlation from causation.",
    )
    kb.ingest(
        "source-evaluation-criteria",
        "Evaluate a source on authority, currency, accuracy, and "
        "purpose (is it trying to inform or persuade) before citing it.",
    )
    return kb


def _build_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        Tool(name="assess_source_reliability", call=_assess_source_reliability, description="Heuristic source-reliability tier.")
    )
    registry.register(
        Tool(name="extract_confidence_level", call=_extract_confidence_level, description="Detect hedge vs definitive language.")
    )
    registry.register(as_tool(_build_knowledge_base(), name="search_research_literature", top_k=2))
    registry.register(MCPToolRef(server="semanticscholar", tool_name="search_papers"))
    return registry


# --- Guardrails ------------------------------------------------------------

_FABRICATION_PATTERN = re.compile(r"\b(make up a citation|invent a source|fabricate a study)\b", re.IGNORECASE)


def _no_fabricating_citations(task) -> Optional[str]:
    if _FABRICATION_PATTERN.search(task.input):
        return "task requests a fabricated citation/source -- this agent only cites real, verifiable sources"
    return None


def _build_guardrails() -> Tuple[Guardrail, ...]:
    return (
        make_secret_scanning_guardrail(),
        Guardrail(name="no-fabricating-citations", check=_no_fabricating_citations),
    )


# --- Quality gates -----------------------------------------------------------


def _minimum_substance(result) -> bool:
    return len(result.output.strip()) >= 10


def _build_quality_gates() -> Tuple[QualityGate, ...]:
    suite = EvalSuite(name="confidence-qualifier", cases=(EvalCase(inputs={}, expected=None),))
    scorer = weighted_keyword_scorer({"suggests": 1.0, "preliminary": 1.0, "evidence indicates": 1.0})
    gate = make_quality_gate("includes-confidence-qualifier", suite, scorer, threshold=0.0)
    return (
        QualityGate(name="minimum-substance", check=_minimum_substance),
        gate,
    )


# --- Construction -----------------------------------------------------------


def load_blueprint(model_override: Optional[str] = None) -> AgentBlueprint:
    blueprint = AgentBlueprint.from_file(_BLUEPRINT_PATH)
    if model_override is None:
        return blueprint
    return dataclasses.replace(blueprint, default_model=model_override)


def build_research_intelligence_agent(
    router: Router, *, model_override: Optional[str] = None, memory_db_path: str = ":memory:"
) -> ChiefDomainAgent:
    blueprint = load_blueprint(model_override)
    memory = build_memory_policy(blueprint.memory_policy, db_path=memory_db_path)
    return ChiefDomainAgent(
        blueprint=blueprint,
        router=router,
        memory=memory,
        tools=_build_tool_registry(),
        thinking_models=DEFAULT_THINKING_MODELS,
        guardrails=_build_guardrails(),
        quality_gates=_build_quality_gates(),
    )
