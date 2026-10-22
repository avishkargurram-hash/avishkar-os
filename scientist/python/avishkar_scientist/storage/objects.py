"""Content-addressed object store for large artifacts (document text,
experiment stdout, reports). Postgres keeps the sha256; the bytes live
on disk under objects/ab/cdef... so identical content is stored once."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path


class ObjectStore:
    def __init__(self, root: str):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, digest: str) -> Path:
        return self.root / digest[:2] / digest[2:]

    def put(self, data: bytes | str) -> str:
        if isinstance(data, str):
            data = data.encode("utf-8")
        digest = hashlib.sha256(data).hexdigest()
        p = self._path(digest)
        if not p.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_suffix(".tmp%d" % os.getpid())
            tmp.write_bytes(data)
            os.replace(tmp, p)
        return digest

    def get(self, digest: str) -> bytes:
        return self._path(digest).read_bytes()

    def get_text(self, digest: str) -> str:
        return self.get(digest).decode("utf-8", errors="replace")

    def exists(self, digest: str) -> bool:
        return self._path(digest).exists()
