"""LearningLoop -- Mission Layla Part 13. See CONTRACT.md SS24.

Experience -> Outcome -> Reflection -> Pattern extraction -> Candidate
improvement -> Evaluation -> Security validation -> Versioned Skill ->
Future use -- built entirely from real, already-recorded Layla state
(`SessionManager`/`AuditLogger`) feeding the real `SkillRegistry`
(Part 12). No arbitrary self-modifying source code anywhere in this
module -- it never writes to a `.py` file, never calls `exec`/`eval`,
never touches this codebase's own source. The only thing it ever
produces is a `Skill` in `SKILL_CANDIDATE` status: proposing a skill is
not learning it. "Evaluation" and "Security validation" both remain
genuinely separate, explicit, human/deployment-driven steps
(`SkillRegistry.evaluate()`) -- `LearningLoop` never calls `evaluate()`
itself, and therefore can never approve its own suggestions. This is
the same anti-self-escalation discipline Priority 17.1's
`AuthorizationManager` already established for permissions, applied
here to skill learning.
"""

from __future__ import annotations

import collections
import dataclasses
from typing import Tuple

from .audit import AuditLogger
from .session import SessionManager
from .skills import Skill, SkillRegistry
from .types import COMPLETED, RISK_LOW


@dataclasses.dataclass(frozen=True)
class SkillCandidateSuggestion:
    skill: Skill
    occurrence_count: int


class LearningLoop:
    def __init__(
        self, session_manager: SessionManager, audit_logger: AuditLogger, skill_registry: SkillRegistry,
        *, min_occurrences: int = 3,
    ) -> None:
        self._sessions = session_manager
        self._audit = audit_logger
        self._skills = skill_registry
        self._min_occurrences = min_occurrences

    def extract_candidate_skills(self) -> Tuple[SkillCandidateSuggestion, ...]:
        """Pattern extraction over real Experience (every COMPLETED
        task's real plan). A capability used successfully in >=
        `min_occurrences` completed tasks is proposed as a
        SKILL_CANDIDATE -- never auto-approved, never executed, just
        proposed for a human/deployment to evaluate later via
        `SkillRegistry.evaluate()`. Skips a capability that already has
        an active (non-retired) proposed skill, so re-running this
        doesn't create duplicate candidates every tick.
        """
        capability_counts: collections.Counter = collections.Counter()
        for task in self._sessions.list_all():
            if task.state != COMPLETED or task.plan is None:
                continue
            history = self._audit.history(task_id=task.id)
            completed_steps = {r.payload.get("step_id") for r in history if r.event_type == "layla.delegation.completed"}
            for step in task.plan.steps:
                if step.id in completed_steps:
                    capability_counts[step.required_capability] += 1

        existing_capabilities = {s.required_capability for s in self._skills.list_all() if s.status != "RETIRED"}

        suggestions = []
        for capability, count in capability_counts.items():
            if count < self._min_occurrences or capability in existing_capabilities:
                continue
            skill = self._skills.propose(
                name=f"auto-{capability}", purpose=f"Reusable request template for {capability!r}, "
                                                     f"extracted from {count} real successful completions.",
                required_capability=capability, input_template="{request}",
                risk_level=RISK_LOW, provenance="learning-loop",
            )
            suggestions.append(SkillCandidateSuggestion(skill=skill, occurrence_count=count))
        return tuple(suggestions)
