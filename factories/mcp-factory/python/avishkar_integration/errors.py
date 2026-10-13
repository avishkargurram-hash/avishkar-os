"""Error types for the Universal Integration Framework. See CONTRACT.md."""

from __future__ import annotations


class IntegrationError(Exception):
    """Base class for every error avishkar_integration raises."""


class ToolNotFoundError(IntegrationError):
    """UniversalToolRegistry.get() named a tool that was never registered."""


class ProtocolNotRegisteredError(IntegrationError):
    """UniversalToolRegistry.get_adapter() named a protocol with no
    registered ProtocolAdapter.
    """


class DuplicateAdapterError(IntegrationError):
    """Two adapters with the same protocol_name were registered with one
    UniversalToolRegistry -- refused at registration time (mirrors
    router.DuplicateModelError / agent.DuplicateAgentError).
    """


class ProtocolMismatchError(IntegrationError):
    """A ProtocolAdapter's discover_tools() returned a ToolContract whose
    `.protocol` doesn't match the adapter's own `protocol_name` -- caught
    at registration time so a copy-pasted or misconfigured adapter can't
    silently corrupt the registry's protocol:identity addressing.
    """


class NoMatchingToolError(IntegrationError):
    """IntegrationPlanner.plan() / request_capability() found no
    registered tool matching the requested capability.
    """


class ProtocolInvocationError(IntegrationError):
    """A ProtocolAdapter's underlying transport (MCP session, HTTP call,
    ...) failed. Adapters normalize their vendor-specific exceptions into
    this type before returning -- mirrors router.errors.ProviderError.
    """
