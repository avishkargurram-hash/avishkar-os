"""PersonalModel -- Layla's continuously-evolving model of the person
she works for. See CONTRACT.md SS20, ADR-0026.

Mission Layla directive Part 1: Identity, Preferences, Goals, Decision
Patterns, Work Patterns, Communication Style, Project Context,
Relationships, Behavioral Patterns, Personal Knowledge, Life Events,
Habits, Long-term Objectives -- confidence, provenance, timestamps,
recency, contradiction handling, correction, privacy, retention, user
control.

Not a second memory system. Every fact is a namespaced key inside the
same `LaylaMemoryPolicy` (`kind="long_term"`, `personal:{category}:{key}`)
every other Layla component already uses -- reusing exactly the
index-key pattern `SessionManager`/`AuditLogger`/`ApprovalManager`
already established, since the underlying `MemoryPolicy` contract has
no key-enumeration method (CONTRACT.md SS2).

Contradiction handling, concretely: `set()` refuses to silently
overwrite an existing, *different* value -- it raises
`PersonalFactContradictionError` unless the caller explicitly resolves
it via `correct()` (an intentional, reasoned overwrite, exactly
`LaylaMemoryPolicy.correct()`'s own semantics) or passes
`resolve="overwrite"`/`resolve="ignore"` to `set()` directly. Writing
the *same* value again is always a no-op (idempotent), matching the
same discipline `ExecutionTracker`/`SessionManager` already use
elsewhere in this codebase.

Privacy, concretely: no category in this module ever ships with
seed/default/example personal data (unlike GENESIS's `owner_system.py`/
`founder_profile_loader.py`, which hardcode a real person's name,
family, and health information directly in source -- see the Mission
Layla 1 forensic audit). `SENSITIVE_CATEGORIES` (relationships,
behavioral_patterns) additionally require an explicit `confirmed=True`
on every write -- the one GENESIS pattern (`digital_founder_genome.py`'s
sensitive-layer gate) judged worth reusing as a *pattern*, reimplemented
here from scratch, no GENESIS code referenced or copied.
"""

from __future__ import annotations

import dataclasses
import datetime
from typing import Any, Dict, Optional

from .errors import PersonalFactContradictionError, SensitiveCategoryNotConfirmedError
from .memory_policy import LaylaMemoryPolicy

_KIND = "long_term"

# --- Categories (Mission Layla directive Part 1) ----------------------------

CATEGORY_IDENTITY = "identity"
CATEGORY_PREFERENCES = "preferences"
CATEGORY_GOALS = "goals"
CATEGORY_DECISION_PATTERNS = "decision_patterns"
CATEGORY_WORK_PATTERNS = "work_patterns"
CATEGORY_COMMUNICATION_STYLE = "communication_style"
CATEGORY_PROJECT_CONTEXT = "project_context"
CATEGORY_RELATIONSHIPS = "relationships"
CATEGORY_BEHAVIORAL_PATTERNS = "behavioral_patterns"
CATEGORY_PERSONAL_KNOWLEDGE = "personal_knowledge"
CATEGORY_LIFE_EVENTS = "life_events"
CATEGORY_HABITS = "habits"
CATEGORY_LONG_TERM_OBJECTIVES = "long_term_objectives"

# Mission Layla Part 4 (Life OS) categories -- deliberately added here,
# not as a competing structure: Life OS is a thin domain-specific
# wrapper (life_os.py) over this same PersonalModel, reusing its
# confirmation-gate/contradiction-handling machinery rather than
# duplicating it. See life_os.py.
CATEGORY_SCHEDULE = "schedule"
CATEGORY_TASKS = "tasks"
CATEGORY_FINANCE = "finance"
CATEGORY_HEALTH = "health"
CATEGORY_TRAVEL = "travel"
CATEGORY_APPOINTMENTS = "appointments"
CATEGORY_REMINDERS = "reminders"

CATEGORIES = (
    CATEGORY_IDENTITY, CATEGORY_PREFERENCES, CATEGORY_GOALS,
    CATEGORY_DECISION_PATTERNS, CATEGORY_WORK_PATTERNS, CATEGORY_COMMUNICATION_STYLE,
    CATEGORY_PROJECT_CONTEXT, CATEGORY_RELATIONSHIPS, CATEGORY_BEHAVIORAL_PATTERNS,
    CATEGORY_PERSONAL_KNOWLEDGE, CATEGORY_LIFE_EVENTS, CATEGORY_HABITS,
    CATEGORY_LONG_TERM_OBJECTIVES,
    CATEGORY_SCHEDULE, CATEGORY_TASKS, CATEGORY_FINANCE, CATEGORY_HEALTH,
    CATEGORY_TRAVEL, CATEGORY_APPOINTMENTS, CATEGORY_REMINDERS,
)

# Categories where a contradiction can never be silently resolved even
# with resolve="overwrite" from a low-confidence source, and where a
# write always requires explicit confirmation -- GENESIS's own audit
# showed exactly these two categories (relationships, behavior) are
# where hardcoded, unauthorized, unconfirmed personal data caused real
# harm. Reused here as a *policy*, not as data or code.
SENSITIVE_CATEGORIES = frozenset({
    CATEGORY_RELATIONSHIPS, CATEGORY_BEHAVIORAL_PATTERNS,
    # Mission Layla Part 4 explicitly requires "all sensitive categories
    # must use explicit authorization and privacy controls" for
    # finance/health data specifically.
    CATEGORY_FINANCE, CATEGORY_HEALTH,
})

RESOLVE_OVERWRITE = "overwrite"
RESOLVE_IGNORE = "ignore"


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


@dataclasses.dataclass(frozen=True)
class PersonalFact:
    """One fact Layla holds about the person. `value` is deliberately
    untyped (Any) -- the same discipline MemoryRecord already uses;
    categories give it whatever shape the caller wants (a string, a
    dict, a list).
    """

    category: str
    key: str
    value: Any
    confidence: float = 1.0
    provenance: str = "user"
    importance: str = "normal"
    stored_at: str = ""
    corrected: bool = False  # True if this fact has ever been through correct()


class PersonalModel:
    """Layla's model of the person she works for. See module docstring
    and CONTRACT.md SS20.
    """

    def __init__(self, memory: LaylaMemoryPolicy) -> None:
        self._memory = memory

    def _entry_key(self, category: str, key: str) -> str:
        return f"personal:{category}:{key}"

    def _index_key(self, category: str) -> str:
        return f"personal:__index__:{category}"

    def _require_category(self, category: str) -> None:
        if category not in CATEGORIES:
            raise ValueError(f"unknown PersonalModel category {category!r} -- expected one of {CATEGORIES}")

    def set(
        self, category: str, key: str, value: Any, *,
        confidence: float = 1.0, provenance: str = "user", importance: str = "normal",
        confirmed: bool = False, resolve: Optional[str] = None,
    ) -> PersonalFact:
        """Writes a fact. Idempotent if `value` is unchanged from the
        existing fact at this (category, key). Raises
        `PersonalFactContradictionError` if a *different* existing
        value is found and `resolve` isn't given (use `correct()` for
        an explicit, reasoned overwrite, or pass
        `resolve="overwrite"`/`resolve="ignore"` here directly).

        `confirmed=True` is required for any write to a
        SENSITIVE_CATEGORIES category (relationships,
        behavioral_patterns) -- raises `SensitiveCategoryNotConfirmedError`
        otherwise, regardless of `resolve`.
        """
        self._require_category(category)
        if category in SENSITIVE_CATEGORIES and not confirmed:
            raise SensitiveCategoryNotConfirmedError(
                f"writing to sensitive category {category!r} requires confirmed=True -- "
                f"this is never inferred automatically"
            )

        existing = self.get(category, key)
        if existing is not None and existing.value != value:
            if resolve == RESOLVE_IGNORE:
                return existing
            if resolve != RESOLVE_OVERWRITE:
                raise PersonalFactContradictionError(
                    f"{category}:{key} already holds a different value -- "
                    f"call correct() for a reasoned overwrite, or pass "
                    f"resolve='overwrite'/resolve='ignore' to set() explicitly"
                )
        elif existing is not None and existing.value == value:
            return existing  # idempotent -- no-op on an identical value

        self._memory.remember(
            _KIND, self._entry_key(category, key), value,
            confidence=confidence, provenance=provenance, importance=importance,
        )
        self._add_to_index(category, key)
        return self.get(category, key)  # re-read so stored_at reflects the real write

    def correct(self, category: str, key: str, new_value: Any, *, reason: str, confirmed: bool = False) -> PersonalFact:
        """The explicit, reasoned-overwrite path -- reuses
        `LaylaMemoryPolicy.correct()` verbatim, tagging provenance with
        the reason. Always allowed regardless of any prior contradiction
        (that's the point of this method existing separately from set()).
        """
        self._require_category(category)
        if category in SENSITIVE_CATEGORIES and not confirmed:
            raise SensitiveCategoryNotConfirmedError(
                f"correcting sensitive category {category!r} requires confirmed=True"
            )
        self._memory.correct(_KIND, self._entry_key(category, key), new_value, reason=reason)
        self._add_to_index(category, key)
        record = self._memory.recall(_KIND, self._entry_key(category, key))
        return PersonalFact(
            category=category, key=key, value=record.value, confidence=record.confidence,
            provenance=record.provenance, importance=record.importance, stored_at=record.stored_at,
            corrected=True,
        )

    def get(self, category: str, key: str) -> Optional[PersonalFact]:
        self._require_category(category)
        record = self._memory.recall(_KIND, self._entry_key(category, key))
        if record is None:
            return None
        return PersonalFact(
            category=category, key=key, value=record.value, confidence=record.confidence,
            provenance=record.provenance, importance=record.importance, stored_at=record.stored_at,
            corrected=record.provenance.startswith("correction:"),
        )

    def get_category(self, category: str) -> Dict[str, PersonalFact]:
        """Every fact currently held under one category. O(n) in the
        number of keys ever written to that category (same index-scan
        pattern SessionManager.list_incomplete() already uses).
        """
        self._require_category(category)
        index_record = self._memory.recall(_KIND, self._index_key(category))
        if index_record is None:
            return {}
        facts = {}
        for key in index_record.value:
            fact = self.get(category, key)
            if fact is not None:
                facts[key] = fact
        return facts

    def forget(self, category: str, key: str) -> None:
        """Deletion is never a policy decision -- always allowed, same
        as LaylaMemoryPolicy.forget() itself (CONTRACT.md SS2). Also
        removes the key from this category's index.
        """
        self._require_category(category)
        self._memory.forget(_KIND, self._entry_key(category, key))
        index_record = self._memory.recall(_KIND, self._index_key(category))
        if index_record is not None:
            remaining = [k for k in index_record.value if k != key]
            self._memory.remember(_KIND, self._index_key(category), remaining, provenance="personal-model")

    def summary(self) -> str:
        """A compact, human-readable digest across every category --
        intended for ContextBuilder to fold into a prompt. Deliberately
        terse (one line per category with data), never dumps raw
        SENSITIVE_CATEGORIES content verbatim into a summary that might
        be logged or shown broadly -- it names the category and count
        only for those, not the values.
        """
        lines = []
        for category in CATEGORIES:
            facts = self.get_category(category)
            if not facts:
                continue
            if category in SENSITIVE_CATEGORIES:
                lines.append(f"{category}: {len(facts)} fact(s) on file (sensitive, not summarized)")
            else:
                preview = ", ".join(f"{k}={v.value!r}" for k, v in tuple(facts.items())[:5])
                lines.append(f"{category}: {preview}")
        return "\n".join(lines) if lines else "No personal model data recorded yet."

    def _add_to_index(self, category: str, key: str) -> None:
        index_record = self._memory.recall(_KIND, self._index_key(category))
        keys = set(index_record.value) if index_record else set()
        keys.add(key)
        self._memory.remember(_KIND, self._index_key(category), sorted(keys), provenance="personal-model")
