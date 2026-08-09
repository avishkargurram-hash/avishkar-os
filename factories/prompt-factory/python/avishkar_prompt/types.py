"""Core data types for the Prompt Framework. See CONTRACT.md SS1, SS4."""

from __future__ import annotations

import dataclasses
import string
from typing import Any, Mapping, Optional, Tuple

from .errors import UnknownVariableError

_FORMATTER = string.Formatter()


def _template_field_names(template: str) -> Tuple[str, ...]:
    """Every `{name}` placeholder actually present in a str.format-style
    template, in first-appearance order, de-duplicated.
    """

    seen: list = []
    for _, field_name, _, _ in _FORMATTER.parse(template):
        if field_name and field_name not in seen:
            seen.append(field_name)
    return tuple(seen)


@dataclasses.dataclass(frozen=True)
class PromptVariable:
    name: str
    description: str = ""
    required: bool = True


@dataclasses.dataclass(frozen=True)
class PromptVersion:
    """A single, immutable version of a prompt. See CONTRACT.md SS1."""

    version: str
    template: str
    variables: Tuple[PromptVariable, ...] = ()
    target_models: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        declared = {v.name for v in self.variables}
        used = set(_template_field_names(self.template))
        unknown = used - declared
        if unknown:
            raise UnknownVariableError(
                f"template references undeclared variable(s) {sorted(unknown)} "
                f"in prompt version {self.version!r}"
            )

    @property
    def variable_names(self) -> Tuple[str, ...]:
        return tuple(v.name for v in self.variables)

    @property
    def required_variable_names(self) -> Tuple[str, ...]:
        return tuple(v.name for v in self.variables if v.required)


@dataclasses.dataclass(frozen=True)
class EvalCase:
    """One test case for scoring a rendered prompt. See CONTRACT.md SS4."""

    inputs: Mapping[str, Any]
    expected: Any = None


@dataclasses.dataclass(frozen=True)
class EvalReport:
    scores: Tuple[float, ...]
    average: float


@dataclasses.dataclass(frozen=True)
class RegressionResult:
    improved: bool
    delta: float
