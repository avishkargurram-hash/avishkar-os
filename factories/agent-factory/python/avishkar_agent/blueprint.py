"""AgentBlueprint -- the declarative definition of a Chief Domain Agent.
See CONTRACT.md SS2 and schemas/agent-blueprint.schema.json.

A blueprint is data; the behavior it names (guardrails, quality gates,
thinking strategies) lives in the domain module that constructs the
ChiefDomainAgent, resolved by name at construction time. This
indirection is what lets a new Chief Domain Agent plug in without
modifying this framework -- see README.md Extension Model.
"""

from __future__ import annotations

import dataclasses
import json
import re
from pathlib import Path
from typing import Any, Dict, Mapping, Tuple, Union

from .errors import InvalidBlueprintError

_NAME_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+(-[a-zA-Z0-9.]+)?$")


@dataclasses.dataclass(frozen=True)
class MemoryPolicyConfig:
    """Which memory backend a blueprint requests. v1 only 'in_memory'
    resolves to a real implementation -- see memory.py.
    """

    backend: str = "in_memory"


@dataclasses.dataclass(frozen=True)
class BlueprintToolRef:
    """A blueprint-level tool declaration -- either a concrete tool name
    (resolved against the domain module's ToolRegistry) or an MCP
    reference (kind="mcp").
    """

    kind: str  # "tool" | "mcp"
    name: str = ""
    server: str = ""
    tool_name: str = ""


@dataclasses.dataclass(frozen=True)
class AgentBlueprint:
    """See CONTRACT.md SS2 for the full field-by-field contract."""

    name: str
    domain: str
    version: str
    mission: str
    default_model: str
    memory_policy: MemoryPolicyConfig = dataclasses.field(default_factory=MemoryPolicyConfig)
    reasoning_strategies: Tuple[str, ...] = ()
    max_iterations: int = 5
    tools: Tuple[BlueprintToolRef, ...] = ()
    guardrails: Tuple[str, ...] = ()
    quality_gates: Tuple[str, ...] = ()
    sub_agent_roles: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not _NAME_PATTERN.match(self.name):
            raise InvalidBlueprintError(f"Blueprint name '{self.name}' must be kebab-case")
        if not _VERSION_PATTERN.match(self.version):
            raise InvalidBlueprintError(f"Blueprint version '{self.version}' must be semantic (x.y.z)")
        if not self.mission.strip():
            raise InvalidBlueprintError(f"Blueprint '{self.name}' has an empty mission")
        if self.max_iterations < 1:
            raise InvalidBlueprintError(f"Blueprint '{self.name}' max_iterations must be >= 1")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AgentBlueprint":
        raw_tools = data.get("tools", ())
        tools = tuple(_tool_ref_from_dict(t) for t in raw_tools)
        raw_memory = data.get("memory_policy", {}) or {}
        memory_policy = MemoryPolicyConfig(backend=raw_memory.get("backend", "in_memory"))
        try:
            return cls(
                name=data["name"],
                domain=data["domain"],
                version=data["version"],
                mission=data["mission"],
                default_model=data["default_model"],
                memory_policy=memory_policy,
                reasoning_strategies=tuple(data.get("reasoning_strategies", ())),
                max_iterations=data.get("max_iterations", 5),
                tools=tools,
                guardrails=tuple(data.get("guardrails", ())),
                quality_gates=tuple(data.get("quality_gates", ())),
                sub_agent_roles=tuple(data.get("sub_agent_roles", ())),
            )
        except KeyError as exc:
            raise InvalidBlueprintError(f"Blueprint is missing required field: {exc}") from exc

    @classmethod
    def from_file(cls, path: Union[str, Path]) -> "AgentBlueprint":
        text = Path(path).read_text(encoding="utf-8")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise InvalidBlueprintError(f"Blueprint file '{path}' is not valid JSON: {exc}") from exc
        return cls.from_dict(data)


def _tool_ref_from_dict(data: Dict[str, Any]) -> BlueprintToolRef:
    kind = data.get("kind")
    if kind == "tool":
        return BlueprintToolRef(kind="tool", name=data["name"])
    if kind == "mcp":
        return BlueprintToolRef(kind="mcp", server=data["server"], tool_name=data["tool_name"])
    raise InvalidBlueprintError(f"Unknown tool ref kind: {kind!r} (expected 'tool' or 'mcp')")
