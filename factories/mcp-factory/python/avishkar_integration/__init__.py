"""avishkar_integration -- Python reference implementation of the
Universal Integration Framework.

See ../CONTRACT.md for the language-agnostic contract this package
implements, and ../README.md for the framework's full documentation.

Per DECISIONS.md ADR-0011: MCP is the first-class protocol
implementation of a protocol-agnostic core -- the same shape AI Router
(Phase 2) established for model providers. Protocol adapters
(MCPAdapter, RESTAdapter) are NOT re-exported from this root because
MCPAdapter's default path needs the optional `mcp` package; import them
explicitly from `avishkar_integration.adapters.*`.
"""

from .agent_bridge import request_capability, resolve_mcp_tool_ref
from .errors import (
    DuplicateAdapterError,
    IntegrationError,
    NoMatchingToolError,
    ProtocolInvocationError,
    ProtocolMismatchError,
    ProtocolNotRegisteredError,
    ToolNotFoundError,
)
from .langgraph_nodes import (
    make_approval_node,
    make_logging_node,
    make_mcp_call_node,
    make_rest_call_node,
    make_retry_node,
    make_tool_execution_node,
)
from .metrics import MetricsCollector
from .planner import ExecutionPlan, IntegrationPlanner
from .policies import AccessControlPolicy, SecurityPolicy
from .protocol import ProtocolAdapter
from .registry import UniversalToolRegistry
from .runtime import ToolRuntime
from .types import AuditInfo, RateLimit, RetryPolicy, ToolContract, ToolExecutionRequest, ToolExecutionResult

__version__ = "0.1.0"

__all__ = [
    "ToolContract",
    "ToolExecutionRequest",
    "ToolExecutionResult",
    "RateLimit",
    "RetryPolicy",
    "AuditInfo",
    "ProtocolAdapter",
    "UniversalToolRegistry",
    "AccessControlPolicy",
    "SecurityPolicy",
    "ToolRuntime",
    "MetricsCollector",
    "IntegrationPlanner",
    "ExecutionPlan",
    "resolve_mcp_tool_ref",
    "request_capability",
    "make_tool_execution_node",
    "make_mcp_call_node",
    "make_rest_call_node",
    "make_retry_node",
    "make_approval_node",
    "make_logging_node",
    "IntegrationError",
    "ToolNotFoundError",
    "ProtocolNotRegisteredError",
    "ProtocolMismatchError",
    "DuplicateAdapterError",
    "NoMatchingToolError",
    "ProtocolInvocationError",
    "__version__",
]
