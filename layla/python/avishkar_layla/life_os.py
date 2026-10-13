"""LifeOS -- Mission Layla Part 4. See CONTRACT.md SS25.

A thin, domain-organized convenience layer over `PersonalModel` --
deliberately not a competing structure: goals/schedule/tasks/habits/
finance/health/relationships/travel/life events/appointments/reminders
are all just `PersonalModel` categories, reusing its existing
confidence/provenance/contradiction-handling/confirmation-gate
machinery verbatim. `finance` and `health` are `SENSITIVE_CATEGORIES`
(personal_model.py) -- every write requires `confirmed=True`, per this
mission's own explicit instruction that "all sensitive categories must
use explicit authorization and privacy controls."
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, Optional, Tuple

from .personal_model import (
    CATEGORY_APPOINTMENTS,
    CATEGORY_FINANCE,
    CATEGORY_GOALS,
    CATEGORY_HABITS,
    CATEGORY_HEALTH,
    CATEGORY_LIFE_EVENTS,
    CATEGORY_REMINDERS,
    CATEGORY_TASKS,
    CATEGORY_TRAVEL,
    PersonalFact,
    PersonalModel,
)


class LifeOS:
    def __init__(self, personal_model: PersonalModel) -> None:
        self._model = personal_model

    # --- WORK -----------------------------------------------------------

    def add_goal(self, goal_id: str, description: str, *, confidence: float = 1.0) -> PersonalFact:
        return self._model.set(CATEGORY_GOALS, goal_id, description, confidence=confidence)

    def add_task(self, task_id: str, description: str, *, due: Optional[str] = None) -> PersonalFact:
        return self._model.set(CATEGORY_TASKS, task_id, {"description": description, "due": due})

    def list_tasks(self) -> Dict[str, PersonalFact]:
        return self._model.get_category(CATEGORY_TASKS)

    # --- LIFE -------------------------------------------------------------

    def add_habit(self, habit_id: str, description: str) -> PersonalFact:
        return self._model.set(CATEGORY_HABITS, habit_id, description)

    def add_life_event(self, event_id: str, description: str, *, when: Optional[str] = None) -> PersonalFact:
        return self._model.set(CATEGORY_LIFE_EVENTS, event_id, {"description": description, "when": when})

    def add_travel_plan(self, plan_id: str, destination: str, *, when: Optional[str] = None) -> PersonalFact:
        return self._model.set(CATEGORY_TRAVEL, plan_id, {"destination": destination, "when": when})

    def log_health(self, entry_id: str, description: str, *, confirmed: bool) -> PersonalFact:
        """SENSITIVE_CATEGORIES -- requires confirmed=True, never
        inferred automatically. Raises SensitiveCategoryNotConfirmedError
        otherwise (personal_model.py).
        """
        return self._model.set(CATEGORY_HEALTH, entry_id, description, confirmed=confirmed)

    def log_finance(self, entry_id: str, description: str, amount: float, *, confirmed: bool) -> PersonalFact:
        """SENSITIVE_CATEGORIES -- requires confirmed=True."""
        return self._model.set(CATEGORY_FINANCE, entry_id, {"description": description, "amount": amount}, confirmed=confirmed)

    # --- SCHEDULING ---------------------------------------------------------

    def add_appointment(self, appointment_id: str, description: str, when: str) -> PersonalFact:
        """`when` is a real ISO-8601 timestamp -- required (not
        optional like tasks/travel/life events), since
        `list_upcoming_appointments()` depends on it to compute a real
        ordering, not a guess.
        """
        return self._model.set(CATEGORY_APPOINTMENTS, appointment_id, {"description": description, "when": when})

    def add_reminder(self, reminder_id: str, message: str, when: str) -> PersonalFact:
        return self._model.set(CATEGORY_REMINDERS, reminder_id, {"message": message, "when": when})

    def list_upcoming_appointments(self, *, now: Optional[str] = None) -> Tuple[PersonalFact, ...]:
        """Real filtering/sorting by each appointment's own `when`
        field -- not a fabricated ordering. `now` defaults to the real
        current UTC time; injectable for deterministic tests.
        """
        now = now or datetime.datetime.now(datetime.timezone.utc).isoformat()
        facts = [f for f in self._model.get_category(CATEGORY_APPOINTMENTS).values() if _when(f.value) is not None]
        upcoming = [f for f in facts if _when(f.value) >= now]
        return tuple(sorted(upcoming, key=lambda f: _when(f.value)))

    def list_due_reminders(self, *, now: Optional[str] = None) -> Tuple[PersonalFact, ...]:
        now = now or datetime.datetime.now(datetime.timezone.utc).isoformat()
        facts = [f for f in self._model.get_category(CATEGORY_REMINDERS).values() if _when(f.value) is not None]
        due = [f for f in facts if _when(f.value) <= now]
        return tuple(sorted(due, key=lambda f: _when(f.value)))


def _when(value: Any) -> Optional[str]:
    if isinstance(value, dict):
        return value.get("when")
    return None
