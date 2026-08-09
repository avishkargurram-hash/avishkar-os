import tempfile
import unittest
from pathlib import Path

from avishkar_agent import MCPServerNotAvailableError, Task
from avishkar_router import ModelSpec, MockProvider, RoutingPolicy, Router

from finance_economics_agent import (
    _calculate_debt_to_equity_ratio,
    _classify_risk_level,
    _no_executing_trades,
    build_finance_economics_agent,
    load_blueprint,
)


def _router(response_text: str = "This is not investment advice -- consult a financial advisor.") -> Router:
    provider = MockProvider(
        models=(ModelSpec(model_id="mock-fast", provider="mock", capabilities=("chat", "tools"),
                           input_cost_per_mtok=1.0, output_cost_per_mtok=1.0,
                           max_context_tokens=8192, max_output_tokens=2048),),
        response_text=response_text,
    )
    return Router([provider], RoutingPolicy(default_model="mock-fast"))


class TestBlueprint(unittest.TestCase):
    def test_loads_committed_blueprint(self):
        blueprint = load_blueprint()
        self.assertEqual(blueprint.name, "finance-economics")
        self.assertIn("risk-modeler", blueprint.sub_agent_roles)


class TestCalculateDebtToEquityRatioTool(unittest.TestCase):
    def test_computes_ratio(self):
        self.assertEqual(_calculate_debt_to_equity_ratio(200.0, 100.0), 2.0)

    def test_zero_equity_raises(self):
        with self.assertRaises(ZeroDivisionError):
            _calculate_debt_to_equity_ratio(100.0, 0.0)


class TestClassifyRiskLevelTool(unittest.TestCase):
    def test_low_risk(self):
        self.assertEqual(_classify_risk_level(5.0), "low")

    def test_medium_risk(self):
        self.assertEqual(_classify_risk_level(15.0), "medium")

    def test_high_risk(self):
        self.assertEqual(_classify_risk_level(30.0), "high")


class TestGuardrail(unittest.TestCase):
    def test_blocks_trade_execution_request(self):
        reason = _no_executing_trades(Task(input="Please execute this trade immediately"))
        self.assertIsNotNone(reason)

    def test_allows_ordinary_question(self):
        self.assertIsNone(_no_executing_trades(Task(input="What's a healthy debt-to-equity ratio?")))


class TestAgentIntegration(unittest.TestCase):
    def _agent(self, tmp):
        return build_finance_economics_agent(_router(), model_override="mock-fast", memory_root_dir=Path(tmp))

    def test_normal_task_completes(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self._agent(tmp).handle(Task(input="What's a healthy debt-to-equity ratio?"))
            self.assertEqual(result.status, "completed")

    def test_trade_execution_request_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self._agent(tmp).handle(Task(input="Please execute this trade immediately"))
            self.assertEqual(result.status, "blocked")

    def test_declared_mcp_tool_raises_typed_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(MCPServerNotAvailableError):
                self._agent(tmp).tools.call("mcp:alpha-vantage/get_market_data", "AAPL")

    def test_knowledge_search_tool_is_callable(self):
        with tempfile.TemporaryDirectory() as tmp:
            results = self._agent(tmp).tools.call("search_finance_references", "how to assess risk")
            self.assertTrue(results)

    def test_sub_agent_routing_to_risk_modeler(self):
        with tempfile.TemporaryDirectory() as tmp:
            role = self._agent(tmp).route_to_sub_agent_role(Task(input="Can the risk-modeler review this?"))
            self.assertEqual(role, "risk-modeler")

    def test_rate_limit_guardrail_blocks_after_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Deterministic clock: every call happens "at the same instant"
            # within the window, so the 11th call within the limit trips.
            agent = build_finance_economics_agent(
                _router(), model_override="mock-fast", memory_root_dir=Path(tmp), rate_limit_clock=lambda: 0.0
            )
            statuses = [agent.handle(Task(input=f"question {i}")).status for i in range(11)]
            self.assertEqual(statuses[:10], ["completed"] * 10)
            self.assertEqual(statuses[10], "blocked")


if __name__ == "__main__":
    unittest.main()
