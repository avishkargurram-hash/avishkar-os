"""PromptRegistry. See CONTRACT.md SS3."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Tuple

from .errors import DuplicateVersionError, UnknownVersionError
from .render import render as _render
from .types import PromptVersion


class PromptRegistry:
    """Holds named prompts, each an ordered list of immutable
    PromptVersions.
    """

    def __init__(self) -> None:
        self._versions: Dict[str, List[PromptVersion]] = {}

    def register(self, name: str, version: PromptVersion) -> None:
        existing = self._versions.setdefault(name, [])
        if any(v.version == version.version for v in existing):
            raise DuplicateVersionError(
                f"prompt {name!r} already has a version {version.version!r}"
            )
        existing.append(version)

    def versions(self, name: str) -> Tuple[str, ...]:
        self._require_known(name)
        return tuple(v.version for v in self._versions[name])

    def get(self, name: str, version: Optional[str] = None) -> PromptVersion:
        self._require_known(name)
        candidates = self._versions[name]
        if version is None:
            return candidates[-1]
        for candidate in candidates:
            if candidate.version == version:
                return candidate
        raise UnknownVersionError(f"prompt {name!r} has no version {version!r}")

    def render(self, name: str, values: Mapping[str, Any], version: Optional[str] = None) -> str:
        return _render(self.get(name, version), values)

    def _require_known(self, name: str) -> None:
        if name not in self._versions:
            raise UnknownVersionError(f"no prompt registered under name {name!r}")
