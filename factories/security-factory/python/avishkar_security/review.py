"""Running the checklist. See CONTRACT.md SS2."""

from __future__ import annotations

from typing import Mapping, Optional

from .checklist import SECURITY_CHECKLIST
from .errors import MissingAnswerError, UnknownChecklistItemError
from .types import ChecklistResult, ReviewReport


def run_checklist(
    subject: str,
    answers: Mapping[str, bool],
    notes: Optional[Mapping[str, str]] = None,
) -> ReviewReport:
    notes = notes or {}
    known_ids = {item.id for item in SECURITY_CHECKLIST}

    unknown = set(answers) - known_ids
    if unknown:
        raise UnknownChecklistItemError(f"unknown checklist item id(s): {sorted(unknown)}")

    missing = known_ids - set(answers)
    if missing:
        raise MissingAnswerError(f"missing answer(s) for checklist item id(s): {sorted(missing)}")

    results = tuple(
        ChecklistResult(item_id=item.id, passed=answers[item.id], note=notes.get(item.id, ""))
        for item in SECURITY_CHECKLIST
    )
    return ReviewReport(subject=subject, results=results)
