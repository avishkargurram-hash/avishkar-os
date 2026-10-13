"""Agent Integration -- wraps a KnowledgeBase as an avishkar_agent.Tool,
the way agent template SS11 (Knowledge Sources) expects a ChiefDomainAgent
to reach a knowledge base. See CONTRACT.md SS2.
"""

from __future__ import annotations

from avishkar_agent import Tool

from .knowledge_base import KnowledgeBase


def as_tool(kb: KnowledgeBase, *, name: str = "search_knowledge", top_k: int = 5) -> Tool:
    def _call(query: str):
        results = kb.search(query, top_k=top_k)
        return [{"text": r.chunk.text, "score": r.score, "document_id": r.chunk.document_id} for r in results]

    return Tool(name=name, call=_call, description="Search this agent's knowledge base for relevant context.")
