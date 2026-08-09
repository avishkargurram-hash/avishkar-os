"""Additional real scorers, extending prompt-factory's scoring seam.
See CONTRACT.md SS3.
"""

from __future__ import annotations

from typing import Mapping

from .types import EvalCase


def length_bounds_scorer(min_length: int, max_length: int):
    """Returns a Scorer: 1.0 if len(rendered) is within [min_length,
    max_length], else 0.0.
    """

    def score(rendered: str, case: EvalCase) -> float:
        return 1.0 if min_length <= len(rendered) <= max_length else 0.0

    return score


def weighted_keyword_scorer(weights: Mapping[str, float]):
    """Returns a Scorer: sum of weights for keywords present
    (case-insensitive) in `rendered`, normalized by the sum of all
    weights. Ignores `case.expected` -- weights are fixed per scorer
    instance, since not every case needs a different weighting.
    Generalizes prompt-factory's unweighted keyword_presence_scorer.
    """

    total_weight = sum(weights.values())

    def score(rendered: str, case: EvalCase) -> float:
        if total_weight == 0:
            return 1.0
        lowered = rendered.lower()
        matched = sum(weight for keyword, weight in weights.items() if keyword.lower() in lowered)
        return matched / total_weight

    return score
