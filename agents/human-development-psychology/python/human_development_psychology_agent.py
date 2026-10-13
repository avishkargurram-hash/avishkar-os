"""Human Development & Psychology -- domain module for the
human-development-psychology Chief Domain Agent.

Wires blueprint.json to real tools, guardrails, and quality gates.
The crisis-escalation guardrail is the most safety-critical piece in
this repository: its block reason carries real crisis-resource contact
information, not just a refusal -- see README.md SS17-18. avishkar_agent
itself never changes to support this agent.
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

_CRISIS_PATTERN = re.compile(
    r"\b(suicidal|kill myself|end my life|self-harm|hurt myself|want to die)\b", re.IGNORECASE
)

_REFLECTION_PROMPTS = {
    "growth": "What's one thing you learned about yourself this week, and what would you do differently?",
    "relationships": "Think of a recent disagreement -- what did the other person need that they didn't say directly?",
    "stress": "What's within your control in this situation, and what genuinely isn't?",
}


def _detect_crisis_language(text: str) -> bool:
    """A real, safety-critical check for self-harm/crisis language.
    Deliberately conservative (a few clear phrases, not a clinical
    screening tool) -- see README.md Limitations for why this
    complements, not replaces, real crisis intervention resources.
    """
    return bool(_CRISIS_PATTERN.search(text))


def _suggest_reflection_prompt(topic: str) -> str:
    """A real, small library of reflection prompts by topic. Falls back
    to a generic prompt for an unrecognized topic rather than raising.
    """
    return _REFLECTION_PROMPTS.get(
        topic.strip().lower(), "What matters most to you about this right now?"
    )


def _build_knowledge_base() -> KnowledgeBase:
    kb = KnowledgeBase()
    kb.ingest(
        "active-listening-principles",
        "Active listening means reflecting back what you heard before "
        "responding, asking open questions, and resisting the urge to "
        "immediately problem-solve when someone just needs to be heard.",
    )
    kb.ingest(
        "growth-mindset",
        "A growth mindset treats ability as developable through effort "
        "and strategy, not fixed -- setbacks are information, not "
        "verdicts on capability.",
    )
    return kb


def _build_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        Tool(name="detect_crisis_language", call=_detect_crisis_language, description="Detect self-harm/crisis language in text.")
    )
    registry.register(
        Tool(name="suggest_reflection_prompt", call=_suggest_reflection_prompt, description="A reflection prompt for a topic.")
    )
    registry.register(as_tool(_build_knowledge_base(), name="search_growth_resources", top_k=2))
    registry.register(MCPToolRef(server="psychology-today", tool_name="find_local_therapist"))
    return registry


# --- Guardrails ------------------------------------------------------------

_CRISIS_RESOURCE_MESSAGE = (
    "crisis language detected -- if you're in crisis, please contact the 988 Suicide & Crisis "
    "Lifeline (call or text 988 in the US) or your local emergency number right now. "
    "This agent is not equipped to handle a crisis situation."
)


def _crisis_escalation(task) -> Optional[str]:
    """The most safety-critical guardrail in this repository: its block
    reason is real, actionable crisis-resource information, not just a
    refusal. See README.md SS17-18.
    """
    if _detect_crisis_language(task.input):
        return _CRISIS_RESOURCE_MESSAGE
    return None


def _build_guardrails() -> Tuple[Guardrail, ...]:
    return (
        make_secret_scanning_guardrail(),
        Guardrail(name="crisis-escalation", check=_crisis_escalation),
    )


# --- Quality gates -----------------------------------------------------------


def _minimum_substance(result) -> bool:
    return len(result.output.strip()) >= 10


def _build_quality_gates() -> Tuple[QualityGate, ...]:
    suite = EvalSuite(name="therapist-disclaimer", cases=(EvalCase(inputs={}, expected=None),))
    scorer = weighted_keyword_scorer({"therapist": 1.0, "counselor": 1.0, "mental health professional": 1.0})
    gate = make_quality_gate("includes-therapist-disclaimer", suite, scorer, threshold=0.0)
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


def build_human_development_psychology_agent(
    router: Router, *, model_override: Optional[str] = None, memory_root_dir: Optional[Path] = None
) -> ChiefDomainAgent:
    blueprint = load_blueprint(model_override)
    root_dir = memory_root_dir or Path(tempfile.mkdtemp(prefix="human-development-psychology-memory-"))
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
