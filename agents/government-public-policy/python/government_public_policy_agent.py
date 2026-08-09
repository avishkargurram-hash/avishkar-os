"""Government & Public Policy -- domain module for the
government-public-policy Chief Domain Agent.

Wires blueprint.json to real tools, guardrails, and quality gates.
avishkar_agent itself never changes to support this agent.
"""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path
from typing import Dict, Optional, Tuple

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

_POLICY_SECTIONS = {
    "objective": re.compile(r"\bobjective\b", re.IGNORECASE),
    "stakeholders": re.compile(r"\bstakeholders?\b", re.IGNORECASE),
    "budget_impact": re.compile(r"\bbudget\b", re.IGNORECASE),
    "implementation_timeline": re.compile(r"\b(timeline|implementation)\b", re.IGNORECASE),
}

_FEDERAL_PATTERN = re.compile(r"\b(federal|congress|nationwide)\b", re.IGNORECASE)
_STATE_PATTERN = re.compile(r"\bstate (law|legislature|government)\b", re.IGNORECASE)
_LOCAL_PATTERN = re.compile(r"\b(city council|county|municipal|local ordinance)\b", re.IGNORECASE)


def _check_policy_structure(text: str) -> Dict[str, bool]:
    """Real, checkable presence check for four sections a well-formed
    policy proposal typically states explicitly. Not a judgment of
    quality -- see README.md Limitations.
    """
    return {name: bool(pattern.search(text)) for name, pattern in _POLICY_SECTIONS.items()}


def _classify_regulatory_scope(text: str) -> str:
    """Keyword-based classification: 'federal' | 'state' | 'local' |
    'unclear'. A cheap heuristic signal, not a jurisdictional analysis.
    """
    if _FEDERAL_PATTERN.search(text):
        return "federal"
    if _STATE_PATTERN.search(text):
        return "state"
    if _LOCAL_PATTERN.search(text):
        return "local"
    return "unclear"


def _build_knowledge_base() -> KnowledgeBase:
    kb = KnowledgeBase()
    kb.ingest(
        "policy-analysis-framework",
        "A sound policy analysis states the objective, identifies "
        "affected stakeholders, estimates budget impact, and proposes "
        "a realistic implementation timeline.",
    )
    kb.ingest(
        "public-comment-process",
        "Most regulatory changes go through a public comment period "
        "before finalization -- affected parties can submit input "
        "through the agency's official channel during that window.",
    )
    return kb


def _build_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        Tool(name="check_policy_structure", call=_check_policy_structure, description="Check presence of core policy-proposal sections.")
    )
    registry.register(
        Tool(name="classify_regulatory_scope", call=_classify_regulatory_scope, description="Keyword-based jurisdiction classification.")
    )
    registry.register(as_tool(_build_knowledge_base(), name="search_policy_references", top_k=2))
    registry.register(MCPToolRef(server="govinfo", tool_name="search_legislation"))
    return registry


# --- Guardrails ------------------------------------------------------------

_BINDING_RULING_PATTERN = re.compile(
    r"\b(issue an official ruling|speak on behalf of the agency|certify this as compliant)\b", re.IGNORECASE
)


def _no_issuing_binding_rulings(task) -> Optional[str]:
    if _BINDING_RULING_PATTERN.search(task.input):
        return "task requests a binding ruling/official representation -- requires the relevant agency, not this agent"
    return None


def _build_guardrails() -> Tuple[Guardrail, ...]:
    return (
        make_secret_scanning_guardrail(),
        Guardrail(name="no-issuing-binding-rulings", check=_no_issuing_binding_rulings),
    )


# --- Quality gates -----------------------------------------------------------


def _minimum_substance(result) -> bool:
    return len(result.output.strip()) >= 10


def _build_quality_gates() -> Tuple[QualityGate, ...]:
    suite = EvalSuite(name="official-channel-note", cases=(EvalCase(inputs={}, expected=None),))
    scorer = weighted_keyword_scorer({"official agency": 1.0, "public comment": 1.0, "your representative": 1.0})
    gate = make_quality_gate("includes-official-channel-note", suite, scorer, threshold=0.0)
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


def build_government_public_policy_agent(
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
