"""Orchestrator -- the multi-agent coordination layer: single-agent
routing, hierarchical teams, swarm broadcast, and conflict resolution.
See CONTRACT.md SS7.

The Orchestrator is "the CEO of the agent ecosystem": it knows about
registered ChiefDomainAgent instances and named strategies only -- never
about any specific product's business logic (ARCHITECTURE.md SS1).
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Mapping, Optional, Sequence

from avishkar_core import get_logger

from .agent import ChiefDomainAgent
from .errors import DuplicateAgentError, NoMatchingAgentError, UnknownAgentError
from .memory import MemoryPolicy
from .types import AgentResult, Task

ConflictStrategy = Callable[[Mapping[str, AgentResult]], AgentResult]


def _first_completed(results: Mapping[str, AgentResult]) -> AgentResult:
    for result in results.values():
        if result.status == "completed":
            return result
    raise NoMatchingAgentError("No candidate result has status 'completed'")


def _prefer_agent(agent_name: str) -> ConflictStrategy:
    def _resolve(results: Mapping[str, AgentResult]) -> AgentResult:
        if agent_name not in results:
            raise UnknownAgentError(f"'{agent_name}' is not among the results being resolved: {list(results)}")
        return results[agent_name]

    return _resolve


class Orchestrator:
    """Coordinates a fixed set of registered ChiefDomainAgent instances.
    See CONTRACT.md SS7 for route/delegate_team/broadcast semantics.
    """

    def __init__(
        self,
        agents: Sequence[ChiefDomainAgent],
        *,
        shared_memory: Optional[MemoryPolicy] = None,
        event_bus: Optional[Any] = None,
        logger: Optional[Any] = None,
    ) -> None:
        self._agents: Dict[str, ChiefDomainAgent] = {}
        for agent in agents:
            if agent.name in self._agents:
                raise DuplicateAgentError(
                    f"Agent name '{agent.name}' is registered twice with this Orchestrator"
                )
            self._agents[agent.name] = agent
        self._shared_memory = shared_memory
        self._event_bus = event_bus
        self._logger = logger or get_logger("orchestrator")

    def list_agents(self) -> tuple:
        return tuple(self._agents.keys())

    def route(self, task: Task) -> AgentResult:
        """Single-agent dispatch. Requires task.task_type to disambiguate
        whenever more than one agent is registered -- this Orchestrator
        never guesses which agent a task means when more than one could
        plausibly handle it (see CONTRACT.md SS7).
        """
        agent = self._match_one(task)
        self._logger.info("Routed task", agent=agent.name, task_type=task.task_type)
        if self._event_bus is not None:
            self._event_bus.publish("orchestrator.routed", {"agent": agent.name}, source="orchestrator")
        return agent.handle(task)

    def delegate_team(self, task: Task, agent_names: Sequence[str]) -> Dict[str, AgentResult]:
        """Hierarchical team: the same task, dispatched to every named
        agent in order, results collected. v1 does not auto-decompose the
        task per agent -- see README.md Future Roadmap.
        """
        results: Dict[str, AgentResult] = {}
        for name in agent_names:
            agent = self._require_agent(name)
            results[name] = agent.handle(task)
        if self._event_bus is not None:
            self._event_bus.publish(
                "orchestrator.team.completed", {"agents": list(agent_names)}, source="orchestrator"
            )
        return results

    def broadcast(self, task: Task, agent_names: Sequence[str]) -> Dict[str, AgentResult]:
        """Swarm: the same task to every named agent, independently, for
        comparison/voting. v1 runs candidates sequentially (concurrency
        is a Future Roadmap item, not a correctness requirement here).
        """
        results: Dict[str, AgentResult] = {}
        for name in agent_names:
            agent = self._require_agent(name)
            results[name] = agent.handle(task)
        if self._event_bus is not None:
            self._event_bus.publish(
                "orchestrator.broadcast.completed", {"agents": list(agent_names)}, source="orchestrator"
            )
        return results

    def resolve_conflict(self, results: Mapping[str, AgentResult], strategy: str) -> AgentResult:
        """Named, pluggable conflict-resolution strategies -- not
        hardcoded to one policy. Supported: "first_completed" and
        "prefer_agent:<name>".
        """
        if strategy == "first_completed":
            return _first_completed(results)
        if strategy.startswith("prefer_agent:"):
            agent_name = strategy.split(":", 1)[1]
            return _prefer_agent(agent_name)(results)
        raise ValueError(f"Unknown conflict resolution strategy: {strategy!r}")

    def _require_agent(self, name: str) -> ChiefDomainAgent:
        agent = self._agents.get(name)
        if agent is None:
            raise UnknownAgentError(f"No agent named '{name}' is registered with this Orchestrator")
        return agent

    def _match_one(self, task: Task) -> ChiefDomainAgent:
        if task.task_type is not None:
            if task.task_type in self._agents:
                return self._agents[task.task_type]
            domain_matches = [
                name for name, agent in self._agents.items() if task.task_type.lower() in agent.domain.lower()
            ]
            if len(domain_matches) == 1:
                return self._agents[domain_matches[0]]
            if len(domain_matches) > 1:
                raise NoMatchingAgentError(
                    f"task_type '{task.task_type}' matches multiple agents {domain_matches} -- "
                    f"address one by its exact name, or use delegate_team()/broadcast()"
                )
            raise NoMatchingAgentError(f"No agent matches task_type '{task.task_type}'")
        if len(self._agents) == 1:
            return next(iter(self._agents.values()))
        raise NoMatchingAgentError(
            "task.task_type is required to route among multiple registered agents "
            "-- this Orchestrator never guesses"
        )
