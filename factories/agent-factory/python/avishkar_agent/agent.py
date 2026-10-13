"""ChiefDomainAgent -- the reasoning-loop runtime every Chief Domain Agent
is built on. See CONTRACT.md SS6 and the agent template's SS4, SS7,
SS18-20 (Reasoning Strategies, Planning & Reflection, Guardrails, Quality
Gates, Error Recovery).

This is the load-bearing claim of ADR-0010: a Chief Domain Agent is a
software system with an inspectable reasoning trace, not a system prompt
that produces a single opaque answer.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Mapping, Optional, Sequence, Tuple

from avishkar_core import get_logger
from avishkar_router import CompletionRequest, Message, Router

from .blueprint import AgentBlueprint
from .guardrails import ApprovalGate, Guardrail, QualityGate
from .memory import MemoryPolicy
from .thinking import ThinkingModel
from .tools import ToolRegistry
from .types import AgentResult, Task, ThinkingStep, ToolCallRecord

#: Default sub-agent routing: naive keyword match against role names,
#: falling back to the first declared role. A domain module may pass its
#: own `sub_agent_router` to ChiefDomainAgent for smarter routing --
#: this default exists so a blueprint with sub_agent_roles is usable
#: out of the box, not so it's the only reasonable policy.
def _default_sub_agent_router(task: Task, roles: Sequence[str]) -> Optional[str]:
    if not roles:
        return None
    # Normalize both sides the same way (hyphens -> spaces) so a role
    # like "security-auditor" matches task text written as "security
    # auditor" AND as "security-auditor" -- matching only one side was a
    # real bug caught by examples/quickstart.py, not a hypothetical.
    haystack = f"{task.input} {task.task_type or ''}".lower().replace("-", " ")
    for role in roles:
        if role.lower().replace("-", " ") in haystack:
            return role
    return roles[0]


class ChiefDomainAgent:
    """A Chief Domain Agent: a blueprint plus the primitives it's wired
    to (router, memory, tools, thinking models, guardrails, quality
    gates, an optional approval gate). See README.md for how a domain
    module assembles one.
    """

    def __init__(
        self,
        blueprint: AgentBlueprint,
        router: Router,
        memory: MemoryPolicy,
        tools: ToolRegistry,
        thinking_models: Sequence[ThinkingModel],
        *,
        guardrails: Sequence[Guardrail] = (),
        quality_gates: Sequence[QualityGate] = (),
        approval_gate: Optional[ApprovalGate] = None,
        sub_agent_router: Callable[[Task, Sequence[str]], Optional[str]] = _default_sub_agent_router,
        event_bus: Optional[Any] = None,
        logger: Optional[Any] = None,
    ) -> None:
        self._blueprint = blueprint
        self._router = router
        self._memory = memory
        self._tools = tools
        self._thinking_models: Dict[str, ThinkingModel] = {tm.name: tm for tm in thinking_models}
        self._guardrails = tuple(guardrails)
        self._quality_gates = tuple(quality_gates)
        self._approval_gate = approval_gate
        self._sub_agent_router = sub_agent_router
        self._event_bus = event_bus
        self._logger = logger or get_logger(f"agent.{blueprint.name}")

    @property
    def name(self) -> str:
        return self._blueprint.name

    @property
    def domain(self) -> str:
        return self._blueprint.domain

    @property
    def blueprint(self) -> AgentBlueprint:
        return self._blueprint

    @property
    def memory(self) -> MemoryPolicy:
        return self._memory

    @property
    def tools(self) -> ToolRegistry:
        return self._tools

    def route_to_sub_agent_role(self, task: Task) -> Optional[str]:
        """Internal routing (agent template SS24): which absorbed expert
        role handles `task`, if any. Never spins up a new top-level
        agent -- see ARCHITECTURE.md SS4.
        """
        return self._sub_agent_router(task, self._blueprint.sub_agent_roles)

    def handle(self, task: Task) -> AgentResult:
        blocked = self._check_guardrails(task)
        if blocked is not None:
            return blocked

        if self._approval_gate is not None and not self._approval_gate.evaluate(task):
            self._logger.warning("Task denied by approval gate", agent=self.name)
            return self._blocked_result("approval_gate: denied by human-in-the-loop reviewer")

        thinking_trace: list = []
        tool_calls: list = []
        total_cost = 0.0
        output = ""
        status = "completed"
        iteration = 0

        strategies = self._blueprint.reasoning_strategies or ("__default__",)

        for iteration in range(1, self._blueprint.max_iterations + 1):
            strategy_name = strategies[(iteration - 1) % len(strategies)]
            plan_step = self._plan(task, strategy_name)
            if plan_step is not None:
                thinking_trace.append(plan_step)

            output, call_cost = self._act(task, thinking_trace)
            total_cost += call_cost

            reflect_step = self._reflect(task, output, iteration)
            thinking_trace.append(reflect_step)

            candidate = AgentResult(
                output=output,
                agent_name=self.name,
                thinking_trace=tuple(thinking_trace),
                tool_calls=tuple(tool_calls),
                iterations=iteration,
                status="completed",
                cost_usd=total_cost,
            )
            failing_gates = [g.name for g in self._quality_gates if not g.check(candidate)]
            if not failing_gates:
                status = "completed"
                break
            self._logger.info(
                "Quality gate(s) failed, considering another iteration",
                agent=self.name,
                failing_gates=failing_gates,
                iteration=iteration,
            )
            if iteration >= self._blueprint.max_iterations:
                status = "failed"

        result = AgentResult(
            output=output,
            agent_name=self.name,
            thinking_trace=tuple(thinking_trace),
            tool_calls=tuple(tool_calls),
            iterations=iteration,
            status=status,
            cost_usd=total_cost,
        )
        self._publish(result)
        return result

    def _check_guardrails(self, task: Task) -> Optional[AgentResult]:
        for guardrail in self._guardrails:
            reason = guardrail.check(task)
            if reason is not None:
                self._logger.warning("Guardrail blocked task", agent=self.name, guardrail=guardrail.name, reason=reason)
                return self._blocked_result(f"{guardrail.name}: {reason}")
        return None

    def _blocked_result(self, reason: str) -> AgentResult:
        result = AgentResult(
            output="",
            agent_name=self.name,
            thinking_trace=(),
            tool_calls=(),
            iterations=0,
            status="blocked",
            blocked_reason=reason,
            cost_usd=0.0,
        )
        self._publish(result)
        return result

    def _plan(self, task: Task, strategy_name: str) -> Optional[ThinkingStep]:
        thinking_model = self._thinking_models.get(strategy_name)
        if thinking_model is None:
            return None
        return thinking_model.apply(task, task.context)

    def _act(self, task: Task, thinking_trace: Sequence[ThinkingStep]) -> Tuple[str, float]:
        approach = thinking_trace[-1].content if thinking_trace else ""
        prompt = (
            f"Mission: {self._blueprint.mission}\n\n"
            f"Task: {task.input}\n\n"
            f"Approach: {approach}"
        )
        # blueprint.default_model is set explicitly (rather than left for
        # the router's own policy to decide) so an agent's behavior stays
        # predictable regardless of how the shared RoutingPolicy changes.
        request = CompletionRequest(
            messages=(Message(role="user", content=prompt),),
            model=self._blueprint.default_model,
            task_type=task.task_type,
            metadata={"caller": self._blueprint.name, **task.metadata},
        )
        response = self._router.route(request)
        return response.content, response.cost_usd

    def _reflect(self, task: Task, output: str, iteration: int) -> ThinkingStep:
        content = (
            f"Iteration {iteration}: produced {len(output)} characters. "
            f"Checking against the task's intent before accepting this as done."
        )
        return ThinkingStep(strategy="reflection", content=content)

    def _publish(self, result: AgentResult) -> None:
        if self._event_bus is None:
            return
        event_type = f"agent.task.{result.status}"
        self._event_bus.publish(
            event_type,
            {"agent": self.name, "iterations": result.iterations, "cost_usd": result.cost_usd},
            source=f"agent.{self.name}",
        )
