"""Startup, Business & Product -- domain module for the
startup-business-product Chief Domain Agent.

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

_PITCH_SECTIONS = {
    "problem": re.compile(r"\bproblem\b", re.IGNORECASE),
    "solution": re.compile(r"\bsolution\b", re.IGNORECASE),
    "market": re.compile(r"\bmarket\b", re.IGNORECASE),
    "ask": re.compile(r"\b(ask|raising|seeking)\b", re.IGNORECASE),
}

_LARGE_MARKET_PATTERN = re.compile(r"\b(billion|global|mass market|everyone)\b", re.IGNORECASE)
_NICHE_MARKET_PATTERN = re.compile(r"\b(niche|specific segment|small group|enthusiasts)\b", re.IGNORECASE)


def _score_pitch_clarity(text: str) -> Dict[str, bool]:
    """Real, checkable presence check for the four pitch sections a
    clear pitch typically states explicitly. Not a judgment of quality,
    only presence -- see README.md Limitations.
    """
    return {name: bool(pattern.search(text)) for name, pattern in _PITCH_SECTIONS.items()}


def _classify_market_size(description: str) -> str:
    """Keyword-based classification: 'large' | 'niche' | 'unclear'. A
    cheap heuristic signal, not a real market-sizing analysis.
    """
    if _LARGE_MARKET_PATTERN.search(description):
        return "large"
    if _NICHE_MARKET_PATTERN.search(description):
        return "niche"
    return "unclear"


def _build_knowledge_base() -> KnowledgeBase:
    kb = KnowledgeBase()
    kb.ingest(
        "prd-structure",
        "A good PRD states the problem, the target user, the proposed "
        "solution, success metrics, and explicit non-goals so scope "
        "stays bounded.",
    )
    kb.ingest(
        "pitch-deck-checklist",
        "A pitch deck should cover: problem, solution, market size, "
        "business model, traction, team, and a clear ask.",
    )
    return kb


def _build_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        Tool(name="score_pitch_clarity", call=_score_pitch_clarity, description="Check presence of core pitch sections.")
    )
    registry.register(
        Tool(name="classify_market_size", call=_classify_market_size, description="Keyword-based market-size classification.")
    )
    registry.register(as_tool(_build_knowledge_base(), name="search_startup_playbooks", top_k=2))
    registry.register(MCPToolRef(server="crunchbase", tool_name="get_company_data"))
    return registry


# --- Guardrails ------------------------------------------------------------

_BINDING_COMMITMENT_PATTERN = re.compile(
    r"\b(sign this term sheet|commit to hiring|accept this investment on my behalf)\b", re.IGNORECASE
)


def _no_binding_business_commitments(task) -> Optional[str]:
    if _BINDING_COMMITMENT_PATTERN.search(task.input):
        return "task requests a binding business commitment -- requires the founder's own decision, not this agent"
    return None


def _build_guardrails() -> Tuple[Guardrail, ...]:
    return (
        make_secret_scanning_guardrail(),
        Guardrail(name="no-binding-business-commitments", check=_no_binding_business_commitments),
    )


# --- Quality gates -----------------------------------------------------------


def _minimum_substance(result) -> bool:
    return len(result.output.strip()) >= 10


def _build_quality_gates() -> Tuple[QualityGate, ...]:
    suite = EvalSuite(name="not-financial-advice-note", cases=(EvalCase(inputs={}, expected=None),))
    scorer = weighted_keyword_scorer({"not financial advice": 1.0, "consult": 1.0, "your own judgment": 1.0})
    disclaimer_gate = make_quality_gate("includes-not-financial-advice-note", suite, scorer, threshold=0.0)
    return (
        QualityGate(name="minimum-substance", check=_minimum_substance),
        disclaimer_gate,
    )


# --- Construction -----------------------------------------------------------


def load_blueprint(model_override: Optional[str] = None) -> AgentBlueprint:
    blueprint = AgentBlueprint.from_file(_BLUEPRINT_PATH)
    if model_override is None:
        return blueprint
    return dataclasses.replace(blueprint, default_model=model_override)


def build_startup_business_product_agent(
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
