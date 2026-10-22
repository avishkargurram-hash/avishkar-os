"""BGE-M3 embeddings via the local llama.cpp server (1024-d, normalized).
Unavailable embedder -> None, and callers fall back to lexical similarity."""

from __future__ import annotations

import json
import math
import re
import urllib.request
from typing import List, Optional, Sequence

DIM = 1024


class Embedder:
    def __init__(self, base_url: Optional[str], model: str = "local-embed", timeout: float = 30.0):
        self.base_url = base_url.rstrip("/") if base_url else None
        self.model = model
        self.timeout = timeout
        self.available = bool(self.base_url)

    def embed(self, texts: Sequence[str]) -> Optional[List[List[float]]]:
        if not self.available or not texts:
            return None
        body = json.dumps({"model": self.model, "input": [t[:4000] for t in texts]}).encode()
        req = urllib.request.Request(f"{self.base_url}/embeddings", data=body,
                                     headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:  # noqa: S310 -- local endpoint
                data = json.loads(r.read())
        except Exception:
            return None
        out = []
        for item in sorted(data.get("data", []), key=lambda d: d.get("index", 0)):
            v = item["embedding"]
            if v and isinstance(v[0], list):  # some servers return per-token vectors
                v = v[0]
            n = math.sqrt(sum(x * x for x in v)) or 1.0
            out.append([x / n for x in v])
        if len(out) != len(texts) or any(len(v) != DIM for v in out):
            return None
        return out


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def vec_literal(v: Sequence[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]"


_WORD = re.compile(r"[a-z0-9]+")
_STOP = frozenset("a an the of in on at to for and or is are was were be been by with from that this these those as it its into than then can could may might not no".split())


def tokens(text: str) -> set:
    return {w for w in _WORD.findall(text.lower()) if w not in _STOP and len(w) > 2}


def jaccard(a: str, b: str) -> float:
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)
