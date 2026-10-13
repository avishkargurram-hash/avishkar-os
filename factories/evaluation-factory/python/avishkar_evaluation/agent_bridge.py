"""Agent Framework bridge. See CONTRACT.md SS4.

Turns an EvalSuite into a real avishkar_agent.QualityGate -- a pure
consumer of agent-factory's already-public type, no changes to
agent-factory's locked source (same dependency-direction discipline
every later framework has followed since mcp-factory, ADR-0011).
"""

from __future__ import annotations

from avishkar_agent import AgentResult, QualityGate

from .runner import passes_threshold, run_suite
from .types import EvalSuite, Scorer


def make_quality_gate(name: str, suite: EvalSuite, scorer: Scorer, threshold: float) -> QualityGate:
    def check(candidate: AgentResult) -> bool:
        report = run_suite(suite, lambda case: candidate.output, scorer)
        return passes_threshold(report, threshold)

    return QualityGate(name=name, check=check)
