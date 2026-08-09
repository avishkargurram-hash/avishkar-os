"""Cross-domain review workflow -- the first concrete, product-facing
WorkflowSpec committed under workflows/ (Phase 14), rather than only
an example living inside factories/workflow-factory.

Composes two real Chief Domain Agents (any two -- the built-in example
pairs legal-compliance with finance-economics, but this module is
generic) via workflow-factory's make_agent_step bridge: get each
agent's perspective, then synthesize both into one combined summary.
No new architecture -- pure composition of what Phases 3-13 already built.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping

from avishkar_agent import ChiefDomainAgent
from avishkar_workflow import Step, WorkflowEngine, WorkflowResult, WorkflowSpec, make_agent_step


def _make_synthesize_step(first_name: str, second_name: str) -> Callable[[Mapping[str, Any]], Mapping[str, Any]]:
    def synthesize(state: Mapping[str, Any]) -> Mapping[str, Any]:
        first = state["first_result"].output
        second = state["second_result"].output
        summary = f"[{first_name}]: {first}\n[{second_name}]: {second}"
        return {"summary": summary}

    return synthesize


def build_cross_domain_review_workflow(
    first_agent: ChiefDomainAgent, second_agent: ChiefDomainAgent
) -> WorkflowSpec:
    """A named, reusable two-agent review workflow: first_agent's
    perspective, then second_agent's, then a synthesized summary of
    both. Real workflow-factory Steps (Phase 7), real agent-factory
    agents (Phase 3+) -- this module only wires them together.
    """
    steps = (
        Step(
            "first_review",
            make_agent_step(first_agent, input_key="input", output_key="first_result"),
            next="second_review",
        ),
        Step(
            "second_review",
            make_agent_step(second_agent, input_key="input", output_key="second_result"),
            next="synthesize",
        ),
        Step("synthesize", _make_synthesize_step(first_agent.name, second_agent.name), next=None),
    )
    return WorkflowSpec("cross-domain-review", steps, start="first_review")


def run_cross_domain_review(
    first_agent: ChiefDomainAgent, second_agent: ChiefDomainAgent, input_text: str
) -> WorkflowResult:
    """Convenience entry point: builds the spec and runs it in one call."""
    spec = build_cross_domain_review_workflow(first_agent, second_agent)
    return WorkflowEngine().run(spec, {"input": input_text})
