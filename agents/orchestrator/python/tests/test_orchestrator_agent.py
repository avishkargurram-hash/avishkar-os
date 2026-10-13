import unittest

from avishkar_agent import Task
from avishkar_router import ModelSpec, MockProvider, RoutingPolicy, Router

from orchestrator_agent import build_all_domain_agents, build_executive_orchestrator


def _router(response_text: str = "Here is the answer.") -> Router:
    provider = MockProvider(
        models=(ModelSpec(model_id="mock-fast", provider="mock", capabilities=("chat", "tools"),
                           input_cost_per_mtok=1.0, output_cost_per_mtok=1.0,
                           max_context_tokens=8192, max_output_tokens=2048),),
        response_text=response_text,
    )
    return Router([provider], RoutingPolicy(default_model="mock-fast"))


class TestBuildAllDomainAgents(unittest.TestCase):
    def test_builds_all_ten_domain_agents(self):
        agents = build_all_domain_agents(_router(), model_override="mock-fast")
        self.assertEqual(len(agents), 10)
        self.assertIn("software-ai-engineering", agents)
        self.assertIn("medical-healthcare", agents)
        self.assertIn("legal-compliance", agents)
        self.assertIn("startup-business-product", agents)
        self.assertIn("education-knowledge", agents)
        self.assertIn("research-intelligence", agents)
        self.assertIn("finance-economics", agents)
        self.assertIn("government-public-policy", agents)
        self.assertIn("human-development-psychology", agents)
        self.assertIn("creative-media", agents)

    def test_every_domain_agent_actually_completes_a_task(self):
        # Not just "constructs without error" -- every one of the 10
        # actually runs its real reasoning loop successfully.
        agents = build_all_domain_agents(_router(), model_override="mock-fast")
        for name, agent in agents.items():
            with self.subTest(agent=name):
                result = agent.handle(Task(input="Give me a brief, general overview."))
                self.assertEqual(result.status, "completed")


class TestBuildExecutiveOrchestrator(unittest.TestCase):
    def test_lists_all_ten_agents(self):
        orchestrator = build_executive_orchestrator(_router(), model_override="mock-fast")
        self.assertEqual(len(orchestrator.list_agents()), 10)

    def test_routes_to_a_named_agent(self):
        orchestrator = build_executive_orchestrator(_router(), model_override="mock-fast")
        result = orchestrator.route(Task(input="What's a healthy debt-to-equity ratio?", task_type="finance-economics"))
        self.assertEqual(result.status, "completed")

    def test_delegate_team_dispatches_to_every_named_agent(self):
        orchestrator = build_executive_orchestrator(_router(), model_override="mock-fast")
        results = orchestrator.delegate_team(
            Task(input="Review this from both a legal and financial angle."),
            ["legal-compliance", "finance-economics"],
        )
        self.assertEqual(set(results.keys()), {"legal-compliance", "finance-economics"})
        self.assertTrue(all(r.status == "completed" for r in results.values()))

    def test_broadcast_dispatches_to_every_named_agent(self):
        orchestrator = build_executive_orchestrator(_router(), model_override="mock-fast")
        results = orchestrator.broadcast(
            Task(input="What do you think of this idea?"),
            ["creative-media", "startup-business-product"],
        )
        self.assertEqual(len(results), 2)

    def test_resolve_conflict_first_completed(self):
        orchestrator = build_executive_orchestrator(_router(), model_override="mock-fast")
        results = orchestrator.delegate_team(Task(input="Quick check."), ["software-ai-engineering"])
        resolved = orchestrator.resolve_conflict(results, "first_completed")
        self.assertEqual(resolved.status, "completed")


if __name__ == "__main__":
    unittest.main()
