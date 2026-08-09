"""Layla -- real end-to-end demonstration (Part IX of the Phase 16
directive).

Scenario: "Research the latest developments relevant to one of my
projects, summarize the important findings, identify anything that
requires my attention, update the project task state, and prepare a
follow-up plan."

Architecture exercised, every piece real (no mocked claims beyond
MockProvider standing in for a live model, the same discipline every
example in this repository already follows):

    Layla (ExecutiveRuntime)
      -> Context (ContextBuilder: Memory + Knowledge)
      -> Planning (Planner: capability inference)
      -> Delegation (DelegationEngine -> real avishkar_agent.Orchestrator
         -> the real research-intelligence Chief Domain Agent, Phase 13)
      -> Validation (ResultValidator)
      -> Project state (ProjectStore, updated with a new task entry)
      -> Executive summary (ExecutiveSynthesizer)
      -> Human approval where required (none here -- LOW risk)

Run directly:

    python layla/examples/end_to_end_scenario.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
for rel in (
    "core/python", "router/python", "factories/agent-factory/python",
    "factories/mcp-factory/python", "factories/knowledge-factory/python",
    "factories/memory-factory/python", "factories/workflow-factory/python",
    "factories/prompt-factory/python", "factories/evaluation-factory/python",
    "factories/security-factory/python", "agents/research-intelligence/python",
    "layla/python",
):
    sys.path.insert(0, str(_ROOT / rel))

from avishkar_agent import InMemoryMemoryPolicy, Orchestrator  # noqa: E402
from avishkar_knowledge import KnowledgeBase  # noqa: E402
from avishkar_router import ModelSpec, MockProvider, RoutingPolicy, Router  # noqa: E402

from avishkar_layla import LaylaMemoryPolicy, Project  # noqa: E402
from avishkar_layla.project import ProjectStore  # noqa: E402
from avishkar_layla.runtime import ExecutiveRuntime  # noqa: E402

from research_intelligence_agent import build_research_intelligence_agent  # noqa: E402


def main() -> None:
    provider = MockProvider(
        models=(ModelSpec(model_id="mock-fast", provider="mock", capabilities=("chat", "tools"),
                           input_cost_per_mtok=0.0, output_cost_per_mtok=0.0,
                           max_context_tokens=8192, max_output_tokens=2048),),
        response_text=(
            "Recent evidence suggests growing interest in retrieval-augmented "
            "planning agents; this is preliminary but worth tracking for Project Atlas."
        ),
    )
    router = Router([provider], RoutingPolicy(default_model="mock-fast"))
    research_agent = build_research_intelligence_agent(router, model_override="mock-fast")
    orchestrator = Orchestrator([research_agent])

    # Real Memory (Phase 5) + a real per-project KnowledgeBase (Phase 6).
    layla_memory = LaylaMemoryPolicy(InMemoryMemoryPolicy())
    project_store = ProjectStore(layla_memory)
    kb = KnowledgeBase()
    kb.ingest(
        "project-atlas-background",
        "Project Atlas is exploring retrieval-augmented planning agents "
        "for autonomous task execution.",
    )

    project = Project(
        id="atlas", name="Project Atlas",
        objectives=("evaluate retrieval-augmented planning",),
        status="active",
    )
    project_store.save(project)
    print(f"1. Project registered: {project.name} (status={project.status})\n")

    runtime = ExecutiveRuntime(
        orchestrator=orchestrator,
        agent_domains={research_agent.name: research_agent.domain},
        memory=layla_memory,
        knowledge_bases=[kb],
        clock=lambda: 0.0,
        sleep_fn=lambda s: None,
    )

    request = (
        "Research the latest developments relevant to research-intelligence for Project Atlas, "
        "summarize the important findings, and prepare a follow-up plan."
    )
    print(f"2. User request: {request!r}\n")

    task = runtime.handle_event(request)

    print(f"3. Task state machine reached: {task.state}")
    print(f"   History: {' -> '.join(t.to_state for t in task.history)}\n")

    print("4. Executive summary (synthesized from delegated research):")
    print(f"   {task.result}\n")

    print("5. Audit trail (structured, no raw chain-of-thought):")
    for record in runtime.audit.history(task.id):
        print(f"   [{record.event_type}] {dict(record.payload)}")
    print()

    # "update the project task state" -- a real ProjectStore write.
    updated_project = Project(
        id=project.id, name=project.name, objectives=project.objectives,
        milestones=project.milestones,
        tasks=project.tasks + (f"Reviewed research findings (task {task.id})",),
        decisions=project.decisions, owners=project.owners,
        status=project.status, dependencies=project.dependencies,
    )
    project_store.save(updated_project)
    reloaded = project_store.load("atlas")
    print("6. Project task state updated:")
    print(f"   tasks={reloaded.tasks}\n")

    print(f"7. Session persisted (restart-recoverable): {runtime.sessions.load(task.id) is not None}")
    print(f"8. Pending notifications requiring attention: {len(runtime.notifications.pending())}")


if __name__ == "__main__":
    main()
