"""Core data types for Layla. See CONTRACT.md SS1-10.

Every dataclass here is deliberately plain data (frozen where nothing
needs post-construction mutation) -- the same discipline every
framework in this platform already follows (e.g. avishkar_agent.Task/
AgentResult, avishkar_workflow.Step/WorkflowResult).
"""

from __future__ import annotations

import dataclasses
import uuid
from typing import Any, Mapping, Optional, Tuple

# --- State machine (CONTRACT.md SS1) ---------------------------------------

RECEIVED = "RECEIVED"
UNDERSTANDING = "UNDERSTANDING"
CONTEXT_LOADING = "CONTEXT_LOADING"
PLANNING = "PLANNING"
APPROVAL_PENDING = "APPROVAL_PENDING"
EXECUTING = "EXECUTING"
DELEGATING = "DELEGATING"
WAITING = "WAITING"
VERIFYING = "VERIFYING"
SYNTHESIZING = "SYNTHESIZING"
COMPLETED = "COMPLETED"
FAILED = "FAILED"
CANCELLED = "CANCELLED"
TIMEOUT = "TIMEOUT"
BLOCKED = "BLOCKED"
REQUIRES_HUMAN = "REQUIRES_HUMAN"

TERMINAL_STATES = frozenset({COMPLETED, FAILED, CANCELLED, TIMEOUT, BLOCKED})
NON_TERMINAL_STATES = frozenset(
    {RECEIVED, UNDERSTANDING, CONTEXT_LOADING, PLANNING, APPROVAL_PENDING,
     EXECUTING, DELEGATING, WAITING, VERIFYING, SYNTHESIZING, REQUIRES_HUMAN}
)
ALL_STATES = TERMINAL_STATES | NON_TERMINAL_STATES


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


@dataclasses.dataclass(frozen=True)
class StateTransition:
    from_state: str
    to_state: str
    at: str  # ISO-8601 timestamp


@dataclasses.dataclass
class LaylaTask:
    """One request Layla is processing, moving through the state
    machine. Mutable (state/history/context change over the task's
    life) -- unlike most frozen types in this platform, a task is
    explicitly a stateful record, the same shape agent-factory's own
    ChiefDomainAgent.handle() loop builds up internally, just made
    externally visible and persistable (SessionManager, CONTRACT.md
    SS10).
    """

    input: str
    id: str = dataclasses.field(default_factory=lambda: new_id("task"))
    state: str = RECEIVED
    history: Tuple[StateTransition, ...] = ()
    context: Mapping[str, Any] = dataclasses.field(default_factory=dict)
    plan_id: Optional[str] = None
    result: Optional[str] = None
    blocked_reason: Optional[str] = None
    principal_id: Optional[str] = None  # who this task is being processed on behalf of (Priority 17.1)
    # Priority 17.3 (resume-in-place, ADR-0023): the actual Plan, not just
    # its id, persisted so a resumed task can continue DELEGATING without
    # re-planning -- see CONTRACT.md SS17 and session.py.
    plan: Optional["Plan"] = None
    pending_approval_id: Optional[str] = None


# --- Memory (CONTRACT.md SS2) -----------------------------------------------

MEMORY_KINDS = ("short_term", "long_term", "episodic", "semantic")


@dataclasses.dataclass(frozen=True)
class MemoryRecord:
    value: Any
    confidence: float = 1.0
    provenance: str = "user"
    importance: str = "normal"  # "low" | "normal" | "high" | "critical"
    stored_at: str = ""


# --- Project (CONTRACT.md SS3) ----------------------------------------------


@dataclasses.dataclass(frozen=True)
class Project:
    id: str
    name: str
    objectives: Tuple[str, ...] = ()
    milestones: Tuple[str, ...] = ()
    tasks: Tuple[str, ...] = ()
    decisions: Tuple[str, ...] = ()
    owners: Tuple[str, ...] = ()
    status: str = "active"  # "active" | "paused" | "completed" | "archived"
    dependencies: Tuple[str, ...] = ()


# --- Risk / Approval (CONTRACT.md SS4) --------------------------------------

RISK_LOW = "LOW"
RISK_MEDIUM = "MEDIUM"
RISK_HIGH = "HIGH"
RISK_LEVELS = (RISK_LOW, RISK_MEDIUM, RISK_HIGH)


@dataclasses.dataclass
class ApprovalRequest:
    id: str
    task_id: str
    action_description: str
    risk_level: str
    status: str = "pending"  # "pending" | "granted" | "denied"
    auto: bool = False
    created_at: str = ""
    expiration: Optional[str] = None
    decided_at: Optional[str] = None
    reason: str = ""
    requested_by: Optional[str] = None  # Principal.id of the requester, for self-approval prevention


# --- Planning / Delegation (CONTRACT.md SS5-6) ------------------------------


@dataclasses.dataclass(frozen=True)
class PlanStep:
    id: str
    required_capability: str
    input: str
    depends_on: Tuple[str, ...] = ()
    risk_level: str = RISK_LOW
    timeout_seconds: float = 30.0
    max_attempts: int = 1


@dataclasses.dataclass(frozen=True)
class Plan:
    id: str
    task_id: str
    steps: Tuple[PlanStep, ...]


@dataclasses.dataclass
class DelegationRecord:
    step_id: str
    agent_name: str
    status: str = "pending"  # "pending" | "completed" | "failed" | "timeout" | "denied"
    output: Optional[str] = None
    attempts: int = 0
    started_at: str = ""
    completed_at: Optional[str] = None
    error: Optional[str] = None


@dataclasses.dataclass(frozen=True)
class ValidationReport:
    all_completed: bool
    failing: Tuple[str, ...]  # step_ids that didn't complete


@dataclasses.dataclass(frozen=True)
class Conflict:
    step_ids: Tuple[str, str]
    reason: str


# --- Notifications (CONTRACT.md SS8) ----------------------------------------

SEVERITY_INFO = "INFO"
SEVERITY_WARNING = "WARNING"
SEVERITY_ACTION_REQUIRED = "ACTION_REQUIRED"
SEVERITY_CRITICAL = "CRITICAL"
SEVERITY_ORDER = (SEVERITY_INFO, SEVERITY_WARNING, SEVERITY_ACTION_REQUIRED, SEVERITY_CRITICAL)


@dataclasses.dataclass(frozen=True)
class Notification:
    severity: str
    message: str
    source: str
    created_at: str = ""


# --- Audit (CONTRACT.md SS9) -------------------------------------------------


@dataclasses.dataclass(frozen=True)
class AuditRecord:
    event_type: str
    payload: Mapping[str, Any]
    task_id: Optional[str]
    recorded_at: str = ""
    principal_id: Optional[str] = None


# --- Scheduling (CONTRACT.md SS7) -------------------------------------------


@dataclasses.dataclass(frozen=True)
class ScheduledJob:
    id: str
    run_at: float  # clock units, comparable to the Scheduler's clock()
    interval_seconds: Optional[float]  # None = one-shot
