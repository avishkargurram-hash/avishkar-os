"""Knowledge Framework -- quickstart.

Ingests two documents, searches with a natural-language query, and wraps
the knowledge base as a real Tool a ChiefDomainAgent can register. Run
directly:

    python factories/knowledge-factory/examples/quickstart.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_ROOT / "core" / "python"))
sys.path.insert(0, str(_ROOT / "router" / "python"))
sys.path.insert(0, str(_ROOT / "factories" / "agent-factory" / "python"))
sys.path.insert(0, str(_ROOT / "factories" / "knowledge-factory" / "python"))

from avishkar_agent import ToolRegistry  # noqa: E402
from avishkar_knowledge import KnowledgeBase, as_tool  # noqa: E402


def main() -> None:
    kb = KnowledgeBase(chunk_size=40, overlap=5)

    kb.ingest(
        "deploy-policy",
        "All production deploys require a passing test suite, a code review "
        "from a second engineer, and must happen on a weekday before 4pm.",
    )
    kb.ingest(
        "onboarding",
        "New engineers get repo access on day one, a laptop by day two, and "
        "should ship their first small PR within the first week.",
    )

    print("1. Keyword-overlap search across two documents (offline, stdlib-only embedding):")
    # A distinctive query (shares vocabulary with exactly one document)
    # is deliberate: HashingEmbedder is a real but crude bag-of-words
    # baseline with no stopword removal or TF-IDF weighting, so an
    # ambiguous query built mostly from common words CAN rank the wrong
    # document first -- see README.md Limitations. This isn't hidden;
    # it's why the framework documents an upgrade path to real
    # embeddings rather than claiming state-of-the-art search today.
    results = kb.search("production deploy review requirements")
    for r in results:
        print(f"   score={r.score:.3f} doc={r.chunk.document_id}: {r.chunk.text[:60]}...")
    print()

    print("2. Wrapped as a real Tool an agent can register:")
    tool = as_tool(kb, name="search_company_policies")
    registry = ToolRegistry()
    registry.register(tool)
    output = registry.call("search_company_policies", "production deploy test suite review")
    print(f"   registry.call(...) -> {output[0]['text'][:70]}...")


if __name__ == "__main__":
    main()
