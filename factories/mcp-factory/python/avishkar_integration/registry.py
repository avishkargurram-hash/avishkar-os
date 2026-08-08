"""UniversalToolRegistry -- every tool, across every protocol, addressed
by one common contract. See CONTRACT.md SS3.
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

from avishkar_core import get_logger

from .errors import DuplicateAdapterError, ProtocolMismatchError, ProtocolNotRegisteredError, ToolNotFoundError
from .protocol import ProtocolAdapter
from .types import ToolContract


class UniversalToolRegistry:
    """Tracks every registered ProtocolAdapter and every ToolContract it
    (or a caller) has published, keyed by "protocol:identity".
    """

    def __init__(self, *, logger=None) -> None:
        self._adapters: Dict[str, ProtocolAdapter] = {}
        self._contracts: Dict[str, ToolContract] = {}
        self._health: Dict[str, str] = {}
        self._logger = logger or get_logger("integration.registry")

    def register_adapter(self, adapter: ProtocolAdapter) -> None:
        if adapter.protocol_name in self._adapters:
            raise DuplicateAdapterError(
                f"Protocol '{adapter.protocol_name}' is already registered with this registry"
            )
        self._adapters[adapter.protocol_name] = adapter
        discovered = adapter.discover_tools()
        for contract in discovered:
            if contract.protocol != adapter.protocol_name:
                raise ProtocolMismatchError(
                    f"Adapter '{adapter.protocol_name}' discovered a contract for "
                    f"'{contract.identity}' declaring protocol '{contract.protocol}' -- "
                    f"ToolContract.protocol must match the adapter's protocol_name"
                )
            self.register_tool(contract)
        self._logger.info(
            "Protocol adapter registered",
            protocol=adapter.protocol_name,
            tools_discovered=len(discovered),
        )

    def register_tool(self, contract: ToolContract) -> None:
        self._contracts[contract.qualified_name] = contract
        self._health[contract.qualified_name] = contract.health_status

    def get(self, protocol: str, identity: str) -> ToolContract:
        key = f"{protocol}:{identity}"
        contract = self._contracts.get(key)
        if contract is None:
            raise ToolNotFoundError(f"No tool registered as '{key}'")
        return contract

    def get_adapter(self, protocol: str) -> ProtocolAdapter:
        adapter = self._adapters.get(protocol)
        if adapter is None:
            raise ProtocolNotRegisteredError(f"No adapter registered for protocol '{protocol}'")
        return adapter

    def list_tools(self, protocol: Optional[str] = None) -> Tuple[ToolContract, ...]:
        contracts = tuple(self._contracts.values())
        if protocol is not None:
            contracts = tuple(c for c in contracts if c.protocol == protocol)
        return contracts

    def find_by_capability(self, capability: str) -> Tuple[ToolContract, ...]:
        """An honest, simple matcher (case-insensitive substring against
        permission tags, identity, and description) -- not a claimed
        semantic search. See CONTRACT.md SS3.
        """
        needle = capability.lower()
        matches = []
        for contract in self._contracts.values():
            haystack = " ".join((contract.identity, contract.description, *contract.permissions)).lower()
            if needle in haystack:
                matches.append(contract)
        return tuple(matches)

    def health_check_all(self) -> Dict[str, str]:
        for protocol, adapter in self._adapters.items():
            status = adapter.health_check()
            for key, contract in self._contracts.items():
                if contract.protocol == protocol:
                    self._health[key] = status
        return dict(self._health)

    def get_health(self, protocol: str, identity: str) -> str:
        key = f"{protocol}:{identity}"
        if key not in self._contracts:
            raise ToolNotFoundError(f"No tool registered as '{key}'")
        return self._health.get(key, "unknown")
