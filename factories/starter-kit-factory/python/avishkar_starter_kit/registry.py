"""StarterKitRegistry. See CONTRACT.md SS2."""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from .errors import DuplicateVersionError, UnknownVersionError
from .types import StarterKit


class StarterKitRegistry:
    """Holds named starter kits, each an ordered list of immutable
    versions. Same shape as prompt-factory's PromptRegistry and
    template-factory's TemplateRegistry.
    """

    def __init__(self) -> None:
        self._versions: Dict[str, List[StarterKit]] = {}

    def register(self, name: str, kit: StarterKit) -> None:
        existing = self._versions.setdefault(name, [])
        if any(k.version == kit.version for k in existing):
            raise DuplicateVersionError(
                f"starter kit {name!r} already has a version {kit.version!r}"
            )
        existing.append(kit)

    def versions(self, name: str) -> Tuple[str, ...]:
        self._require_known(name)
        return tuple(k.version for k in self._versions[name])

    def get(self, name: str, version: Optional[str] = None) -> StarterKit:
        self._require_known(name)
        candidates = self._versions[name]
        if version is None:
            return candidates[-1]
        for candidate in candidates:
            if candidate.version == version:
                return candidate
        raise UnknownVersionError(f"starter kit {name!r} has no version {version!r}")

    def _require_known(self, name: str) -> None:
        if name not in self._versions:
            raise UnknownVersionError(f"no starter kit registered under name {name!r}")
