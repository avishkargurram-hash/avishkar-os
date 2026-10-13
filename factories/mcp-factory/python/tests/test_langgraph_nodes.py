import unittest

from avishkar_agent import ApprovalGate, Task
from avishkar_core import get_logger
from avishkar_integration import (
    ToolRuntime,
    UniversalToolRegistry,
    make_approval_node,
    make_logging_node,
    make_mcp_call_node,
    make_rest_call_node,
    make_retry_node,
    make_tool_execution_node,
)

from fixtures import FakeAdapter, make_contract


def _runtime():
    registry = UniversalToolRegistry()
    registry.register_adapter(FakeAdapter(tools=(make_contract("demo", protocol="mcp"),), protocol_name="mcp"))
    return ToolRuntime(registry, sleep_fn=lambda s: None)


class TestToolExecutionNode(unittest.TestCase):
    def test_node_is_a_plain_function_of_state(self):
        node = make_tool_execution_node(_runtime(), "mcp", "demo")

        result_state = node({"tool_input": {"x": 1}})

        self.assertIn("tool_output", result_state)
        self.assertEqual(result_state["tool_output"].status, "success")

    def test_custom_keys(self):
        node = make_tool_execution_node(_runtime(), "mcp", "demo", input_key="in", output_key="out")

        result_state = node({"in": {"x": 1}})

        self.assertIn("out", result_state)


class TestMcpAndRestConvenienceNodes(unittest.TestCase):
    def test_mcp_call_node_uses_mcp_protocol(self):
        node = make_mcp_call_node(_runtime(), "demo")
        result_state = node({"tool_input": {}})
        self.assertEqual(result_state["tool_output"].protocol, "mcp")

    def test_rest_call_node_uses_rest_protocol(self):
        registry = UniversalToolRegistry()
        registry.register_adapter(
            FakeAdapter(tools=(make_contract("demo-rest", protocol="rest"),), protocol_name="rest")
        )
        runtime = ToolRuntime(registry, sleep_fn=lambda s: None)

        node = make_rest_call_node(runtime, "demo-rest")
        result_state = node({"tool_input": {}})

        self.assertEqual(result_state["tool_output"].protocol, "rest")


class TestRetryNode(unittest.TestCase):
    def test_stops_once_is_success(self):
        calls = {"n": 0}

        def inner(state):
            calls["n"] += 1
            return {"attempt": calls["n"]}

        node = make_retry_node(inner, max_attempts=5, is_success=lambda state: state.get("attempt", 0) >= 2)

        result_state = node({})

        self.assertEqual(result_state["attempt"], 2)
        self.assertEqual(calls["n"], 2)

    def test_exhausts_attempts_if_never_successful(self):
        calls = {"n": 0}

        def inner(state):
            calls["n"] += 1
            return {"attempt": calls["n"]}

        node = make_retry_node(inner, max_attempts=3, is_success=lambda state: False)
        node({})

        self.assertEqual(calls["n"], 3)


class TestApprovalNode(unittest.TestCase):
    def test_records_approval_decision(self):
        gate = ApprovalGate(policy="always_ask", callback=lambda task: True)
        node = make_approval_node(gate, task_factory=lambda state: Task(input=state["request"]))

        result_state = node({"request": "deploy service X"})

        self.assertTrue(result_state["approved"])

    def test_records_denial(self):
        gate = ApprovalGate(policy="always_ask", callback=lambda task: False)
        node = make_approval_node(gate, task_factory=lambda state: Task(input=state["request"]))

        result_state = node({"request": "deploy service X"})

        self.assertFalse(result_state["approved"])


class TestLoggingNode(unittest.TestCase):
    def test_returns_no_state_change(self):
        node = make_logging_node(get_logger("test.langgraph"))

        result_state = node({"a": 1, "b": 2})

        self.assertEqual(result_state, {})


if __name__ == "__main__":
    unittest.main()
