"""Creative & Media -- domain module for the creative-media Chief
Domain Agent.

Wires blueprint.json to real tools, guardrails, and quality gates.
avishkar_agent itself never changes to support this agent.
"""

from __future__ import annotations

import dataclasses
import re
import statistics
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


def _count_words(text: str) -> int:
    return len(text.split())


def _analyze_pacing(text: str) -> str:
    """A real heuristic: variance in sentence length signals pacing.
    'choppy' (very short, uniform sentences), 'dense' (long sentences),
    'flowing' (varied length) -- not a certified stylometric measure.
    """
    sentences = [s for s in re.split(r"[.!?]+", text) if s.strip()]
    if len(sentences) < 2:
        return "unclear"
    lengths = [len(s.split()) for s in sentences]
    avg_len = statistics.mean(lengths)
    stdev = statistics.pstdev(lengths)
    if avg_len > 20:
        return "dense"
    if stdev < 2:
        return "choppy"
    return "flowing"


def _build_knowledge_base() -> KnowledgeBase:
    kb = KnowledgeBase()
    kb.ingest(
        "story-structure-basics",
        "A classic three-act structure sets up the situation, escalates "
        "through rising conflict, and resolves with a climax and "
        "denouement -- deviating from it should be a choice, not an accident.",
    )
    kb.ingest(
        "copy-editing-checklist",
        "Edit for clarity first, then concision, then voice consistency "
        "-- cutting an unnecessary word is almost always an improvement.",
    )
    return kb


def _build_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(Tool(name="count_words", call=_count_words, description="Real word count."))
    registry.register(Tool(name="analyze_pacing", call=_analyze_pacing, description="Sentence-length-variance pacing heuristic."))
    registry.register(as_tool(_build_knowledge_base(), name="search_craft_references", top_k=2))
    registry.register(MCPToolRef(server="unsplash", tool_name="search_stock_images"))
    return registry


# --- Guardrails ------------------------------------------------------------

_VERBATIM_REPRODUCTION_PATTERN = re.compile(
    r"\b(reproduce the full text of|give me the entire lyrics to|copy the whole chapter from)\b", re.IGNORECASE
)


def _no_verbatim_copyrighted_reproduction(task) -> Optional[str]:
    if _VERBATIM_REPRODUCTION_PATTERN.search(task.input):
        return "task requests verbatim reproduction of copyrighted material -- this agent helps create original work, not copy existing work"
    return None


def _build_guardrails() -> Tuple[Guardrail, ...]:
    return (
        make_secret_scanning_guardrail(),
        Guardrail(name="no-verbatim-copyrighted-reproduction", check=_no_verbatim_copyrighted_reproduction),
    )


# --- Quality gates -----------------------------------------------------------


def _minimum_substance(result) -> bool:
    return len(result.output.strip()) >= 10


def _build_quality_gates() -> Tuple[QualityGate, ...]:
    suite = EvalSuite(name="originality-note", cases=(EvalCase(inputs={}, expected=None),))
    scorer = weighted_keyword_scorer({"your own voice": 1.0, "original": 1.0, "starting point": 1.0})
    gate = make_quality_gate("includes-originality-note", suite, scorer, threshold=0.0)
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


def build_creative_media_agent(
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
