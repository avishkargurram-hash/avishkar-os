"""Core data types for the Evaluation Framework. See CONTRACT.md SS0-1.

EvalCase/EvalReport/RegressionResult/Scorer are reused verbatim from
avishkar_prompt rather than redefined -- one canonical scoring
vocabulary shared by prompts, agents, and workflows. See CONTRACT.md SS0.
"""

from __future__ import annotations

import dataclasses
from typing import Tuple

from avishkar_prompt import EvalCase, EvalReport, RegressionResult, Scorer

__all__ = ["EvalCase", "EvalReport", "RegressionResult", "Scorer", "EvalSuite"]


@dataclasses.dataclass(frozen=True)
class EvalSuite:
    """A named, reusable collection of EvalCases. See CONTRACT.md SS1."""

    name: str
    cases: Tuple[EvalCase, ...]
