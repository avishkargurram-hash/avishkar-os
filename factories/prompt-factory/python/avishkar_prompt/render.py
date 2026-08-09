"""Rendering. See CONTRACT.md SS2."""

from __future__ import annotations

from typing import Any, Mapping

from .errors import MissingVariableError
from .types import PromptVersion


def render(version: PromptVersion, values: Mapping[str, Any]) -> str:
    missing = [name for name in version.required_variable_names if name not in values]
    if missing:
        raise MissingVariableError(
            f"prompt version {version.version!r} is missing required variable(s): {missing}"
        )
    # Only pass declared variables through -- extra keys in `values` (a
    # shared context dict reused across several prompts) are ignored
    # rather than rejected, per CONTRACT.md SS2.
    relevant = {name: values[name] for name in version.variable_names if name in values}
    return version.template.format(**relevant)
