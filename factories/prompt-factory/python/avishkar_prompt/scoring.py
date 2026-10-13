"""Scoring seam + two real built-in scorers. See CONTRACT.md SS4-5.

`Scorer` is deliberately just a plain Callable -- the seam Phase 11's
evaluation-factory extends with richer scorers, not this framework's
job to build out fully. See CONTRACT.md SS4 for the precedent this
follows.
"""

from __future__ import annotations

from typing import Callable, Sequence

from .registry import PromptRegistry
from .types import EvalCase, EvalReport, RegressionResult

Scorer = Callable[[str, EvalCase], float]


def exact_match_scorer(rendered: str, case: EvalCase) -> float:
    """1.0 if the rendered text equals `case.expected` exactly, else 0.0."""

    return 1.0 if rendered == case.expected else 0.0


def keyword_presence_scorer(rendered: str, case: EvalCase) -> float:
    """Fraction of `case.expected` (an iterable of required keywords)
    that appear in `rendered`, case-insensitive. 1.0 if all are present,
    0.0 if none are, proportional in between.
    """

    keywords = list(case.expected)
    if not keywords:
        return 1.0
    lowered = rendered.lower()
    hits = sum(1 for kw in keywords if kw.lower() in lowered)
    return hits / len(keywords)


def evaluate_version(
    registry: PromptRegistry,
    name: str,
    version: str,
    cases: Sequence[EvalCase],
    scorer: Scorer,
) -> EvalReport:
    scores = tuple(
        scorer(registry.render(name, case.inputs, version=version), case) for case in cases
    )
    average = sum(scores) / len(scores) if scores else 0.0
    return EvalReport(scores=scores, average=average)


def compare_versions(report_a: EvalReport, report_b: EvalReport) -> RegressionResult:
    """Is `report_b` better than `report_a`? See CONTRACT.md SS5."""

    delta = report_b.average - report_a.average
    return RegressionResult(improved=delta > 0, delta=delta)
