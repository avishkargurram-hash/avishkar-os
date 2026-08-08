"""Integration bridges to agent-factory, memory-factory, and
knowledge-factory. See CONTRACT.md SS6.

Each `make_*_step` is a pure consumer of an earlier framework's already-
public types -- no changes to agent-factory, memory-factory, or
knowledge-factory source, the same dependency-direction discipline
ADR-0011 SS3 established for mcp-factory's agent bridge.
"""

from __future__ import annotations

from typing import Optional

from avishkar_agent import ChiefDomainAgent, MemoryPolicy, Task
from avishkar_knowledge import KnowledgeBase

from .types import NodeFn, State


def make_agent_step(
    agent: ChiefDomainAgent,
    *,
    input_key: str = "input",
    output_key: str = "output",
    task_type: Optional[str] = None,
) -> NodeFn:
    """Runs a ChiefDomainAgent.handle() call as a workflow step."""

    def step(state: State) -> dict:
        task = Task(input=state[input_key], task_type=task_type)
        result = agent.handle(task)
        return {output_key: result}

    return step


def make_knowledge_search_step(
    kb: KnowledgeBase,
    *,
    query_key: str = "query",
    results_key: str = "knowledge_results",
    top_k: int = 5,
) -> NodeFn:
    """Runs a KnowledgeBase.search() call as a workflow step."""

    def step(state: State) -> dict:
        results = kb.search(state[query_key], top_k=top_k)
        return {results_key: results}

    return step


def make_memory_read_step(
    memory: MemoryPolicy,
    kind: str,
    *,
    key_from_state: str,
    output_key: str,
) -> NodeFn:
    """Reads one value from a MemoryPolicy as a workflow step."""

    def step(state: State) -> dict:
        value = memory.recall(kind, state[key_from_state])
        return {output_key: value}

    return step


def make_memory_write_step(
    memory: MemoryPolicy,
    kind: str,
    *,
    key_from_state: str,
    value_from_state: str,
) -> NodeFn:
    """Writes one value into a MemoryPolicy as a workflow step.

    Returns an empty partial update -- writing memory is a side effect,
    not new workflow state.
    """

    def step(state: State) -> dict:
        memory.remember(kind, state[key_from_state], state[value_from_state])
        return {}

    return step
