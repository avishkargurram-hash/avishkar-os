import unittest

from avishkar_agent import AgentResult

from avishkar_evaluation import EvalCase, EvalSuite, exact_match_scorer, make_quality_gate


def _result(output: str) -> AgentResult:
    return AgentResult(
        output=output, agent_name="demo", thinking_trace=(), tool_calls=(),
        iterations=1, status="completed", cost_usd=0.0,
    )


class TestMakeQualityGate(unittest.TestCase):
    def test_gate_passes_when_output_meets_threshold(self):
        suite = EvalSuite(name="demo", cases=(EvalCase(inputs={}, expected="the answer"),))
        gate = make_quality_gate("exact-match", suite, exact_match_scorer, threshold=1.0)

        self.assertTrue(gate.check(_result("the answer")))

    def test_gate_fails_when_output_misses_threshold(self):
        suite = EvalSuite(name="demo", cases=(EvalCase(inputs={}, expected="the answer"),))
        gate = make_quality_gate("exact-match", suite, exact_match_scorer, threshold=1.0)

        self.assertFalse(gate.check(_result("something else")))

    def test_gate_has_the_given_name(self):
        suite = EvalSuite(name="demo", cases=(EvalCase(inputs={}, expected="x"),))
        gate = make_quality_gate("my-gate", suite, exact_match_scorer, threshold=1.0)
        self.assertEqual(gate.name, "my-gate")


if __name__ == "__main__":
    unittest.main()
