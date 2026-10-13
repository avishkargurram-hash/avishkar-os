"""TemplateRegistry. See CONTRACT.md SS3."""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from .errors import DuplicateVersionError, UnknownVersionError
from .types import Template


class TemplateRegistry:
    """Holds named templates, each an ordered list of immutable
    Template versions. Same shape as prompt-factory's PromptRegistry.
    """

    def __init__(self) -> None:
        self._versions: Dict[str, List[Template]] = {}

    def register(self, name: str, template: Template) -> None:
        existing = self._versions.setdefault(name, [])
        if any(t.version == template.version for t in existing):
            raise DuplicateVersionError(
                f"template {name!r} already has a version {template.version!r}"
            )
        existing.append(template)

    def versions(self, name: str) -> Tuple[str, ...]:
        self._require_known(name)
        return tuple(t.version for t in self._versions[name])

    def get(self, name: str, version: Optional[str] = None) -> Template:
        self._require_known(name)
        candidates = self._versions[name]
        if version is None:
            return candidates[-1]
        for candidate in candidates:
            if candidate.version == version:
                return candidate
        raise UnknownVersionError(f"template {name!r} has no version {version!r}")

    def _require_known(self, name: str) -> None:
        if name not in self._versions:
            raise UnknownVersionError(f"no template registered under name {name!r}")
