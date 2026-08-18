"""Personal Executive Communication -- Mission Layla Directive D, Part
X. See CONTRACT.md SS46.

Calendar/Meetings/Appointments/Reminders are already real, existing
`LifeOS` functionality (Mission Layla continuation, ADR-0027) --
`add_appointment`/`add_reminder`/`list_upcoming_appointments`/
`list_due_reminders`; not rebuilt here. This module's real, new
contribution is Directive D's own worked example: "Avishkar has not
responded to this person for 7 days -> Relationship/context lookup ->
Determine follow-up appropriateness -> Generate draft -> Risk
assessment -> Approval policy -> Send -> Record outcome -> Update
memory."

`StaleRelationshipEvaluator` is a real `proactive.TriggerEvaluator`
covering the chain's first three steps (relationship/context lookup,
staleness detection, follow-up-appropriateness filtering) with real,
evidence-backed data from `PersonalModel`'s `relationships` category
-- and stops there, at `ACTION_SUGGEST`, never `ACT`. Directive D's
own chain continues "Generate draft -> Risk assessment -> Approval
policy -> Send" -- that is exactly what the UNCHANGED
`ExecutiveRuntime.handle_event()` pipeline already does for any
suggestion acted on (real intent/context/planning, real
`risk.classify_risk()`, real `ApprovalManager`, real delegation to a
Chief Domain Agent for drafting, real Part V channel adapters for
sending) -- this module does not reimplement drafting, risk
classification, or sending. `record_contact_outcome()` is the chain's
final two steps ("Record outcome -> Update memory"), called after a
real channel adapter confirms delivery.
"""

from __future__ import annotations

import dataclasses
import datetime
from typing import Any, Callable, Mapping, Optional, Sequence, Set

from .personal_model import PersonalModel
from .proactive import ACTION_SUGGEST, ProactiveTrigger

RELATIONSHIPS_CATEGORY = "relationships"
DEFAULT_STALE_THRESHOLD_DAYS = 7.0


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _parse_date(value: str) -> datetime.datetime:
    parsed = datetime.datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed


@dataclasses.dataclass(frozen=True)
class RelationshipContact:
    """The real shape a `relationships` PersonalModel fact's value is
    expected to have. Not enforced by a schema (PersonalModel stores
    arbitrary values) -- this is documentation plus a convenience
    constructor for `set()`/`correct()` callers.
    """

    name: str
    channel: str
    channel_address: str
    last_contact_date: str
    do_not_disturb: bool = False
    notes: str = ""

    def as_dict(self) -> Mapping[str, Any]:
        return dataclasses.asdict(self)


class StaleRelationshipEvaluator:
    """A real `proactive.TriggerEvaluator`. Scans every real fact in
    `PersonalModel`'s `relationships` category, computes a real
    days-since-last-contact delta, and surfaces one `ACTION_SUGGEST`
    trigger per contact that is both stale AND eligible (not
    `do_not_disturb`, and not already surfaced for this exact
    staleness state -- the same retry-storm-safe dedup pattern
    `EnvironmentalChangeEvaluator` (Part VI) and `ProactiveEngine`'s
    own built-in evaluators use). Never emits `ACTION_ACT`: deciding
    whether/what to send to a real person is not something this
    evaluator does -- that is `ExecutiveRuntime.handle_event()`'s job,
    unchanged, if a human or `ProactiveEngine.act_callback` chooses to
    act on the suggestion.
    """

    def __init__(
        self, personal_model: PersonalModel, *, threshold_days: float = DEFAULT_STALE_THRESHOLD_DAYS,
        clock: Callable[[], datetime.datetime] = _now,
        is_eligible: Optional[Callable[[str, Mapping[str, Any]], bool]] = None,
    ) -> None:
        self._personal_model = personal_model
        self._threshold_days = threshold_days
        self._clock = clock
        self._is_eligible = is_eligible
        self._seen: Set[str] = set()

    def __call__(self, engine: Any) -> Sequence[ProactiveTrigger]:
        now = self._clock()
        triggers = []
        for contact_id, fact in self._personal_model.get_category(RELATIONSHIPS_CATEGORY).items():
            value = fact.value
            if not isinstance(value, Mapping):
                continue
            if bool(value.get("do_not_disturb", False)):
                continue
            last_contact = value.get("last_contact_date")
            if not last_contact:
                continue
            try:
                last_contact_dt = _parse_date(last_contact)
            except ValueError:
                continue

            days_since = (now - last_contact_dt).total_seconds() / 86400.0
            if days_since < self._threshold_days:
                continue

            if self._is_eligible is not None and not self._is_eligible(contact_id, value):
                continue

            dedup_key = f"{contact_id}:{last_contact}"
            if dedup_key in self._seen:
                continue
            self._seen.add(dedup_key)

            name = value.get("name", contact_id)
            triggers.append(
                ProactiveTrigger(
                    id=f"stale-relationship-{dedup_key}",
                    action_level=ACTION_SUGGEST,
                    description=f"You haven't contacted {name} in {days_since:.1f} days -- consider a follow-up.",
                    evidence={
                        "contact_id": contact_id, "last_contact_date": last_contact,
                        "days_since": round(days_since, 2), "threshold_days": self._threshold_days,
                    },
                    source="stale_relationship_evaluator",
                )
            )
        return triggers


def record_contact_outcome(
    personal_model: PersonalModel, contact_id: str, *, channel: str, message_id: str,
    when: Optional[str] = None,
) -> None:
    """Directive D's chain's final two steps ("Record outcome ->
    Update memory"). Called after a real Part V channel adapter
    confirms delivery (a real `message_id`) -- never before. Raises
    `ValueError` for an unknown contact rather than silently creating
    one; a follow-up can only be recorded against a relationship that
    was already real, known context.
    """
    existing = personal_model.get(RELATIONSHIPS_CATEGORY, contact_id)
    if existing is None:
        raise ValueError(
            f"no relationship fact found for contact_id {contact_id!r} -- cannot record a follow-up outcome "
            f"for a contact PersonalModel has no record of"
        )
    new_value = dict(existing.value)
    new_value["last_contact_date"] = when or _now().isoformat()
    new_value["last_contact_channel"] = channel
    new_value["last_contact_message_id"] = message_id
    personal_model.correct(
        RELATIONSHIPS_CATEGORY, contact_id, new_value, reason=f"follow-up sent via {channel}", confirmed=True,
    )
