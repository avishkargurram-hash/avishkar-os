"""Education & Knowledge -- domain module for the education-knowledge
Chief Domain Agent.

Wires blueprint.json to real tools, guardrails, and quality gates.
avishkar_agent itself never changes to support this agent.
"""

from __future__ import annotations

import dataclasses
import re
import tempfile
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

_BLOOM_VERBS = re.compile(
    r"\b(explain|analyze|describe|evaluate|apply|create|compare|summarize)\b", re.IGNORECASE
)


def _estimate_reading_level(text: str) -> str:
    """A real, simple heuristic (avg word length + avg sentence length),
    not a certified readability formula. See README.md Limitations.
    """
    sentences = [s for s in re.split(r"[.!?]+", text) if s.strip()]
    words = text.split()
    if not sentences or not words:
        return "unclear"
    avg_word_len = sum(len(w) for w in words) / len(words)
    avg_sentence_len = len(words) / len(sentences)
    score = avg_word_len + (avg_sentence_len / 5)
    if score < 6:
        return "elementary"
    if score < 9:
        return "intermediate"
    return "advanced"


def _check_learning_objective_format(text: str) -> bool:
    """True if `text` uses a Bloom's-taxonomy-style action verb
    (explain, analyze, evaluate, ...) -- a real, checkable convention
    for well-formed learning objectives, not exhaustive.
    """
    return bool(_BLOOM_VERBS.search(text))


def _build_knowledge_base() -> KnowledgeBase:
    kb = KnowledgeBase()
    kb.ingest(
        "curriculum-design-principles",
        "Effective curriculum design starts from learning objectives, "
        "works backward to assessments that measure them, and only "
        "then designs the instructional activities.",
    )
    kb.ingest(
        "blooms-taxonomy",
        "Bloom's taxonomy orders cognitive skills from remember and "
        "understand through apply, analyze, evaluate, and create -- "
        "objectives should name the actual verb of the target skill.",
    )
    return kb


def _build_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        Tool(name="estimate_reading_level", call=_estimate_reading_level, description="Heuristic reading-level estimate.")
    )
    registry.register(
        Tool(
            name="check_learning_objective_format",
            call=_check_learning_objective_format,
            description="Check for a Bloom's-taxonomy-style action verb.",
        )
    )
    registry.register(as_tool(_build_knowledge_base(), name="search_curriculum_resources", top_k=2))
    registry.register(MCPToolRef(server="openstax", tool_name="search_resources"))
    return registry


# --- Guardrails ------------------------------------------------------------

_OFFICIAL_GRADE_PATTERN = re.compile(
    r"\b(issue the official grade|certify this student|submit to the registrar)\b", re.IGNORECASE
)


def _no_issuing_official_grades(task) -> Optional[str]:
    if _OFFICIAL_GRADE_PATTERN.search(task.input):
        return "task requests an official grade/certification -- requires the instructor of record, not this agent"
    return None


def _build_guardrails() -> Tuple[Guardrail, ...]:
    return (
        make_secret_scanning_guardrail(),
        Guardrail(name="no-issuing-official-grades", check=_no_issuing_official_grades),
    )


# --- Quality gates -----------------------------------------------------------


def _minimum_substance(result) -> bool:
    return len(result.output.strip()) >= 10


def _build_quality_gates() -> Tuple[QualityGate, ...]:
    suite = EvalSuite(name="instructor-disclaimer", cases=(EvalCase(inputs={}, expected=None),))
    scorer = weighted_keyword_scorer({"instructor": 1.0, "educator": 1.0, "teacher": 1.0})
    disclaimer_gate = make_quality_gate("includes-instructor-disclaimer", suite, scorer, threshold=0.0)
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


def build_education_knowledge_agent(
    router: Router, *, model_override: Optional[str] = None, memory_root_dir: Optional[Path] = None
) -> ChiefDomainAgent:
    blueprint = load_blueprint(model_override)
    root_dir = memory_root_dir or Path(tempfile.mkdtemp(prefix="education-knowledge-memory-"))
    memory = build_memory_policy(blueprint.memory_policy, root_dir=root_dir)
    return ChiefDomainAgent(
        blueprint=blueprint,
        router=router,
        memory=memory,
        tools=_build_tool_registry(),
        thinking_models=DEFAULT_THINKING_MODELS,
        guardrails=_build_guardrails(),
        quality_gates=_build_quality_gates(),
    )
