"""ExecutiveDashboard -- Mission Layla Part 23 (Executive Intelligence)
and Part 27 (Communication Management, insofar as this is what
actually gets communicated to the person Layla works for). See
CONTRACT.md SS31.

Not a new cognitive layer -- `ExecutiveRuntime` already *is* Layla's
executive intelligence (Phase 16). This is a thin, real aggregator
tying together every Mission Layla Foundation-tier component's own
`summary()`/report method into one coherent brief -- every section is
backed by a real call into a real component, nothing synthesized here.
Optional components are simply omitted from the brief if not supplied,
never faked.
"""

from __future__ import annotations

from typing import Optional

from .business_intelligence import BusinessIntelligenceEngine
from .life_os import LifeOS
from .personal_model import PersonalModel
from .prediction import PredictionEngine
from .skills import SkillRegistry


class ExecutiveDashboard:
    def __init__(
        self, *, personal_model: Optional[PersonalModel] = None, life_os: Optional[LifeOS] = None,
        prediction_engine: Optional[PredictionEngine] = None, skill_registry: Optional[SkillRegistry] = None,
        business_intelligence: Optional[BusinessIntelligenceEngine] = None,
    ) -> None:
        self._personal_model = personal_model
        self._life_os = life_os
        self._prediction = prediction_engine
        self._skills = skill_registry
        self._bi = business_intelligence

    def brief(self) -> str:
        """A real executive brief -- every section below is a direct
        call into a real, already-tested component. Sections whose
        backing component wasn't supplied are simply omitted, not
        fabricated.
        """
        sections = []

        if self._personal_model is not None:
            sections.append("## Personal Model\n" + self._personal_model.summary())

        if self._life_os is not None:
            upcoming = self._life_os.list_upcoming_appointments()
            due = self._life_os.list_due_reminders()
            lines = [f"{len(upcoming)} upcoming appointment(s), {len(due)} due reminder(s)."]
            for fact in upcoming[:5]:
                lines.append(f"  - {fact.value.get('description', fact.key)} at {fact.value.get('when', '?')}")
            for fact in due[:5]:
                lines.append(f"  - REMINDER DUE: {fact.value.get('message', fact.key)}")
            sections.append("## Life OS\n" + "\n".join(lines))

        if self._prediction is not None:
            stuck_predictions = self._prediction.predict_stuck_task_risk()
            next_capability = self._prediction.predict_next_capability()
            lines = []
            for p in stuck_predictions:
                lines.append(f"  - {p.prediction} (confidence {p.confidence:.0%}): {p.recommended_action}")
            if next_capability is not None:
                lines.append(f"  - {next_capability.prediction} (confidence {next_capability.confidence:.0%})")
            sections.append("## Predictions\n" + ("\n".join(lines) if lines else "No predictions available yet."))

        if self._skills is not None:
            approved = self._skills.list_approved()
            sections.append(f"## Skills\n{len(approved)} approved, reusable skill(s) available.")

        if self._bi is not None:
            sections.append("## Business Intelligence\n" + self._bi.summary())

        return "\n\n".join(sections) if sections else "No Foundation-tier components wired into this dashboard yet."
