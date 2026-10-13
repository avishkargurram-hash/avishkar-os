"""LangGraph-shaped reusable nodes -- SS9 of the requirement list.

A LangGraph node is, by LangGraph's own public contract, a plain
Callable[[State], PartialState]. Every function below returns exactly
that shape, with NO import of the `langgraph` package anywhere in this
module (ADR-0011 SS2) -- a caller wires the returned function into their
own StateGraph once they have langgraph installed. This is deliberately
NOT "LangGraph-native orchestration" (that remains langgraph-factory's
job, still deferred per ADR-0009) -- it's reusable building blocks that
happen to fit LangGraph's node shape today, with zero dependency cost.
"""

from __future__ import annotations

from typing import Any, Callable, Dict

from avishkar_agent import ApprovalGate, Task

from .runtime import ToolRuntime

StateDict = Dict[str, Any]
NodeFn = Callable[[StateDict], StateDict]


def make_tool_execution_node(
    runtime: ToolRuntime,
    protocol: str,
    identity: str,
    *,
    input_key: str = "tool_input",
    output_key: str = "tool_output",
) -> NodeFn:
    def node(state: StateDict) -> StateDict:
        result = runtime.execute(protocol, identity, state.get(input_key), caller=state.get("caller"))
        return {output_key: result}

    return node


def make_mcp_call_node(runtime: ToolRuntime, identity: str, **kwargs: Any) -> NodeFn:
    return make_tool_execution_node(runtime, "mcp", identity, **kwargs)


def make_rest_call_node(runtime: ToolRuntime, identity: str, **kwargs: Any) -> NodeFn:
    return make_tool_execution_node(runtime, "rest", identity, **kwargs)


def make_retry_node(inner: NodeFn, *, max_attempts: int = 3, is_success: Callable[[StateDict], bool]) -> NodeFn:
    """Wraps another node, re-running it (merged into state each time)
    until `is_success` passes or attempts are exhausted.
    """

    def node(state: StateDict) -> StateDict:
        merged = dict(state)
        for _ in range(max(1, max_attempts)):
            merged = {**merged, **inner(merged)}
            if is_success(merged):
                break
        return merged

    return node


def make_approval_node(approval_gate: ApprovalGate, *, task_factory: Callable[[StateDict], Task]) -> NodeFn:
    def node(state: StateDict) -> StateDict:
        task = task_factory(state)
        return {"approved": approval_gate.evaluate(task)}

    return node


def make_logging_node(logger: Any, *, message: str = "node executed") -> NodeFn:
    def node(state: StateDict) -> StateDict:
        logger.info(message, state_keys=sorted(state.keys()))
        return {}

    return node
