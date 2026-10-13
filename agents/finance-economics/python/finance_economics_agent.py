"""Finance & Economics -- domain module for the finance-economics
Chief Domain Agent.

Wires blueprint.json to real tools, guardrails, and quality gates.
Demonstrates security-factory's make_rate_limit_guardrail() bridge (a
different bridge than prior agents used), a real DI'd clock for
deterministic tests. avishkar_agent itself never changes to support
this agent.
"""

from __future__ import annotations

import dataclasses
import re
import tempfile
import time
from pathlib import Path
from typing import Callable, Optional, Tuple

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
from avishkar_security import make_rate_limit_guardrail, make_secret_scanning_guardrail

_BLUEPRINT_PATH = Path(__file__).resolve().parent.parent / "blueprint.json"

# --- Tools ---------------------------------------------------------------


def _calculate_debt_to_equity_ratio(total_debt: float, total_equity: float) -> float:
    """A real, standard financial ratio: total debt / total equity.
    Raises ZeroDivisionError for zero equity -- a caller's problem to
    handle, not silently masked as 0.0 (which would misleadingly read
    as "no leverage").
    """
    return total_debt / total_equity


def _classify_risk_level(volatility_pct: float) -> str:
    """A real, simple volatility-tier classification. Not a substitute
    for a real risk model -- see README.md Limitations.
    """
    if volatility_pct < 10:
        return "low"
    if volatility_pct < 25:
        return "medium"
    return "high"


def _build_knowledge_base() -> KnowledgeBase:
    kb = KnowledgeBase()
    kb.ingest(
        "financial-ratio-basics",
        "Debt-to-equity ratio measures leverage: total liabilities "
        "divided by shareholder equity. A ratio above 2.0 generally "
        "signals higher financial risk, though norms vary by industry.",
    )
    kb.ingest(
        "risk-assessment-principles",
        "Assess risk by volatility, liquidity, and correlation to "
        "existing holdings -- concentration risk matters as much as "
        "any single asset's own volatility.",
    )
    return kb


def _build_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        Tool(
            name="calculate_debt_to_equity_ratio",
            call=lambda input: _calculate_debt_to_equity_ratio(input[0], input[1]),
            description="Compute total_debt / total_equity. input: a (total_debt, total_equity) pair.",
        )
    )
    registry.register(
        Tool(name="classify_risk_level", call=_classify_risk_level, description="Classify volatility percentage into low/medium/high.")
    )
    registry.register(as_tool(_build_knowledge_base(), name="search_finance_references", top_k=2))
    registry.register(MCPToolRef(server="alpha-vantage", tool_name="get_market_data"))
    return registry


# --- Guardrails ------------------------------------------------------------

_TRADE_EXECUTION_PATTERN = re.compile(r"\b(execute this trade|buy \d+ shares for me|sell my position now)\b", re.IGNORECASE)


def _no_executing_trades(task) -> Optional[str]:
    if _TRADE_EXECUTION_PATTERN.search(task.input):
        return "task requests trade execution -- requires the account holder or a licensed advisor, not this agent"
    return None


def _build_guardrails(*, clock: Callable[[], float] = time.monotonic) -> Tuple[Guardrail, ...]:
    return (
        make_secret_scanning_guardrail(),
        Guardrail(name="no-executing-trades", check=_no_executing_trades),
        # A different security-factory bridge than prior agents used --
        # proving make_rate_limit_guardrail is genuinely reusable, not a
        # one-off. Real limit: 10 calls per 60s, generous for a demo but
        # a real, stateful guard against runaway market-data polling.
        make_rate_limit_guardrail("market-data-rate-limit", max_calls=10, window_seconds=60, clock=clock),
    )


# --- Quality gates -----------------------------------------------------------


def _minimum_substance(result) -> bool:
    return len(result.output.strip()) >= 10


def _build_quality_gates() -> Tuple[QualityGate, ...]:
    suite = EvalSuite(name="advisor-disclaimer", cases=(EvalCase(inputs={}, expected=None),))
    scorer = weighted_keyword_scorer({"financial advisor": 1.0, "not investment advice": 1.0, "your own research": 1.0})
    gate = make_quality_gate("includes-advisor-disclaimer", suite, scorer, threshold=0.0)
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


def build_finance_economics_agent(
    router: Router,
    *,
    model_override: Optional[str] = None,
    memory_root_dir: Optional[Path] = None,
    rate_limit_clock: Callable[[], float] = time.monotonic,
) -> ChiefDomainAgent:
    blueprint = load_blueprint(model_override)
    root_dir = memory_root_dir or Path(tempfile.mkdtemp(prefix="finance-economics-memory-"))
    memory = build_memory_policy(blueprint.memory_policy, root_dir=root_dir)
    return ChiefDomainAgent(
        blueprint=blueprint,
        router=router,
        memory=memory,
        tools=_build_tool_registry(),
        thinking_models=DEFAULT_THINKING_MODELS,
        guardrails=_build_guardrails(clock=rate_limit_clock),
        quality_gates=_build_quality_gates(),
    )
