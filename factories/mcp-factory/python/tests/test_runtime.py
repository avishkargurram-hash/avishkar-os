import unittest

from avishkar_agent import ApprovalGate, InMemoryMemoryPolicy
from avishkar_core import EventBus
from avishkar_integration import (
    AccessControlPolicy,
    RetryPolicy,
    SecurityPolicy,
    ToolNotFoundError,
    ToolRuntime,
    UniversalToolRegistry,
)

from fixtures import FakeAdapter, make_contract


def _setup(*, max_attempts=1, fail_identities=()):
    registry = UniversalToolRegistry()
    contract = make_contract("demo", retry_policy=RetryPolicy(max_attempts=max_attempts, backoff_seconds=0.0))
    adapter = FakeAdapter(tools=(contract,), fail_identities=fail_identities)
    registry.register_adapter(adapter)
    return registry, adapter


class TestToolRuntimeExecute(unittest.TestCase):
    def test_successful_execution(self):
        registry, _ = _setup()
        runtime = ToolRuntime(registry, sleep_fn=lambda s: None)

        result = runtime.execute("fake", "demo", {"x": 1}, caller="agent-a")

        self.assertEqual(result.status, "success")
        self.assertEqual(result.attempts, 1)

    def test_unknown_tool_raises(self):
        registry = UniversalToolRegistry()
        runtime = ToolRuntime(registry, sleep_fn=lambda s: None)

        with self.assertRaises(ToolNotFoundError):
            runtime.execute("fake", "nonexistent", {})

    def test_retry_exhaustion_returns_error_result(self):
        # FakeAdapter fails deterministically every attempt for a given
        # identity, so this exercises retry exhaustion, not a flaky
        # success-on-retry (real transport-level retry recovery is
        # covered by the MCP/REST adapter tests instead).
        registry, adapter = _setup(max_attempts=3, fail_identities=("demo",))
        runtime = ToolRuntime(registry, sleep_fn=lambda s: None)

        result = runtime.execute("fake", "demo", {})

        self.assertEqual(result.status, "error")
        self.assertEqual(result.attempts, 3)
        self.assertEqual(adapter.invocation_count, 3)


class TestToolRuntimeAccessControl(unittest.TestCase):
    def test_denied_caller_blocked_before_invocation(self):
        registry, adapter = _setup()
        policy = SecurityPolicy(access_control=AccessControlPolicy(allowed_callers=("trusted-agent",)))
        runtime = ToolRuntime(registry, security_policies={"fake:demo": policy}, sleep_fn=lambda s: None)

        result = runtime.execute("fake", "demo", {}, caller="untrusted-agent")

        self.assertEqual(result.status, "denied")
        self.assertEqual(adapter.invocation_count, 0)

    def test_allowed_caller_proceeds(self):
        registry, adapter = _setup()
        policy = SecurityPolicy(access_control=AccessControlPolicy(allowed_callers=("trusted-agent",)))
        runtime = ToolRuntime(registry, security_policies={"fake:demo": policy}, sleep_fn=lambda s: None)

        result = runtime.execute("fake", "demo", {}, caller="trusted-agent")

        self.assertEqual(result.status, "success")

    def test_untrusted_tool_requiring_sandbox_is_denied_not_run_unsandboxed(self):
        registry, adapter = _setup()
        policy = SecurityPolicy(trust_level="untrusted", require_sandbox=True)
        runtime = ToolRuntime(registry, security_policies={"fake:demo": policy}, sleep_fn=lambda s: None)

        result = runtime.execute("fake", "demo", {})

        self.assertEqual(result.status, "denied")
        self.assertEqual(adapter.invocation_count, 0)


class TestToolRuntimeApprovalGate(unittest.TestCase):
    def test_denied_approval_blocks_execution(self):
        registry, adapter = _setup()
        gate = ApprovalGate(policy="always_ask", callback=lambda task: False)
        runtime = ToolRuntime(registry, approval_gate=gate, sleep_fn=lambda s: None)

        result = runtime.execute("fake", "demo", {})

        self.assertEqual(result.status, "denied")
        self.assertEqual(adapter.invocation_count, 0)

    def test_allowed_approval_proceeds(self):
        registry, _ = _setup()
        gate = ApprovalGate(policy="always_ask", callback=lambda task: True)
        runtime = ToolRuntime(registry, approval_gate=gate, sleep_fn=lambda s: None)

        result = runtime.execute("fake", "demo", {})

        self.assertEqual(result.status, "success")

    def test_approval_callback_can_see_the_actual_call_input(self):
        # Regression test: the synthesized Task's `.input` must embed the
        # real tool-call arguments, not just a generic description --
        # examples/quickstart.py caught a version that silently let a
        # "block anything mentioning production" callback through
        # because it only ever saw a static string.
        registry, _ = _setup()
        gate = ApprovalGate(policy="always_ask", callback=lambda task: "production" not in task.input.lower())
        runtime = ToolRuntime(registry, approval_gate=gate, sleep_fn=lambda s: None)

        safe = runtime.execute("fake", "demo", {"title": "add a cache"})
        risky = runtime.execute("fake", "demo", {"title": "deploy to production"})

        self.assertEqual(safe.status, "success")
        self.assertEqual(risky.status, "denied")


class TestToolRuntimeMemoryIntegration(unittest.TestCase):
    def test_records_short_term_last_tool_call(self):
        registry, _ = _setup()
        memory = InMemoryMemoryPolicy()
        runtime = ToolRuntime(registry, memory=memory, sleep_fn=lambda s: None)

        runtime.execute("fake", "demo", {})

        self.assertEqual(memory.recall("short_term", "last_tool_call"), "fake:demo")

    def test_no_memory_configured_does_not_raise(self):
        registry, _ = _setup()
        runtime = ToolRuntime(registry, sleep_fn=lambda s: None)
        runtime.execute("fake", "demo", {})  # must not raise


class TestToolRuntimeEventsAndMetrics(unittest.TestCase):
    def test_publishes_executed_event(self):
        registry, _ = _setup()
        bus = EventBus()
        received = []
        bus.subscribe("integration.tool.executed", lambda e: received.append(e))
        runtime = ToolRuntime(registry, event_bus=bus, sleep_fn=lambda s: None)

        runtime.execute("fake", "demo", {})

        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].payload["status"], "success")

    def test_publishes_denied_event(self):
        registry, _ = _setup()
        bus = EventBus()
        received = []
        bus.subscribe("integration.tool.denied", lambda e: received.append(e))
        gate = ApprovalGate(policy="always_ask", callback=lambda task: False)
        runtime = ToolRuntime(registry, approval_gate=gate, event_bus=bus, sleep_fn=lambda s: None)

        runtime.execute("fake", "demo", {})

        self.assertEqual(len(received), 1)

    def test_records_metrics(self):
        registry, _ = _setup()
        runtime = ToolRuntime(registry, sleep_fn=lambda s: None)

        runtime.execute("fake", "demo", {})

        self.assertEqual(runtime.metrics.call_count("fake:demo"), 1)


if __name__ == "__main__":
    unittest.main()
