"""Two caches in front of the models (spec section 25):

* result cache  -- exact (purpose, chain, prompt) match, all tiers.
* semantic cache -- pgvector cosine >= 0.97 within the same purpose, used
  only for Tier 3+ where a hit actually saves money."""

from __future__ import annotations

import hashlib
import json
from typing import Optional

from ..storage.db import J
from .embed import vec_literal

SEMANTIC_THRESHOLD = 0.97


def result_key(purpose: str, chain: str, messages: list) -> str:
    return hashlib.sha256(json.dumps([purpose, chain, messages], sort_keys=True).encode()).hexdigest()


def get_result(conn, key: str) -> Optional[dict]:
    r = conn.execute("SELECT response FROM result_cache WHERE key=%s", (key,)).fetchone()
    return r["response"] if r else None


def put_result(conn, key: str, purpose: str, response: dict) -> None:
    conn.execute("INSERT INTO result_cache(key, purpose, response) VALUES (%s,%s,%s) ON CONFLICT (key) DO NOTHING",
                 (key, purpose, J(response)))


def get_semantic(conn, purpose: str, embedding) -> Optional[dict]:
    r = conn.execute(
        "SELECT response, 1 - (embedding <=> %s::vector) AS sim FROM semantic_cache WHERE purpose=%s "
        "ORDER BY embedding <=> %s::vector LIMIT 1",
        (vec_literal(embedding), purpose, vec_literal(embedding))).fetchone()
    if r and r["sim"] is not None and r["sim"] >= SEMANTIC_THRESHOLD:
        return r["response"]
    return None


def put_semantic(conn, purpose: str, prompt_hash: str, embedding, response: dict) -> None:
    conn.execute(
        "INSERT INTO semantic_cache(purpose, prompt_hash, embedding, response) VALUES (%s,%s,%s::vector,%s) "
        "ON CONFLICT (purpose, prompt_hash) DO NOTHING",
        (purpose, prompt_hash, vec_literal(embedding), J(response)))
