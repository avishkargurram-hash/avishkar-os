"""ResultValidator, ConflictResolver, ExecutiveSynthesizer. See
CONTRACT.md SS6.

ConflictResolver reuses avishkar_knowledge.HashingEmbedder (Phase 6) to
turn each delegated result's output into a comparable vector -- cosine
similarity itself is three lines of arithmetic, not a "framework," so
it's computed locally rather than reaching into knowledge-factory's
private _cosine_similarity helper.
"""

from __future__ import annotations

import math
from typing import Optional, Sequence, Tuple

from avishkar_knowledge import HashingEmbedder

from .errors import UnresolvedConflictError
from .types import Conflict, DelegationRecord, ValidationReport


def _cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


class ResultValidator:
    def validate(self, records: Sequence[DelegationRecord]) -> ValidationReport:
        failing = tuple(r.step_id for r in records if r.status != "completed")
        return ValidationReport(all_completed=not failing, failing=failing)


class ConflictResolver:
    """Detects disagreement among completed delegated results. See
    CONTRACT.md SS6.
    """

    def __init__(self, *, embedder: Optional[HashingEmbedder] = None, agreement_threshold: float = 0.2) -> None:
        self._embedder = embedder or HashingEmbedder()
        self._agreement_threshold = agreement_threshold

    def detect(self, records: Sequence[DelegationRecord]) -> Tuple[Conflict, ...]:
        completed = [r for r in records if r.status == "completed" and r.output]
        conflicts = []
        for i in range(len(completed)):
            for j in range(i + 1, len(completed)):
                a, b = completed[i], completed[j]
                similarity = _cosine_similarity(self._embedder.embed(a.output), self._embedder.embed(b.output))
                if similarity < self._agreement_threshold:
                    conflicts.append(Conflict(
                        step_ids=(a.step_id, b.step_id),
                        reason=f"low agreement between '{a.agent_name}' and '{b.agent_name}' "
                               f"(similarity={similarity:.2f} < threshold={self._agreement_threshold})",
                    ))
        return tuple(conflicts)


class ExecutiveSynthesizer:
    """Combines delegated results into one executive summary. Refuses
    to silently pick a side when conflicts exist and no resolution was
    given -- see CONTRACT.md SS6 and Part V's "do not silently choose
    an answer when confidence is insufficient."
    """

    def synthesize(
        self, records: Sequence[DelegationRecord], conflicts: Sequence[Conflict], *, allow_unresolved: bool = False
    ) -> str:
        if conflicts and not allow_unresolved:
            raise UnresolvedConflictError(
                f"{len(conflicts)} unresolved conflict(s) among delegated results -- "
                f"resolve them or pass allow_unresolved=True to synthesize anyway"
            )
        completed = [r for r in records if r.status == "completed" and r.output]
        if not completed:
            return "No delegated work completed successfully."
        return "\n".join(f"[{r.agent_name}]: {r.output}" for r in completed)
