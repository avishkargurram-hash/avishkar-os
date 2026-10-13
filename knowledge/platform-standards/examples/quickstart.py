"""Platform Standards knowledge base -- quickstart.

Demonstrates a real, product-facing KnowledgeBase any product built on
Avishkar OS can import to give its own agents awareness of this
platform's own conventions. Run directly:

    python knowledge/platform-standards/examples/quickstart.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
for rel in (
    "core/python", "router/python", "factories/agent-factory/python",
    "factories/knowledge-factory/python", "knowledge/platform-standards/python",
):
    sys.path.insert(0, str(_ROOT / rel))

from platform_standards_kb import build_platform_standards_kb  # noqa: E402


def main() -> None:
    kb = build_platform_standards_kb()

    print(f"1. Loaded {len(kb)} platform-standards chunks.\n")

    print("2. Search for engineering principles guidance:")
    for r in kb.search("does this already exist somewhere DRY reuse", top_k=1):
        print(f"   score={r.score:.3f} doc={r.chunk.document_id}: {r.chunk.text[:80]}...\n")

    print("3. Search for security guidance:")
    for r in kb.search("secrets credentials committed API keys", top_k=1):
        print(f"   score={r.score:.3f} doc={r.chunk.document_id}: {r.chunk.text[:80]}...")


if __name__ == "__main__":
    main()
