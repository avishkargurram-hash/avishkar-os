"""avishkar_layla -- Layla, Avishkar OS's Personal Executive
Intelligence layer.

See ../CONTRACT.md for the language-agnostic contract this package
implements, and ../README.md for the framework's full documentation.
Per DECISIONS.md ADR-0020: a new top-level platform capability, not a
Chief Domain Agent or a factory, composed entirely from existing
frameworks' public contracts.
"""

from .approval import ApprovalManager
from .audit import AuditLogger
from .capability_resolver import CapabilityResolver
from .context import ContextBuilder
from .delegation import DelegationEngine
from .errors import (
    ApprovalDeniedError,
    ApprovalExpiredError,
    DelegationTimeoutError,
    InvalidTransitionError,
    LaylaError,
    MemoryPolicyViolationError,
    SessionNotFoundError,
    UnknownCapabilityError,
    UnresolvedConflictError,
)
from .intent import Intent, IntentInterpreter
from .memory_policy import LaylaMemoryPolicy
from .monitoring import HealthMonitor
from .notifications import NotificationManager
from .planning import Planner
from .project import ProjectStore
from .risk import classify_risk
from .runtime import ExecutiveRuntime
from .scheduler import Scheduler
from .session import SessionManager
from .state_machine import ALLOWED_TRANSITIONS, StateMachine
from .synthesis import ConflictResolver, ExecutiveSynthesizer, ResultValidator
from .types import (
    RISK_HIGH,
    RISK_LOW,
    RISK_MEDIUM,
    SEVERITY_ACTION_REQUIRED,
    SEVERITY_CRITICAL,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    ApprovalRequest,
    AuditRecord,
    Conflict,
    DelegationRecord,
    LaylaTask,
    MemoryRecord,
    Notification,
    Plan,
    PlanStep,
    Project,
    ScheduledJob,
    ValidationReport,
)

__version__ = "0.1.0"

__all__ = [
    "LaylaTask",
    "StateMachine",
    "ALLOWED_TRANSITIONS",
    "LaylaMemoryPolicy",
    "MemoryRecord",
    "Project",
    "ProjectStore",
    "ApprovalRequest",
    "ApprovalManager",
    "RISK_LOW",
    "RISK_MEDIUM",
    "RISK_HIGH",
    "classify_risk",
    "Plan",
    "PlanStep",
    "Planner",
    "CapabilityResolver",
    "DelegationEngine",
    "DelegationRecord",
    "ValidationReport",
    "Conflict",
    "ResultValidator",
    "ConflictResolver",
    "ExecutiveSynthesizer",
    "Intent",
    "IntentInterpreter",
    "ContextBuilder",
    "Scheduler",
    "ScheduledJob",
    "AuditLogger",
    "AuditRecord",
    "SessionManager",
    "Notification",
    "NotificationManager",
    "HealthMonitor",
    "SEVERITY_INFO",
    "SEVERITY_WARNING",
    "SEVERITY_ACTION_REQUIRED",
    "SEVERITY_CRITICAL",
    "ExecutiveRuntime",
    "LaylaError",
    "InvalidTransitionError",
    "MemoryPolicyViolationError",
    "UnknownCapabilityError",
    "DelegationTimeoutError",
    "UnresolvedConflictError",
    "ApprovalExpiredError",
    "ApprovalDeniedError",
    "SessionNotFoundError",
    "__version__",
]
