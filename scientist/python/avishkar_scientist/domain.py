"""Vocabulary of Scientist OS: statuses, phases, stances, outcomes, depths.

Plain string enums (str subclass) so values round-trip through Postgres
text columns and JSON without conversion code.
"""

from __future__ import annotations

import dataclasses
import enum


class _S(str, enum.Enum):
    def __str__(self) -> str:  # f"{x}" -> value, not "Cls.X"
        return self.value


class MissionStatus(_S):
    CREATED = "CREATED"
    PLANNING = "PLANNING"
    RUNNING = "RUNNING"
    WAITING = "WAITING"
    PAUSED = "PAUSED"
    BLOCKED = "BLOCKED"
    WAITING_FOR_HUMAN = "WAITING_FOR_HUMAN"
    VALIDATING = "VALIDATING"
    SYNTHESIZING = "SYNTHESIZING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


ACTIVE_STATUSES = (
    MissionStatus.CREATED, MissionStatus.PLANNING, MissionStatus.RUNNING,
    MissionStatus.WAITING, MissionStatus.VALIDATING, MissionStatus.SYNTHESIZING,
)
TERMINAL_STATUSES = (MissionStatus.COMPLETED, MissionStatus.FAILED, MissionStatus.CANCELLED)


class Phase(_S):
    SCOPING = "SCOPING"
    LITERATURE_RESEARCH = "LITERATURE_RESEARCH"
    HYPOTHESIS_GENERATION = "HYPOTHESIS_GENERATION"
    EVIDENCE_COLLECTION = "EVIDENCE_COLLECTION"
    DATA_ANALYSIS = "DATA_ANALYSIS"
    EXPERIMENTATION = "EXPERIMENTATION"
    CRITICISM = "CRITICISM"
    REPLICATION = "REPLICATION"
    SYNTHESIS = "SYNTHESIS"
    VERIFICATION = "VERIFICATION"
    VERDICT = "VERDICT"
    REPORTING = "REPORTING"


class Depth(_S):
    QUICK = "QUICK"
    STANDARD = "STANDARD"
    DEEP = "DEEP"
    EXTREME = "EXTREME"


class TaskStatus(_S):
    PENDING = "PENDING"
    LEASED = "LEASED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"        # transient: will be retried (status flips back to PENDING)
    DEAD = "DEAD"            # dead-lettered after max_attempts
    CANCELLED = "CANCELLED"


TERMINAL_TASK = (TaskStatus.SUCCEEDED, TaskStatus.DEAD, TaskStatus.CANCELLED)


class Queue(_S):
    RESEARCH = "research"
    LITERATURE = "literature"
    DATA = "data"
    ANALYSIS = "analysis"
    EXPERIMENT = "experiment"
    SIMULATION = "simulation"
    CRITICISM = "criticism"
    REPLICATION = "replication"
    VERIFICATION = "verification"
    REPORTING = "reporting"


ALL_QUEUES = tuple(q.value for q in Queue)


class Stance(_S):
    SUPPORTS = "SUPPORTS"
    REFUTES = "REFUTES"
    NEUTRAL = "NEUTRAL"


class Epistemic(_S):
    FACT = "FACT"
    OBSERVATION = "OBSERVATION"
    INFERENCE = "INFERENCE"
    HYPOTHESIS = "HYPOTHESIS"
    SPECULATION = "SPECULATION"


class ClaimStatus(_S):
    UNVERIFIED = "UNVERIFIED"
    SUPPORTED = "SUPPORTED"
    CONTESTED = "CONTESTED"
    REFUTED = "REFUTED"


class Severity(_S):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class Resolution(_S):
    UNRESOLVED = "UNRESOLVED"
    RESOLVED_CONDITIONAL = "RESOLVED_CONDITIONAL"   # both true under different conditions
    ONE_SIDE_WEAKER = "ONE_SIDE_WEAKER"             # documented, weaker side discounted
    DOCUMENTED = "DOCUMENTED"                       # irreconcilable; carried into verdict


class Outcome(_S):
    STOP_CONFIDENT = "STOP_CONFIDENT"
    STOP_WITH_UNCERTAINTY = "STOP_WITH_UNCERTAINTY"
    STOP_BUDGET = "STOP_BUDGET"
    STOP_TIME_LIMIT = "STOP_TIME_LIMIT"
    BLOCKED_EXTERNAL_EXPERIMENT = "BLOCKED_EXTERNAL_EXPERIMENT"
    CONTINUE = "CONTINUE"


class VerdictLabel(_S):
    SUPPORTED = "SUPPORTED"
    LIKELY_SUPPORTED = "LIKELY_SUPPORTED"
    CONTESTED = "CONTESTED"
    LIKELY_NOT_SUPPORTED = "LIKELY_NOT_SUPPORTED"
    NOT_SUPPORTED = "NOT_SUPPORTED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    PHYSICAL_VALIDATION_REQUIRED = "PHYSICAL_VALIDATION_REQUIRED"


# Spec section 38: the exact phrases the system must use.
INTEGRITY_PHRASES = {
    VerdictLabel.INSUFFICIENT_EVIDENCE: "Insufficient evidence.",
    VerdictLabel.PHYSICAL_VALIDATION_REQUIRED: "Physical validation required.",
    VerdictLabel.CONTESTED: "Evidence is contested.",
}


class ExperimentKind(_S):
    COMPUTATIONAL = "COMPUTATIONAL"
    SIMULATION = "SIMULATION"
    STATISTICAL = "STATISTICAL"
    PHYSICAL = "PHYSICAL"


class ExperimentStatus(_S):
    PROPOSED = "PROPOSED"
    REJECTED_STATIC = "REJECTED_STATIC"           # failed static validation, never executed
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SANDBOX_UNAVAILABLE = "SANDBOX_UNAVAILABLE"   # never run on host as a fallback
    PHYSICAL_EXPERIMENT_REQUIRED = "PHYSICAL_EXPERIMENT_REQUIRED"


class Tier(int, enum.Enum):
    T0_DETERMINISTIC = 0
    T1_LOCAL = 1
    T2_LOCAL_HEAVY = 2
    T3_STRONG = 3
    T4_PREMIUM = 4


CRITIC_ROLES = (
    "scientific_critic",
    "skeptic",
    "evidence_auditor",
    "methodology_critic",
    "logical_critic",
    "bias_detector",
)


@dataclasses.dataclass(frozen=True)
class DepthProfile:
    """A budget, not a requirement (spec section 7): missions stop early when
    the Termination Engine says so."""

    depth: Depth
    time_budget_s: int
    max_tasks: int
    max_iterations: int
    min_iterations: int
    max_sources: int
    max_experiments: int
    premium_calls: int          # Tier 3+ calls allowed for this mission (D3: Gemini only for key decisions)
    premium_usd: float          # hard USD cap on Tier 3+ spend for this mission
    evidence_threshold: float   # confidence needed for STOP_CONFIDENT
    rqs_threshold: float        # research quality needed for STOP_CONFIDENT
    critics: tuple
    council: bool
    replicate: bool
    queries_per_cycle: int
    estimate: str               # human-facing range, never an exact time


DEPTH_PROFILES = {
    Depth.QUICK: DepthProfile(
        Depth.QUICK, 20 * 60, 60, 1, 1, 10, 0, 0, 0.0, 0.70, 0.45,
        ("skeptic", "evidence_auditor"), False, False, 3, "~3-15 minutes"),
    Depth.STANDARD: DepthProfile(
        Depth.STANDARD, 90 * 60, 160, 2, 1, 24, 2, 5, 0.25, 0.72, 0.50,
        ("scientific_critic", "skeptic", "evidence_auditor", "bias_detector"), False, True, 4,
        "~15-60 minutes"),
    Depth.DEEP: DepthProfile(
        Depth.DEEP, 8 * 3600, 450, 4, 2, 60, 5, 25, 1.50, 0.75, 0.55, CRITIC_ROLES, True, True, 6,
        "~1-6 hours"),
    Depth.EXTREME: DepthProfile(
        Depth.EXTREME, 48 * 3600, 1500, 8, 3, 140, 12, 60, 4.00, 0.80, 0.60, CRITIC_ROLES, True, True, 8,
        "~6-36 hours"),
}


def profile(depth) -> DepthProfile:
    return DEPTH_PROFILES[Depth(str(depth))]
