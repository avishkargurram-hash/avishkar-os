"""Core data types for the Template Framework. See CONTRACT.md SS1-2.

TemplateFile wraps `avishkar_prompt.PromptVersion` rather than
redefining a parallel "content + declared variables" type -- see
CONTRACT.md SS0 for why.
"""

from __future__ import annotations

import dataclasses
from typing import Dict, Tuple

from avishkar_prompt import PromptVersion

from .errors import DuplicateFileError


@dataclasses.dataclass(frozen=True)
class TemplateFile:
    """One file within a Template. See CONTRACT.md SS1."""

    relative_path: str
    spec: PromptVersion


@dataclasses.dataclass(frozen=True)
class Template:
    """A named, versioned collection of TemplateFiles. See CONTRACT.md SS2."""

    name: str
    version: str
    files: Tuple[TemplateFile, ...]

    def __post_init__(self) -> None:
        seen: Dict[str, bool] = {}
        for file in self.files:
            if file.relative_path in seen:
                raise DuplicateFileError(
                    f"template {self.name!r} v{self.version!r} has duplicate "
                    f"relative_path {file.relative_path!r}"
                )
            seen[file.relative_path] = True
