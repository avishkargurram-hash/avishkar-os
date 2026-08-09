"""Legal & Compliance -- domain module for the legal-compliance Chief
Domain Agent.

Wires blueprint.json to real tools, guardrails, and quality gates.
Demonstrates memory-factory's FileMemoryPolicy (a different backend
than medical-healthcare's SQLite -- proving both are genuinely usable),
a real knowledge-factory KnowledgeBase, and evaluation-factory/
security-factory bridges. avishkar_agent itself never changes to
support this agent.
"""

from __future__ import annotations

import dataclasses
import re
import tempfile
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

_RISKY_CLAUSE_PATTERNS = {
    "unlimited_liability": re.compile(r"\bunlimited liability\b", re.IGNORECASE),
    "unilateral_termination": re.compile(r"\b(sole discretion|unilaterally)\b.{0,40}\bterminat", re.IGNORECASE),
    "auto_renewal_without_notice": re.compile(r"\bautomatically renew\b(?!.{0,60}\bnotice\b)", re.IGNORECASE),
    "broad_indemnification": re.compile(r"\bindemnify\b.{0,30}\bany and all\b", re.IGNORECASE),
}

_CITATION_PATTERN = re.compile(r"\d+\s+[A-Z][a-zA-Z.]*\s+\d+")  # e.g. "410 U.S. 113"


def _flag_risky_clauses(text: str) -> List[str]:
    """Flags a small set of real, checkable risky-clause patterns. Not a
    substitute for attorney review -- see README.md Limitations.
    """
    return [name for name, pattern in _RISKY_CLAUSE_PATTERNS.items() if pattern.search(text)]


def _check_citation_format(text: str) -> bool:
    """True if `text` contains at least one citation matching a common
    reporter-style format (e.g. '410 U.S. 113'). A format check, not a
    verification that the citation is real or correct.
    """
    return bool(_CITATION_PATTERN.search(text))


def _build_knowledge_base() -> KnowledgeBase:
    kb = KnowledgeBase()
    kb.ingest(
        "nda-basics",
        "A mutual NDA should define confidential information narrowly, "
        "set a reasonable term (typically 1-5 years), and exclude "
        "information already public or independently developed.",
    )
    kb.ingest(
        "contract-review-checklist",
        "Review every contract for: parties and signing authority, "
        "term and termination, liability caps, indemnification scope, "
        "governing law, and dispute resolution mechanism.",
    )
    return kb


def _build_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        Tool(name="flag_risky_clauses", call=_flag_risky_clauses, description="Flag known risky contract clause patterns.")
    )
    registry.register(
        Tool(
            name="check_citation_format",
            call=_check_citation_format,
            description="Check whether text contains a reporter-style legal citation.",
        )
    )
    registry.register(as_tool(_build_knowledge_base(), name="search_legal_references", top_k=2))
    registry.register(MCPToolRef(server="courtlistener", tool_name="search_case_law"))
    return registry


# --- Guardrails ------------------------------------------------------------

_UNAUTHORIZED_ADVICE_PATTERN = re.compile(
    r"\b(represent me in court|file this lawsuit for me|is this legally binding, act now)\b", re.IGNORECASE
)


def _no_unauthorized_legal_advice(task) -> Optional[str]:
    if _UNAUTHORIZED_ADVICE_PATTERN.search(task.input):
        return "task requests representation/binding legal action -- requires a licensed attorney, not this agent"
    return None


def _build_guardrails() -> Tuple[Guardrail, ...]:
    return (
        make_secret_scanning_guardrail(),
        Guardrail(name="no-unauthorized-legal-advice", check=_no_unauthorized_legal_advice),
    )


# --- Quality gates -----------------------------------------------------------


def _minimum_substance(result) -> bool:
    return len(result.output.strip()) >= 10


def _build_quality_gates() -> Tuple[QualityGate, ...]:
    disclaimer_suite = EvalSuite(name="attorney-disclaimer", cases=(EvalCase(inputs={}, expected=None),))
    disclaimer_scorer = weighted_keyword_scorer({"attorney": 1.0, "legal counsel": 1.0, "licensed lawyer": 1.0})
    disclaimer_gate = make_quality_gate("includes-attorney-disclaimer", disclaimer_suite, disclaimer_scorer, threshold=0.0)
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


def build_legal_compliance_agent(
    router: Router, *, model_override: Optional[str] = None, memory_root_dir: Optional[Path] = None
) -> ChiefDomainAgent:
    """Construct the Legal & Compliance Chief Domain Agent.

    `memory_root_dir` defaults to a fresh temp directory so tests/
    examples never write into this repository; pass a real path for
    durable file-backed memory across process restarts.
    """
    blueprint = load_blueprint(model_override)
    root_dir = memory_root_dir or Path(tempfile.mkdtemp(prefix="legal-compliance-memory-"))
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
