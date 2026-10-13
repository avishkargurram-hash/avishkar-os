"""Suite running + threshold gating. See CONTRACT.md SS2."""

from __future__ import annotations

from typing import Callable

from .errors import EmptyCaseSetError
from .types import EvalCase, EvalReport, EvalSuite, Scorer


def run_suite(suite: EvalSuite, subject_fn: Callable[[EvalCase], str], scorer: Scorer) -> EvalReport:
    if not suite.cases:
        raise EmptyCaseSetError(f"eval suite {suite.name!r} has no cases")

    scores = tuple(scorer(subject_fn(case), case) for case in suite.cases)
    return EvalReport(scores=scores, average=sum(scores) / len(scores))


def passes_threshold(report: EvalReport, threshold: float) -> bool:
    return report.average >= threshold
