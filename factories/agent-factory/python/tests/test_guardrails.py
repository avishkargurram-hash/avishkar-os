import unittest

from avishkar_agent import ApprovalGate, AgentResult, Guardrail, QualityGate, Task


def _task(**kwargs):
    kwargs.setdefault("input", "delete production database")
    return Task(**kwargs)


def _result(status="completed"):
    return AgentResult(
        output="done",
        agent_name="test-agent",
        thinking_trace=(),
        tool_calls=(),
        iterations=1,
        status=status,
        cost_usd=0.0,
    )


class TestGuardrail(unittest.TestCase):
    def test_allows_when_check_returns_none(self):
        guardrail = Guardrail(name="no-op", check=lambda task: None)
        self.assertIsNone(guardrail.check(_task()))

    def test_blocks_with_reason(self):
        guardrail = Guardrail(name="destructive-action", check=lambda task: "destructive keyword detected")
        self.assertEqual(guardrail.check(_task()), "destructive keyword detected")


class TestQualityGate(unittest.TestCase):
    def test_passes(self):
        gate = QualityGate(name="non-empty", check=lambda result: len(result.output) > 0)
        self.assertTrue(gate.check(_result()))

    def test_fails(self):
        gate = QualityGate(name="always-fail", check=lambda result: False)
        self.assertFalse(gate.check(_result()))


class TestApprovalGate(unittest.TestCase):
    def test_always_allow_evaluates_true_without_callback(self):
        gate = ApprovalGate(policy="always_allow")
        self.assertTrue(gate.evaluate(_task()))

    def test_always_ask_uses_callback_allow(self):
        gate = ApprovalGate(policy="always_ask", callback=lambda task: True)
        self.assertTrue(gate.evaluate(_task()))

    def test_always_ask_uses_callback_deny(self):
        gate = ApprovalGate(policy="always_ask", callback=lambda task: False)
        self.assertFalse(gate.evaluate(_task()))

    def test_always_ask_without_callback_raises(self):
        with self.assertRaises(ValueError):
            ApprovalGate(policy="always_ask")

    def test_invalid_policy_raises(self):
        with self.assertRaises(ValueError):
            ApprovalGate(policy="sometimes")


if __name__ == "__main__":
    unittest.main()
