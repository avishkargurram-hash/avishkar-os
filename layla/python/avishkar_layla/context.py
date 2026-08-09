"""ContextBuilder. See CONTRACT.md SS13.

A pure composer over LaylaMemoryPolicy (Phase 5, via SS2) and real
knowledge-factory KnowledgeBases (Phase 6) -- it does not decide what's
relevant beyond what the caller asks it to look up.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Sequence, Tuple

from avishkar_knowledge import KnowledgeBase

from .memory_policy import LaylaMemoryPolicy
from .types import LaylaTask


class ContextBuilder:
    def build(
        self,
        task: LaylaTask,
        memory: LaylaMemoryPolicy,
        *,
        memory_lookups: Sequence[Tuple[str, str]] = (),
        knowledge_bases: Sequence[KnowledgeBase] = (),
        knowledge_top_k: int = 3,
    ) -> Mapping[str, Any]:
        """`memory_lookups` is a sequence of (kind, key) pairs the caller
        wants pulled in (e.g. a user's known preferences) -- this
        method does not guess which memories matter.
        """
        context: Dict[str, Any] = {"task_input": task.input}

        memories = {}
        for kind, key in memory_lookups:
            record = memory.recall(kind, key)
            if record is not None:
                memories[f"{kind}:{key}"] = record.value
        context["memories"] = memories

        knowledge_results = []
        for kb in knowledge_bases:
            knowledge_results.extend(kb.search(task.input, top_k=knowledge_top_k))
        context["knowledge"] = tuple(knowledge_results)

        return context
