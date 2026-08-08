"""FileMemoryPolicy -- one JSON file per memory kind, durable across
process restarts. Implements avishkar_agent.MemoryPolicy verbatim (no
new interface -- see CONTRACT.md).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional, Union

from avishkar_agent import MemoryPolicy

from ..errors import InvalidMemoryKindError

_KINDS = ("short_term", "long_term", "episodic", "semantic")


class FileMemoryPolicy(MemoryPolicy):
    def __init__(self, root_dir: Union[str, Path]) -> None:
        self._root = Path(root_dir)
        self._root.mkdir(parents=True, exist_ok=True)

    def _path_for(self, kind: str) -> Path:
        if kind not in _KINDS:
            raise InvalidMemoryKindError(f"Unknown memory kind '{kind}' -- expected one of {_KINDS}")
        return self._root / f"{kind}.json"

    def _load(self, kind: str) -> Dict[str, Any]:
        path = self._path_for(kind)
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def _save(self, kind: str, data: Dict[str, Any]) -> None:
        self._path_for(kind).write_text(json.dumps(data, indent=2), encoding="utf-8")

    def remember(self, kind: str, key: str, value: Any) -> None:
        data = self._load(kind)
        data[key] = value
        self._save(kind, data)

    def recall(self, kind: str, key: str) -> Optional[Any]:
        return self._load(kind).get(key)

    def forget(self, kind: str, key: str) -> None:
        data = self._load(kind)
        if key in data:
            del data[key]
            self._save(kind, data)

    def list_keys(self, kind: str) -> tuple:
        """Extra capability beyond the MemoryPolicy interface -- useful
        for inspection/debugging, not required by any consumer.
        """
        return tuple(self._load(kind).keys())
