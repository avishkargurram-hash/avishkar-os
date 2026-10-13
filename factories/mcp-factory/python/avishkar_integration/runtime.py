"""ToolRuntime -- registers/discovers/executes/routes tool calls, with
retries, logging, metrics, cost tracking, memory integration, and
human-in-the-loop approval. See CONTRACT.md SS5.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Mapping, Optional

from avishkar_agent import ApprovalGate, MemoryPolicy, Task
from avishkar_core import get_logger

from .errors import ProtocolInvocationError
from .metrics import MetricsCollector
from .policies import SecurityPolicy
from .registry import UniversalToolRegistry
from .types import ToolExecutionRequest, ToolExecutionResult


def _approval_task_for(protocol: str, identity: str, input: Any, caller: Optional[str]) -> Task:
    """Synthesizes a Task representing a pending tool call, so
    avishkar_agent.ApprovalGate -- built for agent-level HITL -- can be
    reused unchanged at the tool-execution boundary (ADR-0011 SS7)
    instead of duplicating a near-identical class.

    The actual call `input` is embedded directly in `task.input`, not
    only in `task.context["tool_input"]` -- a content-based approval
    callback (e.g. "deny anything mentioning production") naturally
    inspects `task.input`, matching how agent-level ApprovalGate callbacks
    already work. An earlier version omitted this and a callback checking
    task.input silently never saw the real arguments -- caught by
    examples/quickstart.py, not invented for show; regression-tested in
    test_runtime.py.
    """
    return Task(
        input=f"Execute tool '{protocol}:{identity}' with input: {input!r}",
        context={"tool_input": input},
        task_type=protocol,
        metadata={"caller": caller} if caller else {},
    )


class ToolRuntime:
    def __init__(
        self,
        registry: UniversalToolRegistry,
        *,
        security_policies: Optional[Mapping[str, SecurityPolicy]] = None,
        approval_gate: Optional[ApprovalGate] = None,
        memory: Optional[MemoryPolicy] = None,
        event_bus: Optional[Any] = None,
        metrics: Optional[MetricsCollector] = None,
        sleep_fn: Callable[[float], None] = time.sleep,
        logger: Optional[Any] = None,
    ) -> None:
        self._registry = registry
        self._security_policies = dict(security_policies or {})
        self._approval_gate = approval_gate
        self._memory = memory
        self._event_bus = event_bus
        self._metrics = metrics or MetricsCollector()
        self._sleep_fn = sleep_fn
        self._logger = logger or get_logger("integration.runtime")

    @property
    def metrics(self) -> MetricsCollector:
        return self._metrics

    def execute(
        self,
        protocol: str,
        identity: str,
        input: Any,
        *,
        caller: Optional[str] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> ToolExecutionResult:
        contract = self._registry.get(protocol, identity)  # raises ToolNotFoundError -- a caller bug
        key = contract.qualified_name
        metadata = metadata or {}

        policy = self._security_policies.get(key) or self._security_policies.get(protocol)
        if policy is not None:
            if not policy.access_control.is_allowed(caller):
                return self._denied(contract, "access_control: caller not permitted")
            if policy.trust_level == "untrusted" and policy.require_sandbox:
                return self._denied(
                    contract,
                    "untrusted tool requires sandboxed execution, which v1 does not implement -- "
                    "denying rather than running unsandboxed (see README.md Limitations)",
                )

        if self._approval_gate is not None:
            task = _approval_task_for(protocol, identity, input, caller)
            if not self._approval_gate.evaluate(task):
                return self._denied(contract, "approval_gate: denied by human-in-the-loop reviewer")

        adapter = self._registry.get_adapter(protocol)
        max_attempts = max(1, contract.retry_policy.max_attempts)
        last_result: Optional[ToolExecutionResult] = None

        for attempt in range(1, max_attempts + 1):
            start = time.monotonic()
            try:
                result = adapter.invoke(contract, ToolExecutionRequest(input=input, caller=caller, metadata=metadata))
            except ProtocolInvocationError as exc:
                elapsed_ms = (time.monotonic() - start) * 1000
                result = ToolExecutionResult(
                    tool_identity=identity, protocol=protocol, status="error",
                    error=str(exc), latency_ms=elapsed_ms, attempts=attempt,
                )
            self._record(contract, result, attempt)
            last_result = result
            if result.status == "success":
                return result
            if attempt < max_attempts:
                self._logger.info(
                    "Tool call failed, retrying", tool=key, attempt=attempt, status=result.status
                )
                self._sleep_fn(contract.retry_policy.backoff_seconds)

        assert last_result is not None  # loop runs at least once
        return last_result

    def _denied(self, contract, reason: str) -> ToolExecutionResult:
        result = ToolExecutionResult(
            tool_identity=contract.identity, protocol=contract.protocol,
            status="denied", error=reason, latency_ms=0.0, attempts=0,
        )
        self._logger.warning("Tool call denied", tool=contract.qualified_name, reason=reason)
        if self._event_bus is not None:
            self._event_bus.publish(
                "integration.tool.denied", {"tool": contract.qualified_name, "reason": reason}, source="tool-runtime"
            )
        return result

    def _record(self, contract, result: ToolExecutionResult, attempt: int) -> None:
        cost = float(contract.protocol_config.get("cost_per_call", 0.0))
        self._metrics.record(contract.qualified_name, status=result.status, latency_ms=result.latency_ms, cost=cost)
        self._logger.info(
            "Tool executed", tool=contract.qualified_name, attempt=attempt,
            status=result.status, latency_ms=round(result.latency_ms, 2),
        )
        if self._event_bus is not None:
            self._event_bus.publish(
                "integration.tool.executed",
                {"tool": contract.qualified_name, "status": result.status, "attempt": attempt},
                source="tool-runtime",
            )
        if self._memory is not None:
            self._memory.remember("short_term", "last_tool_call", contract.qualified_name)
            self._memory.remember(
                "episodic",
                f"{contract.qualified_name}:{time.time()}",
                {"status": result.status, "output": result.output, "attempt": attempt},
            )
