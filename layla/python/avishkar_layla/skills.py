"""SkillRegistry -- Mission Layla Part 12 (Hermes-style reusable
skills). See CONTRACT.md SS23.

A Skill is a named, versioned, reusable request template
(`required_capability` + `input_template`) with a real lifecycle:
CANDIDATE -> EVALUATING -> APPROVED (or REJECTED) -> RETIRED. Reuses
`avishkar_evaluation`'s real `EvalSuite`/`run_suite()`/
`passes_threshold()` for the EVALUATE step -- not a second scoring
system. `evaluate()` requires the caller to supply a real `subject_fn`
(how to actually exercise the candidate skill, typically a delegation
through the existing `Orchestrator`) and a real `Scorer` -- there is no
internal fake scoring.

This directly avoids the exact failure this mission's forensic audit
found in GENESIS's own `core/skill_engine.py`: a `learned: bool` field
on every skill that is **never set to True anywhere in that codebase**
-- i.e. a data model implying a learning loop with no learning loop
behind it. Here, `status` only ever becomes `APPROVED` as the direct,
observable result of a real `run_suite()` call clearing a real
threshold -- never a flag flipped for its own sake.
"""

from __future__ import annotations

import dataclasses
import datetime
import threading
import time
from typing import Any, Callable, Dict, Optional, Tuple

from avishkar_evaluation import EvalSuite, Scorer, passes_threshold, run_suite

from .errors import LaylaError
from .memory_policy import LaylaMemoryPolicy
from .types import RISK_LOW

_KIND = "long_term"
_INDEX_KEY = "skill:__index__"

SKILL_CANDIDATE = "CANDIDATE"
SKILL_EVALUATING = "EVALUATING"
SKILL_APPROVED = "APPROVED"
SKILL_REJECTED = "REJECTED"
SKILL_RETIRED = "RETIRED"


class SkillNotFoundError(LaylaError):
    """No Skill with the given id exists."""


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


@dataclasses.dataclass(frozen=True)
class Skill:
    id: str
    name: str
    version: int
    purpose: str
    required_capability: str
    input_template: str
    status: str = SKILL_CANDIDATE
    risk_level: str = RISK_LOW
    eval_average: Optional[float] = None
    eval_case_count: Optional[int] = None
    eval_threshold: Optional[float] = None
    execution_count: int = 0
    success_count: int = 0
    created_at: str = ""
    updated_at: str = ""
    provenance: str = "user"


class SkillRegistry:
    def __init__(self, memory: LaylaMemoryPolicy, *, clock: Callable[[], float] = time.time) -> None:
        self._memory = memory
        self._clock = clock
        self._lock = threading.Lock()  # ADR-0024 discipline: guards the index read-modify-write

    def _key(self, skill_id: str) -> str:
        return f"skill:{skill_id}"

    def _save(self, skill: Skill) -> None:
        self._memory.remember(_KIND, self._key(skill.id), dataclasses.asdict(skill), provenance="skill-registry")
        with self._lock:
            index_record = self._memory.recall(_KIND, _INDEX_KEY)
            ids = set(index_record.value) if index_record else set()
            ids.add(skill.id)
            self._memory.remember(_KIND, _INDEX_KEY, sorted(ids), provenance="skill-registry")

    def propose(
        self, name: str, purpose: str, required_capability: str, input_template: str, *,
        risk_level: str = RISK_LOW, provenance: str = "user",
    ) -> Skill:
        """DISCOVER/LEARN -> CANDIDATE. Never auto-approved."""
        now = _now()
        skill = Skill(
            id=f"skill-{name}-v1", name=name, version=1, purpose=purpose,
            required_capability=required_capability, input_template=input_template,
            status=SKILL_CANDIDATE, risk_level=risk_level, created_at=now, updated_at=now, provenance=provenance,
        )
        self._save(skill)
        return skill

    def evaluate(
        self, skill_id: str, suite: EvalSuite, subject_fn: Callable[[Any], str], scorer: Scorer, *,
        threshold: float = 0.7,
    ) -> Skill:
        """CANDIDATE -> EVALUATING -> APPROVED|REJECTED, via a real
        `avishkar_evaluation.run_suite()` call -- the caller supplies
        `subject_fn` (how the candidate skill is actually exercised,
        e.g. a real delegation through Orchestrator) and `scorer`; this
        method only orchestrates the real evaluation lifecycle and
        persists its real, observed result. No internal fake scoring.
        """
        skill = self.get(skill_id)
        if skill is None:
            raise SkillNotFoundError(f"no skill with id {skill_id!r}")
        report = run_suite(suite, subject_fn, scorer)
        approved = passes_threshold(report, threshold)
        updated = dataclasses.replace(
            skill, status=SKILL_APPROVED if approved else SKILL_REJECTED,
            eval_average=report.average, eval_case_count=len(report.scores), eval_threshold=threshold,
            updated_at=_now(),
        )
        self._save(updated)
        return updated

    def record_execution(self, skill_id: str, *, success: bool) -> Skill:
        skill = self.get(skill_id)
        if skill is None:
            raise SkillNotFoundError(f"no skill with id {skill_id!r}")
        updated = dataclasses.replace(
            skill, execution_count=skill.execution_count + 1,
            success_count=skill.success_count + (1 if success else 0), updated_at=_now(),
        )
        self._save(updated)
        return updated

    def retire(self, skill_id: str) -> Skill:
        skill = self.get(skill_id)
        if skill is None:
            raise SkillNotFoundError(f"no skill with id {skill_id!r}")
        updated = dataclasses.replace(skill, status=SKILL_RETIRED, updated_at=_now())
        self._save(updated)
        return updated

    def get(self, skill_id: str) -> Optional[Skill]:
        record = self._memory.recall(_KIND, self._key(skill_id))
        return Skill(**record.value) if record is not None else None

    def list_all(self) -> Tuple[Skill, ...]:
        index_record = self._memory.recall(_KIND, _INDEX_KEY)
        if index_record is None:
            return ()
        skills = (self.get(sid) for sid in index_record.value)
        return tuple(s for s in skills if s is not None)

    def list_approved(self) -> Tuple[Skill, ...]:
        return tuple(s for s in self.list_all() if s.status == SKILL_APPROVED)

    def resolve_for_capability(self, required_capability: str) -> Tuple[Skill, ...]:
        """Every APPROVED skill for a given capability -- what a
        Planner/DelegationEngine caller would consult before falling
        back to a fresh, un-templated request.
        """
        return tuple(s for s in self.list_approved() if s.required_capability == required_capability)
