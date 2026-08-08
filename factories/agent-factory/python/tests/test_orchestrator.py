import unittest

from avishkar_core import EventBus

from avishkar_agent import AgentResult, DuplicateAgentError, NoMatchingAgentError, Orchestrator, Task, UnknownAgentError


class _FakeAgent:
    """A lightweight test double implementing the surface Orchestrator
    depends on (.name, .domain, .handle()) -- mirrors how router tests
    use MockProvider instead of a real network-calling adapter.
    """

    def __init__(self, name, domain, status="completed"):
        self.name = name
        self.domain = domain
        self._status = status
        self.handled_tasks = []

    def handle(self, task: Task) -> AgentResult:
        self.handled_tasks.append(task)
        return AgentResult(
            output=f"handled by {self.name}",
            agent_name=self.name,
            thinking_trace=(),
            tool_calls=(),
            iterations=1,
            status=self._status,
            cost_usd=0.0,
        )


def _task(**kwargs):
    kwargs.setdefault("input", "do something")
    return Task(**kwargs)


class TestOrchestratorConstruction(unittest.TestCase):
    def test_duplicate_agent_name_raises(self):
        agent_a = _FakeAgent("software", "Software Engineering")
        agent_b = _FakeAgent("software", "Software Engineering (duplicate)")
        with self.assertRaises(DuplicateAgentError):
            Orchestrator([agent_a, agent_b])

    def test_list_agents(self):
        orchestrator = Orchestrator([_FakeAgent("a", "Domain A"), _FakeAgent("b", "Domain B")])
        self.assertEqual(set(orchestrator.list_agents()), {"a", "b"})


class TestOrchestratorRoute(unittest.TestCase):
    def test_single_registered_agent_used_without_task_type(self):
        agent = _FakeAgent("software", "Software Engineering")
        orchestrator = Orchestrator([agent])

        result = orchestrator.route(_task())

        self.assertEqual(result.agent_name, "software")

    def test_multiple_agents_without_task_type_raises(self):
        orchestrator = Orchestrator([_FakeAgent("a", "Domain A"), _FakeAgent("b", "Domain B")])
        with self.assertRaises(NoMatchingAgentError):
            orchestrator.route(_task())

    def test_task_type_matching_exact_agent_name(self):
        orchestrator = Orchestrator([_FakeAgent("a", "Domain A"), _FakeAgent("b", "Domain B")])
        result = orchestrator.route(_task(task_type="b"))
        self.assertEqual(result.agent_name, "b")

    def test_task_type_matching_domain_substring(self):
        orchestrator = Orchestrator([_FakeAgent("legal", "Legal & Compliance"), _FakeAgent("medical", "Medical & Healthcare")])
        result = orchestrator.route(_task(task_type="legal"))
        self.assertEqual(result.agent_name, "legal")

    def test_task_type_matching_multiple_domains_raises(self):
        orchestrator = Orchestrator([_FakeAgent("a", "Engineering A"), _FakeAgent("b", "Engineering B")])
        with self.assertRaises(NoMatchingAgentError):
            orchestrator.route(_task(task_type="engineering"))

    def test_task_type_matching_nothing_raises(self):
        orchestrator = Orchestrator([_FakeAgent("a", "Domain A")])
        with self.assertRaises(NoMatchingAgentError):
            orchestrator.route(_task(task_type="nonexistent-domain"))


class TestOrchestratorTeamAndBroadcast(unittest.TestCase):
    def test_delegate_team_dispatches_to_every_named_agent(self):
        orchestrator = Orchestrator([_FakeAgent("a", "Domain A"), _FakeAgent("b", "Domain B")])

        results = orchestrator.delegate_team(_task(), ["a", "b"])

        self.assertEqual(set(results), {"a", "b"})
        self.assertEqual(results["a"].agent_name, "a")

    def test_delegate_team_unknown_agent_raises(self):
        orchestrator = Orchestrator([_FakeAgent("a", "Domain A")])
        with self.assertRaises(UnknownAgentError):
            orchestrator.delegate_team(_task(), ["a", "nonexistent"])

    def test_broadcast_dispatches_to_every_named_agent(self):
        orchestrator = Orchestrator([_FakeAgent("a", "Domain A"), _FakeAgent("b", "Domain B")])

        results = orchestrator.broadcast(_task(), ["a", "b"])

        self.assertEqual(set(results), {"a", "b"})

    def test_broadcast_and_team_publish_distinct_events(self):
        bus = EventBus()
        received = []
        bus.subscribe("*", lambda e: received.append(e.event_type))
        orchestrator = Orchestrator([_FakeAgent("a", "Domain A")], event_bus=bus)

        orchestrator.delegate_team(_task(), ["a"])
        orchestrator.broadcast(_task(), ["a"])

        self.assertIn("orchestrator.team.completed", received)
        self.assertIn("orchestrator.broadcast.completed", received)


class TestOrchestratorConflictResolution(unittest.TestCase):
    def test_first_completed_strategy(self):
        results = {
            "a": AgentResult(output="", agent_name="a", thinking_trace=(), tool_calls=(), iterations=1, status="blocked", cost_usd=0.0),
            "b": AgentResult(output="", agent_name="b", thinking_trace=(), tool_calls=(), iterations=1, status="completed", cost_usd=0.0),
        }
        orchestrator = Orchestrator([])

        resolved = orchestrator.resolve_conflict(results, "first_completed")

        self.assertEqual(resolved.agent_name, "b")

    def test_first_completed_none_completed_raises(self):
        results = {
            "a": AgentResult(output="", agent_name="a", thinking_trace=(), tool_calls=(), iterations=1, status="blocked", cost_usd=0.0),
        }
        orchestrator = Orchestrator([])
        with self.assertRaises(NoMatchingAgentError):
            orchestrator.resolve_conflict(results, "first_completed")

    def test_prefer_agent_strategy(self):
        results = {
            "a": AgentResult(output="from a", agent_name="a", thinking_trace=(), tool_calls=(), iterations=1, status="completed", cost_usd=0.0),
            "b": AgentResult(output="from b", agent_name="b", thinking_trace=(), tool_calls=(), iterations=1, status="completed", cost_usd=0.0),
        }
        orchestrator = Orchestrator([])

        resolved = orchestrator.resolve_conflict(results, "prefer_agent:b")

        self.assertEqual(resolved.output, "from b")

    def test_prefer_agent_unknown_name_raises(self):
        results = {"a": AgentResult(output="", agent_name="a", thinking_trace=(), tool_calls=(), iterations=1, status="completed", cost_usd=0.0)}
        orchestrator = Orchestrator([])
        with self.assertRaises(UnknownAgentError):
            orchestrator.resolve_conflict(results, "prefer_agent:nonexistent")

    def test_unknown_strategy_raises(self):
        orchestrator = Orchestrator([])
        with self.assertRaises(ValueError):
            orchestrator.resolve_conflict({}, "coin_flip")


if __name__ == "__main__":
    unittest.main()
