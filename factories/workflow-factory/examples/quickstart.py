"""Workflow Framework -- quickstart.

Builds a real ChiefDomainAgent, a real KnowledgeBase, and a real
InMemoryMemoryPolicy, then composes all three into one multi-step
WorkflowSpec: search knowledge -> ask the agent using the retrieved
context -> remember the answer -> branch on whether the agent needed a
follow-up. Run directly:

    python factories/workflow-factory/examples/quickstart.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_ROOT / "core" / "python"))
sys.path.insert(0, str(_ROOT / "router" / "python"))
sys.path.insert(0, str(_ROOT / "factories" / "agent-factory" / "python"))
sys.path.insert(0, str(_ROOT / "factories" / "mcp-factory" / "python"))
sys.path.insert(0, str(_ROOT / "factories" / "knowledge-factory" / "python"))
sys.path.insert(0, str(_ROOT / "factories" / "workflow-factory" / "python"))

from avishkar_agent import AgentBlueprint, ChiefDomainAgent, InMemoryMemoryPolicy, ToolRegistry  # noqa: E402
from avishkar_agent.thinking import DEFAULT_THINKING_MODELS  # noqa: E402
from avishkar_knowledge import KnowledgeBase  # noqa: E402
from avishkar_router import ModelSpec, MockProvider, Router, RoutingPolicy  # noqa: E402

from avishkar_workflow import (  # noqa: E402
    Step,
    WorkflowEngine,
    WorkflowSpec,
    make_agent_step,
    make_knowledge_search_step,
    make_memory_write_step,
)


def main() -> None:
    kb = KnowledgeBase()
    kb.ingest(
        "deploy-policy",
        "All production deploys require a passing test suite, a code review "
        "from a second engineer, and must happen on a weekday before 4pm.",
    )

    blueprint = AgentBlueprint(
        name="support-agent", domain="Support", version="0.1.0",
        mission="Answer employee questions using company policy.",
        default_model="mock-fast",
    )
    provider = MockProvider(
        models=(ModelSpec(model_id="mock-fast", provider="mock", capabilities=("chat",),
                           input_cost_per_mtok=0.0, output_cost_per_mtok=0.0,
                           max_context_tokens=8192, max_output_tokens=2048),),
        response_text="Yes -- a passing test suite and a second reviewer are required.",
    )
    router = Router([provider], RoutingPolicy(default_model="mock-fast"))
    memory = InMemoryMemoryPolicy()
    agent = ChiefDomainAgent(blueprint, router, memory, ToolRegistry(), DEFAULT_THINKING_MODELS)

    def build_question(state: dict) -> dict:
        context = state["knowledge_results"][0].chunk.text if state["knowledge_results"] else ""
        return {"input": f"Context: {context}\nQuestion: {state['query']}"}

    def extract_answer(state: dict) -> dict:
        return {"answer_text": state["output"].output}

    def decide_next(state: dict) -> str:
        # A real workflow's branch function inspects agent output to route
        # follow-ups; here we always have an answer, so we always remember it.
        return "remember"

    steps = [
        Step("search", make_knowledge_search_step(kb, query_key="query", top_k=1), next="ask"),
        Step("ask", build_question, next="answer"),
        Step("answer", make_agent_step(agent), next="extract"),
        Step("extract", extract_answer, branch=decide_next),
        Step(
            "remember",
            make_memory_write_step(memory, "semantic", key_from_state="query", value_from_state="answer_text"),
            next=None,
        ),
    ]
    spec = WorkflowSpec("support-qa", steps, start="search")

    print("Running a 5-step workflow: search -> ask -> answer -> extract -> remember\n")
    query = "what do I need before deploying to production"
    result = WorkflowEngine().run(spec, {"query": query})

    print(f"History: {' -> '.join(result.history)}")
    print(f"Agent answer: {result.state['answer_text']}")
    print(f"Memory now recalls this query's answer: {memory.recall('semantic', query)}")


if __name__ == "__main__":
    main()
