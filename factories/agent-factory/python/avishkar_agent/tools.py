"""ToolRegistry -- concrete and MCP-declared tools a ChiefDomainAgent can
invoke. See CONTRACT.md SS4 (Tool Registry, SS10 of the agent template)
and SS9 (MCP Integration Points).
"""

from __future__ import annotations

import dataclasses
from typing import Any, Callable, Dict, Optional, Union

from .errors import MCPServerNotAvailableError, ToolNotFoundError


@dataclasses.dataclass(frozen=True)
class Tool:
    """A concrete, callable tool this framework can invoke directly."""

    name: str
    call: Callable[[Any], Any]
    description: str = ""


@dataclasses.dataclass(frozen=True)
class MCPToolRef:
    """A DECLARED, not-yet-resolvable tool reference -- this is what
    "MCP-native" means at this stage of the platform: the typed extension
    point exists and a blueprint can declare it, even though no `mcp/`
    server is built yet (that's Phase 4). Calling one raises
    MCPServerNotAvailableError -- a clear, typed failure, not a crash or
    a silent no-op.
    """

    server: str
    tool_name: str
    description: str = ""

    @property
    def name(self) -> str:
        return f"mcp:{self.server}/{self.tool_name}"


RegisteredEntry = Union[Tool, MCPToolRef]


class ToolRegistry:
    """The set of tools one ChiefDomainAgent (or the framework generally)
    can call by name.
    """

    def __init__(self) -> None:
        self._entries: Dict[str, RegisteredEntry] = {}

    def register(self, entry: RegisteredEntry) -> None:
        self._entries[entry.name] = entry

    def get(self, name: str) -> Optional[RegisteredEntry]:
        return self._entries.get(name)

    def list_names(self) -> tuple:
        return tuple(self._entries.keys())

    def call(self, name: str, input: Any) -> Any:
        entry = self._entries.get(name)
        if entry is None:
            raise ToolNotFoundError(f"No tool named '{name}' is registered")
        if isinstance(entry, MCPToolRef):
            raise MCPServerNotAvailableError(
                f"Tool '{name}' is declared against MCP server '{entry.server}', "
                f"which isn't available yet (mcp-factory is Phase 4 -- see ROADMAP.md). "
                f"This is a typed placeholder, not a bug."
            )
        return entry.call(input)
