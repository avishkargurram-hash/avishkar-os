"""BusinessIntelligenceEngine -- Mission Layla Part 26. See
CONTRACT.md SS30.

A real reporting layer over already-recorded Layla state
(`SessionManager`/`AuditLogger`) -- task counts by state, delegation
success rate per capability, total real cost (`DelegationRecord.
cost_usd`, real since Priority 17.5). No fabricated metrics: every
number in a `BusinessIntelligenceReport` is a direct count/sum/ratio
over real records, the same evidence-only discipline `prediction.py`
and `proactive.py` already established for this mission.
"""

from __future__ import annotations

import collections
import dataclasses
import datetime
from typing import Dict, Mapping

from .audit import AuditLogger
from .session import SessionManager
from .types import TERMINAL_STATES


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


@dataclasses.dataclass(frozen=True)
class BusinessIntelligenceReport:
    generated_at: str
    total_tasks: int
    tasks_by_state: Mapping[str, int]
    completed_count: int
    incomplete_count: int
    delegation_success_rate_by_capability: Mapping[str, float]
    total_cost_usd: float


class BusinessIntelligenceEngine:
    def __init__(self, session_manager: SessionManager, audit_logger: AuditLogger) -> None:
        self._sessions = session_manager
        self._audit = audit_logger

    def generate_report(self) -> BusinessIntelligenceReport:
        all_tasks = self._sessions.list_all()
        tasks_by_state: Dict[str, int] = collections.Counter(t.state for t in all_tasks)
        completed_count = tasks_by_state.get("COMPLETED", 0)
        incomplete_count = sum(c for state, c in tasks_by_state.items() if state not in TERMINAL_STATES)

        capability_attempts: Dict[str, int] = collections.Counter()
        capability_successes: Dict[str, int] = collections.Counter()
        total_cost = 0.0

        for task in all_tasks:
            if task.plan is None:
                continue
            history = self._audit.history(task_id=task.id)
            outcomes: Dict[str, str] = {}
            for record in history:
                if record.event_type.startswith("layla.delegation."):
                    step_id = record.payload.get("step_id")
                    if step_id:
                        outcomes[step_id] = record.event_type.rsplit(".", 1)[-1]
                    cost = record.payload.get("cost_usd")
                    if isinstance(cost, (int, float)):
                        total_cost += cost
            for step in task.plan.steps:
                outcome = outcomes.get(step.id)
                if outcome is None:
                    continue
                capability_attempts[step.required_capability] += 1
                if outcome == "completed":
                    capability_successes[step.required_capability] += 1

        success_rate_by_capability: Dict[str, float] = {
            capability: capability_successes[capability] / attempts
            for capability, attempts in capability_attempts.items()
        }

        return BusinessIntelligenceReport(
            generated_at=_now(), total_tasks=len(all_tasks), tasks_by_state=dict(tasks_by_state),
            completed_count=completed_count, incomplete_count=incomplete_count,
            delegation_success_rate_by_capability=success_rate_by_capability, total_cost_usd=total_cost,
        )

    def summary(self) -> str:
        report = self.generate_report()
        if report.total_tasks == 0:
            return "No tasks recorded yet."
        lines = [
            f"{report.total_tasks} total task(s): {report.completed_count} completed, "
            f"{report.incomplete_count} incomplete.",
            f"Total delegation cost recorded: ${report.total_cost_usd:.4f}",
        ]
        for capability, rate in sorted(report.delegation_success_rate_by_capability.items()):
            lines.append(f"  {capability}: {rate:.0%} success rate")
        return "\n".join(lines)
