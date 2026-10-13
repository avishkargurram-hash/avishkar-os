"""ThinkingModel -- named cognitive strategies a ChiefDomainAgent applies
during planning and reflection. See CONTRACT.md SS5 and SS6 of the agent
template.

Shipped reference strategies are deliberately simple, deterministic
structuring functions -- they shape *how a prompt to the model is framed*,
not a separate reasoning engine. The actual intelligence still comes from
the model call the reasoning loop makes via Router; a ThinkingModel's job
is to make that call ask the right kind of question.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Callable, Mapping

from .types import Task, ThinkingStep


@dataclasses.dataclass(frozen=True)
class ThinkingModel:
    name: str
    apply: Callable[[Task, Mapping[str, Any]], ThinkingStep]


def _first_principles(task: Task, context: Mapping[str, Any]) -> ThinkingStep:
    content = (
        f"Breaking '{task.input}' down to its fundamental constraints and "
        f"requirements, ignoring how similar problems are usually solved, "
        f"then rebuilding a solution from those fundamentals up."
    )
    return ThinkingStep(strategy="first_principles", content=content)


def _systems_thinking(task: Task, context: Mapping[str, Any]) -> ThinkingStep:
    content = (
        f"Mapping '{task.input}' as a system: its components, the "
        f"feedback loops between them, and second-order effects a purely "
        f"local fix would miss."
    )
    return ThinkingStep(strategy="systems_thinking", content=content)


def _scientific_method(task: Task, context: Mapping[str, Any]) -> ThinkingStep:
    content = (
        f"Forming a testable hypothesis about '{task.input}', identifying "
        f"what evidence would confirm or falsify it, and preferring the "
        f"explanation that best survives that evidence."
    )
    return ThinkingStep(strategy="scientific_method", content=content)


def _decision_matrix(task: Task, context: Mapping[str, Any]) -> ThinkingStep:
    criteria = context.get("decision_criteria", ("correctness", "cost", "maintainability"))
    content = (
        f"Weighing the candidate approaches to '{task.input}' against: "
        f"{', '.join(criteria)} -- selecting the option with the best "
        f"weighted score, not just the first one that works."
    )
    return ThinkingStep(strategy="decision_matrix", content=content)


FIRST_PRINCIPLES = ThinkingModel(name="first_principles", apply=_first_principles)
SYSTEMS_THINKING = ThinkingModel(name="systems_thinking", apply=_systems_thinking)
SCIENTIFIC_METHOD = ThinkingModel(name="scientific_method", apply=_scientific_method)
DECISION_MATRIX = ThinkingModel(name="decision_matrix", apply=_decision_matrix)

DEFAULT_THINKING_MODELS = (FIRST_PRINCIPLES, SYSTEMS_THINKING, SCIENTIFIC_METHOD, DECISION_MATRIX)
