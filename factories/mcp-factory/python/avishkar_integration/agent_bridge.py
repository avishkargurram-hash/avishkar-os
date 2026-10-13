"""Agent Integration -- lets a Chief Domain Agent consume tools without
knowing the underlying protocol. See CONTRACT.md SS7 and DECISIONS.md
ADR-0011 SS7 (this module is a new consumer of agent-factory's already-
public types; agent-factory's own source is never modified).
"""

from __future__ import annotations

from avishkar_agent import MCPToolRef

from .errors import NoMatchingToolError, ToolNotFoundError
from .registry import UniversalToolRegistry
from .types import ToolContract


def resolve_mcp_tool_ref(ref: MCPToolRef, registry: UniversalToolRegistry) -> ToolContract:
    """Resolves an agent-declared MCPToolRef (agent-factory CONTRACT.md
    SS4) against a real registry -- the seam agent-factory always
    intended for once an MCP adapter exists.
    """
    try:
        return registry.get("mcp", ref.tool_name)
    except ToolNotFoundError as exc:
        raise ToolNotFoundError(
            f"MCPToolRef(server={ref.server!r}, tool_name={ref.tool_name!r}) does not resolve against "
            f"any tool registered in this UniversalToolRegistry"
        ) from exc


def request_capability(registry: UniversalToolRegistry, capability: str) -> ToolContract:
    """The "agents request capabilities, not implementations" entry
    point -- call this instead of naming a specific protocol/tool.
    """
    matches = registry.find_by_capability(capability)
    if not matches:
        raise NoMatchingToolError(f"No registered tool matches capability '{capability}'")
    return matches[0]
