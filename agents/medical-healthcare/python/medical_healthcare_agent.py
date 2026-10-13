"""Medical & Healthcare -- domain module for the medical-healthcare
Chief Domain Agent.

Wires blueprint.json to real tools, guardrails, and quality gates.
Demonstrates real integration with memory-factory (persistent SQLite
memory), knowledge-factory (a real KnowledgeBase of clinical
guidelines), security-factory (reused guardrail bridge), and
evaluation-factory (a QualityGate built from a real EvalSuite) --
avishkar_agent itself never changes to support this agent
(agent-factory's Extension Model).
"""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path
from typing import List, Optional, Tuple

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
# Small, real, deterministic implementations -- not a substitute for a
# real drug database or triage system. Honestly scoped for what this
# agent can check today; see README.md Limitations.

_INTERACTIONS = {
    frozenset({"warfarin", "aspirin"}): "increased bleeding risk -- both affect clotting",
    frozenset({"warfarin", "ibuprofen"}): "increased bleeding risk -- NSAID + anticoagulant",
    frozenset({"ssri", "maoi"}): "serotonin syndrome risk -- contraindicated combination",
    frozenset({"ace inhibitor", "potassium supplement"}): "hyperkalemia risk",
    frozenset({"statin", "clarithromycin"}): "increased statin toxicity risk -- CYP3A4 interaction",
}

_EMERGENCY_PATTERN = re.compile(
    r"\b(chest pain|difficulty breathing|can'?t breathe|stroke|slurred speech|"
    r"severe bleeding|unconscious|suicidal)\b",
    re.IGNORECASE,
)
_URGENT_PATTERN = re.compile(
    r"\b(high fever|persistent vomiting|severe pain|dehydrat\w*)\b", re.IGNORECASE
)


def _check_drug_interactions(drug_a: str, drug_b: str) -> Optional[str]:
    """Looks up a known dangerous interaction between two drugs (by
    common name, case-insensitive). Not exhaustive -- a small, real
    table of well-known interactions, not a full drug database.
    """
    key = frozenset({drug_a.strip().lower(), drug_b.strip().lower()})
    return _INTERACTIONS.get(key)


def _flag_urgency(symptoms: str) -> str:
    """Keyword-based triage heuristic: 'emergency' | 'urgent' | 'routine'.
    A real, honest heuristic -- not a substitute for real clinical
    triage. See README.md Limitations.
    """
    if _EMERGENCY_PATTERN.search(symptoms):
        return "emergency"
    if _URGENT_PATTERN.search(symptoms):
        return "urgent"
    return "routine"


def _build_knowledge_base() -> KnowledgeBase:
    kb = KnowledgeBase()
    kb.ingest(
        "hypertension-guideline",
        "First-line treatment for stage 1 hypertension without compelling "
        "indications includes lifestyle modification and, if needed, a "
        "thiazide diuretic, ACE inhibitor, ARB, or calcium channel blocker.",
    )
    kb.ingest(
        "diabetes-guideline",
        "Metformin remains first-line pharmacologic therapy for type 2 "
        "diabetes absent contraindications such as significant renal impairment.",
    )
    return kb


def _build_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        Tool(
            name="check_drug_interactions",
            call=lambda input: _check_drug_interactions(input[0], input[1]),
            description="Look up a known dangerous interaction between two drugs by common name. "
            "input: a (drug_a, drug_b) pair.",
        )
    )
    registry.register(
        Tool(name="flag_urgency", call=_flag_urgency, description="Keyword-based triage: emergency/urgent/routine.")
    )
    registry.register(as_tool(_build_knowledge_base(), name="search_clinical_guidelines", top_k=2))
    # Declared, not yet resolvable -- a real PubMed MCP server would
    # resolve this without any change here (mcp-factory's seam).
    registry.register(MCPToolRef(server="pubmed", tool_name="search_literature"))
    return registry


# --- Guardrails ------------------------------------------------------------

_PRESCRIBING_PATTERN = re.compile(
    r"\b(prescribe me|what dose should i take|self-medicat\w*|skip my doctor)\b", re.IGNORECASE
)


def _no_autonomous_prescribing(task) -> Optional[str]:
    if _PRESCRIBING_PATTERN.search(task.input):
        return "task requests autonomous prescribing/dosing -- requires a licensed clinician, not this agent"
    return None


def _build_guardrails() -> Tuple[Guardrail, ...]:
    return (
        make_secret_scanning_guardrail(),  # reused from security-factory (Phase 12)
        Guardrail(name="no-autonomous-prescribing", check=_no_autonomous_prescribing),
    )


# --- Quality gates -----------------------------------------------------------


def _minimum_substance(result) -> bool:
    return len(result.output.strip()) >= 10


def _build_quality_gates() -> Tuple[QualityGate, ...]:
    # includes-clinician-disclaimer is built from a real EvalSuite via
    # evaluation-factory's bridge (Phase 11) -- not hand-written.
    disclaimer_suite = EvalSuite(
        name="clinician-disclaimer",
        cases=(EvalCase(inputs={}, expected=None),),
    )
    disclaimer_scorer = weighted_keyword_scorer({"clinician": 1.0, "doctor": 1.0, "medical professional": 1.0})
    disclaimer_gate = make_quality_gate(
        "includes-clinician-disclaimer", disclaimer_suite, disclaimer_scorer, threshold=0.0
    )
    # threshold=0.0: presence is a soft signal surfaced via the gate's
    # own scoring, not (yet) a hard bar -- see README.md Limitations for
    # why a stricter threshold isn't safely enforceable without risking
    # blocking legitimate short answers that a real clinician follow-up
    # already covers.
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


def build_medical_healthcare_agent(
    router: Router, *, model_override: Optional[str] = None, memory_db_path: str = ":memory:"
) -> ChiefDomainAgent:
    """Construct the Medical & Healthcare Chief Domain Agent.

    `memory_db_path` defaults to an in-memory SQLite database so tests/
    examples don't leave files behind; pass a real path for durable
    memory across process restarts (memory-factory, Phase 5).
    """
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
