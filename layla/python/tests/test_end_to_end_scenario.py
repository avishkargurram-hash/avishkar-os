"""Deterministic test fixture for the Part IX end-to-end scenario:
"Research the latest developments relevant to one of my projects,
summarize the important findings, identify anything that requires my
attention, update the project task state, and prepare a follow-up
plan." See layla/examples/end_to_end_scenario.py for the runnable,
narrated version of this same scenario against the real
research-intelligence Chief Domain Agent.
"""

import unittest

from avishkar_agent import InMemoryMemoryPolicy, Orchestrator

from avishkar_layla import LaylaMemoryPolicy, Project
from avishkar_layla.project import ProjectStore
from avishkar_layla.runtime import ExecutiveRuntime
from avishkar_layla.types import COMPLETED


class TestEndToEndResearchScenario(unittest.TestCase):
    def _agent(self, name, domain, response_text):
        from avishkar_agent import AgentBlueprint, ChiefDomainAgent, ToolRegistry
        from avishkar_agent.thinking import DEFAULT_THINKING_MODELS
        from avishkar_router import ModelSpec, MockProvider, RoutingPolicy, Router

        blueprint = AgentBlueprint(name=name, domain=domain, version="0.1.0", mission="test", default_model="mock-fast")
        provider = MockProvider(
            models=(ModelSpec(model_id="mock-fast", provider="mock", capabilities=("chat",),
                               input_cost_per_mtok=0.0, output_cost_per_mtok=0.0,
                               max_context_tokens=8192, max_output_tokens=2048),),
            response_text=response_text,
        )
        router = Router([provider], RoutingPolicy(default_model="mock-fast"))
        return ChiefDomainAgent(blueprint, router, InMemoryMemoryPolicy(), ToolRegistry(), DEFAULT_THINKING_MODELS)

    def test_full_scenario_reaches_completed_with_project_state_updated(self):
        from avishkar_knowledge import KnowledgeBase

        research_agent = self._agent(
            "research-intelligence", "Research & Intelligence",
            "Findings suggest a preliminary trend worth tracking for this project.",
        )
        orchestrator = Orchestrator([research_agent])
        memory = LaylaMemoryPolicy(InMemoryMemoryPolicy())
        project_store = ProjectStore(memory)
        kb = KnowledgeBase()
        kb.ingest("project-background", "This project explores retrieval-augmented planning agents.")

        project = Project(id="proj-1", name="Test Project", status="active")
        project_store.save(project)

        runtime = ExecutiveRuntime(
            orchestrator=orchestrator,
            agent_domains={research_agent.name: research_agent.domain},
            memory=memory,
            knowledge_bases=[kb],
            clock=lambda: 0.0,
            sleep_fn=lambda s: None,
        )

        task = runtime.handle_event(
            "Research the latest developments relevant to research for this project and prepare a follow-up plan."
        )

        # 1. Task reaches COMPLETED through the real state machine.
        self.assertEqual(task.state, COMPLETED)
        self.assertEqual(
            [t.to_state for t in task.history],
            ["UNDERSTANDING", "CONTEXT_LOADING", "PLANNING", "EXECUTING", "DELEGATING", "WAITING", "VERIFYING", "SYNTHESIZING", "COMPLETED"],
        )

        # 2. Context included the real knowledge search.
        self.assertTrue(task.context["knowledge"])

        # 3. Delegation reached the real research agent.
        self.assertIn("research-intelligence", task.result)

        # 4. Audit trail is complete and structured.
        history = runtime.audit.history(task.id)
        event_types = [r.event_type for r in history]
        self.assertEqual(
            event_types,
            ["layla.task.received", "layla.intent.classified", "layla.plan.created",
             "layla.delegation.completed", "layla.validation.completed", "layla.task.completed"],
        )

        # 5. Project state can be updated (ProjectStore write survives).
        updated = Project(id=project.id, name=project.name, status=project.status,
                           tasks=project.tasks + (f"Reviewed findings (task {task.id})",))
        project_store.save(updated)
        self.assertEqual(len(project_store.load("proj-1").tasks), 1)

        # 6. Session is durable (restart-recoverable in principle --
        # cross-instance recovery itself proven in test_session.py).
        self.assertIsNotNone(runtime.sessions.load(task.id))

        # 7. No approval was required for this LOW-risk research request.
        self.assertEqual(runtime.notifications.pending(), ())


if __name__ == "__main__":
    unittest.main()
