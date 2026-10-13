"""FileMemoryPolicy -- one JSON file per memory kind, durable across
process restarts. Implements avishkar_agent.MemoryPolicy verbatim (no
new interface -- see CONTRACT.md).

Concurrency (Priority 17.4 platform-wide hardening pass, ADR-0024): a
per-instance lock guards every operation. remember()/forget() are a
load-the-whole-file, mutate, write-the-whole-file-back cycle -- without
a lock, two concurrent remember() calls for the SAME kind (even for
two entirely DIFFERENT keys) would both load the same on-disk snapshot,
each add their own key in memory, and whichever writes last would
silently discard the other's key entirely (a classic lost update, not
just a theoretical race). This is a narrow, additive exception to
memory-factory's Phase 5 "locked" status -- justified because the
Phase 17 directive explicitly names Memory as an audit/harden target,
and because the fix changes nothing about single-process, single-
threaded behavior (every existing test still passes unmodified).

Explicitly NOT fixed here: cross-process safety. This lock only
serializes callers within one Python process; two separate OS
processes writing the same root_dir concurrently can still race (no
OS-level file locking is used). See README.md Limitations.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Dict, Optional, Union

from avishkar_agent import MemoryPolicy

from ..errors import InvalidMemoryKindError

_KINDS = ("short_term", "long_term", "episodic", "semantic")


class FileMemoryPolicy(MemoryPolicy):
    def __init__(self, root_dir: Union[str, Path]) -> None:
        self._root = Path(root_dir)
        self._root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

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
        with self._lock:
            data = self._load(kind)
            data[key] = value
            self._save(kind, data)

    def recall(self, kind: str, key: str) -> Optional[Any]:
        with self._lock:
            return self._load(kind).get(key)

    def forget(self, kind: str, key: str) -> None:
        with self._lock:
            data = self._load(kind)
            if key in data:
                del data[key]
                self._save(kind, data)

    def list_keys(self, kind: str) -> tuple:
        """Extra capability beyond the MemoryPolicy interface -- useful
        for inspection/debugging, not required by any consumer.
        """
        with self._lock:
            return tuple(self._load(kind).keys())
